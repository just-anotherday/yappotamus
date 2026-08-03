"""Contract tests for Finnhub quote and company-profile normalization."""

import asyncio
import threading

import pytest

from backend.services import finnhub_service


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