"""Normalize provider payloads into the public watchlist contract.

Provider APIs occasionally return ``None``, empty strings, booleans, numpy
numbers, or non-finite floats for otherwise numeric fields.  Keeping this
normalization outside the provider adapters prevents one malformed symbol from
breaking serialization of the complete watchlist response.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any, Dict


SECURITY_TYPES = {"STOCK", "ETF", "INDEX", "CRYPTO", "ADR", "UNKNOWN"}
DATA_SOURCES = {"fh", "yf"}

REQUIRED_NUMERIC_DEFAULTS: Dict[str, float] = {
    "current_price": 0.0,
    "open_price": 0.0,
    "previous_close": 0.0,
    "day_low": 0.0,
    "day_high": 0.0,
    "fifty_two_week_high": 0.0,
    "fifty_two_week_low": 0.0,
    "change": 0.0,
    "change_percent": 0.0,
    "market_cap": 0.0,
    "beta": 1.0,
    "overall_risk": 5.0,
}

OPTIONAL_FLOAT_FIELDS = {
    "forward_pe",
    "insider_percent",
    "institution_percent",
    "short_percent_of_float",
    "target_mean_price",
    "target_median_price",
    "target_high_price",
    "target_low_price",
    "post_market_price",
    "post_market_change",
    "post_market_change_percent",
}

OPTIONAL_INT_FIELDS = {
    "full_time_employees",
    "shares_outstanding",
    "float_shares",
    "shares_short",
    "number_of_analysts",
}

OPTIONAL_TEXT_FIELDS = {
    "sector",
    "industry",
    "long_business_summary",
    "website",
    "average_analyst_rating",
    "ceo_name",
    "exchange",
}

ETF_FLOAT_FIELDS = {"expense_ratio", "dividend_yield"}
ETF_INT_FIELDS = {"net_assets", "holdings_count"}
ETF_TEXT_FIELDS = {
    "fund_family",
    "inception_date",
    "distribution_frequency",
    "index_tracked",
    "category",
}


def _finite_float(value: Any, default: float | None) -> float | None:
    if isinstance(value, bool):
        return default
    try:
        normalized = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return normalized if math.isfinite(normalized) else default


def _finite_int(value: Any, default: int | None) -> int | None:
    normalized = _finite_float(value, None)
    return int(normalized) if normalized is not None else default


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _normalize_etf_data(value: Any) -> Dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None

    normalized: Dict[str, Any] = dict(value)
    for field in ETF_FLOAT_FIELDS:
        normalized[field] = _finite_float(value.get(field), None)
    for field in ETF_INT_FIELDS:
        normalized[field] = _finite_int(value.get(field), None)
    for field in ETF_TEXT_FIELDS:
        normalized[field] = _optional_text(value.get(field))

    for collection_field in (
        "top_holdings",
        "sector_allocation",
        "geographic_allocation",
    ):
        collection = value.get(collection_field)
        normalized[collection_field] = collection if isinstance(collection, list) else None

    return normalized


def normalize_market_data_payload(
    ticker: str,
    payload: Mapping[str, Any],
    *,
    default_source: str,
) -> Dict[str, Any]:
    """Return a finite, serialization-safe watchlist payload.

    Zero remains zero and optional ``None`` remains ``None``.  Only required
    numeric fields use defaults because the public response model requires
    numbers for those fields.
    """

    ticker_upper = ticker.strip().upper()
    normalized: Dict[str, Any] = dict(payload)

    normalized["ticker"] = _optional_text(payload.get("ticker")) or ticker_upper
    normalized["symbol"] = _optional_text(payload.get("symbol")) or normalized["ticker"]
    normalized["company_name"] = (
        _optional_text(payload.get("company_name")) or normalized["ticker"]
    )

    for field, default in REQUIRED_NUMERIC_DEFAULTS.items():
        normalized[field] = _finite_float(payload.get(field), default)

    for field in OPTIONAL_FLOAT_FIELDS:
        normalized[field] = _finite_float(payload.get(field), None)

    for field in OPTIONAL_INT_FIELDS:
        normalized[field] = _finite_int(payload.get(field), None)

    for field in OPTIONAL_TEXT_FIELDS:
        normalized[field] = _optional_text(payload.get(field))

    normalized["volume"] = _finite_int(payload.get("volume"), 0) or 0

    source = str(payload.get("data_source") or default_source).strip().lower()
    normalized["data_source"] = source if source in DATA_SOURCES else default_source

    security_type = str(payload.get("security_type") or "UNKNOWN").strip().upper()
    normalized["security_type"] = (
        security_type if security_type in SECURITY_TYPES else "UNKNOWN"
    )

    recommendation = _optional_text(payload.get("recommendation_key"))
    normalized["recommendation_key"] = recommendation or "N/A"

    enriched_fields = payload.get("yf_enriched_fields")
    normalized["yf_enriched_fields"] = (
        [str(field) for field in enriched_fields if str(field).strip()]
        if isinstance(enriched_fields, list)
        else []
    )

    normalized["etf_data"] = _normalize_etf_data(payload.get("etf_data"))
    return normalized
