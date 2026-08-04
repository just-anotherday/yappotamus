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
from backend.services.yfinance_cache import configure_yfinance_cache

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


def _regular_session_date(value: Any) -> Any:
    """Return the US regular-session date for a timestamp, otherwise ``None``."""
    if not all(hasattr(value, field) for field in ("date", "hour", "minute")):
        return None
    local_value = value
    if getattr(value, "tzinfo", None) is not None:
        try:
            local_value = value.tz_convert(ET)
        except AttributeError:
            local_value = value.astimezone(ET)
    minutes = local_value.hour * 60 + local_value.minute
    if 9 * 60 + 30 <= minutes < 16 * 60:
        return local_value.date()
    return None


def merge_live_quote_payload(
    payload: Dict[str, Any], quote: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    """Overlay trustworthy live quote fields without altering fundamentals.

    A price-only quote is still useful, but it cannot establish a session
    baseline.  An official close may come from either the live provider or the
    already-normalized REST payload; the previous WebSocket price is never a
    candidate.
    """
    if not quote:
        return dict(payload)

    merged = dict(payload)
    current_price = (
        _finite_positive(quote.get("current_price"))
        or _finite_positive(quote.get("price"))
        or _finite_positive(payload.get("current_price"))
    )
    previous_close = (
        _finite_positive(quote.get("previous_close"))
        or _finite_positive(payload.get("previous_close"))
    )
    merged["current_price"] = current_price
    merged["previous_close"] = previous_close

    for field in ("open_price", "day_low", "day_high"):
        merged[field] = (
            _finite_positive(quote.get(field))
            or _finite_positive(payload.get(field))
        )

    if current_price is not None and previous_close is not None:
        change = current_price - previous_close
        merged["change"] = change
        merged["change_percent"] = change / previous_close * 100
    else:
        merged["change"] = None
        merged["change_percent"] = None

    if quote.get("volume") is not None:
        merged["volume"] = quote["volume"]
    for field in (
        "quote_timestamp",
        "previous_close_timestamp",
        "quote_provider",
        "market_session",
    ):
        if quote.get(field) is not None:
            merged[field] = quote[field]

    # These describe the pre-overlay payload.  Let the normalizer recompute
    # availability from the combined quote + fundamental result.
    merged.pop("missing_fields", None)
    merged.pop("data_status", None)
    return merged


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
            index = symbol_frame.index
            if hasattr(index, "duplicated"):
                symbol_frame = symbol_frame.loc[~index.duplicated(keep="last")].sort_index()
            timestamp_index = all(
                hasattr(value, "date") and hasattr(value, "hour")
                for value in symbol_frame.index
            )
            if timestamp_index:
                session_dates = [_regular_session_date(value) for value in symbol_frame.index]
                symbol_frame = symbol_frame.loc[[value is not None for value in session_dates]]
                session_dates = [value for value in session_dates if value is not None]
                if symbol_frame.empty:
                    continue
            else:
                session_dates = []

            closes = symbol_frame["Close"].dropna()
            if closes.empty:
                continue
            price = _finite_positive(closes.iloc[-1])
            if price is None:
                continue
            volumes = symbol_frame["Volume"].dropna() if "Volume" in symbol_frame else []
            volume = int(volumes.iloc[-1]) if len(volumes) else 0
            quote: Dict[str, Any] = {"price": price, "volume": volume}

            # Recent minute bars give us today's session values and the prior
            # trading session's close without another provider call.
            # Range-indexed test/partial frames intentionally remain price-only.
            latest_timestamp = closes.index[-1]
            latest_date = _regular_session_date(latest_timestamp)
            if latest_date is not None:
                current_mask = [value == latest_date for value in session_dates]
                current_session = symbol_frame.loc[current_mask]
                for output_field, source_field, reducer in (
                    ("open_price", "Open", lambda values: values.iloc[0]),
                    ("day_low", "Low", lambda values: values.min()),
                    ("day_high", "High", lambda values: values.max()),
                ):
                    if source_field in current_session:
                        source_values = current_session[source_field].dropna()
                        value = _finite_positive(reducer(source_values)) if not source_values.empty else None
                        if value is not None:
                            quote[output_field] = value
                prior_dates = [value for value in session_dates if value < latest_date]
                if prior_dates and "Close" in symbol_frame:
                    previous_date = max(prior_dates)
                    prior_session = symbol_frame.loc[
                        [value == previous_date for value in session_dates]
                    ]
                    prior_closes = prior_session["Close"].dropna()
                    previous_close = _finite_positive(prior_closes.iloc[-1] if not prior_closes.empty else None)
                    if previous_close is not None:
                        quote["previous_close"] = previous_close
                        quote["previous_close_timestamp"] = str(prior_closes.index[-1])
                quote["quote_timestamp"] = str(latest_timestamp)
                quote["quote_provider"] = "yfinance_download"
                quote["market_session"] = "regular"
            results[ticker] = quote
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

    def seed_reference_quotes(self, items: List[Dict[str, Any]]) -> int:
        """Seed prior-close baselines from the authoritative REST quote response.

        The minute-bar poll stays lightweight while Finnhub's prior close keeps
        WebSocket daily change values accurate. Existing live prices win over
        the slightly older REST price when both are available.
        """
        seeded = 0
        for item in items:
            ticker = str(item.get("ticker") or "").strip().upper()
            previous_close = _finite_positive(item.get("previous_close"))
            if not ticker or previous_close is None:
                continue
            with self._lock:
                previous = self.latest_quotes.get(ticker, {})
                price = _finite_positive(previous.get("price")) or _finite_positive(item.get("current_price"))
                if price is None:
                    continue
                change = price - previous_close
                quote = {
                    **previous,
                    "ticker": ticker,
                    "price": price,
                    "change": change,
                    "change_percent": change / previous_close * 100,
                    "volume": int(previous.get("volume") or item.get("volume") or 0),
                    "previous_close": previous_close,
                }
                changed = quote != previous
                self.latest_quotes[ticker] = quote
            seeded += 1
            if changed:
                self._broadcast(quote)
        return seeded

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
        configure_yfinance_cache(yf)
        return yf.download(tickers=tickers if len(tickers) > 1 else tickers[0], period="5d", interval="1m", group_by="column", auto_adjust=False, prepost=False, progress=False, threads=True, timeout=10)

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
                        previous_close = _finite_positive(values.get("previous_close")) or _finite_positive(previous.get("previous_close"))
                        change = values["price"] - previous_close if previous_close is not None else None
                        quote = {
                            **previous,
                            "ticker": ticker,
                            "symbol": ticker,
                            "price": values["price"],
                            "current_price": values["price"],
                            "change": change,
                            "change_percent": change / previous_close * 100 if previous_close is not None else None,
                            "volume": values["volume"],
                            "previous_close": previous_close,
                        }
                        for field in ("open_price", "day_low", "day_high", "quote_timestamp", "quote_provider", "market_session", "previous_close_timestamp"):
                            if values.get(field) is not None:
                                quote[field] = values[field]
                        changed = quote != previous
                        self.latest_quotes[ticker] = quote
                    if ticker in {"SPY", "QQQ", "IWM", "DIA"}:
                        logger.debug(
                            "[MarketData] event=etf_quote_completeness symbol=%s current_price_present=%s previous_close_present=%s open_present=%s day_range_present=%s daily_change_present=%s provider=%s source_timestamp=%s",
                            ticker, True, previous_close is not None, quote.get("open_price") is not None,
                            quote.get("day_low") is not None and quote.get("day_high") is not None,
                            change is not None, quote.get("quote_provider", "none"), quote.get("quote_timestamp", "none"),
                        )
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
