"""Deterministic tests for batched regular-market polling."""
from datetime import datetime
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pandas as pd

from backend.services.market_data_service import (
    MarketDataService,
    is_regular_market_session,
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