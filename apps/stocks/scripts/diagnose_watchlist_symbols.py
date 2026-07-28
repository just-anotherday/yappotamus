"""Print normalized watchlist payloads for selected symbols.

Read-only: calls configured market-data providers and does not access or mutate
the database.  API keys and environment values are never printed.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / ".env")

from backend.models.stock import WatchlistItem
from backend.services.market_data_observability import (
    market_data_correlation,
    normalize_correlation_id,
)
from backend.services.hybrid_data_service import get_hybrid_batch_prices
from backend.services.yfinance_cache import configure_yfinance_cache


async def collect(symbols: list[str]) -> list[dict]:
    correlation_id = normalize_correlation_id(None)
    with market_data_correlation(correlation_id):
        configure_yfinance_cache()
        results = await get_hybrid_batch_prices(symbols)
    return [
        WatchlistItem.model_validate(result).model_dump(mode="json")
        for result in results
    ]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Print normalized watchlist responses without credentials."
    )
    parser.add_argument(
        "symbols",
        nargs="*",
        default=["SPY", "QQQ", "SPCX", "AAPL"],
        help="Ticker symbols (default: SPY QQQ SPCX AAPL)",
    )
    args = parser.parse_args()
    symbols = [symbol.strip().upper() for symbol in args.symbols if symbol.strip()]
    print(json.dumps(asyncio.run(collect(symbols)), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
