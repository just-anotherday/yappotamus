import asyncio
import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException, Body, Depends
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

from backend.lib.tickers import normalize_ticker
from backend.models.stock import WatchlistItem
from backend.models.watchlist_schemas import AddTickerRequest, WatchlistResponse, WatchlistConfigResponse
from backend.services.hybrid_data_service import (
    get_hybrid_stock_price as get_stock_price,
    get_hybrid_batch_prices as get_batch_prices,
)
from backend.services.market_data_service import MarketDataService
from backend.config.watchlist import DEFAULT_TICKERS, MAX_WATCHLIST_SIZE, CONFIG_VERSION
from backend.config.database import get_async_session, async_session_factory
from backend.services.news_ingestion_service import fetch_and_ingest_news
from backend.services.watchlist_service import seed_defaults, get_all_tickers, add_ticker, remove_ticker, update_order
from backend.services.post_market_service import PostMarketService

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])

# Timeout for batch price fetching (Finnhub + yfallback hybrid)
BATCH_TIMEOUT = 90  # seconds - increased for parallel Finnhub batches + concurrent yfinance fallback


async def _get_batch_prices_safe(tickers: list[str]) -> list:
    """Fetch batch prices from Finnhub with timeout."""
    try:
        return await asyncio.wait_for(
            get_batch_prices(tickers),
            timeout=BATCH_TIMEOUT,
        )
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=504,
            detail=f"Watchlist data fetch timed out after {BATCH_TIMEOUT}s",
        )


async def _get_stock_price_safe(ticker: str):
    """Fetch single stock price from Finnhub with timeout."""
    try:
        return await asyncio.wait_for(
            get_stock_price(ticker),
            timeout=15,
        )
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=504,
            detail=f"Stock data fetch timed out after 15s for {ticker}",
        )


@router.get("", response_model=list[WatchlistItem])
async def get_watchlist(
    tickers: str | None = None,
    session: AsyncSession = Depends(get_async_session),
):
    """Fetch fundamental + static price data for the persistent watchlist tickers.
    If ?tickers=... is provided, fetch those explicitly instead (backward compat).
    """
    if tickers:
        raw_list = [t.strip() for t in tickers.split(",") if t.strip()]
        validated: list[str] = []
        for t in raw_list:
            try:
                validated.append(normalize_ticker(t))
            except ValueError as e:
                raise HTTPException(status_code=400, detail=f"Invalid ticker '{t}': {e}")
        ticker_list = validated
    else:
        ticker_list = await get_all_tickers(session)

    if not ticker_list:
        return []

    try:
        results = await _get_batch_prices_safe(ticker_list)
        # Inject post-market data into each result
        pm_service = PostMarketService.get_instance()
        pm_data = pm_service.get_post_market_data()
        for item in results:
            ticker_key = item.get("ticker", "")
            if ticker_key and ticker_key in pm_data:
                item.update(pm_data[ticker_key])
        return [WatchlistItem(**item) for item in results]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching watchlist: {str(e)}")


@router.post("/add", response_model=WatchlistResponse)
async def add_to_watchlist(
    request: AddTickerRequest = Body(...),
    session: AsyncSession = Depends(get_async_session),
):
    """Add a single ticker to the persistent watchlist (idempotent)."""
    try:
        ticker = normalize_ticker(request.ticker)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    market_data = MarketDataService.get_instance()

    try:
        await add_ticker(session, ticker)
    except ValueError as e:
        error_msg = str(e)
        if "full" in error_msg:
            raise HTTPException(status_code=400, detail=error_msg)
        raise HTTPException(status_code=409, detail=error_msg)

    # Subscribe to live WS updates for the new ticker
    market_data.subscribe([ticker])

    # TD-007 fix: Track background task properly with error handling
    async def _ingest_with_tracking(ticker_sym: str):
        try:
            async with async_session_factory() as news_session:
                await fetch_and_ingest_news(ticker_sym, news_session, limit=20)
            logger.info("[Watchlist] Background news ingestion for %s complete.", ticker_sym)
        except Exception as e:
            logger.error("[Watchlist] Background news ingestion for %s failed: %s", ticker_sym, e)

    # Create tracked task (TD-007 fix)
    task = asyncio.create_task(_ingest_with_tracking(ticker))
    task.add_done_callback(
        lambda t: logger.warning("Background ingest task exception: %s", t.exception()) 
        if t.cancelled() is False and t.exception() else None
    )

    # Fetch full watchlist data for the ticker
    try:
        item = await _get_stock_price_safe(ticker)
        if not item:
            raise HTTPException(status_code=404, detail=f"Ticker {ticker} not found")
        watchlist_item = WatchlistItem(**item)
        return WatchlistResponse(
            success=True,
            message=f"{ticker} added to watchlist.",
            data=watchlist_item,
        )
    except HTTPException:
        raise
    except Exception as e:
        # Roll back: remove from DB on data fetch failure
        try:
            await remove_ticker(session, ticker)
        except KeyError:
            pass
        raise HTTPException(status_code=500, detail=f"Failed to add {ticker}: {str(e)}")


@router.put("/order")
async def update_watchlist_order(
    tickers: list[str] = Body(..., embed=True),
    session: AsyncSession = Depends(get_async_session),
):
    """Update the visual ordering of watchlist tickers."""
    validated: list[str] = []
    for t in tickers:
        try:
            validated.append(normalize_ticker(t))
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid ticker '{t}': {e}")
    normalized = validated

    try:
        await update_order(session, normalized)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"success": True}


@router.delete("/{ticker}", response_model=WatchlistResponse)
async def remove_from_watchlist(
    ticker: str,
    session: AsyncSession = Depends(get_async_session),
):
    """Remove a single ticker from the persistent watchlist."""
    try:
        ticker = normalize_ticker(ticker)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        await remove_ticker(session, ticker)
    except KeyError as e:
        raise HTTPException(
            status_code=404,
            detail=f"{ticker} is not in your watchlist."
        )

    return WatchlistResponse(
        success=True,
        message=f"{ticker} removed from watchlist.",
        data=None,
    )


@router.post("/post-market/refresh")
async def refresh_post_market_prices():
    """Manually trigger post-market price fetch (useful for testing)."""
    pm_service = PostMarketService.get_instance()
    try:
        async with async_session_factory() as session:
            tickers = await get_all_tickers(session)
        if not tickers:
            return {"success": True, "message": "No tickers in watchlist.", "updated": 0}

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, pm_service.fetch_all, tickers)

        data = pm_service.get_post_market_data()
        return {
            "success": True,
            "message": f"Fetched post-market prices.",
            "updated": len(data),
            "tickers": list(data.keys()),
        }
    except Exception as e:
        logger.error("[Watchlist] Post-market refresh failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to refresh post-market prices: {str(e)}")


@router.get("/post-market")
async def get_post_market_prices():
    """Return the latest cached extended-hours prices without refetching fundamentals."""
    return PostMarketService.get_instance().get_post_market_data()


@router.get("/config", response_model=WatchlistConfigResponse)
async def get_watchlist_config():
    """Return watchlist configuration (defaults, limits, version)."""
    return WatchlistConfigResponse(
        default_tickers=list(DEFAULT_TICKERS),
        max_watchlist_size=MAX_WATCHLIST_SIZE,
        version=CONFIG_VERSION,
    )
