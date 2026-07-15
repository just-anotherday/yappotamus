"""Post-market price fetching service using yfinance.

Fetches after-hours prices at 4:00 PM ET on market days and caches them
for inclusion in watchlist responses. Prices are cached until the next
market open (9:30 AM ET) when they expire.
"""
import asyncio
import logging
import os
import threading
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Any, Dict, Optional

import yfinance as yf

logger = logging.getLogger(__name__)

__all__ = ["PostMarketService", "_post_market_fetch_loop"]

# Rate limiting: delay between individual ticker fetches (heavy .info endpoint)
PER_TICKER_DELAY = float(os.environ.get("PM_PER_TICKER_DELAY_S", "1.0"))
# Minimum interval between full post-market fetch cycles
PM_FETCH_INTERVAL_S = int(os.environ.get("PM_FETCH_INTERVAL_S", "10"))


class PostMarketService:
    """Singleton service that fetches post-market prices via yfinance.

    Designed to be triggered by an APScheduler job at 4:00 PM ET on weekdays.
    Fetched prices are cached in-memory and served to the watchlist endpoint.
    """

    _instance: Optional["PostMarketService"] = None
    _instance_lock = threading.Lock()

    def __init__(self) -> None:
        self._post_market_prices: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()

    @classmethod
    def get_instance(cls) -> "PostMarketService":
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    # ------------------------------------------------------------------
    # Fetching
    # ------------------------------------------------------------------
    def _get_post_market_data_for_ticker(self, ticker: str) -> tuple[float | None, float | None]:
        """Fetch post-market price and regular market price for a single ticker.

        Try multiple yfinance property paths since the API has changed over versions.
        Returns (pm_price, last_price) or (None, None) on failure.
        """
        try:
            tkr = yf.Ticker(ticker)
            info = tkr.info  # dict-based .info is more stable than .fast_info

            # Try multiple known property names for post-market price
            pm_price = None
            for key in ("postMarketPrice", "postMarket", "priceHint"):
                val = info.get(key)
                if val and isinstance(val, (int, float)) and val > 0:
                    pm_price = float(val)
                    break

            # Current/last price
            last_price = None
            for key in ("regularMarketPrice", "currentPrice", "lastPrice", "price"):
                val = info.get(key)
                if val and isinstance(val, (int, float)) and val > 0:
                    last_price = float(val)
                    break

            return pm_price, last_price
        except Exception as e:
            logger.warning("[PostMarket] yfinance info fetch failed for %s: %s", ticker, e)
            return None, None

    def fetch_all(self, tickers: list[str]) -> None:
        """Fetch post-market prices for all given tickers via yfinance."""
        logger.info("[PostMarket] Fetching after-hours prices for %d tickers", len(tickers))
        updated = 0
        failed = 0

        for i, ticker in enumerate(tickers):
            try:
                pm_price, last_price = self._get_post_market_data_for_ticker(ticker)

                if not pm_price or not last_price:
                    logger.debug(
                        "[PostMarket] %s has no post-market data (pm=%s, last=%s)",
                        ticker, pm_price, last_price,
                    )
                    continue

                pm_change = round(pm_price - last_price, 4)
                pm_change_pct = round((pm_price - last_price) / last_price * 100, 4) if last_price > 0 else 0.0

                with self._lock:
                    self._post_market_prices[ticker] = {
                        "post_market_price": round(pm_price, 2),
                        "post_market_change": pm_change,
                        "post_market_change_percent": pm_change_pct,
                    }
                updated += 1
                # Per-ticker detail at DEBUG; only log if price moved > 0.5%
                if abs(pm_change_pct) > 0.5:
                    logger.info(
                        "[PostMarket] %s after-hours: $%.2f (%+.2f%%)",
                        ticker, pm_price, pm_change_pct,
                    )
                else:
                    logger.debug(
                        "[PostMarket] %s after-hours: $%.2f (%+.2f%%)",
                        ticker, pm_price, pm_change_pct,
                    )

            except Exception as e:
                failed += 1
                logger.warning("[PostMarket] Failed to fetch %s: %s", ticker, e)

            # Rate limiting: delay between individual ticker fetches
            if i < len(tickers) - 1:
                time.sleep(PER_TICKER_DELAY)

        logger.info("[PostMarket] Updated %d / %d tickers (%d failed)", updated, len(tickers), failed)

    # ------------------------------------------------------------------
    # Thread-safe read accessors
    # ------------------------------------------------------------------
    def get_post_market_data(self) -> Dict[str, Dict[str, Any]]:
        """Return a snapshot of all cached post-market data (thread-safe copy)."""
        with self._lock:
            return dict(self._post_market_prices)

    def get_post_market_price(self, ticker: str) -> Optional[Dict[str, Any]]:
        """Return the latest post-market data for a single ticker (thread-safe)."""
        with self._lock:
            return self._post_market_prices.get(ticker)

    def clear_cache(self) -> None:
        """Clear all cached post-market prices (called at market open)."""
        with self._lock:
            self._post_market_prices.clear()
        logger.info("[PostMarket] Cache cleared.")


async def _post_market_fetch_loop(get_session_factory) -> None:
    """Async loop that polls periodically; fetches post-market prices during after-hours (4PM until next day 9:30AM ET) on weekdays."""
    pm_service = PostMarketService.get_instance()
    _last_fetch = None  # Track last fetch to refresh periodically during after-hours

    while True:
        now_et = datetime.now(tz=ZoneInfo("US/Eastern"))
        is_weekday = now_et.weekday() < 5

        # Determine if currently in regular market hours (9:30 AM - 4 PM)
        is_market_hours = is_weekday and (
            (now_et.hour > 9 and now_et.hour < 16) or
            (now_et.hour == 9 and now_et.minute >= 30) or
            (now_et.hour == 16 and now_et.minute == 0)
        )

        # Clear cache at 9:30 AM ET on weekdays (market open)
        if is_weekday and now_et.hour == 9 and now_et.minute == 30:
            pm_service.clear_cache()
            _last_fetch = None

        # Fetch during after-hours (outside regular market hours) OR on weekends.
        # Weekends are treated as after-hours since yfinance has no new data but
        # the in-memory cache may be empty after a restart.
        is_after_hours = (is_weekday and not is_market_hours) or (not is_weekday)
        if is_after_hours:
            should_fetch = False
            if _last_fetch is None:
                # First fetch after 4PM, early morning, or on weekend
                should_fetch = True
            elif (now_et - _last_fetch).total_seconds() >= PM_FETCH_INTERVAL_S:
                # Refresh every PM_FETCH_INTERVAL_S seconds
                should_fetch = True

            if should_fetch:
                try:
                    async with get_session_factory() as session:
                        from backend.services.watchlist_service import get_all_tickers
                        tickers = await get_all_tickers(session)
                    if tickers:
                        loop = asyncio.get_running_loop()
                        await loop.run_in_executor(None, pm_service.fetch_all, tickers)
                        _last_fetch = now_et
                except Exception as e:
                    logger.error("[PostMarket] Fetch failed: %s", e)

        await asyncio.sleep(PM_FETCH_INTERVAL_S)
