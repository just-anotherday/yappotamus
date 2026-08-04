"""Deterministic tests for batched regular-market polling."""
from datetime import datetime
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pandas as pd

from backend.services.market_data_service import (
    MarketDataService,
    is_regular_market_session,
    merge_live_quote_payload,
    parse_download_quotes,
)


ET = ZoneInfo("US/Eastern")


def test_parses_single_symbol_download_shape():
    frame = pd.DataFrame({"Close": [100.0, 101.5], "Volume": [10, 20]})
    assert parse_download_quotes(frame, ["AAA"]) == {"AAA": {"price": 101.5, "volume": 20}}


def test_parses_multi_symbol_and_preserves_partial_results():
    columns = pd.MultiIndex.from_product([["Close", "Volume"], ["AAA", "BBB"]])
    frame = pd.DataFrame([[10.0, float("nan"), 100, float("nan")]], columns=columns)
    assert parse_download_quotes(frame, ["AAA", "BBB"]) == {"AAA": {"price": 10.0, "volume": 100}}


def test_empty_download_has_no_quotes():
    assert parse_download_quotes(pd.DataFrame(), ["SPY"]) == {}


def test_multiindex_bars_use_regular_sessions_across_weekend_and_ignore_extended_hours():
    index = pd.DatetimeIndex([
        "2026-07-31 15:59:00-04:00",
        "2026-07-31 16:05:00-04:00",
        "2026-08-03 09:00:00-04:00",
        "2026-08-03 09:30:00-04:00",
        "2026-08-03 09:31:00-04:00",
        "2026-08-03 09:31:00-04:00",
    ])
    fields = ["Open", "High", "Low", "Close", "Volume"]
    columns = pd.MultiIndex.from_product([fields, ["SPY", "QQQ"]])
    spy_values = {
        "Open": [99.0, 120.0, 130.0, 101.0, 102.0, 102.2],
        "High": [100.0, 121.0, 131.0, 102.5, 103.0, 103.5],
        "Low": [98.5, 119.0, 129.0, 100.5, 101.5, 101.8],
        "Close": [100.0, 120.0, 130.0, 102.0, 102.5, 102.75],
        "Volume": [20, 1, 1, 30, 40, 50],
    }
    frame = pd.DataFrame(
        [
            [spy_values[field][row] if ticker == "SPY" else float("nan") for field, ticker in columns]
            for row in range(len(index))
        ],
        columns=columns,
        index=index,
    )

    assert parse_download_quotes(frame, ["SPY", "QQQ"]) == {
        "SPY": {
            "price": 102.75,
            "volume": 50,
            "open_price": 101.0,
            "day_low": 100.5,
            "day_high": 103.5,
            "previous_close": 100.0,
            "previous_close_timestamp": "2026-07-31 15:59:00-04:00",
            "quote_timestamp": "2026-08-03 09:31:00-04:00",
            "quote_provider": "yfinance_download",
            "market_session": "regular",
        }
    }


def test_live_quote_overlay_keeps_fundamentals_independent():
    merged = merge_live_quote_payload(
        {
            "ticker": "SPY",
            "security_type": "ETF",
            "fund_assets": None,
            "fifty_two_week_low": None,
            "fifty_two_week_high": None,
            "data_status": "unavailable",
            "missing_fields": ["previous_close"],
        },
        {
            "ticker": "SPY",
            "price": 502.0,
            "previous_close": 500.0,
            "open_price": 501.0,
            "day_low": 499.5,
            "day_high": 503.0,
            "volume": 10,
            "quote_provider": "yfinance_download",
        },
    )

    assert merged["current_price"] == 502.0
    assert merged["previous_close"] == 500.0
    assert merged["change"] == 2.0
    assert merged["change_percent"] == 0.4
    assert merged["fund_assets"] is None
    assert merged["fifty_two_week_low"] is None
    assert merged["fifty_two_week_high"] is None
    assert "data_status" not in merged
    assert "missing_fields" not in merged


def test_missing_symbol_retains_last_valid_quote_and_batches_by_configuration(monkeypatch):
    monkeypatch.setenv("MARKET_DATA_BATCH_SIZE", "2")
    service = MarketDataService()
    service.subscribe(["AAA", "BBB", "CCC"])
    service.latest_quotes["BBB"] = {"ticker": "BBB", "price": 20.0}
    calls = []

    def download(batch):
        calls.append(batch)
        if "AAA" in batch:
            return pd.DataFrame({"Close": [10.0], "Volume": [1]}) if len(batch) == 1 else pd.DataFrame(
                [[10.0, float("nan"), 1, float("nan")]],
                columns=pd.MultiIndex.from_product([["Close", "Volume"], batch]),
            )
        return pd.DataFrame({"Close": [30.0], "Volume": [3]})

    service._download_batch = download
    service._do_poll()
    assert calls == [["AAA", "BBB"], ["CCC"]]
    assert service.latest_quotes["BBB"] == {"ticker": "BBB", "price": 20.0}
    assert service.latest_quotes["CCC"]["price"] == 30.0


def test_only_changed_quotes_are_broadcast():
    service = MarketDataService()
    service.subscribe(["AAA"])
    service._download_batch = lambda _batch: pd.DataFrame({"Close": [10.0], "Volume": [1]})
    service._broadcast = MagicMock(return_value=True)
    service._do_poll()
    service._do_poll()
    assert service._broadcast.call_count == 1


def test_reference_quote_seeding_corrects_live_change_without_replacing_live_price():
    service = MarketDataService()
    service.latest_quotes["AAA"] = {
        "ticker": "AAA",
        "price": 102.0,
        "change": 0.0,
        "change_percent": 0.0,
        "volume": 20,
        "previous_close": 102.0,
    }
    service._broadcast = MagicMock(return_value=True)

    assert service.seed_reference_quotes([
        {"ticker": "AAA", "current_price": 101.0, "previous_close": 100.0, "volume": 10}
    ]) == 1
    assert service.latest_quotes["AAA"] == {
        "ticker": "AAA",
        "price": 102.0,
        "change": 2.0,
        "change_percent": 2.0,
        "volume": 20,
        "previous_close": 100.0,
    }
    service._broadcast.assert_called_once_with(service.latest_quotes["AAA"])


def test_poll_does_not_turn_sequential_ticks_into_daily_change():
    service = MarketDataService()
    service.subscribe(["AAA"])
    service._download_batch = lambda _batch: pd.DataFrame({"Close": [101.0], "Volume": [1]})
    service._do_poll()
    assert service.latest_quotes["AAA"]["previous_close"] is None
    assert service.latest_quotes["AAA"]["change_percent"] is None

    service._download_batch = lambda _batch: pd.DataFrame({"Close": [102.0], "Volume": [2]})
    service._do_poll()
    assert service.latest_quotes["AAA"]["previous_close"] is None
    assert service.latest_quotes["AAA"]["change_percent"] is None


def test_sequential_ticks_continue_using_provider_previous_close():
    index = pd.DatetimeIndex([
        "2026-08-03 15:59:00-04:00",
        "2026-08-04 09:30:00-04:00",
    ])
    first = pd.DataFrame(
        {
            "Open": [99.0, 101.0],
            "High": [100.0, 102.0],
            "Low": [98.0, 100.5],
            "Close": [100.0, 101.5],
            "Volume": [10, 20],
        },
        index=index,
    )
    service = MarketDataService()
    service.subscribe(["SPY"])
    service._download_batch = lambda _batch: first

    service._do_poll()
    assert service.latest_quotes["SPY"]["previous_close"] == 100.0
    assert service.latest_quotes["SPY"]["change_percent"] == 1.5

    service._download_batch = lambda _batch: pd.DataFrame(
        {"Close": [102.0], "Volume": [30]}
    )
    service._do_poll()

    assert service.latest_quotes["SPY"]["previous_close"] == 100.0
    assert service.latest_quotes["SPY"]["change"] == 2.0
    assert service.latest_quotes["SPY"]["change_percent"] == 2.0
    assert service.latest_quotes["SPY"]["open_price"] == 101.0
    assert service.latest_quotes["SPY"]["day_low"] == 100.5
    assert service.latest_quotes["SPY"]["day_high"] == 102.0


def test_single_flight_rejects_overlapping_cycle():
    service = MarketDataService()
    service._poll_guard.acquire()
    try:
        assert service._do_poll() is False
    finally:
        service._poll_guard.release()


def test_start_to_start_delay_jitter_backoff_and_recovery(monkeypatch):
    service = MarketDataService()
    monkeypatch.setenv("LIVE_PRICE_POLL_S", "15")
    monkeypatch.setenv("MARKET_DATA_JITTER_S", "2")
    monkeypatch.setenv("MARKET_DATA_BACKOFF_INITIAL_S", "5")
    with patch("backend.services.market_data_service.time.monotonic", return_value=104.0), patch(
        "backend.services.market_data_service.random.uniform", return_value=1.0
    ):
        assert service._next_delay(100.0, True) == 12.0
        assert service._next_delay(100.0, False) == 2.0
        assert service._next_delay(100.0, False) == 7.0
        assert service._next_delay(100.0, True) == 12.0
        assert service._backoff_s == 0.0


def test_regular_market_session_boundaries():
    assert not is_regular_market_session(datetime(2026, 7, 21, 9, 29, tzinfo=ET))
    assert is_regular_market_session(datetime(2026, 7, 21, 9, 30, tzinfo=ET))
    assert not is_regular_market_session(datetime(2026, 7, 21, 16, 0, tzinfo=ET))
    assert not is_regular_market_session(datetime(2026, 7, 25, 12, 0, tzinfo=ET))


def test_stop_signals_and_joins_thread():
    service = MarketDataService()
    thread = MagicMock()
    service._thread = thread
    service._running = True
    service.stop()
    assert service._stop_event.is_set()
    thread.join.assert_called_once_with(timeout=5)
