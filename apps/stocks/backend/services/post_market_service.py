"""Post-market price fetching service using yfinance.

Fetches after-hours prices at 4:00 PM ET on market days and caches them
for inclusion in watchlist responses. Prices are cached until the next
market open (9:30 AM ET) when they expire.
"""
import asyncio
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging
import math
import random
import threading
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Any, Callable, Dict, Optional

import yfinance as yf

from backend.config.polling_settings import polling_settings
from backend.config.settings import settings as app_settings
from backend.services.yfinance_cache import configure_yfinance_cache
from backend.services.yfinance_fallback import (
    _record_yfinance_outage_failure,
    _yfinance_cooldown_status,
)
from backend.services.market_data_observability import normalize_correlation_id
from backend.services.memory_diagnostics import log_memory

logger = logging.getLogger(__name__)

__all__ = ["PostMarketService", "_post_market_fetch_loop"]

# Rate limiting: delay between individual ticker fetches (heavy .info endpoint)
PM_FETCH_INTERVAL_S = polling_settings.PM_FETCH_INTERVAL_S


def _next_poll_delay(cycle_started: float, success: bool, current_backoff: float) -> tuple[float, float]:
    """Return start-to-start delay and updated backoff for extended polling."""
    if success:
        backoff = 0.0
        target = float(polling_settings.PM_FETCH_INTERVAL_S)
    else:
        backoff = min(
            polling_settings.MARKET_DATA_BACKOFF_MAX_S,
            current_backoff * 2 if current_backoff else polling_settings.MARKET_DATA_BACKOFF_INITIAL_S,
        )
        target = backoff
    delay = max(
        0.0,
        target + random.uniform(0, polling_settings.MARKET_DATA_JITTER_S) - (time.monotonic() - cycle_started),
    )
    return delay, backoff


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
    @staticmethod
    def _valid_price(value: Any) -> float | None:
        """Return a finite positive market price, rejecting booleans and metadata."""
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        price = float(value)
        return price if math.isfinite(price) and price > 0 else None

    @classmethod
    def _extract_extended_hours_prices(
        cls,
        info: Dict[str, Any],
        now_et: datetime,
    ) -> tuple[float | None, float | None]:
        """Extract the session-appropriate extended quote and regular reference price."""
        reference_price = next(
            (
                price
                for key in ("regularMarketPrice", "currentPrice", "lastPrice")
                if (price := cls._valid_price(info.get(key))) is not None
            ),
            None,
        )
        if reference_price is None:
            return None, None

        minutes = now_et.hour * 60 + now_et.minute
        market_open = 9 * 60 + 30
        market_close = 16 * 60
        quote_key = "preMarketPrice" if minutes < market_open else "postMarketPrice" if minutes >= market_close else None
        extended_price = cls._valid_price(info.get(quote_key)) if quote_key else None

        # Extended-hours quotes can move sharply, but metadata/malformed values should
        # never be allowed to masquerade as a tradable price.
        if extended_price is not None and not (reference_price * 0.2 <= extended_price <= reference_price * 5):
            extended_price = None

        return extended_price, reference_price

    def _get_post_market_data_for_ticker(
        self,
        ticker: str,
        now_et: datetime | None = None,
        correlation_id: str = "none",
        on_cooldown_skip: Callable[[], None] | None = None,
    ) -> tuple[float | None, float | None]:
        """Fetch extended-hours and regular-market prices for a single ticker.

        Returns (extended_price, regular_price) or (None, regular_price) when no
        valid quote exists for the current pre-market/post-market session.
        """
        try:
            configure_yfinance_cache(yf)
            cooldown_active, failure_class = _yfinance_cooldown_status()
            if cooldown_active:
                if on_cooldown_skip is not None:
                    on_cooldown_skip()
                logger.debug(
                    "[PostMarket] event=yfinance_cooldown_skip correlation_id=%s "
                    "symbol=%s failure_class=%s",
                    correlation_id,
                    ticker,
                    failure_class,
                )
                return None, None

            tkr = yf.Ticker(ticker)
            info = tkr.info  # dict-based .info is more stable than .fast_info
            effective_now = now_et or datetime.now(tz=ZoneInfo("US/Eastern"))
            return self._extract_extended_hours_prices(info, effective_now)
        except Exception as e:
            failure_class = _record_yfinance_outage_failure(e)
            logger.warning(
                "[PostMarket] event=provider_attempt correlation_id=%s symbol=%s "
                "provider=yf success=false exception_type=%s failure_class=%s",
                correlation_id,
                ticker,
                type(e).__name__,
                failure_class,
            )
            return None, None

    def fetch_all(self, tickers: list[str]) -> None:
        """Fetch extended-hours metadata with conservative bounded concurrency."""
        started = time.monotonic()
        correlation_id = normalize_correlation_id(None)
        updated = failed = missing = cooldown_skips = 0

        def fetch(ticker: str):
            def record_cooldown_skip() -> None:
                nonlocal cooldown_skips
                with self._lock:
                    cooldown_skips += 1

            return ticker, self._get_post_market_data_for_ticker(
                ticker,
                correlation_id=correlation_id,
                on_cooldown_skip=record_cooldown_skip,
            )

        with ThreadPoolExecutor(max_workers=polling_settings.PM_MAX_CONCURRENCY, thread_name_prefix="extended-hours") as executor:
            futures = {executor.submit(fetch, ticker): ticker for ticker in tickers}
            for future in as_completed(futures):
                ticker = futures[future]
                definitive = False
                try:
                    ticker, (pm_price, last_price) = future.result()
                    definitive = last_price is not None
                except Exception as e:
                    failed += 1
                    logger.warning(
                        "[PostMarket] correlation_id=%s provider_failure=%s ticker=%s",
                        correlation_id,
                        type(e).__name__,
                        ticker,
                    )
                    continue

                if not pm_price or not last_price:
                    missing += 1
                    # A valid regular reference with no session quote is definitive;
                    # transport/provider failures retain the last known valid quote.
                    if definitive:
                        with self._lock:
                            self._post_market_prices.pop(ticker, None)
                    continue

                pm_change = round(pm_price - last_price, 4)
                pm_change_pct = round((pm_price - last_price) / last_price * 100, 4)
                with self._lock:
                    self._post_market_prices[ticker] = {
                        "post_market_price": round(pm_price, 2),
                        "post_market_change": pm_change,
                        "post_market_change_percent": pm_change_pct,
                    }
                updated += 1

        cooldown_active, _ = _yfinance_cooldown_status()
        logger.info(
            "[PostMarket] cycle=extended correlation_id=%s duration_ms=%.1f requested=%d valid=%d missing=%d failures=%d cooldown_skips=%d cooldown_active=%s concurrency=%d",
            correlation_id,
            (time.monotonic() - started) * 1000, len(tickers), updated, missing, failed,
            cooldown_skips,
            cooldown_active,
            polling_settings.PM_MAX_CONCURRENCY,
        )

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
    backoff_s = 0.0

    while True:
        now_et = datetime.now(tz=ZoneInfo("US/Eastern"))
        is_weekday = now_et.weekday() < 5

        # Determine if currently in regular market hours (9:30 AM - 4 PM)
        is_market_hours = is_weekday and (
            (now_et.hour > 9 and now_et.hour < 16) or
            (now_et.hour == 9 and now_et.minute >= 30) or
            (now_et.hour == 16 and now_et.minute == 0)
        )

        if is_weekday and now_et.hour == 9 and now_et.minute == 30:
            pm_service.clear_cache()

        # Fetch during after-hours (outside regular market hours) OR on weekends.
        # Weekends are treated as after-hours since yfinance has no new data but
        # the in-memory cache may be empty after a restart.
        is_after_hours = (is_weekday and not is_market_hours) or (not is_weekday)
        cycle_started = time.monotonic()
        success = True
        if is_after_hours:
            tickers_list = []
            try:
                async with get_session_factory() as session:
                    from backend.services.watchlist_service import get_all_tickers
                    tickers_list = await get_all_tickers(session)
                if tickers_list:
                    log_memory(
                        "post_market_cycle_start",
                        logger_to_use=logger,
                        enabled=app_settings.MEMORY_DIAGNOSTICS_ENABLED,
                        extra={"symbol_count": len(tickers_list)},
                    )
                    try:
                        await asyncio.get_running_loop().run_in_executor(
                            None, pm_service.fetch_all, tickers_list
                        )
                    finally:
                        log_memory(
                            "post_market_cycle_complete",
                            logger_to_use=logger,
                            enabled=app_settings.MEMORY_DIAGNOSTICS_ENABLED,
                            extra={"symbol_count": len(tickers_list)},
                        )
            except asyncio.CancelledError:
                raise
            except Exception as e:
                success = False
                logger.warning("[PostMarket] cycle=extended provider_failure=%s", type(e).__name__)

        delay, backoff_s = _next_poll_delay(cycle_started, success, backoff_s)
        await asyncio.sleep(delay)
