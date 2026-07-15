"""
Financial Analysis Router

Exposes REST endpoints for generating AI-powered financial analysis reports
using news articles and market price data via Ollama.
"""

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import List, Optional

from dotenv import load_dotenv
load_dotenv()

from fastapi import APIRouter, HTTPException, Query, Body, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.analysis import (
    FinancialAnalysisRequest,
    FinancialAnalysisResponse,
    NewsArticleRequest,
    OllamaConfigResponse,
    PriceDataRequest,
)
from backend.models.news import NewsArticle
from backend.config.database import get_async_session
from backend.services.report_service import create_report
from backend.services.ollama_service import (
    generate_analysis,
    get_ollama_config,
    check_ollama_connection,
    _get_timeout_for_model,
)
from backend.services.hybrid_data_service import get_hybrid_stock_price

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/analysis", tags=["analysis"])

# Default fallback timeout (configurable via ANALYSIS_TIMEOUT_S env var)
ANALYSIS_TIMEOUT = float(os.getenv("ANALYSIS_TIMEOUT_S", "900"))  # seconds (default 15 min)


@router.get("/config", response_model=OllamaConfigResponse)
async def analysis_get_config():
    """Get current Ollama configuration and connection status."""
    return await get_ollama_config()


@router.post("/generate", response_model=FinancialAnalysisResponse)
async def analysis_generate(
    request: FinancialAnalysisRequest,
    model: Optional[str] = Query(None, description="Override default Ollama model"),
    session: AsyncSession = Depends(get_async_session),
):
    """
    Generate a comprehensive financial analysis report.

    Accepts news articles and price data, feeds them to the LLM,
    and returns a structured analysis report.
    """
    # Validate Ollama is reachable
    connected = await check_ollama_connection()
    if not connected:
        raise HTTPException(
            status_code=503,
            detail="Ollama server is unreachable. Ensure Ollama is running on the configured endpoint.",
        )

    try:
        result = await asyncio.wait_for(
            generate_analysis(request, model=model),
            timeout=ANALYSIS_TIMEOUT,
        )
        result.current_price_at_analysis = request.price_data.current_price
        return result
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=504,
            detail=f"Analysis generation timed out after {ANALYSIS_TIMEOUT}s",
        )
    except RuntimeError as e:
        logger.error(f"[Analysis] Generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/articles/{ticker}")
async def analysis_get_available_articles(
    ticker: str,
    days_back: int = Query(3, ge=1, le=14, description="Only consider articles from the last N days"),
    session: AsyncSession = Depends(get_async_session),
):
    """
    Return available news articles for a ticker within the last N days.
    
    Used by the frontend article picker so the user can manually select
    which articles to include in an analysis.
    """
    from datetime import timedelta
    from backend.models.news_schemas import NewsArticleOut

    from sqlalchemy import select, case
    cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)
    # Use CASE to fall back to imported_at when pub_date is NULL
    effective_date = case(
        (NewsArticle.pub_date.isnot(None), NewsArticle.pub_date),
        else_=NewsArticle.imported_at,
    )
    try:
        result = await session.execute(
            select(NewsArticle)
            .where(
                NewsArticle.ticker == ticker.upper(),
                effective_date >= cutoff,
            )
            .order_by(effective_date.desc())
            .limit(30)
        )
        articles = result.scalars().all()
    except Exception as e:
        logger.error(f"[Analysis] Failed to fetch available articles for {ticker}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch articles: {e}")

    return {
        "ticker": ticker.upper(),
        "days_back": days_back,
        "count": len(articles),
        "articles": [NewsArticleOut.model_validate(a).model_dump() for a in articles],
    }


@router.post("/analyze_ticker", response_model=FinancialAnalysisResponse)
async def analysis_analyze_ticker(
    ticker: str = Body(..., embed=True, description="Ticker symbol to analyze"),
    max_articles: int = Body(15, ge=1, le=30, description="Max news articles to include (default 15, max 30 for performance)"),
    days_back: int = Body(3, ge=1, le=14, description="Only consider articles from the last N days (default 3, max 14)"),
    model: Optional[str] = Body(None, embed=True, description="Override default Ollama model"),
    article_ids: Optional[List[int]] = Body(None, embed=True, description="Optional list of specific article IDs to analyze (max 20). If not provided, auto-selects most recent articles."),
    session: AsyncSession = Depends(get_async_session),
):
    """
    Convenience endpoint: Analyze a ticker by automatically fetching news and price data.

    This endpoint queries the database for recent news articles and fetches current
    market price data, then generates a full analysis report.

    If article_ids is provided, it will use only those specific articles (filtered by ticker for safety).
    Otherwise it auto-selects the most recent articles.
    """
    from sqlalchemy import select

    # 1. Fetch news articles for this ticker
    if article_ids is not None and len(article_ids) > 0:
        # Custom selection: fetch only the specified articles, but filter by ticker for safety
        capped_ids = article_ids[:20]  # Enforce max 20 articles
        try:
            result = await session.execute(
                select(NewsArticle)
                .where(
                    NewsArticle.id.in_(capped_ids),
                    NewsArticle.ticker == ticker.upper(),  # Safety: only include articles matching this ticker
                )
            )
            articles = result.scalars().all()
        except Exception as e:
            logger.error(f"[Analysis] Failed to fetch news for {ticker}: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to fetch news: {e}")

        if not articles:
            raise HTTPException(
                status_code=404,
                detail=f"No matching news articles found for {ticker} with the provided IDs",
            )
    else:
        # Auto-selection: most recent articles filtered by recency
        from datetime import timedelta
        from sqlalchemy import case
        cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)
        # Use CASE to fall back to imported_at when pub_date is NULL
        effective_date = case(
            (NewsArticle.pub_date.isnot(None), NewsArticle.pub_date),
            else_=NewsArticle.imported_at,
        )
        try:
            result = await session.execute(
                select(NewsArticle)
                .where(
                    NewsArticle.ticker == ticker.upper(),
                    effective_date >= cutoff,
                )
                .order_by(effective_date.desc())
                .limit(max_articles)
            )
            articles = result.scalars().all()
        except Exception as e:
            logger.error(f"[Analysis] Failed to fetch news for {ticker}: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to fetch news: {e}")

    if not articles:
        raise HTTPException(
            status_code=404,
            detail=f"No news articles found for {ticker}",
        )

    # 2. Fetch current price data
    try:
        price_info = await asyncio.wait_for(
            get_hybrid_stock_price(ticker.upper()),
            timeout=30,
        )
    except Exception as e:
        logger.warning(f"[Analysis] Price fetch failed for {ticker}, using fallback: {e}")
        price_info = None

    if not price_info:
        raise HTTPException(
            status_code=404,
            detail=f"Could not fetch market data for {ticker}",
        )

    # 3. Build the analysis request
    news_requests = [
        NewsArticleRequest(
            title=a.title or "Untitled",
            summary=a.summary,
            published_at=a.pub_date.isoformat() if a.pub_date else None,
            source=a.provider_name,
            url=a.article_url,
        )
        for a in articles
    ]

    current_price = price_info.get("current_price", 0)
    previous_close = price_info.get("previous_close", 0) or current_price
    daily_change_pct = (
        round(((current_price - previous_close) / previous_close) * 100, 2) if previous_close else 0
    )

    price_data = PriceDataRequest(
        current_price=current_price or 0,
        daily_change_percent=daily_change_pct,
        fifty_two_week_high=price_info.get("fifty_two_week_high", 0) or 0,
        fifty_two_week_low=price_info.get("fifty_two_week_low", 0) or 0,
        trading_volume=int(price_info.get("volume", 0) or 0),
        beta=price_info.get("beta"),
        support_level=price_info.get("support_level"),
        resistance_level=price_info.get("resistance_level"),
        market_cap=price_info.get("market_cap"),
    )

    analysis_request = FinancialAnalysisRequest(
        ticker=ticker.upper(),
        company_name=price_info.get("company_name"),
        news_articles=news_requests,
        price_data=price_data,
        analysis_date=datetime.now(timezone.utc).isoformat(),
    )

    # 4. Generate analysis
    connected = await check_ollama_connection()
    if not connected:
        raise HTTPException(
            status_code=503,
            detail="Ollama server is unreachable.",
        )

    try:
        # Use dynamic timeout based on model size (15 min small, 20 min large)
        model_name = model or os.getenv("OLLAMA_MODEL", "unknown")
        dyn_timeout = _get_timeout_for_model(model_name)
        result = await asyncio.wait_for(
            generate_analysis(analysis_request, model=model),
            timeout=dyn_timeout,
        )

        # Set price BEFORE saving so it's captured inside the JSON blob too
        result.current_price_at_analysis = current_price if current_price else None

        # 5. Save report to database
        model_name = model or os.getenv("OLLAMA_MODEL", "unknown")
        report_id = await create_report(
            session=session,
            ticker=ticker.upper(),
            report_data=result.model_dump(),
            articles_count=len(news_requests),
            model_used=model_name,
            prompt_version="1.0",
            current_price_at_analysis=current_price if current_price else None,
        )
        await session.commit()
        result.report_id = report_id
        logger.info(f"[Analysis] Report saved as id={report_id} for {ticker.upper()}")
        return result
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=504,
            detail=f"Analysis generation timed out after {dyn_timeout}s",
        )
    except RuntimeError as e:
        logger.error(f"[Analysis] Generation failed for {ticker}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
