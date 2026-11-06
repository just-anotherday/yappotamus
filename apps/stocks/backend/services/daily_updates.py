"""Live-site preferences are authoritative; the local worker pulls a bounded snapshot."""
import asyncio
import hashlib
import json
import logging
from datetime import timedelta

import httpx
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert

from backend.config.database import async_session_factory
from backend.config.watchlist import MAX_WATCHLIST_SIZE
from backend.lib.tickers import normalize_ticker
from backend.lib.timestamps import utc_isoformat, utc_now_naive
from backend.models.daily_updates import DailyUpdateState
from backend.models.watchlist import WatchlistModel
from backend.services.report_publishing import PUBLICATION_TIMEOUT, publishing_target

logger = logging.getLogger(__name__)


def sync_target():
    from backend.config.settings import settings
    return publishing_target() if settings.DAILY_UPDATES_SYNC_ENABLED else ""


class DailyTicker(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    ticker: str
    news_enabled: bool = True
    reports_enabled: bool = True

    @field_validator("ticker")
    @classmethod
    def valid_ticker(cls, value):
        return normalize_ticker(value)


class DailyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    revision: str = Field(pattern=r"^[a-f0-9]{64}$")
    tickers: list[DailyTicker] = Field(max_length=MAX_WATCHLIST_SIZE)

    @model_validator(mode="after")
    def valid_snapshot(self):
        names = [item.ticker for item in self.tickers]
        if len(names) != len(set(names)) or self.revision != config_revision(self.tickers):
            raise ValueError("Invalid configuration revision or duplicate ticker")
        return self


def config_revision(tickers):
    values = [item.model_dump() if isinstance(item, DailyTicker) else item for item in tickers]
    return hashlib.sha256(json.dumps(values, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


async def config_snapshot(session):
    rows = (await session.scalars(select(WatchlistModel).order_by(WatchlistModel.position, WatchlistModel.id).limit(MAX_WATCHLIST_SIZE))).all()
    items = [DailyTicker(ticker=row.ticker, news_enabled=row.news_enabled, reports_enabled=row.reports_enabled) for row in rows]
    return DailyConfig(revision=config_revision(items), tickers=items)


async def ensure_state(session):
    await session.execute(insert(DailyUpdateState).values(id=1, local_status={}).on_conflict_do_nothing(index_elements=[DailyUpdateState.id]))
    return await session.get(DailyUpdateState, 1)


def update_quote_subscriptions(*, added=(), removed=()):
    from backend.services.market_data_service import MarketDataService
    market_data = MarketDataService.get_instance()
    if added:
        market_data.subscribe(list(added))
    if removed:
        market_data.unsubscribe(list(removed))


async def owner_status(session):
    from backend.config.settings import settings
    config = await config_snapshot(session)
    state = await session.get(DailyUpdateState, 1)
    rows = (await session.scalars(select(WatchlistModel).order_by(WatchlistModel.position, WatchlistModel.id))).all()
    return {**config.model_dump(), "tickers": [
        {**item.model_dump(), "news_status": row.news_status if row.news_enabled else "paused",
         "news_checked_at": utc_isoformat(row.news_checked_at)} for item, row in zip(config.tickers, rows)
    ], "applied_revision": state.applied_revision if state else None,
        "applied_at": utc_isoformat(state.applied_at) if state else None,
        "last_seen_at": utc_isoformat(state.last_seen_at) if state else None,
        "local_status": state.local_status if state else {}, "max_tickers": MAX_WATCHLIST_SIZE,
        "shared_settings_ready": not bool(settings.REPORT_PUBLISH_URL) or settings.DAILY_UPDATES_SYNC_ENABLED}


async def sync_config(*, session_factory=async_session_factory, transport=None):
    """Fail closed before a daily run instead of silently using an outdated list."""
    target = sync_target()
    if not target:
        return None
    pull_started_at = utc_now_naive()
    from backend.config.settings import settings
    headers = {"Authorization": f"Bearer {settings.REPORT_PUBLISH_TOKEN}"}
    async with httpx.AsyncClient(timeout=PUBLICATION_TIMEOUT, follow_redirects=False, transport=transport) as client:
        # A receiver may need a second request while waking up.
        for attempt in range(2):
            try:
                async with asyncio.timeout(110):
                    response = await client.get(target + "/api/internal/daily-updates", headers=headers)
                    response.raise_for_status()
                    if len(response.content) > 100_000:
                        raise ValueError("Configuration too large")
                    config = DailyConfig.model_validate(response.json())
                break
            except (httpx.TransportError, TimeoutError):
                if attempt:
                    raise
                await asyncio.sleep(2)
            except httpx.HTTPStatusError as exc:
                if attempt or exc.response.status_code not in {502, 503, 504}:
                    raise
                await asyncio.sleep(2)
        async with session_factory() as session:
            # Serialize replacement transactions; the cloud ACK rejects stale pulls.
            await ensure_state(session)
            state = await session.get(DailyUpdateState, 1, with_for_update=True, populate_existing=True)
            if state.last_seen_at and state.last_seen_at > pull_started_at and state.applied_revision != config.revision:
                raise RuntimeError("Settings pull superseded; retry")
            current = {row.ticker: row for row in (await session.scalars(select(WatchlistModel))).all()}
            names = [item.ticker for item in config.tickers]
            await session.execute(delete(WatchlistModel).where(WatchlistModel.ticker.not_in(names)))
            for position, item in enumerate(config.tickers):
                row = current.get(item.ticker)
                if row is None:
                    row = WatchlistModel(ticker=item.ticker)
                    session.add(row)
                if item.news_enabled and (row.news_enabled is False or row.id is None):
                    row.news_pending, row.news_status, row.news_checked_at = True, "pending", None
                if not item.news_enabled:
                    row.news_pending, row.news_status = False, "paused"
                row.position, row.news_enabled, row.reports_enabled = position, item.news_enabled, item.reports_enabled
            state = await session.get(DailyUpdateState, 1)
            state.applied_revision, state.last_seen_at = config.revision, utc_now_naive()
            await session.commit()
        update_quote_subscriptions(added=set(names) - set(current), removed=set(current) - set(names))
        async with session_factory() as session:
            rows = (await session.scalars(select(WatchlistModel))).all()
            news = [{"ticker": row.ticker, "status": row.news_status,
                     "checked_at": utc_isoformat(row.news_checked_at)} for row in rows]
        # ACK only after the local transaction committed. Cloud rejects stale revisions.
        async with asyncio.timeout(110):
            response = await client.post(target + "/api/internal/daily-updates/ack", headers=headers,
                                         json={"revision": config.revision, "news": news})
            response.raise_for_status()
        return config


async def ingest_pending_news(*, session_factory=async_session_factory):
    """Durable initial-fetch queue; short claims survive crashes and multiple workers."""
    from backend.services.news_ingestion_service import fetch_and_ingest_news
    for _ in range(MAX_WATCHLIST_SIZE):
        now = utc_now_naive()
        async with session_factory() as session:
            row = await session.scalar(select(WatchlistModel).where(
                WatchlistModel.news_enabled.is_(True), WatchlistModel.news_pending.is_(True),
                (WatchlistModel.news_checked_at.is_(None)) | (WatchlistModel.news_checked_at < now - timedelta(minutes=5)),
            ).order_by(WatchlistModel.position).limit(1).with_for_update(skip_locked=True))
            if row is None:
                return
            ticker, claim_id = row.ticker, row.id
            row.news_status, row.news_checked_at = "fetching", now
            await session.commit()
        try:
            async with session_factory() as session:
                # Recheck after claiming: a removal or pause should prevent a new fetch.
                allowed = await session.scalar(select(WatchlistModel.news_enabled).where(WatchlistModel.id == claim_id))
                if not allowed:
                    continue
                provider_state = {}
                async with asyncio.timeout(120):
                    await fetch_and_ingest_news(ticker, session, limit=50, _provider_state=provider_state)
                if provider_state.get("last_outcome") != "success":
                    raise RuntimeError("News provider did not complete")
            status, pending = "completed", False
        except Exception:
            status, pending = "retrying", True
            logger.warning("Daily updates initial news fetch failed for %s", ticker)
        async with session_factory() as session:
            await session.execute(update(WatchlistModel).where(
                WatchlistModel.id == claim_id, WatchlistModel.news_enabled.is_(True),
                WatchlistModel.news_checked_at == now,
            ).values(news_status=status, news_pending=pending, news_checked_at=utc_now_naive()))
            await session.commit()


async def _initial_news_loop():
    while True:
        try:
            fresh = True
            if sync_target():
                async with async_session_factory() as session:
                    state = await session.get(DailyUpdateState, 1)
                    fresh = bool(state and state.last_seen_at and state.last_seen_at > utc_now_naive() - timedelta(minutes=2))
            if fresh:
                await ingest_pending_news()
        except Exception as exc:
            logger.warning("Daily updates initial news deferred: %s", type(exc).__name__)
        await asyncio.sleep(15)


async def daily_updates_loop():
    news_task = asyncio.create_task(_initial_news_loop())
    try:
        while True:
            try:
                await sync_config()
            except Exception as exc:
                # No credentials, response bodies, or private URLs in logs.
                logger.warning("Daily updates sync deferred: %s", type(exc).__name__)
            await asyncio.sleep(30)
    finally:
        news_task.cancel()
        await asyncio.gather(news_task, return_exceptions=True)
