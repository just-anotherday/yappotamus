"""Centralized configuration and startup validation for YapVibes Stocks Backend.

Provides:
  1. Single source of truth for all environment variables with defaults.
  2. Fast-fail validation at import time so the application refuses to start
     when required variables are missing.
  3. Convenience properties used by the rest of the codebase.

Usage:
    from backend.config.settings import settings
    db_url = settings.DATABASE_URL
"""

import logging
import os
import re
from functools import cached_property
from typing import List, Optional

logger = logging.getLogger(__name__)


class Settings:
    _TICKER_PATTERN = re.compile(r"^[A-Z][A-Z0-9.-]{0,19}$")

    @staticmethod
    def _number(name: str, default: str, cast, *, minimum=None, maximum=None):
        """Read and range-check a numeric environment variable."""
        raw = os.getenv(name, default)
        try:
            value = cast(raw)
        except (TypeError, ValueError) as exc:
            raise EnvironmentError(f"{name} must be a valid {cast.__name__}") from exc
        if minimum is not None and value < minimum:
            raise EnvironmentError(f"{name} must be >= {minimum}")
        if maximum is not None and value > maximum:
            raise EnvironmentError(f"{name} must be <= {maximum}")
        return value

    @property
    def APP_VERSION(self) -> str:
        return os.getenv("APP_VERSION", "1.0.0")

    @property
    def ENVIRONMENT(self) -> str:
        return os.getenv("ENVIRONMENT", "development")

    """Reads environment variables exactly once and validates required ones."""

    # ----- Database -----
    @property
    def DATABASE_URL(self) -> str:
        return os.getenv("DATABASE_URL", "")

    @property
    def DB_POOL_SIZE(self) -> int:
        """Maximum number of persistent connections in the pool.

        Defaults to 3 because many providers (Railway Free, Supabase Free) cap
        total sessions at ~15.  With deployment overlap the worst-case budget is::

            old process:  pool_size + max_overflow = 5
            new process:  pool_size + max_overflow = 5
            alembic:     1
            total:       11   (headroom 4 below a 15-session cap)

        Set higher only if your provider's connection limit is known to exceed it.
        """
        return self._number("DB_POOL_SIZE", "3", int, minimum=1)

    @property
    def DB_MAX_OVERFLOW(self) -> int:
        """Maximum overflow connections beyond pool_size.

        Overflow connections are created on-demand when all pool_size connections
        are checked out and new requests arrive.  Combined with ``DB_POOL_SIZE``,
        the total per-process budget is ``pool_size + max_overflow``.
        """
        return self._number("DB_MAX_OVERFLOW", "2", int, minimum=0)

    @property
    def DB_POOL_TIMEOUT(self) -> int:
        """Maximum seconds to wait for acquiring a connection from the pool.

        Defaults to 10 because under heavy load without this setting the driver
        hangs indefinitely until the request times out — masking a connection
        exhaustion bug behind a generic timeout.
        """
        return self._number("DB_POOL_TIMEOUT", "10", int, minimum=1)

    @cached_property
    def DB_POOL_TOTAL(self) -> int:
        """Worst-case single-process connection budget (pool_size + max_overflow)."""
        return self.DB_POOL_SIZE + self.DB_MAX_OVERFLOW

    # ----- Supabase (optional - used by news ingestion for image proxy) -----
    @property
    def SUPABASE_URL(self) -> Optional[str]:
        return os.getenv("SUPABASE_URL") or None

    @property
    def SUPABASE_SERVICE_ROLE_KEY(self) -> Optional[str]:
        return os.getenv("SUPABASE_SERVICE_ROLE_KEY") or None

    # ----- Access Control -----
    @property
    def APP_ACCESS_TOKEN(self) -> Optional[str]:
        return os.getenv("APP_ACCESS_TOKEN") or None

    @property
    def MAINTENANCE_API_TOKEN(self) -> Optional[str]:
        return os.getenv("MAINTENANCE_API_TOKEN") or None

    @property
    def MAINTENANCE_API_ENABLED(self) -> bool:
        return os.getenv("MAINTENANCE_API_ENABLED", "false").strip().lower() in {"1", "true", "yes"}

    @property
    def MAINTENANCE_MAX_REQUEST_BYTES(self) -> int:
        return int(os.getenv("MAINTENANCE_MAX_REQUEST_BYTES", "1048576"))

    # ----- AI Provider -----
    @property
    def AI_PROVIDER(self) -> str:
        return (os.getenv("AI_PROVIDER") or "ollama").strip().lower()

    @property
    def INTELLIGENCE_ENABLED(self) -> bool:
        return os.getenv("INTELLIGENCE_ENABLED", "false").strip().lower() in {"1", "true", "yes"}

    @property
    def INTELLIGENCE_ROUTING_PROFILE(self) -> str:
        return os.getenv("INTELLIGENCE_ROUTING_PROFILE", "local-only").strip().lower()

    @property
    def INTELLIGENCE_ROUTING_REVISION(self) -> str:
        return os.getenv("INTELLIGENCE_ROUTING_REVISION", "env:v1").strip()

    @property
    def OPENAI_AUTOMATIC_GENERATION_ENABLED(self) -> bool:
        return os.getenv("OPENAI_AUTOMATIC_GENERATION_ENABLED", "false").strip().lower() in {"1", "true", "yes"}

    @property
    def OPENAI_MANUAL_GENERATION_ENABLED(self) -> bool:
        return os.getenv("OPENAI_MANUAL_GENERATION_ENABLED", "true").strip().lower() in {"1", "true", "yes"}

    @property
    def MAINTENANCE_AI_PROVIDER(self) -> str:
        return (os.getenv("MAINTENANCE_AI_PROVIDER") or "ollama").strip().lower()

    @property
    def MAINTENANCE_OLLAMA_ALLOWED_MODELS(self) -> tuple[str, ...]:
        raw = os.getenv("MAINTENANCE_OLLAMA_ALLOWED_MODELS", self.OLLAMA_MODEL)
        return tuple(dict.fromkeys(value.strip() for value in raw.split(",") if value.strip()))

    @cached_property
    def INTELLIGENCE_PILOT_TICKERS(self) -> tuple[str, ...]:
        """Normalized, validated pilot universe loaded once per Settings instance."""
        raw = os.getenv("INTELLIGENCE_PILOT_TICKERS", "SPY,QQQ,IWM,DIA")
        tickers = tuple(dict.fromkeys(value.strip().upper() for value in raw.split(",") if value.strip()))
        if not tickers:
            raise EnvironmentError("INTELLIGENCE_PILOT_TICKERS must contain at least one ticker")
        invalid = [ticker for ticker in tickers if not self._TICKER_PATTERN.fullmatch(ticker)]
        if invalid:
            raise EnvironmentError(f"INTELLIGENCE_PILOT_TICKERS contains invalid ticker(s): {', '.join(invalid)}")
        return tickers

    def is_intelligence_pilot_ticker(self, ticker: str | None) -> bool:
        return bool(ticker and ticker.strip().upper() in self.INTELLIGENCE_PILOT_TICKERS)

    # ----- Ollama -----
    @property
    def OLLAMA_BASE_URL(self) -> str:
        return os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

    @property
    def OLLAMA_MODEL(self) -> str:
        return os.getenv("OLLAMA_MODEL", "llama3.2")

    @property
    def OLLAMA_TIMEOUT_SMALL_S(self) -> float:
        return float(os.getenv("OLLAMA_TIMEOUT_SMALL_S", "900"))

    @property
    def OLLAMA_TIMEOUT_LARGE_S(self) -> float:
        return float(os.getenv("OLLAMA_TIMEOUT_LARGE_S", "1200"))

    @property
    def OLLAMA_MAX_RETRIES(self) -> int:
        return int(os.getenv("OLLAMA_MAX_RETRIES", "3"))

    @property
    def MODEL_SIZE_THRESHOLD_GB(self) -> float:
        return float(os.getenv("MODEL_SIZE_THRESHOLD_GB", "8"))

    # ----- OpenAI -----
    @property
    def OPENAI_API_KEY(self) -> Optional[str]:
        return os.getenv("OPENAI_API_KEY") or None

    @property
    def OPENAI_MODEL(self) -> str:
        return (os.getenv("OPENAI_MODEL") or "gpt-4o-mini").strip()

    @property
    def OPENAI_ALLOWED_MODELS(self) -> List[str]:
        """Whitelist of OpenAI models allowed for generation.

        Cost control source of truth. Only models in this list can be used,
        even if they exist in the OpenAI API catalog.

        Example: OPENAI_ALLOWED_MODELS=gpt-4o-mini,gpt-4.1-mini
        """
        raw = os.getenv("OPENAI_ALLOWED_MODELS", "")
        if not raw:
            return ["gpt-4o-mini"]

        # Preserve declaration order while removing whitespace and duplicates.
        return list(dict.fromkeys(m.strip() for m in raw.split(",") if m.strip()))

    def default_model_for_provider(self, provider_id: Optional[str] = None) -> str:
        """Return the configured default model for a registered provider."""
        provider = (provider_id or self.AI_PROVIDER).strip().lower()
        if provider == "openai":
            return self.OPENAI_MODEL
        if provider == "ollama":
            return self.OLLAMA_MODEL
        return ""

    # ----- Market Data -----
    @property
    def FINNHUB_API_KEY(self) -> Optional[str]:
        return os.getenv("FINNHUB_API_KEY") or None

    @property
    def LIVE_PRICE_POLL_S(self) -> int:
        return self._number("LIVE_PRICE_POLL_S", "15", int, minimum=1)

    @property
    def MARKET_DATA_BATCH_SIZE(self) -> int:
        return self._number("MARKET_DATA_BATCH_SIZE", "50", int, minimum=1, maximum=200)

    @property
    def PM_FETCH_INTERVAL_S(self) -> int:
        return self._number("PM_FETCH_INTERVAL_S", "30", int, minimum=5)

    @property
    def PM_MAX_CONCURRENCY(self) -> int:
        return self._number("PM_MAX_CONCURRENCY", "3", int, minimum=1, maximum=10)

    @property
    def MARKET_DATA_BACKOFF_INITIAL_S(self) -> float:
        return self._number("MARKET_DATA_BACKOFF_INITIAL_S", "5", float, minimum=0.1)

    @property
    def MARKET_DATA_BACKOFF_MAX_S(self) -> float:
        return self._number("MARKET_DATA_BACKOFF_MAX_S", "120", float, minimum=1)

    @property
    def MARKET_DATA_JITTER_S(self) -> float:
        return self._number("MARKET_DATA_JITTER_S", "1.0", float, minimum=0, maximum=30)

    @property
    def FINNHUB_REQUESTS_PER_MINUTE(self) -> int:
        return self._number("FINNHUB_REQUESTS_PER_MINUTE", "55", int, minimum=1, maximum=60)

    @property
    def YF_PER_TICKER_DELAY_S(self) -> float:
        return float(os.getenv("YF_PER_TICKER_DELAY_S", "0.6"))

    @property
    def QUOTE_CACHE_MAX_SIZE(self) -> int:
        return int(os.getenv("QUOTE_CACHE_MAX_SIZE", "256"))

    # ----- CORS -----
    @property
    def CORS_ORIGINS(self) -> List[str]:
        raw = os.getenv("CORS_ORIGINS", "")
        if not raw:
            return ["http://localhost:3000", "http://localhost:5173"]
        return [o.strip() for o in raw.split(",") if o.strip()]

    # ----- Rate Limiting -----
    @property
    def RATE_LIMIT_WINDOW_S(self) -> int:
        return int(os.getenv("RATE_LIMIT_WINDOW_S", "60"))

    @property
    def RATE_LIMIT_MAX_REQUESTS(self) -> int:
        return int(os.getenv("RATE_LIMIT_MAX_REQUESTS", "20"))

    # ----- AI Worker -----
    @property
    def AI_WORKER_POLL_INTERVAL_S(self) -> int:
        return int(os.getenv("AI_WORKER_POLL_INTERVAL_S", "5"))

    @property
    def AI_WORKER_QUEUE_TIMEOUT_S(self) -> int:
        return int(os.getenv("AI_WORKER_QUEUE_TIMEOUT_S", "1800"))

    # ----- WebSocket Market Data -----
    @property
    def WS_INITIAL_DELAY_S(self) -> float:
        return float(os.getenv("WS_INITIAL_DELAY_S", "2.0"))

    @property
    def WS_PING_INTERVAL_S(self) -> float:
        return float(os.getenv("WS_PING_INTERVAL_S", "30.0"))

    @property
    def WS_PING_TIMEOUT_S(self) -> float:
        return float(os.getenv("WS_PING_TIMEOUT_S", "10.0"))

    # ----- AI Worker Concurrency -----
    @property
    def AI_WORKER_MAX_CONCURRENT(self) -> int:
        return int(os.getenv("AI_WORKER_MAX_CONCURRENT", "2"))

    # ----- Analysis Timeout -----
    @property
    def ANALYSIS_TIMEOUT_S(self) -> float:
        return float(os.getenv("ANALYSIS_TIMEOUT_S", "900"))

    # ----- Hybrid Data Cache -----
    @property
    def HYBRID_CACHE_TTL_S(self) -> float:
        return float(os.getenv("HYBRID_CACHE_TTL_S", "300"))

    @property
    def HYBRID_CACHE_MAX_SIZE(self) -> int:
        return int(os.getenv("HYBRID_CACHE_MAX_SIZE", "1000"))

    # ----- Startup Validation -----
    def validate(self) -> None:
        """Fail fast if required environment variables are missing."""
        self.INTELLIGENCE_PILOT_TICKERS
        # Force validation of polling/rate-limit configuration at startup.
        polling_values = (
            self.LIVE_PRICE_POLL_S, self.MARKET_DATA_BATCH_SIZE,
            self.PM_FETCH_INTERVAL_S, self.PM_MAX_CONCURRENCY,
            self.MARKET_DATA_BACKOFF_INITIAL_S, self.MARKET_DATA_BACKOFF_MAX_S,
            self.MARKET_DATA_JITTER_S, self.FINNHUB_REQUESTS_PER_MINUTE,
        )
        if self.MARKET_DATA_BACKOFF_MAX_S < self.MARKET_DATA_BACKOFF_INITIAL_S:
            raise EnvironmentError("MARKET_DATA_BACKOFF_MAX_S must be >= MARKET_DATA_BACKOFF_INITIAL_S")
        if not self.APP_ACCESS_TOKEN:
            raise EnvironmentError("APP_ACCESS_TOKEN is required")
        if self.MAINTENANCE_API_ENABLED and not self.MAINTENANCE_API_TOKEN:
            raise EnvironmentError("MAINTENANCE_API_TOKEN is required when MAINTENANCE_API_ENABLED=true")

        missing: List[str] = []

        if not self.DATABASE_URL:
            missing.append("DATABASE_URL")

        provider = self.AI_PROVIDER
        if self.MAINTENANCE_API_ENABLED and self.MAINTENANCE_AI_PROVIDER != "ollama":
            missing.append("MAINTENANCE_AI_PROVIDER must be 'ollama'")
        if self.MAINTENANCE_API_ENABLED and not self.MAINTENANCE_OLLAMA_ALLOWED_MODELS:
            missing.append("MAINTENANCE_OLLAMA_ALLOWED_MODELS must contain at least one model")
        if provider == "openai" and not self.OPENAI_API_KEY:
            missing.append("OPENAI_API_KEY (required when AI_PROVIDER=openai)")
        elif provider == "ollama":
            # Ollama is optional locally — don't fail, just warn
            pass

        # OpenAI configuration is validated only when that provider is active;
        # local Ollama development must not require any OpenAI configuration.
        allowed = self.OPENAI_ALLOWED_MODELS
        if provider == "openai" and self.OPENAI_MODEL not in allowed:
            missing.append(
                f"OPENAI_MODEL '{self.OPENAI_MODEL}' is not included in OPENAI_ALLOWED_MODELS [{', '.join(allowed)}]"
            )

        if missing:
            raise EnvironmentError(
                f"Missing required environment variables: {', '.join(missing)}\n\n"
                f"Please check your .env configuration.\n"
                f"See apps/stocks/.env.example for all available variables."
            )

        # Warn about optional-but-recommended vars
        if not self.FINNHUB_API_KEY:
            logger.warning(
                "[Config] FINNHUB_API_KEY is not set. "
                "Finnhub-dependent features (news ingestion, some market data) will be degraded."
            )

        logger.info(
            "[Config] Environment validation passed | "
            "Provider: %s | DB configured: %s | Finnhub: %s",
            provider,
            bool(self.DATABASE_URL),
            bool(self.FINNHUB_API_KEY),
        )


# Module-level singleton so callers can do `from backend.config.settings import settings`
settings = Settings()
