# services/connection_manager.py
"""WebSocket connection manager with thread-safe broadcast and cleanup."""
import asyncio
import logging
from fastapi import WebSocket
from typing import List

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages WebSocket connections with proper locking to prevent race conditions."""

    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, subprotocol: str | None = None):
        await websocket.accept(subprotocol=subprotocol)
        async with self._lock:
            self.active_connections.append(websocket)
        logger.info("[WS] New connection. Total: %d", len(self.active_connections))

    async def disconnect(self, websocket: WebSocket) -> None:
        """Remove a WebSocket connection (async-safe)."""
        async with self._lock:
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)
                logger.info("[WS] Disconnected. Total: %d", len(self.active_connections))

    async def broadcast(self, quote: dict) -> None:
        """Send a single quote update to all connected clients, cleaning up dead connections."""
        disconnected = []
        async with self._lock:
            connections = list(self.active_connections)
        for ws in connections:
            try:
                await ws.send_json(quote)
            except Exception as e:
                logger.debug("[WS] Connection dead during broadcast, removing: %s", e)
                disconnected.append(ws)

        # Clean up dead connections under lock
        if disconnected:
            async with self._lock:
                for ws in disconnected:
                    if ws in self.active_connections:
                        self.active_connections.remove(ws)
            logger.warning("[WS] Cleaned up %d dead connections.", len(disconnected))
