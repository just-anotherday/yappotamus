"""Browser-triggered ingestion must keep the existing user-auth boundary."""
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app
from backend.routers import news


@pytest.fixture
def sync_client(monkeypatch):
    monkeypatch.setenv('AUTH_PROVIDER', 'token')
    monkeypatch.setenv('APP_ACCESS_TOKEN', 'browser-test-token')
    monkeypatch.delenv('APP_ACCESS_TOKENS', raising=False)
    monkeypatch.setenv('INTERNAL_JOB_TOKEN', 'machine-test-token')
    ingest = AsyncMock(return_value={'status': 'completed', 'articles_inserted': 2})
    monkeypatch.setattr(news, 'fetch_and_ingest_watchlist_once', ingest)
    # No lifespan: the route test must not start workers or touch a real DB.
    return TestClient(create_app()), ingest


@pytest.mark.parametrize('token', [None, 'wrong-token', 'machine-test-token'])
def test_unauthorized_sync_never_calls_provider(sync_client, token):
    client, ingest = sync_client
    headers = {'Authorization': f'Bearer {token}'} if token else {}
    assert client.post('/api/news/ingest', headers=headers).status_code == 401
    ingest.assert_not_awaited()


def test_owner_can_trigger_one_forced_sync_without_internal_token(sync_client):
    client, ingest = sync_client
    response = client.post('/api/news/ingest', headers={'Authorization': 'Bearer browser-test-token'})
    assert response.status_code == 200
    assert response.json()['articles_inserted'] == 2
    ingest.assert_awaited_once_with(news.async_session_factory, force=True)


def test_partial_and_overlap_results_are_preserved_for_browser(sync_client):
    client, ingest = sync_client
    for summary in [{'status': 'partial', 'symbols_failed': 2}, {'status': 'skipped_overlap'}]:
        ingest.return_value = summary
        response = client.post('/api/news/ingest', headers={'Authorization': 'Bearer browser-test-token'})
        assert response.json() == summary
