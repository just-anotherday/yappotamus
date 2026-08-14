# services/finnhub_service.py
"""
Finnhub API Service — replaces yfinance for all market data operations.

Free tier limits (https://finnhub.io/pricing):
 - 60 REST API calls per minute
 - 30 API calls per second across all plans

Endpoints used:
 - /quote              → real-time quote data
 - /stock/profile2     → company profile + fundamentals
 - /search             → search valid ticker symbols
 - /company-news       → market news for a ticker
 - WebSocket           → real-time trade/quote streaming
"""

import asyncio
from email.utils import parsedate_to_datetime
import logging
import random
import time
from typing import Any, Dict, List, Optional

import finnhub
from requests.exceptions import ConnectionError as RequestsConnectionError
from requests.exceptions import Timeout as RequestsTimeout

from backend.config.settings import settings
from backend.config.polling_settings import polling_settings
from backend.lib.constants import KNOWN_NON_STOCK_SYMBOLS
from backend.lib.error_fallback import create_error_fallback
from backend.lib.risk_metrics import _safe_pct

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Client initialization
# ------------------------------------------------------------------

if not settings.FINNHUB_API_KEY:
    logger.warning("[Finnhub] FINNHUB_API_KEY not set in environment. API calls will fail.")

_client: Optional[finnhub.Client] = None


def get_finnhub_client() -> finnhub.Client:
    """Return a singleton Finnhub client instance.
    
    Raises RuntimeError if FINNHUB_API_KEY is not configured.
    """
    global _client
    if _client is None:
        if not settings.FINNHUB_API_KEY:
            raise RuntimeError(
                "Finnhub API key not set. Set FINNHUB_API_KEY in your .env file."
            )
        _client = finnhub.Client(api_key=settings.FINNHUB_API_KEY)
    return _client


# ------------------------------------------------------------------
# Rate limiter (Free tier: 60 calls/min ≈ 1 call/sec safe average)
# ------------------------------------------------------------------

_rate_lock: Optional[asyncio.Lock] = None
_last_call_time: float = 0.0
_min_interval: float = 60.0 / polling_settings.FINNHUB_REQUESTS_PER_MINUTE


def _get_rate_lock() -> asyncio.Lock:
    """Return the process-shared limiter lock, bound lazily to the active loop."""
    global _rate_lock
    if _rate_lock is None:
        _rate_lock = asyncio.Lock()
    return _rate_lock


async def _rate_limiter():
    """Pace every physical REST attempt below the configured shared ceiling."""
    global _last_call_time
    async with _get_rate_lock():
        now = time.monotonic()
        elapsed = now - _last_call_time
        if elapsed < _min_interval:
            wait_time = _min_interval - elapsed
            await asyncio.sleep(wait_time)
        _last_call_time = time.monotonic()


# ------------------------------------------------------------------
# Async retry helper for transient failures
# ------------------------------------------------------------------

def _exception_chain(exc: BaseException):
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        yield current
        current = current.__cause__ or current.__context__


def _exception_status_code(exc: BaseException) -> Optional[int]:
    """Return an HTTP status from an SDK/requests exception chain, if present."""
    for current in _exception_chain(exc):
        status = getattr(current, "status_code", None)
        if isinstance(status, int):
            return status
        response = getattr(current, "response", None)
        response_status = getattr(response, "status_code", None)
        if isinstance(response_status, int):
            return response_status
    return None


def _is_rate_limit_error(exc: BaseException) -> bool:
    return _exception_status_code(exc) == 429


def _is_retryable_error(exc: BaseException) -> bool:
    status = _exception_status_code(exc)
    transport_error = any(
        isinstance(item, (TimeoutError, ConnectionError, RequestsTimeout, RequestsConnectionError))
        for item in _exception_chain(exc)
    )
    return transport_error or (
        status is not None and (status == 429 or status >= 500)
    )


def _is_timeout_error(exc: BaseException) -> bool:
    return any(isinstance(item, (TimeoutError, RequestsTimeout)) for item in _exception_chain(exc))


def _retry_after_seconds(exc: BaseException) -> Optional[float]:
    """Parse Retry-After seconds or an HTTP date from a provider response."""
    raw = None
    for item in _exception_chain(exc):
        response = getattr(item, "response", None)
        headers = getattr(response, "headers", None)
        raw = headers.get("Retry-After") if headers is not None else None
        if raw:
            break
    if not raw:
        return None
    try:
        return max(0.0, float(raw))
    except (TypeError, ValueError):
        try:
            retry_at = parsedate_to_datetime(str(raw))
            return max(0.0, retry_at.timestamp() - time.time())
        except (TypeError, ValueError, OverflowError):
            return None


def _increment_metric(metrics: Optional[dict[str, Any]], key: str) -> None:
    if metrics is not None:
        metrics[key] = int(metrics.get(key, 0)) + 1


async def _retry_api(func, *args, **kwargs):
    """Run an async Finnhub operation with paced, bounded transient retries.

    Private ``_request_*`` keywords configure safe logging and optional cycle
    metrics. Every physical attempt re-enters the shared rate limiter.
    """
    operation = kwargs.pop("_request_operation", getattr(func, "__name__", "unknown"))
    ticker = kwargs.pop("_request_ticker", None)
    metrics = kwargs.pop("_request_metrics", None)
    attempts = polling_settings.FINNHUB_MAX_RETRY_ATTEMPTS

    for attempt_number in range(1, attempts + 1):
        await _rate_limiter()
        _increment_metric(metrics, "provider_requests")
        try:
            result = await func(*args, **kwargs)
            _increment_metric(metrics, "provider_successes")
            return result
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            rate_limited = _is_rate_limit_error(exc)
            if rate_limited:
                _increment_metric(metrics, "provider_rate_limits")
            elif _is_timeout_error(exc):
                _increment_metric(metrics, "provider_timeouts")
            else:
                _increment_metric(metrics, "provider_failures")

            if not _is_retryable_error(exc) or attempt_number >= attempts:
                raise

            retry_after = _retry_after_seconds(exc) if rate_limited else None
            if retry_after is not None and retry_after > polling_settings.FINNHUB_MAX_RETRY_AFTER_S:
                logger.warning(
                    "[Finnhub] event=retry_deferred operation=%s ticker=%s attempt=%d "
                    "reason=retry_after_exceeds_bound retry_after_seconds=%.3f",
                    operation, ticker or "-", attempt_number, retry_after,
                )
                raise

            if retry_after is not None:
                delay = retry_after
            else:
                exponential = min(
                    polling_settings.FINNHUB_BACKOFF_INITIAL_S * (2 ** (attempt_number - 1)),
                    polling_settings.FINNHUB_BACKOFF_MAX_S,
                )
                delay = exponential + random.uniform(0, polling_settings.FINNHUB_RETRY_JITTER_S)

            _increment_metric(metrics, "provider_retries")
            logger.warning(
                "[Finnhub] event=retry_scheduled operation=%s ticker=%s attempt=%d "
                "status_code=%s rate_limited=%s delay_seconds=%.3f",
                operation, ticker or "-", attempt_number, _exception_status_code(exc),
                str(rate_limited).lower(), delay,
            )
            await asyncio.sleep(delay)

    raise RuntimeError("unreachable Finnhub retry state")


# ------------------------------------------------------------------
# Core: Fetch quote data (replaces yfinance current price info)
# ------------------------------------------------------------------

async def _do_quote(client: finnhub.Client, ticker: str):
    """Inner API call — may raise on transient failures (retryable)."""
    return await asyncio.to_thread(client.quote, ticker.upper())


async def fetch_quote(ticker: str) -> Dict[str, Any]:
    """Fetch real-time quote for a ticker via Finnhub /quote endpoint."""
    client = get_finnhub_client()
    try:
        quote = await _retry_api(
            _do_quote, client, ticker,
            _request_operation="quote", _request_ticker=ticker.upper(),
        )
        if not quote or quote.get("c") == 0:
            logger.warning("[Finnhub] No quote data for %s", ticker)
            return {}
        return quote
    except Exception as e:
        logger.error(
            "[Finnhub] operation=quote ticker=%s outcome=failed exception_type=%s status_code=%s",
            ticker.upper(), type(e).__name__, _exception_status_code(e),
        )
        return {}


# ------------------------------------------------------------------
# Core: Fetch company profile (replaces yfinance .info fundamentals)
# ------------------------------------------------------------------

async def _do_profile(client: finnhub.Client, ticker: str):
    """Inner API call — may raise on transient failures (retryable)."""
    return await asyncio.to_thread(client.company_profile2, symbol=ticker.upper())


async def fetch_company_profile(ticker: str) -> Dict[str, Any]:
    """Fetch company profile via Finnhub /stock-profile2 endpoint."""
    client = get_finnhub_client()
    try:
        profile = await _retry_api(
            _do_profile, client, ticker,
            _request_operation="company_profile", _request_ticker=ticker.upper(),
        )
        # finnhub-python 2.x returns profile2 as a dict. Accept the legacy list
        # shape as well so an SDK change cannot silently erase fundamentals.
        if isinstance(profile, dict):
            return profile
        if isinstance(profile, list):
            return next((item for item in profile if isinstance(item, dict)), {})
        # Empty result is expected for ETFs, indices, etc. — don't spam logs
        if ticker.upper() in KNOWN_NON_STOCK_SYMBOLS:
            logger.debug("[Finnhub] %s is a non-stock symbol (ETF/index), no profile available.", ticker)
        else:
            logger.info("[Finnhub] No profile data for %s", ticker)
        return {}
    except Exception as e:
        # Finnhub returns error code 0 for symbols it doesn't recognize as US equities
        err_str = str(e)
        if "0" in err_str or "not found" in err_str.lower():
            logger.debug(
                "[Finnhub] operation=company_profile ticker=%s outcome=unavailable "
                "exception_type=%s status_code=%s",
                ticker.upper(), type(e).__name__, _exception_status_code(e),
            )
        else:
            logger.warning(
                "[Finnhub] operation=company_profile ticker=%s outcome=failed "
                "exception_type=%s status_code=%s",
                ticker.upper(), type(e).__name__, _exception_status_code(e),
            )
        return {}


# ------------------------------------------------------------------
# Core: Search symbol (replaces yfinance ticker validation)
# ------------------------------------------------------------------

async def _do_symbol_lookup(client: finnhub.Client, query: str):
    return await asyncio.to_thread(client.symbol_lookup, query.upper())


async def search_symbol(query: str) -> List[Dict[str, Any]]:
    """Search for valid ticker symbols via Finnhub /symbol-search endpoint."""
    client = get_finnhub_client()
    try:
        results = await _retry_api(
            _do_symbol_lookup, client, query,
            _request_operation="symbol_search", _request_ticker=query.upper(),
        )
        return results if results else []
    except Exception as e:
        logger.error(
            "[Finnhub] operation=symbol_search query=%s outcome=failed "
            "exception_type=%s status_code=%s",
            query.upper(), type(e).__name__, _exception_status_code(e),
        )
        return []


# ------------------------------------------------------------------
# Public API: get_ticker_info (same contract as old yfinance service)
# ------------------------------------------------------------------

async def get_ticker_info(ticker: str) -> Dict[str, Any]:
    """Return combined quote + profile data for a ticker.

    This replaces the old blocking `yfinance Ticker.info` call.
    """
    quote = await fetch_quote(ticker)
    profile = await fetch_company_profile(ticker)

    if not quote and not profile:
        logger.error("[Finnhub] No data available for %s", ticker)
        return {}

    market_cap = (profile.get("marketCapitalization") or 0) * 1_000_000
    if profile.get("shareOutstanding") is not None:
        shares_outstanding = (profile.get("shareOutstanding") or 0) * 1_000_000
    else:
        # Preserve the former plural-key contract as an absolute-unit fallback.
        shares_outstanding = profile.get("sharesOutstanding") or 0

    # Merge into the same structure expected by downstream consumers
    info: Dict[str, Any] = {
        # Identity (from profile or quote)
        "symbol": ticker.upper(),
        "ticker": ticker.upper(),
        "shortName": profile.get("shareClassFullName") or profile.get("name") or ticker.upper(),
        "longName": profile.get("name") or profile.get("shareClassFullName") or "",
        "sector": profile.get("industry"),
        "industry": profile.get("finnhubIndustry"),
        "longBusinessSummary": None,  # Finnhub free tier doesn't provide summary text - yfinance enrichment will fill this
        "website": profile.get("weburl"),
        "exchange": profile.get("exchange"),

        # Price data (from quote)
        "currentPrice": quote.get("c", 0),
        "previousClose": quote.get("pc", 0),
        "regularMarketOpen": quote.get("o", 0) or quote.get("c", 0),
        "regularMarketDayLow": quote.get("l", 0),
        "regularMarketDayHigh": quote.get("h", 0),
        "regularMarketChangePercent": _safe_pct(quote.get("d", 0), quote.get("pc", 1)),

        # Market cap + fundamentals (from profile)
        # Finnhub reports marketCapitalization in millions; the public API and
        # frontend use absolute currency units.
        "marketCap": market_cap,
        "sharesOutstanding": shares_outstanding,
        "floatShares": profile.get("dilutedSharesOutstanding") or 0,

        # Risk indicators (best-effort from profile)
        "beta": profile.get("beta"),

	# 52-week range not available on Finnhub free tier — set to 0 so hybrid_data_service
	# enrichment via yfinance can fill these gap fields correctly.
	"fiftyTwoWeekHigh": 0,
	"fiftyTwoWeekLow": 0,

        # Analyst data (not available on free Finnhub tier — set defaults)
        "forwardPE": None,
        "averageAnalystRating": None,
        "heldPercentInsiders": None,
        "heldPercentInstitutions": None,
        "shortPercentOfFloat": None,
        "sharesShort": None,
        "debtToEquity": None,
        "targetMeanPrice": None,
        "targetMedianPrice": None,
        "targetHighPrice": None,
        "targetLowPrice": None,
        "recommendationKey": "N/A",
        "numberOfAnalystOpinions": None,
        "regularMarketVolume": 0,
        "currency": profile.get("currency") or "USD",
    }

    return info


# ------------------------------------------------------------------
# Public API: get_stock_price (same contract as old yfinance service)
# ------------------------------------------------------------------

async def get_stock_price(ticker: str) -> Optional[Dict[str, Any]]:
    """Return analyst-grade data for a single ticker.

    Same output shape as the old `get_stock_price` from yfinance_service.py.
    """
    info = await get_ticker_info(ticker.upper())
    if not info:
        return None

    def positive_or_none(value: Any) -> float | None:
        return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0 else None

    current_price = positive_or_none(info.get("currentPrice"))
    previous_close = positive_or_none(info.get("previousClose"))

    return {
        # Identity
        "ticker": ticker.upper(),
        "symbol": info.get("symbol", ticker.upper()),
        "company_name": info.get("shortName") or info.get("longName") or ticker.upper(),
        "sector": info.get("sector"),
        "industry": info.get("industry"),
        "long_business_summary": info.get("longBusinessSummary"),
        "website": info.get("website"),
        "full_time_employees": None,  # Not available on free Finnhub tier
        "average_analyst_rating": info.get("averageAnalystRating"),
        "forward_pe": info.get("forwardPE"),
        "ceo_name": None,  # Not available on free Finnhub tier
        "exchange": info.get("exchange"),

        # Price Data
        "current_price": current_price,
        "open_price": positive_or_none(info.get("regularMarketOpen")),
        "previous_close": previous_close,
        "day_low": positive_or_none(info.get("regularMarketDayLow")),
        "day_high": positive_or_none(info.get("regularMarketDayHigh")),
        "fifty_two_week_high": None,
        "fifty_two_week_low": None,
        "change": round(current_price - previous_close, 2) if current_price is not None and previous_close is not None else None,
        "change_percent": round(info["regularMarketChangePercent"], 2) if previous_close and info.get("regularMarketChangePercent") is not None else None,
        "market_cap": positive_or_none(info.get("marketCap")),
        "market_size_currency": info.get("currency"),

        # Share Structure
        "shares_outstanding": int(info["sharesOutstanding"]) if positive_or_none(info.get("sharesOutstanding")) else None,
        "float_shares": int(info["floatShares"]) if positive_or_none(info.get("floatShares")) else None,
        "insider_percent": None,
        "institution_percent": None,

        # Risk & Demand Signals (computed)
        "beta": info.get("beta"),
        "short_percent_of_float": None,
        "shares_short": None,
        "overall_risk": None,
        "debt_to_equity": None,

        # Analyst Targets (not available on free tier)
        "target_mean_price": info.get("targetMeanPrice"),
        "target_median_price": info.get("targetMedianPrice"),
        "target_high_price": info.get("targetHighPrice"),
        "target_low_price": info.get("targetLowPrice"),
        "recommendation_key": info.get("recommendationKey") or None,
        "number_of_analysts": info.get("numberOfAnalystOpinions"),

        # DATA SOURCE TAG
        "data_source": "fh",
        "security_type": "STOCK",
        "provider_status": {"finnhub": "healthy", "yfinance": "degraded"},
    }


# ------------------------------------------------------------------
# Public API: get_batch_prices (same contract as old yfinance service)
# ------------------------------------------------------------------

async def _fetch_stock_price_safe(ticker: str) -> Dict[str, Any]:
    """Wrapper that catches per-ticker exceptions."""
    try:
        data = await get_stock_price(ticker)
        if data:
            return data
        return create_error_fallback(ticker, "fh")
    except Exception as e:
        logger.error(
            "[Finnhub] operation=batch_price ticker=%s outcome=failed exception_type=%s",
            ticker.upper(), type(e).__name__,
        )
        return create_error_fallback(ticker, "fh")


async def get_batch_prices(tickers: List[str]) -> List[Dict[str, Any]]:
    """Fetch analyst-grade data for multiple tickers in parallel batches.

    Finnhub free tier allows 60 REST calls/min (2 calls per ticker: quote + profile).
    We process tickers in small concurrent batches of 6 with staggered starts
    to stay well within the rate limit while being much faster than sequential.
    
    Sequential: ~35 tickers × 2.1s = ~73s (times out)
    Batched (6 concurrency): ~35 tickers / 6 × 2.1s ≈ 12-15s
    """
    # Deduplicate while preserving order
    seen: set = set()
    unique_tickers: List[str] = []
    for t in tickers:
        key = t.upper()
        if key not in seen:
            seen.add(key)
            unique_tickers.append(t)

    results: Dict[str, Dict[str, Any]] = {}
    batch_size = 6
    stagger_delay = 0.3  # seconds between batch starts
    
    for i in range(0, len(unique_tickers), batch_size):
        batch = unique_tickers[i:i + batch_size]
        tasks = [_fetch_stock_price_safe(t) for t in batch]
        batch_results = await asyncio.gather(*tasks)
        
        for ticker, data in zip(batch, batch_results):
            results[ticker.upper()] = data
        
        # Stagger batches to avoid bursting rate limits
        if i + batch_size < len(unique_tickers):
            await asyncio.sleep(stagger_delay)

    # Return results in original ticker order (preserve duplicates from input)
    return [results.get(t.upper(), create_error_fallback(t, "fh")) for t in tickers]
