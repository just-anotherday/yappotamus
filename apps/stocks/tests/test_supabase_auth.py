"""Owner-only Supabase authentication for HTTP and WebSocket handshakes."""
import base64
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from backend.auth import verify_app_access_token, verify_user_access_token
from backend.config.settings import Settings
from backend.routers.websocket import router as ws_router

OWNER = "ecd5917f-ab88-4981-9ded-d8df188b2156"


@pytest.fixture(autouse=True)
def supabase_env(monkeypatch):
    monkeypatch.setenv("AUTH_PROVIDER", "supabase")
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_PUBLISHABLE_KEY", "sb_publishable_test")
    monkeypatch.setenv("SUPABASE_ALLOWED_USER_ID", OWNER)
    monkeypatch.setenv("APP_ACCESS_TOKEN", "old-shared-token")


def auth_client():
    app = FastAPI()
    app.add_api_route("/protected", lambda: {"ok": True}, dependencies=[Depends(verify_app_access_token)])
    app.include_router(ws_router)
    return TestClient(app)


@pytest.mark.parametrize("status,payload,expected", [
    (200, {"id": OWNER, "is_anonymous": False}, 200),
    (200, {"id": "another-user"}, 403),
    (200, {"id": OWNER, "is_anonymous": True}, 403),
    (200, {}, 503),
    (200, [], 503),
    (401, {"message": "expired"}, 401),
    (403, {}, 401),
    (429, {}, 503),
    (500, {}, 503),
])
def test_http_owner_enforcement(status, payload, expected):
    with patch("backend.auth.httpx.AsyncClient.get", new_callable=AsyncMock) as get:
        get.return_value = httpx.Response(status, json=payload)
        response = auth_client().get("/protected", headers={"Authorization": "Bearer session-jwt"})
        assert response.status_code == expected
        assert get.call_args.args[0] == "https://example.supabase.co/auth/v1/user"
        assert get.call_args.kwargs["headers"]["Authorization"] == "Bearer session-jwt"
        assert get.call_args.kwargs["headers"]["apikey"] == "sb_publishable_test"


@pytest.mark.parametrize("token", ["old-shared-token", "forged-jwt"])
async def test_no_shared_token_or_unverified_jwt_bypass(token):
    with patch("backend.auth.httpx.AsyncClient.get", new_callable=AsyncMock) as get:
        get.return_value = httpx.Response(401, json={})
        with pytest.raises(HTTPException) as exc:
            await verify_user_access_token(token)
        assert exc.value.status_code == 401


async def test_network_failure_fails_closed():
    with patch("backend.auth.httpx.AsyncClient.get", new_callable=AsyncMock) as get:
        get.side_effect = httpx.ConnectError("offline")
        with pytest.raises(HTTPException) as exc:
            await verify_user_access_token("session-jwt")
        assert exc.value.status_code == 503


@pytest.mark.parametrize("token", ["non-ascii-\u00e9", "jwt\r\ninjected: value", "jwt\x00", "jwt\x7f"])
async def test_malformed_token_rejected_before_auth_service(token):
    with patch("backend.auth.httpx.AsyncClient.get", new_callable=AsyncMock) as get:
        with pytest.raises(HTTPException) as exc:
            await verify_user_access_token(token)
        assert exc.value.status_code == 401
        get.assert_not_called()


@pytest.mark.parametrize("payload,code", [({"id": "other"}, 4403), ({}, 1013)])
def test_websocket_rejects_non_owner(payload, code):
    with patch("backend.auth.httpx.AsyncClient.get", new_callable=AsyncMock) as get:
        get.return_value = httpx.Response(200, json=payload)
        token = base64.urlsafe_b64encode(b"session-jwt").decode().rstrip("=")
        with pytest.raises(WebSocketDisconnect) as exc:
            with auth_client().websocket_connect("/ws", subprotocols=["yapvibes", token]):
                pass
        assert exc.value.code == code


def test_missing_auth_does_not_call_supabase():
    with patch("backend.auth.httpx.AsyncClient.get", new_callable=AsyncMock) as get:
        assert auth_client().get("/protected").status_code == 401
        get.assert_not_called()


def test_supabase_startup_without_legacy_tokens(monkeypatch):
    monkeypatch.delenv("APP_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("APP_ACCESS_TOKENS", raising=False)
    Settings().validate()


@pytest.mark.parametrize("name,value", [
    ("AUTH_PROVIDER", "unknown"),
    ("SUPABASE_URL", "http://example.supabase.co"),
    ("SUPABASE_PUBLISHABLE_KEY", ""),
    ("SUPABASE_ALLOWED_USER_ID", ""),
    ("SUPABASE_ALLOWED_USER_ID", "invalid"),
])
def test_missing_or_invalid_configuration_fails_startup(monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(EnvironmentError):
        Settings().validate()
