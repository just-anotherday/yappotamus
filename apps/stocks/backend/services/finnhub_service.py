# services/finnhub_service.py
"""
Finnhub API Service — replaces yfinance for all market data operations.

Free tier limits (https://finnhub.io/docs/api/rate-limit):
 - 60 REST API calls per minute
 - 30 WebSocket messages per second
 - 1 request/second for some endpoints

Endpoints used:
 - /quote              → real-time quote data
 - /stock-profile2     → company profile + fundamentals (via symbol search + profile)
 - /symbol-search      → search valid ticker symbols
 - /company-news2      → market news for a ticker
 - WebSocket           → real-time trade/quote streaming
"""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

import finnhub
import tenacity

from backend.config.settings import settings
from backend.config.polling_settings import polling_settings
from backend.lib.constants import KNOWN_NON_STOCK_SYMBOLS
from backend.lib.error_fallback import create_error_fallback
from backend.lib.risk_metrics import _compute_composite_risk, _safe_pct

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
    """Ensure we don't exceed the free-tier rate limit."""
    global _last_call_time
    async with _get_rate_lock():
        now = time.time()
        elapsed = now - _last_call_time
        if elapsed < _min_interval:
            wait_time = _min_interval - elapsed
            await asyncio.sleep(wait_time)
        _last_call_time = time.time()


# ------------------------------------------------------------------
# Async retry helper for transient failures (ARCH-003 fix)
# ------------------------------------------------------------------

async def _retry_api(func, *args, **kwargs):
    """Call an async function with retry on transient network failures.

    Only retries TimeoutError and ConnectionError.
    Programming errors, validation errors, and auth failures fail fast.
    """
    async for attempt in tenacity.AsyncRetrying(
        stop=tenacity.stop_after_attempt(3),
        wait=tenacity.wait_exponential(multiplier=0.5, max=5),
        retry=tenacity.retry_if_exception_type((TimeoutError, ConnectionError)),
        reraise=True,
    ):
        with attempt:
            return await func(*args, **kwargs)


def _retry_api_sync(func, *args, **kwargs):
    """Call a synchronous function with retry on transient network failures."""
    for attempt in tenacity.Retrying(
        stop=tenacity.stop_after_attempt(3),
        wait=tenacity.wait_exponential(multiplier=0.5, max=5),
        retry=tenacity.retry_if_exception_type((TimeoutError, ConnectionError)),
        reraise=True,
    ):
        with attempt:
            return func(*args, **kwargs)


# ------------------------------------------------------------------
# Core: Fetch quote data (replaces yfinance current price info)
# ------------------------------------------------------------------

async def _do_quote(client: finnhub.Client, ticker: str):
    """Inner API call — may raise on transient failures (retryable)."""
    return client.quote(ticker.upper())


async def fetch_quote(ticker: str) -> Dict[str, Any]:
    """Fetch real-time quote for a ticker via Finnhub /quote endpoint."""
    await _rate_limiter()
    client = get_finnhub_client()
    try:
        quote = await _retry_api(_do_quote, client, ticker)
        if not quote or quote.get("c") == 0:
            logger.warning("[Finnhub] No quote data for %s", ticker)
            return {}
        return quote
    except Exception as e:
        logger.error("[Finnhub] Failed to fetch quote for %s: %s", ticker, e)
        return {}


# ------------------------------------------------------------------
# Core: Fetch company profile (replaces yfinance .info fundamentals)
# ------------------------------------------------------------------

async def _do_profile(client: finnhub.Client, ticker: str):
    """Inner API call — may raise on transient failures (retryable)."""
    return client.company_profile2(symbol=ticker.upper())


async def fetch_company_profile(ticker: str) -> Dict[str, Any]:
    """Fetch company profile via Finnhub /stock-profile2 endpoint."""
    await _rate_limiter()
    client = get_finnhub_client()
    try:
        profile = await _retry_api(_do_profile, client, ticker)
        # company_profile2 returns a list; take first match
        if profile and len(profile) > 0:
            return profile[0]
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
            logger.debug("[Finnhub] Profile unavailable for %s (not a traded equity): %s", ticker, e)
        else:
            logger.warning("[Finnhub] Unexpected profile error for %s: %s", ticker, e)
        return {}


# ------------------------------------------------------------------
# Core: Search symbol (replaces yfinance ticker validation)
# ------------------------------------------------------------------

async def search_symbol(query: str) -> List[Dict[str, Any]]:
    """Search for valid ticker symbols via Finnhub /symbol-search endpoint."""
    await _rate_limiter()
    client = get_finnhub_client()
    try:
        results = _retry_api_sync(client.symbol_lookup, query.upper(), exchange="US")
        return results if results else []
    except Exception as e:
        logger.error("[Finnhub] Symbol search failed for %s: %s", query, e)
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
        "marketCap": profile.get("marketCapitalization") or 0,
        "sharesOutstanding": profile.get("sharesOutstanding") or 0,
        "floatShares": profile.get("dilutedSharesOutstanding") or 0,

        # Risk indicators (best-effort from profile)
        "beta": profile.get("beta") or 1.0,

	# 52-week range not available on Finnhub free tier — set to 0 so hybrid_data_service
	# enrichment via yfinance can fill these gap fields correctly.
	"fiftyTwoWeekHigh": 0,
	"fiftyTwoWeekLow": 0,

        # Analyst data (not available on free Finnhub tier — set defaults)
        "forwardPE": None,
        "averageAnalystRating": None,
        "heldPercentInsiders": 0.0,
        "heldPercentInstitutions": 0.0,
        "shortPercentOfFloat": 0.0,
        "sharesShort": 0,
        "debtToEquity": 0.0,
        "targetMeanPrice": None,
        "targetMedianPrice": None,
        "targetHighPrice": None,
        "targetLowPrice": None,
        "recommendationKey": "N/A",
        "numberOfAnalystOpinions": 0,
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

    current_price = info.get("currentPrice", 0) or 0
    previous_close = info.get("previousClose", 0) or 0

    return {
        # Identity
        "ticker": ticker.upper(),
        "symbol": info.get("symbol", ticker.upper()),
        "company_name": info.get("shortName", info.get("longName", "N/A")),
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
        "open_price": info.get("regularMarketOpen", 0) or 0,
        "previous_close": previous_close,
        "day_low": info.get("regularMarketDayLow", 0) or 0,
        "day_high": info.get("regularMarketDayHigh", 0) or 0,
        "fifty_two_week_high": info.get("fiftyTwoWeekHigh", 0) or 0,
        "fifty_two_week_low": info.get("fiftyTwoWeekLow", 0) or 0,
        "change": round(current_price - previous_close, 2) if current_price and previous_close else 0,
        "change_percent": round(info.get("regularMarketChangePercent", 0) or 0, 2),
        "market_cap": info.get("marketCap", 0) or 0,

        # Share Structure
        "shares_outstanding": int(info.get("sharesOutstanding", 0) or 0),
        "float_shares": int(info.get("floatShares", 0) or 0),
        "insider_percent": round(info.get("heldPercentInsiders", 0.0) or 0.0, 4),
        "institution_percent": round(info.get("heldPercentInstitutions", 0.0) or 0.0, 4),

        # Risk & Demand Signals (computed)
        "beta": info.get("beta", 1.0) or 1.0,
        "short_percent_of_float": round(info.get("shortPercentOfFloat", 0.0) or 0.0, 4),
        "shares_short": int(info.get("sharesShort", 0) or 0),
        "overall_risk": _compute_composite_risk(
            beta=info.get("beta") or 1.0,
            short_pct_of_float=info.get("shortPercentOfFloat") or 0.0,
            debt_eq=info.get("debtToEquity") or 0.0,
            high52=info.get("fiftyTwoWeekHigh") or 0,
            low52=info.get("fiftyTwoWeekLow") or 0,
            current_price=current_price,
        ),

        # Analyst Targets (not available on free tier)
        "target_mean_price": info.get("targetMeanPrice"),
        "target_median_price": info.get("targetMedianPrice"),
        "target_high_price": info.get("targetHighPrice"),
        "target_low_price": info.get("targetLowPrice"),
        "recommendation_key": info.get("recommendationKey", "N/A") or "N/A",
        "number_of_analysts": info.get("numberOfAnalystOpinions", 0) or 0,

        # DATA SOURCE TAG
        "data_source": "fh",
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
        logger.error("[Finnhub] Batch fetch failed for %s: %s", ticker, e)
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
