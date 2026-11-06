"""Durable run tracking shared by the Windows daily script and retry API."""
from datetime import timedelta
from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from backend.config.database import async_session_factory
from backend.lib.timestamps import utc_now_naive
from backend.models.research import ReportRun

ACTIVE = ("queued", "running")


async def expire_interrupted_runs(session):
    # Each ticker writes progress, so six hours without progress is interrupted.
    rows = (await session.execute(select(ReportRun).where(ReportRun.status.in_(ACTIVE), ReportRun.updated_at < utc_now_naive() - timedelta(hours=6)).with_for_update())).scalars().all()
    for row in rows:
        done = {item["ticker"] for item in row.outcomes}
        row.outcomes = row.outcomes + [{"ticker": ticker, "status": "failed", "error": "Run interrupted before this report completed."} for ticker in row.tickers if ticker not in done]
        row.status = "interrupted"
        row.stage = "No progress for six hours; run interrupted"
        row.finished_at = utc_now_naive()
    # Release the unique active slot before a replacement INSERT is flushed.
    await session.flush()


async def create_run(tickers, *, kind="daily", parent_id=None):
    async with async_session_factory() as session:
        await expire_interrupted_runs(session)
        row = ReportRun(tickers=list(tickers), outcomes=[], news_counts={}, kind=kind, parent_id=parent_id, status="queued", stage="queued", started_at=utc_now_naive(), updated_at=utc_now_naive())
        session.add(row)
        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            raise HTTPException(409, "A report run is already active. Wait for it to finish.") from exc
        return row.id


async def progress_run(run_id, **fields):
    async with async_session_factory() as session:
        await session.execute(update(ReportRun).where(ReportRun.id == run_id).values(updated_at=utc_now_naive(), **fields))
        await session.commit()


async def finish_run(run_id, *, interrupted=False, failed=False):
    async with async_session_factory() as session:
        row = await session.get(ReportRun, run_id, with_for_update=True)
        done = {item["ticker"] for item in row.outcomes}
        row.outcomes = row.outcomes + [{"ticker": t, "status": "failed", "error": "Run ended before this report completed."} for t in row.tickers if t not in done]
        failed = failed or any(item["status"] != "completed" for item in row.outcomes)
        row.status = "interrupted" if interrupted else "failed" if failed else "completed"
        row.current_ticker = None
        row.stage = row.stage if interrupted else "finished"
        row.finished_at = row.updated_at = utc_now_naive()
        await session.commit()


def run_payload(row):
    if row is None:
        return None
    return {"id": row.id, "kind": row.kind, "parent_id": row.parent_id, "status": row.status, "stage": row.stage, "current_ticker": row.current_ticker, "tickers": row.tickers, "outcomes": row.outcomes, "news_counts": row.news_counts, "started_at": row.started_at, "updated_at": row.updated_at, "finished_at": row.finished_at}


async def execute_retry(run_id):
    from scripts.run_daily_news_and_reports import execute_tracked_run
    async with async_session_factory() as session:
        row = await session.get(ReportRun, run_id)
        tickers = tuple(row.tickers)
    await execute_tracked_run(tickers, run_id, collect_news=False)
