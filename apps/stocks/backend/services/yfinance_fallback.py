# services/yfinance_fallback.py
"""
Pure yfinance fallback service — used ONLY when Finnhub fails or for ETFs/non-US symbols.

This module provides the same output shape as finnhub_service but tags every field
with `data_source: "yf"` so the frontend can display a purple "YF" badge.

ETF support: prefers fund assets and uses provider ETF market cap only as an
explicitly labeled market-size fallback.

Dynamic Security Detection: Uses quoteType metadata from yfinance to classify
securities as STOCK, ETF, INDEX, CRYPTO, ADR, or UNKNOWN.
"""

import logging
import math
import socket
import threading
import time
from numbers import Real
from typing import Any, Dict, List, Optional

import yfinance as yf
from yfinance.exceptions import YFRateLimitError

from backend.lib.constants import KNOWN_ETF_NAMES
from backend.lib.error_fallback import create_error_fallback
from backend.lib.market_data_normalization import normalize_market_data_payload
from backend.lib.risk_metrics import _compute_composite_risk, _safe_pct
from backend.services.yfinance_cache import configure_yfinance_cache

logger = logging.getLogger(__name__)

_YFINANCE_COOLDOWN_SECONDS = 120
_yfinance_cooldown_until = 0.0
_yfinance_last_failure_class: Optional[str] = None
_yfinance_cooldown_lock = threading.Lock()
_yfinance_half_open_probe_in_progress = False

_COOLDOWN_FAILURES = {"rate_limit", "invalid_crumb", "unauthorized"}


def _raise_programmer_error(exception: BaseException) -> None:
    """Do not convert coding/test-contract failures into provider degradation."""
    if isinstance(exception, (AssertionError, NameError, UnboundLocalError)):
        raise exception


def _classify_yfinance_outage(exception: BaseException) -> str:
    """Normalize provider failures without relying on exception class names alone."""
    message = str(exception).strip().casefold()
    if "invalid crumb" in message:
        return "invalid_crumb"
    if isinstance(exception, YFRateLimitError):
        return "rate_limit"

    response = getattr(exception, "response", None)
    status_code = getattr(exception, "status_code", None) or getattr(
        response, "status_code", None
    )
    if status_code == 429:
        return "rate_limit"
    if "too many requests" in message or "http 429" in message:
        return "rate_limit"
    if status_code in {401, 403} or any(
        marker in message for marker in ("unauthorized", "access denied", "forbidden")
    ):
        return "unauthorized"
    if isinstance(exception, (TimeoutError, socket.timeout)) or "timed out" in message or "timeout" in message:
        return "timeout"
    if any(marker in message for marker in ("json", "decode", "parse")):
        return "parse_error"
    if any(marker in message for marker in ("empty response", "no data", "no info")):
        return "empty_response"
    if any(marker in message for marker in ("unsupported", "not applicable")):
        return "unsupported_field"
    return "transport_error"


def _record_yfinance_outage_failure(exception: BaseException) -> Optional[str]:
    """Open the bounded process-local cooldown for a recognized Yahoo outage."""
    failure_class = _classify_yfinance_outage(exception)
    if failure_class not in _COOLDOWN_FAILURES:
        return None

    global _yfinance_cooldown_until, _yfinance_last_failure_class, _yfinance_half_open_probe_in_progress
    with _yfinance_cooldown_lock:
        now = time.monotonic()
        opened = now >= _yfinance_cooldown_until
        if opened:
            _yfinance_cooldown_until = now + _YFINANCE_COOLDOWN_SECONDS
            _yfinance_last_failure_class = failure_class
            _yfinance_half_open_probe_in_progress = False
    if opened:
        logger.warning(
            "[YF-Fallback] event=yfinance_cooldown_opened failure_class=%s cooldown_seconds=%s",
            failure_class,
            _YFINANCE_COOLDOWN_SECONDS,
        )
    else:
        logger.debug("[YF-Fallback] event=yfinance_cooldown_already_open failure_class=%s", failure_class)
    return failure_class


def _load_yfinance_info(ticker: str) -> tuple[yf.Ticker, Dict[str, Any]]:
    """Fetch metadata once; yfinance owns its cookie-strategy switching internally."""
    ticker_obj = yf.Ticker(ticker.upper())
    return ticker_obj, ticker_obj.info or {}


def _begin_yfinance_fundamentals_attempt() -> tuple[bool, Optional[str], bool]:
    """Atomically authorize a normal attempt or the sole half-open probe."""
    global _yfinance_half_open_probe_in_progress
    now = time.monotonic()
    with _yfinance_cooldown_lock:
        if now < _yfinance_cooldown_until:
            return False, "cooldown_open", False
        if _yfinance_last_failure_class in _COOLDOWN_FAILURES:
            if _yfinance_half_open_probe_in_progress:
                return False, "cooldown_open", False
            _yfinance_half_open_probe_in_progress = True
            return True, _yfinance_last_failure_class, True
        return True, None, False


def _complete_yfinance_fundamentals_attempt(*, probe: bool, succeeded: bool) -> None:
    """Close a half-open probe, clearing the outage only after provider success."""
    global _yfinance_cooldown_until, _yfinance_last_failure_class, _yfinance_half_open_probe_in_progress
    if not probe:
        return
    with _yfinance_cooldown_lock:
        _yfinance_half_open_probe_in_progress = False
        if succeeded:
            _yfinance_cooldown_until = 0.0
            _yfinance_last_failure_class = None
        else:
            _yfinance_cooldown_until = time.monotonic() + _YFINANCE_COOLDOWN_SECONDS


def _yfinance_cooldown_status() -> tuple[bool, Optional[str]]:
    """Return whether the process-local Yahoo cooldown remains active."""
    now = time.monotonic()
    with _yfinance_cooldown_lock:
        return now < _yfinance_cooldown_until, _yfinance_last_failure_class


def _reset_yfinance_cooldown_for_tests() -> None:
    """Reset bounded process-local cooldown state for test isolation."""
    global _yfinance_cooldown_until, _yfinance_last_failure_class, _yfinance_half_open_probe_in_progress
    with _yfinance_cooldown_lock:
        _yfinance_cooldown_until = 0.0
        _yfinance_last_failure_class = None
        _yfinance_half_open_probe_in_progress = False


# ==============================================================================
# Security Type Detection
# ==============================================================================

def _detect_security_type(info: Dict[str, Any]) -> str:
    """Dynamically detect security type from yfinance quoteType metadata.
    
    Returns one of: STOCK, ETF, INDEX, CRYPTO, ADR, UNKNOWN
    """
    quote_type = info.get("quoteType", "").upper()
    if not quote_type:
        # Fallback: try assetType
        asset_type = info.get("assetType", "").upper()
        if asset_type:
            return _normalize_asset_type(asset_type)
        return "UNKNOWN"
    
    return _normalize_asset_type(quote_type)


def _normalize_asset_type(asset_type: str) -> str:
    """Normalize yfinance assetType/quoteType to our SecurityType enum."""
    mapping = {
        "ETF": "ETF",
        "ETF ETF": "ETF",
        "FUND": "ETF",
        "INDEX": "INDEX",
        "CRYPTOCURRENCY": "CRYPTO",
        "CRYPTO": "CRYPTO",
        "ADR": "ADR",
        "STOCK": "STOCK",
        "EQUITY": "STOCK",
        "CLOSED_FUND": "STOCK",
    }
    return mapping.get(asset_type, "UNKNOWN")


def _normalize_yfinance_percentage(value: Any) -> Optional[float]:
    """Normalize yfinance percentage metadata to a decimal fraction.

    yfinance 1.x reports ETF percentage metadata in percentage points, while
    older 0.x releases reported a decimal fraction. The frontend contract
    always uses decimal fractions.
    """
    if isinstance(value, bool):
        return None
    try:
        normalized = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(normalized):
        return None
    try:
        major_version = int(str(yf.__version__).split(".", 1)[0])
    except (AttributeError, TypeError, ValueError):
        major_version = 0
    return normalized / 100 if major_version >= 1 else normalized


# ==============================================================================
# Helper functions (extracted for testability and readability — TD-CQ-005 fix)
# ==============================================================================

def _get_quote_type(info: Dict[str, Any]) -> str:
    """Return normalized quote type string."""
    return info.get("quoteType", "").upper()


def _is_etf(info: Dict[str, Any]) -> bool:
    """Check if the ticker represents an ETF."""
    return _get_quote_type(info) == "ETF"


def _is_index(info: Dict[str, Any]) -> bool:
    """Check if the ticker represents an Index."""
    return _get_quote_type(info) == "INDEX"


def _is_crypto(info: Dict[str, Any]) -> bool:
    """Check if the ticker represents a Cryptocurrency."""
    return _get_quote_type(info) == "CRYPTOCURRENCY"


def _positive_market_number(value: Any) -> float | None:
    """Accept only finite positive numeric provider values, never bools/strings."""
    if isinstance(value, bool) or not isinstance(value, Real):
        return None
    normalized = float(value)
    return normalized if math.isfinite(normalized) and normalized > 0 else None


def _resolve_market_cap(info: Dict[str, Any], security_type: str, current_price: Any) -> tuple[float | None, bool]:
    """Return a direct company cap or a conservative ordinary-stock fallback.

    ADR fallback is disabled because generic sharesOutstanding can describe
    native ordinary shares rather than the listed ADR share class.
    """
    if security_type not in {"STOCK", "ADR"}:
        return None, False
    direct = _positive_market_number(info.get("marketCap")) or _positive_market_number(info.get("nonDilutedMarketCap"))
    if direct is not None:
        return direct, False
    if security_type != "STOCK":
        return None, False
    price = _positive_market_number(current_price)
    shares = _positive_market_number(info.get("sharesOutstanding"))
    if price is None or shares is None or not (info.get("currency") or info.get("financialCurrency")):
        return None, False
    result = price * shares
    return (result, True) if math.isfinite(result) and 0 < result <= 100_000_000_000_000 else (None, False)


def _resolve_fund_assets(info: Dict[str, Any]) -> float | None:
    for field in ("totalAssets", "netAssets"):
        value = _positive_market_number(info.get(field))
        if value is not None:
            return value
    return None


def _resolve_fund_assets_with_source(info: Dict[str, Any]) -> tuple[float | None, str | None]:
    for field in ("totalAssets", "netAssets"):
        value = _positive_market_number(info.get(field))
        if value is not None:
            return value, f"yfinance_info.{field}"
    return None, None

def _resolve_etf_market_cap(
    ticker_obj: yf.Ticker, info: Dict[str, Any]
) -> tuple[float | None, str | None]:
    """Return Yahoo's absolute ETF market value and its access path."""
    for field in ("marketCap", "nonDilutedMarketCap"):
        value = _positive_market_number(info.get(field))
        if value is not None:
            return value, f"yfinance_info.{field}"
    try:
        fast_info = ticker_obj.fast_info
        try:
            raw_value = fast_info["market_cap"]
        except (KeyError, TypeError):
            raw_value = getattr(fast_info, "market_cap", None)
    except Exception as exc:
        _raise_programmer_error(exc)
        logger.debug(
            "[YF-ETF] Fast market cap unavailable for %s: %s",
            ticker_obj.ticker,
            type(exc).__name__,
        )
        return None, None
    value = _positive_market_number(raw_value)
    return (value, "yfinance_fast_info.market_cap") if value is not None else (None, None)

def _resolve_shares_outstanding(info: Dict[str, Any], is_etf_flag: bool) -> int | None:
    """Resolve shares outstanding, computing from NAV for ETFs when needed."""
    value = _positive_market_number(
        info.get("sharesOutstanding") or info.get("impliedSharesOutstanding")
    )
    if value is None and is_etf_flag:
        total_assets = _positive_market_number(
            info.get("totalAssets") or info.get("netAssets")
        )
        nav_price = _positive_market_number(info.get("navPrice"))
        if total_assets is not None and nav_price is not None:
            value = total_assets / nav_price
    return int(value) if value is not None else None


def _resolve_float_shares(
    info: Dict[str, Any], shares_outstanding: int | None, is_etf_flag: bool
) -> int | None:
    """Resolve float shares, using outstanding as fallback for ETFs."""
    value = _positive_market_number(info.get("floatShares"))
    if is_etf_flag and value is None:
        value = _positive_market_number(shares_outstanding)
    return int(value) if value is not None else None


def _resolve_beta(info: Dict[str, Any]) -> float | None:
    """Resolve beta value, falling back to beta3Year for ETFs."""
    # beta3Year rarely populated; keep as last resort fallback (TD-CQ-006 noted)
    for field in ("beta", "beta3Year"):
        value = info.get(field)
        if isinstance(value, Real) and not isinstance(value, bool) and math.isfinite(float(value)):
            return float(value)
    return None


def _assemble_price_fields(info: Dict[str, Any]) -> Dict[str, Any]:
    """Extract core price + volume fields from yfinance info.
    
    Uses post-market/after-hours prices when available so watchlist stays live after 4pm ET.
    Falls back to regular market prices during trading hours or for ETFs without after-hours data.
    """
    # Prefer a valid post-market quote while retaining its session provenance.
    post_market_price = _positive_market_number(info.get("postMarketPrice"))
    regular_market_price = (
        _positive_market_number(info.get("regularMarketPrice"))
        or _positive_market_number(info.get("currentPrice"))
    )
    current_price = post_market_price or regular_market_price
    
    previous_close = info.get("previousClose") or info.get("regularMarketPreviousClose")

    return {
        "current_price": current_price,
        "open_price": info.get("open") or info.get("regularMarketOpen"),
        "previous_close": previous_close,
        "day_low": info.get("dayLow") or info.get("regularMarketDayLow"),
        "day_high": info.get("dayHigh") or info.get("regularMarketDayHigh"),
        "fifty_two_week_high": info.get("fiftyTwoWeekHigh"),
        "fifty_two_week_low": info.get("fiftyTwoWeekLow"),
        "change": None,
        "change_percent": None,
        "volume": info.get("regularMarketVolume"),
        "post_market_price": post_market_price,
        "post_market_change": info.get("postMarketChange"),
        "post_market_change_percent": info.get("postMarketChangePercent"),
        "regular_close": regular_market_price,
        "market_session": "after_hours" if post_market_price is not None else None,
        "price_source": "post_market_price" if post_market_price is not None else None,
    }


def _normalize_price_fields(fields: Dict[str, Any]) -> None:
    """Reject placeholder numerics and keep range/change fields internally consistent."""
    for field in (
        "current_price", "open_price", "previous_close", "day_low", "day_high",
        "fifty_two_week_high", "fifty_two_week_low",
    ):
        fields[field] = _positive_market_number(fields.get(field))
    volume = fields.get("volume")
    if isinstance(volume, bool) or not isinstance(volume, Real) or not math.isfinite(float(volume)) or volume < 0:
        fields["volume"] = None
    else:
        fields["volume"] = int(volume)
    high = fields.get("fifty_two_week_high")
    low = fields.get("fifty_two_week_low")
    if high is not None and low is not None and low > high:
        fields["fifty_two_week_high"] = None
        fields["fifty_two_week_low"] = None
    current = fields.get("current_price")
    previous = fields.get("previous_close")
    if current is not None and previous is not None:
        fields["change"] = round(current - previous, 2)
        fields["change_percent"] = _safe_pct(current - previous, previous)
    else:
        fields["change"] = None
        fields["change_percent"] = None


def _fast_info_value(fast_info: Any, *names: str) -> Any:
    for name in names:
        try:
            value = fast_info[name]
        except (KeyError, TypeError):
            value = getattr(fast_info, name, None)
        if value is not None:
            return value
    return None


def _recover_fast_info_fields(ticker_obj: yf.Ticker, fields: Dict[str, Any]) -> None:
    """Fill only missing quote/range fields from the independent fast-info path."""
    mapping = {
        "current_price": ("last_price", "lastPrice"),
        "previous_close": ("previous_close", "previousClose"),
        "open_price": ("open",),
        "day_low": ("day_low", "dayLow"),
        "day_high": ("day_high", "dayHigh"),
        "fifty_two_week_low": ("year_low", "yearLow"),
        "fifty_two_week_high": ("year_high", "yearHigh"),
        "volume": ("last_volume", "lastVolume"),
    }
    if all(fields.get(output_field) is not None for output_field in mapping):
        return
    fast_info = ticker_obj.fast_info
    for output_field, names in mapping.items():
        if fields.get(output_field) is None:
            value = _fast_info_value(fast_info, *names)
            if output_field == "volume":
                normalized = _finite_real(value)
                if normalized is not None and normalized >= 0:
                    fields[output_field] = int(normalized)
            elif _positive_market_number(value) is not None:
                fields[output_field] = float(value)


def _recover_history_fields(
    ticker_obj: yf.Ticker,
    fields: Dict[str, Any],
    cached_fields: Optional[Dict[str, Any]] = None,
) -> None:
    """Use one bounded one-year history request for range/volume gaps only."""
    wanted = {
        "fifty_two_week_high": "High",
        "fifty_two_week_low": "Low",
        "volume": "Volume",
    }
    cached_fields = cached_fields or {}
    missing = {
        name for name in wanted
        if fields.get(name) is None and _positive_market_number(cached_fields.get(name)) is None
    }
    if not missing:
        return
    history = ticker_obj.history(period="1y", auto_adjust=True, keepna=True, timeout=10)
    if history is None or getattr(history, "empty", True):
        return
    recovered: Dict[str, Any] = {}
    for output_field, column_name in wanted.items():
        if output_field not in missing or column_name not in history:
            continue
        series = history[column_name].dropna()
        if getattr(series, "empty", True):
            continue
        if output_field == "fifty_two_week_high":
            value = series.max()
        elif output_field == "fifty_two_week_low":
            value = series.min()
        else:
            value = series.iloc[-1]
        if output_field == "volume":
            normalized = _finite_real(value)
            if normalized is not None and normalized >= 0:
                recovered[output_field] = int(normalized)
        elif _positive_market_number(value) is not None:
            recovered[output_field] = float(value)
    candidate_high = recovered.get("fifty_two_week_high", fields.get("fifty_two_week_high"))
    candidate_low = recovered.get("fifty_two_week_low", fields.get("fifty_two_week_low"))
    if candidate_high is not None and candidate_low is not None and candidate_low > candidate_high:
        recovered.pop("fifty_two_week_high", None)
        recovered.pop("fifty_two_week_low", None)
    fields.update(recovered)


def _assemble_risk_fields(
    beta: float | None,
    current_price: float | None,
    info: Dict[str, Any],
    high: float | None,
    low: float | None,
) -> Dict[str, Any]:
    """Extract risk + demand signal fields."""
    short_pct = _nonnegative_real(info.get("shortPercentOfFloat"))
    debt_to_equity = _finite_real(info.get("debtToEquity"))
    inputs = (beta, short_pct, debt_to_equity, high, low, current_price)
    risk = (
        _compute_composite_risk(
            beta=float(beta), short_pct_of_float=float(short_pct), debt_eq=float(debt_to_equity),
            high52=float(high), low52=float(low), current_price=float(current_price),
        )
        if all(value is not None for value in inputs) and low <= high
        else None
    )
    return {
        "beta": beta,
        "short_percent_of_float": round(short_pct, 4) if short_pct is not None else None,
        "shares_short": _positive_int(info.get("sharesShort")),
        "insider_percent": _rounded_nonnegative(info.get("heldPercentInsiders")),
        "institution_percent": _rounded_nonnegative(info.get("heldPercentInstitutions")),
        "debt_to_equity": debt_to_equity,
        "overall_risk": risk,
    }


def _finite_real(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, Real):
        return None
    normalized = float(value)
    return normalized if math.isfinite(normalized) else None


def _positive_int(value: Any) -> int | None:
    normalized = _positive_market_number(value)
    return int(normalized) if normalized is not None else None


def _nonnegative_real(value: Any) -> float | None:
    normalized = _finite_real(value)
    return normalized if normalized is not None and normalized >= 0 else None


def _nonnegative_int(value: Any) -> int | None:
    normalized = _nonnegative_real(value)
    return int(normalized) if normalized is not None else None


def _rounded_nonnegative(value: Any) -> float | None:
    normalized = _nonnegative_real(value)
    return round(normalized, 4) if normalized is not None else None


def _assemble_analyst_fields(info: Dict[str, Any]) -> Dict[str, Any]:
    """Extract analyst target and recommendation fields."""
    return {
        "target_mean_price": _positive_market_number(info.get("targetMeanPrice")),
        "target_median_price": _positive_market_number(info.get("targetMedianPrice")),
        "target_high_price": _positive_market_number(info.get("targetHighPrice")),
        "target_low_price": _positive_market_number(info.get("targetLowPrice")),
        "recommendation_key": info.get("recommendationKey") or None,
        "number_of_analysts": _nonnegative_int(info.get("numberOfAnalystOpinions")),
    }


def _extract_ceo_name(ticker_obj: yf.Ticker, info: Dict[str, Any]) -> Optional[str]:
    """Read CEO only from already-fetched info; never call ``ticker.officers``."""
    officers = info.get("companyOfficers")
    if isinstance(officers, list):
        for officer in officers:
            if not isinstance(officer, dict):
                continue
            title = str(officer.get("title") or "").casefold()
            name = officer.get("name")
            if (
                "chief executive officer" in title or title == "ceo"
            ) and isinstance(name, str) and name.strip():
                return name.strip()
    return None


def _resolve_fund_name(info: Dict[str, Any], ticker: str) -> str:
    """Prefer provider names and fall back to the valid ticker."""
    for field in ("longName", "shortName"):
        value = info.get(field)
        if isinstance(value, str) and value.strip() and value.strip().upper() != "N/A":
            return value.strip()
    return ticker.upper()
def _assemble_company_fields(ticker_obj: yf.Ticker, info: Dict[str, Any]) -> Dict[str, Any]:
    """Extract company profile fields without additional provider calls."""
    return {
        "company_name": _resolve_fund_name(info, ticker_obj.ticker),
        "sector": info.get("sector"),
        "industry": info.get("industry"),
        "long_business_summary": info.get("longBusinessSummary"),
        "website": info.get("website"),
        "full_time_employees": _positive_int(info.get("fullTimeEmployees")),
        "average_analyst_rating": info.get("recommendationKey"),
        "forward_pe": info.get("forwardPE"),
        "ceo_name": _extract_ceo_name(ticker_obj, info),
        "exchange": info.get("exchange"),
    }


# ==============================================================================
# Lazy ETF Data Fetching
# ==============================================================================

def _fetch_etf_data_lazy(ticker_obj: yf.Ticker, info: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Fetch ETF-specific data using lazy evaluation.
    
    Only fetches fund-specific endpoints when the security is detected as an ETF.
    Returns None for non-ETF securities to avoid unnecessary API calls.
    """
    if not _is_etf(info):
        return None
    
    etf_data = {
        "fund_family": info.get("fundFamily"),
        "expense_ratio": _normalize_yfinance_percentage(info.get("expenseRatio")),
        "net_assets": _resolve_fund_assets(info) or None,
        "inception_date": _format_date(info.get("fundInceptionDate")),
        "dividend_yield": _normalize_yfinance_percentage(info.get("dividendYield")),
        "distribution_frequency": _get_distribution_frequency(info),
        "index_tracked": info.get("indexType"),
        "category": info.get("category"),
        "holdings_count": info.get("holdingsCount"),
    }
    
    # Fetch top holdings only for ETFs (expensive call, lazy-loaded)
    try:
        holdings = _get_top_holdings(ticker_obj)
        if holdings:
            etf_data["top_holdings"] = holdings
    except Exception as e:
        _raise_programmer_error(e)
        logger.debug("[YF-ETF] Failed to fetch holdings for %s: %s", ticker_obj.ticker, e)
        etf_data["top_holdings"] = None
    
    # Fetch sector allocation only for ETFs
    try:
        sector_alloc = _get_sector_allocation(info)
        if sector_alloc:
            etf_data["sector_allocation"] = sector_alloc
    except Exception as e:
        _raise_programmer_error(e)
        logger.debug("[YF-ETF] Failed to fetch sector allocation for %s: %s", ticker_obj.ticker, e)
        etf_data["sector_allocation"] = None
    
    # Clean up None values
    return {k: v for k, v in etf_data.items() if v is not None}


def _format_date(date_val: Any) -> Optional[str]:
    """Format date value to ISO string."""
    if not date_val:
        return None
    try:
        if isinstance(date_val, (int, float)):
            from datetime import datetime
            return datetime.fromtimestamp(date_val).strftime("%Y-%m-%d")
        return str(date_val)
    except Exception as exc:
        _raise_programmer_error(exc)
        return None


def _get_distribution_frequency(info: Dict[str, Any]) -> Optional[str]:
    """Extract distribution frequency from ETF info."""
    # Common values: "Quarterly", "Monthly", "Semi-Annual", "Annual"
    freq = info.get("distributionFrequency")
    if freq:
        return str(freq)
    return None


def _get_top_holdings(ticker_obj: yf.Ticker) -> Optional[List[Dict[str, Any]]]:
    """Fetch top holdings for an ETF.
    
    Uses the holdings endpoint which contains individual position data.
    """
    try:
        holdings = ticker_obj.holdings
        if holdings is not None and len(holdings) > 0:
            result = []
            for _, row in holdings.iterrows():
                result.append({
                    "name": str(row.get("Holdings", "")),
                    "ticker": "",  # Holdings API doesn't provide ticker symbols
                    "weight": float(row.get("Weight", 0)),
                })
            return result[:10]  # Limit to top 10
    except Exception as exc:
        _raise_programmer_error(exc)
    
    return None


def _get_sector_allocation(info: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
    """Extract sector allocation from ETF info."""
    # yfinance provides sector data in various formats
    sectors = info.get("sectorWeightings")
    if isinstance(sectors, dict):
        result = []
        for sector_name, weight in sectors.items():
            if weight and weight > 0:
                result.append({
                    "sector": str(sector_name),
                    "weight": round(float(weight), 2),
                })
        return result if result else None
    return None


# ==============================================================================
# Main API Functions
# ==============================================================================

def get_stock_price_yf(
    ticker: str,
    *,
    cached_fundamentals: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Fetch stock data via yfinance (fallback). Returns None on failure.
    
    Includes dynamic security type detection and lazy ETF data fetching.
    """
    cooldown_active, failure_class = _yfinance_cooldown_status()
    if cooldown_active:
        logger.debug(
            "[YF-Fallback] event=yfinance_cooldown_skip failure_class=%s",
            failure_class,
        )
        return None

    configure_yfinance_cache(yf)
    try:
        ticker_obj = yf.Ticker(ticker.upper())
        info_error: BaseException | None = None
        try:
            info = ticker_obj.info or {}
        except Exception as exc:
            _raise_programmer_error(exc)
            info_error = exc
            if _classify_yfinance_outage(exc) in _COOLDOWN_FAILURES:
                raise
            info = {}

        security_type = _detect_security_type(info)
        if security_type == "UNKNOWN" and ticker.upper() in KNOWN_ETF_NAMES:
            security_type = "ETF"
        etf = security_type == "ETF"
        # Prefer post-market price for after-hours trading, fall back to regular market price
        current_price = info.get("postMarketPrice") or info.get("currentPrice") or info.get("regularMarketPrice")
        beta = _resolve_beta(info)

        # Build result by composing helpers
        result: Dict[str, Any] = {
            "ticker": ticker.upper(),
            "symbol": ticker.upper(),
            "data_source": "yf",
            "security_type": security_type,
            "provider_status": {"finnhub": "degraded", "yfinance": "healthy"},
        }
        result.update(_assemble_company_fields(ticker_obj, info))
        if security_type == "ETF":
            for field in ("ceo_name", "full_time_employees", "average_analyst_rating", "forward_pe"):
                result[field] = None
        if security_type == "ETF" and not result.get("long_business_summary"):
            try:
                description = ticker_obj.funds_data.description
            except Exception as exc:
                _raise_programmer_error(exc)
                logger.debug("[YF-ETF] Fund description unavailable for %s: %s", ticker, type(exc).__name__)
            else:
                if isinstance(description, str) and description.strip():
                    result["long_business_summary"] = description.strip()
        price_fields = _assemble_price_fields(info)
        _normalize_price_fields(price_fields)
        try:
            _recover_fast_info_fields(ticker_obj, price_fields)
        except Exception as exc:
            _raise_programmer_error(exc)
            logger.debug("[YF-Fallback] fast_info unavailable for %s: %s", ticker, type(exc).__name__)
        try:
            _normalize_price_fields(price_fields)
            _recover_history_fields(ticker_obj, price_fields, cached_fundamentals)
        except Exception as exc:
            _raise_programmer_error(exc)
            logger.debug("[YF-Fallback] history unavailable for %s: %s", ticker, type(exc).__name__)
        _normalize_price_fields(price_fields)
        result.update(price_fields)
        current_price = result.get("current_price")
        if not info and not any(
            _positive_market_number(result.get(field)) is not None
            for field in ("current_price", "previous_close", "fifty_two_week_high", "fifty_two_week_low", "volume")
        ):
            if info_error is not None:
                raise info_error
            raise RuntimeError("empty response")
        result["market_size_currency"] = info.get("currency") or info.get("financialCurrency")
        result["market_cap"], result["market_size_fallback_used"] = _resolve_market_cap(info, security_type, current_price)
        if security_type == "ETF":
            fund_assets, fund_assets_source = _resolve_fund_assets_with_source(info)
            result["fund_assets"] = fund_assets
            result["fund_assets_source"] = fund_assets_source
            etf_market_cap, etf_market_cap_source = (
                _resolve_etf_market_cap(ticker_obj, info)
                if fund_assets is None
                else (None, None)
            )
            result["etf_market_cap"] = etf_market_cap
            result["etf_market_cap_source"] = etf_market_cap_source
        
        # Only include share structure for STOCKs
        if security_type == "STOCK":
            result["shares_outstanding"] = _resolve_shares_outstanding(info, etf)
            result["float_shares"] = _resolve_float_shares(
                info, result.get("shares_outstanding"), etf
            )
        
        # Only include stock-specific risk fields for STOCKs
        if security_type == "STOCK":
            result.update(_assemble_risk_fields(
                beta,
                current_price,
                info,
                result.get("fifty_two_week_high"),
                result.get("fifty_two_week_low"),
            ))
        
        # Beta is always useful
        result["beta"] = beta
        
        # Only include analyst targets for STOCKs
        if security_type == "STOCK":
            result.update(_assemble_analyst_fields(info))
        
        # Lazy-fetch ETF data only for ETFs
        if security_type == "ETF":
            etf_data = _fetch_etf_data_lazy(ticker_obj, info)
            if etf_data:
                result["etf_data"] = etf_data
        
        normalized = normalize_market_data_payload(
            ticker,
            result,
            default_source="yf",
        )
        return normalized
    except Exception as exc:
        _raise_programmer_error(exc)
        failure_class = _classify_yfinance_outage(exc)
        _record_yfinance_outage_failure(exc)
        logger.log(
            logging.WARNING if failure_class in _COOLDOWN_FAILURES else logging.ERROR,
            "[YF-Fallback] Failed for %s: failure_class=%s exception_type=%s",
            ticker,
            failure_class,
            type(exc).__name__,
        )
        return None


def get_batch_prices_yf(tickers: List[str]) -> List[Dict[str, Any]]:
    """Fetch multiple tickers via yfinance (fallback)."""
    results = []
    for t in tickers:
        data = get_stock_price_yf(t)
        if data:
            results.append(data)
        else:
            results.append(create_error_fallback(t, "yf"))
    return results


__all__ = [
    "get_stock_price_yf",
    "get_batch_prices_yf",
]
