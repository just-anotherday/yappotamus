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
from datetime import datetime, timezone
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
_BATCH_BUDGET_S = settings.MARKET_DATA_BATCH_BUDGET_S
_REFRESH_BACKOFF_S = settings.HYBRID_REFRESH_BACKOFF_S
_BACKGROUND_REFRESH_TIMEOUT_S = settings.HYBRID_BACKGROUND_REFRESH_TIMEOUT_S
_SHUTDOWN_TIMEOUT_S = settings.HYBRID_SHUTDOWN_TIMEOUT_S
_CACHE_MAX_SIZE = settings.HYBRID_CACHE_MAX_SIZE
_cache: Dict[str, Tuple[Dict[str, Any], float]] = {}
_refresh_retry_after: Dict[str, float] = {}

_coordination_loop: asyncio.AbstractEventLoop | None = None
_yfinance_gate: asyncio.Lock | None = None
_singleflight_lock: asyncio.Lock | None = None
_hybrid_singleflight_lock: asyncio.Lock | None = None
_yfinance_flights: Dict[str, asyncio.Task[Optional[Dict[str, Any]]]] = {}
_hybrid_flights: Dict[str, asyncio.Task[Optional[Dict[str, Any]]]] = {}
_hybrid_flight_waiters: Dict[str, int] = {}
_background_tasks: Set[asyncio.Task[Any]] = set()
_refresh_tasks_by_symbol: Dict[str, asyncio.Task[Any]] = {}

_FUNDAMENTALS_FIELDS = {
    "company_name", "sector", "industry", "long_business_summary", "website",
    "full_time_employees", "average_analyst_rating", "forward_pe", "ceo_name",
    "exchange", "security_type", "fund_assets", "fund_assets_source",
    "etf_market_cap", "etf_market_cap_source", "market_size_value",
    "market_size_type", "market_size_currency", "market_size_source",
    "market_size_fallback_used", "market_size_status", "shares_outstanding",
    "float_shares", "insider_percent", "institution_percent",
    "short_percent_of_float", "shares_short", "target_mean_price",
    "target_median_price", "target_high_price", "target_low_price",
    "recommendation_key", "number_of_analysts", "fifty_two_week_high",
    "fifty_two_week_low", "beta", "debt_to_equity", "overall_risk", "etf_data",
}


def _raise_programmer_error(exception: BaseException) -> None:
    if isinstance(exception, (AssertionError, NameError, UnboundLocalError)):
        raise exception


def _coordination_locks() -> tuple[asyncio.Lock, asyncio.Lock]:
    """Create loop-local coordination primitives (pytest uses multiple loops)."""
    global _coordination_loop, _yfinance_gate, _singleflight_lock
    global _hybrid_singleflight_lock
    loop = asyncio.get_running_loop()
    if _coordination_loop is not loop:
        _coordination_loop = loop
        _yfinance_gate = asyncio.Lock()
        _singleflight_lock = asyncio.Lock()
        _hybrid_singleflight_lock = asyncio.Lock()
        _yfinance_flights.clear()
        _hybrid_flights.clear()
        _hybrid_flight_waiters.clear()
    assert (
        _yfinance_gate is not None
        and _singleflight_lock is not None
        and _hybrid_singleflight_lock is not None
    )
    return _yfinance_gate, _singleflight_lock


def _hybrid_flight_lock() -> asyncio.Lock:
    """Return the loop-local lock protecting full hybrid refresh flights."""
    _coordination_locks()
    assert _hybrid_singleflight_lock is not None
    return _hybrid_singleflight_lock


def _track_background_task(task: asyncio.Task[Any]) -> None:
    """Retain background work and consume every terminal exception."""
    _background_tasks.add(task)

    def _finished(completed: asyncio.Task[Any]) -> None:
        _background_tasks.discard(completed)
        if completed.cancelled():
            return
        try:
            completed.exception()
        except Exception:
            logger.exception("[Hybrid] event=background_refresh_callback_failed")

    task.add_done_callback(_finished)


async def shutdown_hybrid_data_service() -> None:
    """Cancel tracked refresh tasks without allowing provider threads to hang shutdown."""
    current_loop = asyncio.get_running_loop()
    tasks = [task for task in _background_tasks if task.get_loop() is current_loop]
    foreign_tasks = [task for task in _background_tasks if task.get_loop() is not current_loop]
    for task in foreign_tasks:
        _background_tasks.discard(task)
    for task in tasks:
        task.cancel()
    if tasks:
        done, pending = await asyncio.wait(tasks, timeout=_SHUTDOWN_TIMEOUT_S)
        for task in done:
            if not task.cancelled():
                task.exception()
        if pending:
            logger.warning(
                "[Hybrid] event=background_shutdown_timeout pending_tasks=%d timeout_seconds=%s",
                len(pending),
                _SHUTDOWN_TIMEOUT_S,
            )

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


def _has_usable_etf_financial_data(data: Any) -> bool:
    """Reject identity-only Yahoo ETF shells as financial-provider successes."""
    if not isinstance(data, dict):
        return False
    for field in ("current_price", "previous_close", "fund_assets", "market_size_value"):
        value = data.get(field)
        if (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(float(value))
            and value > 0
        ):
            return True
    return False


def _is_cacheable_financial_data(data: Dict[str, Any]) -> bool:
    """Never admit identity-only or unavailable shells to the fresh cache."""
    if data.get("data_status") == "unavailable":
        return False
    if data.get("security_type") == "ETF":
        return _has_usable_etf_financial_data(data)
    return _has_usable_finnhub_quote(data) or isinstance(data.get("market_cap"), (int, float))


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
    """Merge recovered fundamentals without erasing still-valid cached fields."""
    stored = data.copy()
    existing_entry = _cache.get(ticker)
    preserved = False
    if existing_entry is not None:
        existing, _ = existing_entry
        merged = existing.copy()
        for field, value in stored.items():
            if field not in _FUNDAMENTALS_FIELDS or value is not None:
                merged[field] = value
        for field in _FUNDAMENTALS_FIELDS:
            if stored.get(field) is None and existing.get(field) is not None:
                preserved = True
        stored = merged

        # Valid absolute fund assets are stronger than an ETF market-value fallback.
        if _positive_cache_number(existing.get("fund_assets")) is not None and _positive_cache_number(data.get("fund_assets")) is None:
            stored["fund_assets"] = existing["fund_assets"]
            stored["market_size_value"] = existing["fund_assets"]
            stored["market_size_type"] = "fund_assets"
            stored["market_size_source"] = existing.get("fund_assets_source") or existing.get("market_size_source")
            stored["market_size_fallback_used"] = False

    now_iso = datetime.now(timezone.utc).isoformat()
    if preserved:
        stored["fundamentals_status"] = "stale"
        stored["fundamentals_is_stale"] = True
        stored["fundamentals_as_of"] = (
            existing_entry[0].get("fundamentals_as_of") if existing_entry else None
        ) or now_iso
    else:
        status = "complete" if stored.get("data_status") == "complete" else "partial"
        stored["fundamentals_status"] = status
        stored["fundamentals_is_stale"] = False
        stored["fundamentals_as_of"] = stored.get("fundamentals_as_of") or now_iso

    if stored.get("security_type") != "ETF":
        _recompute_final_risk(stored)

    if ticker not in _cache and len(_cache) >= _CACHE_MAX_SIZE:
        # Remove the oldest entry by timestamp
        oldest_key = min(_cache, key=lambda k: _cache[k][1])
        del _cache[oldest_key]
    cache_timestamp = existing_entry[1] if preserved and existing_entry is not None else time.time()
    _cache[ticker] = (stored, cache_timestamp)


def _positive_cache_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    normalized = float(value)
    return normalized if math.isfinite(normalized) and normalized > 0 else None


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
    merged["fundamentals_status"] = "stale"
    merged["fundamentals_is_stale"] = True
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
    if values[1] < 0 or values[3] <= 0 or values[4] <= 0 or values[5] <= 0 or values[4] > values[3]:
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
    cached_entry = _cache.get(ticker.upper())
    cached_fundamentals = cached_entry[0].copy() if cached_entry is not None else None
    data = get_stock_price_yf(ticker, cached_fundamentals=cached_fundamentals)
    if data:
        data["data_source"] = "yf"
    return data


async def _yf_async(ticker: str) -> Optional[Dict[str, Any]]:
    """Serialize Yahoo fundamentals and re-check cooldown after waiting."""
    gate, _ = _coordination_locks()
    async with gate:
        allowed, reason, probe = yfinance_fallback._begin_yfinance_fundamentals_attempt()
        if not allowed:
            logger.debug(
                "[Hybrid] event=yfinance_cooldown_skip failure_class=%s",
                reason,
            )
            return None
        loop = asyncio.get_running_loop()
        succeeded = False
        future = loop.run_in_executor(_executor, _yf_sync, ticker)
        try:
            try:
                data = await asyncio.shield(future)
            except asyncio.CancelledError:
                # A running thread cannot be cancelled. Keep the global gate
                # until it actually exits, then propagate caller cancellation.
                await future
                raise
            succeeded = data is not None
            return data
        finally:
            yfinance_fallback._complete_yfinance_fundamentals_attempt(
                probe=probe,
                succeeded=succeeded,
            )


async def _yf_singleflight(ticker: str) -> Optional[Dict[str, Any]]:
    """Share one cancellation-safe Yahoo fundamentals task per normalized symbol."""
    ticker_upper = ticker.strip().upper()
    cooldown_active, failure_class = yfinance_fallback._yfinance_cooldown_status()
    if cooldown_active:
        logger.debug(
            "[Hybrid] event=yfinance_cooldown_skip failure_class=%s",
            failure_class,
        )
        return None
    _, flight_lock = _coordination_locks()

    async with flight_lock:
        task = _yfinance_flights.get(ticker_upper)
        if task is None or task.done():
            async def _run() -> Optional[Dict[str, Any]]:
                try:
                    return await _yf_async(ticker_upper)
                finally:
                    current = asyncio.current_task()
                    _, cleanup_lock = _coordination_locks()
                    async with cleanup_lock:
                        if _yfinance_flights.get(ticker_upper) is current:
                            _yfinance_flights.pop(ticker_upper, None)

            task = asyncio.create_task(_run(), name=f"yf-fundamentals-{ticker_upper}")
            _yfinance_flights[ticker_upper] = task
            _track_background_task(task)

    return await asyncio.shield(task)


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
            operation=lambda: _yf_singleflight(ticker_upper),
            result_is_usable=_has_usable_etf_financial_data,
        )
        if failure is not None:
            logger.info("[Hybrid] %s returned no usable ETF financial fields (reason=%s).", ticker_upper, failure)
            return create_error_fallback(ticker_upper, "yf")
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
                            yf_data = await _yf_singleflight(ticker_upper)
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
                        _raise_programmer_error(exc)
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
        _raise_programmer_error(e)
        logger.warning("[Hybrid] Finnhub failed for %s: %s", ticker_upper, e)

    # Fallback to yfinance
    logger.debug("[Hybrid] Falling back to yfinance for %s.", ticker_upper)
    data, _ = await run_provider_attempt(
        ticker=ticker_upper,
        provider="yf",
        timeout_s=_PROVIDER_TIMEOUT_S,
        operation=lambda: _yf_singleflight(ticker_upper),
    )
    return data


async def _refresh_hybrid_stock_price(ticker: str) -> Optional[Dict[str, Any]]:
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
        _raise_programmer_error(exc)
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
        if normalized.get("data_status") != "unavailable" and not normalized.get("fundamentals_as_of"):
            normalized["fundamentals_as_of"] = datetime.now(timezone.utc).isoformat()
        normalized["fundamentals_status"] = normalized.get("fundamentals_status") or normalized.get("data_status")
        normalized["fundamentals_is_stale"] = bool(
            normalized.get("fundamentals_is_stale")
            or normalized.get("fundamentals_status") == "stale"
        )
        if normalized.get("data_status") in {"partial", "unavailable"}:
            stale = _cache_get_stale(ticker_upper)
            if stale is not None and _is_cacheable_financial_data(stale):
                if _is_cacheable_financial_data(normalized) or normalized.get("data_status") == "partial":
                    _cache_set(ticker_upper, normalized)
                    merged_entry = _cache.get(ticker_upper)
                    stale = merged_entry[0].copy() if merged_entry else stale
                normalized = _merge_stale_static_metadata(stale, normalized)
        if normalized.get("data_status") != "stale" and _is_cacheable_financial_data(normalized):
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
        stale["fundamentals_status"] = "stale"
        stale["fundamentals_is_stale"] = True
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


async def _run_hybrid_refresh_flight(ticker: str) -> Optional[Dict[str, Any]]:
    """Join or create the one process-wide provider refresh for a symbol."""
    ticker_upper = ticker.strip().upper()
    lock = _hybrid_flight_lock()

    async with lock:
        task = _hybrid_flights.get(ticker_upper)
        if task is None or task.done():
            async def _run_shared_refresh() -> Optional[Dict[str, Any]]:
                started = time.monotonic()
                try:
                    result = await _refresh_hybrid_stock_price(ticker_upper)
                    waiters = _hybrid_flight_waiters.get(ticker_upper, 0)
                    if result is None:
                        logger.warning(
                            "[Hybrid] event=singleflight_failed ticker=%s waiters=%d "
                            "correlation_id=%s failure_reason=providers_exhausted "
                            "duration_ms=%d",
                            ticker_upper,
                            waiters,
                            current_correlation_id(),
                            int((time.monotonic() - started) * 1000),
                        )
                    else:
                        logger.info(
                            "[Hybrid] event=singleflight_completed ticker=%s waiters=%d "
                            "correlation_id=%s duration_ms=%d",
                            ticker_upper,
                            waiters,
                            current_correlation_id(),
                            int((time.monotonic() - started) * 1000),
                        )
                    return result
                except asyncio.CancelledError:
                    logger.warning(
                        "[Hybrid] event=singleflight_failed ticker=%s waiters=%d "
                        "correlation_id=%s failure_reason=cancelled duration_ms=%d",
                        ticker_upper,
                        _hybrid_flight_waiters.get(ticker_upper, 0),
                        current_correlation_id(),
                        int((time.monotonic() - started) * 1000),
                    )
                    raise
                except Exception as exc:
                    logger.warning(
                        "[Hybrid] event=singleflight_failed ticker=%s waiters=%d "
                        "correlation_id=%s failure_reason=%s duration_ms=%d",
                        ticker_upper,
                        _hybrid_flight_waiters.get(ticker_upper, 0),
                        current_correlation_id(),
                        type(exc).__name__,
                        int((time.monotonic() - started) * 1000),
                    )
                    raise
                finally:
                    cleanup_lock = _hybrid_flight_lock()
                    async with cleanup_lock:
                        current = asyncio.current_task()
                        if _hybrid_flights.get(ticker_upper) is current:
                            _hybrid_flights.pop(ticker_upper, None)
                            _hybrid_flight_waiters.pop(ticker_upper, None)

            task = asyncio.create_task(
                _run_shared_refresh(), name=f"hybrid-provider-{ticker_upper}"
            )
            _hybrid_flights[ticker_upper] = task
            _hybrid_flight_waiters[ticker_upper] = 1
            _track_background_task(task)
            logger.info(
                "[Hybrid] event=singleflight_created ticker=%s waiters=1 correlation_id=%s",
                ticker_upper,
                current_correlation_id(),
            )
        else:
            waiters = _hybrid_flight_waiters.get(ticker_upper, 0) + 1
            _hybrid_flight_waiters[ticker_upper] = waiters
            logger.info(
                "[Hybrid] event=singleflight_joined ticker=%s waiters=%d correlation_id=%s",
                ticker_upper,
                waiters,
                current_correlation_id(),
            )

    try:
        return await asyncio.shield(task)
    finally:
        lock = _hybrid_flight_lock()
        async with lock:
            if _hybrid_flights.get(ticker_upper) is task:
                _hybrid_flight_waiters[ticker_upper] = max(
                    0, _hybrid_flight_waiters.get(ticker_upper, 1) - 1
                )


def _schedule_symbol_refresh(ticker: str) -> None:
    ticker_upper = ticker.strip().upper()
    existing = _refresh_tasks_by_symbol.get(ticker_upper)
    if existing is not None and not existing.done():
        return
    if time.monotonic() < _refresh_retry_after.get(ticker_upper, 0.0):
        return

    refresh_task = asyncio.create_task(
        _run_hybrid_refresh_flight(ticker_upper),
        name=f"fundamentals-provider-{ticker_upper}",
    )
    _refresh_tasks_by_symbol[ticker_upper] = refresh_task
    _track_background_task(refresh_task)

    def _clear_symbol(completed: asyncio.Task[Any]) -> None:
        if _refresh_tasks_by_symbol.get(ticker_upper) is completed:
            _refresh_tasks_by_symbol.pop(ticker_upper, None)

    refresh_task.add_done_callback(_clear_symbol)

    async def _monitor() -> None:
        try:
            done, _ = await asyncio.wait(
                {refresh_task}, timeout=_BACKGROUND_REFRESH_TIMEOUT_S,
            )
            if not done:
                _refresh_retry_after[ticker_upper] = time.monotonic() + _REFRESH_BACKOFF_S
                logger.warning(
                    "[Hybrid] event=background_refresh_timeout symbol=%s timeout_seconds=%s",
                    ticker_upper,
                    _BACKGROUND_REFRESH_TIMEOUT_S,
                )
                return
            result = refresh_task.result()
            if result is None or result.get("data_status") in {"stale", "unavailable"}:
                _refresh_retry_after[ticker_upper] = time.monotonic() + _REFRESH_BACKOFF_S
            else:
                _refresh_retry_after.pop(ticker_upper, None)
        except asyncio.CancelledError:
            raise
        except Exception:
            _refresh_retry_after[ticker_upper] = time.monotonic() + _REFRESH_BACKOFF_S
            logger.exception("[Hybrid] event=background_refresh_failed symbol=%s", ticker_upper)

    monitor_task = asyncio.create_task(
        _monitor(), name=f"fundamentals-monitor-{ticker_upper}"
    )
    _track_background_task(monitor_task)


async def get_hybrid_stock_price(ticker: str) -> Optional[Dict[str, Any]]:
    """Serve fresh/stale data immediately and refresh stale fundamentals off-path."""
    ticker_upper = ticker.strip().upper()
    cached = _cache_get(ticker_upper)
    if cached is not None:
        started = time.monotonic()
        default_source = "yf" if ticker_upper in KNOWN_NON_STOCK_SYMBOLS else "fh"
        normalized = normalize_market_data_payload(
            ticker_upper,
            cached,
            default_source=str(cached.get("data_source") or default_source),
        )
        log_collection_result(
            ticker=ticker_upper,
            selected_provider=str(normalized.get("data_source") or default_source),
            fallback_provider=None,
            started=started,
            payload=normalized,
            cache_state="fresh",
            failure_reason=None,
        )
        return normalized

    stale = _cache_get_stale(ticker_upper)
    if stale is not None and _is_cacheable_financial_data(stale):
        started = time.monotonic()
        stale["data_status"] = "stale"
        stale["fundamentals_status"] = "stale"
        stale["fundamentals_is_stale"] = True
        stale["market_size_status"] = "stale_cache"
        stale["provider_status"] = {"finnhub": "unavailable", "yfinance": "unavailable"}
        _schedule_symbol_refresh(ticker_upper)
        normalized = normalize_market_data_payload(
            ticker_upper,
            stale,
            default_source=str(stale.get("data_source") or "yf"),
        )
        log_collection_result(
            ticker=ticker_upper,
            selected_provider=str(normalized.get("data_source") or "yf"),
            fallback_provider=None,
            started=started,
            payload=normalized,
            cache_state="stale",
            failure_reason=None,
        )
        return normalized
    return await _run_hybrid_refresh_flight(ticker_upper)


async def _fetch_one(ticker: str) -> Tuple[str, Optional[Dict[str, Any]]]:
    """Fetch a single ticker and return (ticker, data) tuple.
    
    If both Finnhub and yfinance fail, fall back to cached data rather than
    returning an empty error shell with null fundamentals.
    """
    try:
        data = await get_hybrid_stock_price(ticker)
        return (ticker, data)
    except Exception as e:
        _raise_programmer_error(e)
        logger.error("[Hybrid] Fetch failed for %s: %s", ticker, e)
    # Fallback: return cached data if available to avoid nulling out fundamentals
    cached = _cache_get(ticker.upper())
    if cached is not None:
        logger.info("[Hybrid] Using cached data for %s (fetch failed).", ticker.upper())
        return (ticker, cached)
    return (ticker, create_error_fallback(ticker, "yf"))


async def get_hybrid_batch_prices(tickers: List[str]) -> List[Dict[str, Any]]:
    """Fetch a watchlist within one explicit budget, preserving max concurrency six."""
    # Deduplicate while preserving order
    seen = set()
    unique_tickers = []
    for t in tickers:
        key = t.upper()
        if key not in seen:
            seen.add(key)
            unique_tickers.append(t)

    results: Dict[str, Dict[str, Any]] = {}
    semaphore = asyncio.Semaphore(6)

    async def _bounded_fetch(ticker: str) -> Tuple[str, Optional[Dict[str, Any]]]:
        async with semaphore:
            return await _fetch_one(ticker)

    tasks = {
        asyncio.create_task(_bounded_fetch(ticker), name=f"watchlist-fetch-{ticker.upper()}"): ticker
        for ticker in unique_tickers
    }
    if not tasks:
        return []
    for task in tasks:
        _track_background_task(task)
    done, pending = await asyncio.wait(tasks, timeout=_BATCH_BUDGET_S)
    for task in done:
        try:
            ticker, data = task.result()
        except Exception as exc:
            _raise_programmer_error(exc)
            logger.exception("[Hybrid] event=batch_symbol_failed symbol=%s", tasks[task].upper())
            continue
        if data:
            results[ticker.upper()] = data

    # Do not cancel shared provider work at the response boundary. It will warm
    # the bounded cache and every terminal exception is consumed by the tracker.
    # Return in original order
    output: List[Dict[str, Any]] = []
    for ticker in tickers:
        ticker_upper = ticker.upper()
        data = results.get(ticker_upper)
        if data is None:
            stale = _cache_get_stale(ticker_upper) or _cache_get(ticker_upper)
            if stale is not None:
                stale["data_status"] = "stale"
                stale["fundamentals_status"] = "stale"
                stale["fundamentals_is_stale"] = True
                data = stale
            else:
                data = create_error_fallback(ticker, "yf")
                data["fundamentals_status"] = "unavailable"
                data["fundamentals_as_of"] = None
                data["fundamentals_is_stale"] = False
        output.append(data)
    return output


async def _fetch_hybrid_safe(ticker: str) -> Optional[Dict[str, Any]]:
    """Wrapper that catches per-ticker exceptions."""
    try:
        return await get_hybrid_stock_price(ticker)
    except Exception as e:
        _raise_programmer_error(e)
        logger.error("[Hybrid] Final fetch failed for %s: %s", ticker, e)
        return None
