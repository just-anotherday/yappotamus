"""
News Query Service — centralized query building for news article retrieval.

Provides paginated, filtered, and sorted queries against the NewsArticle model.
Extracted from main.py to separate query logic from route definitions (DEBT-016).
"""

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import select, func, case as sa_case
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.news import NewsArticle

logger = logging.getLogger(__name__)


def _effective_date_expr() -> sa_case:
    """Build a CASE expression that uses pub_date when available, falling back to imported_at.
    This handles NULL pub_dates gracefully in sorting and filtering."""
    return sa_case(
        (NewsArticle.pub_date.isnot(None), NewsArticle.pub_date),
        else_=NewsArticle.imported_at,
    )


def _sorted_news_query() -> select:
    """Return a base SELECT ordered by effective date descending."""
    return select(NewsArticle).order_by(_effective_date_expr().desc())


async def query_news(
    session: AsyncSession,
    ticker: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[NewsArticle], int]:
    """Return paginated news articles with total count.

    Args:
        session: Async SQLAlchemy session.
        ticker: Filter by ticker symbol (case-insensitive).
        start_date: Filter from this date (YYYY-MM-DD).
        end_date: Filter until this date (YYYY-MM-DD).
        limit: Max results per page.
        offset: Pagination offset.

    Returns:
        Tuple of (articles list, total matching count).
    """
    stmt = _sorted_news_query()

    if ticker:
        stmt = stmt.where(NewsArticle.ticker == ticker.upper())

    effective_date = _effective_date_expr()

    if start_date:
        try:
            sd = datetime.strptime(start_date, "%Y-%m-%d")
            stmt = stmt.where(effective_date >= sd)
        except ValueError:
            logger.warning(f"[NewsQuery] Ignoring malformed start_date: {start_date}")

    if end_date:
        try:
            ed = datetime.strptime(end_date, "%Y-%m-%d")
            ed = ed.replace(hour=23, minute=59, second=59)
            stmt = stmt.where(effective_date <= ed)
        except ValueError:
            logger.warning(f"[NewsQuery] Ignoring malformed end_date: {end_date}")

    # Count total matching articles (before pagination)
    subq = stmt.subquery()
    count_stmt = select(func.count()).select_from(subq)
    total_result = await session.execute(count_stmt)
    total = total_result.scalar() or 0

    # Apply pagination and fetch
    stmt = stmt.offset(offset).limit(limit)
    result = await session.execute(stmt)
    articles = list(result.scalars().all())

    logger.info(
        f"[NewsQuery] Returned {len(articles)} articles (total={total}, "
        f"limit={limit}, offset={offset})"
    )

    return articles, total


async def get_distinct_tickers(session: AsyncSession) -> list[str]:
    """Return all distinct non-null tickers from news_articles, sorted alphabetically."""
    from sqlalchemy import distinct

    stmt = (
        select(distinct(NewsArticle.ticker))
        .where(NewsArticle.ticker.isnot(None))
        .order_by(NewsArticle.ticker)
    )
    result = await session.execute(stmt)
    tickers = sorted(t[0] for t in result.all() if t[0])
    return tickers
