"""Validated configuration used only by market-data pollers and provider limits."""
import os
from typing import Callable, TypeVar


Number = TypeVar("Number", int, float)


def _number(
    name: str,
    default: str,
    cast: Callable[[str], Number],
    *,
    minimum: Number,
    maximum: Number | None = None,
) -> Number:
    raw = os.getenv(name, default)
    try:
        value = cast(raw)
    except (TypeError, ValueError) as exc:
        raise EnvironmentError(f"{name} must be a valid {cast.__name__}") from exc
    if value < minimum:
        raise EnvironmentError(f"{name} must be >= {minimum}")
    if maximum is not None and value > maximum:
        raise EnvironmentError(f"{name} must be <= {maximum}")
    return value


class PollingSettings:
    @property
    def LIVE_PRICE_POLL_S(self) -> int:
        return _number("LIVE_PRICE_POLL_S", "15", int, minimum=1)

    @property
    def MARKET_DATA_BATCH_SIZE(self) -> int:
        return _number("MARKET_DATA_BATCH_SIZE", "50", int, minimum=1, maximum=200)

    @property
    def PM_FETCH_INTERVAL_S(self) -> int:
        return _number("PM_FETCH_INTERVAL_S", "30", int, minimum=5)

    @property
    def PM_MAX_CONCURRENCY(self) -> int:
        return _number("PM_MAX_CONCURRENCY", "3", int, minimum=1, maximum=10)

    @property
    def MARKET_DATA_BACKOFF_INITIAL_S(self) -> float:
        return _number("MARKET_DATA_BACKOFF_INITIAL_S", "5", float, minimum=0.1)

    @property
    def MARKET_DATA_BACKOFF_MAX_S(self) -> float:
        maximum = _number("MARKET_DATA_BACKOFF_MAX_S", "120", float, minimum=1)
        if maximum < self.MARKET_DATA_BACKOFF_INITIAL_S:
            raise EnvironmentError("MARKET_DATA_BACKOFF_MAX_S must be >= MARKET_DATA_BACKOFF_INITIAL_S")
        return maximum

    @property
    def MARKET_DATA_JITTER_S(self) -> float:
        return _number("MARKET_DATA_JITTER_S", "1.0", float, minimum=0, maximum=30)

    @property
    def FINNHUB_REQUESTS_PER_MINUTE(self) -> int:
        # Finnhub Free allows 60 REST requests/minute.  Keep a 25% reserve for
        # interactive traffic, retries, clock skew, and future call sites.
        return _number("FINNHUB_REQUESTS_PER_MINUTE", "45", int, minimum=1, maximum=45)

    @property
    def FINNHUB_MAX_RETRY_ATTEMPTS(self) -> int:
        return _number("FINNHUB_MAX_RETRY_ATTEMPTS", "3", int, minimum=1, maximum=5)

    @property
    def FINNHUB_BACKOFF_INITIAL_S(self) -> float:
        return _number("FINNHUB_BACKOFF_INITIAL_S", "1.0", float, minimum=0.1, maximum=30)

    @property
    def FINNHUB_BACKOFF_MAX_S(self) -> float:
        maximum = _number("FINNHUB_BACKOFF_MAX_S", "30.0", float, minimum=1, maximum=120)
        if maximum < self.FINNHUB_BACKOFF_INITIAL_S:
            raise EnvironmentError("FINNHUB_BACKOFF_MAX_S must be >= FINNHUB_BACKOFF_INITIAL_S")
        return maximum

    @property
    def FINNHUB_RETRY_JITTER_S(self) -> float:
        return _number("FINNHUB_RETRY_JITTER_S", "0.5", float, minimum=0, maximum=10)

    @property
    def FINNHUB_MAX_RETRY_AFTER_S(self) -> float:
        # Together with <=5 attempts and the SDK's 10s request timeout, this
        # stays below the minimum 10-minute ingestion lease before renewal.
        return _number("FINNHUB_MAX_RETRY_AFTER_S", "120", float, minimum=1, maximum=120)

    @property
    def YF_PER_TICKER_DELAY_S(self) -> float:
        return _number("YF_PER_TICKER_DELAY_S", "0.6", float, minimum=0)

    @property
    def QUOTE_CACHE_MAX_SIZE(self) -> int:
        return _number("QUOTE_CACHE_MAX_SIZE", "256", int, minimum=1)

    def validate(self) -> None:
        self.LIVE_PRICE_POLL_S
        self.MARKET_DATA_BATCH_SIZE
        self.PM_FETCH_INTERVAL_S
        self.PM_MAX_CONCURRENCY
        self.MARKET_DATA_BACKOFF_INITIAL_S
        self.MARKET_DATA_BACKOFF_MAX_S
        self.MARKET_DATA_JITTER_S
        self.FINNHUB_REQUESTS_PER_MINUTE
        self.FINNHUB_MAX_RETRY_ATTEMPTS
        self.FINNHUB_BACKOFF_INITIAL_S
        self.FINNHUB_BACKOFF_MAX_S
        self.FINNHUB_RETRY_JITTER_S
        self.FINNHUB_MAX_RETRY_AFTER_S
        self.YF_PER_TICKER_DELAY_S
        self.QUOTE_CACHE_MAX_SIZE


polling_settings = PollingSettings()
