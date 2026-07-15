# services/hybrid_data_service.py
"""
Hybrid Data Service — Finnhub primary, yfinance enrichment for missing fundamentals.

Strategy:
  1. Try Finnhub first (real-time quotes, company profiles)
  2. If Finnhub returns no data or the symbol is a known ETF/index → full yfinance fallback
  3. For Finnhub-served stocks: enrich missing fundamental fields via yfinance in background
  4. Every result tagged with `data_source: "fh"` or `"yf"` + `yf_enriched_fields` list
     so the frontend can display source badges per field.

Rate limit sync:
  - Finnhub free tier: 60 calls/min (respecting internal rate limiter)
  - yfinance: runs in thread pool executor (non-blocking), no artificial delays
"""

import asyncio
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Set, Tuple

from backend.services.finnhub_service import get_stock_price as finnhub_get_stock_price
from backend.services.yfinance_fallback import get_stock_price_yf
from backend.lib.constants import KNOWN_NON_STOCK_SYMBOLS
from backend.lib.error_fallback import create_error_fallback

logger = logging.getLogger(__name__)

# Thread pool for running blocking yfinance calls without freezing the event loop.
_executor = ThreadPoolExecutor(max_workers=6, thread_name_prefix="yf-fallback")

# Bounded TTL cache: stores (data, timestamp) tuples. Entries older than
# _CACHE_TTL seconds are evicted on access. Max size limits memory growth.
_CACHE_TTL = float(os.getenv("HYBRID_CACHE_TTL_S", "300"))  # default 5 minutes
_CACHE_MAX_SIZE = int(os.getenv("HYBRID_CACHE_MAX_SIZE", "1000"))
_cache: Dict[str, Tuple[Dict[str, Any], float]] = {}


def _cache_get(ticker: str) -> Optional[Dict[str, Any]]:
    """Retrieve a cached entry if within TTL."""
    entry = _cache.get(ticker)
    if entry is None:
        return None
    data, ts = entry
    if time.time() - ts > _CACHE_TTL:
        del _cache[ticker]
        return None
    return data


def _cache_set(ticker: str, data: Dict[str, Any]) -> None:
    """Store a cached entry, evicting oldest entries if at capacity."""
    if len(_cache) >= _CACHE_MAX_SIZE:
        # Remove the oldest entry by timestamp
        oldest_key = min(_cache, key=lambda k: _cache[k][1])
        del _cache[oldest_key]
    _cache[ticker] = (data, time.time())


# Fields that Finnhub free tier cannot provide (return 0/None/N/A).
# yfinance is used as an enrichment source for these gaps.
FUNDAMENTAL_GAP_FIELDS: Set[str] = {
    "forward_pe",              # PE ratio
    "fifty_two_week_high",     # 52-week high
    "fifty_two_week_low",      # 52-week low
    "open_price",             # Today's open
    "day_low",                # Today's low
    "day_high",               # Today's high
    "shares_outstanding",     # Shares outstanding
    "float_shares",           # Float shares
    "insider_percent",        # Insider ownership %
    "institution_percent",    # Institution ownership %
    "short_percent_of_float", # Short interest %
    "shares_short",           # Short shares count
    "target_mean_price",      # Analyst mean target
    "target_median_price",    # Analyst median target
    "target_high_price",      # Analyst high target
    "target_low_price",       # Analyst low target
    "recommendation_key",     # Buy/Hold/Sell rating
    "number_of_analysts",     # Number of analysts covering
    "average_analyst_rating", # Average rating (1=Strong Buy)
    "long_business_summary",  # Business description
    "ceo_name",              # CEO name
    "full_time_employees",    # Employee count
    "regularMarketVolume",   # Volume data
    "market_cap",            # Market capitalization
    "beta",                  # Beta coefficient
    "security_type",         # Security classification (STOCK/ETF/INDEX/etc.)
}


def _is_gap_value(value: Any, field: str) -> bool:
    """Check if a value represents a Finnhub gap (missing/zero/default data)."""
    if value is None:
        return True
    if isinstance(value, str) and value in ("N/A", "", "Error"):
        return True
    # Numeric fields that are 0 when not available from Finnhub
    numeric_zero_fields = {
        "forward_pe", "fifty_two_week_high", "fifty_two_week_low",
        "shares_outstanding", "float_shares", "short_percent_of_float",
        "shares_short", "target_mean_price", "target_median_price",
        "target_high_price", "target_low_price", "number_of_analysts",
        "average_analyst_rating", "full_time_employees", "market_cap",
    }
    if field in numeric_zero_fields and value == 0:
        return True
    # Percent fields defaulting to 0 when not available
    percent_fields = {"insider_percent", "institution_percent"}
    if field in percent_fields and value == 0.0:
        return True
    # recommendation_key is "N/A" or "error" when not available
    if field == "recommendation_key" and value in ("N/A", "error"):
        return True
    # beta defaults to 1.0 when Finnhub doesn't provide it (hardcoded fallback)
    if field == "beta" and value == 1.0:
        return True
    return False


def _yf_sync(ticker: str) -> Optional[Dict[str, Any]]:
    """Run yfinance in a thread (called from executor)."""
    data = get_stock_price_yf(ticker)
    if data:
        data["data_source"] = "yf"
    return data


async def _yf_async(ticker: str) -> Optional[Dict[str, Any]]:
    """Offload blocking yfinance call to thread pool executor."""
    loop = asyncio.get_running_loop()
    data = await loop.run_in_executor(_executor, _yf_sync, ticker)
    if data:
        _cache_set(ticker.upper(), data)
    return data


def _enrich_with_yf(finnhub_data: Dict[str, Any], yf_data: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    """Merge yfinance fundamental data into Finnhub result for missing fields.
    
    Returns (merged_dict, list_of_enriched_fields).
    """
    enriched_fields = []
    merged = finnhub_data.copy()

    # If Finnhub company_name is just the ticker symbol (no real name from profile),
    # replace it with the actual company name from yfinance.
    fh_company = merged.get("company_name", "")
    ticker_upper = merged.get("ticker", "").upper()
    yf_company = yf_data.get("company_name", "")
    if fh_company == ticker_upper and yf_company and yf_company != "N/A" and yf_company != ticker_upper:
        merged["company_name"] = yf_company
        enriched_fields.append("company_name")
    
    # Field mapping: output_field -> yfinance_key
    field_mapping = {
        "forward_pe": "forward_pe",
        "fifty_two_week_high": "fifty_two_week_high",
        "fifty_two_week_low": "fifty_two_week_low",
        "open_price": "open_price",
        "day_low": "day_low",
        "day_high": "day_high",
        "volume": "volume",
        "shares_outstanding": "shares_outstanding",
        "float_shares": "float_shares",
        "insider_percent": "insider_percent",
        "institution_percent": "institution_percent",
        "short_percent_of_float": "short_percent_of_float",
        "shares_short": "shares_short",
        "target_mean_price": "target_mean_price",
        "target_median_price": "target_median_price",
        "target_high_price": "target_high_price",
        "target_low_price": "target_low_price",
        "recommendation_key": "recommendation_key",
        "number_of_analysts": "number_of_analysts",
        "average_analyst_rating": "average_analyst_rating",
        "long_business_summary": "long_business_summary",
        "ceo_name": "ceo_name",
        "full_time_employees": "full_time_employees",
        "market_cap": "market_cap",
        "beta": "beta",
        "security_type": "security_type",
    }
    
    for out_field, yf_key in field_mapping.items():
        fh_value = merged.get(out_field)
        yf_value = yf_data.get(yf_key)
        
        # Only enrich if Finnhub value is a gap AND yfinance has real data
        if _is_gap_value(fh_value, out_field) and not _is_gap_value(yf_value, out_field):
            merged[out_field] = yf_value
            enriched_fields.append(out_field)
    
    # Post-enrichment: if security_type is now ETF, also copy etf_data from yfinance
    yf_security_type = merged.get("security_type") or yf_data.get("security_type")
    if yf_security_type == "ETF":
        yf_etf_data = yf_data.get("etf_data")
        if yf_etf_data and not merged.get("etf_data"):
            merged["etf_data"] = yf_etf_data
            enriched_fields.append("etf_data")
    
    return merged, enriched_fields


async def get_hybrid_stock_price(ticker: str) -> Optional[Dict[str, Any]]:
    """Fetch stock data: Finnhub first, enrich with yfinance fundamentals for gaps."""
    ticker_upper = ticker.upper()

    # Check cache first
    cached = _cache_get(ticker_upper)
    if cached is not None:
        logger.debug("[Hybrid] Cache hit for %s.", ticker_upper)
        return cached.copy()

    # ETFs / indices → skip Finnhub, go straight to yfinance
    if ticker_upper in KNOWN_NON_STOCK_SYMBOLS:
        logger.debug("[Hybrid] %s is an ETF/index → routing to yfinance.", ticker_upper)
        data = await _yf_async(ticker_upper)
        return data

    # Try Finnhub
    try:
        data = await finnhub_get_stock_price(ticker_upper)
        if data and data.get("current_price", 0) > 0:
            logger.debug("[Hybrid] %s served by Finnhub.", ticker_upper)
            data["data_source"] = "fh"
            
            # Check if there are gap fields that need enrichment
            has_gaps = False
            for field in FUNDAMENTAL_GAP_FIELDS:
                val = data.get(field)
                if _is_gap_value(val, field):
                    has_gaps = True
                    break
            
            # Also check if company_name is just the ticker symbol (Finnhub had no profile name)
            bad_company_name = (
                data.get("company_name", "") == ticker_upper
            )
            
            if has_gaps or bad_company_name:
                # Fetch yfinance data in background to fill gaps
                logger.debug("[Hybrid] Enriching %s from yfinance (gaps=%s, bad_name=%s).", ticker_upper, has_gaps, bad_company_name)
                try:
                    yf_data = await _yf_async(ticker_upper)
                    if yf_data:
                        data, enriched_fields = _enrich_with_yf(data, yf_data)
                        data["yf_enriched_fields"] = enriched_fields
                        logger.debug(
                            "[Hybrid] %s enriched %d fields from yfinance.",
                            ticker_upper, len(enriched_fields)
                        )
                except Exception as e:
                    logger.warning("[Hybrid] Enrichment failed for %s: %s", ticker_upper, e)
            
            _cache_set(ticker_upper, data)
            return data
    except Exception as e:
        logger.warning("[Hybrid] Finnhub failed for %s: %s", ticker_upper, e)

    # Fallback to yfinance
    logger.debug("[Hybrid] Falling back to yfinance for %s.", ticker_upper)
    return await _yf_async(ticker_upper)


async def _fetch_one(ticker: str) -> Tuple[str, Optional[Dict[str, Any]]]:
    """Fetch a single ticker and return (ticker, data) tuple.
    
    If both Finnhub and yfinance fail, fall back to cached data rather than
    returning an empty error shell with null fundamentals.
    """
    try:
        data = await get_hybrid_stock_price(ticker)
        return (ticker, data)
    except Exception as e:
        logger.error("[Hybrid] Fetch failed for %s: %s", ticker, e)
    # Fallback: return cached data if available to avoid nulling out fundamentals
    cached = _cache_get(ticker.upper())
    if cached is not None:
        logger.info("[Hybrid] Using cached data for %s (fetch failed).", ticker.upper())
        return (ticker, cached)
    return (ticker, create_error_fallback(ticker, "yf"))


async def get_hybrid_batch_prices(tickers: List[str]) -> List[Dict[str, Any]]:
    """Fetch multiple tickers using hybrid logic.

    Performance optimization:
      - Finnhub candidates process in small batches (rate limit friendly)
      - yfinance calls run concurrently in thread pool executor
      - Both groups start together for parallel execution
    """
    # Deduplicate while preserving order
    seen = set()
    unique_tickers = []
    for t in tickers:
        key = t.upper()
        if key not in seen:
            seen.add(key)
            unique_tickers.append(t)

    # Split into two groups
    finnhub_candidates = [t for t in unique_tickers if t.upper() not in KNOWN_NON_STOCK_SYMBOLS]
    yf_only = [t for t in unique_tickers if t.upper() in KNOWN_NON_STOCK_SYMBOLS]

    results: Dict[str, Dict[str, Any]] = {}

    # Build coroutines list
    coros = []

    # Finnhub group: batched with stagger delays
    async def finnhub_batch_task():
        batch_size = 6
        for i in range(0, len(finnhub_candidates), batch_size):
            batch = finnhub_candidates[i:i + batch_size]
            batch_coros = [_fetch_one(t) for t in batch]
            batch_results = await asyncio.gather(*batch_coros, return_exceptions=True)
            for item in batch_results:
                if isinstance(item, tuple) and len(item) == 2:
                    tk, data = item
                    if data:
                        results[tk.upper()] = data
                elif isinstance(item, Exception):
                    logger.error("[Hybrid] Finnhub batch exception: %s", item)
            if i + batch_size < len(finnhub_candidates):
                await asyncio.sleep(0.3)

    # yfinance group: all concurrent via thread pool
    async def yf_batch_task():
        if not yf_only:
            return
        yf_coros = [_fetch_one(t) for t in yf_only]
        yf_results = await asyncio.gather(*yf_coros, return_exceptions=True)
        for item in yf_results:
            if isinstance(item, tuple) and len(item) == 2:
                tk, data = item
                if data:
                    results[tk.upper()] = data
            elif isinstance(item, Exception):
                logger.error("[Hybrid] YF batch exception: %s", item)

    # Run both groups concurrently
    await asyncio.gather(
        finnhub_batch_task(),
        yf_batch_task(),
    )

    # Return in original order
    return [results.get(t.upper(), create_error_fallback(t, "yf")) for t in tickers]


async def _fetch_hybrid_safe(ticker: str) -> Optional[Dict[str, Any]]:
    """Wrapper that catches per-ticker exceptions."""
    try:
        return await get_hybrid_stock_price(ticker)
    except Exception as e:
        logger.error("[Hybrid] Final fetch failed for %s: %s", ticker, e)
        return None
