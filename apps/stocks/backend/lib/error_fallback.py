# lib/error_fallback.py
"""Shared error fallback factory for market data responses."""

from typing import Any, Dict


def create_error_fallback(ticker: str, data_source: str = "fh") -> Dict[str, Any]:
    """Return a minimal fallback dict when ticker data fails."""
    return {
        "ticker": ticker.upper(),
        "symbol": ticker.upper(),
        "company_name": "Error",
        "sector": None,
        "industry": None,
        "long_business_summary": None,
        "website": None,
        "full_time_employees": None,
        "average_analyst_rating": None,
        "forward_pe": None,
        "ceo_name": None,
        "exchange": None,
        "current_price": 0,
        "open_price": 0,
        "previous_close": 0,
        "day_low": 0,
        "day_high": 0,
        "fifty_two_week_high": 0,
        "fifty_two_week_low": 0,
        "change": 0,
        "change_percent": 0,
        "market_cap": 0,
        "shares_outstanding": 0,
        "float_shares": 0,
        "insider_percent": 0.0,
        "institution_percent": 0.0,
        "beta": 9.9,
        "short_percent_of_float": 0.0,
        "shares_short": 0,
        "overall_risk": 5,
        "target_mean_price": None,
        "target_median_price": None,
        "target_high_price": None,
        "target_low_price": None,
        "recommendation_key": "error",
        "number_of_analysts": 0,
        "data_source": data_source,
    }
