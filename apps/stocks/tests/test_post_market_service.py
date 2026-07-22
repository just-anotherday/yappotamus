"""Regression tests for extended-hours quote extraction and caching."""

from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from backend.services.post_market_service import PostMarketService, _next_poll_delay


ET = ZoneInfo("US/Eastern")


def test_price_hint_is_not_treated_as_an_after_hours_price():
    info = {"regularMarketPrice": 682.21, "priceHint": 2}

    extended, regular = PostMarketService._extract_extended_hours_prices(
        info,
        datetime(2026, 7, 21, 16, 30, tzinfo=ET),
    )

    assert extended is None
    assert regular == 682.21


def test_extracts_post_market_price_after_close():
    info = {"regularMarketPrice": 100.0, "postMarketPrice": 101.25}

    extended, regular = PostMarketService._extract_extended_hours_prices(
        info,
        datetime(2026, 7, 21, 17, 0, tzinfo=ET),
    )

    assert extended == 101.25
    assert regular == 100.0


def test_extracts_pre_market_price_before_open():
    info = {"regularMarketPrice": 100.0, "preMarketPrice": 99.5}

    extended, regular = PostMarketService._extract_extended_hours_prices(
        info,
        datetime(2026, 7, 21, 8, 0, tzinfo=ET),
    )

    assert extended == 99.5
    assert regular == 100.0


def test_rejects_implausible_metadata_like_price():
    info = {"regularMarketPrice": 682.21, "postMarketPrice": 2}

    extended, regular = PostMarketService._extract_extended_hours_prices(
        info,
        datetime(2026, 7, 21, 17, 0, tzinfo=ET),
    )

    assert extended is None
    assert regular == 682.21


@patch.object(PostMarketService, "_get_post_market_data_for_ticker", return_value=(None, 100.0))
def test_fetch_removes_stale_quote_when_provider_has_no_valid_quote(_mock_fetch):
    service = PostMarketService()
    service._post_market_prices["VOO"] = {
        "post_market_price": 2.0,
        "post_market_change": -680.21,
        "post_market_change_percent": -99.7,
    }

    service.fetch_all(["VOO"])

    assert service.get_post_market_price("VOO") is None


@patch.object(PostMarketService, "_get_post_market_data_for_ticker", return_value=(101.0, 100.0))
def test_fetch_caches_valid_quote_and_change(_mock_fetch):
    service = PostMarketService()

    service.fetch_all(["TEST"])

    assert service.get_post_market_price("TEST") == {
        "post_market_price": 101.0,
        "post_market_change": 1.0,
        "post_market_change_percent": 1.0,
    }


def test_provider_failure_retains_stale_extended_quote():
    service = PostMarketService()
    service._post_market_prices["VOO"] = {"post_market_price": 101.0}
    with patch.object(service, "_get_post_market_data_for_ticker", return_value=(None, None)):
        service.fetch_all(["VOO"])
    assert service.get_post_market_price("VOO") == {"post_market_price": 101.0}


def test_extended_hours_uses_bounded_executor():
    service = PostMarketService()
    with patch("backend.services.post_market_service.ThreadPoolExecutor") as executor:
        executor.return_value.__enter__.return_value.submit.return_value = object()
        with patch("backend.services.post_market_service.as_completed", return_value=[]):
            service.fetch_all(["AAA", "BBB"])
    from backend.config.polling_settings import polling_settings as settings
    executor.assert_called_once_with(max_workers=settings.PM_MAX_CONCURRENCY, thread_name_prefix="extended-hours")


def test_extended_start_to_start_delay_backoff_jitter_and_recovery(monkeypatch):
    monkeypatch.setenv("PM_FETCH_INTERVAL_S", "30")
    monkeypatch.setenv("MARKET_DATA_BACKOFF_INITIAL_S", "5")
    monkeypatch.setenv("MARKET_DATA_JITTER_S", "2")
    with patch("backend.services.post_market_service.time.monotonic", return_value=104.0), patch(
        "backend.services.post_market_service.random.uniform", return_value=1.0
    ):
        assert _next_poll_delay(100.0, True, 10.0) == (27.0, 0.0)
        assert _next_poll_delay(100.0, False, 0.0) == (2.0, 5.0)
        assert _next_poll_delay(100.0, False, 5.0) == (7.0, 10.0)