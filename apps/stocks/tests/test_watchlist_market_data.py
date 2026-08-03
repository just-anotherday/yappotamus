"""Regression coverage for watchlist provider routing and normalization."""

from __future__ import annotations

import asyncio
import time

import pytest

from backend.lib.constants import KNOWN_NON_STOCK_SYMBOLS
from backend.lib.market_data_normalization import normalize_market_data_payload
from backend.models.stock import WatchlistItem
from backend.services import hybrid_data_service, yfinance_fallback
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
    yield
    hybrid_data_service._cache.clear()


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
    assert yfinance_fallback._resolve_market_cap({"sharesOutstanding": 99, "currency": "USD"}, "ADR", 10) == (None, False)