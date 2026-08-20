"""
News Ingestion Service

Fetches articles from Finnhub API, normalizes them to the news_articles schema,
and persists them to PostgreSQL using UPSERT logic (no duplicates).
Includes a background scheduler for periodic auto-ingestion.

Finnhub endpoints:
 - /company-news  → market news for a specific ticker (free tier)

Free tier limits:
 - 60 REST API calls/min
 - ~1 call/sec safe average with rate limiter
"""

import asyncio
from dataclasses import dataclass
import hashlib
import logging
import re
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import uuid4
from zoneinfo import ZoneInfo

import httpx
from requests.exceptions import Timeout as RequestsTimeout
from urllib3.exceptions import TimeoutError as Urllib3TimeoutError
from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert

from backend.models.news import NewsArticle
from backend.models.news_ingestion_state import NewsIngestionState
from backend.models.news_schemas import NewsArticleIngest
from backend.services.finnhub_service import (
    _exception_status_code,
    _is_rate_limit_error,
    _retry_api,
    get_finnhub_client,
)
from backend.services.ticker_extractor import ticker_extractor
from backend.services.asset_sync import get_asset_id_by_ticker
from backend.services.watchlist_service import get_all_tickers
from backend.services.ai_worker import enqueue_job
from backend.services.memory_diagnostics import log_memory
from backend.config.settings import settings
from backend.config.database import sanitize_database_error

logger = logging.getLogger(__name__)

# Concurrency control: limit parallel OG scrapes to avoid hammering sites
_OG_CONCURRENCY_LIMIT = 4
# Minimum delay (seconds) between per-ticker news fetches to stay under Finnhub limits
_TICKER_DELAY = 2.0
# Stop a cycle after a short run of provider-wide timeouts; a later cycle retries normally.
_MAX_CONSECUTIVE_NEWS_PROVIDER_TIMEOUTS = 3
_ARTICLE_DB_CHUNK_SIZE = 250
# The Finnhub SDK client is process-singleton; this also serializes an in-flight
# request whose async waiter was cancelled before its synchronous timeout expires.
_finnhub_company_news_lock = threading.Lock()
_NEWS_JOB_NAME = "production-watchlist-news"
_NEW_YORK = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class IngestionWindow:
    start: datetime
    end: datetime
    mode: str

    @property
    def lookback_minutes(self) -> int:
        return max(0, round((self.end - self.start).total_seconds() / 60))


@dataclass(frozen=True)
class ArticlePersistResult:
    inserted_ids: list[int]
    submitted: int
    unique_submitted: int

    @property
    def inserted(self) -> int:
        return len(self.inserted_ids)

    @property
    def duplicates_ignored(self) -> int:
        return self.submitted - self.inserted


def _as_utc(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def calculate_ingestion_window(
    now: datetime,
    last_successful_window_end: Optional[datetime],
) -> IngestionWindow:
    """Calculate an overlapping, outage-aware, bounded logical window."""
    end = _as_utc(now) or datetime.now(timezone.utc)
    checkpoint = _as_utc(last_successful_window_end)
    maximum_start = end - timedelta(hours=settings.NEWS_MAX_BACKFILL_HOURS)
    if checkpoint is None:
        start = max(maximum_start, end - timedelta(hours=settings.NEWS_INITIAL_BACKFILL_HOURS))
        return IngestionWindow(start=start, end=end, mode="initial_backfill")

    checkpoint = min(checkpoint, end)
    proposed = checkpoint - timedelta(minutes=settings.NEWS_OVERLAP_MINUTES)
    start = max(maximum_start, min(proposed, end))
    gap_minutes = max(0.0, (end - checkpoint).total_seconds() / 60)
    if proposed < maximum_start:
        mode = "bounded_backfill"
    elif gap_minutes > settings.NEWS_ACTIVE_INTERVAL_MINUTES * 1.5:
        mode = "recovery"
    else:
        mode = "normal"
    return IngestionWindow(start=start, end=end, mode=mode)


def _active_news_window(now: datetime) -> bool:
    local = (_as_utc(now) or now).astimezone(_NEW_YORK)
    return local.weekday() < 5 and 4 <= local.hour < 20


def should_run_ingestion(
    now: datetime,
    last_successful_window_end: Optional[datetime],
    *,
    trigger_kind: str = "auto",
) -> bool:
    """Apply the New York cadence guard to a classified external trigger."""
    previous = _as_utc(last_successful_window_end)
    if previous is not None:
        repeat_guard_minutes = max(1.0, settings.NEWS_ACTIVE_INTERVAL_MINUTES / 3)
        if (now - previous).total_seconds() / 60 < repeat_guard_minutes:
            # Suppress an immediate transport retry after the server completed
            # but its successful response did not reach the workflow runner.
            return False
    if trigger_kind == "hourly":
        return True
    if trigger_kind == "quarter_hour":
        return _active_news_window(now)
    if _active_news_window(now) or last_successful_window_end is None:
        return True
    if previous is None:
        return True
    elapsed_minutes = (now - previous).total_seconds() / 60
    # Allow normal scheduler jitter without accidentally turning hourly into 75m.
    return elapsed_minutes >= settings.NEWS_OFF_HOURS_INTERVAL_MINUTES - 5


async def _load_ingestion_state(session: AsyncSession) -> Optional[NewsIngestionState]:
    return await session.get(NewsIngestionState, _NEWS_JOB_NAME)


async def _acquire_ingestion_lease(
    session: AsyncSession,
    *,
    owner: str,
    now: datetime,
) -> Optional[NewsIngestionState]:
    expires_at = now + timedelta(minutes=settings.NEWS_INGESTION_LEASE_MINUTES)
    stmt = pg_insert(NewsIngestionState).values(
        job_name=_NEWS_JOB_NAME,
        last_attempted_at=now,
        last_status="running",
        consecutive_failures=0,
        last_metrics={},
        lease_owner=owner,
        lease_expires_at=expires_at,
        updated_at=now,
    ).on_conflict_do_update(
        index_elements=[NewsIngestionState.job_name],
        set_={
            "last_attempted_at": now,
            "last_status": "running",
            "last_error_code": None,
            "lease_owner": owner,
            "lease_expires_at": expires_at,
            "updated_at": now,
        },
        where=or_(
            NewsIngestionState.lease_expires_at.is_(None),
            NewsIngestionState.lease_expires_at <= now,
        ),
    ).returning(NewsIngestionState)
    state = (await session.execute(stmt)).scalar_one_or_none()
    await session.commit()
    return state


async def _finish_ingestion_run(
    session: AsyncSession,
    *,
    owner: str,
    now: datetime,
    status: str,
    metrics: dict[str, Any],
    successful_window_end: Optional[datetime] = None,
    error_code: Optional[str] = None,
) -> None:
    successful = status == "completed"
    values: dict[str, Any] = {
        "last_completed_at": now,
        "last_status": status,
        "last_error_code": error_code,
        "last_metrics": metrics,
        "lease_owner": None,
        "lease_expires_at": None,
        "updated_at": now,
        "consecutive_failures": 0 if successful else NewsIngestionState.consecutive_failures + 1,
    }
    if successful:
        values["last_successful_at"] = now
        values["last_successful_window_end"] = successful_window_end or now
    if int(metrics.get("articles_returned", 0)) > 0:
        values["last_article_retrieved_at"] = now
    if int(metrics.get("articles_inserted", 0)) > 0:
        values["last_article_inserted_at"] = now
    if metrics.get("newest_fetched_article_timestamp"):
        values["latest_retrieved_pub_date"] = datetime.fromisoformat(
            metrics["newest_fetched_article_timestamp"]
        )
    if metrics.get("newest_inserted_article_timestamp"):
        values["latest_inserted_pub_date"] = datetime.fromisoformat(
            metrics["newest_inserted_article_timestamp"]
        )

    result = await session.execute(
        update(NewsIngestionState)
        .where(
            NewsIngestionState.job_name == _NEWS_JOB_NAME,
            NewsIngestionState.lease_owner == owner,
        )
        .values(**values)
    )
    await session.commit()
    if result.rowcount != 1:
        logger.error("[NewsIngestion] event=lease_release_missed owner=%s", owner)
        raise RuntimeError("news_ingestion_lease_lost")


async def _renew_ingestion_lease(
    session: AsyncSession,
    *,
    owner: str,
    now: datetime,
) -> None:
    """Extend an owned lease or abort before another run can overlap it."""
    result = await session.execute(
        update(NewsIngestionState)
        .where(
            NewsIngestionState.job_name == _NEWS_JOB_NAME,
            NewsIngestionState.lease_owner == owner,
        )
        .values(
            lease_expires_at=now + timedelta(minutes=settings.NEWS_INGESTION_LEASE_MINUTES),
            updated_at=now,
        )
    )
    await session.commit()
    if result.rowcount != 1:
        raise RuntimeError("news_ingestion_lease_lost")


async def get_news_ingestion_health(
    session: AsyncSession,
    *,
    now: Optional[datetime] = None,
) -> dict[str, Any]:
    """Return a safe authenticated health snapshot for operations tooling."""
    checked_at = _as_utc(now) or datetime.now(timezone.utc)
    state = await _load_ingestion_state(session)
    if state is None:
        return {
            "status": "never_run", "stale": True, "running": False,
            "last_attempted_at": None, "last_successful_at": None,
            "consecutive_failures": 0, "metrics": {},
        }

    lease_expires = _as_utc(state.lease_expires_at)
    running = bool(state.lease_owner and lease_expires and lease_expires > checked_at)
    last_success = _as_utc(state.last_successful_at)
    stale = last_success is None or (
        checked_at - last_success > timedelta(minutes=settings.NEWS_STALE_AFTER_MINUTES)
    )
    if running:
        health_status = "running"
    elif stale:
        health_status = "stale"
    elif state.last_status != "completed":
        health_status = "degraded"
    else:
        health_status = "healthy"

    def iso(value: Optional[datetime]) -> Optional[str]:
        normalized = _as_utc(value)
        return normalized.isoformat() if normalized else None

    return {
        "status": health_status,
        "stale": stale,
        "running": running,
        "last_run_status": state.last_status,
        "last_attempted_at": iso(state.last_attempted_at),
        "last_completed_at": iso(state.last_completed_at),
        "last_successful_at": iso(state.last_successful_at),
        "last_article_retrieved_at": iso(state.last_article_retrieved_at),
        "last_article_inserted_at": iso(state.last_article_inserted_at),
        "latest_retrieved_pub_date": iso(state.latest_retrieved_pub_date),
        "latest_inserted_pub_date": iso(state.latest_inserted_pub_date),
        "consecutive_failures": state.consecutive_failures,
        "error_code": state.last_error_code,
        "metrics": state.last_metrics or {},
    }


def _is_finnhub_timeout(exc: BaseException) -> bool:
    """Recognize requests/urllib3 timeouts, including safely chained causes."""
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, (TimeoutError, RequestsTimeout, Urllib3TimeoutError)):
            return True
        current = current.__cause__ or current.__context__
    return False


def _fetch_finnhub_company_news(
    client: Any,
    ticker: str,
    from_date: str,
    to_date: str,
) -> list[dict[str, Any]]:
    """Call the singleton synchronous client without concurrent use."""
    with _finnhub_company_news_lock:
        return client.company_news(ticker, _from=from_date, to=to_date)

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


async def fetch_and_ingest_watchlist_once(
    session_factory,
    *,
    connection_manager=None,
    limit: Optional[int] = None,
    force: bool = False,
    now: Optional[datetime] = None,
    trigger_kind: str = "auto",
) -> dict[str, Any]:
    """Run one leased, checkpointed, idempotent production ingestion cycle."""
    started_at = time.monotonic()
    now_utc = _as_utc(now) or datetime.now(timezone.utc)
    owner = uuid4().hex
    # Production persists the complete bounded provider response. Applying an
    # article-count cutoff could permanently omit delayed/older stories while
    # still advancing the successful-window checkpoint.
    article_limit = limit
    counters: dict[str, Any] = {
        "articles_returned": 0, "articles_fetched": 0, "articles_inserted": 0,
        "articles_changed": 0, "duplicates_ignored": 0,
        "oldest_fetched_article_timestamp": None, "newest_fetched_article_timestamp": None,
        "newest_inserted_article_timestamp": None, "report_candidates": 0,
        "report_candidates_discovered": 0, "report_candidates_unique": 0,
        "scheduler_duplicates_skipped": 0, "enqueue_attempts": 0, "jobs_created": 0,
        "jobs_deduplicated": 0,
    }
    provider: dict[str, int | bool] = {
        "provider_requests": 0, "provider_successes": 0,
        "provider_timeouts": 0, "provider_failures": 0, "consecutive_timeouts": 0,
        "provider_rate_limits": 0, "provider_retries": 0,
        "provider_timeout_breaker_open": False, "provider_rate_limit_breaker_open": False,
        "tickers_skipped_provider_timeout": 0, "tickers_skipped_rate_limit": 0,
    }
    symbol_outcomes: dict[str, dict[str, Any]] = {}

    async with session_factory() as state_session:
        previous = await _load_ingestion_state(state_session)
        if not force and not should_run_ingestion(
            now_utc,
            previous.last_successful_window_end if previous else None,
            trigger_kind=trigger_kind,
        ):
            return {
                "status": "skipped_cadence", "tickers": 0,
                "reason": "new_york_cadence_guard", "trigger_kind": trigger_kind,
                "duration_seconds": 0.0,
            }
        lease = await _acquire_ingestion_lease(state_session, owner=owner, now=now_utc)
    if lease is None:
        logger.info("[NewsIngestion] event=skipped reason=active_lease")
        return {"status": "skipped_overlap", "tickers": 0, "duration_seconds": 0.0}

    window = calculate_ingestion_window(now_utc, lease.last_successful_window_end)
    logger.info(
        "[NewsIngestion] event=started operation=watchlist_once owner=%s "
        "window_start=%s window_end=%s lookback_minutes=%d recovery_mode=%s",
        owner, window.start.isoformat(), window.end.isoformat(),
        window.lookback_minutes, window.mode,
    )
    tickers: list[str] = []
    results: dict[str, int] = {}
    try:
        async with session_factory() as session:
            tickers = await get_all_tickers(session)
            if tickers:
                results = await fetch_and_ingest_many(
                    tickers, session, limit=article_limit, window=window,
                    _cycle_counters=counters, _scheduler_attempted_asset_ids=set(),
                    _provider_counters=provider, _symbol_outcomes=symbol_outcomes,
                    _lease_owner=owner,
                )
                if counters["articles_inserted"]:
                    try:
                        await _recover_thumbnails(session)
                    except Exception as exc:
                        logger.warning(
                            "[NewsIngestion] event=thumbnail_recovery_failed exception_type=%s",
                            type(exc).__name__,
                        )
    except asyncio.CancelledError:
        cancellation_metrics = {
            "duration_seconds": round(time.monotonic() - started_at, 3),
            "symbols_configured": len(tickers),
            "symbols_attempted": len(symbol_outcomes),
            "symbols_successful": sum(
                1 for item in symbol_outcomes.values()
                if item.get("last_outcome") == "success"
            ),
            "symbols_failed": len(tickers) - sum(
                1 for item in symbol_outcomes.values()
                if item.get("last_outcome") == "success"
            ),
            "lookback_minutes": window.lookback_minutes,
            "recovery_mode": window.mode,
            **provider,
            **counters,
        }

        async def _record_cancellation() -> None:
            async with session_factory() as state_session:
                await _finish_ingestion_run(
                    state_session,
                    owner=owner,
                    now=datetime.now(timezone.utc),
                    status="cancelled",
                    metrics=cancellation_metrics,
                    error_code="cancelled",
                )

        try:
            await asyncio.shield(_record_cancellation())
        except Exception:
            logger.error("[NewsIngestion] event=cancellation_state_write_failed")
        logger.warning("[NewsIngestion] event=cancelled operation=watchlist_once")
        raise
    except Exception as exc:
        logger.error(
            "[NewsIngestion] event=failed operation=watchlist_once exception_type=%s message=%s",
            type(exc).__name__, sanitize_database_error(exc),
        )
        failure_successes = sum(
            1 for item in symbol_outcomes.values()
            if item.get("last_outcome") == "success"
        )
        failure_metrics = {
            "duration_seconds": round(time.monotonic() - started_at, 3),
            "symbols_attempted": len(symbol_outcomes),
            "symbols_successful": failure_successes,
            "symbols_failed": len(tickers) - failure_successes,
            "lookback_minutes": window.lookback_minutes,
            "recovery_mode": window.mode,
            **provider,
            **counters,
        }
        try:
            async with session_factory() as state_session:
                await _finish_ingestion_run(
                    state_session, owner=owner, now=datetime.now(timezone.utc),
                    status="failed", metrics=failure_metrics,
                    error_code=type(exc).__name__,
                )
        except Exception:
            logger.error("[NewsIngestion] event=failure_state_write_failed", exc_info=True)
        raise

    successful_symbols = sum(
        1 for item in symbol_outcomes.values()
        if item.get("last_outcome") == "success"
    )
    failed_symbols = len(tickers) - successful_symbols
    status = "completed" if failed_symbols == 0 else "partial"
    failure_outcomes = {
        item.get("last_outcome")
        for item in symbol_outcomes.values()
        if item.get("last_outcome") != "success"
    }
    if provider["provider_rate_limit_breaker_open"] or failure_outcomes == {"rate_limited"}:
        error_code = "provider_rate_limited"
    elif provider["provider_timeout_breaker_open"] or failure_outcomes == {"timeout"}:
        error_code = "provider_timeout"
    elif failed_symbols:
        error_code = "provider_failure"
    else:
        error_code = None
    duration = round(time.monotonic() - started_at, 3)
    metrics = {
        "duration_seconds": duration,
        "symbols_configured": len(tickers),
        "symbols_attempted": len(symbol_outcomes),
        "symbols_successful": successful_symbols,
        "symbols_failed": failed_symbols,
        "lookback_minutes": window.lookback_minutes,
        "window_start": window.start.isoformat(),
        "window_end": window.end.isoformat(),
        "provider_from_date": window.start.strftime("%Y-%m-%d"),
        "provider_to_date": window.end.strftime("%Y-%m-%d"),
        "recovery_mode": window.mode,
        **provider,
        **counters,
    }
    async with session_factory() as state_session:
        await _finish_ingestion_run(
            state_session, owner=owner, now=datetime.now(timezone.utc),
            status=status, metrics=metrics,
            successful_window_end=window.end if status == "completed" else None,
            error_code=error_code,
        )

    provider_failure_details: dict[str, dict[str, Any]] = {}
    for ticker, outcome in symbol_outcomes.items():
        if outcome.get("last_outcome") == "success":
            continue
        safe_outcome: dict[str, Any] = {
            "outcome": outcome.get("last_outcome") or "unknown",
        }
        if isinstance(outcome.get("status_code"), int):
            safe_outcome["status_code"] = outcome["status_code"]
        if isinstance(outcome.get("exception_type"), str):
            safe_outcome["exception_type"] = outcome["exception_type"]
        provider_failure_details[ticker] = safe_outcome

    summary = {
        "status": status, "tickers": len(tickers), "tickers_processed": len(results),
        "symbols_attempted": len(symbol_outcomes),
        "symbols_successful": successful_symbols, "symbols_failed": failed_symbols,
        "error_code": error_code,
        "articles_returned": counters["articles_returned"],
        "articles_inserted": counters["articles_inserted"],
        "duplicates_ignored": counters["duplicates_ignored"],
        "provider_requests": provider["provider_requests"],
        "provider_successes": provider["provider_successes"],
        "provider_timeouts": provider["provider_timeouts"],
        "provider_failures": provider["provider_failures"],
        "provider_retries": provider["provider_retries"],
        "provider_rate_limits": provider["provider_rate_limits"],
        "provider_timeout_breaker_open": provider["provider_timeout_breaker_open"],
        "provider_rate_limit_breaker_open": provider["provider_rate_limit_breaker_open"],
        "tickers_skipped_provider_timeout": provider["tickers_skipped_provider_timeout"],
        "tickers_skipped_rate_limit": provider["tickers_skipped_rate_limit"],
        "provider_failure_details": provider_failure_details,
        "results": results, "duration_seconds": duration,
        "lookback_minutes": window.lookback_minutes, "recovery_mode": window.mode,
    }
    logger.info(
        "[NewsIngestion] event=%s operation=watchlist_once status=%s metrics=%s",
        "completed" if status == "completed" else "partial", status, metrics,
    )
    if connection_manager is not None and counters["articles_inserted"]:
        try:
            await connection_manager.broadcast({"type": "news_refresh"})
        except Exception:
            logger.warning("[NewsIngestion] event=broadcast_failed", exc_info=True)
    return summary

async def _scheduled_ingest_loop(session_factory, tickers_fn, connection_manager) -> None:
    """Run sequential ticker ingestion and bounded thumbnail recovery every 15 minutes."""
    def memory_context(*, ticker_count: int, tickers_processed: int, articles_ingested: int,
                       cycle_counters: dict[str, int], thumbnail_counters: dict[str, int],
                       provider_counters: dict[str, int | bool],
                       duration_seconds: float | None = None, outcome: str | None = None) -> dict[str, int | float | str | bool]:
        context: dict[str, int | float | str | bool] = {
            "ticker_count": ticker_count, "tickers_processed": tickers_processed,
            "articles_fetched": cycle_counters["articles_fetched"], "articles_changed": cycle_counters["articles_changed"],
            "articles_ingested": articles_ingested, "report_candidates": cycle_counters["report_candidates"],
            "report_candidates_discovered": cycle_counters["report_candidates_discovered"],
            "report_candidates_unique": cycle_counters["report_candidates_unique"],
            "scheduler_duplicates_skipped": cycle_counters["scheduler_duplicates_skipped"],
            "enqueue_attempts": cycle_counters["enqueue_attempts"], "jobs_created": cycle_counters["jobs_created"],
            "jobs_deduplicated": cycle_counters["jobs_deduplicated"],
            "thumbnail_candidates": thumbnail_counters["thumbnail_candidates"],
            "thumbnail_attempted": thumbnail_counters["thumbnail_attempted"],
            "thumbnail_recovered": thumbnail_counters["thumbnail_recovered"],
            "provider_requests": provider_counters["provider_requests"],
            "provider_successes": provider_counters["provider_successes"],
            "provider_timeouts": provider_counters["provider_timeouts"],
            "provider_failures": provider_counters["provider_failures"],
            "consecutive_timeouts": provider_counters["consecutive_timeouts"],
            "provider_timeout_breaker_open": provider_counters["provider_timeout_breaker_open"],
            "tickers_skipped_provider_timeout": provider_counters["tickers_skipped_provider_timeout"],
        }
        if duration_seconds is not None: context["duration_seconds"] = duration_seconds
        if outcome is not None: context["outcome"] = outcome
        return context

    while True:
        cycle_started_at = time.monotonic()
        ticker_count = tickers_processed = articles_ingested = recovered_thumbnail_count = 0
        cycle_counters = {"articles_fetched": 0, "articles_changed": 0, "report_candidates": 0,
            "report_candidates_discovered": 0, "report_candidates_unique": 0,
            "scheduler_duplicates_skipped": 0, "enqueue_attempts": 0, "jobs_created": 0, "jobs_deduplicated": 0}
        thumbnail_counters = {"thumbnail_candidates": 0, "thumbnail_attempted": 0, "thumbnail_recovered": 0}
        provider_counters: dict[str, int | bool] = {"provider_requests": 0, "provider_successes": 0,
            "provider_timeouts": 0, "provider_failures": 0, "consecutive_timeouts": 0,
            "provider_timeout_breaker_open": False, "tickers_skipped_provider_timeout": 0}
        scheduler_attempted_asset_ids: set[int] = set()
        outcome = "cancelled"
        try:
            tickers = await tickers_fn()
            ticker_count = len(tickers)
            if settings.MEMORY_DIAGNOSTICS_ENABLED:
                log_memory("news_cycle_start", logger_to_use=logger, enabled=True, extra=memory_context(
                    ticker_count=ticker_count, tickers_processed=tickers_processed, articles_ingested=articles_ingested,
                    cycle_counters=cycle_counters, thumbnail_counters=thumbnail_counters, provider_counters=provider_counters))
            async with session_factory() as session:
                if not tickers:
                    logger.info("[NewsScheduler] No tickers in watchlist; skipping cycle.")
                else:
                    results = await fetch_and_ingest_many(tickers, session, limit=None, _cycle_counters=cycle_counters,
                        _scheduler_attempted_asset_ids=scheduler_attempted_asset_ids, _provider_counters=provider_counters)
                    articles_ingested = sum(results.values())
                    tickers_processed = len(results)
                    logger.info("[NewsScheduler] Cycle complete - ingested %d articles across %d tickers: %s",
                        articles_ingested, tickers_processed, results)
                    logger.info("[NewsScheduler] Provider summary provider_requests=%d provider_successes=%d "
                        "provider_timeouts=%d provider_failures=%d consecutive_timeouts=%d "
                        "provider_timeout_breaker_open=%s tickers_skipped_provider_timeout=%d",
                        provider_counters["provider_requests"], provider_counters["provider_successes"],
                        provider_counters["provider_timeouts"], provider_counters["provider_failures"],
                        provider_counters["consecutive_timeouts"], provider_counters["provider_timeout_breaker_open"],
                        provider_counters["tickers_skipped_provider_timeout"])
                if settings.MEMORY_DIAGNOSTICS_ENABLED:
                    log_memory("after_ticker_ingestion", logger_to_use=logger, enabled=True, extra=memory_context(
                        ticker_count=ticker_count, tickers_processed=tickers_processed, articles_ingested=articles_ingested,
                        cycle_counters=cycle_counters, thumbnail_counters=thumbnail_counters, provider_counters=provider_counters))
                    log_memory("before_thumbnail_recovery", logger_to_use=logger, enabled=True, extra=memory_context(
                        ticker_count=ticker_count, tickers_processed=tickers_processed, articles_ingested=articles_ingested,
                        cycle_counters=cycle_counters, thumbnail_counters=thumbnail_counters, provider_counters=provider_counters))
                if cycle_counters["articles_fetched"] > 0:
                    try:
                        recovered_thumbnail_count = await _recover_thumbnails(session, counters=thumbnail_counters)
                        if recovered_thumbnail_count:
                            logger.info("[NewsScheduler] Thumbnail recovery: +%d images recovered.", recovered_thumbnail_count)
                    except Exception as exc:
                        logger.error("[NewsScheduler] Thumbnail recovery failed exception_type=%s", type(exc).__name__)
                else:
                    logger.info("[NewsScheduler] Thumbnail recovery skipped articles_fetched=0")
                if settings.MEMORY_DIAGNOSTICS_ENABLED:
                    log_memory("after_thumbnail_recovery", logger_to_use=logger, enabled=True, extra=memory_context(
                        ticker_count=ticker_count, tickers_processed=tickers_processed, articles_ingested=articles_ingested,
                        cycle_counters=cycle_counters, thumbnail_counters=thumbnail_counters, provider_counters=provider_counters))
            try:
                await connection_manager.broadcast({"type": "news_refresh"})
                logger.info("[NewsScheduler] Broadcast news_refresh to all clients.")
            except Exception as exc:
                logger.error("[NewsScheduler] Failed to broadcast news_refresh exception_type=%s", type(exc).__name__)
            if settings.MEMORY_DIAGNOSTICS_ENABLED:
                log_memory("after_broadcast", logger_to_use=logger, enabled=True, extra=memory_context(
                    ticker_count=ticker_count, tickers_processed=tickers_processed, articles_ingested=articles_ingested,
                    cycle_counters=cycle_counters, thumbnail_counters=thumbnail_counters, provider_counters=provider_counters))
            outcome = "provider_timeout" if provider_counters["provider_timeout_breaker_open"] else "completed"
        except Exception as exc:
            outcome = "failed"
            logger.error("[NewsScheduler] Error during ingestion cycle exception_type=%s", type(exc).__name__)
        finally:
            if settings.MEMORY_DIAGNOSTICS_ENABLED:
                log_memory("news_ingestion_cycle_end", logger_to_use=logger, enabled=True, extra=memory_context(
                    ticker_count=ticker_count, tickers_processed=tickers_processed, articles_ingested=articles_ingested,
                    cycle_counters=cycle_counters, thumbnail_counters=thumbnail_counters, provider_counters=provider_counters,
                    duration_seconds=round(time.monotonic() - cycle_started_at, 3), outcome=outcome))
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
    """Convert a Unix/ISO timestamp to the schema's UTC-naive representation."""
    if not ts:
        return None
    # Handle integer timestamps
    if isinstance(ts, (int, float)):
        try:
            return datetime.fromtimestamp(ts, tz=timezone.utc).replace(tzinfo=None)
        except (TypeError, ValueError, OSError):
            return None
    # Handle ISO format strings like "2025-08-13T09:30:43Z"
    if isinstance(ts, str):
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc).replace(tzinfo=None)
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


_TRACKING_QUERY_KEYS = {
    "fbclid", "gclid", "mc_cid", "mc_eid", "ref", "ref_src", "source",
}


def _canonical_url_for_identity(url: str) -> str:
    """Remove fragments and known tracking parameters without changing routing keys."""
    parts = urlsplit(url.strip())
    filtered_query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in _TRACKING_QUERY_KEYS
    ]
    return urlunsplit((
        parts.scheme.lower(), parts.netloc.lower(), parts.path,
        urlencode(filtered_query, doseq=True), "",
    ))


def _stable_finnhub_identity(article: Dict[str, Any], url: str) -> str:
    provider_id = article.get("id")
    if provider_id is not None and str(provider_id).strip():
        return f"finnhub:{str(provider_id).strip()}"
    canonical = _canonical_url_for_identity(url)
    return f"url:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"


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

    # Prefer Finnhub's immutable provider identifier. Canonical URL hashing is
    # the deterministic fallback for legacy/provider rows without an ID.
    finnhub_id = _stable_finnhub_identity(article, url)

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
    """Insert one immutable article, ignoring either database identity conflict."""
    values = article_in.model_dump(exclude_unset=True)
    stmt = pg_insert(NewsArticle).values(**values).on_conflict_do_nothing().returning(NewsArticle.id)
    inserted_id = (await session.execute(stmt)).scalar_one_or_none()
    await session.commit()
    if inserted_id is None:
        return None
    return (await session.execute(select(NewsArticle).where(NewsArticle.id == inserted_id))).scalar_one()


async def batch_ingest_articles(
    session: AsyncSession, articles_in: list[NewsArticleIngest]
) -> ArticlePersistResult:
    """Insert an in-memory de-duplicated batch and ignore all DB conflicts."""
    if not articles_in:
        return ArticlePersistResult(inserted_ids=[], submitted=0, unique_submitted=0)

    unique_articles = _deduplicate_articles(articles_in)
    values = [article.model_dump(exclude_unset=True) for article in unique_articles]
    if not values:
        return ArticlePersistResult(inserted_ids=[], submitted=len(articles_in), unique_submitted=0)

    # No target means either unique(finnhub_id) or unique(article_url) safely
    # suppresses replays and races. Avoiding an UPDATE also prevents ticker
    # ownership from flapping when one story appears in several symbol feeds.
    inserted_ids: list[int] = []
    for offset in range(0, len(values), _ARTICLE_DB_CHUNK_SIZE):
        chunk = values[offset:offset + _ARTICLE_DB_CHUNK_SIZE]
        stmt = (
            pg_insert(NewsArticle)
            .values(chunk)
            .on_conflict_do_nothing()
            .returning(NewsArticle.id)
        )
        result = await session.execute(stmt)
        inserted_ids.extend(result.scalars().all())
    await session.commit()
    return ArticlePersistResult(
        inserted_ids=inserted_ids,
        submitted=len(articles_in),
        unique_submitted=len(values),
    )


def _deduplicate_articles(articles_in: list[NewsArticleIngest]) -> list[NewsArticleIngest]:
    """Preserve the first row for each strong ID/canonical URL in a response."""
    unique: dict[tuple[str, str], NewsArticleIngest] = {}
    for article in articles_in:
        if article.finnhub_id:
            identity = ("finnhub_id", article.finnhub_id)
        elif article.article_url:
            identity = ("article_url", _canonical_url_for_identity(article.article_url))
        else:
            continue
        unique.setdefault(identity, article)
    return list(unique.values())


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
    limit: Optional[int] = 30,
    *,
    window: Optional[IngestionWindow] = None,
    _cycle_counters: Optional[dict[str, int]] = None,
    _scheduler_attempted_asset_ids: Optional[set[int]] = None,
    _provider_counters: Optional[dict[str, int | bool]] = None,
    _provider_state: Optional[dict[str, Any]] = None,
) -> int:
    """
    Fetch latest news for a ticker from Finnhub and persist to PostgreSQL.
    Returns the count of newly ingested articles.
    Uses batch upsert to minimize database round-trips.
    """
    request_window = window or calculate_ingestion_window(datetime.now(timezone.utc), None)
    from_date = request_window.start.strftime("%Y-%m-%d")
    to_date = request_window.end.strftime("%Y-%m-%d")

    async def _company_news_request(client, symbol: str, start_date: str, end_date: str):
        response = await asyncio.to_thread(
            _fetch_finnhub_company_news, client, symbol, start_date, end_date,
        )
        if not isinstance(response, list):
            raise TypeError("Finnhub company-news response must be a list")
        return response

    try:
        client = get_finnhub_client()
        raw_news = await _retry_api(
            _company_news_request, client, ticker.upper(), from_date, to_date,
            _request_operation="company_news", _request_ticker=ticker.upper(),
            _request_metrics=_provider_counters,
        )
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        is_timeout = _is_finnhub_timeout(exc)
        rate_limited = _is_rate_limit_error(exc)
        if _provider_state is not None:
            _provider_state.update({
                "last_outcome": "rate_limited" if rate_limited else ("timeout" if is_timeout else "failure"),
                "status_code": _exception_status_code(exc),
                "exception_type": type(exc).__name__,
            })
        logger.error(
            "[NewsIngestion] event=provider_failed ticker=%s exception_type=%s "
            "status_code=%s rate_limited=%s",
            ticker.upper(), type(exc).__name__, _exception_status_code(exc),
            str(rate_limited).lower(),
        )
        return 0

    if _provider_state is not None:
        _provider_state.update({"last_outcome": "success", "articles_returned": len(raw_news or [])})
    if _cycle_counters is not None:
        _cycle_counters.setdefault("articles_returned", 0)
        _cycle_counters["articles_returned"] += len(raw_news or [])
    logger.info(
        "[NewsIngestion] event=provider_succeeded ticker=%s articles_returned=%d "
        "provider_from_date=%s provider_to_date=%s lookback_minutes=%d recovery_mode=%s",
        ticker.upper(), len(raw_news or []), from_date, to_date,
        request_window.lookback_minutes, request_window.mode,
    )

    if not raw_news:
        logger.info(f"[NewsIngestion] No news returned for {ticker}")
        return 0

    def _sort_timestamp(article: dict[str, Any]) -> datetime:
        parsed = _parse_finnhub_timestamp(article.get("datetime"))
        return parsed or datetime.min

    ordered_news = sorted(raw_news, key=_sort_timestamp, reverse=True)
    if limit is not None and len(ordered_news) > limit:
        logger.warning(
            "[NewsIngestion] event=response_truncated ticker=%s returned=%d limit=%d",
            ticker.upper(), len(ordered_news), limit,
        )
    selected_news = ordered_news if limit is None else ordered_news[:limit]
    normalized_articles: list[NewsArticleIngest] = []
    for article in selected_news:
        try:
            normalized = normalize_finnhub_article(article, ticker)
            if not normalized or not normalized.article_url:
                logger.warning(f"[NewsIngestion] Skipping article without URL for {ticker}")
                continue
            normalized_articles.append(normalized)
        except Exception as e:
            logger.error(f"[NewsIngestion] Failed to normalize Finnhub article for {ticker}: {e}")
            continue

    if not normalized_articles:
        logger.info(f"[NewsIngestion] No valid articles to ingest for {ticker}")
        return 0

    persist_result = await batch_ingest_articles(session, normalized_articles)
    material_article_ids = persist_result.inserted_ids
    ingested = persist_result.inserted
    articles_fetched = len(normalized_articles)
    duplicates_ignored = persist_result.duplicates_ignored
    article_dates = [item.pub_date for item in normalized_articles if item.pub_date is not None]
    oldest_fetched = min(article_dates) if article_dates else None
    newest_fetched = max(article_dates) if article_dates else None
    inserted_rows: list[NewsArticle] = []
    for offset in range(0, len(material_article_ids), _ARTICLE_DB_CHUNK_SIZE):
        id_chunk = material_article_ids[offset:offset + _ARTICLE_DB_CHUNK_SIZE]
        inserted_rows.extend((await session.execute(
            select(NewsArticle).where(NewsArticle.id.in_(id_chunk))
        )).scalars().all())
    inserted_dates = [item.pub_date for item in inserted_rows if item.pub_date is not None]
    newest_inserted = max(inserted_dates) if inserted_dates else None
    logger.info(
        "[NewsIngestion] event=database_persisted ticker=%s articles_fetched=%d "
        "articles_inserted=%d duplicates_ignored=%d",
        ticker.upper(), articles_fetched, ingested, duplicates_ignored,
    )

    if settings.INTELLIGENCE_ENABLED and material_article_ids:
        from backend.intelligence.article_service import ARTICLE_PROMPT_HASH, article_source_content_hash
        for row in inserted_rows:
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
        # Only genuinely new stories can trigger downstream market analysis.
        # Replayed overlap rows therefore do not refresh quote/profile data.
        for article in (inserted_rows if settings.NEWS_ENQUEUE_COMPANY_REPORTS else []):
            # Extract tickers from title + summary
            found_tickers = ticker_extractor.extract(
                text=article.summary or "", title=article.title or "",
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
        f"articles_inserted={ingested} duplicates_ignored={duplicates_ignored} "
        f"report_candidates={report_candidates} "
        f"report_candidates_discovered={report_candidates_discovered} "
        f"report_candidates_unique={report_candidates_unique} "
        f"scheduler_duplicates_skipped={scheduler_duplicates_skipped} "
        f"enqueue_attempts={enqueue_attempts} jobs_created={jobs_created} "
        f"jobs_deduplicated={jobs_deduplicated}"
    )

    if _cycle_counters is not None:
        for key, value in {
            "articles_fetched": articles_fetched,
            "articles_inserted": ingested,
            "articles_changed": ingested,
            "duplicates_ignored": duplicates_ignored,
            "report_candidates": report_candidates,
            "report_candidates_discovered": report_candidates_discovered,
            "report_candidates_unique": report_candidates_unique,
            "scheduler_duplicates_skipped": scheduler_duplicates_skipped,
            "enqueue_attempts": enqueue_attempts,
            "jobs_created": jobs_created,
            "jobs_deduplicated": jobs_deduplicated,
        }.items():
            _cycle_counters[key] = int(_cycle_counters.get(key, 0)) + value

        def _iso_utc_naive(value: Optional[datetime]) -> Optional[str]:
            return value.replace(tzinfo=timezone.utc).isoformat() if value else None

        oldest_iso = _iso_utc_naive(oldest_fetched)
        newest_iso = _iso_utc_naive(newest_fetched)
        inserted_iso = _iso_utc_naive(newest_inserted)
        current_oldest = _cycle_counters.get("oldest_fetched_article_timestamp")
        current_newest = _cycle_counters.get("newest_fetched_article_timestamp")
        current_inserted = _cycle_counters.get("newest_inserted_article_timestamp")
        if oldest_iso and (not current_oldest or oldest_iso < current_oldest):
            _cycle_counters["oldest_fetched_article_timestamp"] = oldest_iso
        if newest_iso and (not current_newest or newest_iso > current_newest):
            _cycle_counters["newest_fetched_article_timestamp"] = newest_iso
        if inserted_iso and (not current_inserted or inserted_iso > current_inserted):
            _cycle_counters["newest_inserted_article_timestamp"] = inserted_iso

    logger.info(f"[NewsIngestion] Ingested {ingested}/{len(normalized_articles)} articles for {ticker}")
    return ingested


async def fetch_and_ingest_many(
    tickers: list[str],
    session: AsyncSession,
    limit: Optional[int] = None,
    *,
    window: Optional[IngestionWindow] = None,
    _cycle_counters: Optional[dict[str, int]] = None,
    _scheduler_attempted_asset_ids: Optional[set[int]] = None,
    _provider_counters: Optional[dict[str, int | bool]] = None,
    _symbol_outcomes: Optional[dict[str, dict[str, Any]]] = None,
    _lease_owner: Optional[str] = None,
) -> dict[str, int]:
    """Fetch sequentially, with timeout and exhausted-429 circuit breakers."""
    results: dict[str, int] = {}
    scheduler_attempted_asset_ids = (
        _scheduler_attempted_asset_ids if _scheduler_attempted_asset_ids is not None else set()
    )
    provider_state: dict[str, Any] = {}
    consecutive_timeouts = 0

    for index, ticker in enumerate(tickers):
        provider_state.clear()
        count = await fetch_and_ingest_news(
            ticker.upper(), session, limit=limit, window=window, _cycle_counters=_cycle_counters,
            _scheduler_attempted_asset_ids=scheduler_attempted_asset_ids,
            _provider_counters=_provider_counters, _provider_state=provider_state,
        )
        results[ticker.upper()] = count
        if _symbol_outcomes is not None:
            _symbol_outcomes[ticker.upper()] = dict(provider_state)
        if _lease_owner and ((index + 1) % 5 == 0 or index == len(tickers) - 1):
            await _renew_ingestion_lease(
                session,
                owner=_lease_owner,
                now=datetime.now(timezone.utc),
            )
        if provider_state.get("last_outcome") == "rate_limited":
            skipped = len(tickers) - index - 1
            if _provider_counters is not None:
                _provider_counters["provider_rate_limit_breaker_open"] = True
                _provider_counters["tickers_skipped_rate_limit"] = int(
                    _provider_counters.get("tickers_skipped_rate_limit", 0)
                ) + skipped
            logger.warning(
                "[NewsScheduler] Provider rate-limit breaker opened tickers_skipped_rate_limit=%d",
                skipped,
            )
            break
        if provider_state.get("last_outcome") == "timeout":
            consecutive_timeouts += 1
        else:
            consecutive_timeouts = 0
        if _provider_counters is not None:
            _provider_counters["consecutive_timeouts"] = consecutive_timeouts
        if consecutive_timeouts >= _MAX_CONSECUTIVE_NEWS_PROVIDER_TIMEOUTS:
            skipped = len(tickers) - index - 1
            if _provider_counters is not None:
                _provider_counters["provider_timeout_breaker_open"] = True
                _provider_counters["tickers_skipped_provider_timeout"] += skipped
            logger.warning("[NewsScheduler] Provider timeout breaker opened consecutive_timeouts=%d "
                "tickers_skipped_provider_timeout=%d", consecutive_timeouts, skipped)
            break
        if index < len(tickers) - 1:
            await asyncio.sleep(_TICKER_DELAY)
    return results
