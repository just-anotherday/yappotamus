"""Regression tests for extended-hours quote extraction and caching."""

from datetime import datetime
import threading
from unittest.mock import patch
from zoneinfo import ZoneInfo

from backend.services.post_market_service import PostMarketService, _next_poll_delay
import pytest

from backend.services import post_market_service, yfinance_fallback


ET = ZoneInfo("US/Eastern")
@pytest.fixture(autouse=True)
def reset_yfinance_cooldown():
    yfinance_fallback._reset_yfinance_cooldown_for_tests()
    yield
    yfinance_fallback._reset_yfinance_cooldown_for_tests()


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


def test_post_market_cooldown_skips_yahoo_and_reports_cycle(monkeypatch, caplog):
    calls = []
    monkeypatch.setattr(post_market_service, "configure_yfinance_cache", lambda _yf: True)
    monkeypatch.setattr(yfinance_fallback.time, "monotonic", lambda: 100.0)
    yfinance_fallback._record_yfinance_outage_failure(yfinance_fallback.YFRateLimitError())

    class FakeTicker:
        def __init__(self, ticker):
            calls.append(ticker)

    monkeypatch.setattr(post_market_service.yf, "Ticker", FakeTicker)

    with caplog.at_level("INFO"):
        PostMarketService().fetch_all(["AAPL", "MSFT"])

    assert calls == []
    assert "cooldown_skips=2" in caplog.text
    assert "cooldown_active=True" in caplog.text


def test_post_market_recognized_yahoo_failure_opens_shared_cooldown(monkeypatch):
    monkeypatch.setattr(post_market_service, "configure_yfinance_cache", lambda _yf: True)

    class RateLimitedTicker:
        def __init__(self, _ticker):
            pass

        @property
        def info(self):
            raise yfinance_fallback.YFRateLimitError()

    monkeypatch.setattr(post_market_service.yf, "Ticker", RateLimitedTicker)

    assert PostMarketService()._get_post_market_data_for_ticker("AAPL") == (None, None)
    assert yfinance_fallback._yfinance_cooldown_status()[0] is True


def test_post_market_unrecognized_failure_does_not_open_shared_cooldown(monkeypatch):
    monkeypatch.setattr(post_market_service, "configure_yfinance_cache", lambda _yf: True)

    class BrokenTicker:
        def __init__(self, _ticker):
            raise RuntimeError("ordinary provider failure")

    monkeypatch.setattr(post_market_service.yf, "Ticker", BrokenTicker)

    assert PostMarketService()._get_post_market_data_for_ticker("AAPL") == (None, None)
    assert yfinance_fallback._yfinance_cooldown_status() == (False, None)


def test_queued_post_market_task_checks_cooldown_when_it_starts(monkeypatch):
    ticker_calls = []
    inflight_started = threading.Event()
    cooldown_opened = threading.Event()
    inflight_finished = threading.Event()
    monkeypatch.setenv("PM_MAX_CONCURRENCY", "2")
    monkeypatch.setattr(post_market_service, "configure_yfinance_cache", lambda _yf: True)

    original_record_failure = post_market_service._record_yfinance_outage_failure

    def record_failure(exception):
        failure_class = original_record_failure(exception)
        if failure_class is not None:
            cooldown_opened.set()
        return failure_class

    monkeypatch.setattr(post_market_service, "_record_yfinance_outage_failure", record_failure)

    class ControlledTicker:
        def __init__(self, ticker):
            ticker_calls.append(ticker)
            self.ticker = ticker

        @property
        def info(self):
            if self.ticker == "AAPL":
                assert inflight_started.wait(timeout=1)
                raise yfinance_fallback.YFRateLimitError()
            if self.ticker == "MSFT":
                inflight_started.set()
                assert cooldown_opened.wait(timeout=1)
                inflight_finished.set()
            return {"regularMarketPrice": 100.0, "postMarketPrice": 101.0}

    monkeypatch.setattr(post_market_service.yf, "Ticker", ControlledTicker)

    PostMarketService().fetch_all(["AAPL", "MSFT", "NVDA"])

    assert ticker_calls == ["AAPL", "MSFT"]
    assert inflight_finished.is_set()
    assert yfinance_fallback._yfinance_cooldown_status()[0] is True

# ---------------------------------------------------------------------------
# Focused memory-boundary instrumentation tests for _post_market_fetch_loop
# ---------------------------------------------------------------------------
import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, Mock, call

from backend.services import watchlist_service


class SaturdayDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        value = cls(2026, 8, 1, 10, 0, 0)
        return value.replace(tzinfo=tz) if tz is not None else value


class FakeSessionContext:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, exc_type, exc, tb):
        return False


def fake_session_factory():
    return FakeSessionContext()


class FakeLoop:
    def __init__(self, *, result=None, error=None):
        if error is None:
            self.run_in_executor = AsyncMock(return_value=result)
        else:
            self.run_in_executor = AsyncMock(side_effect=error)


@pytest.mark.asyncio
async def test_post_market_loop_logs_memory_boundaries_for_successful_cycle(
    monkeypatch,
):
    """Verify that a controlled after-hours cycle emits start/complete memory checkpoints."""
    log_mock = Mock()
    sleep_mock = AsyncMock(side_effect=asyncio.CancelledError())
    ticker_mock = AsyncMock(return_value=["AAPL", "MSFT", "NVDA"])
    fake_loop = FakeLoop(result=None)

    monkeypatch.setattr(post_market_service, "datetime", SaturdayDateTime)
    monkeypatch.setattr(post_market_service, "log_memory", log_mock)
    monkeypatch.setattr(
        post_market_service.asyncio,
        "get_running_loop",
        Mock(return_value=fake_loop),
    )
    monkeypatch.setattr(post_market_service.asyncio, "sleep", sleep_mock)
    monkeypatch.setattr(
        watchlist_service,
        "get_all_tickers",
        ticker_mock,
    )

    with pytest.raises(asyncio.CancelledError):
        await post_market_service._post_market_fetch_loop(
            fake_session_factory
        )

    assert log_mock.call_args_list == [
        call(
            "post_market_cycle_start",
            logger_to_use=post_market_service.logger,
            enabled=post_market_service.app_settings.MEMORY_DIAGNOSTICS_ENABLED,
            extra={"symbol_count": 3},
        ),
        call(
            "post_market_cycle_complete",
            logger_to_use=post_market_service.logger,
            enabled=post_market_service.app_settings.MEMORY_DIAGNOSTICS_ENABLED,
            extra={"symbol_count": 3},
        ),
    ]


@pytest.mark.asyncio
async def test_post_market_loop_logs_completion_when_fetch_fails(
    monkeypatch,
):
    """Verify completion checkpoint fires even when the executor fetch raises."""
    log_mock = Mock()
    sleep_mock = AsyncMock(side_effect=asyncio.CancelledError())
    ticker_mock = AsyncMock(return_value=["AAPL", "MSFT"])
    fake_loop = FakeLoop(error=RuntimeError("test failure"))

    monkeypatch.setattr(post_market_service, "datetime", SaturdayDateTime)
    monkeypatch.setattr(post_market_service, "log_memory", log_mock)
    monkeypatch.setattr(
        post_market_service.asyncio,
        "get_running_loop",
        Mock(return_value=fake_loop),
    )
    monkeypatch.setattr(post_market_service.asyncio, "sleep", sleep_mock)
    monkeypatch.setattr(
        watchlist_service,
        "get_all_tickers",
        ticker_mock,
    )

    with pytest.raises(asyncio.CancelledError):
        await post_market_service._post_market_fetch_loop(
            fake_session_factory
        )

    assert log_mock.call_args_list == [
        call(
            "post_market_cycle_start",
            logger_to_use=post_market_service.logger,
            enabled=post_market_service.app_settings.MEMORY_DIAGNOSTICS_ENABLED,
            extra={"symbol_count": 2},
        ),
        call(
            "post_market_cycle_complete",
            logger_to_use=post_market_service.logger,
            enabled=post_market_service.app_settings.MEMORY_DIAGNOSTICS_ENABLED,
            extra={"symbol_count": 2},
        ),
    ]


@pytest.mark.asyncio
async def test_post_market_loop_propagates_executor_cancellation(
    monkeypatch,
):
    """Verify that CancelledError propagates and the inner finally still fires."""
    log_mock = Mock()
    sleep_mock = AsyncMock()
    ticker_mock = AsyncMock(return_value=["AAPL"])
    fake_loop = FakeLoop(error=asyncio.CancelledError())

    monkeypatch.setattr(post_market_service, "datetime", SaturdayDateTime)
    monkeypatch.setattr(post_market_service, "log_memory", log_mock)
    monkeypatch.setattr(
        post_market_service.asyncio,
        "get_running_loop",
        Mock(return_value=fake_loop),
    )
    monkeypatch.setattr(post_market_service.asyncio, "sleep", sleep_mock)
    monkeypatch.setattr(
        watchlist_service,
        "get_all_tickers",
        ticker_mock,
    )

    with pytest.raises(asyncio.CancelledError):
        await post_market_service._post_market_fetch_loop(
            fake_session_factory
        )

    assert log_mock.call_args_list == [
        call(
            "post_market_cycle_start",
            logger_to_use=post_market_service.logger,
            enabled=post_market_service.app_settings.MEMORY_DIAGNOSTICS_ENABLED,
            extra={"symbol_count": 1},
        ),
        call(
            "post_market_cycle_complete",
            logger_to_use=post_market_service.logger,
            enabled=post_market_service.app_settings.MEMORY_DIAGNOSTICS_ENABLED,
            extra={"symbol_count": 1},
        ),
    ]
    sleep_mock.assert_not_awaited()
