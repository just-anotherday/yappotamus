import asyncio
from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from backend.lib.tickers import normalize_ticker
from backend.models.stock import StockResponse
from backend.services.hybrid_data_service import get_hybrid_stock_price as get_stock_price

router = APIRouter(prefix="/api/stock", tags=["stock"])

# Hybrid API timeout (Finnhub primary + yfinance fallback)
HYBRID_TIMEOUT = 30  # seconds


async def _get_stock_price_safe(ticker: str) -> Dict[str, Any]:
    """Fetch ticker data via hybrid service (Finnhub → yfinance fallback) with a timeout."""
    try:
        return await asyncio.wait_for(
            get_stock_price(ticker),
            timeout=HYBRID_TIMEOUT,
        )
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=504,
            detail=f"Ticker data fetch timed out after {HYBRID_TIMEOUT}s for {ticker}",
        )


@router.get("/{ticker}", response_model=StockResponse)
async def get_stock(ticker: str):
    """Fetch full stock data for a single ticker via hybrid service (Finnhub primary, yfinance fallback)."""
    try:
        ticker = normalize_ticker(ticker)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    try:
        info = await _get_stock_price_safe(ticker)

        if not info or info.get("symbol") != ticker:
            raise HTTPException(status_code=404, detail=f"Ticker {ticker} not found")

        current_price = info.get("current_price", 0)
        previous_close = info.get("previous_close", 0)

        return StockResponse(
            ticker=ticker,
            symbol=info.get("symbol", ticker),
            company_name=info.get("company_name", "N/A"),
            current_price=current_price,
            previous_close=previous_close,
            change=info.get("change", 0),
            change_percent=round(info.get("change_percent", 0) or 0, 2),
            market_cap=info.get("market_cap", 0),
            fifty_two_week_high=info.get("fifty_two_week_high", 0),
            fifty_two_week_low=info.get("fifty_two_week_low", 0),
            volume=int(info.get("volume", 0)),
            pe_ratio=info.get("forward_pe"),
            currency="USD",
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching data: {str(e)}")
