# services/connection_manager.py
"""WebSocket connection manager with thread-safe broadcast and cleanup."""
import asyncio
from dataclasses import dataclass
import logging
import time
from typing import List
from uuid import uuid4

from fastapi import WebSocket

logger = logging.getLogger(__name__)

DEFAULT_CLOSE_REASONS = {
    1000: "normal_closure",
    1001: "endpoint_going_away",
    1005: "no_status_received",
    1006: "abnormal_closure",
    1011: "internal_error",
    1012: "service_restart",
    1013: "try_again_later",
    4401: "unauthorized",
}


@dataclass(frozen=True)
class ConnectionDetails:
    """Safe, non-secret metadata used to correlate WebSocket lifecycle logs."""

    connection_id: str
    channel: str
    client: str
    origin: str
    user_agent: str
    connected_at: float


class ConnectionManager:
    """Manages WebSocket connections with proper locking to prevent race conditions."""

    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self._connection_details: dict[WebSocket, ConnectionDetails] = {}
        self._lock = asyncio.Lock()

    @staticmethod
    def _safe_log_value(
        value: str | None,
        *,
        fallback: str = "-",
        max_length: int = 160,
    ) -> str:
        """Escape control characters and bound untrusted header values."""
        if not value:
            return fallback
        return (
            value.replace("\r", "\\r").replace("\n", "\\n")[:max_length]
            or fallback
        )

    @classmethod
    def _disconnect_reason(
        cls,
        *,
        code: int | None,
        reason: str | None,
    ) -> str:
        if reason:
            return cls._safe_log_value(reason, max_length=120)
        if code is None:
            return "unknown"
        return DEFAULT_CLOSE_REASONS.get(code, f"close_code:{code}")

    @classmethod
    def _client_label(cls, websocket: WebSocket) -> str:
        """Prefer the forwarded browser address when running behind a proxy."""
        forwarded_for = websocket.headers.get("x-forwarded-for")
        if forwarded_for:
            return cls._safe_log_value(
                forwarded_for.split(",", 1)[0].strip(),
                max_length=80,
            )

        client = websocket.client
        if client is None:
            return "-"
        return cls._safe_log_value(
            f"{client.host}:{client.port}",
            max_length=80,
        )

    @classmethod
    def _build_details(cls, websocket: WebSocket, channel: str) -> ConnectionDetails:
        return ConnectionDetails(
            connection_id=uuid4().hex[:12],
            channel=cls._safe_log_value(channel, max_length=32),
            client=cls._client_label(websocket),
            origin=cls._safe_log_value(websocket.headers.get("origin")),
            user_agent=cls._safe_log_value(websocket.headers.get("user-agent")),
            connected_at=time.monotonic(),
        )

    @classmethod
    def _log_disconnected(
        cls,
        details: ConnectionDetails,
        *,
        code: int | None,
        reason: str | None,
        total: int,
    ) -> None:
        duration_ms = max(0, int((time.monotonic() - details.connected_at) * 1000))
        logger.info(
            "[WS] Disconnected id=%s channel=%s client=%s code=%s "
            "reason=%r duration_ms=%d total=%d",
            details.connection_id,
            details.channel,
            details.client,
            code if code is not None else "-",
            cls._disconnect_reason(code=code, reason=reason),
            duration_ms,
            total,
        )

    async def connect(
        self,
        websocket: WebSocket,
        subprotocol: str | None = None,
        channel: str = "unspecified",
    ) -> str:
        await websocket.accept(subprotocol=subprotocol)
        details = self._build_details(websocket, channel)
        async with self._lock:
            self.active_connections.append(websocket)
            self._connection_details[websocket] = details
            total = len(self.active_connections)
        logger.info(
            "[WS] Connected id=%s channel=%s client=%s origin=%r "
            "user_agent=%r total=%d",
            details.connection_id,
            details.channel,
            details.client,
            details.origin,
            details.user_agent,
            total,
        )
        return details.connection_id

    async def disconnect(
        self,
        websocket: WebSocket,
        *,
        code: int | None = None,
        reason: str | None = None,
    ) -> None:
        """Remove and describe a WebSocket connection (async-safe)."""
        async with self._lock:
            if websocket not in self.active_connections:
                return
            self.active_connections.remove(websocket)
            details = self._connection_details.pop(websocket, None)
            total = len(self.active_connections)

        if details is not None:
            self._log_disconnected(
                details,
                code=code,
                reason=reason,
                total=total,
            )

    async def broadcast(self, quote: dict) -> None:
        """Send a single quote update to all connected clients, cleaning up dead connections."""
        disconnected: list[tuple[WebSocket, str]] = []
        async with self._lock:
            connections = list(self.active_connections)
        for ws in connections:
            try:
                await ws.send_json(quote)
            except Exception as e:
                error_name = type(e).__name__
                logger.debug(
                    "[WS] Connection dead during broadcast, removing: %s",
                    error_name,
                )
                disconnected.append((ws, error_name))

        if disconnected:
            removed: list[tuple[ConnectionDetails, str]] = []
            async with self._lock:
                for ws, error_name in disconnected:
                    if ws in self.active_connections:
                        self.active_connections.remove(ws)
                        details = self._connection_details.pop(ws, None)
                        if details is not None:
                            removed.append((details, error_name))
                total = len(self.active_connections)

            for details, error_name in removed:
                self._log_disconnected(
                    details,
                    code=None,
                    reason=f"broadcast_error:{error_name}",
                    total=total,
                )
            if removed:
                logger.warning(
                    "[WS] Cleaned up %d dead connections. Total: %d",
                    len(removed),
                    total,
                )