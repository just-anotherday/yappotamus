# services/yfinance_service.py
"""
Backward-compatible shim — re-exports from hybrid_data_service.

All existing imports like:
    from backend.services.yfinance_service import get_stock_price, get_batch_prices, get_ticker_info
continue to work but route through the hybrid layer (Finnhub primary → yfinance fallback).

Every result is tagged with `data_source: "fh"` or `data_source: "yf"`.
"""

from backend.services.hybrid_data_service import (
    get_hybrid_stock_price as get_stock_price,
    get_hybrid_batch_prices as get_batch_prices,
)
from backend.services.finnhub_service import get_ticker_info

__all__ = [
    "get_ticker_info",
    "get_stock_price",
    "get_batch_prices",
]