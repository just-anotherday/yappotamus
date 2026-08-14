from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.news_schemas import NewsArticleOut, NewsPaginatedResponse
from backend.config.database import async_session_factory, get_async_session
from backend.services.news_query_service import query_news, get_distinct_tickers as query_distinct_tickers
from backend.services.news_ingestion_service import fetch_and_ingest_news, fetch_and_ingest_watchlist_once

router = APIRouter(tags=["news"])


@router.post("/api/news/ingest")
async def ingest_watchlist_news():
    """Immediately ingest news for every ticker in the persisted watchlist."""
    return await fetch_and_ingest_watchlist_once(async_session_factory, force=True)


@router.post("/api/news/ingest/{ticker}")
async def ingest_ticker_news(
    ticker: str,
    session: AsyncSession = Depends(get_async_session),
):
    """Immediately ingest recent news for one ticker."""
    normalized_ticker = ticker.strip().upper()
    provider_state = {}
    count = await fetch_and_ingest_news(
        normalized_ticker,
        session,
        limit=30,
        _provider_state=provider_state,
    )
    if provider_state.get("last_outcome") != "success":
        raise HTTPException(status_code=503, detail="News provider request failed")
    return {
        "status": "completed",
        "ticker": normalized_ticker,
        "articles_processed": count,
    }


@router.get("/news", response_model=NewsPaginatedResponse)
async def get_news_from_db(
    ticker: Optional[str] = Query(None, description="Filter by ticker symbol"),
    limit: int = Query(50, ge=1, le=200, description="Number of articles per page"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    start_date: Optional[str] = Query(None, description="Filter articles from this date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="Filter articles until this date (YYYY-MM-DD)"),
    session: AsyncSession = Depends(get_async_session),
):
    """Return paginated news articles from PostgreSQL."""
    articles, total = await query_news(
        session, ticker=ticker, start_date=start_date, end_date=end_date, limit=limit, offset=offset,
    )

    page_num = (offset // limit) + 1 if limit > 0 else 1
    has_more = (offset + len(articles)) < total

    return NewsPaginatedResponse(
        articles=[NewsArticleOut.model_validate(a) for a in articles],
        total=total,
        page=page_num,
        limit=limit,
        has_more=has_more,
    )


@router.get("/news/tickers")
async def get_distinct_news_tickers(
    session: AsyncSession = Depends(get_async_session),
):
    """Return all distinct, non-null tickers from news_articles."""
    tickers = await query_distinct_tickers(session)
    return {"tickers": sorted(tickers)}
