"""Configuration and process-shared provider limiter tests."""
import asyncio
from unittest.mock import patch

import pytest

from backend.config.polling_settings import PollingSettings
from backend.services import finnhub_service


def test_polling_defaults(monkeypatch):
    for name in ("LIVE_PRICE_POLL_S", "MARKET_DATA_BATCH_SIZE", "PM_FETCH_INTERVAL_S", "PM_MAX_CONCURRENCY", "FINNHUB_REQUESTS_PER_MINUTE"):
        monkeypatch.delenv(name, raising=False)
    config = PollingSettings()
    assert (config.LIVE_PRICE_POLL_S, config.MARKET_DATA_BATCH_SIZE) == (15, 50)
    assert (config.PM_FETCH_INTERVAL_S, config.PM_MAX_CONCURRENCY) == (30, 3)
    assert config.FINNHUB_REQUESTS_PER_MINUTE == 55


def test_invalid_polling_configuration_is_rejected(monkeypatch):
    monkeypatch.setenv("MARKET_DATA_BATCH_SIZE", "0")
    with pytest.raises(EnvironmentError):
        PollingSettings().MARKET_DATA_BATCH_SIZE


@pytest.mark.asyncio
async def test_finnhub_limiter_is_shared_and_enforces_spacing(monkeypatch):
    finnhub_service._rate_lock = None
    finnhub_service._last_call_time = 100.0
    times = iter([100.2, 101.2])
    sleeps = []

    async def fake_sleep(delay):
        sleeps.append(delay)

    with patch("backend.services.finnhub_service.time.time", side_effect=lambda: next(times)), patch(
        "backend.services.finnhub_service.asyncio.sleep", side_effect=fake_sleep
    ):
        first_lock = finnhub_service._get_rate_lock()
        assert first_lock is finnhub_service._get_rate_lock()
        await finnhub_service._rate_limiter()
    assert sleeps[0] == pytest.approx(finnhub_service._min_interval - 0.2)