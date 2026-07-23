import asyncio
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

    connection_manager = app.state.connection_manager
    await connection_manager.connect(websocket, subprotocol="yapvibes")

    try:
        # Send cached quotes immediately on connect
        market_data = MarketDataService.get_instance()
        for quote in market_data.latest_quotes.values():
            await websocket.send_json(quote)

        # Idle loop to keep the connection alive
        while True:
            await asyncio.sleep(60)
    except WebSocketDisconnect:
        logger.debug("[WS] Client disconnected")
    except Exception as e:
        logger.debug("[WS] Connection closed for %s: %s", websocket.client_host, e)
    finally:
        await connection_manager.disconnect(websocket)
