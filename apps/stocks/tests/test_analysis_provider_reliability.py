"""Deterministic concurrency coverage for hybrid analysis market data."""

import asyncio
import time
from collections import Counter

import pytest

from backend.services import hybrid_data_service


def _price(ticker: str, value: float = 100.0) -> dict:
    return {
        "ticker": ticker,
        "current_price": value,
        "previous_close": value - 1,
        "market_cap": 1_000_000_000,
        "security_type": "STOCK",
        "data_source": "fh",
        "data_status": "complete",
    }


@pytest.fixture(autouse=True)
async def reset_hybrid_state():
    hybrid_data_service._cache.clear()
    hybrid_data_service._refresh_retry_after.clear()
    yield
    await hybrid_data_service.shutdown_hybrid_data_service()
    hybrid_data_service._cache.clear()
    hybrid_data_service._refresh_retry_after.clear()


@pytest.mark.asyncio
async def test_same_symbol_callers_share_one_hybrid_refresh(monkeypatch, caplog):
    calls = 0
    started = asyncio.Event()
    release = asyncio.Event()

    async def blocked_refresh(ticker: str):
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()
        return _price(ticker)

    monkeypatch.setattr(hybrid_data_service, "_refresh_hybrid_stock_price", blocked_refresh)
    with caplog.at_level("INFO"):
        callers = [
            asyncio.create_task(hybrid_data_service.get_hybrid_stock_price("spcx"))
            for _ in range(8)
        ]
        await started.wait()
        await asyncio.sleep(0)

        assert calls == 1
        release.set()
        results = await asyncio.gather(*callers)
    assert results == [_price("SPCX")] * 8
    assert "SPCX" not in hybrid_data_service._hybrid_flights
    assert "event=singleflight_created ticker=SPCX waiters=1" in caplog.text
    assert "event=singleflight_joined ticker=SPCX waiters=8" in caplog.text
    assert "event=singleflight_completed ticker=SPCX waiters=8" in caplog.text


@pytest.mark.asyncio
async def test_cancelled_waiter_does_not_cancel_shared_refresh(monkeypatch):
    calls = 0
    started = asyncio.Event()
    release = asyncio.Event()

    async def blocked_refresh(ticker: str):
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()
        return _price(ticker)

    monkeypatch.setattr(hybrid_data_service, "_refresh_hybrid_stock_price", blocked_refresh)
    cancelled = asyncio.create_task(hybrid_data_service.get_hybrid_stock_price("SPCX"))
    survivor = asyncio.create_task(hybrid_data_service.get_hybrid_stock_price("SPCX"))
    await started.wait()
    cancelled.cancel()
    with pytest.raises(asyncio.CancelledError):
        await cancelled

    release.set()
    assert await survivor == _price("SPCX")
    assert calls == 1


@pytest.mark.asyncio
async def test_direct_and_watchlist_callers_share_one_hybrid_refresh(monkeypatch):
    calls = 0
    started = asyncio.Event()
    release = asyncio.Event()

    async def blocked_refresh(ticker: str):
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()
        return _price(ticker)

    monkeypatch.setattr(hybrid_data_service, "_refresh_hybrid_stock_price", blocked_refresh)
    direct = asyncio.create_task(hybrid_data_service.get_hybrid_stock_price("SPCX"))
    batch = asyncio.create_task(hybrid_data_service.get_hybrid_batch_prices(["SPCX"]))
    await started.wait()
    await asyncio.sleep(0)

    assert calls == 1
    release.set()
    direct_result, batch_result = await asyncio.gather(direct, batch)
    assert direct_result == _price("SPCX")
    assert batch_result == [_price("SPCX")]


@pytest.mark.asyncio
async def test_background_and_direct_callers_share_one_hybrid_refresh(monkeypatch):
    calls = 0
    started = asyncio.Event()
    release = asyncio.Event()

    async def blocked_refresh(ticker: str):
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()
        return _price(ticker)

    monkeypatch.setattr(hybrid_data_service, "_refresh_hybrid_stock_price", blocked_refresh)
    hybrid_data_service._schedule_symbol_refresh("SPCX")
    await started.wait()
    direct = asyncio.create_task(hybrid_data_service.get_hybrid_stock_price("SPCX"))
    await asyncio.sleep(0)

    assert calls == 1
    release.set()
    assert await direct == _price("SPCX")


@pytest.mark.asyncio
async def test_different_symbols_refresh_in_parallel(monkeypatch):
    calls = Counter()
    all_started = asyncio.Event()
    release = asyncio.Event()

    async def blocked_refresh(ticker: str):
        calls[ticker] += 1
        if len(calls) == 3:
            all_started.set()
        await release.wait()
        return _price(ticker)

    monkeypatch.setattr(hybrid_data_service, "_refresh_hybrid_stock_price", blocked_refresh)
    callers = [
        asyncio.create_task(hybrid_data_service.get_hybrid_stock_price(ticker))
        for ticker in ("AMD", "NVDA", "SPCX")
    ]
    await asyncio.wait_for(all_started.wait(), timeout=1)
    assert calls == Counter({"AMD": 1, "NVDA": 1, "SPCX": 1})

    release.set()
    await asyncio.gather(*callers)


@pytest.mark.asyncio
async def test_failed_shared_refresh_is_cleaned_up_for_retry(monkeypatch, caplog):
    calls = 0
    started = asyncio.Event()
    release = asyncio.Event()

    async def fail_then_succeed(ticker: str):
        nonlocal calls
        calls += 1
        if calls == 1:
            started.set()
            await release.wait()
            raise RuntimeError("provider outage")
        return _price(ticker, 101.0)

    monkeypatch.setattr(hybrid_data_service, "_refresh_hybrid_stock_price", fail_then_succeed)
    callers = [
        asyncio.create_task(hybrid_data_service.get_hybrid_stock_price("SPCX"))
        for _ in range(4)
    ]
    await started.wait()
    await asyncio.sleep(0)
    assert calls == 1

    release.set()
    with caplog.at_level("WARNING"):
        first_results = await asyncio.gather(*callers, return_exceptions=True)
    assert all(isinstance(result, RuntimeError) for result in first_results)
    assert "SPCX" not in hybrid_data_service._hybrid_flights
    assert "event=singleflight_failed ticker=SPCX waiters=4" in caplog.text
    assert "failure_reason=RuntimeError" in caplog.text
    assert await hybrid_data_service.get_hybrid_stock_price("SPCX") == _price("SPCX", 101.0)
    assert calls == 2


@pytest.mark.asyncio
async def test_fresh_cache_bypasses_hybrid_refresh(monkeypatch):
    hybrid_data_service._cache["SPCX"] = (_price("SPCX"), time.time())

    async def unexpected_refresh(_ticker: str):
        raise AssertionError("fresh cache must bypass the provider flight")

    monkeypatch.setattr(hybrid_data_service, "_refresh_hybrid_stock_price", unexpected_refresh)
    result = await hybrid_data_service.get_hybrid_stock_price("SPCX")

    assert result["ticker"] == "SPCX"
    assert result["current_price"] == 100.0


@pytest.mark.asyncio
async def test_stale_cache_returns_immediately_and_refreshes_once(monkeypatch):
    hybrid_data_service._cache["SPCX"] = (
        _price("SPCX"),
        time.time() - hybrid_data_service._CACHE_TTL - 1,
    )
    calls = 0
    refreshed = asyncio.Event()

    async def refresh(ticker: str):
        nonlocal calls
        calls += 1
        refreshed.set()
        return _price(ticker, 102.0)

    monkeypatch.setattr(hybrid_data_service, "_refresh_hybrid_stock_price", refresh)
    results = await asyncio.gather(
        *(hybrid_data_service.get_hybrid_stock_price("SPCX") for _ in range(5))
    )
    await asyncio.wait_for(refreshed.wait(), timeout=1)
    await asyncio.sleep(0)

    assert all(result["data_status"] == "stale" for result in results)
    assert calls == 1


@pytest.mark.asyncio
async def test_overlapping_22_symbol_watchlists_scale_by_unique_symbol(monkeypatch):
    tickers = ["SPCX"] + [f"SYM{index:02d}" for index in range(21)]
    calls = Counter()

    async def refresh(ticker: str):
        calls[ticker] += 1
        await asyncio.sleep(0.005)
        return _price(ticker)

    monkeypatch.setattr(hybrid_data_service, "_refresh_hybrid_stock_price", refresh)
    monkeypatch.setattr(hybrid_data_service, "_BATCH_BUDGET_S", 2)
    results = await asyncio.gather(
        *(hybrid_data_service.get_hybrid_batch_prices(tickers) for _ in range(3))
    )

    assert all(len(result) == 22 for result in results)
    assert calls == Counter({ticker: 1 for ticker in tickers})


@pytest.mark.asyncio
async def test_foreground_symbol_completes_by_joining_watchlist_flight(monkeypatch):
    tickers = ["SPCX"] + [f"SYM{index:02d}" for index in range(21)]
    calls = Counter()
    spcx_started = asyncio.Event()
    release_spcx = asyncio.Event()
    release_rest = asyncio.Event()

    async def refresh(ticker: str):
        calls[ticker] += 1
        if ticker == "SPCX":
            spcx_started.set()
            await release_spcx.wait()
        else:
            await release_rest.wait()
        return _price(ticker)

    monkeypatch.setattr(hybrid_data_service, "_refresh_hybrid_stock_price", refresh)
    monkeypatch.setattr(hybrid_data_service, "_BATCH_BUDGET_S", 2)
    batch = asyncio.create_task(hybrid_data_service.get_hybrid_batch_prices(tickers))
    await spcx_started.wait()
    foreground = asyncio.create_task(hybrid_data_service.get_hybrid_stock_price("SPCX"))
    await asyncio.sleep(0)

    assert calls["SPCX"] == 1
    release_spcx.set()
    assert await asyncio.wait_for(foreground, timeout=0.2) == _price("SPCX")

    release_rest.set()
    await batch


@pytest.mark.asyncio
async def test_provider_exhaustion_cleans_flight_for_later_retry(monkeypatch):
    finnhub = 0

    async def no_finnhub(_ticker: str):
        nonlocal finnhub
        finnhub += 1
        return None

    async def no_yfinance(_ticker: str):
        return None

    monkeypatch.setattr(hybrid_data_service, "finnhub_get_stock_price", no_finnhub)
    monkeypatch.setattr(hybrid_data_service, "_yf_async", no_yfinance)

    assert await hybrid_data_service.get_hybrid_stock_price("SPCX") is None
    assert "SPCX" not in hybrid_data_service._hybrid_flights
    assert await hybrid_data_service.get_hybrid_stock_price("SPCX") is None
    assert finnhub == 2
