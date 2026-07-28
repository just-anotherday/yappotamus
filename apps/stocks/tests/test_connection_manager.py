"""WebSocket connection lifecycle logging regressions."""

import logging
from types import SimpleNamespace

import pytest

from backend.services.connection_manager import ConnectionManager


class FakeWebSocket:
    def __init__(self, *, fail_send: bool = False):
        self.fail_send = fail_send
        self.accepted_subprotocol = None
        self.client = SimpleNamespace(host="127.0.0.1", port=43210)
        self.headers = {
            "origin": "https://stocks.yapvibes.com",
            "user-agent": "YapVibesTest/1.0",
            "sec-websocket-protocol": "yapvibes, secret-token-that-must-not-be-logged",
        }

    async def accept(self, subprotocol=None):
        self.accepted_subprotocol = subprotocol

    async def send_json(self, payload):
        if self.fail_send:
            raise RuntimeError("simulated dead connection")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("code", "reason", "expected_reason"),
    [
        (1000, None, "normal_closure"),
        (1001, None, "endpoint_going_away"),
        (1005, None, "no_status_received"),
        (1006, None, "abnormal_closure"),
        (1011, None, "internal_error"),
        (1012, None, "service_restart"),
        (1013, None, "try_again_later"),
        (4999, None, "close_code:4999"),
        (None, None, "unknown"),
        (1000, "Component unmounted", "Component unmounted"),
        (None, "server_error:RuntimeError", "server_error:RuntimeError"),
    ],
)
async def test_disconnect_reason_is_explicit_or_derived_from_close_code(
    caplog,
    code,
    reason,
    expected_reason,
):
    manager = ConnectionManager()
    websocket = FakeWebSocket()

    with caplog.at_level(logging.INFO, logger="backend.services.connection_manager"):
        connection_id = await manager.connect(
            websocket,
            subprotocol="yapvibes",
            channel="prices",
        )
        await manager.disconnect(websocket, code=code, reason=reason)

    messages = [record.getMessage() for record in caplog.records]
    connected = next(message for message in messages if message.startswith("[WS] Connected"))
    disconnected = next(
        message for message in messages if message.startswith("[WS] Disconnected")
    )

    assert websocket.accepted_subprotocol == "yapvibes"
    assert manager.active_connections == []
    assert f"id={connection_id}" in connected
    assert f"id={connection_id}" in disconnected
    assert f"reason={expected_reason!r}" in disconnected
    assert "secret-token-that-must-not-be-logged" not in connected
    assert "secret-token-that-must-not-be-logged" not in disconnected


@pytest.mark.asyncio
async def test_broadcast_failure_logs_reason_and_removes_connection(caplog):
    manager = ConnectionManager()
    websocket = FakeWebSocket(fail_send=True)

    with caplog.at_level(logging.INFO, logger="backend.services.connection_manager"):
        connection_id = await manager.connect(websocket, channel="news")
        await manager.broadcast({"type": "news_refresh"})

    messages = [record.getMessage() for record in caplog.records]
    disconnected = next(
        message for message in messages if message.startswith("[WS] Disconnected")
    )

    assert manager.active_connections == []
    assert f"id={connection_id}" in disconnected
    assert "channel=news" in disconnected
    assert "reason='broadcast_error:RuntimeError'" in disconnected