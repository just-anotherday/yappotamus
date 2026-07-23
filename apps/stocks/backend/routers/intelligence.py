"""Authenticated intelligence retrieval and generation APIs."""

from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config.database import get_async_session
from backend.config.settings import settings
from backend.intelligence.article_service import ARTICLE_PROMPT_HASH, article_source_content_hash
from backend.models.intelligence import ArticleIntelligence, DailyTickerIntelligence
from backend.models.news import NewsArticle
from backend.services.ai_worker import enqueue_job

router = APIRouter(prefix="/api/intelligence", tags=["intelligence"])


class GenerateRequest(BaseModel):
    force: bool = False
    provider: str | None = None
    model: str | None = None


def _article_out(row: ArticleIntelligence) -> dict:
    return {"status": row.status, "article_id": row.article_id, "ticker": row.ticker, "summary": row.summary,
            "sentiment": row.sentiment, "confidence": row.confidence, "importance_score": row.importance_score,
            "provider": row.provider, "model": row.model, "prompt_version": row.prompt_version,
            "prompt_hash": row.prompt_hash, "source_content_hash": row.source_content_hash,
            "input_hash": row.input_hash, "generation_revision": row.generation_revision,
            "generated_at": row.generated_at, "created_at": row.created_at, "structured_data": row.structured_data}


@router.get("/articles/{article_id}")
async def article_current(article_id: int, session: AsyncSession = Depends(get_async_session)):
    article = await session.get(NewsArticle, article_id)
    if not article or not settings.is_intelligence_pilot_ticker(article.ticker): raise HTTPException(404, "article intelligence not found")
    row = (await session.execute(select(ArticleIntelligence).where(ArticleIntelligence.article_id == article_id, ArticleIntelligence.status == "completed").order_by(ArticleIntelligence.generation_revision.desc()).limit(1))).scalar_one_or_none()
    if not row: raise HTTPException(404, "article intelligence not found")
    return _article_out(row)


@router.get("/articles/{article_id}/history")
async def article_history(article_id: int, limit: int = Query(20, ge=1, le=100), session: AsyncSession = Depends(get_async_session)):
    article = await session.get(NewsArticle, article_id)
    if not article or not settings.is_intelligence_pilot_ticker(article.ticker): raise HTTPException(404, "article intelligence not found")
    rows = (await session.execute(select(ArticleIntelligence).where(ArticleIntelligence.article_id == article_id).order_by(ArticleIntelligence.generation_revision.desc()).limit(limit))).scalars().all()
    return {"items": [_article_out(row) for row in rows], "limit": limit}


@router.post("/articles/{article_id}/generate", status_code=202)
async def article_generate(article_id: int, request: GenerateRequest, session: AsyncSession = Depends(get_async_session)):
    article = await session.get(NewsArticle, article_id)
    if not article: raise HTTPException(404, "article not found")
    if not settings.is_intelligence_pilot_ticker(article.ticker): raise HTTPException(404, "article not in intelligence pilot universe")
    source_hash = article_source_content_hash(article)
    queued = await enqueue_job(session, "article_intelligence", "article", article_id,
        payload=request.model_dump(), priority=8,
        dedupe_key=f"{article_id}:{source_hash}:{ARTICLE_PROMPT_HASH}:{request.force}:{request.provider}:{request.model}")
    return {"status": "queued" if queued else "reused", "article_id": article_id}


@router.get("/daily/{ticker}/{trading_date}")
async def daily_current(ticker: str, trading_date: date, session: AsyncSession = Depends(get_async_session)):
    normalized_ticker = ticker.strip().upper()
    if not settings.is_intelligence_pilot_ticker(normalized_ticker): raise HTTPException(404, "daily intelligence not found")
    row = (await session.execute(select(DailyTickerIntelligence).where(DailyTickerIntelligence.ticker == normalized_ticker, DailyTickerIntelligence.trading_date == trading_date, DailyTickerIntelligence.status == "completed").order_by(DailyTickerIntelligence.revision.desc()).limit(1))).scalar_one_or_none()
    if not row: raise HTTPException(404, "daily intelligence not found")
    return {"ticker": row.ticker, "trading_date": row.trading_date, "revision": row.revision, "status": row.status,
            "executive_summary": row.executive_summary, "overall_sentiment": row.overall_sentiment,
            "confidence": row.confidence, "structured_data": row.structured_data, "source_set_hash": row.source_set_hash}