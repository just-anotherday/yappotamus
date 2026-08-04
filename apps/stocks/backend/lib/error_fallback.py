# lib/error_fallback.py
"""Shared error fallback factory for market data responses."""

from typing import Any, Dict

from backend.lib.constants import KNOWN_ETF_NAMES


def create_error_fallback(ticker: str, data_source: str = "fh") -> Dict[str, Any]:
    """Return a minimal fallback dict when ticker data fails."""
    ticker_upper = ticker.upper()
    is_known_etf = ticker_upper in KNOWN_ETF_NAMES
    return {
        "ticker": ticker_upper,
        "symbol": ticker_upper,
        "company_name": KNOWN_ETF_NAMES.get(ticker_upper, ticker_upper),
        "sector": None,
        "industry": None,
        "long_business_summary": None,
        "website": None,
        "full_time_employees": None,
        "average_analyst_rating": None,
        "forward_pe": None,
        "ceo_name": None,
        "exchange": None,
        "current_price": None,
        "open_price": None,
        "previous_close": None,
        "day_low": None,
        "day_high": None,
        "fifty_two_week_high": None,
        "fifty_two_week_low": None,
        "change": None,
        "change_percent": None,
        "market_cap": None,
        "fund_assets": None,
        "market_size_value": None,
        "market_size_type": "fund_assets" if is_known_etf else None,
        "market_size_currency": None,
        "market_size_fallback_used": False,
        "market_size_status": "provider_failed",
        "security_type": "ETF" if is_known_etf else "UNKNOWN",
        "shares_outstanding": None,
        "float_shares": None,
        "insider_percent": None,
        "institution_percent": None,
        "beta": None,
        "short_percent_of_float": None,
        "shares_short": None,
        "overall_risk": None,
        "target_mean_price": None,
        "target_median_price": None,
        "target_high_price": None,
        "target_low_price": None,
        "recommendation_key": None,
        "number_of_analysts": None,
        "data_source": data_source,
        "data_status": "unavailable",
        "provider_status": {
            "finnhub": "unavailable" if data_source == "fh" else "degraded",
            "yfinance": "unavailable" if data_source == "yf" else "degraded",
        },
        "missing_fields": [
            "current_price", "open_price", "previous_close", "day_low", "day_high",
            "fifty_two_week_low", "fifty_two_week_high", "beta", "overall_risk",
            "fund_assets" if is_known_etf else "market_cap",
        ],
    }
