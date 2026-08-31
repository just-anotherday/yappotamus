"""
Financial Analysis Router

Exposes REST endpoints for generating AI-powered financial analysis reports
using news articles and market price data via Ollama.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Annotated, List, Literal, Optional

from fastapi import APIRouter, HTTPException, Query, Body, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.analysis import (
    FinancialAnalysisRequest,
    FinancialAnalysisResponse,
    NewsArticleRequest,
    OllamaConfigResponse,
    PriceDataRequest,
    ProviderConfigResponse,
)
from backend.models.news import NewsArticle
from backend.config.database import get_async_session
from backend.lib.timestamps import utc_isoformat
from backend.services.report_service import create_report
from backend.services.ollama_service import (
    get_analysis_prompt_pipeline,
    get_current_analysis_prompt_pipeline,
    get_ollama_config,
    check_ollama_connection,
    _get_timeout_for_model,
)
from backend.services.hybrid_data_service import get_hybrid_stock_price
from backend.services.market_data_observability import current_correlation_id
from backend.services.market_data_errors import (
    MarketDataUnavailableError,
    require_usable_analysis_snapshot,
)

from backend.config.settings import settings
from backend.services.ai.ai_service import resolve_provider_model

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/analysis", tags=["analysis"])

# Default fallback timeout (configurable via ANALYSIS_TIMEOUT_S env var)
ANALYSIS_TIMEOUT = settings.ANALYSIS_TIMEOUT_S

# Upper bound on how many articles can be sent to the LLM in one analysis.
# Keeps prompt size (and cost) bounded regardless of how many articles the
# picker surfaces for browsing.
MAX_ARTICLES_PER_ANALYSIS = 50


def _resolve_analysis_prompt_pipeline(
    requested_version: Optional[Literal["2.0", "3.0"]],
):
    """Resolve one request to an immutable execution/provenance descriptor."""
    default_pipeline = get_current_analysis_prompt_pipeline()
    if requested_version is None or requested_version == default_pipeline.version:
        return default_pipeline
    if not settings.ALLOW_PROMPT_VERSION_OVERRIDE:
        raise HTTPException(
            status_code=403,
            detail=(
                f"Prompt version {requested_version} is not available; "
                f"the server default is {default_pipeline.version}"
            ),
        )
    return get_analysis_prompt_pipeline(requested_version)


def _order_articles_by_requested_ids(articles, requested_ids: List[int]):
    """Restore deterministic caller order after an unordered SQL IN query."""
    by_id = {article.id: article for article in articles}
    seen = set()
    ordered = []
    for article_id in requested_ids:
        if article_id in by_id and article_id not in seen:
            ordered.append(by_id[article_id])
            seen.add(article_id)
    return ordered


@router.get("/config", response_model=OllamaConfigResponse)
async def analysis_get_config():
    """Get current Ollama/AI provider configuration and connection status."""
    return await get_ollama_config()


@router.get("/providers", response_model=ProviderConfigResponse)
async def analysis_get_providers():
    """
    Get all available AI providers and their models.

    Returns a list of providers (ollama, openai) with their availability status
    and available models for each provider.
    """
    from backend.services.ollama_service import get_provider_config
    return await get_provider_config()


@router.post("/generate", response_model=FinancialAnalysisResponse)
async def analysis_generate(
    request: FinancialAnalysisRequest,
    model: Optional[str] = Query(None, description="Override default model"),
    provider: Optional[str] = Query(None, description="AI provider to use (ollama, openai)"),
    session: AsyncSession = Depends(get_async_session),
):
    """
    Generate a comprehensive financial analysis report.

    Accepts news articles and price data, feeds them to the LLM,
    and returns a structured analysis report.

    If provider is specified, uses that provider for generation.
    Otherwise falls back to the globally configured AI_PROVIDER setting.
    """
    pipeline = get_current_analysis_prompt_pipeline()
    try:
        result = await asyncio.wait_for(
            pipeline.generate(request, model=model, provider=provider),
            timeout=ANALYSIS_TIMEOUT,
        )
        result.current_price_at_analysis = request.price_data.current_price
        return result
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=504,
            detail=f"Analysis generation timed out after {ANALYSIS_TIMEOUT}s",
        )


@router.get("/articles/{ticker}")
async def analysis_get_available_articles(
    ticker: str,
    days_back: int = Query(3, ge=1, le=14, description="Only consider articles from the last N days"),
    limit: int = Query(100, ge=1, le=200, description="Max articles to return for browsing/selection"),
    session: AsyncSession = Depends(get_async_session),
):
    """
    Return available news articles for a ticker within the last N days.

    Used by the frontend article picker so the user can manually select
    which articles to include in an analysis. `limit` bounds how many
    candidates are returned for browsing - raising `days_back` only surfaces
    older articles if the window hasn't already been truncated by `limit`.
    """
    from datetime import timedelta
    from backend.models.news_schemas import NewsArticleOut

    from sqlalchemy import select, case
    cutoff = datetime.now() - timedelta(days=days_back)
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
            .limit(limit)
        )
        articles = result.scalars().all()
    except Exception as e:
        logger.error(f"[Analysis] Failed to fetch available articles for {ticker}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch articles: {e}")

    import traceback
    serialized = []
    for a in articles:
        try:
            serialized.append(NewsArticleOut.model_validate(a).model_dump(mode='json'))
        except Exception as se:
            logger.warning(f"[Analysis] Failed to serialize article id={getattr(a, 'id', '?')}: {se}\n{traceback.format_exc()}")
            # Fallback: manual dict construction for problematic rows
            serialized.append({
                "id": getattr(a, 'id', None),
                "finnhub_id": getattr(a, 'finnhub_id', None),
                "ticker": getattr(a, 'ticker', None),
                "title": getattr(a, 'title', None),
                "summary": getattr(a, 'summary', None),
                "provider_name": getattr(a, 'provider_name', None),
                "article_url": getattr(a, 'article_url', None),
                "thumbnail_url": getattr(a, 'thumbnail_url', None),
                "pub_date": utc_isoformat(getattr(a, 'pub_date', None)),
                "imported_at": utc_isoformat(getattr(a, 'imported_at', None)),
            })
    return {
        "ticker": ticker.upper(),
        "days_back": days_back,
        "count": len(articles),
        "articles": serialized,
    }


@router.post("/analyze_ticker", response_model=FinancialAnalysisResponse)
async def analysis_analyze_ticker(
    ticker: str = Body(..., embed=True, description="Ticker symbol to analyze"),
    max_articles: int = Body(50, ge=1, le=MAX_ARTICLES_PER_ANALYSIS, description=f"Max news articles to include (default 50, max {MAX_ARTICLES_PER_ANALYSIS} for cost/performance)"),
    days_back: int = Body(3, ge=1, le=14, description="Only consider articles from the last N days (default 3, max 14)"),
    model: Optional[str] = Body(None, embed=True, description="Override default model"),
    provider: Optional[str] = Body(None, embed=True, description="AI provider to use (ollama, openai)"),
    prompt_version: Annotated[
        Optional[Literal["2.0", "3.0"]],
        Body(embed=True, description="Development-only prompt pipeline override"),
    ] = None,
    article_ids: Optional[List[int]] = Body(None, embed=True, description=f"Optional list of specific article IDs to analyze (max {MAX_ARTICLES_PER_ANALYSIS}). If not provided, auto-selects most recent articles."),
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

    # Resolve and authorize the pipeline before any database, provider, or
    # persistence work. The frontend visibility flag is never trusted here.
    pipeline = _resolve_analysis_prompt_pipeline(prompt_version)

    # 1. Fetch news articles for this ticker
    if article_ids is not None and len(article_ids) > 0:
        # Custom selection: fetch only the specified articles, but filter by ticker for safety
        capped_ids = list(dict.fromkeys(article_ids))
        if len(capped_ids) > MAX_ARTICLES_PER_ANALYSIS:
            raise HTTPException(
                status_code=422,
                detail=f"A maximum of {MAX_ARTICLES_PER_ANALYSIS} distinct article IDs may be analyzed",
            )
        try:
            result = await session.execute(
                select(NewsArticle)
                .where(
                    NewsArticle.id.in_(capped_ids),
                    NewsArticle.ticker == ticker.upper(),  # Safety: only include articles matching this ticker
                )
            )
            articles = _order_articles_by_requested_ids(
                result.scalars().all(),
                capped_ids,
            )
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
        cutoff = datetime.now() - timedelta(days=days_back)
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
        logger.info(
            "[Analysis] event=analysis_input_rejected correlation_id=%s ticker=%s "
            "failure_kind=no_news_articles failure_reason=no_matching_articles",
            current_correlation_id(),
            ticker.upper(),
        )
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

    try:
        price_info = require_usable_analysis_snapshot(ticker, price_info)
    except MarketDataUnavailableError as unavailable:
        logger.warning(
            "[Analysis] event=market_data_rejected correlation_id=%s ticker=%s "
            "failure_kind=%s failure_reason=providers_exhausted",
            current_correlation_id(),
            ticker.upper(),
            unavailable.failure_kind,
        )
        raise HTTPException(
            status_code=503,
            detail=str(unavailable),
        ) from unavailable

    # 3. Build the analysis request
    news_requests = [
        NewsArticleRequest(
            title=a.title or "Untitled",
            summary=a.summary,
            published_at=utc_isoformat(a.pub_date),
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
        fifty_two_week_high=price_info.get("fifty_two_week_high") or None,
        fifty_two_week_low=price_info.get("fifty_two_week_low") or None,
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
    logger.info(
        "[Analysis] event=analysis_request_built correlation_id=%s ticker=%s "
        "requested_max_articles=%d supplied_count=%d",
        current_correlation_id(),
        ticker.upper(),
        max_articles,
        len(analysis_request.news_articles),
    )

    # 4. Generate analysis
    provider_name, model_name = resolve_provider_model(provider, model)
    try:
        # Use dynamic timeout based on model size (15 min small, 20 min large)
        dyn_timeout = _get_timeout_for_model(model_name, provider_name)
        result = await asyncio.wait_for(
            pipeline.generate(analysis_request, model=model, provider=provider),
            timeout=dyn_timeout,
        )

        # Set price BEFORE saving so it's captured inside the JSON blob too
        result.current_price_at_analysis = current_price if current_price else None

        # 5. Save report to database
        report_id = await create_report(
            session=session,
            ticker=ticker.upper(),
            report_data=result.model_dump(),
            articles_count=len(news_requests),
            model_used=model_name,
            prompt_version=pipeline.version,
            prompt_hash=pipeline.prompt_hash(analysis_request),
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
