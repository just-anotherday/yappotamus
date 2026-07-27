"""Health-state and WebSocket authentication regressions."""

import base64
from unittest.mock import MagicMock

from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
import pytest

from backend.main import app


def test_health_liveness_is_lightweight():
    response = TestClient(app).get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_health_instantiates_registered_ai_providers(monkeypatch):
    class AvailableProvider:
        def __init__(self):
            self.initialized = True

        async def is_available(self):
            return self.initialized

    class EmptyResult:
        def all(self):
            return []

        def scalar_one_or_none(self):
            return None

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return False

        async def execute(self, statement):
            return EmptyResult()

    class FakeSessionFactory:
        def __call__(self):
            return FakeSession()

    worker = MagicMock()
    worker._running = True
    monkeypatch.setattr(app.state, "ai_worker", worker)
    monkeypatch.setattr("backend.main.async_session_factory", FakeSessionFactory())
    monkeypatch.setattr(
        "backend.services.ai.ProviderRegistry.get", lambda provider_id: AvailableProvider
    )

    response = TestClient(app).get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["dependencies"]["openai"]["status"] == "available"
    assert payload["dependencies"]["ollama"]["status"] == "available"


def test_websocket_rejects_missing_token():
    client = TestClient(app)
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect("/ws"):
            raise AssertionError("unauthorized websocket connected")
    assert exc_info.value.code == 4401


def test_websocket_accepts_authorized_subprotocol(monkeypatch):
    monkeypatch.setenv("APP_ACCESS_TOKEN", "ws-test-token")
    market_data = MagicMock()
    market_data.latest_quotes = {}
    monkeypatch.setattr(
        "backend.routers.websocket.MarketDataService.get_instance", lambda: market_data
    )
    encoded = base64.urlsafe_b64encode(b"ws-test-token").decode().rstrip("=")
    with TestClient(app) as client:
        with client.websocket_connect(
            "/ws", subprotocols=["yapvibes", encoded]
        ) as websocket:
            assert websocket.accepted_subprotocol == "yapvibes"