"""Focused coverage for the local daily workflow database preflight."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
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
def daily_runner():
    spec = importlib.util.spec_from_file_location("daily_news_runner_test", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
async def test_empty_watchlist_fails_before_ingestion(daily_runner, monkeypatch, capsys):
    monkeypatch.setattr(daily_runner, "_run_schema_preflight", AsyncMock(return_value=True))
    monkeypatch.setattr(daily_runner, "_watchlist_report_tickers", AsyncMock(return_value=()))
    ingestion = AsyncMock()
    monkeypatch.setattr(daily_runner, "fetch_and_ingest_watchlist_once", ingestion)
    assert await daily_runner.run() == 1
    ingestion.assert_not_awaited()
    assert "watchlist_empty" in capsys.readouterr().out
