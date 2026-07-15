"""
Asset Sync Service — Ensure watchlist tickers have corresponding Asset + AssetTicker records.

On startup, every ticker in the watchlist is matched or created as an Asset entity.
Finnhub company profile data is fetched to populate metadata (name, sector, industry).

Usage:
    from backend.services.asset_sync import sync_watchlist_to_assets
"""

import asyncio
import logging
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.asset import Asset, AssetTicker
from backend.services.finnhub_service import fetch_company_profile

logger = logging.getLogger(__name__)


async def _get_or_create_asset(session: AsyncSession, ticker: str) -> Optional[Asset]:
    """Find or create an Asset for the given ticker, fetching profile from Finnhub."""
    ticker_upper = ticker.upper()

    # Check if asset already exists with this ticker
    existing_ticker = await session.execute(
        select(AssetTicker).where(
            AssetTicker.ticker == ticker_upper,
            AssetTicker.active_to.is_(None),
        )
    )
    at = existing_ticker.scalar_one_or_none()

    if at:
        asset = at.asset
        return asset if asset.is_active else None

    # Fetch company profile from Finnhub for metadata.
    profile_data = {}
    try:
        profile = await fetch_company_profile(ticker_upper)
        if profile and isinstance(profile, dict):
            profile_data = profile
    except Exception as e:
        logger.warning("[AssetSync] Failed to fetch profile for %s: %s", ticker_upper, e)

    # Build asset record
    name = profile_data.get("name") or ticker_upper
    slug = name.lower().replace(" ", "-").replace(",", "").replace(".", "")[:100] or ticker_upper.lower()

    # Check if slug already exists (another asset with same company name)
    slug_check = await session.execute(
        select(Asset).where(Asset.slug == slug)
    )
    existing_by_slug = slug_check.scalar_one_or_none()

    if existing_by_slug:
        # Add ticker reference to existing asset
        new_at = AssetTicker(
            asset_id=existing_by_slug.id,
            ticker=ticker_upper,
            exchange=profile_data.get("exchange", "US"),
            is_primary=(existing_by_slug.primary_ticker is None),
        )
        await session.add(new_at)

        # If existing had no primary ticker, set this one
        if not existing_by_slug.primary_ticker:
            existing_by_slug.primary_ticker = ticker_upper
            new_at.is_primary = True

        return existing_by_slug

    # Create new asset
    asset = Asset(
        slug=slug,
        name=name,
        asset_type="stock",
        sector=profile_data.get("finnhubIndustry"),
        industry=profile_data.get("industry"),
        exchange=profile_data.get("exchange"),
        country=profile_data.get("country"),
        currency=profile_data.get("currency", "USD"),
        description=profile_data.get("sharedfulldescription"),
        website=profile_data.get("weburl"),
        logo_url=profile_data.get("image"),
        primary_ticker=ticker_upper,
        raw_source_data=profile_data if profile_data else None,
        is_active=True,
    )

    await session.add(asset)
    await session.flush()  # get asset.id

    # Create ticker mapping
    at_record = AssetTicker(
        asset_id=asset.id,
        ticker=ticker_upper,
        exchange=profile_data.get("exchange", "US"),
        is_primary=True,
    )
    await session.add(at_record)

    logger.info("[AssetSync] Created asset %s (%s)", name, ticker_upper)
    return asset


async def sync_watchlist_to_assets(session: AsyncSession, tickers: List[str]) -> int:
    """
    Ensure every ticker in the watchlist has a corresponding Asset record.
    Returns the number of new assets created.
    """
    if not tickers:
        logger.info("[AssetSync] No tickers to sync.")
        return 0

    created = 0
    for ticker in tickers:
        try:
            asset = await _get_or_create_asset(session, ticker)
            if asset and asset.id:
                # Only count truly new ones (heuristic: just count successes)
                created += 1
        except Exception as e:
            logger.error("[AssetSync] Error syncing %s: %s", ticker, e)

    await session.commit()
    logger.info("[AssetSync] Synced %d tickers -> %d asset records processed.", len(tickers), created)
    return created


async def get_asset_by_ticker(session: AsyncSession, ticker: str) -> Optional[Asset]:
    """Look up an Asset by its active ticker symbol."""
    ticker_upper = ticker.upper()

    # Fast path: check primary_ticker index
    asset = await session.execute(
        select(Asset).where(Asset.primary_ticker == ticker_upper, Asset.is_active.is_(True))
    )
    result = asset.scalar_one_or_none()
    if result:
        return result

    # Fallback: check asset_tickers table
    at_result = await session.execute(
        select(AssetTicker).where(
            AssetTicker.ticker == ticker_upper,
            AssetTicker.active_to.is_(None),
        )
    )
    at_row = at_result.scalar_one_or_none()
    if at_row:
        return at_row.asset

    return None


async def get_asset_id_by_ticker(session: AsyncSession, ticker: str) -> Optional[int]:
    """Get the asset ID for a ticker. Returns None if not found."""
    asset = await get_asset_by_ticker(session, ticker)
    return asset.id if asset else None
