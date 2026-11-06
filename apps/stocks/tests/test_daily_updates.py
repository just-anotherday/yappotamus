"""Isolated local/cloud settings, worker, and authorization regressions."""
import os
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from dotenv import dotenv_values
from fastapi import FastAPI, HTTPException, Request
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.auth import verify_app_access_token
from backend.config.database import Base, get_async_session
from backend.models.daily_updates import DailyUpdateState
from backend.models.watchlist import WatchlistModel
from backend.routers.daily_updates import router
from backend.services import daily_updates as service
from backend.services.watchlist_service import get_news_tickers, get_report_tickers, seed_defaults

TOKEN = 'test-machine-token-' + 'x' * 32
ORIGIN = 'https://settings.example.test'
OWNER = {'Authorization': 'Bearer owner'}
MACHINE = {'Authorization': 'Bearer ' + TOKEN}


@pytest.fixture(autouse=True)
def settings(monkeypatch):
    monkeypatch.setenv('REPORT_PUBLISH_URL', '')
    monkeypatch.setenv('REPORT_PUBLISH_TOKEN', TOKEN)
    monkeypatch.setenv('DAILY_UPDATES_SYNC_ENABLED', 'true')


@pytest_asyncio.fixture
async def pair():
    if os.getenv('RUN_DAILY_UPDATES_DB_TESTS') != '1':
        pytest.skip('Enable isolated daily-updates database tests explicitly')
    url = dotenv_values(Path(__file__).resolve().parents[1] / '.env')['DATABASE_URL']
    engine = create_async_engine(url.replace('postgresql://', 'postgresql+asyncpg://', 1), connect_args={'timeout': 5})
    schemas, factories = [], []
    try:
        for _ in range(2):
            schema = 'daily_test_' + uuid4().hex
            async with engine.begin() as conn:
                await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
            schemas.append(schema)
            bound = engine.execution_options(schema_translate_map={None: schema})
            async with bound.begin() as conn:
                await conn.run_sync(lambda sync: Base.metadata.create_all(sync, tables=[WatchlistModel.__table__, DailyUpdateState.__table__]))
            factories.append(async_sessionmaker(bound, expire_on_commit=False))
        local, cloud = factories
        app = FastAPI()
        app.include_router(router)

        async def session():
            async with cloud() as conn:
                yield conn

        async def owner(request: Request):
            if request.headers.get('Authorization') != 'Bearer owner':
                raise HTTPException(401, 'Owner required')

        app.dependency_overrides[get_async_session] = session
        app.dependency_overrides[verify_app_access_token] = owner
        yield local, cloud, app
    finally:
        for schema in schemas:
            assert schema.startswith('daily_test_') and len(schema) == 43
            async with engine.begin() as conn:
                await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await engine.dispose()


async def client_for(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url=ORIGIN)


@pytest.mark.asyncio
async def test_owner_edits_and_machine_credentials_have_separate_scopes(pair):
    _, cloud, app = pair
    async with await client_for(app) as client:
        assert (await client.get('/api/daily-updates')).status_code == 401
        assert (await client.post('/api/daily-updates/tickers', headers=MACHINE, json={'ticker': 'AMD'})).status_code == 401
        assert (await client.get('/api/internal/daily-updates', headers=OWNER)).status_code == 401
        created = await client.post('/api/daily-updates/tickers', headers=OWNER, json={'ticker': 'amd'})
        assert created.status_code == 200
        before = created.json()['revision']
        assert created.json()['tickers'][0]['news_status'] == 'pending'
        assert (await client.post('/api/daily-updates/tickers', headers=OWNER, json={'ticker': 'AMD'})).status_code == 409
        changed = await client.patch('/api/daily-updates/tickers/AMD', headers=OWNER, json={'news_enabled': False, 'reports_enabled': True})
        assert changed.json()['revision'] != before
        assert changed.json()['tickers'][0]['news_status'] == 'paused'
        assert (await client.post('/api/internal/daily-updates/ack', headers=MACHINE, json={'revision': before})).status_code == 409
        async with cloud() as session:
            assert await get_news_tickers(session) == []
            assert await get_report_tickers(session) == ['AMD']
        enabled = await client.patch('/api/daily-updates/tickers/AMD', headers=OWNER, json={'news_enabled': True, 'reports_enabled': False})
        assert enabled.json()['tickers'][0]['news_status'] == 'pending'
        async with cloud() as session:
            assert await get_news_tickers(session) == ['AMD']
            assert await get_report_tickers(session) == []


@pytest.mark.asyncio
async def test_pull_mirrors_live_preferences_and_acknowledges_after_commit(pair, monkeypatch):
    local, cloud, app = pair
    async with local() as session:
        session.add(WatchlistModel(ticker='OLD', position=0))
        await session.commit()
    async with await client_for(app) as client:
        for ticker, news, reports in [('AMD', True, False), ('MSFT', False, True)]:
            assert (await client.post('/api/daily-updates/tickers', headers=OWNER, json={'ticker': ticker, 'news_enabled': news, 'reports_enabled': reports})).status_code == 200
    monkeypatch.setenv('REPORT_PUBLISH_URL', ORIGIN)
    received = await service.sync_config(session_factory=local, transport=httpx.ASGITransport(app))
    async with local() as session:
        assert await get_news_tickers(session) == ['AMD']
        assert await get_report_tickers(session) == ['MSFT']
        assert await session.scalar(select(func.count()).select_from(WatchlistModel)) == 2
    async with cloud() as session:
        state = await session.get(DailyUpdateState, 1)
        assert state.applied_revision == received.revision and state.last_seen_at
        assert state.local_status['AMD']['status'] == 'pending'


@pytest.mark.asyncio
async def test_invalid_snapshot_never_deletes_local_settings(pair, monkeypatch):
    local, _, _ = pair
    async with local() as session:
        session.add(WatchlistModel(ticker='AMD', position=0))
        await session.commit()
    monkeypatch.setenv('REPORT_PUBLISH_URL', ORIGIN)
    with pytest.raises(ValueError):
        await service.sync_config(session_factory=local, transport=httpx.MockTransport(lambda request: httpx.Response(200, json={'revision': '0' * 64, 'tickers': []})))
    async with local() as session:
        assert await get_report_tickers(session) == ['AMD']


@pytest.mark.asyncio
async def test_empty_live_list_stays_empty_after_pull_and_restart(pair, monkeypatch):
    local, cloud, app = pair
    async with await client_for(app) as client:
        await client.post('/api/daily-updates/tickers', headers=OWNER, json={'ticker': 'AMD'})
        assert (await client.delete('/api/daily-updates/tickers/AMD', headers=OWNER)).status_code == 200
    monkeypatch.setenv('REPORT_PUBLISH_URL', ORIGIN)
    await service.sync_config(session_factory=local, transport=httpx.ASGITransport(app))
    for factory in (local, cloud):
        async with factory() as session:
            assert await seed_defaults(session) == 0
            assert await get_report_tickers(session) == []


@pytest.mark.asyncio
async def test_initial_fetch_is_durable_and_disabled_or_removed_tickers_are_skipped(pair, monkeypatch):
    _, cloud, app = pair
    from backend.services import news_ingestion_service
    async def successful_fetch(*args, **kwargs):
        kwargs['_provider_state']['last_outcome'] = 'success'
        return 4
    fetch = AsyncMock(side_effect=successful_fetch)
    monkeypatch.setattr(news_ingestion_service, 'fetch_and_ingest_news', fetch)
    async with await client_for(app) as client:
        for ticker in ('AMD', 'MSFT', 'OLD'):
            await client.post('/api/daily-updates/tickers', headers=OWNER, json={'ticker': ticker})
        await client.patch('/api/daily-updates/tickers/MSFT', headers=OWNER, json={'news_enabled': False, 'reports_enabled': True})
        await client.delete('/api/daily-updates/tickers/OLD', headers=OWNER)
    await service.ingest_pending_news(session_factory=cloud)
    assert fetch.await_count == 1 and fetch.await_args.args[0] == 'AMD'
    await service.ingest_pending_news(session_factory=cloud)
    assert fetch.await_count == 1
    async with cloud() as session:
        row = await session.scalar(select(WatchlistModel).where(WatchlistModel.ticker == 'AMD'))
        assert row.news_status == 'completed' and not row.news_pending


@pytest.mark.asyncio
async def test_failed_initial_fetch_is_retained_with_backoff(pair, monkeypatch):
    _, cloud, app = pair
    from backend.services import news_ingestion_service
    fetch = AsyncMock(side_effect=RuntimeError('provider unavailable'))
    monkeypatch.setattr(news_ingestion_service, 'fetch_and_ingest_news', fetch)
    async with await client_for(app) as client:
        await client.post('/api/daily-updates/tickers', headers=OWNER, json={'ticker': 'AMD'})
    await service.ingest_pending_news(session_factory=cloud)
    await service.ingest_pending_news(session_factory=cloud)
    assert fetch.await_count == 1
    async with cloud() as session:
        row = await session.scalar(select(WatchlistModel))
        assert row.news_status == 'retrying' and row.news_pending
