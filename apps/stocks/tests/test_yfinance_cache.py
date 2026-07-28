"""Tests for non-fatal yfinance writable-cache configuration."""

from __future__ import annotations

from pathlib import Path

from backend.services import yfinance_cache, yfinance_fallback


def test_cache_directory_is_created_and_configuration_is_idempotent(monkeypatch, tmp_path):
    calls: list[str] = []

    class FakeYFinance:
        @staticmethod
        def set_tz_cache_location(path):
            calls.append(path)

    cache_dir = tmp_path / "nested" / "yf"
    monkeypatch.setenv("YFINANCE_CACHE_DIR", str(cache_dir))
    yfinance_cache._reset_yfinance_cache_state_for_tests()

    assert yfinance_cache.configure_yfinance_cache(FakeYFinance) is True
    assert yfinance_cache.configure_yfinance_cache(FakeYFinance) is True
    assert cache_dir.is_dir()
    assert calls == [str(cache_dir)]


def test_cache_creation_failure_does_not_block_quote_retrieval(monkeypatch):
    class FakeTicker:
        ticker = "AAPL"
        holdings = None
        info = {
            "quoteType": "EQUITY",
            "shortName": "Apple Inc.",
            "currentPrice": 100,
            "previousClose": 99,
        }

        def __init__(self, _ticker):
            pass

    def fail_mkdir(*_args, **_kwargs):
        raise PermissionError("read-only filesystem")

    yfinance_cache._reset_yfinance_cache_state_for_tests()
    monkeypatch.setattr(Path, "mkdir", fail_mkdir)
    assert yfinance_cache.configure_yfinance_cache(object()) is False

    monkeypatch.setattr(yfinance_fallback, "configure_yfinance_cache", lambda _yf: False)
    monkeypatch.setattr(yfinance_fallback.yf, "Ticker", FakeTicker)
    result = yfinance_fallback.get_stock_price_yf("AAPL")

    assert result is not None
    assert result["current_price"] == 100
    assert result["company_name"] == "Apple Inc."
