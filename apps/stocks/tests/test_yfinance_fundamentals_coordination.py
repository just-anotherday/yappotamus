import asyncio
import threading
import time

import pandas as pd
import pytest

from backend.services import hybrid_data_service, yfinance_fallback


@pytest.fixture(autouse=True)
async def reset_provider_state(monkeypatch):
    yfinance_fallback._reset_yfinance_cooldown_for_tests()
    hybrid_data_service._cache.clear()
    hybrid_data_service._refresh_retry_after.clear()
    yield
    await hybrid_data_service.shutdown_hybrid_data_service()
    yfinance_fallback._reset_yfinance_cooldown_for_tests()
    hybrid_data_service._cache.clear()
    hybrid_data_service._refresh_retry_after.clear()


@pytest.mark.parametrize(
    ("exception", "expected"),
    [
        (yfinance_fallback.YFRateLimitError(), "rate_limit"),
        (RuntimeError("Invalid Crumb"), "invalid_crumb"),
        (RuntimeError("HTTP 401 Unauthorized"), "unauthorized"),
        (TimeoutError("timed out"), "timeout"),
        (ConnectionError("connection reset"), "transport_error"),
        (ValueError("JSON decode failed"), "parse_error"),
        (RuntimeError("empty response"), "empty_response"),
        (RuntimeError("unsupported field"), "unsupported_field"),
    ],
)
def test_failure_classification_is_stable(exception, expected):
    assert yfinance_fallback._classify_yfinance_outage(exception) == expected


def test_half_open_allows_exactly_one_probe(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(yfinance_fallback.time, "monotonic", lambda: now[0])
    yfinance_fallback._record_yfinance_outage_failure(RuntimeError("Invalid Crumb"))

    now[0] = 220.0
    assert yfinance_fallback._begin_yfinance_fundamentals_attempt() == (
        True, "invalid_crumb", True,
    )
    assert yfinance_fallback._begin_yfinance_fundamentals_attempt() == (
        False, "cooldown_open", False,
    )

    yfinance_fallback._complete_yfinance_fundamentals_attempt(probe=True, succeeded=True)
    assert yfinance_fallback._begin_yfinance_fundamentals_attempt() == (True, None, False)


def test_failed_half_open_probe_reopens_cooldown(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(yfinance_fallback.time, "monotonic", lambda: now[0])
    yfinance_fallback._record_yfinance_outage_failure(RuntimeError("Invalid Crumb"))
    now[0] = 220.0
    allowed, _, probe = yfinance_fallback._begin_yfinance_fundamentals_attempt()

    yfinance_fallback._complete_yfinance_fundamentals_attempt(probe=probe, succeeded=False)

    assert allowed is True
    assert yfinance_fallback._yfinance_cooldown_status() == (True, "invalid_crumb")


@pytest.mark.asyncio
async def test_fundamentals_calls_are_serialized_across_symbols(monkeypatch):
    state_lock = threading.Lock()
    active = 0
    max_active = 0

    def fake_sync(ticker):
        nonlocal active, max_active
        with state_lock:
            active += 1
            max_active = max(max_active, active)
        time.sleep(0.03)
        with state_lock:
            active -= 1
        return {"ticker": ticker, "current_price": 1}

    monkeypatch.setattr(hybrid_data_service, "_yf_sync", fake_sync)
    first, second = await asyncio.gather(
        hybrid_data_service._yf_singleflight("AAA"),
        hybrid_data_service._yf_singleflight("BBB"),
    )

    assert first["ticker"] == "AAA"
    assert second["ticker"] == "BBB"
    assert max_active == 1


@pytest.mark.asyncio
async def test_waiter_rechecks_cooldown_after_gate_acquisition(monkeypatch):
    started = threading.Event()
    release = threading.Event()
    calls = []

    def fake_sync(ticker):
        calls.append(ticker)
        if ticker == "AAA":
            started.set()
            assert release.wait(timeout=1)
            yfinance_fallback._record_yfinance_outage_failure(RuntimeError("Invalid Crumb"))
            return None
        return {"ticker": ticker, "current_price": 1}

    monkeypatch.setattr(hybrid_data_service, "_yf_sync", fake_sync)
    first = asyncio.create_task(hybrid_data_service._yf_singleflight("AAA"))
    assert await asyncio.to_thread(started.wait, 0.5)
    waiting = asyncio.create_task(hybrid_data_service._yf_singleflight("BBB"))
    release.set()

    assert await first is None
    assert await waiting is None
    assert calls == ["AAA"]


@pytest.mark.asyncio
async def test_same_symbol_singleflight_survives_waiter_cancellation(monkeypatch):
    started = asyncio.Event()
    release = asyncio.Event()
    calls = 0

    async def fake_yf(ticker):
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()
        return {"ticker": ticker, "current_price": 1}

    monkeypatch.setattr(hybrid_data_service, "_yf_async", fake_yf)
    cancelled_waiter = asyncio.create_task(hybrid_data_service._yf_singleflight("spy"))
    await started.wait()
    surviving_waiter = asyncio.create_task(hybrid_data_service._yf_singleflight("SPY"))
    cancelled_waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await cancelled_waiter
    release.set()

    assert await surviving_waiter == {"ticker": "SPY", "current_price": 1}
    assert calls == 1
    await asyncio.sleep(0)
    assert "SPY" not in hybrid_data_service._yfinance_flights


@pytest.mark.asyncio
async def test_singleflight_registry_cleans_up_after_failure(monkeypatch):
    async def failing_yf(_ticker):
        raise RuntimeError("transport failed")

    monkeypatch.setattr(hybrid_data_service, "_yf_async", failing_yf)
    with pytest.raises(RuntimeError, match="transport failed"):
        await hybrid_data_service._yf_singleflight("AAPL")
    await asyncio.sleep(0)

    assert "AAPL" not in hybrid_data_service._yfinance_flights


@pytest.mark.asyncio
async def test_cancelled_half_open_probe_reopens_cooldown_and_cleans_registry(monkeypatch):
    now = [100.0]
    started = threading.Event()
    release = threading.Event()
    monkeypatch.setattr(yfinance_fallback.time, "monotonic", lambda: now[0])
    yfinance_fallback._record_yfinance_outage_failure(RuntimeError("Invalid Crumb"))
    now[0] = 220.0

    def fake_sync(_ticker):
        started.set()
        release.wait(timeout=1)
        return {"ticker": "AAPL", "current_price": 1}

    monkeypatch.setattr(hybrid_data_service, "_yf_sync", fake_sync)
    waiter = asyncio.create_task(hybrid_data_service._yf_singleflight("AAPL"))
    assert await asyncio.to_thread(started.wait, 0.5)
    flight = hybrid_data_service._yfinance_flights["AAPL"]
    flight.cancel()
    release.set()

    with pytest.raises(asyncio.CancelledError):
        await waiter
    await asyncio.sleep(0)

    assert "AAPL" not in hybrid_data_service._yfinance_flights
    assert yfinance_fallback._yfinance_cooldown_status() == (True, "invalid_crumb")


def test_no_private_yfinance_cookie_or_crumb_reset_exists():
    assert not hasattr(yfinance_fallback, "_invalidate_yfinance_crumb")


def test_rate_limit_is_not_retried(monkeypatch):
    calls = 0

    class FakeTicker:
        def __init__(self, _ticker):
            pass

        @property
        def info(self):
            nonlocal calls
            calls += 1
            raise yfinance_fallback.YFRateLimitError()

    monkeypatch.setattr(yfinance_fallback, "configure_yfinance_cache", lambda _yf: True)
    monkeypatch.setattr(yfinance_fallback.yf, "Ticker", FakeTicker)

    assert yfinance_fallback.get_stock_price_yf("AAPL") is None
    assert calls == 1
    assert yfinance_fallback._yfinance_cooldown_status()[0] is True


def test_fast_info_recovers_when_info_transport_fails(monkeypatch):
    class FakeTicker:
        ticker = "AAPL"

        def __init__(self, _ticker):
            pass

        @property
        def info(self):
            raise TimeoutError("metadata timeout")

        fast_info = {
            "last_price": 101,
            "previous_close": 100,
            "year_high": 120,
            "year_low": 80,
            "last_volume": 1234,
        }

        def history(self, **_kwargs):
            raise AssertionError("history should not run after fast_info fills range and volume")

    monkeypatch.setattr(yfinance_fallback, "configure_yfinance_cache", lambda _yf: True)
    monkeypatch.setattr(yfinance_fallback.yf, "Ticker", FakeTicker)

    result = yfinance_fallback.get_stock_price_yf("AAPL")

    assert result["current_price"] == 101
    assert result["fifty_two_week_high"] == 120
    assert result["fifty_two_week_low"] == 80
    assert result["volume"] == 1234
    assert yfinance_fallback._yfinance_cooldown_status() == (False, None)


def test_history_is_bounded_and_only_fills_remaining_range_gaps(monkeypatch):
    history_calls = []

    class FakeTicker:
        ticker = "AAPL"
        info = {}
        fast_info = {"last_price": 101, "previous_close": 100}

        def __init__(self, _ticker):
            pass

        def history(self, **kwargs):
            history_calls.append(kwargs)
            return pd.DataFrame({"High": [110.0, 120.0], "Low": [90.0, 80.0], "Volume": [10, 20]})

    monkeypatch.setattr(yfinance_fallback, "configure_yfinance_cache", lambda _yf: True)
    monkeypatch.setattr(yfinance_fallback.yf, "Ticker", FakeTicker)

    result = yfinance_fallback.get_stock_price_yf("AAPL")

    assert result["fifty_two_week_high"] == 120
    assert result["fifty_two_week_low"] == 80
    assert result["volume"] == 20
    assert history_calls == [{"period": "1y", "auto_adjust": True, "keepna": True, "timeout": 10}]


def test_fast_info_recomputes_change_after_info_failure(monkeypatch):
    class FakeTicker:
        ticker = "AAPL"
        info = {}
        fast_info = {
            "last_price": 101, "previous_close": 100,
            "year_high": 120, "year_low": 80, "last_volume": 1234,
        }

        def __init__(self, _ticker):
            pass

        def history(self, **_kwargs):
            raise AssertionError("complete fast_info must suppress history")

    monkeypatch.setattr(yfinance_fallback, "configure_yfinance_cache", lambda _yf: True)
    monkeypatch.setattr(yfinance_fallback.yf, "Ticker", FakeTicker)

    result = yfinance_fallback.get_stock_price_yf("AAPL")

    assert result["change"] == 1
    assert result["change_percent"] == 1


def test_valid_cached_range_suppresses_history(monkeypatch):
    class FakeTicker:
        ticker = "AAPL"
        info = {}
        fast_info = {"last_price": 101, "previous_close": 100}

        def __init__(self, _ticker):
            pass

        def history(self, **_kwargs):
            raise AssertionError("valid cached fundamentals must suppress history")

    monkeypatch.setattr(yfinance_fallback, "configure_yfinance_cache", lambda _yf: True)
    monkeypatch.setattr(yfinance_fallback.yf, "Ticker", FakeTicker)

    result = yfinance_fallback.get_stock_price_yf(
        "AAPL",
        cached_fundamentals={
            "fifty_two_week_high": 120,
            "fifty_two_week_low": 80,
            "volume": 1234,
        },
    )

    assert result["current_price"] == 101


def test_history_rejects_inverted_range(monkeypatch):
    class FakeTicker:
        ticker = "AAPL"
        info = {}
        fast_info = {"last_price": 101, "previous_close": 100}

        def __init__(self, _ticker):
            pass

        def history(self, **_kwargs):
            return pd.DataFrame({"High": [80.0], "Low": [90.0], "Volume": [20]})

    monkeypatch.setattr(yfinance_fallback, "configure_yfinance_cache", lambda _yf: True)
    monkeypatch.setattr(yfinance_fallback.yf, "Ticker", FakeTicker)

    result = yfinance_fallback.get_stock_price_yf("AAPL")

    assert result["fifty_two_week_high"] is None
    assert result["fifty_two_week_low"] is None
    assert result["volume"] == 20


def test_programmer_assertion_is_not_hidden_as_provider_failure(monkeypatch):
    class FakeTicker:
        ticker = "AAPL"

        def __init__(self, _ticker):
            pass

        @property
        def info(self):
            raise AssertionError("contract violated")

    monkeypatch.setattr(yfinance_fallback, "configure_yfinance_cache", lambda _yf: True)
    monkeypatch.setattr(yfinance_fallback.yf, "Ticker", FakeTicker)

    with pytest.raises(AssertionError, match="contract violated"):
        yfinance_fallback.get_stock_price_yf("AAPL")


def test_etf_description_falls_back_to_funds_data(monkeypatch):
    class FakeTicker:
        ticker = "SPY"
        holdings = None
        info = {
            "quoteType": "ETF", "currentPrice": 500, "previousClose": 499,
            "open": 498, "dayLow": 497, "dayHigh": 501,
            "fiftyTwoWeekLow": 400, "fiftyTwoWeekHigh": 510,
            "regularMarketVolume": 100, "totalAssets": 600,
        }
        funds_data = type("Funds", (), {"description": "Documented fund description."})()

        def __init__(self, _ticker):
            pass

    monkeypatch.setattr(yfinance_fallback, "configure_yfinance_cache", lambda _yf: True)
    monkeypatch.setattr(yfinance_fallback.yf, "Ticker", FakeTicker)

    result = yfinance_fallback.get_stock_price_yf("SPY")

    assert result["long_business_summary"] == "Documented fund description."


def test_etf_clears_stock_company_semantics_and_uses_beta3year(monkeypatch):
    class FakeTicker:
        ticker = "SPY"
        holdings = None
        funds_data = type("Funds", (), {"description": "Fund"})()
        info = {
            "quoteType": "ETF", "currentPrice": 500, "previousClose": 499,
            "open": 498, "dayLow": 497, "dayHigh": 501,
            "fiftyTwoWeekLow": 400, "fiftyTwoWeekHigh": 510,
            "regularMarketVolume": 100, "totalAssets": 600, "beta3Year": 0.9,
            "fullTimeEmployees": 10, "recommendationKey": "buy", "forwardPE": 20,
            "companyOfficers": [{"name": "Jane", "title": "CEO"}],
        }

        def __init__(self, _ticker):
            pass

    monkeypatch.setattr(yfinance_fallback, "configure_yfinance_cache", lambda _yf: True)
    monkeypatch.setattr(yfinance_fallback.yf, "Ticker", FakeTicker)

    result = yfinance_fallback.get_stock_price_yf("SPY")

    assert result["beta"] == 0.9
    assert result["fifty_two_week_high"] == 510
    assert result["fifty_two_week_low"] == 400
    assert result["volume"] == 100
    assert result["ceo_name"] is None
    assert result["full_time_employees"] is None
    assert result["average_analyst_rating"] is None
    assert result["forward_pe"] is None


def test_ceo_uses_already_fetched_info_without_officers_accessor():
    ticker = type("Ticker", (), {"ticker": "AAPL"})()
    info = {"companyOfficers": [
        {"name": "Jane Example", "title": "Chief Executive Officer & Director"},
    ]}

    assert yfinance_fallback._extract_ceo_name(ticker, info) == "Jane Example"


def test_field_level_cache_merge_preserves_old_gaps_and_marks_stale():
    old_timestamp = time.time() - hybrid_data_service._CACHE_TTL - 1
    hybrid_data_service._cache["ORI"] = ({
        "ticker": "ORI", "security_type": "STOCK", "current_price": 42,
        "market_cap": 10_000_000_000, "beta": 0.6,
        "fifty_two_week_high": 47, "fundamentals_as_of": "2026-01-01T00:00:00+00:00",
    }, old_timestamp)

    hybrid_data_service._cache_set("ORI", {
        "ticker": "ORI", "security_type": "STOCK", "current_price": 44,
        "market_cap": 10_500_000_000, "beta": None,
        "fifty_two_week_high": None, "data_status": "partial",
    })
    merged, timestamp = hybrid_data_service._cache["ORI"]

    assert merged["current_price"] == 44
    assert merged["market_cap"] == 10_500_000_000
    assert merged["beta"] == 0.6
    assert merged["fifty_two_week_high"] == 47
    assert merged["fundamentals_status"] == "stale"
    assert merged["fundamentals_is_stale"] is True
    assert merged["fundamentals_as_of"] == "2026-01-01T00:00:00+00:00"
    assert timestamp == old_timestamp


def test_cache_merge_recomputes_risk_from_final_inputs():
    hybrid_data_service._cache["ORI"] = ({
        "ticker": "ORI", "security_type": "STOCK", "current_price": 40,
        "beta": 0.6, "short_percent_of_float": 0.1, "debt_to_equity": 20,
        "fifty_two_week_high": 50, "fifty_two_week_low": 30, "overall_risk": 99,
    }, time.time())

    hybrid_data_service._cache_set("ORI", {
        "ticker": "ORI", "security_type": "STOCK", "current_price": 45,
        "beta": 0.8, "short_percent_of_float": 0.1, "debt_to_equity": 20,
        "fifty_two_week_high": 50, "fifty_two_week_low": 30,
        "overall_risk": None, "data_status": "complete",
    })

    merged = hybrid_data_service._cache["ORI"][0]
    expected = hybrid_data_service._compute_composite_risk(
        beta=0.8, short_pct_of_float=0.1, debt_eq=20,
        high52=50, low52=30, current_price=45,
    )
    assert merged["overall_risk"] == expected
    assert merged["overall_risk"] != 99


def test_cached_fund_assets_outrank_new_etf_market_value():
    hybrid_data_service._cache["SPY"] = ({
        "ticker": "SPY", "security_type": "ETF", "fund_assets": 600,
        "fund_assets_source": "yfinance_info.totalAssets", "market_size_value": 600,
        "market_size_type": "fund_assets",
    }, time.time() - hybrid_data_service._CACHE_TTL - 1)

    hybrid_data_service._cache_set("SPY", {
        "ticker": "SPY", "security_type": "ETF", "fund_assets": None,
        "etf_market_cap": 550, "market_size_value": 550,
        "market_size_type": "etf_market_cap", "data_status": "partial",
    })
    merged = hybrid_data_service._cache["SPY"][0]

    assert merged["fund_assets"] == 600
    assert merged["market_size_value"] == 600
    assert merged["market_size_type"] == "fund_assets"
    assert merged["market_size_fallback_used"] is False


@pytest.mark.asyncio
async def test_batch_budget_returns_unavailable_without_cancelling_warmup(monkeypatch):
    completed = asyncio.Event()

    async def slow_fetch(ticker):
        await asyncio.sleep(0.04)
        completed.set()
        return ticker, {"ticker": ticker, "current_price": 10, "data_status": "partial"}

    monkeypatch.setattr(hybrid_data_service, "_BATCH_BUDGET_S", 0.005)
    monkeypatch.setattr(hybrid_data_service, "_fetch_one", slow_fetch)

    started = time.monotonic()
    result = await hybrid_data_service.get_hybrid_batch_prices(["AAPL"])

    assert time.monotonic() - started < 0.03
    assert result[0]["fundamentals_status"] == "unavailable"
    await asyncio.wait_for(completed.wait(), timeout=0.2)


@pytest.mark.asyncio
async def test_empty_batch_returns_without_creating_tasks():
    assert await hybrid_data_service.get_hybrid_batch_prices([]) == []


@pytest.mark.asyncio
async def test_background_refresh_monitor_times_out_without_duplicating_provider(monkeypatch):
    started = asyncio.Event()
    release = asyncio.Event()

    async def blocked_refresh(_ticker):
        started.set()
        await release.wait()
        return {"ticker": "AAPL", "current_price": 10, "data_status": "complete"}

    monkeypatch.setattr(hybrid_data_service, "_BACKGROUND_REFRESH_TIMEOUT_S", 0.005)
    monkeypatch.setattr(hybrid_data_service, "_refresh_hybrid_stock_price", blocked_refresh)

    hybrid_data_service._schedule_symbol_refresh("AAPL")
    await started.wait()
    await asyncio.sleep(0.02)

    provider_task = hybrid_data_service._refresh_tasks_by_symbol["AAPL"]
    assert not provider_task.done()
    assert "AAPL" in hybrid_data_service._refresh_retry_after
    hybrid_data_service._schedule_symbol_refresh("AAPL")
    assert hybrid_data_service._refresh_tasks_by_symbol["AAPL"] is provider_task

    release.set()
    await provider_task
    await asyncio.sleep(0)
    assert "AAPL" not in hybrid_data_service._refresh_tasks_by_symbol


@pytest.mark.asyncio
async def test_shutdown_cancels_tracked_refresh_tasks():
    task = asyncio.create_task(asyncio.sleep(60))
    hybrid_data_service._track_background_task(task)

    await hybrid_data_service.shutdown_hybrid_data_service()

    assert task.cancelled()
    assert not hybrid_data_service._background_tasks
