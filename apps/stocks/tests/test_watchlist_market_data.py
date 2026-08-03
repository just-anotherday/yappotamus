"""Regression coverage for watchlist provider routing and normalization."""

from __future__ import annotations

import asyncio
import threading
import numpy as np
import pandas as pd
import time

import pytest

from backend.lib.constants import KNOWN_NON_STOCK_SYMBOLS
from backend.lib.market_data_normalization import normalize_market_data_payload
from backend.models.stock import WatchlistItem
from backend.services import hybrid_data_service, yfinance_fallback
from backend.services import finnhub_service
from backend.services.market_data_observability import (
    market_data_correlation,
    normalize_correlation_id,
    run_provider_attempt,
    summarize_normalized_fields,
)


def _stock_payload(ticker: str, *, source: str = "yf") -> dict:
    return normalize_market_data_payload(
        ticker,
        {
            "ticker": ticker,
            "symbol": ticker,
            "company_name": f"{ticker} Corp",
            "current_price": 101,
            "previous_close": 100,
            "change": 1,
            "change_percent": 1,
            "market_cap": 1_000_000,
            "security_type": "STOCK",
            "data_source": source,
        },
        default_source=source,
    )


@pytest.fixture(autouse=True)
def clear_hybrid_cache():
    hybrid_data_service._cache.clear()
    yfinance_fallback._reset_yfinance_cooldown_for_tests()
    yield
    hybrid_data_service._cache.clear()
    yfinance_fallback._reset_yfinance_cooldown_for_tests()


@pytest.mark.parametrize(
    ("exception", "expected_class"),
    [
        (yfinance_fallback.YFRateLimitError(), "yf_rate_limit"),
        (RuntimeError("Too Many Requests"), "rate_limited"),
        (RuntimeError("HTTP 429"), "rate_limited"),
        (RuntimeError("Invalid Crumb"), "invalid_crumb"),
        (RuntimeError("Yahoo unauthorized"), "yahoo_access_denied"),
    ],
)
def test_yfinance_cooldown_opens_for_recognized_outages(
    monkeypatch, caplog, exception, expected_class
):
    now = [100.0]
    monkeypatch.setattr(yfinance_fallback.time, "monotonic", lambda: now[0])

    assert yfinance_fallback._yfinance_cooldown_status() == (False, None)
    with caplog.at_level("WARNING"):
        assert yfinance_fallback._record_yfinance_outage_failure(exception) == expected_class

    assert yfinance_fallback._yfinance_cooldown_status() == (True, expected_class)
    assert "event=yfinance_cooldown_opened" in caplog.text
    assert f"failure_class={expected_class}" in caplog.text
    assert "cooldown_seconds=120" in caplog.text
    assert "crumb=" not in caplog.text
    assert "cookie" not in caplog.text
    assert "http://" not in caplog.text

    now[0] = 219.999
    assert yfinance_fallback._yfinance_cooldown_status()[0] is True
    now[0] = 220.0
    assert yfinance_fallback._yfinance_cooldown_status()[0] is False

    assert yfinance_fallback._record_yfinance_outage_failure(exception) == expected_class
    now[0] = 339.999
    assert yfinance_fallback._yfinance_cooldown_status()[0] is True


def test_cooldown_reset_and_unrecognized_failures_do_not_leak(monkeypatch):
    monkeypatch.setattr(yfinance_fallback.time, "monotonic", lambda: 100.0)

    yfinance_fallback._record_yfinance_outage_failure(yfinance_fallback.YFRateLimitError())
    assert yfinance_fallback._yfinance_cooldown_status()[0] is True
    yfinance_fallback._reset_yfinance_cooldown_for_tests()
    assert yfinance_fallback._yfinance_cooldown_status() == (False, None)

    assert yfinance_fallback._record_yfinance_outage_failure(RuntimeError("ordinary failure")) is None
    assert yfinance_fallback._yfinance_cooldown_status() == (False, None)


@pytest.mark.asyncio
async def test_yfinance_cooldown_skips_optional_enrichment_and_preserves_finnhub(
    monkeypatch, caplog
):
    now = [100.0]
    calls: list[str] = []
    finnhub_market_cap = 2_000_000_000_000
    monkeypatch.setattr(yfinance_fallback.time, "monotonic", lambda: now[0])
    yfinance_fallback._record_yfinance_outage_failure(
        RuntimeError("Invalid Crumb: crumb=secret-cookie")
    )

    async def finnhub_result(ticker):
        calls.append(f"fh:{ticker}")
        return {
            "ticker": ticker,
            "symbol": ticker,
            "company_name": "Amazon.com, Inc.",
            "current_price": 200,
            "market_cap": finnhub_market_cap,
            "market_size_value": finnhub_market_cap,
            "market_size_type": "market_cap",
            "market_size_currency": "USD",
            "market_size_fallback_used": False,
            "market_size_status": "available",
            "long_business_summary": None,
            "security_type": "STOCK",
            "data_source": "fh",
        }

    async def yfinance_enrichment(ticker):
        calls.append(f"yf:{ticker}")
        return {"ticker": ticker, "long_business_summary": "must not be fetched"}

    monkeypatch.setattr(hybrid_data_service, "finnhub_get_stock_price", finnhub_result)
    monkeypatch.setattr(hybrid_data_service, "_yf_async", yfinance_enrichment)

    with caplog.at_level("DEBUG"):
        result = await hybrid_data_service.get_hybrid_stock_price("AMZN")

    assert calls == ["fh:AMZN"]
    assert result["data_source"] == "fh"
    assert result["yf_enriched_fields"] == []
    assert result["market_cap"] == finnhub_market_cap
    assert result["market_size_value"] == finnhub_market_cap
    assert result["market_size_type"] == "market_cap"
    assert result["market_size_currency"] == "USD"
    assert result["market_size_fallback_used"] is False
    assert result["market_size_status"] == "available"
    assert "event=yfinance_cooldown_skip" in caplog.text
    assert "secret-cookie" not in caplog.text


def test_yfinance_primary_cooldown_skips_provider_call(monkeypatch):
    now = [100.0]
    calls: list[str] = []
    monkeypatch.setattr(yfinance_fallback.time, "monotonic", lambda: now[0])
    yfinance_fallback._record_yfinance_outage_failure(yfinance_fallback.YFRateLimitError())

    class FakeTicker:
        def __init__(self, _ticker):
            calls.append("ticker")

    monkeypatch.setattr(yfinance_fallback.yf, "Ticker", FakeTicker)

    assert yfinance_fallback.get_stock_price_yf("SPY") is None
    assert calls == []
    assert yfinance_fallback._yfinance_cooldown_status()[0] is True




def test_complete_etf_data_uses_etf_shape_and_decimal_percentages(monkeypatch):
    class FakeTicker:
        ticker = "SPY"
        holdings = None
        info = {
            "quoteType": "ETF",
            "shortName": "Example ETF",
            "currentPrice": 500,
            "previousClose": 495,
            "open": 496,
            "dayLow": 494,
            "dayHigh": 501,
            "fiftyTwoWeekLow": 400,
            "fiftyTwoWeekHigh": 510,
            "regularMarketVolume": 123,
            "totalAssets": 50_000_000_000,
            "fundFamily": "Example Funds",
            "expenseRatio": 0.09,
            "dividendYield": 1.01,
            "fundInceptionDate": 946684800,
            "category": "Large Blend",
            "exchange": "PCX",
        }

        def __init__(self, _ticker):
            pass

    monkeypatch.setattr(yfinance_fallback, "configure_yfinance_cache", lambda _yf: True)
    monkeypatch.setattr(yfinance_fallback.yf, "Ticker", FakeTicker)
    monkeypatch.setattr(yfinance_fallback.yf, "__version__", "1.5.1")

    result = yfinance_fallback.get_stock_price_yf("SPY")
    item = WatchlistItem.model_validate(result)

    assert item.security_type == "ETF"
    assert item.market_cap is None
    assert item.fund_assets == 50_000_000_000
    assert item.market_size_type == "fund_assets"
    assert item.shares_outstanding is None
    assert item.etf_data is not None
    assert yfinance_fallback._yfinance_cooldown_status() == (False, None)
    assert item.etf_data.expense_ratio == pytest.approx(0.0009)
    assert item.etf_data.dividend_yield == pytest.approx(0.0101)


def test_sparse_etf_metadata_is_serialization_safe(monkeypatch):
    class FakeTicker:
        ticker = "QQQ"
        holdings = None
        info = {
            "quoteType": "ETF",
            "currentPrice": 100,
            "previousClose": 100,
        }

        def __init__(self, _ticker):
            pass

    monkeypatch.setattr(yfinance_fallback, "configure_yfinance_cache", lambda _yf: True)
    monkeypatch.setattr(yfinance_fallback.yf, "Ticker", FakeTicker)

    result = yfinance_fallback.get_stock_price_yf("QQQ")
    item = WatchlistItem.model_validate(result)

    assert item.security_type == "ETF"
    assert item.current_price == 100
    assert item.etf_data is None
    assert item.shares_outstanding is None
    assert item.recommendation_key == "N/A"


@pytest.mark.asyncio
async def test_provider_timeout_falls_back_to_yfinance(monkeypatch, caplog):
    async def slow_finnhub(_ticker):
        await asyncio.sleep(0.05)
        return _stock_payload("AAPL", source="fh")

    async def yfinance_result(_ticker):
        return _stock_payload("AAPL", source="yf")

    monkeypatch.setattr(hybrid_data_service, "finnhub_get_stock_price", slow_finnhub)
    monkeypatch.setattr(hybrid_data_service, "_yf_async", yfinance_result)
    monkeypatch.setattr(hybrid_data_service, "_PROVIDER_TIMEOUT_S", 0.001)

    with caplog.at_level("INFO"):
        result = await hybrid_data_service.get_hybrid_stock_price("AAPL")

    assert result is not None
    assert result["data_source"] == "yf"
    assert "provider=fh success=false timeout=true" in caplog.text
    assert "fallback_provider=yf" in caplog.text


@pytest.mark.asyncio
async def test_partial_provider_response_is_normalized_without_breaking_batch(monkeypatch):
    async def partial_finnhub(_ticker):
        return {
            "ticker": "PART",
            "symbol": "PART",
            "company_name": "",
            "current_price": 10,
            "previous_close": None,
            "beta": float("nan"),
            "data_source": "fh",
        }

    async def no_enrichment(_ticker):
        return None

    monkeypatch.setattr(hybrid_data_service, "finnhub_get_stock_price", partial_finnhub)
    monkeypatch.setattr(hybrid_data_service, "_yf_async", no_enrichment)

    result = await hybrid_data_service.get_hybrid_stock_price("PART")
    item = WatchlistItem.model_validate(result)

    assert item.company_name == "PART"
    assert item.current_price == 10
    assert item.previous_close == 0
    assert item.beta == 1
    assert item.target_mean_price is None


@pytest.mark.asyncio
async def test_finnhub_market_cap_is_preserved_during_yfinance_enrichment(monkeypatch):
    calls: list[str] = []
    finnhub_market_cap = 2_000_000_000_000

    async def finnhub_result(ticker):
        calls.append(f"fh:{ticker}")
        return {
            "ticker": ticker,
            "symbol": ticker,
            "company_name": "Amazon.com, Inc.",
            "current_price": 200,
            "market_cap": finnhub_market_cap,
            "market_size_value": finnhub_market_cap,
            "market_size_type": "market_cap",
            "market_size_currency": "USD",
            "market_size_fallback_used": False,
            "market_size_status": "available",
            "industry": "Internet Retail",
            "long_business_summary": None,
            "security_type": "STOCK",
            "data_source": "fh",
        }

    async def yfinance_enrichment(ticker):
        calls.append(f"yf:{ticker}")
        return {
            "ticker": ticker,
            "market_cap": 1_000_000_000_000,
            "long_business_summary": "Online retail and cloud computing company.",
            "security_type": "STOCK",
            "data_source": "yf",
        }

    monkeypatch.setattr(hybrid_data_service, "finnhub_get_stock_price", finnhub_result)
    monkeypatch.setattr(hybrid_data_service, "_yf_async", yfinance_enrichment)

    result = await hybrid_data_service.get_hybrid_stock_price("AMZN")

    assert calls == ["fh:AMZN", "yf:AMZN"]
    assert result["long_business_summary"] == "Online retail and cloud computing company."
    assert result["market_cap"] == finnhub_market_cap
    assert result["market_cap"] != 1_000_000_000_000
    assert result["market_size_value"] == finnhub_market_cap
    assert result["market_size_type"] == "market_cap"
    assert result["market_size_currency"] == "USD"
    assert result["market_size_fallback_used"] is False
    assert result["market_size_status"] == "available"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("yf_payload", "primary_updates"),
    [
        (None, {}),
        ({}, {}),
        ({"ticker": "AMZN"}, {}),
        (
            {
                "ticker": "AMZN",
                "long_business_summary": None,
                "ceo_name": None,
                "forward_pe": None,
            },
            {},
        ),
        (
            {
                "ticker": "AMZN",
                "company_name": "Unknown",
                "long_business_summary": " N/A ",
                "ceo_name": "null",
            },
            {},
        ),
        ({"ticker": "AMZN", "long_business_summary": "Existing summary"}, {"long_business_summary": "Existing summary"}),
        (
            {
                "ticker": "AMZN",
                "current_price": 0,
                "open_price": 0,
                "volume": 0,
                "forward_pe": 0,
                "beta": 0,
            },
            {},
        ),
        ({"ticker": "AMZN", "market_cap": 1_000_000_000_000}, {}),
    ],
    ids=[
        "none",
        "empty-dict",
        "ticker-only",
        "all-null",
        "placeholder-only",
        "duplicate",
        "zero-filled-quote-shell",
        "market-cap-only",
    ],
)
async def test_unusable_yfinance_enrichment_does_not_count_as_success(
    monkeypatch, caplog, yf_payload, primary_updates
):
    calls: list[str] = []
    finnhub_market_cap = 2_000_000_000_000

    async def finnhub_result(ticker):
        calls.append(f"fh:{ticker}")
        result = {
            "ticker": ticker,
            "symbol": ticker,
            "company_name": ticker,
            "current_price": 200,
            "market_cap": finnhub_market_cap,
            "market_size_value": finnhub_market_cap,
            "market_size_type": "market_cap",
            "market_size_currency": "USD",
            "market_size_fallback_used": False,
            "market_size_status": "available",
            "industry": "Internet Retail",
            "sector": None,
            "long_business_summary": None,
            "ceo_name": None,
            "beta": 2,
            "security_type": "STOCK",
            "data_source": "fh",
        }
        result.update(primary_updates)
        return result

    async def yfinance_enrichment(ticker):
        calls.append(f"yf:{ticker}")
        return yf_payload

    monkeypatch.setattr(hybrid_data_service, "finnhub_get_stock_price", finnhub_result)
    monkeypatch.setattr(hybrid_data_service, "_yf_async", yfinance_enrichment)

    with caplog.at_level("INFO"):
        result = await hybrid_data_service.get_hybrid_stock_price("AMZN")

    assert calls == ["fh:AMZN", "yf:AMZN"]
    assert "provider=yf_enrichment success=false" in caplog.text
    assert result["yf_enriched_fields"] == []
    assert yfinance_fallback._yfinance_cooldown_status() == (False, None)
    assert result["market_cap"] == finnhub_market_cap
    assert result["market_size_value"] == finnhub_market_cap
    assert result["market_size_type"] == "market_cap"
    assert result["market_size_currency"] == "USD"
    assert result["market_size_fallback_used"] is False
    assert result["market_size_status"] == "available"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("yf_payload", "field", "expected_value"),
    [
        (
            {"ticker": "AMZN", "long_business_summary": "Online retail and cloud computing company."},
            "long_business_summary",
            "Online retail and cloud computing company.",
        ),
        (
            {"ticker": "AMZN", "sector": "Consumer Cyclical"},
            "sector",
            "Consumer Cyclical",
        ),
        (
            {
                "ticker": "AMZN",
                "market_cap": 1_000_000_000_000,
                "forward_pe": float("nan"),
                "company_name": "Unknown",
                "long_business_summary": "Online retail and cloud computing company.",
            },
            "long_business_summary",
            "Online retail and cloud computing company.",
        ),
    ],
    ids=["long-business-summary", "sector", "invalid-fields-plus-summary"],
)
async def test_meaningful_yfinance_enrichment_merges_only_valid_fields(
    monkeypatch, yf_payload, field, expected_value
):
    calls: list[str] = []
    finnhub_market_cap = 2_000_000_000_000

    async def finnhub_result(ticker):
        calls.append(f"fh:{ticker}")
        return {
            "ticker": ticker,
            "symbol": ticker,
            "company_name": "Amazon.com, Inc.",
            "current_price": 200,
            "market_cap": finnhub_market_cap,
            "market_size_value": finnhub_market_cap,
            "market_size_type": "market_cap",
            "market_size_currency": "USD",
            "market_size_fallback_used": False,
            "market_size_status": "available",
            "industry": "Internet Retail",
            "sector": None,
            "long_business_summary": None,
            "ceo_name": None,
            "beta": 2,
            "security_type": "STOCK",
            "data_source": "fh",
        }

    async def yfinance_enrichment(ticker):
        calls.append(f"yf:{ticker}")
        return yf_payload

    monkeypatch.setattr(hybrid_data_service, "finnhub_get_stock_price", finnhub_result)
    monkeypatch.setattr(hybrid_data_service, "_yf_async", yfinance_enrichment)

    result = await hybrid_data_service.get_hybrid_stock_price("AMZN")

    assert calls == ["fh:AMZN", "yf:AMZN"]
    assert result[field] == expected_value
    assert result["yf_enriched_fields"] == [field]
    assert result["market_cap"] == finnhub_market_cap
    assert result["market_cap"] != yf_payload.get("market_cap")
    assert result["market_size_value"] == finnhub_market_cap
    assert result["market_size_type"] == "market_cap"
    assert result["market_size_currency"] == "USD"
    assert result["market_size_fallback_used"] is False
    assert result["market_size_status"] == "available"


@pytest.mark.parametrize(
    "field",
    [
        "beta",
        "number_of_analysts",
        "insider_percent",
        "institution_percent",
        "short_percent_of_float",
        "shares_short",
    ],
)
def test_legitimate_zero_enrichment_fields_are_preserved(field):
    merged, enriched_fields = hybrid_data_service._enrich_with_yf(
        {"ticker": "AMZN", field: None, "market_cap": 2_000_000_000_000},
        {field: 0},
    )

    assert merged[field] == 0
    assert enriched_fields == [field]
    assert merged["market_cap"] == 2_000_000_000_000


@pytest.mark.parametrize(
    "field",
    [
        "forward_pe",
        "open_price",
        "previous_close",
        "day_low",
        "day_high",
        "fifty_two_week_high",
        "fifty_two_week_low",
        "volume",
        "shares_outstanding",
        "float_shares",
        "overall_risk",
        "target_mean_price",
        "target_median_price",
        "target_high_price",
        "target_low_price",
        "average_analyst_rating",
        "full_time_employees",
    ],
)
def test_nonmeaningful_zero_values_are_rejected_by_field_policy(field):
    assert hybrid_data_service._normalize_meaningful_enrichment_value(0, field) is None




@pytest.mark.parametrize(
    "value",
    ["Unknown Industries Inc.", "Error Control Systems", "None Such Company"],
)
def test_placeholder_substrings_remain_meaningful(value):
    assert hybrid_data_service._normalize_meaningful_enrichment_value(value, "sector") == value




def test_null_and_zero_are_diagnosed_differently():
    normalized = normalize_market_data_payload(
        "ZERO",
        {
            "ticker": "ZERO",
            "current_price": None,
            "market_cap": 0,
            "target_mean_price": None,
            "number_of_analysts": 0,
        },
        default_source="yf",
    )
    present, missing, zero_fields = summarize_normalized_fields(normalized)

    assert normalized["current_price"] == 0
    assert normalized["market_cap"] is None
    assert normalized["target_mean_price"] is None
    assert "market_cap" in missing
    assert "number_of_analysts" in present
    assert "target_mean_price" in missing
    assert {"current_price", "number_of_analysts"} <= set(zero_fields)


@pytest.mark.asyncio
async def test_stale_cache_used_only_after_provider_failure(monkeypatch, caplog):
    cached = _stock_payload("AAPL", source="fh")
    hybrid_data_service._cache["AAPL"] = (
        cached,
        time.time() - hybrid_data_service._CACHE_TTL - 1,
    )

    async def no_finnhub(_ticker):
        return None

    async def no_yfinance(_ticker):
        return None

    monkeypatch.setattr(hybrid_data_service, "finnhub_get_stock_price", no_finnhub)
    monkeypatch.setattr(hybrid_data_service, "_yf_async", no_yfinance)

    with caplog.at_level("INFO"):
        result = await hybrid_data_service.get_hybrid_stock_price("AAPL")

    assert result is not None
    assert result["current_price"] == 101
    assert "cache_state=stale" in caplog.text
    assert "stale_cache_used=true" in caplog.text


@pytest.mark.asyncio
async def test_spcx_is_stock_candidate_with_yfinance_fallback(monkeypatch):
    calls: list[str] = []

    async def no_finnhub(ticker):
        calls.append(f"fh:{ticker}")
        return None

    async def yfinance_stock(ticker):
        calls.append(f"yf:{ticker}")
        return _stock_payload(ticker, source="yf")

    monkeypatch.setattr(hybrid_data_service, "finnhub_get_stock_price", no_finnhub)
    monkeypatch.setattr(hybrid_data_service, "_yf_async", yfinance_stock)

    result = await hybrid_data_service.get_hybrid_stock_price("SPCX")

    assert "SPCX" not in KNOWN_NON_STOCK_SYMBOLS
    assert calls == ["fh:SPCX", "yf:SPCX"]
    assert result is not None
    assert result["security_type"] == "STOCK"


@pytest.mark.asyncio
async def test_unsupported_symbol_returns_safe_per_symbol_fallback(monkeypatch):
    async def no_finnhub(_ticker):
        return None

    async def no_yfinance(_ticker):
        return None

    monkeypatch.setattr(hybrid_data_service, "finnhub_get_stock_price", no_finnhub)
    monkeypatch.setattr(hybrid_data_service, "_yf_async", no_yfinance)

    [result] = await hybrid_data_service.get_hybrid_batch_prices(["NOPE"])
    item = WatchlistItem.model_validate(result)

    assert item.ticker == "NOPE"
    assert item.company_name == "NOPE"
    assert item.market_size_status == "provider_failed"
    assert item.market_cap is None
    assert item.fund_assets is None
    assert item.current_price == 0
    assert item.security_type == "UNKNOWN"



@pytest.mark.asyncio
async def test_market_data_logs_include_safe_request_correlation(caplog):
    async def provider_result():
        return _stock_payload("AAPL", source="fh")

    with caplog.at_level("INFO"):
        with market_data_correlation("watchlist-refresh-42"):
            result, failure = await run_provider_attempt(
                ticker="AAPL",
                provider="fh",
                timeout_s=1,
                operation=provider_result,
            )

    assert result is not None
    assert failure is None
    assert "correlation_id=watchlist-refresh-42" in caplog.text
    generated = normalize_correlation_id("unsafe\nlog=value")


@pytest.mark.asyncio
async def test_timeout_attempt_keeps_correlation_and_symbol_order(caplog):
    async def provider_timeout():
        raise asyncio.TimeoutError()

    with caplog.at_level("WARNING"):
        with market_data_correlation("request-42"):
            result, failure = await run_provider_attempt(
                ticker="AMD",
                provider="fh",
                timeout_s=1,
                operation=provider_timeout,
            )

    assert result is None
    assert failure == "timeout"
    assert "correlation_id=request-42 symbol=AMD provider=fh success=false timeout=true" in caplog.text
    assert "correlation_id=AMD symbol=request-42" not in caplog.text


@pytest.mark.asyncio
async def test_empty_and_unusable_finnhub_results_are_not_successes(caplog):
    async def empty_provider():
        return {}

    async def unusable_provider():
        return {"current_price": 0}

    with caplog.at_level("INFO"):
        with market_data_correlation("request-43"):
            empty, empty_failure = await run_provider_attempt(
                ticker="EMPTY",
                provider="fh",
                timeout_s=1,
                operation=empty_provider,
            )
            unusable, unusable_failure = await run_provider_attempt(
                ticker="ZERO",
                provider="fh",
                timeout_s=1,
                operation=unusable_provider,
                result_is_usable=hybrid_data_service._has_usable_finnhub_quote,
            )

    assert empty == {}
    assert empty_failure == "empty_response"
    assert unusable == {"current_price": 0}
    assert unusable_failure == "empty_response"
    assert "symbol=EMPTY provider=fh success=false timeout=false" in caplog.text
    assert "symbol=ZERO provider=fh success=false timeout=false" in caplog.text


@pytest.mark.asyncio
async def test_valid_finnhub_result_is_logged_as_success(caplog):
    async def valid_provider():
        return _stock_payload("NVDA", source="fh")

    with caplog.at_level("INFO"):
        with market_data_correlation("request-44"):
            result, failure = await run_provider_attempt(
                ticker="NVDA",
                provider="fh",
                timeout_s=1,
                operation=valid_provider,
                result_is_usable=hybrid_data_service._has_usable_finnhub_quote,
            )

    assert result is not None
    assert failure is None
    assert "correlation_id=request-44 symbol=NVDA provider=fh success=true timeout=false" in caplog.text


@pytest.mark.asyncio
async def test_collection_result_agrees_when_finnhub_quote_is_unusable(monkeypatch, caplog):
    async def unusable_finnhub(_ticker):
        return {"ticker": "NVDA", "current_price": 0, "data_source": "fh"}

    async def no_yfinance(_ticker):
        return None

    monkeypatch.setattr(hybrid_data_service, "finnhub_get_stock_price", unusable_finnhub)
    monkeypatch.setattr(hybrid_data_service, "_yf_async", no_yfinance)

    with caplog.at_level("INFO"):
        with market_data_correlation("request-45"):
            result = await hybrid_data_service.get_hybrid_stock_price("NVDA")

    assert result is None
    assert "symbol=NVDA provider=fh success=false timeout=false" in caplog.text
    assert "event=collection_result correlation_id=request-45 symbol=NVDA" in caplog.text
    assert "selected_provider=fh" in caplog.text
    assert "success=false" in caplog.text


@pytest.mark.asyncio
async def test_late_threaded_quote_result_is_discarded_after_timeout(monkeypatch, caplog):
    quote_started = threading.Event()
    release_quote = threading.Event()
    quote_finished = threading.Event()
    late_continuations = []
    yfinance_calls = []
    monkeypatch.setattr(hybrid_data_service, "_PROVIDER_TIMEOUT_S", 0.01)

    class BlockingClient:
        def quote(self, _ticker):
            quote_started.set()
            assert release_quote.wait(timeout=1)
            quote_finished.set()
            return {"c": 100.0}

    async def delayed_finnhub(_ticker):
        quote = await finnhub_service._do_quote(BlockingClient(), "NVDA")
        late_continuations.append(quote)
        return _stock_payload("NVDA", source="fh")

    async def no_yfinance(_ticker):
        yfinance_calls.append("fallback")
        return None

    monkeypatch.setattr(hybrid_data_service, "finnhub_get_stock_price", delayed_finnhub)
    monkeypatch.setattr(hybrid_data_service, "_yf_async", no_yfinance)

    with caplog.at_level("INFO"):
        with market_data_correlation("late-thread-42"):
            pending = asyncio.create_task(hybrid_data_service.get_hybrid_stock_price("NVDA"))
            assert await asyncio.wait_for(asyncio.to_thread(quote_started.wait), timeout=1)
            assert await pending is None

    release_quote.set()
    assert await asyncio.wait_for(asyncio.to_thread(quote_finished.wait), timeout=1)
    await asyncio.sleep(0)

    assert late_continuations == []
    assert yfinance_calls == ["fallback"]
    assert hybrid_data_service._cache == {}
    assert "symbol=NVDA provider=fh success=false timeout=true" in caplog.text
    assert "symbol=NVDA provider=fh success=true" not in caplog.text
    assert "event=collection_result correlation_id=late-thread-42 symbol=NVDA" in caplog.text
    assert "selected_provider=fh" in caplog.text
    assert "success=false" in caplog.text
@pytest.mark.parametrize("ticker", ["SPY", "QQQ", "IWM", "DIA"])
def test_etf_assets_are_never_normalized_as_market_cap(ticker):
    normalized = normalize_market_data_payload(
        ticker,
        {"ticker": ticker, "company_name": ticker, "security_type": "ETF", "totalAssets": 1, "fund_assets": 12_000_000_000, "currency": "USD"},
        default_source="yf",
    )
    assert normalized["market_cap"] is None
    assert normalized["fund_assets"] == 12_000_000_000
    assert normalized["market_size_type"] == "fund_assets"
    assert normalized["market_size_status"] == "available"


def test_equity_market_cap_and_currency_are_preserved():
    normalized = normalize_market_data_payload(
        "TSM", {"ticker": "TSM", "security_type": "ADR", "market_cap": 62_890_000_000_000, "currency": "TWD"}, default_source="yf"
    )
    assert normalized["market_size_type"] == "market_cap"
    assert normalized["market_size_currency"] == "TWD"


def test_watchlist_response_serializes_market_cap_contract():
    item = WatchlistItem.model_validate(normalize_market_data_payload(
        "ORI",
        {"ticker": "ORI", "security_type": "STOCK", "market_cap": 10_523_970_132, "currency": "USD"},
        default_source="fh",
    ))

    response = item.model_dump(mode="json")

    assert response["market_cap"] == 10_523_970_132
    assert response["market_size_value"] == 10_523_970_132
    assert response["market_size_type"] == "market_cap"
    assert response["market_size_status"] == "available"


def test_yfinance_market_cap_fills_missing_finnhub_profile_value():
    merged, enriched = hybrid_data_service._enrich_with_yf(
        {"ticker": "ORI", "security_type": "STOCK", "market_cap": 0},
        {"ticker": "ORI", "security_type": "STOCK", "market_cap": 10_523_970_132},
    )

    assert merged["market_cap"] == 10_523_970_132
    assert "market_cap" in enriched


def test_equity_price_times_shares_fallback_is_not_used_for_etfs():
    assert yfinance_fallback._resolve_market_cap({"sharesOutstanding": 10, "currency": "USD"}, "STOCK", 5) == (50, True)
    assert yfinance_fallback._resolve_market_cap({"sharesOutstanding": 10, "currency": "USD"}, "ETF", 5) == (None, False)


def test_provider_failure_is_distinct_from_unsupported_market_size():
    failed = normalize_market_data_payload("NOPE", hybrid_data_service.create_error_fallback("NOPE"), default_source="yf")
    unsupported = normalize_market_data_payload("NONE", {"ticker": "NONE", "security_type": "ETF"}, default_source="yf")
    assert failed["market_size_status"] == "provider_failed"
    assert unsupported["market_size_status"] == "unsupported"
@pytest.mark.asyncio
async def test_provider_failure_preserves_cached_market_size_identity(monkeypatch):
    previous = [
        WatchlistItem(ticker="SPY", symbol="SPY", company_name="SPDR", security_type="ETF", market_cap=None,
                      fund_assets=100, market_size_value=100, market_size_type="fund_assets",
                      market_size_currency="USD", market_size_status="available"),
        WatchlistItem(ticker="AAPL", symbol="AAPL", company_name="Apple", security_type="STOCK", market_cap=200,
                      market_size_value=200, market_size_type="market_cap", market_size_currency="USD",
                      market_size_status="available"),
    ]
    failure = normalize_market_data_payload("SPY", hybrid_data_service.create_error_fallback("SPY"), default_source="yf")
    assert failure["market_size_status"] == "provider_failed"
    assert previous[0].fund_assets == 100
    assert previous[1].market_cap == 200


def test_strict_market_size_inputs_reject_bools_strings_and_non_finite_values():
    for value in (True, False, "12", "", float("nan"), float("inf"), -1, 0):
        assert yfinance_fallback._positive_market_number(value) is None


def test_tsm_direct_provider_market_cap_never_uses_calculated_fallback():
    cap, fallback = yfinance_fallback._resolve_market_cap(
        {"marketCap": 2_090_000_000_000, "sharesOutstanding": 99, "currency": "USD"}, "ADR", 10
    )
    assert cap == 2_090_000_000_000
    assert fallback is False

@pytest.mark.parametrize("field", ["totalAssets", "netAssets", "fundTotalAssets"])
def test_etf_info_asset_fields_and_names_are_supported(monkeypatch, field):
    class FakeTicker:
        ticker = "SPY"
        holdings = None
        info = {"quoteType": "ETF", "longName": "Long Fund", "shortName": "Short Fund", "currentPrice": 1, field: np.int64(500)}
        def __init__(self, _ticker): pass
    monkeypatch.setattr(yfinance_fallback, "configure_yfinance_cache", lambda _yf: True)
    monkeypatch.setattr(yfinance_fallback.yf, "Ticker", FakeTicker)
    item = WatchlistItem.model_validate(yfinance_fallback.get_stock_price_yf("SPY"))
    assert item.company_name == "Long Fund"
    assert item.market_cap is None
    assert item.fund_assets == 500
    assert item.market_size_currency is None


def test_fund_operations_uses_row_then_ticker_column_and_keeps_currency_unknown(monkeypatch):
    class FakeTicker:
        ticker = "DIA"
        holdings = None
        info = {"quoteType": "ETF", "currentPrice": 1, "currency": "USD"}
        def __init__(self, _ticker):
            self.funds_data = type("Funds", (), {"fund_operations": pd.DataFrame({"DIA": [np.float64(700)], "Category Average": [1]}, index=["Total Net Assets"])})()
    monkeypatch.setattr(yfinance_fallback, "configure_yfinance_cache", lambda _yf: True)
    monkeypatch.setattr(yfinance_fallback.yf, "Ticker", FakeTicker)
    item = WatchlistItem.model_validate(yfinance_fallback.get_stock_price_yf("DIA"))
    assert (item.market_cap, item.fund_assets, item.market_size_value, item.market_size_currency) == (None, 700, 700, None)


def test_fund_metadata_errors_and_invalid_values_are_non_fatal(monkeypatch):
    class FakeTicker:
        ticker = "QQQ"
        holdings = None
        info = {"quoteType": "ETF", "currentPrice": 1}

        def __init__(self, _ticker):
            pass

        @property
        def funds_data(self):
            raise RuntimeError("provider unavailable")

    monkeypatch.setattr(yfinance_fallback, "configure_yfinance_cache", lambda _yf: True)
    monkeypatch.setattr(yfinance_fallback.yf, "Ticker", FakeTicker)
    item = WatchlistItem.model_validate(yfinance_fallback.get_stock_price_yf("QQQ"))
    assert item.company_name == "QQQ"
    assert item.market_size_status == "unsupported"
    for value in (True, "1", 0, -1, np.nan, np.inf):
        assert yfinance_fallback._positive_market_number(value) is None


def test_adr_calculated_market_cap_remains_disabled():
    assert yfinance_fallback._resolve_market_cap(
        {"sharesOutstanding": 99, "currency": "USD"}, "ADR", 10
    ) == (None, False)
