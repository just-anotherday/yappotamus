"""Analysis Reports Router

CRUD endpoints for saved analysis reports.
List endpoint returns slim DTOs (no full JSON payload).
Detail endpoint returns complete report_data.
"""

import logging
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Depends, Query, Body
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config.database import get_async_session
from backend.models.report_schemas import (
    AnalysisReportDetail,
    CreateReportResponse,
    ReportPaginationResponse,
)
from backend.services.report_service import (
    create_report,
    delete_report,
    get_latest_for_ticker,
    get_report_by_id,
    list_reports,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/analysis/reports", tags=["analysis reports"])


class SaveReportRequest(BaseModel):
    """Body for saving an analysis report."""
    ticker: str
    report_data: Dict[str, Any]
    articles_count: int = 0
    model_used: str = ""
    prompt_version: str = "1.0"
    current_price_at_analysis: Optional[float] = None


def _parse_date(value: Optional[str], label: str) -> Optional[datetime]:
    """Parse an ISO date string; returns None on failure."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail=f"Invalid {label} format")


@router.get("/", response_model=ReportPaginationResponse)
async def reports_list(
    ticker: Optional[str] = Query(None),
    sentiment: Optional[str] = Query(None),
    from_date: Optional[str] = Query(None, alias="from"),
    to_date: Optional[str] = Query(None, alias="to"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    sort: str = Query("newest", pattern="^(newest|oldest)$"),
    session: AsyncSession = Depends(get_async_session),
):
    """List saved reports with filtering and pagination."""
    summaries, total = await list_reports(
        session=session,
        ticker=ticker,
        sentiment=sentiment,
        from_date=_parse_date(from_date, "from_date"),
        to_date=_parse_date(to_date, "to_date"),
        page=page,
        limit=limit,
        sort=sort,
    )
    has_more = (page * limit) < total
    return ReportPaginationResponse(
        items=summaries,
        total=total,
        page=page,
        limit=limit,
        has_more=has_more,
    )


@router.get("/latest/{ticker}", response_model=AnalysisReportDetail)
async def reports_latest_for_ticker(
    ticker: str,
    session: AsyncSession = Depends(get_async_session),
):
    """Get the most recent report for a specific ticker."""
    row = await get_latest_for_ticker(session, ticker)
    if not row:
        raise HTTPException(status_code=404, detail=f"No saved reports found for {ticker}")
    return AnalysisReportDetail.model_validate(row)


@router.get("/{report_id}", response_model=AnalysisReportDetail)
async def reports_get_by_id(
    report_id: int,
    session: AsyncSession = Depends(get_async_session),
):
    """Get a single saved report by ID (full payload)."""
    row = await get_report_by_id(session, report_id)
    if not row:
        raise HTTPException(status_code=404, detail="Report not found")
    return AnalysisReportDetail.model_validate(row)


@router.post("/save", response_model=CreateReportResponse)
async def reports_save(
    request: SaveReportRequest = Body(...),
    session: AsyncSession = Depends(get_async_session),
):
    """Save an analysis report to the database."""
    report_id = await create_report(
        session=session,
        ticker=request.ticker,
        report_data=request.report_data,
        articles_count=request.articles_count,
        model_used=request.model_used,
        prompt_version=request.prompt_version,
        current_price_at_analysis=request.current_price_at_analysis,
    )
    await session.commit()
    logger.info(f"[Reports] Saved report id={report_id} for {request.ticker.upper()}")
    return CreateReportResponse(report_id=report_id, report=request.report_data)


@router.delete("/{report_id}")
async def reports_delete(
    report_id: int,
    session: AsyncSession = Depends(get_async_session),
):
    """Delete a saved report."""
    deleted = await delete_report(session, report_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Report not found")
    await session.commit()
    return {"status": "deleted", "id": report_id}


# ------------------------------------------------------------------
# Cached Intelligence Endpoints (event-driven pipeline outputs)
# ------------------------------------------------------------------

@router.get("/company/{ticker}")
async def get_cached_company_report(
    ticker: str,
    session: AsyncSession = Depends(get_async_session),
):
    """Get the latest cached AI intelligence report for a company.

    Returns the most recent asynchronously-generated report from the event-driven pipeline.
    If no report exists yet, returns 404 with a hint to trigger regeneration.
    """
    from sqlalchemy import select
    from backend.models.ai_reports import AICompanyReport
    from backend.models.asset import Asset, AssetTicker

    # Fetch latest cached report by ticker only.
    # NOTE: We intentionally do NOT join on asset_id here because historical reports
    # may reference stale asset_ids from before the asset system was introduced.
    # The ticker column is the stable identifier across all eras.
    report_row = await session.execute(
        select(AICompanyReport)
        .where(AICompanyReport.ticker == ticker.upper())
        .order_by(AICompanyReport.updated_at.desc())
        .limit(1)
    )
    report = report_row.scalar_one_or_none()

    # Optionally resolve current asset_id for the response (non-blocking)
    current_asset_id = None
    if report:
        asset_row = await session.execute(
            select(Asset.id).where(
                Asset.id == AssetTicker.asset_id,
                AssetTicker.ticker == ticker.upper(),
                AssetTicker.is_primary.is_(True),
            )
        )
        current_asset_id = asset_row.scalar_one_or_none()

    if not report:
        raise HTTPException(
            status_code=404,
            detail=f"No cached intelligence report for {ticker.upper()}. Reports are generated asynchronously when new news arrives."
        )

    return {
        "id": report.id,
        "ticker": report.ticker,
        "asset_id": report.asset_id,
        "report_data": report.report_data,
        "overall_sentiment": report.overall_sentiment,
        "confidence_score": report.confidence_score,
        "articles_count": report.articles_count,
        "model_used": report.model_used,
        "prompt_version": report.prompt_version,
        "price_snapshot": report.price_snapshot,
        "last_updated": report.updated_at.isoformat() if report.updated_at else None,
    }


@router.get("/market/latest")
async def get_latest_market_report(
    session: AsyncSession = Depends(get_async_session),
):
    """Get the latest cached daily market-wide intelligence report."""
    from sqlalchemy import select
    from backend.models.ai_reports import AIMarketReport

    report_row = await session.execute(
        select(AIMarketReport)
        .order_by(AIMarketReport.report_date.desc())
        .limit(1)
    )
    report = report_row.scalar_one_or_none()

    if not report:
        raise HTTPException(
            status_code=404,
            detail="No cached market report available yet."
        )

    return {
        "id": report.id,
        "report_date": report.report_date.isoformat() if report.report_date else None,
        "report_data": report.report_data,
        "overall_sentiment": report.overall_sentiment,
        "risk_level": report.risk_level,
        "confidence_score": report.confidence_score,
        "model_used": report.model_used,
        "last_generated": report.created_at.isoformat() if report.created_at else None,
    }


@router.get("/market/history")
async def get_market_report_history(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_async_session),
):
    """Get all daily market reports in paginated form (newest first)."""
    from sqlalchemy import select, func
    from backend.models.ai_reports import AIMarketReport

    total_row = await session.execute(select(func.count(AIMarketReport.id)))
    total = total_row.scalar() or 0

    offset = (page - 1) * limit
    rows = await session.execute(
        select(AIMarketReport)
        .order_by(AIMarketReport.report_date.desc())
        .offset(offset)
        .limit(limit)
    )
    reports = list(rows.scalars().all())

    has_more = (page * limit) < total

    return {
        "items": [
            {
                "id": r.id,
                "report_date": r.report_date.isoformat() if r.report_date else None,
                "overall_sentiment": r.overall_sentiment,
                "risk_level": r.risk_level,
                "confidence_score": r.confidence_score,
                "model_used": r.model_used,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in reports
        ],
        "total": total,
        "page": page,
        "limit": limit,
        "has_more": has_more,
    }


@router.get("/market/{report_id}")
async def get_market_report_by_id(
    report_id: int,
    session: AsyncSession = Depends(get_async_session),
):
    """Get a specific market report by ID (full payload)."""
    from sqlalchemy import select
    from backend.models.ai_reports import AIMarketReport

    report_row = await session.execute(
        select(AIMarketReport).where(AIMarketReport.id == report_id)
    )
    report = report_row.scalar_one_or_none()

    if not report:
        raise HTTPException(status_code=404, detail="Market report not found")

    return {
        "id": report.id,
        "report_date": report.report_date.isoformat() if report.report_date else None,
        "report_data": report.report_data,
        "overall_sentiment": report.overall_sentiment,
        "risk_level": report.risk_level,
        "confidence_score": report.confidence_score,
        "model_used": report.model_used,
        "created_at": report.created_at.isoformat() if report.created_at else None,
    }


@router.post("/company/{ticker}/regenerate")
async def trigger_company_regeneration(
    ticker: str,
    model: Optional[str] = Body(None, embed=True, description="Override default Ollama model"),
    session: AsyncSession = Depends(get_async_session),
):
    """Manually trigger a company report regeneration by enqueuing a job."""
    from sqlalchemy import select
    from backend.models.asset import Asset, AssetTicker
    from backend.services.ai_worker import enqueue_job

    # Resolve asset_id
    asset_row = await session.execute(
        select(Asset.id).where(
            Asset.id == AssetTicker.asset_id,
            AssetTicker.ticker == ticker.upper(),
            AssetTicker.is_primary.is_(True),
        )
    )
    asset_id = asset_row.scalar_one_or_none()

    if not asset_id:
        raise HTTPException(status_code=404, detail=f"No asset found for {ticker.upper()}")

    payload = {"ticker": ticker.upper()}
    if model:
        payload["model"] = model

    queued = await enqueue_job(
        session=session,
        job_type="company_report",
        target_type="asset",
        target_id=asset_id,
        payload=payload,
        priority=5,  # High priority for manual triggers
    )

    return {
        "status": "queued" if queued else "already_pending",
        "ticker": ticker.upper(),
        "asset_id": asset_id,
    }


@router.get("/sector/all")
async def get_all_sector_reports(
    session: AsyncSession = Depends(get_async_session),
):
    """Get all cached sector intelligence reports."""
    from sqlalchemy import select
    from backend.models.ai_reports import AISectorReport

    rows = await session.execute(
        select(AISectorReport).order_by(AISectorReport.created_at.desc())
    )
    reports = list(rows.scalars().all())

    return [
        {
            "id": r.id,
            "sector": r.sector,
            "report_data": r.report_data,
            "overall_sentiment": r.overall_sentiment,
            "confidence_score": r.confidence_score,
            "assets_count": r.assets_count,
            "model_used": r.model_used,
            "last_updated": r.created_at.isoformat() if r.created_at else None,
        }
        for r in reports
    ]


@router.get("/sector/{sector}")
async def get_sector_report(
    sector: str,
    session: AsyncSession = Depends(get_async_session),
):
    """Get the latest cached AI intelligence report for a sector."""
    from sqlalchemy import select
    from backend.models.ai_reports import AISectorReport

    report_row = await session.execute(
        select(AISectorReport)
        .where(AISectorReport.sector == sector)
        .order_by(AISectorReport.created_at.desc())
        .limit(1)
    )
    report = report_row.scalar_one_or_none()

    if not report:
        raise HTTPException(
            status_code=404,
            detail=f"No cached sector report for {sector}. Reports are generated asynchronously when company reports update."
        )

    return {
        "id": report.id,
        "sector": report.sector,
        "report_data": report.report_data,
        "overall_sentiment": report.overall_sentiment,
        "confidence_score": report.confidence_score,
        "assets_count": report.assets_count,
        "model_used": report.model_used,
        "prompt_version": report.prompt_version,
        "last_updated": report.created_at.isoformat() if report.created_at else None,
    }


@router.post("/sector/{sector}/regenerate")
async def trigger_sector_regeneration(
    sector: str,
    session: AsyncSession = Depends(get_async_session),
):
    """Manually trigger a sector report regeneration by enqueuing a job."""
    from backend.services.ai_worker import enqueue_job

    queued = await enqueue_job(
        session=session,
        job_type="sector_report",
        target_type="sector",
        target_id=0,
        payload={"sector": sector},
        priority=10,
    )

    return {
        "status": "queued" if queued else "already_pending",
        "sector": sector,
    }


@router.post("/market/regenerate")
async def trigger_market_regeneration(
    session: AsyncSession = Depends(get_async_session),
):
    """Manually trigger a market report regeneration by enqueuing a job."""
    from backend.services.ai_worker import enqueue_job

    queued = await enqueue_job(
        session=session,
        job_type="market_report",
        target_type="market",
        target_id=0,
        payload={},
        priority=5,
    )

    return {
        "status": "queued" if queued else "already_pending",
    }


@router.get("/company/{ticker}/history")
async def get_company_report_history(
    ticker: str,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_async_session),
):
    """Get the history of AI intelligence reports for a company.

    Returns past report snapshots so users can track how sentiment/confidence evolved.
    """
    from sqlalchemy import select, func
    from backend.models.ai_report_history import AICompanyReportHistory

    offset = (page - 1) * limit
    total_row = await session.execute(
        select(func.count(AICompanyReportHistory.id)).where(
            AICompanyReportHistory.ticker == ticker.upper()
        )
    )
    total = total_row.scalar() or 0

    rows = await session.execute(
        select(AICompanyReportHistory)
        .where(AICompanyReportHistory.ticker == ticker.upper())
        .order_by(AICompanyReportHistory.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    history_rows = list(rows.scalars().all())

    return {
        "ticker": ticker.upper(),
        "total": total,
        "page": page,
        "limit": limit,
        "entries": [
            {
                "id": r.id,
                "original_report_id": r.original_report_id,
                "overall_sentiment": r.overall_sentiment,
                "confidence_score": r.confidence_score,
                "articles_count": r.articles_count,
                "model_used": r.model_used,
                "prompt_version": r.prompt_version,
                "price_snapshot": r.price_snapshot,
                "report_data": r.report_data_snapshot,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in history_rows
        ],
    }


@router.get("/queue/status")
async def get_queue_status(
    session: AsyncSession = Depends(get_async_session),
):
    """Get current AI job queue status (counts by status)."""
    from sqlalchemy import select, func
    from backend.models.ai_job_queue import AIJobQueue

    total_row = await session.execute(
        select(func.count(AIJobQueue.id)).where(AIJobQueue.status.in_(["pending", "processing"]))
    )
    pending_count = total_row.scalar() or 0

    jobs_row = await session.execute(
        select(AIJobQueue.job_type, AIJobQueue.status, func.count(AIJobQueue.id).label("cnt"))
        .where(AIJobQueue.status.in_(["pending", "processing"]))
        .group_by(AIJobQueue.job_type, AIJobQueue.status)
    )
    breakdown = {}
    for row in jobs_row.fetchall():
        key = f"{row[0]}_{row[1]}"
        breakdown[key] = row[1] if isinstance(row[1], int) else row[2]

    return {
        "pending_processing_count": pending_count,
        "breakdown": breakdown,
    }


@router.get("/pipeline/status")
async def get_pipeline_status(
    session: AsyncSession = Depends(get_async_session),
):
    """Get comprehensive pipeline status for the frontend monitor.
    
    Returns counts and stats for every layer of the data ingestion and AI processing pipeline.
    This endpoint is designed for the Pipeline Monitor dashboard to visualize all data generation.
    """
    from sqlalchemy import select, func
    from backend.models.ai_reports import AICompanyReport, AISectorReport, AIMarketReport
    from backend.models.ai_job_queue import AIJobQueue

    # --- News articles stats ---
    try:
        from backend.models.news import NewsArticle
        news_total_row = await session.execute(select(func.count(NewsArticle.id)))
        news_total = news_total_row.scalar() or 0

        now_local = datetime.now()
        today_start = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        # Use COALESCE-style logic: pub_date may be NULL so check IS NOT NULL first.
        # A row counts if either pub_date OR imported_at falls on today.
        news_today_row = await session.execute(
            select(func.count(NewsArticle.id)).where(
                ((NewsArticle.pub_date.isnot(None)) & (NewsArticle.pub_date >= today_start)) |
                (NewsArticle.imported_at >= today_start)
            )
        )
        news_today = news_today_row.scalar() or 0

        # Watchlist count (needed for coverage calculation)
        from backend.models.watchlist import WatchlistModel
        wl_tickers_result = await session.execute(
            select(WatchlistModel.ticker)
        )
        wl_ticker_set = {row[0] for row in wl_tickers_result.all()}

        # Distinct watchlist tickers that have news coverage
        # (only count tickers the user actually monitors)
        if wl_ticker_set:
            news_wl_tickers_row = await session.execute(
                select(func.count(func.distinct(NewsArticle.ticker))).where(
                    NewsArticle.ticker.in_(wl_ticker_set)
                )
            )
            news_ticker_count = news_wl_tickers_row.scalar() or 0
        else:
            news_ticker_count = 0

        # Recent articles ingested today (up to 10 most recent)
        try:
            recent_articles_row = await session.execute(
                select(NewsArticle.id, NewsArticle.title, NewsArticle.ticker, NewsArticle.pub_date, NewsArticle.article_url)
                .where(
                    ((NewsArticle.pub_date.isnot(None)) & (NewsArticle.pub_date >= today_start)) |
                    (NewsArticle.imported_at >= today_start)
                )
                .order_by(NewsArticle.imported_at.desc())
                .limit(10)
            )
            recent_articles = []
            for r in recent_articles_row.fetchall():
                recent_articles.append({
                    "id": r[0],
                    "title": (r[1] or "Untitled")[:120],
                    "ticker": r[2],
                    "pub_date": r[3].isoformat() if r[3] else None,
                    "article_url": r[4],
                })
        except Exception:
            recent_articles = []

        # Per-watchlist-ticker coverage status
        try:
            ticker_status = []
            for ticker in sorted(wl_ticker_set):
                # Count articles today for this ticker
                ta_row = await session.execute(
                    select(func.count(NewsArticle.id)).where(
                        NewsArticle.ticker == ticker,
                        ((NewsArticle.pub_date.isnot(None)) & (NewsArticle.pub_date >= today_start)) |
                        (NewsArticle.imported_at >= today_start)
                    )
                )
                articles_today_count = ta_row.scalar() or 0
                # Check if there's a company report for this ticker
                cr_row = await session.execute(
                    select(func.count(AICompanyReport.id)).where(
                        AICompanyReport.ticker == ticker
                    )
                )
                has_report = (cr_row.scalar() or 0) > 0
                ticker_status.append({
                    "ticker": ticker,
                    "articles_today": articles_today_count,
                    "has_report": has_report,
                })
        except Exception:
            ticker_status = []
    except Exception as e:
        logger.error(f"[Pipeline Status] Failed to query news stats: {e}")
        news_total = 0
        news_today = 0
        news_ticker_count = 0
        recent_articles = []
        ticker_status = []

    # --- Company reports stats ---
    company_reports_row = await session.execute(select(func.count(AICompanyReport.id)))
    company_reports_total = company_reports_row.scalar() or 0
    
    company_reports_distinct_row = await session.execute(
        select(func.count(func.distinct(AICompanyReport.ticker)))
    )
    company_reports_tickers = company_reports_distinct_row.scalar() or 0

    # --- Sector reports stats ---
    sector_reports_row = await session.execute(select(func.count(AISectorReport.id)))
    sector_reports_total = sector_reports_row.scalar() or 0
    
    sector_reports_distinct_row = await session.execute(
        select(func.count(func.distinct(AISectorReport.sector)))
    )
    sector_reports_count = sector_reports_distinct_row.scalar() or 0

    # --- Market reports stats ---
    market_reports_row = await session.execute(select(func.count(AIMarketReport.id)))
    market_reports_total = market_reports_row.scalar() or 0

    # --- Job queue stats ---
    queue_pending_row = await session.execute(
        select(func.count(AIJobQueue.id)).where(AIJobQueue.status == "pending")
    )
    queue_pending = queue_pending_row.scalar() or 0
    
    queue_processing_row = await session.execute(
        select(func.count(AIJobQueue.id)).where(AIJobQueue.status == "processing")
    )
    queue_processing = queue_processing_row.scalar() or 0
    
    queue_completed_row = await session.execute(
        select(func.count(AIJobQueue.id)).where(AIJobQueue.status == "completed")
    )
    queue_completed = queue_completed_row.scalar() or 0
    
    queue_failed_row = await session.execute(
        select(func.count(AIJobQueue.id)).where(AIJobQueue.status == "failed")
    )
    queue_failed = queue_failed_row.scalar() or 0

    # Job type breakdown
    job_type_breakdown = {}
    try:
        jt_row = await session.execute(
            select(AIJobQueue.job_type, AIJobQueue.status, func.count(AIJobQueue.id).label("cnt"))
            .group_by(AIJobQueue.job_type, AIJobQueue.status)
        )
        for row in jt_row.fetchall():
            job_type = row[0] or "unknown"
            status = row[1] or "unknown"
            count = row[2] or 0
            if job_type not in job_type_breakdown:
                job_type_breakdown[job_type] = {}
            job_type_breakdown[job_type][status] = count
    except Exception:
        pass

    # --- Watchlist tickers ---
    try:
        from backend.models.watchlist import WatchlistModel
        watchlist_row = await session.execute(select(func.count(WatchlistModel.id)))
        watchlist_count = watchlist_row.scalar() or 0
    except Exception:
        watchlist_count = 0

    # --- Assets ---
    try:
        from backend.models.asset import Asset
        assets_row = await session.execute(select(func.count(Asset.id)))
        assets_count = assets_row.scalar() or 0
    except Exception:
        assets_count = 0

    # --- Processing job details (what's currently running) ---
    processing_tasks = []
    try:
        proc_row = await session.execute(
            select(AIJobQueue.job_type, AIJobQueue.target_id, AIJobQueue.updated_at)
            .where(AIJobQueue.status == "processing")
            .order_by(AIJobQueue.updated_at.desc())
        )
        for r in proc_row.fetchall():
            processing_tasks.append({
                "job_type": r[0],
                "target_id": r[1],
                "started_at": r[2].isoformat() if r[2] else None,
            })
    except Exception:
        pass

    return {
        "news": {
            "total_articles": news_total,
            "articles_today": news_today,
            "tickers_with_news": news_ticker_count,
            "recent_articles": recent_articles,
            "ticker_status": ticker_status,
        },
        "company_reports": {
            "total_reports": company_reports_total,
            "tickers_covered": company_reports_tickers,
        },
        "sector_reports": {
            "total_reports": sector_reports_total,
            "sectors_covered": sector_reports_count,
        },
        "market_reports": {
            "total_reports": market_reports_total,
        },
        "job_queue": {
            "pending": queue_pending,
            "processing": queue_processing,
            "completed": queue_completed,
            "failed": queue_failed,
            "total": queue_pending + queue_processing + queue_completed + queue_failed,
            "by_type": job_type_breakdown,
        },
        "watchlist": {
            "tickers": watchlist_count,
        },
        "assets": {
            "total": assets_count,
        },
    }


# ------------------------------------------------------------------
# Unified Intelligence Browser — combine all report types
# ------------------------------------------------------------------

@router.get("/unified")
async def get_unified_intelligence(
    ticker: Optional[str] = Query(None, description="Filter by ticker/symbol"),
    report_type: Optional[str] = Query(None, pattern="^(company|sector|market)$", description="Filter by report type"),
    sentiment: Optional[str] = Query(None, description="Filter by overall sentiment"),
    date_from: Optional[str] = Query(None, alias="from", description="ISO date filter (lower bound)"),
    date_to: Optional[str] = Query(None, alias="to", description="ISO date filter (upper bound)"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_async_session),
):
    """Unified endpoint that combines company, sector, and market reports.

    Returns a single paginated list of all report types with consistent fields.
    Useful for building an Intelligence Browser page.
    """
    from sqlalchemy import select, func

    from backend.models.ai_reports import AICompanyReport, AISectorReport, AIMarketReport

    date_start = _parse_date(date_from, "date_from")
    date_end = _parse_date(date_to, "date_to")

    results: list[Dict[str, Any]] = []
    total_count = 0

    # --- Company Reports ---
    if not report_type or report_type == "company":
        q = select(AICompanyReport)
        if ticker:
            q = q.where(AICompanyReport.ticker == ticker.upper())
        if sentiment:
            q = q.where(AICompanyReport.overall_sentiment.ilike(f"%{sentiment}%"))
        if date_start:
            q = q.where(AICompanyReport.created_at >= date_start)
        if date_end:
            q = q.where(AICompanyReport.created_at <= date_end)

        count_row = await session.execute(
            select(func.count(AICompanyReport.id)).where(*[c for c in q._where_criteria if hasattr(c, 'name')]) if hasattr(q, '_where_criteria') else None
        )
        # Simpler approach: just fetch and count
        rows = await session.execute(q.order_by(AICompanyReport.created_at.desc()))
        company_reports = list(rows.scalars().all())

        for r in company_reports:
            preview = ""
            if isinstance(r.report_data, dict):
                summary = r.report_data.get("executive_summary", "")
                preview = (summary or "")[:150]
            results.append({
                "id": f"company_{r.id}",
                "ticker": r.ticker,
                "company_name": None,
                "report_type": "company",
                "overall_sentiment": r.overall_sentiment,
                "confidence_score": r.confidence_score,
                "articles_count": r.articles_count,
                "summary_preview": preview,
                "price_snapshot": r.price_snapshot,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "model_used": r.model_used,
            })

    # --- Sector Reports ---
    if not report_type or report_type == "sector":
        q = select(AISectorReport)
        if ticker:
            q = q.where(AISectorReport.sector.ilike(f"%{ticker}%"))
        if sentiment:
            q = q.where(AISectorReport.overall_sentiment.ilike(f"%{sentiment}%"))
        if date_start:
            q = q.where(AISectorReport.created_at >= date_start)
        if date_end:
            q = q.where(AISectorReport.created_at <= date_end)

        rows = await session.execute(q.order_by(AISectorReport.created_at.desc()))
        sector_reports = list(rows.scalars().all())

        for r in sector_reports:
            preview = ""
            if isinstance(r.report_data, dict):
                summary = r.report_data.get("executive_summary", r.report_data.get("sector_outlook", ""))
                preview = (summary or "")[:150]
            results.append({
                "id": f"sector_{r.id}",
                "ticker": r.sector,
                "company_name": None,
                "report_type": "sector",
                "overall_sentiment": r.overall_sentiment,
                "confidence_score": r.confidence_score,
                "articles_count": r.assets_count,
                "summary_preview": preview,
                "price_snapshot": None,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "model_used": r.model_used,
            })

    # --- Market Reports ---
    if not report_type or report_type == "market":
        q = select(AIMarketReport)
        if sentiment:
            q = q.where(AIMarketReport.overall_sentiment.ilike(f"%{sentiment}%"))
        if date_start:
            q = q.where(AIMarketReport.created_at >= date_start)
        if date_end:
            q = q.where(AIMarketReport.created_at <= date_end)

        rows = await session.execute(q.order_by(AIMarketReport.created_at.desc()))
        market_reports = list(rows.scalars().all())

        for r in market_reports:
            preview = ""
            if isinstance(r.report_data, dict):
                summary = r.report_data.get("executive_summary", r.report_data.get("summary_text", ""))
                preview = (summary or "")[:150]
            results.append({
                "id": f"market_{r.id}",
                "ticker": "MARKET",
                "company_name": None,
                "report_type": "market",
                "overall_sentiment": r.overall_sentiment,
                "confidence_score": r.confidence_score,
                "articles_count": None,
                "summary_preview": preview,
                "price_snapshot": None,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "model_used": r.model_used,
            })

    # Sort all results by created_at descending
    results.sort(key=lambda x: x["created_at"] or "", reverse=True)

    total_count = len(results)
    offset = (page - 1) * limit
    paginated = results[offset:offset + limit]
    has_more = (page * limit) < total_count

    return {
        "items": paginated,
        "total": total_count,
        "page": page,
        "limit": limit,
        "has_more": has_more,
    }
