"""Report persistence service

Handles CRUD operations on the analysis_reports table.
Keeps all DB access out of routers so future consumers (scheduled jobs, exports) reuse this layer.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.lib.timestamps import utc_now_naive
from backend.models.report import AnalysisReportModel
from backend.models.report_schemas import ReportCompanyOption, ReportSummaryOut
from backend.models.asset import Asset
from backend.models.ai_reports import AICompanyReport  # Register Asset's related mapper.

logger = logging.getLogger(__name__)

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


async def list_report_companies(session: AsyncSession) -> List[ReportCompanyOption]:
    """Company choices across all saved reports, independent of pagination/watchlist."""
    company_name = func.coalesce(
        func.nullif(Asset.name, ""), AnalysisReportModel.ticker
    )
    result = await session.execute(
        select(
            AnalysisReportModel.ticker,
            company_name.label("company_name"),
            func.count(AnalysisReportModel.id).label("report_count"),
        )
        .outerjoin(Asset, Asset.primary_ticker == AnalysisReportModel.ticker)
        .group_by(AnalysisReportModel.ticker, Asset.name)
        .order_by(func.lower(company_name), AnalysisReportModel.ticker)
    )
    return [ReportCompanyOption(**row._mapping) for row in result.all()]


def count_cited_articles(report_data: Any) -> int:
    """Return the trusted stored citation count, safely handling legacy reports."""

    if not isinstance(report_data, dict):
        return 0
    articles_used = report_data.get("articles_used")
    return len(articles_used) if isinstance(articles_used, list) else 0

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
        # Do not depend on the database session timezone for this legacy
        # TIMESTAMP WITHOUT TIME ZONE column. Persist a UTC wall clock value.
        created_at=utc_now_naive(),
    )
    session.add(obj)
    logger.info(
        "[AI][Citations] persisted_count=%d supplied_count=%d ticker=%s",
        count_cited_articles(report_data),
        articles_count,
        ticker.upper(),
    )
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
    # Count citations in PostgreSQL; don't transfer/decode entire report JSON bodies.
    articles_used = AnalysisReportModel.report_data["articles_used"]
    cited_count = case(
        (func.jsonb_typeof(articles_used) == "array", func.jsonb_array_length(articles_used)),
        else_=0,
    ).label("articles_cited_count")
    stmt = select(
        AnalysisReportModel.id, AnalysisReportModel.ticker,
        AnalysisReportModel.overall_sentiment, AnalysisReportModel.confidence_score,
        AnalysisReportModel.articles_count, cited_count,
        AnalysisReportModel.model_used, AnalysisReportModel.prompt_version,
        AnalysisReportModel.prompt_hash, AnalysisReportModel.current_price_at_analysis,
        AnalysisReportModel.created_at,
    ).order_by(direction).limit(limit).offset(offset)
    stmt = apply_where(stmt)

    rows = (await session.execute(stmt)).mappings().all()
    summaries = []
    for idx, r in enumerate(rows):
        data = dict(r)
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
