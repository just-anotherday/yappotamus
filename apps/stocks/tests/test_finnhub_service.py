"""Contract tests for Finnhub quote and company-profile normalization."""

import asyncio
import threading

import pytest
from unittest.mock import AsyncMock

from backend.services import finnhub_service


class _ProviderError(Exception):
    def __init__(self, status_code, retry_after=None):
        self.status_code = status_code
        self.response = type(
            "Response", (), {"status_code": status_code, "headers": {"Retry-After": retry_after} if retry_after else {}}
        )()


@pytest.mark.asyncio
async def test_retry_api_honors_retry_after_and_counts_each_physical_attempt(monkeypatch):
    attempts = 0

    async def operation():
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise _ProviderError(429, "7")
        return {"ok": True}

    sleep = AsyncMock()
    monkeypatch.setattr(finnhub_service, "_rate_limiter", AsyncMock())
    monkeypatch.setattr(finnhub_service.asyncio, "sleep", sleep)
    metrics = {}

    assert await finnhub_service._retry_api(
        operation, _request_operation="test", _request_metrics=metrics,
    ) == {"ok": True}
    assert attempts == 2
    sleep.assert_awaited_once_with(7.0)
    assert metrics == {
        "provider_requests": 2,
        "provider_rate_limits": 1,
        "provider_retries": 1,
        "provider_successes": 1,
    }


@pytest.mark.asyncio
async def test_retry_api_does_not_retry_permanent_client_failure(monkeypatch):
    operation = AsyncMock(side_effect=_ProviderError(400))
    monkeypatch.setattr(finnhub_service, "_rate_limiter", AsyncMock())
    sleep = AsyncMock()
    monkeypatch.setattr(finnhub_service.asyncio, "sleep", sleep)

    with pytest.raises(_ProviderError):
        await finnhub_service._retry_api(operation, _request_operation="test")
    assert operation.await_count == 1
    sleep.assert_not_awaited()


@pytest.mark.asyncio
async def test_company_profile_accepts_current_dict_shape(monkeypatch):
    profile = {"name": "Example Inc.", "marketCapitalization": 3210.5}

    async def no_rate_limit():
        return None

    async def return_profile(*_args, **_kwargs):
        return profile

    monkeypatch.setattr(finnhub_service, "_rate_limiter", no_rate_limit)
    monkeypatch.setattr(finnhub_service, "get_finnhub_client", lambda: object())
    monkeypatch.setattr(finnhub_service, "_retry_api", return_profile)

    assert await finnhub_service.fetch_company_profile("EXM") == profile


@pytest.mark.asyncio
async def test_ticker_info_converts_finnhub_market_cap_millions_to_absolute_units(monkeypatch):
    async def quote(_ticker):
        return {"c": 102.0, "pc": 100.0, "d": 2.0}

    async def profile(_ticker):
        return {
            "name": "Example Inc.",
            "marketCapitalization": 3210.5,
            "shareOutstanding": 125.25,
        }

    monkeypatch.setattr(finnhub_service, "fetch_quote", quote)
    monkeypatch.setattr(finnhub_service, "fetch_company_profile", profile)

    info = await finnhub_service.get_ticker_info("EXM")

    assert info["marketCap"] == 3_210_500_000
    assert info["sharesOutstanding"] == 125_250_000
    assert info["regularMarketChangePercent"] == 2.0


@pytest.mark.asyncio
async def test_stock_price_preserves_market_cap_currency(monkeypatch):
    async def ticker_info(_ticker):
        return {
            "symbol": "ORI",
            "shortName": "Old Republic International Corporation",
            "currentPrice": 43.33,
            "previousClose": 43.0,
            "marketCap": 10_523_970_132,
            "currency": "USD",
        }

    monkeypatch.setattr(finnhub_service, "get_ticker_info", ticker_info)

    result = await finnhub_service.get_stock_price("ORI")

    assert result["market_cap"] == 10_523_970_132
    assert result["market_size_currency"] == "USD"

@pytest.mark.asyncio
async def test_blocked_quotes_are_offloaded_and_do_not_serialize(monkeypatch):
    started = []
    started_lock = threading.Lock()
    all_started = threading.Event()
    release_quotes = threading.Event()

    async def no_rate_limit():
        return None

    class BlockingClient:
        def quote(self, ticker):
            with started_lock:
                started.append(ticker)
                if len(started) == 4:
                    all_started.set()
            assert release_quotes.wait(timeout=1)
            return {"c": 100.0}

    monkeypatch.setattr(finnhub_service, "_rate_limiter", no_rate_limit)
    monkeypatch.setattr(finnhub_service, "get_finnhub_client", lambda: BlockingClient())

    pending = [asyncio.create_task(finnhub_service.fetch_quote(ticker)) for ticker in ("AAA", "BBB", "CCC", "DDD")]
    assert await asyncio.wait_for(asyncio.to_thread(all_started.wait), timeout=1)

    heartbeat = asyncio.Event()
    await asyncio.sleep(0)
    heartbeat.set()
    assert heartbeat.is_set()
    assert len(started) == 4

    release_quotes.set()
    assert await asyncio.gather(*pending) == [{"c": 100.0}] * 4
