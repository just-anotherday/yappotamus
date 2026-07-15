"""Seed assets and asset_tickers from existing watchlist + news ticker data."""
import sys, asyncio
sys.path.insert(0, '.')

from sqlalchemy import select, text
from backend.config.database import async_session_factory

# Import ALL models to register them with Base before any query.
# Asset references AICompanyReport via string relationship — both must exist in clsregistry.
from backend.models.asset import Asset, AssetTicker
from backend.models.ai_reports import AICompanyReport, AISectorReport, AIMarketReport
from backend.models.ai_job_queue import AIJobQueue
from backend.models.news import NewsArticle
from backend.models.watchlist import WatchlistModel as Watchlist
# Known asset type classification for common tickers
KNOWN_ETFs = {'SPY', 'QQQ', 'VOO', 'IJH', 'VTV', 'VUG', 'VTI', 'ARKK'}

async def seed():
    async with async_session_factory() as s:
        # Gather all unique tickers from watchlist + news
        wl_result = await s.execute(text("SELECT DISTINCT ticker FROM watchlist"))
        wl_tickers = [r[0] for r in wl_result.fetchall()]

        news_result = await s.execute(text("SELECT DISTINCT ticker FROM news_articles"))
        news_tickers = [r[0] for r in news_result.fetchall()]

        all_tickers = sorted(set(wl_tickers + news_tickers))
        print(f"Found {len(all_tickers)} unique tickers to seed")

        created = 0
        skipped = 0

        for ticker in all_tickers:
            # Check if already exists
            existing = await s.execute(
                select(Asset.id).where(Asset.primary_ticker == ticker)
            )
            if existing.scalar_one_or_none():
                skipped += 1
                continue

            # Determine asset type
            if ticker in KNOWN_ETFs:
                asset_type = "etf"
            else:
                asset_type = "stock"

            # Create asset
            slug = ticker.lower() + "_" + asset_type
            asset = Asset(
                primary_ticker=ticker,
                name=ticker,  # Will be updated later via Finnhub profile sync
                slug=slug,
                asset_type=asset_type,
                is_active=True,
            )
            s.add(asset)
            await s.flush()  # Get the asset ID

            # Create primary ticker mapping
            at = AssetTicker(
                asset_id=asset.id,
                ticker=ticker,
                is_primary=True,
            )
            s.add(at)
            created += 1

        await s.commit()
        print(f"Seeded {created} assets (+ tickers), skipped {skipped} existing")

if __name__ == '__main__':
    asyncio.run(seed())
