import base64
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.auth import is_valid_access_token
from backend.services.market_data_service import MarketDataService

logger = logging.getLogger(__name__)
router = APIRouter(tags=["websocket"])


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    # Import here to avoid circular imports (main.py imports this module)
    from backend.main import app

    # Browsers cannot attach an Authorization header to WebSocket handshakes.
    # Carry the single-user token as the second WebSocket subprotocol instead
    # of exposing it in the URL/query string. Echo only the non-secret protocol.
    protocols = [p.strip() for p in websocket.headers.get("sec-websocket-protocol", "").split(",")]
    token = ""
    if len(protocols) == 2 and protocols[0] == "yapvibes":
        try:
            encoded = protocols[1]
            token = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            token = ""
    if not is_valid_access_token(token):
        await websocket.close(code=4401, reason="Unauthorized")
        return

    requested_channel = websocket.query_params.get("channel", "").strip().lower()
    channel = requested_channel if requested_channel in {"prices", "news"} else "unspecified"

    connection_manager = app.state.connection_manager
    connection_id = await connection_manager.connect(
        websocket,
        subprotocol="yapvibes",
        channel=channel,
    )
    close_code: int | None = None
    close_reason: str | None = None

    try:
        # Send cached quotes immediately on connect
        market_data = MarketDataService.get_instance()
        for quote in market_data.latest_quotes.values():
            await websocket.send_json(quote)

        # Consume ASGI events so client disconnects are observed immediately.
        # A sleep-only loop leaves closed sockets in active_connections until a
        # later broadcast happens to fail.
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                close_code = message.get("code", 1000)
                close_reason = message.get("reason") or None
                logger.debug("[WS] Client disconnected id=%s", connection_id)
                break
    except WebSocketDisconnect as exc:
        close_code = exc.code
        close_reason = exc.reason or None
        logger.debug("[WS] Client disconnected id=%s", connection_id)
    except Exception as exc:
        close_reason = f"server_error:{type(exc).__name__}"
        logger.debug(
            "[WS] Connection closed id=%s error=%s",
            connection_id,
            type(exc).__name__,
        )
    finally:
        await connection_manager.disconnect(
            websocket,
            code=close_code,
            reason=close_reason,
        )