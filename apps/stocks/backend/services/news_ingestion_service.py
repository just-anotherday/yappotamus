"""
News Ingestion Service

Fetches articles from Finnhub API, normalizes them to the news_articles schema,
and persists them to PostgreSQL using UPSERT logic (no duplicates).
Includes a background scheduler for periodic auto-ingestion.

Finnhub endpoints:
 - /company-news2  → market news for a specific ticker (free tier)

Free tier limits:
 - 60 REST API calls/min
 - ~1 call/sec safe average with rate limiter
"""

import asyncio
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert

from backend.models.news import NewsArticle
from backend.models.news_schemas import NewsArticleIngest
from backend.services.finnhub_service import get_finnhub_client, _rate_limiter
from backend.services.ticker_extractor import ticker_extractor
from backend.services.asset_sync import get_asset_id_by_ticker
from backend.services.ai_worker import enqueue_job
from backend.services.memory_diagnostics import log_memory
from backend.config.settings import settings

logger = logging.getLogger(__name__)

# Concurrency control: limit parallel OG scrapes to avoid hammering sites
_OG_CONCURRENCY_LIMIT = 4
# Minimum delay (seconds) between per-ticker news fetches to stay under Finnhub limits
_TICKER_DELAY = 2.0

# ---------- Background Scheduler ----------

_scheduler_task: Optional[asyncio.Task] = None
_scheduler_interval_seconds = 900  # 15 minutes


# Max thumbnail recovery attempts per scheduler cycle (keep it light)
_THUMBNAIL_RECOVERY_BATCH_SIZE = 20
_MAX_OG_HTML_BYTES = 1_048_576
_OG_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


async def _recover_thumbnails(
    session: AsyncSession,
    batch_size: int = _THUMBNAIL_RECOVERY_BATCH_SIZE,
    *,
    counters: Optional[dict[str, int]] = None,
) -> int:
    """Recover recent missing thumbnails with one bounded shared HTTP client."""
    from sqlalchemy import text
    result = await session.execute(text(
        "SELECT id, article_url FROM news_articles "
        "WHERE thumbnail_url IS NULL "
        "AND imported_at >= NOW() - INTERVAL '30 days' "
        "ORDER BY imported_at DESC LIMIT :limit"
    ), {"limit": batch_size})
    rows = result.fetchall()
    if counters is not None:
        counters["thumbnail_candidates"] += len(rows)
    if not rows:
        return 0
    recovered = 0
    semaphore = asyncio.Semaphore(_OG_CONCURRENCY_LIMIT)
    async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
        async def _try_extract(url: str) -> Optional[str]:
            async with semaphore:
                return await _extract_og_image(url, client=client)
        tasks = [_try_extract(row[1]) for row in rows]
        if counters is not None:
            counters["thumbnail_attempted"] += len(tasks)
        results = await asyncio.gather(*tasks, return_exceptions=True)
    for row, res in zip(rows, results):
        if isinstance(res, str):
            await session.execute(
                text("UPDATE news_articles SET thumbnail_url = :thumb WHERE id = :id"),
                {"thumb": res, "id": row[0]},
            )
            recovered += 1
        elif isinstance(res, Exception):
            logger.debug("[ThumbRecovery] OG extraction failed exception_type=%s", type(res).__name__)
    if counters is not None:
        counters["thumbnail_recovered"] += recovered
    if recovered:
        await session.commit()
        logger.info("[ThumbRecovery] Recovered %d/%d thumbnails this cycle.", recovered, len(rows))
    return recovered

async def _scheduled_ingest_loop(session_factory, tickers_fn, connection_manager) -> None:
    """Run sequential ticker ingestion and bounded thumbnail recovery every 15 minutes."""
    def memory_context(*, ticker_count: int, tickers_processed: int, articles_ingested: int,
                       cycle_counters: dict[str, int], thumbnail_counters: dict[str, int],
                       duration_seconds: float | None = None, outcome: str | None = None) -> dict[str, int | float | str]:
        context: dict[str, int | float | str] = {
            "ticker_count": ticker_count,
            "tickers_processed": tickers_processed,
            "articles_fetched": cycle_counters["articles_fetched"],
            "articles_changed": cycle_counters["articles_changed"],
            "articles_ingested": articles_ingested,
            "report_candidates": cycle_counters["report_candidates"],
            "report_candidates_discovered": cycle_counters["report_candidates_discovered"],
            "report_candidates_unique": cycle_counters["report_candidates_unique"],
            "scheduler_duplicates_skipped": cycle_counters["scheduler_duplicates_skipped"],
            "enqueue_attempts": cycle_counters["enqueue_attempts"],
            "jobs_created": cycle_counters["jobs_created"],
            "jobs_deduplicated": cycle_counters["jobs_deduplicated"],
            "thumbnail_candidates": thumbnail_counters["thumbnail_candidates"],
            "thumbnail_attempted": thumbnail_counters["thumbnail_attempted"],
            "thumbnail_recovered": thumbnail_counters["thumbnail_recovered"],
        }
        if duration_seconds is not None:
            context["duration_seconds"] = duration_seconds
        if outcome is not None:
            context["outcome"] = outcome
        return context
    while True:
        cycle_started_at = time.monotonic()
        ticker_count = tickers_processed = articles_ingested = recovered_thumbnail_count = 0
        cycle_counters = {
            "articles_fetched": 0, "articles_changed": 0, "report_candidates": 0,
            "report_candidates_discovered": 0, "report_candidates_unique": 0,
            "scheduler_duplicates_skipped": 0, "enqueue_attempts": 0,
            "jobs_created": 0, "jobs_deduplicated": 0,
        }
        thumbnail_counters = {"thumbnail_candidates": 0, "thumbnail_attempted": 0, "thumbnail_recovered": 0}
        scheduler_attempted_asset_ids: set[int] = set()
        outcome = "cancelled"
        try:
            tickers = await tickers_fn()
            ticker_count = len(tickers)
            if settings.MEMORY_DIAGNOSTICS_ENABLED:
                log_memory("news_cycle_start", logger_to_use=logger, enabled=True, extra=memory_context(
                    ticker_count=ticker_count, tickers_processed=tickers_processed, articles_ingested=articles_ingested,
                    cycle_counters=cycle_counters, thumbnail_counters=thumbnail_counters,
                ))
            async with session_factory() as session:
                if not tickers:
                    logger.info("[NewsScheduler] No tickers in watchlist; skipping cycle.")
                else:
                    results = await fetch_and_ingest_many(
                        tickers, session, limit=25, _cycle_counters=cycle_counters,
                        _scheduler_attempted_asset_ids=scheduler_attempted_asset_ids,
                    )
                    articles_ingested = sum(results.values())
                    tickers_processed = len(results)
                    logger.info("[NewsScheduler] Cycle complete - ingested %d articles across %d tickers: %s", articles_ingested, tickers_processed, results)
                if settings.MEMORY_DIAGNOSTICS_ENABLED:
                    log_memory("after_ticker_ingestion", logger_to_use=logger, enabled=True, extra=memory_context(
                        ticker_count=ticker_count, tickers_processed=tickers_processed, articles_ingested=articles_ingested,
                        cycle_counters=cycle_counters, thumbnail_counters=thumbnail_counters,
                    ))
                    log_memory("before_thumbnail_recovery", logger_to_use=logger, enabled=True, extra=memory_context(
                        ticker_count=ticker_count, tickers_processed=tickers_processed, articles_ingested=articles_ingested,
                        cycle_counters=cycle_counters, thumbnail_counters=thumbnail_counters,
                    ))
                try:
                    recovered_thumbnail_count = await _recover_thumbnails(session, counters=thumbnail_counters)
                    if recovered_thumbnail_count:
                        logger.info("[NewsScheduler] Thumbnail recovery: +%d images recovered.", recovered_thumbnail_count)
                except Exception as exc:
                    logger.error("[NewsScheduler] Thumbnail recovery failed: %s", exc)
                if settings.MEMORY_DIAGNOSTICS_ENABLED:
                    log_memory("after_thumbnail_recovery", logger_to_use=logger, enabled=True, extra=memory_context(
                        ticker_count=ticker_count, tickers_processed=tickers_processed, articles_ingested=articles_ingested,
                        cycle_counters=cycle_counters, thumbnail_counters=thumbnail_counters,
                    ))
            try:
                await connection_manager.broadcast({"type": "news_refresh"})
                logger.info("[NewsScheduler] Broadcast news_refresh to all clients.")
            except Exception as exc:
                logger.error("[NewsScheduler] Failed to broadcast news_refresh: %s", exc)
            if settings.MEMORY_DIAGNOSTICS_ENABLED:
                log_memory("after_broadcast", logger_to_use=logger, enabled=True, extra=memory_context(
                    ticker_count=ticker_count, tickers_processed=tickers_processed, articles_ingested=articles_ingested,
                    cycle_counters=cycle_counters, thumbnail_counters=thumbnail_counters,
                ))
            outcome = "completed"
        except Exception as exc:
            outcome = "failed"
            logger.error("[NewsScheduler] Error during ingestion cycle: %s", exc)
        finally:
            if settings.MEMORY_DIAGNOSTICS_ENABLED:
                log_memory("news_ingestion_cycle_end", logger_to_use=logger, enabled=True, extra=memory_context(
                    ticker_count=ticker_count, tickers_processed=tickers_processed, articles_ingested=articles_ingested,
                    cycle_counters=cycle_counters, thumbnail_counters=thumbnail_counters,
                    duration_seconds=round(time.monotonic() - cycle_started_at, 3), outcome=outcome,
                ))
        await asyncio.sleep(_scheduler_interval_seconds)

def start_scheduler(session_factory, tickers_fn, connection_manager) -> None:
	"""Start the background news ingestion scheduler."""
	global _scheduler_task
	if _scheduler_task is not None and not _scheduler_task.done():
		logger.info("[NewsScheduler] Scheduler already running; skipping start.")
		return
	_scheduler_task = asyncio.create_task(_scheduled_ingest_loop(session_factory, tickers_fn, connection_manager))
	logger.info(f"[NewsScheduler] Started – will run every {_scheduler_interval_seconds}s (15 min).")


def stop_scheduler() -> None:
    """Stop the background news ingestion scheduler."""
    global _scheduler_task
    if _scheduler_task is not None and not _scheduler_task.done():
        _scheduler_task.cancel()
        _scheduler_task = None
        logger.info("[NewsScheduler] Stopped.")


def _parse_finnhub_timestamp(ts: Any) -> Optional[datetime]:
    """Convert a Unix timestamp (int) or ISO string to a naive datetime."""
    if not ts:
        return None
    # Handle integer timestamps
    if isinstance(ts, (int, float)):
        try:
            return datetime.fromtimestamp(ts).replace(tzinfo=None)
        except (TypeError, ValueError, OSError):
            return None
    # Handle ISO format strings like "2025-08-13T09:30:43Z"
    if isinstance(ts, str):
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            return dt.replace(tzinfo=None)
        except (TypeError, ValueError):
            return None
    return None


# Known placeholder image URLs that Finnhub returns when the original source lacks a real image.
# These are generic fill-ins that should be treated as "no image" so the frontend uses our fallback.
_YAHOO_PLACEHOLDER_PATTERNS = [
    # s.yimg.com/uu and s.yimg.com/rz both serve real article images from Yahoo-sourced content — do NOT filter them.
    "yahoo_finance_en-US_h_p_finance_2.png",   # generic fallback placeholder (only match this specific filename)
]

# OG image quality filters: URLs that look like real images but are actually junk (logos, privacy icons, favicons).
# These appear when scraping og:image/twitter:image tags and must be rejected.
_OG_JUNK_PATTERNS = [
    "privacy-choice-control.png",       # Yahoo privacy icon (438 records in DB)
    "yahoo-finance-default-logo.png",   # Yahoo Finance logo (104 records in DB)
    "/logo/",                           # Generic site logos
    "/favicon",                         # Favicon references
    "siteApp/img/",                     # Yahoo site assets (not article images)
    "imagecache/bz2_opengraph_meta_image_400x300",  # Benzinga generic placeholder
]


def _is_yahoo_placeholder(image_url: Optional[str]) -> bool:
    """Check if a thumbnail URL is a known Yahoo/Finnhub generic placeholder.

    Only the explicit placeholder filename is filtered. Broad domain-level filters (e.g. s.yimg.com/rz/)
    were removed because they incorrectly stripped real article images that happen to route through
    Yahoo's image proxy infrastructure.
    """
    if not image_url:
        return True  # treat None/empty as placeholder
    for pattern in _YAHOO_PLACEHOLDER_PATTERNS:
        if pattern in image_url:
            return True
    return False


def _is_og_junk_image(image_url: Optional[str]) -> bool:
    """Check if an OG-extracted image URL is junk (logo, privacy icon, favicon, etc.).

    These URLs pass through normal og:image tags but are not article thumbnails.
    Returns True if the URL should be rejected.
    """
    if not image_url:
        return True
    lower = image_url.lower()
    for pattern in _OG_JUNK_PATTERNS:
        if pattern.lower() in lower:
            return True
    return False


async def _extract_og_image(
    url: str,
    timeout: float = 8.0,
    *,
    client: httpx.AsyncClient | None = None,
) -> Optional[str]:
    """Extract a usable OG image URL from bounded HTML using a supplied client.
    A caller that supplies ``client`` owns its lifetime.  The compatibility path
    creates one client for this call, while phase callers share one client.
    """
    if client is None:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as owned_client:
            return await _extract_og_image(url, timeout=timeout, client=owned_client)
    last_error: str | None = None
    for attempt in range(2):
        try:
            async with client.stream("GET", url, headers=_OG_HEADERS) as response:
                if response.status_code not in (200, 301, 302):
                    last_error = f"http_{response.status_code}"
                    continue
                content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                if content_type and content_type not in {"text/html", "application/xhtml+xml"}:
                    last_error = "non_html"
                    continue
                body = bytearray()
                oversized = False
                async for chunk in response.aiter_bytes():
                    if len(body) + len(chunk) > _MAX_OG_HTML_BYTES:
                        oversized = True
                        break
                    body.extend(chunk)
                if oversized:
                    last_error = "response_too_large"
                    continue
                html = bytes(body).decode(response.encoding or "utf-8", errors="replace")
            img_url = None
            match = re.search(r'<meta\s+(?:property|name)="og:image"\s+content="(.*?)"', html, re.IGNORECASE)
            if not match:
                match = re.search(r'<meta\s+content="(.*?)"\s+(?:property|name)="og:image"', html, re.IGNORECASE)
            if match:
                img_url = match.group(1).strip()
            if not img_url:
                match = re.search(r'<meta\s+(?:property|name)="twitter:image"\s+content="(.*?)"', html, re.IGNORECASE)
                if not match:
                    match = re.search(r'<meta\s+content="(.*?)"\s+(?:property|name)="twitter:image"', html, re.IGNORECASE)
                if match:
                    img_url = match.group(1).strip()
            if not img_url:
                for match in re.finditer(r'<img[^>]+src="(.*?)"', html, re.IGNORECASE):
                    candidate = match.group(1).strip()
                    if (candidate.startswith("http") and not candidate.startswith("data:")
                            and "favicon" not in candidate.lower() and "tracking" not in candidate.lower()
                            and "pixel" not in candidate.lower()):
                        img_url = candidate
                        break
            if img_url and img_url.startswith("http") and len(img_url) > 10 and not _is_og_junk_image(img_url):
                return img_url
            last_error = "image_not_found"
        except httpx.TimeoutException:
            last_error = "timeout"
        except Exception as exc:
            last_error = type(exc).__name__
    if last_error:
        logger.debug("[OGExtract] exhausted outcome=%s attempt_count=2", last_error)
    return None

def _extract_ticker_from_related(article: Dict[str, Any], query_ticker: str) -> Optional[str]:
    """Extract the best ticker from Finnhub's 'related' field.

    Finnhub returns related symbols like "AAPL,MSFT" as a comma-separated string.
    We prefer symbols that match the query ticker (meaning the article is directly about it).
    If no match, use the first symbol from related as the primary ticker.
    If 'related' is empty or missing, fall back to the query ticker.
    """
    related = article.get("related", "")
    if not related:
        return query_ticker

    # Parse comma-separated symbols, strip whitespace
    symbols = [s.strip().upper() for s in related.split(",") if s.strip()]
    if not symbols:
        return query_ticker

    # Prefer the query ticker if it appears in the related list
    if query_ticker.upper() in symbols:
        return query_ticker.upper()

    # Use the first related symbol as the primary ticker
    return symbols[0]


def normalize_finnhub_article(article: Dict[str, Any], ticker: str) -> Optional[NewsArticleIngest]:
    """Normalize a raw Finnhub company-news article into our schema.

    Finnhub article format:
      {
        "category": "company-news",
        "datetime": "2025-08-13T09:30:43Z",
        "headline": "Some headline...",
        "image": "https://...",
        "related": "AAPL,MSFT",
        "source": "Yahoo Finance",
        "summary": "Article summary text...",
        "url": "https://...",
      }

    Ticker mapping: Use Finnhub's 'related' field (actual article tags) instead of
    the query ticker. This prevents articles about NVDA from being tagged as GOOGL
    simply because they appeared in a GOOGL news feed.

    Note: The `author` column was removed from the database schema as Finnhub does not
    provide author data (<1% of records had values). All articles now originate from
    Finnhub exclusively (yfinance pipeline was removed in Phase 1).
    """
    url = article.get("url")
    if not url:
        return None

    # Generate a stable Finnhub ID from the URL for deduplication
    import hashlib
    finnhub_id = hashlib.md5(url.encode()).hexdigest()[:32]

    pub_date = _parse_finnhub_timestamp(article.get("datetime"))

    # Strip known Yahoo placeholder images; let frontend use fallback
    raw_image = article.get("image")
    thumbnail_url = None if _is_yahoo_placeholder(raw_image) else raw_image

    # Extract the correct ticker from Finnhub's 'related' field
    article_ticker = _extract_ticker_from_related(article, ticker)

    return NewsArticleIngest(
        finnhub_id=finnhub_id,
        ticker=article_ticker,
        title=article.get("headline"),
        summary=article.get("summary"),
        provider_name=article.get("source"),
        article_url=url,
        thumbnail_url=thumbnail_url,
        pub_date=pub_date,
        raw_json=article,
    )


async def ingest_article(session: AsyncSession, article_in: NewsArticleIngest) -> Optional[NewsArticle]:
    """Insert or skip a single article (UPSERT on article_url)."""
    values = article_in.model_dump(exclude_unset=True)

    stmt = pg_insert(NewsArticle).values(**values)

    if article_in.article_url:
        stmt = stmt.on_conflict_do_update(
            constraint="news_articles_article_url_key",
            set_={
                "title": values.get("title"),
                "summary": values.get("summary"),
                "provider_name": values.get("provider_name"),
                "thumbnail_url": values.get("thumbnail_url"),
                "pub_date": values.get("pub_date"),
                "raw_json": values.get("raw_json"),
            },
        )

    await session.execute(stmt)
    await session.commit()

    if article_in.article_url:
        result = await session.execute(
            select(NewsArticle).where(NewsArticle.article_url == article_in.article_url)
        )
        return result.scalar_one_or_none()

    return None


async def batch_ingest_articles(
    session: AsyncSession, articles_in: list[NewsArticleIngest]
) -> list[int]:
    """Batch upsert multiple articles in a single transaction.

    Uses PostgreSQL ON CONFLICT with RETURNING to avoid N+1 round-trips.
    Returns IDs for articles that were inserted or materially updated.
    """
    if not articles_in:
        return []

    values = [article.model_dump(exclude_unset=True) for article in articles_in]

    stmt = pg_insert(NewsArticle).values(values)

    stmt = stmt.on_conflict_do_update(
        constraint="news_articles_article_url_key",
        set_={
            "ticker": stmt.excluded.ticker,
            "title": stmt.excluded.title,
            "summary": stmt.excluded.summary,
            "provider_name": stmt.excluded.provider_name,
            "thumbnail_url": stmt.excluded.thumbnail_url,
            "pub_date": stmt.excluded.pub_date,
            "raw_json": stmt.excluded.raw_json,
        },
        where=(NewsArticle.title.is_distinct_from(stmt.excluded.title)
               | NewsArticle.summary.is_distinct_from(stmt.excluded.summary)
               | NewsArticle.ticker.is_distinct_from(stmt.excluded.ticker)
               | NewsArticle.pub_date.is_distinct_from(stmt.excluded.pub_date)),
    ).returning(NewsArticle.id)

    result = await session.execute(stmt)
    await session.commit()
    return list(result.scalars().all())


async def _enqueue_company_report_jobs(
    session: AsyncSession,
    ticker: str,
    affected_asset_ids: set[int],
    *,
    scheduler_attempted_asset_ids: Optional[set[int]] = None,
) -> dict[str, int]:
    """Enqueue unique cycle targets; ``report_candidates`` means discovered."""
    discovered = len(affected_asset_ids)
    prior_attempts = scheduler_attempted_asset_ids if scheduler_attempted_asset_ids is not None else set()
    enqueue_asset_ids = affected_asset_ids - prior_attempts
    scheduler_duplicates_skipped = discovered - len(enqueue_asset_ids)
    jobs_created = jobs_deduplicated = 0
    for asset_id in enqueue_asset_ids:
        # Mark only when this target is about to make an actual enqueue attempt.
        prior_attempts.add(asset_id)
        job_ok = await enqueue_job(
            session=session, job_type="company_report", target_type="asset", target_id=asset_id,
            payload={"ticker": ticker.upper()}, priority=10,
        )
        if job_ok:
            jobs_created += 1
        else:
            jobs_deduplicated += 1
    return {
        "report_candidates": discovered,
        "report_candidates_discovered": discovered,
        "report_candidates_unique": len(enqueue_asset_ids),
        "scheduler_duplicates_skipped": scheduler_duplicates_skipped,
        "enqueue_attempts": len(enqueue_asset_ids),
        "jobs_created": jobs_created,
        "jobs_deduplicated": jobs_deduplicated,
    }

async def fetch_and_ingest_news(
    ticker: str,
    session: AsyncSession,
    limit: int = 30,
    *,
    _cycle_counters: Optional[dict[str, int]] = None,
    _scheduler_attempted_asset_ids: Optional[set[int]] = None,
) -> int:
    """
    Fetch latest news for a ticker from Finnhub and persist to PostgreSQL.
    Returns the count of newly ingested articles.
    Uses batch upsert to minimize database round-trips.
    """
    try:
        await _rate_limiter()
        client = get_finnhub_client()

        # Finnhub /company-news expects YYYY-MM-DD format dates (not unix timestamps)
        now_utc = datetime.now(timezone.utc)
        to_date   = now_utc.strftime("%Y-%m-%d")
        from_date = (now_utc - timedelta(days=7)).strftime("%Y-%m-%d")

        raw_news = client.company_news(
            ticker.upper(),
            _from=from_date,
            to=to_date,
        )

    except Exception as e:
        logger.error(f"[NewsIngestion] Failed to fetch news for {ticker}: {e}")
        return 0

    if not raw_news:
        logger.info(f"[NewsIngestion] No news returned for {ticker}")
        return 0

    normalized_articles: list[NewsArticleIngest] = []
    articles_missing_images: list[tuple[NewsArticleIngest, str]] = []  # (article, url)
    for article in raw_news[:limit]:
        try:
            normalized = normalize_finnhub_article(article, ticker)
            if not normalized or not normalized.article_url:
                logger.warning(f"[NewsIngestion] Skipping article without URL for {ticker}")
                continue
            normalized_articles.append(normalized)
            # Track articles that lost their thumbnail so we can try OG extraction
            if not normalized.thumbnail_url and normalized.article_url:
                articles_missing_images.append((normalized, normalized.article_url))
        except Exception as e:
            logger.error(f"[NewsIngestion] Failed to normalize Finnhub article for {ticker}: {e}")
            continue

    # Extract OG images in parallel (concurrency-limited) for articles missing thumbnails
    if articles_missing_images:
        semaphore = asyncio.Semaphore(_OG_CONCURRENCY_LIMIT)
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
            async def _extract_with_limit(url: str) -> Optional[str]:
                async with semaphore:
                    return await _extract_og_image(url, client=client)
            og_tasks = [_extract_with_limit(url) for _, url in articles_missing_images]
            og_results = await asyncio.gather(*og_tasks, return_exceptions=True)
        og_success = 0
        for (article, _), result in zip(articles_missing_images, og_results):
            if isinstance(result, str):
                article.thumbnail_url = result
                og_success += 1
        if og_success:
            logger.info(f"[NewsIngestion] Recovered {og_success} OG images via scraping for {ticker}")
    if not normalized_articles:
        logger.info(f"[NewsIngestion] No valid articles to ingest for {ticker}")
        return 0

    material_article_ids = await batch_ingest_articles(session, normalized_articles)
    ingested = len(material_article_ids)
    articles_fetched = len(normalized_articles)
    articles_changed = ingested

    if settings.INTELLIGENCE_ENABLED and material_article_ids:
        from backend.intelligence.article_service import ARTICLE_PROMPT_HASH, article_source_content_hash
        rows = (await session.execute(select(NewsArticle).where(NewsArticle.id.in_(material_article_ids)))).scalars().all()
        for row in rows:
            if not settings.is_intelligence_pilot_ticker(row.ticker):
                continue
            source_hash = article_source_content_hash(row)
            await enqueue_job(session, "article_intelligence", "article", row.id,
                              payload={"source_hash": source_hash, "prompt_hash": ARTICLE_PROMPT_HASH},
                              priority=8, dedupe_key=f"{row.id}:{source_hash}:{ARTICLE_PROMPT_HASH}")

    # --- Pipeline: Extract tickers from new articles → queue company report jobs ---
    report_candidates = report_candidates_discovered = report_candidates_unique = scheduler_duplicates_skipped = 0
    enqueue_attempts = 0
    jobs_created = 0
    jobs_deduplicated = 0
    try:
        affected_asset_ids = set()
        for article in normalized_articles:
            # Extract tickers from title + summary
            found_tickers = ticker_extractor.extract(
                text=article.summary or "",
                title=article.title or "",
            )
            for t in found_tickers:
                aid = await get_asset_id_by_ticker(session, t)
                if aid:
                    affected_asset_ids.add(aid)

        # Queue company report jobs only for affected assets (deduplicated by enqueue_job)
        enqueue_counts = await _enqueue_company_report_jobs(
            session,
            ticker,
            affected_asset_ids,
            scheduler_attempted_asset_ids=_scheduler_attempted_asset_ids,
        )
        report_candidates = enqueue_counts["report_candidates"]
        report_candidates_discovered = enqueue_counts["report_candidates_discovered"]
        report_candidates_unique = enqueue_counts["report_candidates_unique"]
        scheduler_duplicates_skipped = enqueue_counts["scheduler_duplicates_skipped"]
        enqueue_attempts = enqueue_counts["enqueue_attempts"]
        jobs_created = enqueue_counts["jobs_created"]
        jobs_deduplicated = enqueue_counts["jobs_deduplicated"]
    except Exception as e:
        # Non-fatal: article ingestion succeeded, only enrichment queue failed
        logger.warning(f"[NewsIngestion] Failed to queue AI jobs for {ticker}: {e}")

    logger.info(
        f"[NewsIngestion] Company report enqueue summary "
        f"ticker={ticker.upper()} articles_fetched={articles_fetched} "
        f"articles_changed={articles_changed} report_candidates={report_candidates} "
        f"report_candidates_discovered={report_candidates_discovered} "
        f"report_candidates_unique={report_candidates_unique} "
        f"scheduler_duplicates_skipped={scheduler_duplicates_skipped} "
        f"enqueue_attempts={enqueue_attempts} jobs_created={jobs_created} "
        f"jobs_deduplicated={jobs_deduplicated}"
    )

    if _cycle_counters is not None:
        _cycle_counters["articles_fetched"] += articles_fetched
        _cycle_counters["articles_changed"] += articles_changed
        _cycle_counters["report_candidates"] += report_candidates
        _cycle_counters["report_candidates_discovered"] += report_candidates_discovered
        _cycle_counters["report_candidates_unique"] += report_candidates_unique
        _cycle_counters["scheduler_duplicates_skipped"] += scheduler_duplicates_skipped
        _cycle_counters["enqueue_attempts"] += enqueue_attempts
        _cycle_counters["jobs_created"] += jobs_created
        _cycle_counters["jobs_deduplicated"] += jobs_deduplicated

    logger.info(f"[NewsIngestion] Ingested {ingested}/{min(len(raw_news), limit)} articles for {ticker}")
    return ingested


async def fetch_and_ingest_many(
    tickers: list[str],
    session: AsyncSession,
    limit: int = 25,
    *,
    _cycle_counters: Optional[dict[str, int]] = None,
    _scheduler_attempted_asset_ids: Optional[set[int]] = None,
) -> dict[str, int]:
    """Fetch and ingest news for multiple tickers. Returns {ticker: count}.

    Adds delays between ticker requests to stay within Finnhub rate limits
    (60 calls/min on free tier).
    """
    results = {}
    scheduler_attempted_asset_ids = _scheduler_attempted_asset_ids if _scheduler_attempted_asset_ids is not None else set()
    for i, ticker in enumerate(tickers):
        count = await fetch_and_ingest_news(
            ticker.upper(),
            session,
            limit=limit,
            _cycle_counters=_cycle_counters,
            _scheduler_attempted_asset_ids=scheduler_attempted_asset_ids,
        )
        results[ticker.upper()] = count
        # Delay between tickers to avoid rate-limit bursts (skip delay after last ticker)
        if i < len(tickers) - 1:
            await asyncio.sleep(_TICKER_DELAY)
    return results
