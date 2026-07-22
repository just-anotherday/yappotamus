"""Batched, session-aware Yahoo quote polling for WebSocket clients."""
import asyncio
import logging
import math
import random
import threading
import time
from asyncio import AbstractEventLoop
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Set
from zoneinfo import ZoneInfo

import yfinance as yf

from backend.config.polling_settings import polling_settings as settings

logger = logging.getLogger(__name__)
ET = ZoneInfo("US/Eastern")
_event_loop: Optional[AbstractEventLoop] = None


def set_event_loop(loop: AbstractEventLoop) -> None:
    global _event_loop
    _event_loop = loop


def get_event_loop() -> Optional[AbstractEventLoop]:
    return _event_loop


def is_regular_market_session(now_et: Optional[datetime] = None) -> bool:
    now = now_et or datetime.now(tz=ET)
    minutes = now.hour * 60 + now.minute
    return now.weekday() < 5 and 9 * 60 + 30 <= minutes < 16 * 60


def _chunks(values: List[str], size: int) -> Iterable[List[str]]:
    for index in range(0, len(values), size):
        yield values[index:index + size]


def _finite_positive(value: Any) -> Optional[float]:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) and result > 0 else None


def parse_download_quotes(frame: Any, tickers: List[str]) -> Dict[str, Dict[str, Any]]:
    """Parse single- or multi-symbol yfinance download frames independently."""
    if frame is None or getattr(frame, "empty", True):
        return {}
    results: Dict[str, Dict[str, Any]] = {}
    multi = getattr(frame.columns, "nlevels", 1) > 1
    level_zero = set(frame.columns.get_level_values(0)) if multi else set(frame.columns)
    field_first = "Close" in level_zero
    for ticker in tickers:
        try:
            symbol_frame = frame.xs(ticker, axis=1, level=1 if field_first else 0) if multi else frame
            closes = symbol_frame["Close"].dropna()
            if closes.empty:
                continue
            price = _finite_positive(closes.iloc[-1])
            if price is None:
                continue
            volumes = symbol_frame["Volume"].dropna() if "Volume" in symbol_frame else []
            volume = int(volumes.iloc[-1]) if len(volumes) else 0
            results[ticker] = {"price": price, "volume": volume}
        except (KeyError, TypeError, ValueError, IndexError):
            continue
    return results


class MarketDataService:
    _instance: Optional["MarketDataService"] = None
    _instance_lock = threading.Lock()
    QUOTE_CACHE_MAX_SIZE = settings.QUOTE_CACHE_MAX_SIZE

    def __init__(self) -> None:
        self._running = False
        self._stop_event = threading.Event()
        self._poll_guard = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._ticker_lock = threading.Lock()
        self._subscribed_tickers: Set[str] = set()
        self.latest_quotes: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()
        self._connection_manager: Optional[Any] = None
        self._backoff_s = 0.0

    @classmethod
    def get_instance(cls) -> "MarketDataService":
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def set_connection_manager(self, cm: Any) -> None:
        self._connection_manager = cm

    def subscribe(self, tickers: List[str]) -> None:
        normalized = {ticker.strip().upper() for ticker in tickers if ticker.strip()}
        with self._ticker_lock:
            new_tickers = normalized - self._subscribed_tickers
            self._subscribed_tickers.update(new_tickers)
        if new_tickers:
            logger.info("[MarketData] subscribed=%d", len(new_tickers))

    def unsubscribe(self, tickers: List[str]) -> None:
        with self._ticker_lock:
            self._subscribed_tickers.difference_update(t.strip().upper() for t in tickers)
        self.prune_quotes()

    def prune_quotes(self) -> None:
        with self._ticker_lock:
            subscribed = set(self._subscribed_tickers)
        with self._lock:
            for ticker in set(self.latest_quotes) - subscribed:
                self.latest_quotes.pop(ticker, None)
            while len(self.latest_quotes) > self.QUOTE_CACHE_MAX_SIZE:
                self.latest_quotes.pop(next(iter(self.latest_quotes)))

    def get_latest_quotes(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            return dict(self.latest_quotes)

    def get_quote(self, ticker: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self.latest_quotes.get(ticker.strip().upper())

    def start(self, default_tickers: Optional[List[str]] = None) -> None:
        if self._running:
            logger.warning("[MarketData] already_running=true")
            return
        self.subscribe(default_tickers or [])
        self._stop_event.clear()
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True, name="market-data-poller")
        self._thread.start()
        logger.info("[MarketData] started=true interval_s=%s batch_size=%s", settings.LIVE_PRICE_POLL_S, settings.MARKET_DATA_BATCH_SIZE)

    def stop(self) -> None:
        self._running = False
        self._stop_event.set()
        thread = self._thread
        if thread and thread is not threading.current_thread():
            thread.join(timeout=5)
        self._thread = None
        logger.info("[MarketData] stopped=true")

    def _next_delay(self, cycle_started: float, success: bool) -> float:
        if success:
            self._backoff_s = 0.0
            target = float(settings.LIVE_PRICE_POLL_S)
        else:
            self._backoff_s = min(settings.MARKET_DATA_BACKOFF_MAX_S, self._backoff_s * 2 if self._backoff_s else settings.MARKET_DATA_BACKOFF_INITIAL_S)
            target = self._backoff_s
        return max(0.0, target + random.uniform(0, settings.MARKET_DATA_JITTER_S) - (time.monotonic() - cycle_started))

    def _poll_loop(self) -> None:
        while self._running:
            started = time.monotonic()
            success = self._do_poll() if is_regular_market_session() else True
            self._stop_event.wait(self._next_delay(started, success))

    def _download_batch(self, tickers: List[str]):
        return yf.download(tickers=tickers if len(tickers) > 1 else tickers[0], period="1d", interval="1m", group_by="column", auto_adjust=False, prepost=False, progress=False, threads=True, timeout=10)

    def _do_poll(self) -> bool:
        if not self._poll_guard.acquire(blocking=False):
            logger.warning("[MarketData] cycle=regular skipped=overlap")
            return False
        started = time.monotonic()
        with self._ticker_lock:
            tickers = sorted(self._subscribed_tickers)
        valid = missing = broadcasts = failures = 0
        try:
            for batch in _chunks(tickers, settings.MARKET_DATA_BATCH_SIZE):
                try:
                    parsed = parse_download_quotes(self._download_batch(batch), batch)
                except Exception as exc:
                    failures += len(batch)
                    logger.warning("[MarketData] cycle=regular provider_failure=%s symbols=%d", type(exc).__name__, len(batch))
                    continue
                missing += len(batch) - len(parsed)
                for ticker, values in parsed.items():
                    valid += 1
                    with self._lock:
                        previous = self.latest_quotes.get(ticker, {})
                        previous_close = previous.get("previous_close") or previous.get("price") or values["price"]
                        change = round(values["price"] - previous_close, 4)
                        quote = {"ticker": ticker, "price": values["price"], "change": change, "change_percent": round(change / previous_close * 100, 4) if previous_close else 0.0, "volume": values["volume"], "previous_close": previous_close}
                        changed = quote != previous
                        self.latest_quotes[ticker] = quote
                    if changed and self._broadcast(quote):
                        broadcasts += 1
            success = failures == 0 and (not tickers or valid > 0)
            logger.info("[MarketData] cycle=regular duration_ms=%.1f requested=%d valid=%d missing=%d failures=%d broadcasts=%d backoff_s=%.1f", (time.monotonic() - started) * 1000, len(tickers), valid, missing, failures, broadcasts, 0.0 if success else (self._backoff_s or settings.MARKET_DATA_BACKOFF_INITIAL_S))
            return success
        finally:
            self._poll_guard.release()

    def _broadcast(self, quote: Dict[str, Any]) -> bool:
        loop = get_event_loop()
        if not loop or not self._connection_manager:
            return False
        asyncio.run_coroutine_threadsafe(self._connection_manager.broadcast(quote), loop)
        return True