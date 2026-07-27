"""Contract tests for Finnhub quote and company-profile normalization."""

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
