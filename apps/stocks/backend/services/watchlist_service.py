"""
Watchlist Service — CRUD operations for persistent watchlist in PostgreSQL.
"""

import logging
from typing import Optional, List

from sqlalchemy import select, delete, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.watchlist import WatchlistModel
from backend.config.watchlist import DEFAULT_TICKERS, MAX_WATCHLIST_SIZE
from backend.lib.tickers import normalize_ticker

logger = logging.getLogger(__name__)


async def seed_defaults(session: AsyncSession) -> int:
    """If the watchlist table is empty, insert DEFAULT_TICKERS with sequential positions.
    Returns the number of rows seeded."""
    result = await session.execute(select(WatchlistModel).limit(1))
    exists = result.scalar() is not None
    if exists:
        return 0

    for idx, ticker in enumerate(DEFAULT_TICKERS):
        row = WatchlistModel(ticker=normalize_ticker(ticker), position=idx)
        session.add(row)

    await session.commit()
    logger.info(f"[Watchlist] Seeded {len(DEFAULT_TICKERS)} default tickers.")
    return len(DEFAULT_TICKERS)


async def get_all_tickers(session: AsyncSession) -> List[str]:
    """Return all ticker symbols ordered by position."""
    stmt = select(WatchlistModel.ticker).order_by(WatchlistModel.position)
    result = await session.execute(stmt)
    return [row[0] for row in result.all()]


async def count(session: AsyncSession) -> int:
    """Count rows in the watchlist."""
    from sqlalchemy import func
    result = await session.execute(select(func.count()).select_from(WatchlistModel))
    return result.scalar()


async def add_ticker(session: AsyncSession, ticker: str) -> Optional[WatchlistModel]:
    """Insert a single ticker. Returns the created row or raises."""
    ticker = ticker.upper()

    # Capacity check
    c = await count(session)
    if c >= MAX_WATCHLIST_SIZE:
        raise ValueError(f"Watchlist is full (max {MAX_WATCHLIST_SIZE}). Remove a ticker before adding.")

    # Duplicate check
    existing = await session.execute(
        select(WatchlistModel).where(WatchlistModel.ticker == ticker)
    )
    if existing.scalar_one_or_none():
        raise ValueError(f"{ticker} is already in your watchlist.")

    row = WatchlistModel(ticker=ticker, position=c)
    session.add(row)
    await session.commit()
    await session.refresh(row)
    logger.info(f"[Watchlist] Added {ticker}")
    return row


async def remove_ticker(session: AsyncSession, ticker: str) -> bool:
    """Delete a ticker. Returns True if removed, raises if not found."""
    ticker = ticker.upper()
    result = await session.execute(
        select(WatchlistModel).where(WatchlistModel.ticker == ticker)
    )
    row = result.scalar_one_or_none()
    if not row:
        raise KeyError(f"{ticker} is not in your watchlist.")

    await session.execute(delete(WatchlistModel).where(WatchlistModel.ticker == ticker))

    # Re-order positions after removal
    remaining = await session.execute(
        select(WatchlistModel).order_by(WatchlistModel.position)
    )
    rows = remaining.scalars().all()
    for idx, r in enumerate(rows):
        r.position = idx

    await session.commit()
    logger.info(f"[Watchlist] Removed {ticker}")
    return True


async def update_order(session: AsyncSession, tickers: List[str]) -> None:
    """Set the position of every ticker to match the provided ordering."""
    normalized = [t.upper() for t in tickers]

    # Validate: no duplicates
    if len(normalized) != len(set(normalized)):
        raise ValueError("Duplicate tickers in order payload.")

    # Validate: all tickers exist
    existing_result = await session.execute(
        select(WatchlistModel.ticker).where(WatchlistModel.ticker.in_(normalized))
    )
    existing_set = set(row[0] for row in existing_result.all())
    invalid = set(normalized) - existing_set
    if invalid:
        raise ValueError(f"Unknown tickers in order: {', '.join(sorted(invalid))}")

    # Update positions
    for idx, t in enumerate(normalized):
        await session.execute(
            update(WatchlistModel)
            .where(WatchlistModel.ticker == t)
            .values(position=idx)
        )

    await session.commit()
    logger.info(f"[Watchlist] Updated order for {len(normalized)} tickers.")
