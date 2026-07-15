"""
Refresh News Thumbnails from Finnhub

Re-fetches article images from Finnhub for existing database records that currently have
NULL thumbnail_url, and updates them with real image URLs.

This script fixes articles that were ingested before the placeholder filter was corrected —
specifically, articles whose real images were incorrectly stripped by the overly-aggressive
`s.yimg.com/rz/` domain filter.

Usage:
    python scripts/refresh_news_thumbnails.py [--ticker AAPL] [--limit 100]
"""

import asyncio
import argparse
import logging
import sys
from pathlib import Path

# Add project root to path so backend modules are importable
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.news import NewsArticle
from backend.config.database import async_session_factory
from backend.services.finnhub_service import get_finnhub_client, _rate_limiter
from backend.services.news_ingestion_service import normalize_finnhub_article

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("refresh_thumbnails")


async def count_null_thumbnails(session: AsyncSession, ticker: str | None = None) -> int:
    """Count articles with NULL thumbnail_url."""
    stmt = select(func.count()).where(NewsArticle.thumbnail_url.is_(None))
    if ticker:
        stmt = stmt.where(NewsArticle.ticker == ticker)
    result = await session.execute(stmt)
    return result.scalar() or 0


async def refresh_thumbnails(session: AsyncSession, ticker: str | None = None, limit: int = 100) -> dict:
    """
    Full re-ingestion from Finnhub for all tickers. Articles are upserted by article_url,
    so existing records get their thumbnail_url and data_source refreshed properly.

    Returns a summary dict with counts.
    """
    # Get all distinct tickers in the database
    stmt = select(func.distinct(NewsArticle.ticker)).where(NewsArticle.ticker.isnot(None))
    result = await session.execute(stmt)
    target_tickers = [t[0].upper() for t in result.all()]

    if ticker:
        target_tickers = [ticker.upper()]

    stats = {"total_ingested": 0, "tickers_processed": 0, "skipped": 0, "errors": 0}

    for tk in target_tickers:
        logger.info(f"[Refresh] Re-ingesting news from Finnhub for {tk}...")
        try:
            # Use the existing ingestion pipeline which handles upsert + rate limiting
            from backend.services.news_ingestion_service import fetch_and_ingest_news
            count = await fetch_and_ingest_news(tk, session, limit=limit)
            stats["total_ingested"] += count
            stats["tickers_processed"] += 1
            logger.info(f"[Refresh] {tk}: upserted {count} articles")

        except Exception as e:
            logger.error(f"[Refresh] Error processing {tk}: {e}")
            stats["errors"] += 1

    return stats


async def main():
    parser = argparse.ArgumentParser(description="Refresh news thumbnails from Finnhub")
    parser.add_argument("--ticker", type=str, default=None, help="Single ticker to refresh (optional)")
    parser.add_argument("--limit", type=int, default=100, help="Max articles per ticker (default: 100)")
    args = parser.parse_args()

    async with async_session_factory() as session:
        null_count = await count_null_thumbnails(session, args.ticker)
        logger.info(f"[Refresh] Found {null_count} articles with NULL thumbnail_url")

        if null_count == 0:
            logger.info("[Refresh] No NULL thumbnails to refresh. Done.")
            return

        stats = await refresh_thumbnails(session, args.ticker, args.limit)

        logger.info("=" * 60)
        logger.info("[Refresh] Summary:")
        logger.info(f"  Total articles upserted:       {stats['total_ingested']}")
        logger.info(f"  Tickers processed:             {stats['tickers_processed']}")
        logger.info(f"  Errors:                        {stats['errors']}")

        remaining = await count_null_thumbnails(session, args.ticker)
        logger.info(f"  Remaining NULL thumbnails:     {remaining}")
        logger.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
