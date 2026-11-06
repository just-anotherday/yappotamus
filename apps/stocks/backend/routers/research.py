"""Private owner-scoped research tools. Browsers never access DB tables directly."""
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, update, func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from backend.auth import verify_app_access_token
from backend.config.database import get_async_session
from backend.config.settings import settings
from backend.lib.tickers import normalize_ticker
from backend.lib.timestamps import utc_now_naive
from backend.models.news import NewsArticle
from backend.models.news_schemas import NewsArticleOut
from backend.models.report import AnalysisReportModel
from backend.models.research import ResearchNote, ArticleReadingState, ReportRun
from backend.services.report_run_service import create_run, execute_retry, expire_interrupted_runs, run_payload
from backend.services.watchlist_service import get_report_tickers as get_all_tickers

router = APIRouter(prefix="/api/research", tags=["research"])


async def research_owner(_=Depends(verify_app_access_token)) -> str:
    # Supabase validation is owner-only and verifies the user remotely. Never
    # accept an owner ID from a request body or trust an unverified JWT claim.
    return settings.SUPABASE_ALLOWED_USER_ID if settings.AUTH_PROVIDER == "supabase" else "legacy-single-user"


def ticker_key(value):
    try:
        return normalize_ticker(value)
    except ValueError as exc:
        raise HTTPException(422, "Invalid ticker") from exc


class NoteUpdate(BaseModel):
    text: str = Field(max_length=10000)
    version: int = Field(ge=0)


@router.get("/notes/{ticker}")
async def note_get(ticker: str, owner=Depends(research_owner), session: AsyncSession = Depends(get_async_session)):
    row = await session.get(ResearchNote, (owner, ticker_key(ticker)))
    return {"text": row.text if row else "", "version": row.version if row else 0, "updated_at": row.updated_at if row else None}


@router.put("/notes/{ticker}")
async def note_save(ticker: str, body: NoteUpdate, owner=Depends(research_owner), session: AsyncSession = Depends(get_async_session)):
    ticker = ticker_key(ticker)
    if body.version == 0:
        stmt = insert(ResearchNote).values(owner_id=owner, ticker=ticker, text=body.text, version=1, updated_at=utc_now_naive()).on_conflict_do_nothing().returning(ResearchNote.version)
    else:
        stmt = update(ResearchNote).where(ResearchNote.owner_id == owner, ResearchNote.ticker == ticker, ResearchNote.version == body.version).values(text=body.text, version=body.version + 1, updated_at=utc_now_naive()).returning(ResearchNote.version)
    version = (await session.execute(stmt)).scalar_one_or_none()
    if version is None:
        raise HTTPException(409, "This note changed on another device. Keep your draft and reload before saving.")
    await session.commit()
    return {"version": version, "text": body.text}


class ArticleUpdate(BaseModel):
    saved: bool | None = None
    read: bool | None = None


@router.get("/article-state")
async def article_states(owner=Depends(research_owner), session: AsyncSession = Depends(get_async_session)):
    rows = (await session.execute(select(ArticleReadingState).where(ArticleReadingState.owner_id == owner))).scalars()
    return [{"article_id": r.article_id, "saved": r.saved, "read": r.read} for r in rows]


@router.put("/article-state/{article_id}")
async def article_state_save(article_id: int, body: ArticleUpdate, owner=Depends(research_owner), session: AsyncSession = Depends(get_async_session)):
    if not await session.get(NewsArticle, article_id):
        raise HTTPException(404, "Article not found")
    fields = {key: value for key, value in body.model_dump(exclude_unset=True).items() if value is not None}
    if not fields:
        raise HTTPException(422, "Choose saved or read state")
    stmt = insert(ArticleReadingState).values(owner_id=owner, article_id=article_id, saved=fields.get("saved", False), read=fields.get("read", False)).on_conflict_do_update(index_elements=["owner_id", "article_id"], set_=fields).returning(ArticleReadingState)
    row = (await session.execute(stmt)).scalar_one()
    await session.commit()
    return {"article_id": row.article_id, "saved": row.saved, "read": row.read}


@router.get("/news")
async def personal_news(view: str = Query(pattern="^(saved|unread|saved-unread)$"), ticker: str | None = None, start_date: str | None = None, end_date: str | None = None, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0), owner=Depends(research_owner), session: AsyncSession = Depends(get_async_session)):
    from backend.routers.analysis_reports import _parse_date
    states = ArticleReadingState
    join = (states.owner_id == owner) & (states.article_id == NewsArticle.id)
    filters = []
    if "saved" in view:
        filters.append(states.saved.is_(True))
    if "unread" in view:
        filters.append(func.coalesce(states.read, False).is_(False))
    if ticker:
        filters.append(NewsArticle.ticker == ticker_key(ticker))
    if start_date:
        filters.append(NewsArticle.pub_date >= _parse_date(start_date, "from_date"))
    if end_date:
        filters.append(NewsArticle.pub_date < _parse_date(end_date, "to_date"))
    base = select(NewsArticle).outerjoin(states, join).where(*filters)
    total = (await session.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    articles = (await session.execute(base.order_by(NewsArticle.pub_date.desc(), NewsArticle.id.desc()).offset(offset).limit(limit))).scalars()
    return {"articles": [NewsArticleOut.model_validate(a) for a in articles], "total": total, "has_more": offset + limit < total}


@router.get("/runs/latest")
async def latest_run(session: AsyncSession = Depends(get_async_session)):
    await expire_interrupted_runs(session)
    row = (await session.execute(select(ReportRun).order_by(ReportRun.id.desc()).limit(1))).scalar_one_or_none()
    successful = (await session.execute(select(ReportRun.finished_at).where(ReportRun.status == "completed").order_by(ReportRun.id.desc()).limit(1))).scalar_one_or_none()
    await session.commit()
    return {"run": run_payload(row), "last_successful_at": successful}


@router.post("/runs/{run_id}/retry", status_code=202)
async def retry_run(run_id: int, background: BackgroundTasks, session: AsyncSession = Depends(get_async_session)):
    row = await session.get(ReportRun, run_id)
    if not row:
        raise HTTPException(404, "Run not found")
    if row.status in ("queued", "running"):
        raise HTTPException(409, "This run is still active")
    current = set(await get_all_tickers(session))
    completed = {item["ticker"] for item in row.outcomes if item["status"] == "completed"}
    tickers = [t for t in row.tickers if t not in completed and t in current]
    if not tickers:
        raise HTTPException(409, "No failed tickers remain in your watchlist")
    # Read once, then reserve atomically using the unique active-run index.
    # The prior run stays immutable; each retry has a separate history record.
    child_id = await create_run(tickers, kind="retry", parent_id=run_id)
    background.add_task(execute_retry, child_id)
    return {"run_id": child_id, "tickers": tickers}


@router.get("/reports/{report_id}/changes")
async def report_changes(report_id: int, session: AsyncSession = Depends(get_async_session)):
    row = await session.get(AnalysisReportModel, report_id)
    if not row:
        raise HTTPException(404, "Report not found")
    previous = (await session.execute(select(AnalysisReportModel.id, AnalysisReportModel.overall_sentiment, AnalysisReportModel.confidence_score, AnalysisReportModel.created_at).where(AnalysisReportModel.ticker == row.ticker, ((AnalysisReportModel.created_at < row.created_at) | ((AnalysisReportModel.created_at == row.created_at) & (AnalysisReportModel.id < row.id)))).order_by(AnalysisReportModel.created_at.desc(), AnalysisReportModel.id.desc()).limit(1))).mappings().one_or_none()
    return {"previous": dict(previous) if previous else None, "current": {"overall_sentiment": row.overall_sentiment, "confidence_score": row.confidence_score, "created_at": row.created_at}}
