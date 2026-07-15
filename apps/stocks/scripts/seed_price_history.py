"""Seed price history for market trackers."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.services.price_history_service import (
    MARKET_TRACKERS,
    seed_market_tracker_info,
    fetch_and_store_batch,
)

async def main():
    from sqlalchemy.ext.asyncio import AsyncSession
    from backend.config.database import get_async_session
    
    async for session in get_async_session():
        print("Seeding tracker metadata...")
        count = await seed_market_tracker_info(session)
        print(f"  Seeded {count} trackers.")

        print("\nFetching and storing price history (2 years)...")
        results = await fetch_and_store_batch(session, MARKET_TRACKERS, period="2y")
        total = sum(results.values())
        for ticker, n in results.items():
            print(f"  {ticker}: {n} records")
        print(f"\nTotal: {total} OHLCV records stored.")

if __name__ == "__main__":
    asyncio.run(main())
