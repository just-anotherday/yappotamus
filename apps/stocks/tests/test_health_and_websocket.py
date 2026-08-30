"""Health-state and WebSocket authentication regressions."""

import base64
import logging
from unittest.mock import MagicMock

from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
import pytest

from backend import main as backend_main
from backend.main import app


def test_health_liveness_is_lightweight(monkeypatch):
    monkeypatch.delenv("RENDER_GIT_COMMIT", raising=False)
    monkeypatch.delenv("RENDER_GIT_BRANCH", raising=False)

    class UnexpectedDatabaseAccess:
        def __call__(self):
            raise AssertionError("liveness must not access the database")

    monkeypatch.setattr("backend.main.async_session_factory", UnexpectedDatabaseAccess())
    response = TestClient(app).get("/health/live", headers={"X-Request-ID": "health-check-42"})
    assert response.status_code == 200
    assert response.json() == {
        "status": "healthy",
        "git_commit": None,
        "git_branch": None,
    }
    assert response.headers["X-Request-ID"] == "health-check-42"


def test_health_liveness_exposes_render_deployment_identity(monkeypatch):
    expected_sha = "dae788a63e4f14b84a61c25f9cb4b27a43e2b70d"
    monkeypatch.setenv("RENDER_GIT_COMMIT", expected_sha)
    monkeypatch.setenv("RENDER_GIT_BRANCH", "main")

    response = TestClient(app).get("/health/live")

    assert response.status_code == 200
    assert response.json() == {
        "status": "healthy",
        "git_commit": expected_sha,
        "git_branch": "main",
    }


def test_health_liveness_does_not_echo_unrelated_environment(monkeypatch):
    monkeypatch.delenv("RENDER_GIT_COMMIT", raising=False)
    monkeypatch.delenv("RENDER_GIT_BRANCH", raising=False)
    monkeypatch.setenv("APP_ACCESS_TOKEN", "representative-test-secret")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:test-secret@db.example.test/app")
    monkeypatch.setenv("OPENAI_API_KEY", "test-api-key")

    response = TestClient(app).get("/health/live")

    assert response.status_code == 200
    payload = response.json()
    assert payload == {
        "status": "healthy",
        "git_commit": None,
        "git_branch": None,
    }
    serialized = response.text
    assert "representative-test-secret" not in serialized
    assert "test-secret" not in serialized
    assert "test-api-key" not in serialized


def test_health_liveness_openapi_declares_deployment_identity_contract():
    operation = app.openapi()["paths"]["/health/live"]["get"]
    response_schema = operation["responses"]["200"]["content"]["application/json"]["schema"]

    assert response_schema == {
        "$ref": "#/components/schemas/HealthLiveResponse"
    }
    schema = app.openapi()["components"]["schemas"]["HealthLiveResponse"]
    assert set(schema["properties"]) == {"status", "git_commit", "git_branch"}


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


def test_public_readiness_returns_503_when_database_is_unreachable(monkeypatch, caplog):
    class FailingSessionFactory:
        def __call__(self):
            raise ConnectionError(
                "database unavailable at postgresql+asyncpg://user:secret@db.example.test/postgres"
            )

    monkeypatch.setattr("backend.main.async_session_factory", FailingSessionFactory())
    with caplog.at_level(logging.WARNING, logger="backend.main"):
        response = TestClient(app).get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "not_ready", "database": "unreachable"}
    messages = "\n".join(record.getMessage() for record in caplog.records)
    assert "exception_type=ConnectionError" in messages
    assert "secret" not in messages
    assert "postgresql+asyncpg://***@" in messages


def test_rate_limit_middleware_emits_wire_429_instead_of_500(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "https://stocks.yapvibes.com")
    backend_main._rate_limit_store.clear()
    monkeypatch.setattr(backend_main, "_RATE_LIMIT_MAX_REQS", 0)
    try:
        response = TestClient(app, raise_server_exceptions=False).get(
            "/api/operations/status",
            headers={"Origin": "https://stocks.yapvibes.com"},
        )
    finally:
        backend_main._rate_limit_store.clear()

    assert response.status_code == 429
    assert response.json() == {
        "error": "Too many requests. Please slow down.",
        "status_code": 429,
    }
    assert response.headers["Retry-After"] == str(backend_main._RATE_LIMIT_WINDOW)
    assert response.headers["access-control-allow-origin"] == "https://stocks.yapvibes.com"
    exposed_headers = response.headers["access-control-expose-headers"].lower()
    assert "x-request-id" in exposed_headers
    assert "retry-after" in exposed_headers

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
