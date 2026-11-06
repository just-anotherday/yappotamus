"""Opt-in PostgreSQL integration checks in a disposable, isolated schema.

RUN_RESEARCH_DB_TESTS=1 uses the Stocks .env connection without touching app rows.
"""
import os
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4
from unittest.mock import AsyncMock

import httpx
import pytest
import pytest_asyncio
from dotenv import dotenv_values
from fastapi import Depends, FastAPI, Header, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from backend.auth import verify_app_access_token
from backend.config.database import Base, get_async_session
from backend.models.research import ResearchNote, ArticleReadingState, ReportRun
from backend.models.news import NewsArticle
from backend.models.report import AnalysisReportModel
from backend.models.watchlist import WatchlistModel
from backend.routers import research
from backend.services import report_run_service as runs
from backend.services.report_service import list_reports
from backend.lib.timestamps import utc_now_naive

pytestmark = pytest.mark.skipif(os.getenv("RUN_RESEARCH_DB_TESTS") != "1", reason="Explicit database integration opt-in required")


@pytest_asyncio.fixture
async def workspace(monkeypatch):
    values = dotenv_values(Path(__file__).resolve().parents[1] / ".env")
    url = values.get("DATABASE_URL")
    assert url, "A configured integration database is required"
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    engine = create_async_engine(url)
    schema = "research_test_" + uuid4().hex
    tables = [ResearchNote.__table__, ArticleReadingState.__table__, ReportRun.__table__, NewsArticle.__table__, AnalysisReportModel.__table__, WatchlistModel.__table__]
    try:
        async with engine.begin() as conn:
            await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        bound = engine.execution_options(schema_translate_map={None: schema})
        async with bound.begin() as conn:
            await conn.run_sync(lambda sync: Base.metadata.create_all(sync, tables=tables))
        factory = async_sessionmaker(bound, expire_on_commit=False)
        monkeypatch.setattr(runs, "async_session_factory", factory)
        monkeypatch.setattr(research, "execute_retry", AsyncMock())

        async def session_dependency():
            async with factory() as session:
                yield session

        async def owner(authorization: str | None = Header(None)):
            if authorization not in ("Bearer account-a", "Bearer account-b"):
                raise HTTPException(401, "Unauthorized")
            return authorization.removeprefix("Bearer ")

        app = FastAPI()
        app.include_router(research.router, dependencies=[Depends(verify_app_access_token)])
        app.dependency_overrides[verify_app_access_token] = owner
        app.dependency_overrides[research.research_owner] = owner
        app.dependency_overrides[get_async_session] = session_dependency
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test", headers={"Authorization": "Bearer account-a"}) as client:
            yield client, factory
    finally:
        # Only the unique schema created by this fixture is ever removed.
        assert schema.startswith("research_test_") and len(schema) == 46
        async with engine.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await engine.dispose()


@pytest.mark.asyncio
async def test_notes_account_isolation_validation_and_conflict(workspace):
    client, _ = workspace
    assert (await client.get("/api/research/notes/AMD")).json()["version"] == 0
    first = await client.put("/api/research/notes/AMD", json={"text": "My thesis", "version": 0})
    assert first.json()["version"] == 1
    other = await client.get("/api/research/notes/AMD", headers={"Authorization": "Bearer account-b"})
    assert other.json()["text"] == ""
    assert (await client.put("/api/research/notes/AMD", json={"text": "Stale edit", "version": 0})).status_code == 409
    assert (await client.put("/api/research/notes/AMD", json={"text": "Updated", "version": 1})).json()["version"] == 2
    assert (await client.put("/api/research/notes/AMD", json={"text": "x" * 10001, "version": 2})).status_code == 422
    assert (await client.get("/api/research/notes/AMD", headers={"Authorization": "invalid"})).status_code == 401


@pytest.mark.asyncio
async def test_reading_list_filters_and_independent_state(workspace):
    client, factory = workspace
    async with factory() as session:
        session.add_all([NewsArticle(id=i, ticker="AMD", title=f"Story {i}", pub_date=datetime(2026, 10, 28, 12)) for i in range(1, 4)])
        await session.commit()
    assert (await client.put("/api/research/article-state/1", json={"saved": True})).status_code == 200
    await client.put("/api/research/article-state/1", json={"read": True})
    assert (await client.get("/api/research/news?view=saved")).json()["total"] == 1
    assert (await client.get("/api/research/news?view=unread")).json()["total"] == 2
    assert (await client.get("/api/research/news?view=saved-unread")).json()["total"] == 0
    assert (await client.get("/api/research/news?view=saved", headers={"Authorization": "Bearer account-b"})).json()["total"] == 0
    row = (await client.put("/api/research/article-state/1", json={"saved": False})).json()
    assert row["read"] is True and row["saved"] is False
    assert (await client.put("/api/research/article-state/999", json={"saved": True})).status_code == 404


@pytest.mark.asyncio
async def test_search_and_comparison_use_history_outside_current_filters(workspace):
    client, factory = workspace
    async with factory() as session:
        for ident, sentiment, date, payload in [(1, "Bullish", datetime(2026, 10, 20), "Earlier"), (2, "Very Bullish", datetime(2026, 10, 28), "Earnings catalyst")]:
            session.add(AnalysisReportModel(id=ident, ticker="AMD", overall_sentiment=sentiment, confidence_score=60+ident, articles_count=2, model_used="test", prompt_version="2.0", created_at=date, report_data={"executive_summary": payload}))
        await session.commit()
        found, total = await list_reports(session, query="earnings", sentiment="Very Bullish", from_date=datetime(2026, 10, 27))
        assert total == 1 and found[0].previous_report_id == 1
        assert found[0].previous_sentiment == "Bullish"
        _, total = await list_reports(session, query="%")
        assert total == 0
        found, total = await list_reports(session, sentiment="Bullish")
        assert total == 1 and found[0].id == 1
    comparison = (await client.get("/api/research/reports/2/changes")).json()
    assert comparison["previous"]["id"] == 1


@pytest.mark.asyncio
async def test_run_tracking_overlap_and_failed_only_retry(workspace):
    client, factory = workspace
    run_id = await runs.create_run(["AMD", "IBM", "TSM"])
    with pytest.raises(HTTPException) as overlap:
        await runs.create_run(["AMD"])
    assert overlap.value.status_code == 409
    await runs.progress_run(run_id, status="running", outcomes=[{"ticker":"AMD","status":"completed","report_id":7}, {"ticker":"IBM","status":"failed","error":"test failure"}])
    await runs.finish_run(run_id)
    async with factory() as session:
        session.add(WatchlistModel(ticker="IBM", position=0))
        await session.commit()
    retry = await client.post(f"/api/research/runs/{run_id}/retry")
    assert retry.status_code == 202
    assert retry.json()["tickers"] == ["IBM"]
    research.execute_retry.assert_awaited_once_with(retry.json()["run_id"])
    assert (await client.post(f"/api/research/runs/{run_id}/retry")).status_code == 409
    status = (await client.get("/api/research/runs/latest")).json()["run"]
    assert status["parent_id"] == run_id and status["status"] == "queued"


@pytest.mark.asyncio
async def test_migrated_tables_are_private_to_backend(workspace):
    _, factory = workspace
    async with factory() as session:
        for table in ("research_notes", "article_reading_state", "report_runs"):
            secured = (await session.execute(text("SELECT relrowsecurity FROM pg_class WHERE oid = to_regclass(:table)"), {"table": f"public.{table}"})).scalar_one()
            assert secured is True
            roles = (await session.execute(text("SELECT rolname FROM pg_roles WHERE rolname IN ('anon','authenticated')"))).scalars().all()
            for role in roles:
                assert (await session.execute(text("SELECT has_table_privilege(:role, :table, 'SELECT')"), {"role": role, "table": f"public.{table}"})).scalar_one() is False


@pytest.mark.asyncio
async def test_abandoned_runs_expose_unfinished_tickers_and_release_active_slot(workspace):
    client, factory = workspace
    run_id = await runs.create_run(["AMD", "IBM"])
    await runs.progress_run(run_id, status="running", outcomes=[{"ticker":"AMD","status":"completed"}])
    async with factory() as session:
        row = await session.get(ReportRun, run_id)
        row.updated_at = utc_now_naive() - timedelta(hours=7)
        await session.commit()
    latest = (await client.get("/api/research/runs/latest")).json()["run"]
    assert latest["status"] == "interrupted"
    assert latest["outcomes"][-1]["ticker"] == "IBM"
    assert latest["outcomes"][-1]["status"] == "failed"
    assert await runs.create_run(["IBM"], kind="retry", parent_id=run_id) > run_id
