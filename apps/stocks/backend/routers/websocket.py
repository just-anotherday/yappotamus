import asyncio
import logging

from fastapi import APIRouter, WebSocket

from backend.services.market_data_service import MarketDataService

logger = logging.getLogger(__name__)
router = APIRouter(tags=["websocket"])


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    # Import here to avoid circular imports (main.py imports this module)
    from backend.main import app

    connection_manager = app.state.connection_manager
    await connection_manager.connect(websocket)

    try:
        # Send cached quotes immediately on connect
        market_data = MarketDataService.get_instance()
        for quote in market_data.latest_quotes.values():
            await websocket.send_json(quote)

        # Idle loop to keep the connection alive
        while True:
            await asyncio.sleep(60)
    except Exception as e:
        logger.debug("[WS] Connection closed for %s: %s", websocket.client_host, e)
    finally:
        await connection_manager.disconnect(websocket)
