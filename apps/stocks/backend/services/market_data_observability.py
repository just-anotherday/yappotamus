"""Structured, value-free observability for watchlist market-data collection."""

from __future__ import annotations

import asyncio
import contextvars
import logging
import re
import time
import uuid
from collections.abc import Awaitable, Callable, Mapping
from contextlib import contextmanager
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")
_CORRELATION_ID = contextvars.ContextVar(
    "market_data_correlation_id",
    default="none",
)
_SAFE_CORRELATION_ID = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")


def normalize_correlation_id(value: str | None) -> str:
    """Use a log-safe caller ID or generate a new opaque request ID."""

    candidate = (value or "").strip()
    if candidate and _SAFE_CORRELATION_ID.fullmatch(candidate):
        return candidate
    return uuid.uuid4().hex


def current_correlation_id() -> str:
    return _CORRELATION_ID.get()


@contextmanager
def market_data_correlation(correlation_id: str):
    """Scope market-data logs to one request or refresh operation."""

    token = _CORRELATION_ID.set(correlation_id)
    try:
        yield correlation_id
    finally:
        _CORRELATION_ID.reset(token)

# Public fields consumed by collapsed rows, expanded details, tooltips, and
# market-data reference seeding.  Logs contain field names only, never values.
WATCHLIST_DIAGNOSTIC_FIELDS = (
    "ticker",
    "symbol",
    "company_name",
    "sector",
    "industry",
    "long_business_summary",
    "website",
    "full_time_employees",
    "average_analyst_rating",
    "forward_pe",
    "ceo_name",
    "exchange",
    "security_type",
    "current_price",
    "open_price",
    "previous_close",
    "day_low",
    "day_high",
    "fifty_two_week_high",
    "fifty_two_week_low",
    "change",
    "change_percent",
    "market_cap",
    "volume",
    "shares_outstanding",
    "float_shares",
    "insider_percent",
    "institution_percent",
    "beta",
    "short_percent_of_float",
    "shares_short",
    "overall_risk",
    "target_mean_price",
    "target_median_price",
    "target_high_price",
    "target_low_price",
    "recommendation_key",
    "number_of_analysts",
    "etf_data",
    "post_market_price",
    "post_market_change",
    "post_market_change_percent",
    "data_source",
    "yf_enriched_fields",
)


def summarize_normalized_fields(
    payload: Mapping[str, Any] | None,
) -> tuple[list[str], list[str], list[str]]:
    """Return present, missing, and explicit-zero field names.

    Zero is considered present.  ``None``, absent keys, and empty strings are
    missing.  Empty collections are present because an empty enrichment list is
    a valid normalized result.
    """

    present: list[str] = []
    missing: list[str] = []
    zero_fields: list[str] = []
    data = payload or {}

    for field in WATCHLIST_DIAGNOSTIC_FIELDS:
        value = data.get(field)
        is_missing = field not in data or value is None
        if isinstance(value, str) and not value.strip():
            is_missing = True

        if is_missing:
            missing.append(field)
        else:
            present.append(field)
            if isinstance(value, (int, float)) and not isinstance(value, bool) and value == 0:
                zero_fields.append(field)

    return present, missing, zero_fields


async def run_provider_attempt(
    *,
    ticker: str,
    provider: str,
    timeout_s: float,
    operation: Callable[[], Awaitable[T]],
) -> tuple[T | None, str | None]:
    """Execute one provider attempt with timeout and structured diagnostics."""

    started = time.monotonic()
    try:
        result = await asyncio.wait_for(operation(), timeout=timeout_s)
    except asyncio.TimeoutError:
        logger.warning(
            "[MarketData] event=provider_attempt correlation_id=%s symbol=%s provider=%s "
            "success=false timeout=true duration_ms=%.1f",
            ticker,
            current_correlation_id(),
            provider,
            (time.monotonic() - started) * 1000,
        )
        return None, "timeout"
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.warning(
            "[MarketData] event=provider_attempt correlation_id=%s symbol=%s provider=%s "
            "success=false timeout=false exception_type=%s duration_ms=%.1f",
            current_correlation_id(),
            ticker,
            provider,
            type(exc).__name__,
            (time.monotonic() - started) * 1000,
        )
        return None, type(exc).__name__

    success = result is not None
    logger.info(
        "[MarketData] event=provider_attempt correlation_id=%s symbol=%s provider=%s "
        "success=%s timeout=false duration_ms=%.1f",
        current_correlation_id(),
        ticker,
        provider,
        str(success).lower(),
        (time.monotonic() - started) * 1000,
    )
    return result, None if success else "empty_response"


def log_collection_result(
    *,
    ticker: str,
    selected_provider: str,
    fallback_provider: str | None,
    started: float,
    payload: Mapping[str, Any] | None,
    cache_state: str,
    failure_reason: str | None,
) -> None:
    """Log one value-free final collection result for a symbol."""

    present, missing, zero_fields = summarize_normalized_fields(payload)
    logger.info(
        "[MarketData] event=collection_result correlation_id=%s symbol=%s selected_provider=%s "
        "fallback_provider=%s success=%s duration_ms=%.1f cache_state=%s "
        "stale_cache_used=%s failure_reason=%s normalized_fields_present=%s "
        "normalized_fields_missing=%s normalized_zero_fields=%s",
        current_correlation_id(),
        ticker,
        selected_provider,
        fallback_provider or "none",
        str(payload is not None).lower(),
        (time.monotonic() - started) * 1000,
        cache_state,
        str(cache_state == "stale").lower(),
        failure_reason or "none",
        ",".join(present) or "none",
        ",".join(missing) or "none",
        ",".join(zero_fields) or "none",
    )
