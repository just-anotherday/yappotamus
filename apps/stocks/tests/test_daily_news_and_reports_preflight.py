"""Focused coverage for the local daily workflow database preflight."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "run_daily_news_and_reports.py"
)


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
