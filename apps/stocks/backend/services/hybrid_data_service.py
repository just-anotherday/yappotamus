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
import math
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Set, Tuple

from backend.config.settings import settings
from backend.services.finnhub_service import get_stock_price as finnhub_get_stock_price
from backend.services import yfinance_fallback
from backend.services.yfinance_fallback import get_stock_price_yf
from backend.lib.constants import KNOWN_NON_STOCK_SYMBOLS
from backend.lib.error_fallback import create_error_fallback
from backend.lib.market_data_normalization import normalize_market_data_payload
from backend.lib.risk_metrics import _compute_composite_risk
from backend.services.market_data_observability import (
    current_correlation_id,
    log_collection_result,
    run_provider_attempt,
)

logger = logging.getLogger(__name__)

# Thread pool for running blocking yfinance calls without freezing the event loop.
_executor = ThreadPoolExecutor(max_workers=6, thread_name_prefix="yf-fallback")

# Bounded TTL cache: stores (data, timestamp) tuples. Entries can be served as
# stale only until _STALE_CACHE_TTL; max size limits memory growth.
_CACHE_TTL = settings.HYBRID_CACHE_TTL_S  # default 5 minutes
_STALE_CACHE_TTL = settings.HYBRID_STALE_CACHE_TTL_S
_PROVIDER_TIMEOUT_S = settings.MARKET_DATA_PROVIDER_TIMEOUT_S
_CACHE_MAX_SIZE = settings.HYBRID_CACHE_MAX_SIZE
_cache: Dict[str, Tuple[Dict[str, Any], float]] = {}

def _has_usable_finnhub_quote(data: Any) -> bool:
    """Accept only Finnhub payloads with a finite positive current price."""
    if not isinstance(data, dict):
        return False
    price = data.get("current_price")
    return (
        not isinstance(price, bool)
        and isinstance(price, (int, float))
        and math.isfinite(float(price))
        and price > 0
    )


def _cache_get(ticker: str) -> Optional[Dict[str, Any]]:
    """Retrieve a cached entry if within TTL."""
    entry = _cache.get(ticker)
    if entry is None:
        return None
    data, ts = entry
    age = time.time() - ts
    if age > _STALE_CACHE_TTL:
        _cache.pop(ticker, None)
        return None
    if age > _CACHE_TTL:
        return None
    return data.copy()


def _cache_get_stale(ticker: str) -> Optional[Dict[str, Any]]:
    """Return expired-but-bounded data only after provider failure."""
    entry = _cache.get(ticker)
    if entry is None:
        return None
    data, ts = entry
    age = time.time() - ts
    if age <= _CACHE_TTL or age > _STALE_CACHE_TTL:
        if age > _STALE_CACHE_TTL:
            _cache.pop(ticker, None)
        return None
    return data.copy()


def _cache_set(ticker: str, data: Dict[str, Any]) -> None:
    """Store a cached entry, evicting oldest entries if at capacity."""
    if len(_cache) >= _CACHE_MAX_SIZE:
        # Remove the oldest entry by timestamp
        oldest_key = min(_cache, key=lambda k: _cache[k][1])
        del _cache[oldest_key]
    _cache[ticker] = (data.copy(), time.time())


_FRESH_QUOTE_FIELDS = {
    "current_price", "open_price", "previous_close", "day_low", "day_high",
    "change", "change_percent", "volume", "post_market_price",
    "post_market_change", "post_market_change_percent",
}


def _merge_stale_static_metadata(stale: Dict[str, Any], partial: Dict[str, Any]) -> Dict[str, Any]:
    """Keep bounded last-known static data while accepting fresh quote fields."""
    merged = stale.copy()
    for field in _FRESH_QUOTE_FIELDS:
        if partial.get(field) is not None:
            merged[field] = partial[field]
    merged["provider_status"] = partial.get("provider_status", {})
    merged["missing_fields"] = partial.get("missing_fields", [])
    merged["data_status"] = "stale"
    if merged.get("market_size_value") is not None:
        merged["market_size_status"] = "stale_cache"
    if merged.get("security_type") != "ETF":
        _recompute_final_risk(merged)
    return merged


def _recompute_final_risk(payload: Dict[str, Any]) -> None:
    """Calculate risk only after final provider selection and only with complete inputs."""
    fields = ("beta", "short_percent_of_float", "debt_to_equity", "fifty_two_week_high", "fifty_two_week_low", "current_price")
    values = [payload.get(field) for field in fields]
    if not all(isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value)) for value in values):
        payload["overall_risk"] = None
        return
    payload["overall_risk"] = _compute_composite_risk(
        beta=float(values[0]), short_pct_of_float=float(values[1]), debt_eq=float(values[2]),
        high52=float(values[3]), low52=float(values[4]), current_price=float(values[5]),
    )


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
    "sector",                 # Sector classification
    "long_business_summary",  # Business description
    "ceo_name",              # CEO name
    "full_time_employees",    # Employee count
    "volume",                # Normalized volume data
    "market_cap",            # Market capitalization
    "beta",                  # Beta coefficient
    "security_type",         # Security classification (STOCK/ETF/INDEX/etc.)
}


_PLACEHOLDER_ENRICHMENT_VALUES = {"n/a", "none", "null", "unknown", "error"}

_ZERO_MEANINGFUL_ENRICHMENT_FIELDS = {
    "beta",
    "number_of_analysts",
    "insider_percent",
    "institution_percent",
    "short_percent_of_float",
    "shares_short",
    "debt_to_equity",
}


def _is_gap_value(value: Any, field: str) -> bool:
    """Check if a value represents a Finnhub gap (missing/zero/default data)."""
    if value is None or isinstance(value, bool):
        return True
    if isinstance(value, str):
        return value.strip().casefold() in _PLACEHOLDER_ENRICHMENT_VALUES
    if isinstance(value, (int, float)) and not math.isfinite(value):
        return True
    # Numeric fields that are 0 when not available from Finnhub
    numeric_zero_fields = {
        "forward_pe", "fifty_two_week_high", "fifty_two_week_low",
        "open_price", "day_low", "day_high",
        "shares_outstanding", "float_shares",
        "target_mean_price", "target_median_price",
        "target_high_price", "target_low_price",
        "average_analyst_rating", "full_time_employees", "market_cap",
    }
    if field in numeric_zero_fields and value == 0:
        return True
    # recommendation_key is "N/A" or "error" when not available
    if field == "recommendation_key" and value in ("N/A", "error"):
        return True
    return False


def _normalize_meaningful_enrichment_value(value: Any, field: str) -> Any:
    """Return a normalized yfinance value only when it can improve Finnhub data."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str):
        normalized = value.strip()
        return (
            normalized
            if normalized and normalized.casefold() not in _PLACEHOLDER_ENRICHMENT_VALUES
            else None
        )
    if isinstance(value, (int, float)):
        if not math.isfinite(value):
            return None
        if value == 0 and field not in _ZERO_MEANINGFUL_ENRICHMENT_FIELDS:
            return None
        return value
    return None


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
    yf_company = _normalize_meaningful_enrichment_value(
        yf_data.get("company_name"), "company_name"
    )
    if (
        fh_company == ticker_upper
        and isinstance(yf_company, str)
        and yf_company.upper() != ticker_upper
    ):
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
        "sector": "sector",
        "long_business_summary": "long_business_summary",
        "ceo_name": "ceo_name",
        "full_time_employees": "full_time_employees",
        "market_cap": "market_cap",
        "debt_to_equity": "debt_to_equity",
        "beta": "beta",
        "security_type": "security_type",
    }
    
    for out_field, yf_key in field_mapping.items():
        fh_value = merged.get(out_field)
        yf_value = _normalize_meaningful_enrichment_value(
            yf_data.get(yf_key), out_field
        )
        
        # Only enrich a real Finnhub gap with a distinct, meaningful candidate.
        if (
            _is_gap_value(fh_value, out_field)
            and yf_value is not None
            and yf_value != fh_value
        ):
            merged[out_field] = yf_value
            enriched_fields.append(out_field)
    
    # Post-enrichment: if security_type is now ETF, also copy etf_data from yfinance
    yf_security_type = merged.get("security_type") or yf_data.get("security_type")
    if yf_security_type == "ETF":
        yf_etf_data = yf_data.get("etf_data")
        if yf_etf_data and not merged.get("etf_data"):
            merged["etf_data"] = yf_etf_data
            enriched_fields.append("etf_data")
    if merged.get("security_type") != "ETF":
        _recompute_final_risk(merged)
    
    return merged, enriched_fields


async def _collect_hybrid_stock_price(ticker: str) -> Optional[Dict[str, Any]]:
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
        data, failure = await run_provider_attempt(
            ticker=ticker_upper,
            provider="yf",
            timeout_s=_PROVIDER_TIMEOUT_S,
            operation=lambda: _yf_async(ticker_upper),
        )
        if data:
            data["provider_status"] = {"finnhub": "degraded", "yfinance": "healthy"}
        return data

    # Try Finnhub
    try:
        data, _ = await run_provider_attempt(
            ticker=ticker_upper,
            provider="fh",
            timeout_s=_PROVIDER_TIMEOUT_S,
            operation=lambda: finnhub_get_stock_price(ticker_upper),
            result_is_usable=_has_usable_finnhub_quote,
        )
        if data and data.get("current_price", 0) > 0:
            logger.debug("[Hybrid] %s served by Finnhub.", ticker_upper)
            data["data_source"] = "fh"
            data["provider_status"] = {"finnhub": "healthy", "yfinance": "degraded"}
            
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
                cooldown_active, failure_class = yfinance_fallback._yfinance_cooldown_status()
                if cooldown_active:
                    data["data_status"] = "partial"
                    data["provider_status"]["yfinance"] = "cooldown"
                    logger.debug(
                        "[Hybrid] event=yfinance_cooldown_skip failure_class=%s",
                        failure_class,
                    )
                else:
                    # Fetch yfinance data in background to fill gaps
                    logger.debug("[Hybrid] Enriching %s from yfinance (gaps=%s, bad_name=%s).", ticker_upper, has_gaps, bad_company_name)
                    try:
                        async def validated_yf_enrichment():
                            yf_data = await _yf_async(ticker_upper)
                            if not yf_data:
                                return None
                            merged_data, enriched_fields = _enrich_with_yf(data, yf_data)
                            return (merged_data, enriched_fields) if enriched_fields else None

                        enrichment, enrichment_failure = await run_provider_attempt(
                            ticker=ticker_upper,
                            provider="yf_enrichment",
                            timeout_s=_PROVIDER_TIMEOUT_S,
                            operation=validated_yf_enrichment,
                        )
                        if enrichment:
                            data, enriched_fields = enrichment
                            data["yf_enriched_fields"] = enriched_fields
                            data["provider_status"]["yfinance"] = "healthy"
                            logger.debug(
                                "[Hybrid] %s enriched %d fields from yfinance.",
                                ticker_upper, len(enriched_fields)
                            )
                        else:
                            data["data_status"] = "partial"
                            data["provider_status"]["yfinance"] = "unavailable" if enrichment_failure else "degraded"
                    except Exception as exc:
                        failure_class = yfinance_fallback._record_yfinance_outage_failure(exc)
                        data["data_status"] = "partial"
                        data["provider_status"]["yfinance"] = "degraded"
                        logger.warning(
                            "[Hybrid] Enrichment failed for %s: failure_class=%s exception_type=%s",
                            ticker_upper,
                            failure_class or "unclassified",
                            type(exc).__name__,
                        )
            
            return data
    except Exception as e:
        logger.warning("[Hybrid] Finnhub failed for %s: %s", ticker_upper, e)

    # Fallback to yfinance
    logger.debug("[Hybrid] Falling back to yfinance for %s.", ticker_upper)
    data, _ = await run_provider_attempt(
        ticker=ticker_upper,
        provider="yf",
        timeout_s=_PROVIDER_TIMEOUT_S,
        operation=lambda: _yf_async(ticker_upper),
    )
    return data


async def get_hybrid_stock_price(ticker: str) -> Optional[Dict[str, Any]]:
    """Collect, normalize, cache, and diagnose one watchlist symbol."""
    ticker_upper = ticker.strip().upper()
    started = time.monotonic()
    selected_provider = "yf" if ticker_upper in KNOWN_NON_STOCK_SYMBOLS else "fh"

    cached = _cache_get(ticker_upper)
    if cached is not None:
        normalized = normalize_market_data_payload(
            ticker_upper,
            cached,
            default_source=str(cached.get("data_source") or selected_provider),
        )
        log_collection_result(
            ticker=ticker_upper,
            selected_provider=str(normalized.get("data_source") or selected_provider),
            fallback_provider=None,
            started=started,
            payload=normalized,
            cache_state="fresh",
            failure_reason=None,
        )
        return normalized

    try:
        data = await _collect_hybrid_stock_price(ticker_upper)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.warning(
            "[MarketData] event=collection_exception correlation_id=%s "
            "symbol=%s exception_type=%s",
            current_correlation_id(),
            ticker_upper,
            type(exc).__name__,
        )
        data = None
        failure_reason = type(exc).__name__
    else:
        failure_reason = None if data is not None else "providers_exhausted"

    if data is not None:
        normalized = normalize_market_data_payload(
            ticker_upper,
            data,
            default_source=selected_provider,
        )
        if normalized.get("data_status") == "partial":
            stale = _cache_get_stale(ticker_upper)
            if stale is not None and stale.get("data_status") == "complete":
                normalized = _merge_stale_static_metadata(stale, normalized)
        if normalized.get("data_status") != "stale":
            _cache_set(ticker_upper, normalized)
        fallback_provider = None
        if selected_provider == "fh":
            if normalized.get("data_source") == "yf":
                fallback_provider = "yf"
            elif normalized.get("yf_enriched_fields"):
                fallback_provider = "yf_enrichment"
        log_collection_result(
            ticker=ticker_upper,
            selected_provider=selected_provider,
            fallback_provider=fallback_provider,
            started=started,
            payload=normalized,
            cache_state="none",
            failure_reason=failure_reason,
        )
        return normalized

    stale = _cache_get_stale(ticker_upper)
    if stale is not None:
        stale = stale.copy()
        stale["market_size_status"] = "stale_cache"
        stale["data_status"] = "stale"
        stale["provider_status"] = {
            "finnhub": "unavailable",
            "yfinance": "unavailable",
        }
        normalized = normalize_market_data_payload(
            ticker_upper,
            stale,
            default_source=str(stale.get("data_source") or selected_provider),
        )
        log_collection_result(
            ticker=ticker_upper,
            selected_provider=selected_provider,
            fallback_provider=None,
            started=started,
            payload=normalized,
            cache_state="stale",
            failure_reason=failure_reason,
        )
        return normalized

    log_collection_result(
        ticker=ticker_upper,
        selected_provider=selected_provider,
        fallback_provider="yf" if selected_provider == "fh" else None,
        started=started,
        payload=None,
        cache_state="miss",
        failure_reason=failure_reason,
    )
    return None


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
