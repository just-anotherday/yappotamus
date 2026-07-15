# services/market_data_service.py
"""Live price polling service using yfinance (free tier, no API key needed).

Replaces Finnhub WebSocket with periodic yfinance polling.
Polls every 15 seconds for all subscribed tickers and broadcasts
price updates to connected WebSocket clients via ConnectionManager.

Poll interval is configurable via LIVE_PRICE_POLL_S environment variable (default 15s).
"""
import asyncio
import logging
import os
import threading
import time
from asyncio import AbstractEventLoop
from typing import Any, Dict, List, Optional, Set

import yfinance as yf
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

_event_loop: Optional[AbstractEventLoop] = None

POLL_INTERVAL = int(os.environ.get("LIVE_PRICE_POLL_S", "30"))
PER_TICKER_DELAY = float(os.environ.get("YF_PER_TICKER_DELAY_S", "0.6"))  # seconds between individual ticker polls


def set_event_loop(loop: AbstractEventLoop) -> None:
    """Store the main FastAPI event loop reference for cross-thread coroutine scheduling."""
    global _event_loop
    _event_loop = loop


def get_event_loop() -> Optional[AbstractEventLoop]:
    """Retrieve the stored event loop."""
    return _event_loop


class MarketDataService:
    """Singleton service polling yfinance for live prices.

    Runs in a background thread and broadcasts price updates
    to all connected WebSocket clients via ConnectionManager.
    """

    _instance: Optional["MarketDataService"] = None
    _instance_lock = threading.Lock()

    QUOTE_CACHE_MAX_SIZE = int(os.environ.get("QUOTE_CACHE_MAX_SIZE", "256"))

    def __init__(self) -> None:
        self._running = False
        self._ticker_lock = threading.Lock()
        self._subscribed_tickers: Set[str] = set()
        self.latest_quotes: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()
        self._connection_manager: Optional[Any] = None

    # ------------------------------------------------------------------
    # Singleton
    # ------------------------------------------------------------------
    @classmethod
    def get_instance(cls) -> "MarketDataService":
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def set_connection_manager(self, cm: Any) -> None:
        self._connection_manager = cm

    def subscribe(self, tickers: List[str]) -> None:
        """Thread-safe subscribe for additional tickers."""
        with self._ticker_lock:
            new_tickers = set(tickers) - self._subscribed_tickers
            self._subscribed_tickers.update(new_tickers)
            if new_tickers:
                logger.info("[MarketData] Subscribed to %d new tickers", len(new_tickers))

    def unsubscribe(self, tickers: List[str]) -> None:
        """Remove tickers from subscription set and prune their cached quotes."""
        with self._ticker_lock:
            self._subscribed_tickers.difference_update(tickers)
        self.prune_quotes()

    def prune_quotes(self) -> None:
        """Remove quotes for tickers no longer subscribed to, and enforce cache size bound."""
        with self._lock:
            stale = set(self.latest_quotes.keys()) - self._subscribed_tickers
            for ticker in stale:
                self.latest_quotes.pop(ticker, None)

            if len(self.latest_quotes) > self.QUOTE_CACHE_MAX_SIZE:
                excess = len(self.latest_quotes) - self.QUOTE_CACHE_MAX_SIZE
                keys_to_remove = list(self.latest_quotes)[:excess]
                for key in keys_to_remove:
                    del self.latest_quotes[key]

    # ------------------------------------------------------------------
    # Thread-safe read accessors
    # ------------------------------------------------------------------
    def get_latest_quotes(self) -> Dict[str, Dict[str, Any]]:
        """Return a snapshot of all cached quotes (thread-safe copy)."""
        with self._lock:
            return dict(self.latest_quotes)

    def get_quote(self, ticker: str) -> Optional[Dict[str, Any]]:
        """Return the latest quote for a single ticker (thread-safe)."""
        with self._lock:
            return self.latest_quotes.get(ticker)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def start(self, default_tickers: Optional[List[str]] = None) -> None:
        """Start the yfinance polling thread."""
        if self._running:
            logger.warning("[MarketData] Already running. Ignoring duplicate start.")
            return

        tickers = default_tickers or []
        self._running = True
        with self._ticker_lock:
            self._subscribed_tickers.update(tickers)

        threading.Thread(target=self._poll_loop, daemon=True).start()
        logger.info(
            "[MarketData] YFinance poller started for %d tickers (every %ds).",
            len(tickers), POLL_INTERVAL,
        )

    def stop(self) -> None:
        """Stop the polling thread."""
        with self._lock:
            self._running = False
        logger.info("[MarketData] Poller stopped.")

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------
    def _poll_loop(self) -> None:
        """Continuously poll yfinance for price updates."""
        while self._running:
            try:
                self._do_poll()
            except Exception as e:
                logger.error("[MarketData] Poll error: %s", e)

            # Sleep in small increments so we can respond to stop() quickly
            for _ in range(POLL_INTERVAL * 10):
                if not self._running:
                    break
                time.sleep(0.1)

    def _do_poll(self) -> None:
        """Fetch prices from yfinance and broadcast updates for changed tickers."""
        with self._ticker_lock:
            tickers = list(self._subscribed_tickers)

        if not tickers:
            return

        # Use fast_info which is lightweight (single API call per ticker)
        for i, ticker in enumerate(tickers):
            try:
                tkr = yf.Ticker(ticker)
                fi = tkr.fast_info

                current_price = float(fi.get("lastPrice") or 0)
                previous_close = float(fi.get("previousClose") or 0)
                volume = int(fi.get("lastVolume") or 0)

                if not current_price:
                    continue

                with self._lock:
                    prev = self.latest_quotes.get(ticker, {})
                    prev_price = prev.get("price", previous_close)
                    prev_close = prev.get("previous_close", previous_close)

                change = round(current_price - (prev_close or current_price), 4)
                change_pct = (
                    round((current_price - prev_close) / prev_close * 100, 4)
                    if prev_close and prev_close > 0
                    else 0.0
                )

                quote = {
                    "ticker": ticker,
                    "price": current_price,
                    "change": change,
                    "change_percent": change_pct,
                    "volume": volume,
                    "previous_close": prev_close or current_price,
                }

                with self._lock:
                    self.latest_quotes[ticker] = dict(quote)

                logger.debug(
                    "[MarketData] Price update %s: $%.2f (%+.2f%%)",
                    ticker, current_price, change_pct,
                )

                # Broadcast to connected clients
                loop = get_event_loop()
                if loop and self._connection_manager:
                    asyncio.run_coroutine_threadsafe(
                        self._connection_manager.broadcast(quote),
                        loop,
                    )

            except Exception as e:
                logger.warning("[MarketData] Failed to poll %s: %s", ticker, e)
                continue

            # Rate limiting: delay between individual ticker polls to avoid "Too Many Requests"
            if i < len(tickers) - 1:
                time.sleep(PER_TICKER_DELAY)
