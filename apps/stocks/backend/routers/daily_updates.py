"""Owner controls plus a narrow machine read/acknowledge boundary."""
from datetime import datetime
from typing import Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from backend.auth import verify_app_access_token
from backend.config.database import get_async_session
from backend.config.watchlist import MAX_WATCHLIST_SIZE
from backend.lib.tickers import normalize_ticker
from backend.lib.timestamps import utc_now_naive
from backend.models.watchlist import WatchlistModel
from backend.routers.report_publications import verify_publishing_token
from backend.services.daily_updates import DailyTicker, config_snapshot, ensure_state, owner_status, sync_config, sync_target, update_quote_subscriptions
from backend.services.report_publishing import PUBLICATION_TIMEOUT, publishing_target
from backend.services.watchlist_service import add_ticker, remove_ticker

router = APIRouter(tags=["daily updates"])
owner = [Depends(verify_app_access_token)]
machine = [Depends(verify_publishing_token)]


class Preferences(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    news_enabled: bool
    reports_enabled: bool


class NewsState(BaseModel):
    ticker: str = Field(max_length=10)
    status: Literal["pending", "fetching", "completed", "retrying", "paused", "not_requested"]
    checked_at: datetime | None = None


class Acknowledgement(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: str = Field(pattern=r"^[a-f0-9]{64}$")
    news: list[NewsState] = Field(default_factory=list, max_length=MAX_WATCHLIST_SIZE)


async def proxy_owner(request: Request, path: str, *, body=None):
    """Local owner controls edit the same live settings, using their owner login."""
    target = sync_target()
    if not target:
        return None
    try:
        async with httpx.AsyncClient(timeout=PUBLICATION_TIMEOUT, follow_redirects=False) as client:
            response = await client.request(request.method, target + path, json=body,
                                            headers={"Authorization": request.headers.get("Authorization", "")})
            if not response.is_success:
                raise HTTPException(response.status_code if response.status_code in {400, 401, 403, 404, 409, 422} else 503,
                                    "Live Daily Updates settings could not be updated. Refresh and try again.")
            result = response.json()
        if request.method != "GET":
            try:
                await sync_config()
            except Exception:
                # The live edit succeeded. UI must not imply that it was rolled back.
                result["sync_pending"] = True
        return result
    except httpx.HTTPError:
        raise HTTPException(503, "Live settings are temporarily unavailable. No local settings were changed.") from None


@router.get("/api/daily-updates", dependencies=owner)
async def settings_page(request: Request, session=Depends(get_async_session)):
    proxied = await proxy_owner(request, "/api/daily-updates")
    return proxied if proxied is not None else await owner_status(session)


@router.post("/api/daily-updates/tickers", dependencies=owner)
async def add_update_ticker(payload: DailyTicker, request: Request, session=Depends(get_async_session)):
    proxied = await proxy_owner(request, "/api/daily-updates/tickers", body=payload.model_dump())
    if proxied is not None:
        return proxied
    await ensure_state(session)
    try:
        row = await add_ticker(session, payload.ticker)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None
    row.news_enabled, row.reports_enabled = payload.news_enabled, payload.reports_enabled
    row.news_pending = payload.news_enabled
    row.news_status = "pending" if payload.news_enabled else "paused"
    await session.commit()
    update_quote_subscriptions(added=[payload.ticker])
    return await owner_status(session)


@router.patch("/api/daily-updates/tickers/{ticker}", dependencies=owner)
async def edit_update_ticker(ticker: str, payload: Preferences, request: Request, session=Depends(get_async_session)):
    try:
        ticker = normalize_ticker(ticker)
    except ValueError:
        raise HTTPException(422, "Invalid ticker") from None
    proxied = await proxy_owner(request, f"/api/daily-updates/tickers/{ticker}", body=payload.model_dump())
    if proxied is not None:
        return proxied
    await ensure_state(session)
    row = await session.scalar(select(WatchlistModel).where(WatchlistModel.ticker == ticker).with_for_update())
    if row is None:
        raise HTTPException(404, "Ticker is not in your watchlist")
    if payload.news_enabled and not row.news_enabled:
        row.news_pending, row.news_status, row.news_checked_at = True, "pending", None
    if not payload.news_enabled:
        row.news_pending, row.news_status = False, "paused"
    row.news_enabled, row.reports_enabled = payload.news_enabled, payload.reports_enabled
    await session.commit()
    return await owner_status(session)


@router.delete("/api/daily-updates/tickers/{ticker}", dependencies=owner)
async def delete_update_ticker(ticker: str, request: Request, session=Depends(get_async_session)):
    try:
        ticker = normalize_ticker(ticker)
    except ValueError:
        raise HTTPException(422, "Invalid ticker") from None
    proxied = await proxy_owner(request, f"/api/daily-updates/tickers/{ticker}")
    if proxied is not None:
        return proxied
    await ensure_state(session)
    try:
        await remove_ticker(session, ticker)
    except KeyError:
        raise HTTPException(404, "Ticker is not in your watchlist") from None
    update_quote_subscriptions(removed=[ticker])
    return await owner_status(session)


@router.get("/api/internal/daily-updates", dependencies=machine)
async def worker_config(session=Depends(get_async_session)):
    return await config_snapshot(session)


@router.post("/api/internal/daily-updates/ack", dependencies=machine)
async def worker_ack(payload: Acknowledgement, session=Depends(get_async_session)):
    state = await ensure_state(session)
    config = await config_snapshot(session)
    if payload.revision != config.revision:
        raise HTTPException(409, "Settings changed; pull the latest configuration")
    if state.applied_revision != payload.revision:
        state.applied_at = utc_now_naive()
    state.applied_revision, state.last_seen_at = payload.revision, utc_now_naive()
    allowed = {item.ticker for item in config.tickers}
    state.local_status = {item.ticker: item.model_dump(mode="json") for item in payload.news if item.ticker in allowed}
    await session.commit()
    return {"revision": config.revision, "acknowledged": True}
