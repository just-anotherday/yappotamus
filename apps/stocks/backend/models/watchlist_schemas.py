"""Pydantic schemas for watchlist API request/response bodies."""

from typing import Optional
from pydantic import BaseModel, Field

from backend.models.stock import WatchlistItem


class AddTickerRequest(BaseModel):
    """Request body for adding a ticker to the watchlist."""
    ticker: str = Field(..., min_length=1, max_length=10)


class WatchlistResponse(BaseModel):
    """Standard response envelope for watchlist mutations."""
    success: bool
    message: str
    data: Optional[WatchlistItem] = None


class WatchlistConfigResponse(BaseModel):
    """Configuration response with defaults, limits, and version info."""
    default_tickers: list[str]
    max_watchlist_size: int
    version: int
