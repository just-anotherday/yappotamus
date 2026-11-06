"""Focused coverage for the local daily workflow database preflight."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import asyncio
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock

import pytest


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "run_daily_news_and_reports.py"
)


def test_blocked_event_loop_startup_exits_with_diagnostics():
    code = f"""
import importlib.util
import sys
import time
spec = importlib.util.spec_from_file_location('blocked_daily_runner', {str(SCRIPT_PATH)!r})
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
runner.RUNTIME_STARTUP_TIMEOUT_SECONDS = 0.2
runner.asyncio.run = lambda coroutine: time.sleep(60)
sys.argv = ['daily_runner', '--preflight-only']
runner.main()
"""
    result = subprocess.run(
        [sys.executable, "-u", "-c", code], capture_output=True, text=True, timeout=20,
    )
    assert result.returncode != 0
    assert '"event": "runtime_startup_started"' in result.stdout
    assert "local socket access" in result.stdout
    assert "Timeout" in result.stderr
    assert "daily_pipeline_started" not in result.stdout


def test_startup_watchdog_is_cancelled_before_pipeline(daily_runner, monkeypatch, capsys):
    armed = []
    monkeypatch.setattr(daily_runner.faulthandler, "dump_traceback_later", lambda *a, **kw: armed.append(True))
    monkeypatch.setattr(daily_runner.faulthandler, "cancel_dump_traceback_later", lambda: armed.clear())
    monkeypatch.setattr(sys, "argv", ["daily_runner", "--preflight-only"])

    async def pipeline(**kwargs):
        assert not armed
        assert kwargs == {"dry_run": False, "preflight_only": True}
        return 0

    monkeypatch.setattr(daily_runner, "run", pipeline)
    assert daily_runner.main() == 0
    assert not armed


@pytest.fixture
def daily_runner(monkeypatch):
    # Generation-only tests must never inherit the machine's live publishing target.
    monkeypatch.setenv("REPORT_PUBLISH_URL", "")
    spec = importlib.util.spec_from_file_location("daily_news_runner_test", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "create_run", AsyncMock(return_value=1))
    monkeypatch.setattr(module, "progress_run", AsyncMock())
    monkeypatch.setattr(module, "finish_run", AsyncMock())
    return module


@pytest.mark.asyncio
async def test_daily_run_flushes_uploads_without_regenerating(daily_runner, monkeypatch):
    from backend.services import report_publishing
    monkeypatch.setenv("REPORT_PUBLISH_URL", "https://cloud.example.test")
    monkeypatch.setenv("REPORT_PUBLISH_TOKEN", "x" * 40)
    generate = AsyncMock(return_value=0)
    publish = AsyncMock(return_value={"published": 2, "failed": 0})
    monkeypatch.setattr(daily_runner, "_execute_pipeline", generate)
    monkeypatch.setattr(report_publishing, "publish_pending", publish)
    assert await daily_runner.execute_tracked_run(("AMD",), 1, collect_news=True) == 0
    assert generate.await_count == 1
    publish.assert_awaited_once_with(limit=500)
    daily_runner.finish_run.assert_awaited_once_with(1, failed=False)


@pytest.mark.asyncio
async def test_daily_upload_failure_preserves_successful_generation(daily_runner, monkeypatch):
    from backend.services import report_publishing
    monkeypatch.setenv("REPORT_PUBLISH_URL", "https://cloud.example.test")
    monkeypatch.setenv("REPORT_PUBLISH_TOKEN", "x" * 40)
    generate = AsyncMock(return_value=0)
    monkeypatch.setattr(daily_runner, "_execute_pipeline", generate)
    monkeypatch.setattr(report_publishing, "publish_pending", AsyncMock(side_effect=RuntimeError("unavailable")))
    assert await daily_runner.execute_tracked_run(("AMD",), 1, collect_news=True) == 1
    assert generate.await_count == 1
    daily_runner.finish_run.assert_awaited_once_with(1, failed=False)


class _Revision:
    def __init__(self, down_revision):
        self.down_revision = down_revision


class _Script:
    revisions = {
        "base": _Revision(None),
        "old": _Revision("base"),
        "head": _Revision("old"),
    }

    def get_revision(self, revision_id):
        return self.revisions.get(revision_id)


@pytest.mark.asyncio
async def test_matching_revision_allows_workflow_to_proceed(
    daily_runner, monkeypatch, capsys
):
    monkeypatch.setattr(
        daily_runner, "_repository_migration_state", lambda: (_Script(), ("head",))
    )

    async def current():
        return ("head",)

    monkeypatch.setattr(daily_runner, "_database_migration_revisions", current)

    assert await daily_runner._run_schema_preflight() is True
    output = capsys.readouterr()
    assert "database_schema_preflight_completed" in output.out
    assert output.err == ""


@pytest.mark.asyncio
async def test_behind_revision_stops_before_ingestion(
    daily_runner, monkeypatch, capsys
):
    monkeypatch.setattr(
        daily_runner, "_repository_migration_state", lambda: (_Script(), ("head",))
    )

    async def current():
        return ("old",)

    ingestion_called = False

    async def ingest(*args, **kwargs):
        nonlocal ingestion_called
        ingestion_called = True
        return {"status": "completed"}

    monkeypatch.setattr(daily_runner, "_database_migration_revisions", current)
    monkeypatch.setattr(daily_runner, "fetch_and_ingest_watchlist_once", ingest)

    assert await daily_runner.run() == 1
    assert ingestion_called is False
    output = capsys.readouterr()
    assert "Database schema is behind" in output.err
    assert "Current: old" in output.err
    assert "Expected: head" in output.err
    assert daily_runner.ALEMBIC_UPGRADE_COMMAND in output.err


@pytest.mark.asyncio
async def test_unknown_state_stops_with_actionable_error(
    daily_runner, monkeypatch, capsys
):
    monkeypatch.setattr(
        daily_runner, "_repository_migration_state", lambda: (_Script(), ("head",))
    )

    async def current():
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(daily_runner, "_database_migration_revisions", current)

    assert await daily_runner._run_schema_preflight() is False
    output = capsys.readouterr()
    assert "migration state could not be determined" in output.err
    assert "Current: unavailable" in output.err
    assert "Expected: head" in output.err
    assert daily_runner.ALEMBIC_UPGRADE_COMMAND in output.err


@pytest.mark.asyncio
async def test_preflight_error_does_not_expose_database_credentials(
    daily_runner, monkeypatch, capsys
):
    secret_url = "postgresql+asyncpg://private-user:private-password@localhost/news"
    monkeypatch.setattr(
        daily_runner, "_repository_migration_state", lambda: (_Script(), ("head",))
    )

    async def current():
        raise RuntimeError(secret_url)

    monkeypatch.setattr(daily_runner, "_database_migration_revisions", current)

    assert await daily_runner._run_schema_preflight() is False
    output = capsys.readouterr()
    combined = output.out + output.err
    assert secret_url not in combined
    assert "private-user" not in combined
    assert "private-password" not in combined


@pytest.mark.asyncio
@pytest.mark.parametrize("missing_quote,failed_ticker", [(None, None), (None, "AMZN"), ("QQQ", "AMZN")])
async def test_daily_reports_cover_dynamic_watchlist_and_continue_after_failure(
    daily_runner, monkeypatch, capsys, missing_quote, failed_ticker
):
    class Weekday(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 10, 21, 20, 30, tzinfo=tz)

    tickers = ("VOO", "QQQ", "AMZN", "MSFT", "KO")
    monkeypatch.setattr(daily_runner, "datetime", Weekday)
    monkeypatch.setattr(daily_runner, "_run_schema_preflight", AsyncMock(return_value=True))
    monkeypatch.setattr(daily_runner, "_watchlist_report_tickers", AsyncMock(return_value=tickers))
    monkeypatch.setattr(daily_runner, "fetch_and_ingest_watchlist_once", AsyncMock(return_value={"status": "completed"}))

    def quotes(requested):
        assert requested == tickers
        return {ticker: {"price": 100} for ticker in requested if ticker != missing_quote}

    async def generate(ticker, quote):
        return {"ticker": ticker, "status": "failed" if ticker == failed_ticker else "completed"}

    generator = AsyncMock(side_effect=generate)
    monkeypatch.setattr(daily_runner, "_fetch_report_quotes", quotes)
    monkeypatch.setattr(daily_runner, "_generate_report", generator)

    assert await daily_runner.run() == (1 if missing_quote or failed_ticker else 0)
    assert [call.args[0] for call in generator.await_args_list] == [
        ticker for ticker in tickers if ticker != missing_quote
    ]
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    summary = events[-1]
    assert summary["event"] == ("daily_pipeline_failed" if missing_quote or failed_ticker else "daily_pipeline_completed")
    assert [item["ticker"] for item in summary["outcomes"]] == list(tickers)
    assert summary["reports_failed"] == int(missing_quote is not None) + int(failed_ticker is not None)


@pytest.mark.asyncio
async def test_empty_report_list_still_allows_news_collection(daily_runner, monkeypatch, capsys):
    monkeypatch.setattr(daily_runner, "_run_schema_preflight", AsyncMock(return_value=True))
    monkeypatch.setattr(daily_runner, "_watchlist_report_tickers", AsyncMock(return_value=()))
    ingestion = AsyncMock(return_value={"status": "completed"})
    monkeypatch.setattr(daily_runner, "fetch_and_ingest_watchlist_once", ingestion)
    assert await daily_runner.run() == 0
    ingestion.assert_awaited_once()
    assert "reports_skipped" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_unavailable_live_settings_prevent_stale_daily_generation(daily_runner, monkeypatch, capsys):
    from backend.services import daily_updates
    monkeypatch.setattr(daily_runner, "_run_schema_preflight", AsyncMock(return_value=True))
    monkeypatch.setattr(daily_updates, "sync_config", AsyncMock(side_effect=RuntimeError("offline")))
    ingestion = AsyncMock()
    monkeypatch.setattr(daily_runner, "fetch_and_ingest_watchlist_once", ingestion)
    assert await daily_runner.run() == 1
    ingestion.assert_not_awaited()
    daily_runner.create_run.assert_not_awaited()
    assert "live_settings_unavailable" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_scheduled_quotes_are_isolated_between_concurrent_requests(daily_runner, monkeypatch):
    async def generate(ticker, quote):
        await asyncio.sleep(0)
        received = await daily_runner.analysis_router._analysis_quote(ticker)
        assert received == quote
        return {"ticker": ticker, "status": "completed"}

    monkeypatch.setattr(daily_runner, "_generate_report_with_quote", generate)
    await asyncio.gather(
        daily_runner._generate_report("AMD", {"ticker": "AMD", "price": 100}),
        daily_runner._generate_report("NVDA", {"ticker": "NVDA", "price": 200}),
    )
    assert daily_runner.analysis_router.report_quote_override.get() is None
