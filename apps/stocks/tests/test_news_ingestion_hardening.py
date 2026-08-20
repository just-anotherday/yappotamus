"""Focused coverage for news overlap, identity, cadence, and health semantics."""

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.models.news_schemas import NewsArticleIngest
from backend.routers import internal_jobs
from backend.services import news_ingestion_service as service


UTC = timezone.utc


def test_window_has_normal_overlap_and_missed_run_recovery(monkeypatch):
    monkeypatch.setenv("NEWS_OVERLAP_MINUTES", "30")
    monkeypatch.setenv("NEWS_ACTIVE_INTERVAL_MINUTES", "15")
    now = datetime(2026, 8, 14, 14, 15, tzinfo=UTC)

    normal = service.calculate_ingestion_window(now, now - timedelta(minutes=15))
    assert normal.start == now - timedelta(minutes=45)
    assert normal.lookback_minutes == 45
    assert normal.mode == "normal"

    recovered = service.calculate_ingestion_window(now, now - timedelta(minutes=30))
    assert recovered.start == now - timedelta(minutes=60)
    assert recovered.mode == "recovery"


def test_window_bounds_long_outage_and_handles_future_checkpoint(monkeypatch):
    monkeypatch.setenv("NEWS_MAX_BACKFILL_HOURS", "72")
    monkeypatch.setenv("NEWS_OVERLAP_MINUTES", "30")
    now = datetime(2026, 8, 14, 14, 15, tzinfo=UTC)

    bounded = service.calculate_ingestion_window(now, now - timedelta(days=10))
    assert bounded.start == now - timedelta(hours=72)
    assert bounded.mode == "bounded_backfill"

    skewed = service.calculate_ingestion_window(now, now + timedelta(hours=1))
    assert skewed.start == now - timedelta(minutes=30)
    assert skewed.end == now


def test_cadence_covers_active_hours_and_reduces_off_hours(monkeypatch):
    monkeypatch.setenv("NEWS_OFF_HOURS_INTERVAL_MINUTES", "60")
    # Friday 10:00 America/New_York.
    active = datetime(2026, 8, 14, 14, 0, tzinfo=UTC)
    assert service.should_run_ingestion(active, active - timedelta(minutes=15))

    # Saturday: guard until roughly the hourly mark, then run.
    weekend = datetime(2026, 8, 15, 14, 0, tzinfo=UTC)
    assert not service.should_run_ingestion(weekend, weekend - timedelta(minutes=30))
    assert service.should_run_ingestion(weekend, weekend - timedelta(minutes=60))

    # Classified workflow triggers are authoritative and DST-safe: the hourly
    # baseline runs off-hours; quarter-hour triggers are active-hours only.
    assert service.should_run_ingestion(
        weekend, weekend - timedelta(minutes=60), trigger_kind="hourly"
    )
    assert not service.should_run_ingestion(
        weekend, weekend - timedelta(hours=2), trigger_kind="quarter_hour"
    )
    assert not service.should_run_ingestion(
        active, active - timedelta(minutes=1), trigger_kind="hourly"
    )


def test_provider_id_is_preferred_and_url_fallback_is_canonical():
    with_id = service.normalize_finnhub_article(
        {"id": 123, "url": "https://news.example/story?utm_source=x", "datetime": 1}, "AAPL"
    )
    assert with_id and with_id.finnhub_id == "finnhub:123"

    first = service.normalize_finnhub_article(
        {"url": "HTTPS://NEWS.EXAMPLE/story?x=1&utm_source=a#top", "datetime": 1}, "AAPL"
    )
    second = service.normalize_finnhub_article(
        {"url": "https://news.example/story?x=1&utm_campaign=b", "datetime": 1}, "AAPL"
    )
    assert first and second and first.finnhub_id == second.finnhub_id


def test_distinct_provider_ids_do_not_collapse_similar_headlines():
    articles = [
        NewsArticleIngest(finnhub_id="finnhub:1", article_url="https://example/1", title="Same"),
        NewsArticleIngest(finnhub_id="finnhub:2", article_url="https://example/2", title="Same"),
    ]
    assert len(service._deduplicate_articles(articles)) == 2


def test_in_response_duplicate_identity_is_removed_before_postgres_insert():
    articles = [
        NewsArticleIngest(finnhub_id="finnhub:1", article_url="https://example/first"),
        NewsArticleIngest(finnhub_id="finnhub:1", article_url="https://example/variant"),
    ]
    deduplicated = service._deduplicate_articles(articles)
    assert len(deduplicated) == 1
    assert deduplicated[0].article_url == "https://example/first"


def test_provider_timestamps_are_normalized_to_utc_naive():
    unix = service._parse_finnhub_timestamp(1_700_000_000)
    offset = service._parse_finnhub_timestamp("2023-11-14T17:13:20-05:00")
    assert unix == offset == datetime(2023, 11, 14, 22, 13, 20)


@pytest.mark.asyncio
async def test_production_path_persists_complete_bounded_response(monkeypatch):
    raw_news = [
        {
            "id": index,
            "url": f"https://news.example/{index}",
            "datetime": 1_700_000_000 + index,
            "headline": f"Story {index}",
        }
        for index in range(300)
    ]
    monkeypatch.setattr(service, "_retry_api", AsyncMock(return_value=raw_news))
    monkeypatch.setattr(service, "get_finnhub_client", lambda: object())
    persist = AsyncMock(
        return_value=service.ArticlePersistResult(
            inserted_ids=[], submitted=len(raw_news), unique_submitted=len(raw_news),
        )
    )
    monkeypatch.setattr(service, "batch_ingest_articles", persist)

    assert await service.fetch_and_ingest_news("AAPL", object(), limit=None) == 0
    assert len(persist.await_args.args[1]) == len(raw_news)


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid_response", [None, {}])
async def test_non_list_provider_response_is_failure_not_zero_news(
    monkeypatch, invalid_response
):
    provider = {
        "provider_requests": 0,
        "provider_successes": 0,
        "provider_failures": 0,
    }

    async def execute_request(func, *args, **kwargs):
        metrics = kwargs["_request_metrics"]
        metrics["provider_requests"] += 1
        try:
            result = await func(*args)
        except Exception:
            metrics["provider_failures"] += 1
            raise
        metrics["provider_successes"] += 1
        return result

    monkeypatch.setattr(service, "_retry_api", execute_request)
    monkeypatch.setattr(service, "get_finnhub_client", lambda: object())
    monkeypatch.setattr(
        service.asyncio,
        "to_thread",
        AsyncMock(return_value=invalid_response),
    )
    persist = AsyncMock()
    monkeypatch.setattr(service, "batch_ingest_articles", persist)
    outcome = {}

    result = await service.fetch_and_ingest_news(
        "AAPL",
        object(),
        limit=None,
        _provider_counters=provider,
        _provider_state=outcome,
    )

    assert result == 0
    assert provider == {
        "provider_requests": 1,
        "provider_successes": 0,
        "provider_failures": 1,
    }
    assert outcome["last_outcome"] == "failure"
    assert outcome["exception_type"] == "TypeError"
    persist.assert_not_awaited()


@pytest.mark.asyncio
async def test_large_persistence_batch_is_chunked_without_discarding_rows():
    result = SimpleNamespace(
        scalars=lambda: SimpleNamespace(all=lambda: []),
    )
    session = SimpleNamespace(
        execute=AsyncMock(return_value=result),
        commit=AsyncMock(),
    )
    articles = [
        NewsArticleIngest(
            finnhub_id=f"finnhub:{index}",
            article_url=f"https://news.example/{index}",
        )
        for index in range(501)
    ]

    persisted = await service.batch_ingest_articles(session, articles)
    assert session.execute.await_count == 3
    assert persisted.submitted == persisted.unique_submitted == 501


@pytest.mark.asyncio
async def test_rate_limit_breaker_stops_remaining_symbols(monkeypatch):
    async def limited(_ticker, _session, **kwargs):
        kwargs["_provider_state"]["last_outcome"] = "rate_limited"
        return 0

    monkeypatch.setattr(service, "fetch_and_ingest_news", limited)
    counters = {
        "provider_rate_limit_breaker_open": False,
        "tickers_skipped_rate_limit": 0,
    }
    outcomes = {}
    result = await service.fetch_and_ingest_many(
        ["A", "B", "C"], object(), _provider_counters=counters, _symbol_outcomes=outcomes,
    )
    assert result == {"A": 0}
    assert counters["provider_rate_limit_breaker_open"] is True
    assert counters["tickers_skipped_rate_limit"] == 2
    assert outcomes["A"]["last_outcome"] == "rate_limited"


@pytest.mark.asyncio
async def test_long_fanout_renews_owned_lease_and_lost_lease_aborts(monkeypatch):
    async def successful(_ticker, _session, **kwargs):
        kwargs["_provider_state"]["last_outcome"] = "success"
        return 0

    monkeypatch.setattr(service, "fetch_and_ingest_news", successful)
    monkeypatch.setattr(service.asyncio, "sleep", AsyncMock())
    renew = AsyncMock()
    monkeypatch.setattr(service, "_renew_ingestion_lease", renew)

    await service.fetch_and_ingest_many(
        [f"T{index}" for index in range(6)], object(), _lease_owner="owner",
    )
    assert renew.await_count == 2  # after five symbols and at the end

    renew.reset_mock(side_effect=True)
    renew.side_effect = RuntimeError("news_ingestion_lease_lost")
    with pytest.raises(RuntimeError, match="lease_lost"):
        await service.fetch_and_ingest_many(["AAPL"], object(), _lease_owner="owner")


@pytest.mark.asyncio
async def test_completion_cannot_report_success_after_lease_ownership_is_lost():
    session = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(rowcount=0)),
        commit=AsyncMock(),
    )
    with pytest.raises(RuntimeError, match="lease_lost"):
        await service._finish_ingestion_run(
            session,
            owner="old-owner",
            now=datetime(2026, 8, 14, 14, 0, tzinfo=UTC),
            status="completed",
            metrics={},
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["partial", "failed", "cancelled"])
async def test_noncompleted_finish_releases_lease_without_advancing_checkpoint(status):
    class RecordingSession:
        def __init__(self):
            self.statement = None

        async def execute(self, statement):
            self.statement = statement
            return SimpleNamespace(rowcount=1)

        async def commit(self):
            return None

    session = RecordingSession()
    candidate_checkpoint = datetime(2026, 8, 14, 14, 0, tzinfo=UTC)

    await service._finish_ingestion_run(
        session,
        owner="owner",
        now=candidate_checkpoint,
        status=status,
        metrics={},
        successful_window_end=candidate_checkpoint,
    )

    values = {
        column.key: getattr(value, "value", value)
        for column, value in session.statement._values.items()
    }
    assert values["lease_owner"] is None
    assert values["lease_expires_at"] is None
    assert "last_successful_window_end" not in values


@pytest.mark.asyncio
async def test_completed_finish_releases_lease_and_advances_checkpoint():
    class RecordingSession:
        def __init__(self):
            self.statement = None

        async def execute(self, statement):
            self.statement = statement
            return SimpleNamespace(rowcount=1)

        async def commit(self):
            return None

    session = RecordingSession()
    checkpoint = datetime(2026, 8, 14, 14, 0, tzinfo=UTC)

    await service._finish_ingestion_run(
        session,
        owner="owner",
        now=checkpoint,
        status="completed",
        metrics={},
        successful_window_end=checkpoint,
    )

    values = {
        column.key: getattr(value, "value", value)
        for column, value in session.statement._values.items()
    }
    assert values["lease_owner"] is None
    assert values["lease_expires_at"] is None
    assert values["last_successful_window_end"] == checkpoint


class _SessionContext:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, *_args):
        return False


@pytest.mark.asyncio
async def test_overlapping_trigger_is_skipped_before_provider_fanout(monkeypatch):
    state = SimpleNamespace(last_successful_at=None, last_successful_window_end=None)
    monkeypatch.setattr(service, "_load_ingestion_state", AsyncMock(return_value=state))
    monkeypatch.setattr(service, "_acquire_ingestion_lease", AsyncMock(return_value=None))
    provider_fanout = AsyncMock()
    monkeypatch.setattr(service, "fetch_and_ingest_many", provider_fanout)

    result = await service.fetch_and_ingest_watchlist_once(lambda: _SessionContext(), force=True)
    assert result["status"] == "skipped_overlap"
    provider_fanout.assert_not_awaited()


@pytest.mark.asyncio
async def test_cancelled_cycle_records_failure_and_releases_owned_lease(monkeypatch):
    state = SimpleNamespace(last_successful_at=None, last_successful_window_end=None)
    monkeypatch.setattr(service, "_load_ingestion_state", AsyncMock(return_value=state))
    monkeypatch.setattr(service, "_acquire_ingestion_lease", AsyncMock(return_value=state))
    monkeypatch.setattr(service, "get_all_tickers", AsyncMock(return_value=["AAPL"]))
    monkeypatch.setattr(
        service,
        "fetch_and_ingest_many",
        AsyncMock(side_effect=asyncio.CancelledError()),
    )
    finish = AsyncMock()
    monkeypatch.setattr(service, "_finish_ingestion_run", finish)

    with pytest.raises(asyncio.CancelledError):
        await service.fetch_and_ingest_watchlist_once(lambda: _SessionContext(), force=True)
    assert finish.await_args.kwargs["status"] == "cancelled"
    assert finish.await_args.kwargs["error_code"] == "cancelled"


@pytest.mark.asyncio
async def test_partial_cycle_propagates_failure_to_workflow(monkeypatch):
    monkeypatch.setattr(
        internal_jobs, "fetch_and_ingest_watchlist_once",
        AsyncMock(return_value={"status": "partial", "symbols_failed": 1}),
    )
    with pytest.raises(Exception) as exc_info:
        await internal_jobs.ingest_news_once(force=False)
    assert getattr(exc_info.value, "status_code", None) == 424


@pytest.mark.asyncio
async def test_overlapping_cycle_does_not_mask_an_earlier_timed_out_job(monkeypatch):
    monkeypatch.setattr(
        internal_jobs, "fetch_and_ingest_watchlist_once",
        AsyncMock(return_value={"status": "skipped_overlap"}),
    )
    with pytest.raises(Exception) as exc_info:
        await internal_jobs.ingest_news_once(force=False)
    assert getattr(exc_info.value, "status_code", None) == 409


def _state(**overrides):
    values = {
        "lease_owner": None, "lease_expires_at": None, "last_successful_at": None,
        "last_status": None, "last_attempted_at": None, "last_completed_at": None,
        "last_article_retrieved_at": None, "last_article_inserted_at": None,
        "latest_retrieved_pub_date": None, "latest_inserted_pub_date": None,
        "consecutive_failures": 0, "last_error_code": None, "last_metrics": {},
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.asyncio
async def test_health_distinguishes_zero_news_success_from_stale_failure(monkeypatch):
    now = datetime(2026, 8, 14, 14, 0, tzinfo=UTC)
    healthy_zero = _state(
        last_successful_at=now - timedelta(minutes=10),
        last_attempted_at=now - timedelta(minutes=10),
        last_completed_at=now - timedelta(minutes=10),
        last_status="completed",
        last_metrics={"articles_inserted": 0, "articles_returned": 0},
    )
    monkeypatch.setattr(service, "_load_ingestion_state", AsyncMock(return_value=healthy_zero))
    health = await service.get_news_ingestion_health(object(), now=now)
    assert health["status"] == "healthy"
    assert health["stale"] is False
    assert health["metrics"]["articles_inserted"] == 0

    failed = _state(
        last_successful_at=now - timedelta(hours=3), last_status="partial",
        consecutive_failures=2, last_error_code="provider_timeout",
    )
    service._load_ingestion_state = AsyncMock(return_value=failed)
    health = await service.get_news_ingestion_health(object(), now=now)
    assert health["status"] == "stale"
    assert health["consecutive_failures"] == 2
    assert health["error_code"] == "provider_timeout"
