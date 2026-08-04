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

from backend.lib.constants import KNOWN_ETF_NAMES


SECURITY_TYPES = {"STOCK", "ETF", "INDEX", "CRYPTO", "ADR", "UNKNOWN"}
DATA_SOURCES = {"fh", "yf"}

NULLABLE_MEASUREMENT_FIELDS = {
    "current_price", "open_price", "previous_close", "day_low", "day_high",
    "fifty_two_week_high", "fifty_two_week_low", "change", "change_percent",
    "beta", "overall_risk",
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


def _positive_market_size(value: Any) -> float | None:
    """Accept only finite positive provider numbers; reject bools and strings."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    normalized = float(value)
    return normalized if math.isfinite(normalized) and normalized > 0 else None

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

    Legitimate zero remains zero and unavailable measurements remain ``None``.
    """

    ticker_upper = ticker.strip().upper()
    normalized: Dict[str, Any] = dict(payload)

    normalized["ticker"] = _optional_text(payload.get("ticker")) or ticker_upper
    normalized["symbol"] = _optional_text(payload.get("symbol")) or normalized["ticker"]
    normalized["company_name"] = (
        _optional_text(payload.get("company_name")) or normalized["ticker"]
    )

    for field in NULLABLE_MEASUREMENT_FIELDS:
        normalized[field] = _finite_float(payload.get(field), None)

    normalized["market_cap"] = _positive_market_size(payload.get("market_cap"))
    normalized["etf_market_cap"] = _positive_market_size(payload.get("etf_market_cap"))

    for field in OPTIONAL_FLOAT_FIELDS:
        normalized[field] = _finite_float(payload.get(field), None)

    for field in OPTIONAL_INT_FIELDS:
        normalized[field] = _finite_int(payload.get(field), None)

    for field in OPTIONAL_TEXT_FIELDS:
        normalized[field] = _optional_text(payload.get(field))

    normalized["volume"] = _finite_int(payload.get("volume"), None)

    source = str(payload.get("data_source") or default_source).strip().lower()
    normalized["data_source"] = source if source in DATA_SOURCES else default_source

    security_type = str(payload.get("security_type") or "UNKNOWN").strip().upper()
    if security_type == "UNKNOWN" and ticker_upper in KNOWN_ETF_NAMES:
        security_type = "ETF"
    normalized["security_type"] = (
        security_type if security_type in SECURITY_TYPES else "UNKNOWN"
    )
    if normalized["company_name"] == normalized["ticker"] and ticker_upper in KNOWN_ETF_NAMES:
        normalized["company_name"] = KNOWN_ETF_NAMES[ticker_upper]

    recommendation = _optional_text(payload.get("recommendation_key"))
    normalized["recommendation_key"] = (
        None if recommendation and recommendation.casefold() in {"n/a", "none", "null", "unknown", "error"}
        else recommendation
    )

    enriched_fields = payload.get("yf_enriched_fields")
    normalized["yf_enriched_fields"] = (
        [str(field) for field in enriched_fields if str(field).strip()]
        if isinstance(enriched_fields, list)
        else []
    )

    normalized["etf_data"] = _normalize_etf_data(payload.get("etf_data"))
    security_type = normalized["security_type"]
    market_cap = normalized["market_cap"]
    fund_assets = _positive_market_size(payload.get("fund_assets"))
    if security_type == "ETF":
        etf_data = normalized["etf_data"] or {}
        fund_assets = fund_assets or _positive_market_size(etf_data.get("net_assets"))
        etf_market_cap = normalized["etf_market_cap"] or market_cap
        normalized["market_cap"] = None
        normalized["fund_assets"] = fund_assets
        normalized["etf_market_cap"] = etf_market_cap
        normalized["market_size_value"] = fund_assets or etf_market_cap
        normalized["market_size_type"] = (
            "fund_assets" if fund_assets else "etf_market_cap" if etf_market_cap else None
        )
    else:
        normalized["etf_market_cap"] = None
        normalized["fund_assets"] = fund_assets
        normalized["market_size_value"] = market_cap
        normalized["market_size_type"] = "market_cap" if market_cap is not None else None
    currency = _optional_text(payload.get("market_size_currency") or payload.get("currency"))
    normalized["market_size_currency"] = currency.upper() if currency else None
    status = _optional_text(payload.get("market_size_status"))
    valid_statuses = {"available", "unsupported", "provider_failed", "rate_limited", "unauthorized", "stale_cache"}
    if normalized["market_size_value"] is not None:
        normalized["market_size_status"] = "stale_cache" if status == "stale_cache" else "available"
    else:
        normalized["market_size_status"] = status if status in valid_statuses else "unsupported"
    normalized["market_size_fallback_used"] = (
        normalized["market_size_type"] == "etf_market_cap"
        if security_type == "ETF"
        else bool(payload.get("market_size_fallback_used"))
    )
    supplied_market_size_type = _optional_text(payload.get("market_size_type"))
    if normalized["market_size_type"] == "fund_assets":
        normalized["market_size_source"] = _optional_text(
            payload.get("fund_assets_source")
            or (
                payload.get("market_size_source")
                if supplied_market_size_type == "fund_assets"
                else None
            )
        )
    elif normalized["market_size_type"] == "etf_market_cap":
        normalized["market_size_source"] = _optional_text(
            payload.get("etf_market_cap_source")
            or (
                payload.get("market_size_source")
                if supplied_market_size_type == "etf_market_cap"
                or _positive_market_size(payload.get("market_cap")) is not None
                else None
            )
        )
    else:
        normalized["market_size_source"] = _optional_text(payload.get("market_size_source"))
    provider_status = payload.get("provider_status")
    normalized["provider_status"] = dict(provider_status) if isinstance(provider_status, Mapping) else {}
    relevant_fields = ["open_price", "previous_close", "day_low", "day_high", "fifty_two_week_low", "fifty_two_week_high"]
    relevant_fields += ["fund_assets"] if security_type == "ETF" else ["market_cap", "beta", "overall_risk"]
    supplied_missing = payload.get("missing_fields")
    normalized["missing_fields"] = (
        sorted({str(field) for field in supplied_missing})
        if isinstance(supplied_missing, list)
        else [field for field in relevant_fields if normalized.get(field) is None]
    )
    requested_status = _optional_text(payload.get("data_status"))
    if requested_status in {"complete", "partial", "stale", "unavailable"}:
        normalized["data_status"] = requested_status
    elif normalized["market_size_status"] == "provider_failed" and normalized["current_price"] is None:
        normalized["data_status"] = "unavailable"
    else:
        normalized["data_status"] = "partial" if normalized["missing_fields"] else "complete"
    return normalized
