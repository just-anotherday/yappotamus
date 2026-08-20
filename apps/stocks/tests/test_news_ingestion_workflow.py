"""Behavioral checks for the production news-ingestion workflow shell step."""

from __future__ import annotations

import json
import os
from collections import Counter
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import shutil
import subprocess
from threading import Thread
from urllib.parse import urlsplit

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
WORKFLOW_PATH = REPOSITORY_ROOT / ".github" / "workflows" / "stocks-news-ingest.yml"
TEST_TOKEN = "workflow-test-secret"


def _workflow_script() -> str:
    lines = WORKFLOW_PATH.read_text(encoding="utf-8").splitlines()
    run_index = lines.index("        run: |")
    body: list[str] = []
    for line in lines[run_index + 1 :]:
        if line.startswith("          "):
            body.append(line[10:])
        elif not line:
            body.append("")
        else:
            break
    return "\n".join(body)


def _bash_executable() -> str:
    if os.name == "nt":
        git_bash = Path(r"C:\Program Files\Git\bin\bash.exe")
        if git_bash.exists():
            return str(git_bash)
    discovered = shutil.which("bash")
    if discovered:
        return discovered
    pytest.skip("bash is required to exercise the GitHub Actions run block")


class _Scenario:
    def __init__(self, responses: dict[str, list[tuple[int, object]]]):
        self.responses = {path: list(items) for path, items in responses.items()}
        self.calls: Counter[tuple[str, str]] = Counter()
        self.authorization_headers: list[str | None] = []

    def respond(self, method: str, raw_path: str) -> tuple[int, bytes]:
        path = urlsplit(raw_path).path
        self.calls[(method, path)] += 1
        configured = self.responses.get(path, [])
        status, payload = configured.pop(0) if configured else (500, {"error": "unexpected call"})
        body = payload if isinstance(payload, str) else json.dumps(payload)
        return status, body.encode("utf-8")


@contextmanager
def _serve(scenario: _Scenario):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, _format, *_args):
            return

        def _respond(self, method: str):
            if method == "POST":
                scenario.authorization_headers.append(self.headers.get("Authorization"))
            status, body = scenario.respond(method, self.path)
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            self._respond("GET")

        def do_POST(self):
            self._respond("POST")

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def _run_workflow(scenario: _Scenario) -> subprocess.CompletedProcess[str]:
    with _serve(scenario) as api_url:
        environment = os.environ.copy()
        environment.update(
            {
                "STOCKS_API_URL": api_url,
                "STOCKS_INTERNAL_JOB_TOKEN": TEST_TOKEN,
                "FORCE_NEWS_INGEST": "false",
                "NEWS_TRIGGER_SCHEDULE": "",
                "NEWS_INGEST_HEALTH_RETRY_DELAY_SECONDS": "0",
                "NO_PROXY": "127.0.0.1,localhost",
                "no_proxy": "127.0.0.1,localhost",
            }
        )
        return subprocess.run(
            [_bash_executable(), "-e", "-o", "pipefail", "-c", _workflow_script()],
            cwd=REPOSITORY_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )


def test_workflow_wakes_then_checks_readiness_before_one_ingestion_post():
    scenario = _Scenario(
        {
            "/health/live": [
                (502, "<html>Render is starting</html>"),
                (200, {"status": "healthy"}),
            ],
            "/health/ready": [
                (503, {"status": "not_ready", "database": "unreachable"}),
                (200, {"status": "ready", "database": "reachable"}),
            ],
            "/internal/jobs/news-ingest": [(200, {"status": "completed"})],
        }
    )

    result = _run_workflow(scenario)

    assert result.returncode == 0, result.stdout + result.stderr
    assert scenario.calls[("GET", "/health/live")] == 2
    assert scenario.calls[("GET", "/health/ready")] == 2
    assert scenario.calls[("POST", "/internal/jobs/news-ingest")] == 1
    assert scenario.authorization_headers == [f"Bearer {TEST_TOKEN}"]
    assert "phase=wake attempt=1" in result.stdout
    assert "phase=readiness outcome=application_database_not_ready" in result.stdout
    assert "phase=ingestion attempt=1/1 curl_exit=0 http_status=200" in result.stdout
    assert TEST_TOKEN not in result.stdout + result.stderr


@pytest.mark.parametrize("status", [401, 403, 409, 424, 429, 500, 503])
def test_workflow_preserves_ingestion_http_failure_without_post_replay(status):
    scenario = _Scenario(
        {
            "/health/live": [(200, {"status": "healthy"})],
            "/health/ready": [(200, {"status": "ready", "database": "reachable"})],
            "/internal/jobs/news-ingest": [
                (status, {"error": {"status": "partial"}, "status_code": status}),
                (200, {"status": "completed"}),
            ],
        }
    )

    result = _run_workflow(scenario)

    assert result.returncode == 22, result.stdout + result.stderr
    assert scenario.calls[("POST", "/internal/jobs/news-ingest")] == 1
    assert f"phase=ingestion attempt=1/1 curl_exit=22 http_status={status}" in result.stdout
    assert f'"status_code": {status}' in result.stdout
    assert TEST_TOKEN not in result.stdout + result.stderr


def test_workflow_bounds_database_readiness_checks_and_never_posts_when_unready():
    scenario = _Scenario(
        {
            "/health/live": [(200, {"status": "healthy"})],
            "/health/ready": [
                (503, {"status": "not_ready", "database": "unreachable"}),
                (503, {"status": "not_ready", "database": "unreachable"}),
                (503, {"status": "not_ready", "database": "unreachable"}),
            ],
            "/internal/jobs/news-ingest": [(200, {"status": "completed"})],
        }
    )

    result = _run_workflow(scenario)

    assert result.returncode != 0
    assert scenario.calls[("GET", "/health/ready")] == 3
    assert scenario.calls[("POST", "/internal/jobs/news-ingest")] == 0
    assert "phase=readiness outcome=failed attempts=3" in result.stdout


def test_workflow_reports_expected_cadence_noop_as_success():
    scenario = _Scenario(
        {
            "/health/live": [(200, {"status": "healthy"})],
            "/health/ready": [(200, {"status": "ready", "database": "reachable"})],
            "/internal/jobs/news-ingest": [(200, {"status": "skipped_cadence"})],
        }
    )

    result = _run_workflow(scenario)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "phase=ingestion outcome=skipped_cadence" in result.stdout
    assert scenario.calls[("POST", "/internal/jobs/news-ingest")] == 1


def test_workflow_rejects_unexpected_success_body():
    scenario = _Scenario(
        {
            "/health/live": [(200, {"status": "healthy"})],
            "/health/ready": [(200, {"status": "ready", "database": "reachable"})],
            "/internal/jobs/news-ingest": [(200, {"status": "unknown"})],
        }
    )

    result = _run_workflow(scenario)

    assert result.returncode != 0
    assert "phase=ingestion outcome=unexpected_response_body http_status=200" in result.stdout
    assert scenario.calls[("POST", "/internal/jobs/news-ingest")] == 1


def test_workflow_bounds_large_gateway_response_body():
    large_gateway_body = "R" * 20_000
    scenario = _Scenario(
        {
            "/health/live": [
                (502, large_gateway_body),
                (200, {"status": "healthy"}),
            ],
            "/health/ready": [(200, {"status": "ready", "database": "reachable"})],
            "/internal/jobs/news-ingest": [(200, {"status": "completed"})],
        }
    )

    result = _run_workflow(scenario)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "response_body_bytes=20000" in result.stdout
    assert "response body truncated (20000 bytes total)" in result.stdout
    assert result.stdout.count("R") < 9_000


def test_workflow_uses_only_get_preflights_and_has_no_post_retry_flags():
    script = _workflow_script()

    assert 'wake_deadline=$((SECONDS + 180))' in script
    assert 'while [ "$readiness_attempt" -le 3 ]' in script
    assert script.count("--request POST") == 1
    assert "--request HEAD" not in script
    assert "--retry " not in script
    assert "--retry-all-errors" not in script
