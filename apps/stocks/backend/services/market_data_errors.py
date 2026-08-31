"""Typed market-data availability failures shared by API entry points."""

import math
from collections.abc import Mapping
from typing import Any


class MarketDataUnavailableError(RuntimeError):
    """A known asset has no usable trusted provider or bounded-cache price."""

    failure_kind = "providers_exhausted"

    def __init__(self, ticker: str) -> None:
        self.ticker = ticker.strip().upper()
        super().__init__(f"Could not fetch market data for {self.ticker}")


def require_usable_analysis_snapshot(
    ticker: str,
    payload: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Require a finite positive provider/cache-selected analysis price."""
    if payload is not None:
        price = payload.get("current_price")
        if (
            isinstance(price, (int, float))
            and not isinstance(price, bool)
            and math.isfinite(float(price))
            and price > 0
        ):
            return dict(payload)
    raise MarketDataUnavailableError(ticker)
