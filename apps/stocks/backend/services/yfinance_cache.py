"""Best-effort writable cache configuration for yfinance.

The cache is an optimization and must never become a prerequisite for quote
retrieval.  Configuration is intentionally idempotent because several market
data services import yfinance independently.
"""

from __future__ import annotations

import logging
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

from backend.services.market_data_observability import current_correlation_id

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_initialized = False
_initialization_succeeded = False


def configure_yfinance_cache(yf_module: Any | None = None) -> bool:
    """Configure yfinance's SQLite caches in a writable directory.

    Returns ``False`` on any filesystem or yfinance configuration failure and
    deliberately does not raise, allowing the provider to continue with its
    normal fallback behavior.
    """

    global _initialized, _initialization_succeeded

    with _lock:
        if _initialized:
            return _initialization_succeeded

        configured_dir = (os.getenv("YFINANCE_CACHE_DIR") or "").strip()
        cache_source = "environment" if configured_dir else "temporary"
        cache_dir = (
            Path(configured_dir).expanduser()
            if configured_dir
            else Path(tempfile.gettempdir()) / "yapvibes-yfinance"
        )

        try:
            cache_dir.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=cache_dir, prefix=".write-test-"):
                pass
            if yf_module is None:
                import yfinance as yf_module
            setter = getattr(yf_module, "set_tz_cache_location", None)
            if not callable(setter):
                raise RuntimeError("installed yfinance has no cache-location setter")
            setter(str(cache_dir))
        except Exception as exc:
            _initialization_succeeded = False
            logger.warning(
                "[MarketData] event=yfinance_cache_init success=false "
                "correlation_id=%s cache_source=%s exception_type=%s",
                current_correlation_id(),
                cache_source,
                type(exc).__name__,
            )
        else:
            _initialization_succeeded = True
            logger.info(
                "[MarketData] event=yfinance_cache_init success=true "
                "correlation_id=%s cache_source=%s",
                current_correlation_id(),
                cache_source,
            )
        finally:
            _initialized = True

        return _initialization_succeeded


def _reset_yfinance_cache_state_for_tests() -> None:
    """Reset process state for deterministic unit tests."""

    global _initialized, _initialization_succeeded
    with _lock:
        _initialized = False
        _initialization_succeeded = False
