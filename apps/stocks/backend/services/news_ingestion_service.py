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
_THUMB_RECOVERY_BATCH = 50


async def _recover_thumbnails(session: AsyncSession, batch_size: int = _THUMB_RECOVERY_BATCH) -> int:
	"""Attempt to recover thumbnails for articles that are missing them.
	
	Tries OG image extraction on the finnhub.io redirect URL (which follows through
	to the real article page via follow_redirects=True). Updates the database with
	recovered images. Returns the number of thumbnails recovered.
	"""
	from sqlalchemy import text
	
	# Find recent articles (last 30 days) missing thumbnails
	result = await session.execute(text(
		"SELECT id, article_url FROM news_articles "
		"WHERE thumbnail_url IS NULL "
		"AND imported_at >= NOW() - INTERVAL '30 days' "
		"ORDER BY imported_at DESC LIMIT :limit"
	), {"limit": batch_size})
	rows = result.fetchall()
	
	if not rows:
		return 0
	
	recovered = 0
	semaphore = asyncio.Semaphore(_OG_CONCURRENCY_LIMIT)
	
	async def _try_extract(url: str) -> Optional[str]:
		async with semaphore:
			return await _extract_og_image(url)
	
	tasks = [_try_extract(row[1]) for row in rows]  # row[0]=id, row[1]=article_url
	results = await asyncio.gather(*tasks, return_exceptions=True)
	
	for row, res in zip(rows, results):
		if isinstance(res, str):
			await session.execute(
				text("UPDATE news_articles SET thumbnail_url = :thumb WHERE id = :id"),
				{"thumb": res, "id": row[0]}
			)
			recovered += 1
		elif isinstance(res, Exception):
			logger.debug(f"[ThumbRecovery] Failed to extract: {res}")
	
	if recovered:
		await session.commit()
		logger.info(f"[ThumbRecovery] Recovered {recovered}/{len(rows)} thumbnails this cycle.")
	return recovered


async def _scheduled_ingest_loop(session_factory, tickers_fn, connection_manager) -> None:
	"""Periodically fetch news for all watchlist tickers every 15 minutes (runs all day).
	
	Each cycle also attempts to recover thumbnails for recently-ingested articles
	that are missing them.
	"""
	while True:
		try:
			tickers = await tickers_fn()
			async with session_factory() as session:
				if not tickers:
					logger.info("[NewsScheduler] No tickers in watchlist; skipping cycle.")
				else:
					results = await fetch_and_ingest_many(tickers, session, limit=25)
					total = sum(results.values())
					logger.info(
						f"[NewsScheduler] Cycle complete – ingested {total} articles "
						f"across {len(results)} tickers: {results}"
					)

				# Thumbnail recovery: fill in missing images for recent articles
				try:
					rec = await _recover_thumbnails(session)
					if rec > 0:
						logger.info(f"[NewsScheduler] Thumbnail recovery: +{rec} images recovered.")
				except Exception as e:
					logger.error(f"[NewsScheduler] Thumbnail recovery failed: {e}")

			# Broadcast news refresh notification to all connected WebSocket clients
			try:
				await connection_manager.broadcast({"type": "news_refresh"})
				logger.info("[NewsScheduler] Broadcast news_refresh to all clients.")
			except Exception as e:
				logger.error(f"[NewsScheduler] Failed to broadcast news_refresh: {e}")
		except Exception as e:
			logger.error(f"[NewsScheduler] Error during ingestion cycle: {e}")

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


async def _extract_og_image(url: str, timeout: float = 8.0) -> Optional[str]:
    """Scrape an article page for a thumbnail image using multiple strategies.

    Used as a fallback when Finnhub returns a placeholder or null image. Tries multiple
    extraction strategies in order of priority:
      1. OpenGraph <meta property='og:image'> tag
      2. Twitter Card <meta name='twitter:image'> tag
      3. First meaningful <img> tag (article hero images, not favicons/tracking pixels)

    Finnhub redirect URLs (finnhub.io/api/news?id=...) follow a 302 to the real article.
    With follow_redirects=True, httpx will automatically resolve to the target page,
    so we scrape the actual article HTML for OG/Twitter images.
    """
    last_error = None
    for attempt in range(2):
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                resp = await client.get(url, headers={
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                })
                if resp.status_code not in (200, 301, 302):
                    logger.debug(f"[OGExtract] HTTP {resp.status_code} for {url} (attempt {attempt+1})")
                    continue

                html = resp.text

                # Strategy 1: OpenGraph og:image tag
                img_url = None
                match = re.search(r'<meta\s+(?:property|name)="og:image"\s+content="(.*?)"', html, re.IGNORECASE)
                if not match:
                    match = re.search(r'<meta\s+content="(.*?)"\s+(?:property|name)="og:image"', html, re.IGNORECASE)
                if match:
                    img_url = match.group(1).strip()

                # Strategy 2: Twitter Card twitter:image tag
                if not img_url:
                    match = re.search(r'<meta\s+(?:property|name)="twitter:image"\s+content="(.*?)"', html, re.IGNORECASE)
                    if not match:
                        match = re.search(r'<meta\s+content="(.*?)"\s+(?:property|name)="twitter:image"', html, re.IGNORECASE)
                    if match:
                        img_url = match.group(1).strip()

                # Strategy 3: First <img src="..."> tag with meaningful content (not tracking/favicons)
                if not img_url:
                    for m in re.finditer(r'<img[^>]+src="(.*?)"', html, re.IGNORECASE):
                        candidate = m.group(1).strip()
                        if (candidate.startswith("http")
                            and not candidate.startswith("data:")
                            and "favicon" not in candidate.lower()
                            and "tracking" not in candidate.lower()
                            and "pixel" not in candidate.lower()):
                            img_url = candidate
                            break

                if img_url and img_url.startswith("http") and len(img_url) > 10:
                    # Validate: reject junk OG images (logos, privacy icons, favicons)
                    if not _is_og_junk_image(img_url):
                        return img_url

        except httpx.TimeoutException:
            last_error = "timeout"
            logger.debug(f"[OGExtract] Timeout for {url} (attempt {attempt+1}/2)")
        except Exception as e:
            last_error = str(e)
            logger.debug(f"[OGExtract] Error for {url} (attempt {attempt+1}/2): {e}")

    if last_error:
        logger.debug(f"[OGExtract] Exhausted retries for {url} (last error: {last_error})")
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


async def fetch_and_ingest_news(ticker: str, session: AsyncSession, limit: int = 30) -> int:
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

        async def _extract_with_limit(url: str) -> Optional[str]:
            async with semaphore:
                return await _extract_og_image(url)

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
        for asset_id in affected_asset_ids:
            await enqueue_job(
                session=session,
                job_type="company_report",
                target_type="asset",
                target_id=asset_id,
                payload={"ticker": ticker.upper()},
                priority=10,
            )

        if affected_asset_ids:
            logger.info(
                f"[NewsIngestion] Queued company reports for {len(affected_asset_ids)} assets from {ingested} articles ({ticker})"
            )
    except Exception as e:
        # Non-fatal: article ingestion succeeded, only enrichment queue failed
        logger.warning(f"[NewsIngestion] Failed to queue AI jobs for {ticker}: {e}")

    logger.info(f"[NewsIngestion] Ingested {ingested}/{min(len(raw_news), limit)} articles for {ticker}")
    return ingested


async def fetch_and_ingest_many(tickers: list[str], session: AsyncSession, limit: int = 25) -> dict[str, int]:
    """Fetch and ingest news for multiple tickers. Returns {ticker: count}.

    Adds delays between ticker requests to stay within Finnhub rate limits
    (60 calls/min on free tier).
    """
    results = {}
    for i, ticker in enumerate(tickers):
        count = await fetch_and_ingest_news(ticker.upper(), session, limit=limit)
        results[ticker.upper()] = count
        # Delay between tickers to avoid rate-limit bursts (skip delay after last ticker)
        if i < len(tickers) - 1:
            await asyncio.sleep(_TICKER_DELAY)
    return results
