"""Health-state and WebSocket authentication regressions."""

import base64
import logging
from unittest.mock import MagicMock

from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
import pytest

from backend.main import app


def test_health_liveness_is_lightweight():
    response = TestClient(app).get("/health/live", headers={"X-Request-ID": "health-check-42"})
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}
    assert response.headers["X-Request-ID"] == "health-check-42"


def test_public_readiness_only_reports_overall_and_database_state(monkeypatch):
    class EmptyResult:
        pass

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

    monkeypatch.setattr("backend.main.async_session_factory", FakeSessionFactory())
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "reachable"}


def test_public_readiness_returns_503_when_database_is_unreachable(monkeypatch):
    class FailingSessionFactory:
        def __call__(self):
            raise ConnectionError("database unavailable")

    monkeypatch.setattr("backend.main.async_session_factory", FailingSessionFactory())
    response = TestClient(app).get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "not_ready", "database": "unreachable"}

def test_operations_status_is_protected():
    response = TestClient(app).get("/api/operations/status")
    assert response.status_code == 401
    assert "workers" not in response.json()


def test_protected_operations_status_checks_registered_ai_providers(monkeypatch):
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

    response = TestClient(app).get(
        "/api/operations/status",
        headers={"Authorization": "Bearer test-app-token"},
    )

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

@pytest.mark.parametrize(
    ("requested_channel", "expected_channel"),
    [
        ("prices", "prices"),
        ("news", "news"),
        (None, "unspecified"),
        ("unsupported", "unspecified"),
    ],
)
def test_websocket_accepts_authorized_subprotocol(
    monkeypatch,
    caplog,
    requested_channel,
    expected_channel,
):
    monkeypatch.setenv("APP_ACCESS_TOKEN", "ws-test-token")
    market_data = MagicMock()
    market_data.latest_quotes = {}
    monkeypatch.setattr(
        "backend.routers.websocket.MarketDataService.get_instance", lambda: market_data
    )
    encoded = base64.urlsafe_b64encode(b"ws-test-token").decode().rstrip("=")
    websocket_path = "/ws" if requested_channel is None else f"/ws?channel={requested_channel}"

    with caplog.at_level(logging.INFO, logger="backend.services.connection_manager"):
        with TestClient(app) as client:
            connection_manager = app.state.connection_manager
            assert connection_manager.active_connections == []

            with client.websocket_connect(
                websocket_path,
                subprotocols=["yapvibes", encoded],
                headers={
                    "origin": "https://stocks.yapvibes.com",
                    "user-agent": "YapVibesWebSocketTest/1.0",
                },
            ) as websocket:
                assert websocket.accepted_subprotocol == "yapvibes"
                assert len(connection_manager.active_connections) == 1

            assert connection_manager.active_connections == []

    messages = [
        record.getMessage()
        for record in caplog.records
        if record.name == "backend.services.connection_manager"
    ]
    connected = next(message for message in messages if message.startswith("[WS] Connected"))
    disconnected = next(
        message for message in messages if message.startswith("[WS] Disconnected")
    )
    connection_id = connected.split("id=", 1)[1].split(" ", 1)[0]

    assert f"channel={expected_channel}" in connected
    assert "client=testclient" in connected
    assert "origin='https://stocks.yapvibes.com'" in connected
    assert "user_agent='YapVibesWebSocketTest/1.0'" in connected
    assert "ws-test-token" not in connected
    assert encoded not in connected
    assert f"id={connection_id}" in disconnected
    assert f"channel={expected_channel}" in disconnected
    assert "code=1000" in disconnected
    assert "reason='normal_closure'" in disconnected
    assert "total=0" in disconnected