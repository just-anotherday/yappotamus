"""Regression coverage for database recovery and externally triggered ingestion."""

import pytest
from sqlalchemy.exc import OperationalError

from backend.config import database
from backend.config.settings import Settings
from backend.auth import verify_internal_job_token
from backend.services import news_ingestion_service as news


class _FakeSession:
    def __init__(self):
        self.rollbacks = 0

    async def rollback(self):
        self.rollbacks += 1


class _FakeEngine:
    def __init__(self):
        self.disposals = 0

    async def dispose(self):
        self.disposals += 1


class _SessionContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *args):
        return False


@pytest.mark.asyncio
async def test_connection_failure_rolls_back_and_discards_stale_pool(monkeypatch):
    session = _FakeSession()
    engine = _FakeEngine()
    monkeypatch.setattr(database, "engine", engine)

    await database._recover_session_after_failure(
        session,
        OperationalError("SELECT 1", {}, ConnectionError("database unavailable")),
    )

    assert session.rollbacks == 1
    assert engine.disposals == 1


def test_database_error_sanitization_redacts_dsn_passwords():
    message = database.sanitize_database_error(
        RuntimeError("failed postgresql+asyncpg://alice:secret@db.example.com/postgres")
    )
    assert "secret" not in message
    assert "postgresql+asyncpg://***@" in message


def test_production_disables_in_process_scheduler_by_default(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("NEWS_SCHEDULER_ENABLED", raising=False)
    assert Settings().NEWS_SCHEDULER_ENABLED is False


@pytest.mark.asyncio
async def test_internal_job_token_is_distinct_and_required(monkeypatch):
    monkeypatch.setenv("INTERNAL_JOB_TOKEN", "internal-test-token")
    await verify_internal_job_token("Bearer internal-test-token")
    with pytest.raises(Exception) as exc_info:
        await verify_internal_job_token("Bearer wrong-token")
    assert getattr(exc_info.value, "status_code", None) == 401


@pytest.mark.asyncio
async def test_one_shot_watchlist_ingestion_returns_compact_summary(monkeypatch):
    session = object()

    async def fake_tickers(_session):
        return ["AAPL"]

    async def fake_many(tickers, _session, **kwargs):
        kwargs["_cycle_counters"]["articles_fetched"] = 2
        kwargs["_cycle_counters"]["articles_changed"] = 1
        return {ticker: 1 for ticker in tickers}

    async def fake_recover(_session):
        return 0

    monkeypatch.setattr(news, "get_all_tickers", fake_tickers)
    monkeypatch.setattr(news, "fetch_and_ingest_many", fake_many)
    monkeypatch.setattr(news, "_recover_thumbnails", fake_recover)

    summary = await news.fetch_and_ingest_watchlist_once(lambda: _SessionContext(session))

    assert summary["tickers"] == 1
    assert summary["articles_fetched"] == 2
    assert summary["articles_changed"] == 1
