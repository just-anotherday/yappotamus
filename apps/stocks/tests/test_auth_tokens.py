"""Multi-access-key authentication regression tests.

Covers:
- Effective token parsing (APP_ACCESS_TOKEN + APP_ACCESS_TOKENS)
- Shared helper (is_valid_access_token) constant-time semantics
- HTTP Bearer dependency (verify_app_access_token)
- Settings validation for the access-token requirement
- WebSocket authentication with multiple configured tokens

Environment isolation: every test explicitly controls both
``APP_ACCESS_TOKEN`` and ``APP_ACCESS_TOKENS`` via monkeypatch.
"""

import base64
import os
from unittest.mock import MagicMock, patch

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
import pytest

from backend.auth import is_valid_access_token, verify_app_access_token
from backend.config.settings import Settings


# --------------------------------------------------------------------------- #
#  Fixtures
# --------------------------------------------------------------------------- #

def _clear_token_env(monkeypatch):
    """Remove both access-token variables so each test starts clean."""
    monkeypatch.delenv("APP_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("APP_ACCESS_TOKENS", raising=False)


# Minimal test-only FastAPI app for HTTP dependency tests.
_http_app = FastAPI()


@_http_app.get("/protected")
async def _protected():
    return {"ok": True}


_http_app.add_api_route(
    "/protected2",
    _protected,
    methods=["GET"],
    dependencies=[Depends(verify_app_access_token)],
)


@pytest.fixture
def http_client(monkeypatch):
    """Return a fresh TestClient; caller must configure env via monkeypatch."""
    return TestClient(_http_app)


# --------------------------------------------------------------------------- #
#  1. Effective-token parsing tests  (Settings.APP_ACCESS_TOKENS)
# --------------------------------------------------------------------------- #


class TestEffectiveTokenParsing:
    """Parse ``APP_ACCESS_TOKEN`` and ``APP_ACCESS_TOKENS`` correctly."""

    def test_neither_configured(self, monkeypatch):
        _clear_token_env(monkeypatch)
        s = Settings()
        assert s.APP_ACCESS_TOKENS == []

    def test_legacy_only(self, monkeypatch):
        _clear_token_env(monkeypatch)
        monkeypatch.setenv("APP_ACCESS_TOKEN", "single-key")
        s = Settings()
        assert s.APP_ACCESS_TOKENS == ["single-key"]

    def test_plural_only(self, monkeypatch):
        _clear_token_env(monkeypatch)
        monkeypatch.setenv("APP_ACCESS_TOKENS", "a|b|c")
        s = Settings()
        assert s.APP_ACCESS_TOKENS == ["a", "b", "c"]

    def test_both_variables(self, monkeypatch):
        _clear_token_env(monkeypatch)
        monkeypatch.setenv("APP_ACCESS_TOKEN", "legacy")
        monkeypatch.setenv("APP_ACCESS_TOKENS", "x|y")
        s = Settings()
        assert s.APP_ACCESS_TOKENS == ["legacy", "x", "y"]

    def test_legacy_token_first(self, monkeypatch):
        _clear_token_env(monkeypatch)
        monkeypatch.setenv("APP_ACCESS_TOKEN", "first")
        monkeypatch.setenv("APP_ACCESS_TOKENS", "second|third")
        s = Settings()
        assert s.APP_ACCESS_TOKENS[0] == "first"

    def test_first_middle_last_plural_tokens(self, monkeypatch):
        _clear_token_env(monkeypatch)
        monkeypatch.setenv("APP_ACCESS_TOKENS", "alpha|beta|gamma")
        s = Settings()
        tokens = s.APP_ACCESS_TOKENS
        assert tokens[0] == "alpha"
        assert tokens[1] == "beta"
        assert tokens[2] == "gamma"

    def test_whitespace_trimmed(self, monkeypatch):
        _clear_token_env(monkeypatch)
        monkeypatch.setenv("APP_ACCESS_TOKENS", "  one  | two |three ")
        s = Settings()
        assert s.APP_ACCESS_TOKENS == ["one", "two", "three"]

    def test_repeated_separators(self, monkeypatch):
        _clear_token_env(monkeypatch)
        monkeypatch.setenv("APP_ACCESS_TOKENS", "key1||key2")
        s = Settings()
        assert s.APP_ACCESS_TOKENS == ["key1", "key2"]

    def test_leading_trailing_separators(self, monkeypatch):
        _clear_token_env(monkeypatch)
        monkeypatch.setenv("APP_ACCESS_TOKENS", "|key1|key2|")
        s = Settings()
        assert s.APP_ACCESS_TOKENS == ["key1", "key2"]

    def test_duplicate_removal_preserves_order(self, monkeypatch):
        _clear_token_env(monkeypatch)
        monkeypatch.setenv("APP_ACCESS_TOKENS", "a|b|a|c|b")
        s = Settings()
        assert s.APP_ACCESS_TOKENS == ["a", "b", "c"]

    def test_case_preserved(self, monkeypatch):
        _clear_token_env(monkeypatch)
        monkeypatch.setenv("APP_ACCESS_TOKENS", "AbC|deF")
        s = Settings()
        assert s.APP_ACCESS_TOKENS == ["AbC", "deF"]

    def test_empty_and_whitespace_only_entries_ignored(self, monkeypatch):
        _clear_token_env(monkeypatch)
        monkeypatch.setenv("APP_ACCESS_TOKENS", "|  |key|   |")
        s = Settings()
        assert s.APP_ACCESS_TOKENS == ["key"]


# --------------------------------------------------------------------------- #
#  2. Shared helper tests  (is_valid_access_token)
# --------------------------------------------------------------------------- #


class TestIsValidAccessToken:
    """Validate individual tokens against configured keys."""

    def test_legacy_token_accepted(self, monkeypatch):
        _clear_token_env(monkeypatch)
        monkeypatch.setenv("APP_ACCESS_TOKEN", "my-key")
        assert is_valid_access_token("my-key") is True

    def test_first_plural_token_accepted(self, monkeypatch):
        _clear_token_env(monkeypatch)
        monkeypatch.setenv("APP_ACCESS_TOKENS", "first|second|third")
        assert is_valid_access_token("first") is True

    def test_middle_plural_token_accepted(self, monkeypatch):
        _clear_token_env(monkeypatch)
        monkeypatch.setenv("APP_ACCESS_TOKENS", "first|second|third")
        assert is_valid_access_token("second") is True

    def test_last_plural_token_accepted(self, monkeypatch):
        _clear_token_env(monkeypatch)
        monkeypatch.setenv("APP_ACCESS_TOKENS", "first|second|third")
        assert is_valid_access_token("third") is True

    def test_invalid_token_rejected(self, monkeypatch):
        _clear_token_env(monkeypatch)
        monkeypatch.setenv("APP_ACCESS_TOKEN", "correct")
        assert is_valid_access_token("wrong") is False

    def test_empty_string_rejected(self, monkeypatch):
        _clear_token_env(monkeypatch)
        monkeypatch.setenv("APP_ACCESS_TOKEN", "key")
        assert is_valid_access_token("") is False

    def test_non_string_rejected(self, monkeypatch):
        _clear_token_env(monkeypatch)
        monkeypatch.setenv("APP_ACCESS_TOKEN", "key")
        assert is_valid_access_token(123) is False  # type: ignore[arg-type]
        assert is_valid_access_token(None) is False  # type: ignore[arg-type]

    def test_partial_match_rejected(self, monkeypatch):
        _clear_token_env(monkeypatch)
        monkeypatch.setenv("APP_ACCESS_TOKEN", "password")
        assert is_valid_access_token("pass") is False

    def test_case_mismatch_rejected(self, monkeypatch):
        _clear_token_env(monkeypatch)
        monkeypatch.setenv("APP_ACCESS_TOKEN", "MyKey")
        assert is_valid_access_token("mykey") is False
        assert is_valid_access_token("MYKEY") is False

    def test_no_configured_tokens_fails_closed(self, monkeypatch):
        _clear_token_env(monkeypatch)
        assert is_valid_access_token("anything") is False

    def test_submitted_whitespace_not_normalized_by_helper(self, monkeypatch):
        """Helper does not strip the *submitted* token — config parsing trims."""
        _clear_token_env(monkeypatch)
        monkeypatch.setenv("APP_ACCESS_TOKEN", "key")
        # Submitted value has trailing space; helper should reject it.
        assert is_valid_access_token("key ") is False

    def test_compare_digest_called_for_every_configured_token(self, monkeypatch):
        """Even when the first token matches, all configured tokens are
        evaluated (constant-time timing semantics)."""
        _clear_token_env(monkeypatch)
        monkeypatch.setenv("APP_ACCESS_TOKENS", "a|b|c")

        call_log = []

        def fake_compare(a, b):
            call_log.append((a, b))
            return a == b

        with patch("backend.auth.secrets.compare_digest", side_effect=fake_compare):
            is_valid_access_token("a")  # first token matches

        assert len(call_log) == 3
        assert call_log[0][1] == "a"
        assert call_log[1][1] == "b"
        assert call_log[2][1] == "c"


# --------------------------------------------------------------------------- #
#  3. Settings validation tests
# --------------------------------------------------------------------------- #

# Minimum non-secret env needed for Settings.validate() to reach the
# access-token check without connecting to a database.
_SAFE_ENV = {
    "DATABASE_URL": "sqlite:///:memory:",
    "AI_PROVIDER": "ollama",
    "OLLAMA_MODEL": "test-model",
}


def _set_safe_env(monkeypatch):
    for k, v in _SAFE_ENV.items():
        monkeypatch.setenv(k, v)


class TestSettingsValidation:
    """APP_ACCESS_TOKEN / APP_ACCESS_TOKENS required by Settings.validate()."""

    def test_legacy_token_only_passes(self, monkeypatch):
        _clear_token_env(monkeypatch)
        _set_safe_env(monkeypatch)
        monkeypatch.setenv("APP_ACCESS_TOKEN", "legacy-key")
        s = Settings()
        # validate() should not raise for the access-token check
        try:
            s.validate()
        except EnvironmentError as exc:
            assert "TOKEN" not in str(exc).upper() or "DATABASE" in str(
                exc
            ), f"Unexpected validation error: {exc}"

    def test_plural_token_only_passes(self, monkeypatch):
        _clear_token_env(monkeypatch)
        _set_safe_env(monkeypatch)
        monkeypatch.setenv("APP_ACCESS_TOKENS", "k1|k2")
        s = Settings()
        try:
            s.validate()
        except EnvironmentError as exc:
            assert "TOKEN" not in str(exc).upper() or "DATABASE" in str(
                exc
            ), f"Unexpected validation error: {exc}"

    def test_no_token_raises_environment_error(self, monkeypatch):
        _clear_token_env(monkeypatch)
        _set_safe_env(monkeypatch)
        s = Settings()
        with pytest.raises(EnvironmentError, match="TOKEN"):
            s.validate()


# --------------------------------------------------------------------------- #
#  4. HTTP Bearer authentication tests
# --------------------------------------------------------------------------- #


class TestHTTPBearerAuthentication:
    """verify_app_access_token via FastAPI dependency."""

    def test_missing_header_401(self, http_client, monkeypatch):
        _clear_token_env(monkeypatch)
        monkeypatch.setenv("APP_ACCESS_TOKEN", "key")
        resp = http_client.get("/protected2")
        assert resp.status_code == 401
        assert "Missing or invalid Authorization header" in resp.json()["detail"]

    def test_wrong_scheme_401(self, http_client, monkeypatch):
        _clear_token_env(monkeypatch)
        monkeypatch.setenv("APP_ACCESS_TOKEN", "key")
        resp = http_client.get(
            "/protected2", headers={"Authorization": "Basic key"}
        )
        assert resp.status_code == 401
        assert "Missing or invalid Authorization header" in resp.json()["detail"]

    def test_invalid_bearer_token_401(self, http_client, monkeypatch):
        _clear_token_env(monkeypatch)
        monkeypatch.setenv("APP_ACCESS_TOKEN", "correct")
        resp = http_client.get(
            "/protected2", headers={"Authorization": "Bearer wrong"}
        )
        assert resp.status_code == 401
        assert "Invalid access token" in resp.json()["detail"]

    def test_legacy_token_accepted(self, http_client, monkeypatch):
        _clear_token_env(monkeypatch)
        monkeypatch.setenv("APP_ACCESS_TOKEN", "legacy-key")
        resp = http_client.get(
            "/protected2", headers={"Authorization": "Bearer legacy-key"}
        )
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}

    def test_first_plural_token_accepted(self, http_client, monkeypatch):
        _clear_token_env(monkeypatch)
        monkeypatch.setenv("APP_ACCESS_TOKENS", "first|middle|last")
        resp = http_client.get(
            "/protected2", headers={"Authorization": "Bearer first"}
        )
        assert resp.status_code == 200

    def test_middle_plural_token_accepted(self, http_client, monkeypatch):
        _clear_token_env(monkeypatch)
        monkeypatch.setenv("APP_ACCESS_TOKENS", "first|middle|last")
        resp = http_client.get(
            "/protected2", headers={"Authorization": "Bearer middle"}
        )
        assert resp.status_code == 200

    def test_last_plural_token_accepted(self, http_client, monkeypatch):
        _clear_token_env(monkeypatch)
        monkeypatch.setenv("APP_ACCESS_TOKENS", "first|middle|last")
        resp = http_client.get(
            "/protected2", headers={"Authorization": "Bearer last"}
        )
        assert resp.status_code == 200

    def test_partial_token_rejected(self, http_client, monkeypatch):
        _clear_token_env(monkeypatch)
        monkeypatch.setenv("APP_ACCESS_TOKEN", "password")
        resp = http_client.get(
            "/protected2", headers={"Authorization": "Bearer pass"}
        )
        assert resp.status_code == 401

    def test_case_mismatch_rejected(self, http_client, monkeypatch):
        _clear_token_env(monkeypatch)
        monkeypatch.setenv("APP_ACCESS_TOKEN", "MyKey")
        resp = http_client.get(
            "/protected2", headers={"Authorization": "Bearer mykey"}
        )
        assert resp.status_code == 401


# --------------------------------------------------------------------------- #
#  5. WebSocket authentication tests
# --------------------------------------------------------------------------- #


def _encode_token(token: str) -> str:
    """URL-safe Base64 without padding, matching existing convention."""
    return base64.urlsafe_b64encode(token.encode()).decode().rstrip("=")


@pytest.fixture
def ws_app(monkeypatch):
    """Import the full app and mock MarketDataService so the WS route is live."""
    from backend.main import app as main_app

    market_data = MagicMock()
    market_data.latest_quotes = {}
    monkeypatch.setattr(
        "backend.routers.websocket.MarketDataService.get_instance",
        lambda: market_data,
    )
    return main_app


class TestWebSocketAuthentication:
    """WebSocket close-code 4401 for unauthorized clients."""

    def test_legacy_token_accepted(self, ws_app, monkeypatch):
        _clear_token_env(monkeypatch)
        monkeypatch.setenv("APP_ACCESS_TOKEN", "ws-key")
        encoded = _encode_token("ws-key")
        with TestClient(ws_app) as client:
            with client.websocket_connect(
                "/ws", subprotocols=["yapvibes," + encoded]
            ) as ws:
                assert ws.accepted_subprotocol is not None

    def test_first_plural_token_accepted(self, ws_app, monkeypatch):
        _clear_token_env(monkeypatch)
        monkeypatch.setenv("APP_ACCESS_TOKENS", "one|two|three")
        encoded = _encode_token("one")
        with TestClient(ws_app) as client:
            with client.websocket_connect(
                "/ws", subprotocols=["yapvibes," + encoded]
            ) as ws:
                assert ws.accepted_subprotocol is not None

    def test_middle_plural_token_accepted(self, ws_app, monkeypatch):
        _clear_token_env(monkeypatch)
        monkeypatch.setenv("APP_ACCESS_TOKENS", "one|two|three")
        encoded = _encode_token("two")
        with TestClient(ws_app) as client:
            with client.websocket_connect(
                "/ws", subprotocols=["yapvibes," + encoded]
            ) as ws:
                assert ws.accepted_subprotocol is not None

    def test_last_plural_token_accepted(self, ws_app, monkeypatch):
        _clear_token_env(monkeypatch)
        monkeypatch.setenv("APP_ACCESS_TOKENS", "one|two|three")
        encoded = _encode_token("three")
        with TestClient(ws_app) as client:
            with client.websocket_connect(
                "/ws", subprotocols=["yapvibes," + encoded]
            ) as ws:
                assert ws.accepted_subprotocol is not None

    def test_invalid_token_closes_4401(self, ws_app, monkeypatch):
        _clear_token_env(monkeypatch)
        monkeypatch.setenv("APP_ACCESS_TOKEN", "correct")
        encoded = _encode_token("wrong")
        with TestClient(ws_app) as client:
            with pytest.raises(WebSocketDisconnect) as exc:
                with client.websocket_connect(
                    "/ws", subprotocols=["yapvibes," + encoded]
                ):
                    raise AssertionError("should not connect")
            assert exc.value.code == 4401

    def test_empty_encoded_token_closes_4401(self, ws_app, monkeypatch):
        _clear_token_env(monkeypatch)
        monkeypatch.setenv("APP_ACCESS_TOKEN", "key")
        encoded = _encode_token("")
        with TestClient(ws_app) as client:
            with pytest.raises(WebSocketDisconnect) as exc:
                with client.websocket_connect(
                    "/ws", subprotocols=["yapvibes," + encoded]
                ):
                    raise AssertionError("should not connect")
            assert exc.value.code == 4401

    def test_malformed_base64_closes_4401(self, ws_app, monkeypatch):
        _clear_token_env(monkeypatch)
        monkeypatch.setenv("APP_ACCESS_TOKEN", "key")
        with TestClient(ws_app) as client:
            with pytest.raises(WebSocketDisconnect) as exc:
                with client.websocket_connect(
                    "/ws", subprotocols=["yapvibes,!!!not-base64"]
                ):
                    raise AssertionError("should not connect")
            assert exc.value.code == 4401

    def test_partial_token_closes_4401(self, ws_app, monkeypatch):
        _clear_token_env(monkeypatch)
        monkeypatch.setenv("APP_ACCESS_TOKEN", "password")
        encoded = _encode_token("pass")
        with TestClient(ws_app) as client:
            with pytest.raises(WebSocketDisconnect) as exc:
                with client.websocket_connect(
                    "/ws", subprotocols=["yapvibes," + encoded]
                ):
                    raise AssertionError("should not connect")
            assert exc.value.code == 4401

    def test_case_mismatch_closes_4401(self, ws_app, monkeypatch):
        _clear_token_env(monkeypatch)
        monkeypatch.setenv("APP_ACCESS_TOKEN", "MyKey")
        encoded = _encode_token("mykey")
        with TestClient(ws_app) as client:
            with pytest.raises(WebSocketDisconnect) as exc:
                with client.websocket_connect(
                    "/ws", subprotocols=["yapvibes," + encoded]
                ):
                    raise AssertionError("should not connect")
            assert exc.value.code == 4401
