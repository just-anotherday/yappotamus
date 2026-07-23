"""Report persistence service

Handles CRUD operations on the analysis_reports table.
Keeps all DB access out of routers so future consumers (scheduled jobs, exports) reuse this layer.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.report import AnalysisReportModel
from backend.models.report_schemas import ReportSummaryOut

logger = logging.getLogger(__name__)

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100

async def create_report(
    session: AsyncSession,
    ticker: str,
    report_data: Dict[str, Any],
    articles_count: int,
    model_used: str,
    prompt_version: str = "1.0",
    prompt_hash: Optional[str] = None,
    current_price_at_analysis: Optional[float] = None,
) -> int:
    """Save a new analysis report and return its id."""
    sentiment = report_data.get("overall_sentiment", "Neutral")
    confidence = report_data.get("confidence_score", 50)

    obj = AnalysisReportModel(
        ticker=ticker.upper(),
        report_data=report_data,
        overall_sentiment=sentiment,
        confidence_score=confidence,
        articles_count=articles_count,
        model_used=model_used or "",
        prompt_version=prompt_version,
        prompt_hash=prompt_hash,
        current_price_at_analysis=current_price_at_analysis,
    )
    session.add(obj)
    await session.flush()
    return obj.id


async def list_reports(
    session: AsyncSession,
    ticker: Optional[str] = None,
    sentiment: Optional[str] = None,
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
    page: int = 1,
    limit: int = DEFAULT_PAGE_SIZE,
    sort: str = "newest",
) -> Tuple[List[ReportSummaryOut], int]:
    """Return (summaries, total_count) with pagination.

    Each summary gets a consecutive report_number via SQL ROW_NUMBER()
    so numbers are always 1, 2, 3... regardless of deletions or gaps in PKs.
    """
    limit = min(max(limit, 1), MAX_PAGE_SIZE)
    offset = (page - 1) * limit

    conditions = []
    if ticker:
        conditions.append(AnalysisReportModel.ticker == ticker.upper())
    if sentiment:
        conditions.append(AnalysisReportModel.overall_sentiment.ilike(f"%{sentiment}%"))
    if from_date:
        conditions.append(AnalysisReportModel.created_at >= from_date)
    if to_date:
        conditions.append(AnalysisReportModel.created_at <= to_date)

    def apply_where(stmt):
        """Apply filter conditions to a statement (avoids reusing clause objects)."""
        for cond in conditions:
            stmt = stmt.where(cond)
        return stmt

    # Count query
    count_stmt = select(func.count(AnalysisReportModel.id))
    count_stmt = apply_where(count_stmt)
    total = (await session.execute(count_stmt)).scalar_one() or 0

    # Data query — consecutive numbering via row_number = offset + index + 1
    direction = AnalysisReportModel.created_at.desc() if sort == "newest" else AnalysisReportModel.created_at.asc()
    stmt = select(AnalysisReportModel).order_by(direction).limit(limit).offset(offset)
    stmt = apply_where(stmt)

    rows = list((await session.execute(stmt)).scalars().all())
    summaries = []
    for idx, r in enumerate(rows):
        data = {
            "id": r.id,
            "ticker": r.ticker,
            "overall_sentiment": r.overall_sentiment,
            "confidence_score": r.confidence_score,
            "articles_count": r.articles_count,
            "model_used": r.model_used,
            "prompt_version": r.prompt_version,
            "prompt_hash": r.prompt_hash,
            "current_price_at_analysis": r.current_price_at_analysis,
            "created_at": r.created_at,
        }
        data["report_number"] = offset + idx + 1
        summaries.append(ReportSummaryOut(**data))
    return summaries, total


async def get_report_by_id(session: AsyncSession, report_id: int) -> Optional[AnalysisReportModel]:
    """Fetch a single report by primary key."""
    row = await session.get(AnalysisReportModel, report_id)
    return row


async def get_latest_for_ticker(session: AsyncSession, ticker: str) -> Optional[AnalysisReportModel]:
    """Get the most recent report for a given ticker."""
    stmt = (
        select(AnalysisReportModel)
        .where(AnalysisReportModel.ticker == ticker.upper())
        .order_by(AnalysisReportModel.created_at.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalars().first()


async def delete_report(session: AsyncSession, report_id: int) -> bool:
    """Delete a report. Returns True if found and deleted."""
    row = await session.get(AnalysisReportModel, report_id)
    if row is None:
        return False
    await session.delete(row)
    return True
