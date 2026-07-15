# services/yfinance_fallback.py
"""
Pure yfinance fallback service — used ONLY when Finnhub fails or for ETFs/non-US symbols.

This module provides the same output shape as finnhub_service but tags every field
with `data_source: "yf"` so the frontend can display a purple "YF" badge.

ETF support: For ETFs that don't provide marketCap/sharesOutstanding/analyst targets,
uses totalAssets/netAssets as market_cap fallback and beta3Year for beta.

Dynamic Security Detection: Uses quoteType metadata from yfinance to classify
securities as STOCK, ETF, INDEX, CRYPTO, ADR, or UNKNOWN.
"""

import logging
from typing import Any, Dict, List, Optional

import yfinance as yf

from backend.lib.error_fallback import create_error_fallback
from backend.lib.risk_metrics import _compute_composite_risk, _safe_pct

logger = logging.getLogger(__name__)


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
        "Etf Etf": "ETF",
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


def _resolve_market_cap(info: Dict[str, Any], is_etf_flag: bool) -> int:
    """Resolve market cap from yfinance info, handling ETF vs stock differences."""
    if is_etf_flag:
        value = info.get("totalAssets") or info.get("netAssets") or 0
    else:
        value = info.get("marketCap") or info.get("nonDilutedMarketCap") or 0
    return int(value) if value else 0


def _resolve_shares_outstanding(info: Dict[str, Any], is_etf_flag: bool) -> int:
    """Resolve shares outstanding, computing from NAV for ETFs when needed."""
    value = info.get("sharesOutstanding") or info.get("impliedSharesOutstanding") or 0
    if not value and is_etf_flag:
        total_assets = info.get("totalAssets") or info.get("netAssets", 0)
        nav_price = info.get("navPrice")
        if total_assets and nav_price and nav_price > 0:
            value = int(total_assets / nav_price)
    return int(value) if value else 0


def _resolve_float_shares(info: Dict[str, Any], shares_outstanding: int, is_etf_flag: bool) -> int:
    """Resolve float shares, using outstanding as fallback for ETFs."""
    value = info.get("floatShares") or 0
    if is_etf_flag and not value:
        value = shares_outstanding
    return int(value) if value else 0


def _resolve_beta(info: Dict[str, Any]) -> float:
    """Resolve beta value, falling back to beta3Year for ETFs."""
    # beta3Year rarely populated; keep as last resort fallback (TD-CQ-006 noted)
    return info.get("beta") or info.get("beta3Year") or 1.0  # type: ignore[return-value]


def _assemble_price_fields(info: Dict[str, Any]) -> Dict[str, Any]:
    """Extract core price + volume fields from yfinance info.
    
    Uses post-market/after-hours prices when available so watchlist stays live after 4pm ET.
    Falls back to regular market prices during trading hours or for ETFs without after-hours data.
    """
    # Prefer postMarketPrice (live after-hours), then currentPrice, then regularMarketPrice
    post_market_price = info.get("postMarketPrice")
    if post_market_price:
        current_price = post_market_price
    else:
        # Prefer post-market price (live after-hours), fall back to regular market price
        current_price = info.get("postMarketPrice") or info.get("currentPrice") or info.get("regularMarketPrice") or 0
    
    previous_close = info.get("previousClose") or info.get("regularMarketPreviousClose") or 0

    change = round(current_price - previous_close, 2) if current_price and previous_close else 0
    change_pct = _safe_pct(
        (current_price - previous_close) if current_price and previous_close else 0,
        previous_close,
    )

    return {
        "current_price": current_price,
        "open_price": info.get("open") or info.get("regularMarketOpen", 0) or 0,
        "previous_close": previous_close,
        "day_low": info.get("dayLow") or info.get("regularMarketDayLow", 0) or 0,
        "day_high": info.get("dayHigh") or info.get("regularMarketDayHigh", 0) or 0,
        "fifty_two_week_high": info.get("fiftyTwoWeekHigh", 0) or 0,
        "fifty_two_week_low": info.get("fiftyTwoWeekLow", 0) or 0,
        "change": change,
        "change_percent": change_pct,
        "volume": int(info.get("regularMarketVolume", 0) or 0),
    }


def _assemble_risk_fields(beta: float, current_price: float, info: Dict[str, Any]) -> Dict[str, Any]:
    """Extract risk + demand signal fields."""
    short_pct = info.get("shortPercentOfFloat") or 0.0
    return {
        "beta": beta,
        "short_percent_of_float": round(short_pct, 4),
        "shares_short": int(info.get("sharesShort", 0) or 0),
        "insider_percent": round(info.get("heldPercentInsiders", 0.0) or 0.0, 4),
        "institution_percent": round(info.get("heldPercentInstitutions", 0.0) or 0.0, 4),
        "overall_risk": _compute_composite_risk(
            beta=beta,
            short_pct_of_float=short_pct,
            debt_eq=info.get("debtToEquity") or 0.0,
            high52=info.get("fiftyTwoWeekHigh") or 0,
            low52=info.get("fiftyTwoWeekLow") or 0,
            current_price=current_price,
        ),
    }


def _assemble_analyst_fields(info: Dict[str, Any]) -> Dict[str, Any]:
    """Extract analyst target and recommendation fields."""
    return {
        "target_mean_price": info.get("targetMeanPrice"),
        "target_median_price": info.get("targetMedianPrice"),
        "target_high_price": info.get("targetHighPrice"),
        "target_low_price": info.get("targetLowPrice"),
        "recommendation_key": info.get("recommendationKey", "N/A") or "N/A",
        "number_of_analysts": info.get("numberOfAnalystOpinions", 0) or 0,
    }


def _extract_ceo_name(ticker_obj: yf.Ticker, info: Dict[str, Any]) -> Optional[str]:
    """Extract CEO name from yfinance.

    NOTE: CEO enrichment via ticker.officers makes a separate HTTP call per ticker
    and adds ~15-20s to batch watchlist loads (22+ tickers × 0.5-1s each).
    Disabled by default to keep API response times fast (~3-5s for full watchlist).
    Re-enable only if you accept the latency trade-off, or move to background task.
    """
    # Fast path: skip the slow ticker.officers HTTP call (TD-CQ fix — CEO enrichment latency)
    return None


def _assemble_company_fields(ticker_obj: yf.Ticker, info: Dict[str, Any]) -> Dict[str, Any]:
    """Extract company profile fields.

    NOTE: ticker_obj is passed but CEO extraction is disabled for performance.
    The parameter is retained for future re-enablement if needed.
    """
    return {
        "company_name": info.get("shortName") or info.get("longName", "N/A"),
        "sector": info.get("sector"),
        "industry": info.get("industry"),
        "long_business_summary": info.get("longBusinessSummary"),
        "website": info.get("website"),
        "full_time_employees": info.get("fullTimeEmployees"),
        "average_analyst_rating": info.get("recommendationKey"),
        "forward_pe": info.get("forwardPE"),
        "ceo_name": None,  # CEO enrichment moved to background (disabled for latency)
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
        "expense_ratio": info.get("expenseRatio"),
        "net_assets": info.get("totalAssets") or info.get("netAssets"),
        "inception_date": _format_date(info.get("fundInceptionDate")),
        "dividend_yield": info.get("dividendYield"),
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
        logger.debug("[YF-ETF] Failed to fetch holdings for %s: %s", ticker_obj.ticker, e)
        etf_data["top_holdings"] = None
    
    # Fetch sector allocation only for ETFs
    try:
        sector_alloc = _get_sector_allocation(info)
        if sector_alloc:
            etf_data["sector_allocation"] = sector_alloc
    except Exception as e:
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
    except Exception:
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
    except Exception:
        pass
    
    # Fallback: try ETF specific holdings attribute
    try:
        info = ticker_obj.info
        if info.get("holdings"):
            raw_holdings = info["holdings"]
            if isinstance(raw_holdings, list):
                return [{"name": str(h), "ticker": "", "weight": 0} for h in raw_holdings[:10]]
    except Exception:
        pass
    
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

def get_stock_price_yf(ticker: str) -> Optional[Dict[str, Any]]:
    """Fetch stock data via yfinance (fallback). Returns None on failure.
    
    Includes dynamic security type detection and lazy ETF data fetching.
    """
    try:
        ticker_obj = yf.Ticker(ticker.upper())
        info = ticker_obj.info
        if not info:
            logger.warning("[YF-Fallback] No info for %s", ticker)
            return None

        security_type = _detect_security_type(info)
        etf = _is_etf(info)
        # Prefer post-market price for after-hours trading, fall back to regular market price
        current_price = info.get("postMarketPrice") or info.get("currentPrice") or info.get("regularMarketPrice") or 0
        beta = _resolve_beta(info)

        # Build result by composing helpers
        result: Dict[str, Any] = {
            "ticker": ticker.upper(),
            "symbol": ticker.upper(),
            "data_source": "yf",
            "security_type": security_type,
        }
        result.update(_assemble_company_fields(ticker_obj, info))
        result.update(_assemble_price_fields(info))
        result["market_cap"] = _resolve_market_cap(info, etf)
        
        # Only include share structure for STOCKs
        if security_type == "STOCK":
            result["shares_outstanding"] = _resolve_shares_outstanding(info, etf)
            result["float_shares"] = _resolve_float_shares(
                info, result.get("shares_outstanding", 0), etf
            )
        
        # Only include stock-specific risk fields for STOCKs
        if security_type == "STOCK":
            result.update(_assemble_risk_fields(beta, current_price, info))
        
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
        
        return result
    except Exception as e:
        logger.error("[YF-Fallback] Failed for %s: %s", ticker, e)
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
