"""Windows host integration tests using an isolated, non-production backend.

No DB/provider/model requests. Requires host access to process/listener metadata.
"""
import os
import re
from pathlib import Path
import shutil
import socket
import subprocess
import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows launcher")
STOCKS = Path(__file__).resolve().parents[1]

BACKEND = r'''
import argparse, os, threading, time
from pathlib import Path
from http.server import BaseHTTPRequestHandler, HTTPServer
p=argparse.ArgumentParser()
p.add_argument('--port',type=int); p.add_argument('--stop-file'); p.add_argument('--pid-file')
a=p.parse_args()
Path(a.pid_file).write_text(str(os.getpid()))
mode=os.getenv('TEST_BACKEND_MODE','ready')
if mode=='exit': raise SystemExit(9)
class Handler(BaseHTTPRequestHandler):
 def do_GET(self):
  self.send_response(200); self.send_header('Content-Type','application/json'); self.end_headers()
  self.wfile.write(b'{"status":"ready","database":"reachable"}')
 def log_message(self,*args): pass
if mode in ('timeout','stuck'):
 while mode=='stuck' or not Path(a.stop_file).exists(): time.sleep(.05)
else:
 if mode=='cleanup_failure': Path(a.stop_file).mkdir()
 server=HTTPServer(('127.0.0.1',a.port),Handler)
 def stop():
  while mode=='cleanup_failure' or not Path(a.stop_file).exists(): time.sleep(.05)
  server.shutdown()
 threading.Thread(target=stop,daemon=True).start()
 server.serve_forever(poll_interval=.05)
'''


@pytest.fixture
def sandbox(tmp_path):
    root = tmp_path / "repo with spaces" / "apps" / "stocks"
    scripts = root / "scripts"
    scripts.mkdir(parents=True)
    venv = root / ".venv"
    (venv / "Scripts").mkdir(parents=True)
    shutil.copy2(sys.executable, venv / "Scripts" / "python.exe")
    shutil.copy2(Path(sys.prefix) / "pyvenv.cfg", venv / "pyvenv.cfg")
    shutil.copy2(STOCKS / "scripts/run_daily_news_and_reports_task.ps1", scripts)
    (scripts / "run_task_backend.py").write_text(BACKEND)
    (scripts / "run_daily_news_and_reports.py").write_text(
        "import os; print('safe stub pipeline'); raise SystemExit(int(os.getenv('TEST_PIPELINE_EXIT','0')))"
    )
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    return root, port


def invoke(sandbox, **env):
    root, port = sandbox
    # Use a file: an intentionally surviving descendant can retain Windows
    # pipe handles after PowerShell exits and prevent communicate() reaching EOF.
    with (root / "test-launcher-output.log").open("wb") as output:
        result = subprocess.run([
            "powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
            "-File", str(root / "scripts/run_daily_news_and_reports_task.ps1"),
            "-BackendPort", str(port), "-BackendStartupTimeoutSeconds", "4",
            "-BackendShutdownTimeoutSeconds", "2",
        ], env={**os.environ, **env}, stdout=output, stderr=output, timeout=40)
    logs = root / "logs/daily-task"
    runner = max(logs.glob("*.runner.log"), key=lambda p: p.stat().st_mtime).read_text()
    return result.returncode, runner


@pytest.mark.parametrize("pipeline_exit", [0, 1, 2])
def test_pipeline_exit_and_owned_cleanup(sandbox, pipeline_exit):
    code, log = invoke(sandbox, TEST_PIPELINE_EXIT=str(pipeline_exit))
    assert code == pipeline_exit, log
    assert "backend_ready backend_server_pid=" in log
    assert "backend_shutdown_result=stopped" in log
    assert f"python_exit_code={pipeline_exit}" in log
    with socket.socket() as sock:
        assert sock.connect_ex(("127.0.0.1", sandbox[1])) != 0


@pytest.mark.parametrize("mode,reason", [("exit", "process_exited"), ("timeout", "readiness_timeout")])
def test_startup_failure_never_runs_pipeline(sandbox, mode, reason):
    code, log = invoke(sandbox, TEST_BACKEND_MODE=mode)
    assert code == 71, log
    assert f"backend_startup_failure={reason}" in log
    assert "pipeline_started" not in log
    assert "backend_shutdown_result=stopped" in log


def test_forced_cleanup_of_unresponsive_owned_backend(sandbox):
    code, log = invoke(sandbox, TEST_BACKEND_MODE="stuck")
    assert code == 71, log
    assert "backend_shutdown_forced=true" in log
    assert "backend_shutdown_result=stopped" in log


@pytest.mark.parametrize("pipeline_exit,expected", [(0, 72), (1, 1)])
def test_cleanup_failure_records_both_results(sandbox, pipeline_exit, expected):
    log = ""
    try:
        code, log = invoke(sandbox, TEST_BACKEND_MODE="cleanup_failure", TEST_PIPELINE_EXIT=str(pipeline_exit))
        assert code == expected, log
        assert "backend_shutdown_result=failed" in log
        assert f"pipeline_exit_code={pipeline_exit} cleanup_failed=true launcher_exit_code={expected}" in log
    finally:
        # This fixture deliberately blocks stop-file creation. Terminate only
        # the specific test-owned tree captured from its own isolated runner.
        if not log:
            logs = sandbox[0] / "logs/daily-task"
            log = max(logs.glob("*.runner.log"), key=lambda p: p.stat().st_mtime).read_text()
        match = re.search(r"backend_start_pid=(\d+)", log)
        if match:
            subprocess.run(["taskkill.exe", "/PID", match[1], "/T", "/F"], capture_output=True, timeout=10)


@pytest.mark.asyncio
@pytest.mark.parametrize("managed", [False, True])
async def test_task_managed_lifespan_does_not_start_other_schedulers(monkeypatch, managed):
    import asyncio
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, MagicMock
    from backend import main

    monkeypatch.setenv("STOCKS_TASK_MANAGED_BACKEND", "1" if managed else "0")
    monkeypatch.setattr(main, "settings", SimpleNamespace(
        NEWS_SCHEDULER_ENABLED=True, MEMORY_DIAGNOSTICS_ENABLED=False,
        AI_WORKER_POLL_INTERVAL_S=1, AI_WORKER_MAX_CONCURRENT=1,
    ))
    for name in ("init_db", "seed_defaults", "sync_watchlist_to_assets", "shutdown_hybrid_data_service"):
        monkeypatch.setattr(main, name, AsyncMock())
    monkeypatch.setattr(main, "get_all_tickers", AsyncMock(return_value=[]))
    monkeypatch.setattr(main, "async_session_factory", MagicMock())
    monkeypatch.setattr(main, "ticker_extractor", SimpleNamespace(load_tickers_from_db=AsyncMock()))
    monkeypatch.setattr(main, "configure_yfinance_cache", MagicMock())
    monkeypatch.setattr(main, "set_event_loop", MagicMock())
    monkeypatch.setattr(main, "MarketDataService", MagicMock())
    scheduler = MagicMock()
    monkeypatch.setattr(main, "start_scheduler", scheduler)
    monkeypatch.setattr(main, "stop_scheduler", MagicMock())
    worker = MagicMock(return_value=SimpleNamespace(start=AsyncMock(), stop=MagicMock()))
    monkeypatch.setattr(main, "AIWorker", worker)
    market = AsyncMock()
    post_market = AsyncMock()
    monkeypatch.setattr(main, "_daily_market_report_loop", market)
    monkeypatch.setattr(main, "_post_market_fetch_loop", post_market)
    app = SimpleNamespace(state=SimpleNamespace(connection_manager=MagicMock()))
    async with main.lifespan(app):
        await asyncio.sleep(0)
        assert worker.call_count == int(not managed)
        assert scheduler.call_count == int(not managed)
        assert market.call_count == int(not managed)
        assert post_market.call_count == int(not managed)
