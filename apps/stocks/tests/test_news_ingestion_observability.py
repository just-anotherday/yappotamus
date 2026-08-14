"""Focused resource-safety tests for news ingestion."""

import asyncio
import threading
import time
from unittest.mock import AsyncMock

import httpx
from requests.exceptions import ConnectTimeout, ReadTimeout
from urllib3.exceptions import ReadTimeoutError
import pytest

from backend.services import news_ingestion_service as service
from backend.services import finnhub_service


@pytest.mark.asyncio
async def test_enqueue_counts_and_arguments(monkeypatch):
    session = object()
    enqueue = AsyncMock(side_effect=[True, False])
    monkeypatch.setattr(service, "enqueue_job", enqueue)

    result = await service._enqueue_company_report_jobs(session, "spy", {101, 202})

    assert result == {
        "report_candidates": 2,
        "report_candidates_discovered": 2,
        "report_candidates_unique": 2,
        "scheduler_duplicates_skipped": 0,
        "enqueue_attempts": 2,
        "jobs_created": 1,
        "jobs_deduplicated": 1,
    }
    assert enqueue.await_count == 2
    assert not hasattr(session, "commit")
    for call in enqueue.await_args_list:
        assert call.kwargs["job_type"] == "company_report"
        assert call.kwargs["target_type"] == "asset"
        assert call.kwargs["payload"] == {"ticker": "SPY"}
        assert call.kwargs["priority"] == 10


@pytest.mark.asyncio
async def test_scheduler_wide_enqueue_deduplication(monkeypatch):
    session = object()
    enqueue = AsyncMock(return_value=False)
    monkeypatch.setattr(service, "enqueue_job", enqueue)
    attempted = set()

    first = await service._enqueue_company_report_jobs(session, "spy", {1, 2}, scheduler_attempted_asset_ids=attempted)
    second = await service._enqueue_company_report_jobs(session, "qqq", {2, 3}, scheduler_attempted_asset_ids=attempted)

    assert first["enqueue_attempts"] == 2
    assert second["report_candidates_discovered"] == 2
    assert second["report_candidates_unique"] == 1
    assert second["scheduler_duplicates_skipped"] == 1
    assert second["enqueue_attempts"] == 1
    assert enqueue.await_count == 3
    assert {call.kwargs["target_id"] for call in enqueue.await_args_list} == {1, 2, 3}


@pytest.mark.asyncio
async def test_zero_candidates_is_safe(monkeypatch):
    enqueue = AsyncMock()
    monkeypatch.setattr(service, "enqueue_job", enqueue)
    result = await service._enqueue_company_report_jobs(object(), "spy", set())
    assert result["enqueue_attempts"] == 0
    assert result["report_candidates_unique"] == 0
    enqueue.assert_not_awaited()


@pytest.mark.asyncio
async def test_extract_og_image_accepts_html_rejects_non_html_and_bounds(monkeypatch, caplog):
    async def handler(request):
        if request.url.path == "/html":
            return httpx.Response(200, headers={"content-type": "text/html"}, content=b'<meta property="og:image" content="https://image.test/a.jpg">')
        if request.url.path == "/binary":
            return httpx.Response(200, headers={"content-type": "image/jpeg"}, content=b"x")
        return httpx.Response(200, headers={"content-type": "text/html"}, content=b"x" * 32)

    monkeypatch.setattr(service, "_MAX_OG_HTML_BYTES", 16)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=True) as client:
        # Use a normal limit for the valid page, then a strict one for the oversized page.
        monkeypatch.setattr(service, "_MAX_OG_HTML_BYTES", 1024)
        assert await service._extract_og_image("https://test/html", client=client) == "https://image.test/a.jpg"
        assert await service._extract_og_image("https://test/binary", client=client) is None
        monkeypatch.setattr(service, "_MAX_OG_HTML_BYTES", 16)
        assert await service._extract_og_image("https://test/large", client=client) is None
    assert "https://test/large" not in caplog.text
    assert "x" * 20 not in caplog.text


@pytest.mark.asyncio
async def test_extract_og_image_follows_redirect_and_accepts_missing_content_type():
    async def handler(request):
        if request.url.path == "/redirect":
            return httpx.Response(302, headers={"location": "https://test/final"})
        return httpx.Response(200, content=b'<meta property="og:image" content="https://image.test/final.jpg">')

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=True) as client:
        assert await service._extract_og_image("https://test/redirect", client=client) == "https://image.test/final.jpg"


@pytest.mark.asyncio
async def test_recovery_uses_one_shared_client_and_reports_counters(monkeypatch):
    rows = [(3, "https://example/a"), (2, "https://example/b")]
    result = type("Result", (), {"fetchall": lambda self: rows})()
    session = type("Session", (), {"execute": AsyncMock(return_value=result), "commit": AsyncMock()})()
    clients = []
    original_client = httpx.AsyncClient

    class TrackingClient(original_client):
        async def __aenter__(self):
            clients.append(self)
            return await super().__aenter__()

    seen = []
    async def extract(url, *, client, timeout=8.0):
        seen.append(client)
        return "https://image.test/a.jpg" if url.endswith("a") else None

    monkeypatch.setattr(service.httpx, "AsyncClient", TrackingClient)
    monkeypatch.setattr(service, "_extract_og_image", extract)
    counters = {"thumbnail_candidates": 0, "thumbnail_attempted": 0, "thumbnail_recovered": 0}
    assert await service._recover_thumbnails(session, counters=counters) == 1
    assert len(clients) == 1
    assert clients[0].is_closed
    assert len(set(map(id, seen))) == 1
    assert counters == {"thumbnail_candidates": 2, "thumbnail_attempted": 2, "thumbnail_recovered": 1}


@pytest.mark.asyncio
async def test_scheduler_emits_safe_phase_checkpoints(monkeypatch):
    events = []
    monkeypatch.setattr(type(service.settings), "MEMORY_DIAGNOSTICS_ENABLED", property(lambda _self: True))
    monkeypatch.setattr(service, "log_memory", lambda action, **kwargs: events.append((action, kwargs["extra"])))
    monkeypatch.setattr(service, "fetch_and_ingest_many", AsyncMock(return_value={"SPY": 2}))
    monkeypatch.setattr(service, "_recover_thumbnails", AsyncMock(return_value=0))

    class SessionContext:
        async def __aenter__(self): return object()
        async def __aexit__(self, *args): return False
    class Manager:
        broadcast = AsyncMock()
    async def stop_after_cycle(_):
        raise asyncio.CancelledError()

    monkeypatch.setattr(service.asyncio, "sleep", stop_after_cycle)
    with pytest.raises(asyncio.CancelledError):
        await service._scheduled_ingest_loop(lambda: SessionContext(), AsyncMock(return_value=["SPY"]), Manager())

    names = [name for name, _ in events]
    assert names == ["news_cycle_start", "after_ticker_ingestion", "before_thumbnail_recovery", "after_thumbnail_recovery", "after_broadcast", "news_ingestion_cycle_end"]
    forbidden = {"title", "summary", "article_url", "body", "html"}
    for _, context in events:
        assert not forbidden.intersection(context)
        assert all(isinstance(value, (str, int, float, bool, type(None))) for value in context.values())


@pytest.mark.asyncio
async def test_next_scheduler_cycle_uses_a_fresh_attempted_set(monkeypatch):
    enqueue = AsyncMock(return_value=True)
    monkeypatch.setattr(service, "enqueue_job", enqueue)

    await service._enqueue_company_report_jobs(object(), "spy", {7}, scheduler_attempted_asset_ids=set())
    await service._enqueue_company_report_jobs(object(), "spy", {7}, scheduler_attempted_asset_ids=set())

    assert enqueue.await_count == 2


@pytest.mark.asyncio
async def test_enqueue_exception_marks_only_the_attempted_target(monkeypatch):
    attempted = set()
    enqueue = AsyncMock(side_effect=RuntimeError("queue unavailable"))
    monkeypatch.setattr(service, "enqueue_job", enqueue)

    with pytest.raises(RuntimeError):
        await service._enqueue_company_report_jobs(object(), "spy", {7, 8}, scheduler_attempted_asset_ids=attempted)

    assert len(attempted) == 1



@pytest.mark.asyncio
async def test_oversized_stream_is_closed_without_parsing(monkeypatch):
    monkeypatch.setattr(service, "_MAX_OG_HTML_BYTES", 8)

    class TrackingStream(httpx.AsyncByteStream):
        def __init__(self): self.closed = False
        async def __aiter__(self): yield b"x" * 32
        async def aclose(self): self.closed = True

    stream = TrackingStream()
    async def handler(_request):
        return httpx.Response(200, headers={"content-type": "text/html"}, stream=stream)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        assert await service._extract_og_image("https://test/large", client=client) is None
    assert stream.closed


@pytest.mark.asyncio
async def test_recovery_uses_default_batch_limit_and_concurrency_four(monkeypatch):
    rows = [(index, f"https://example/{index}") for index in range(8)]
    result = type("Result", (), {"fetchall": lambda self: rows})()
    session = type("Session", (), {"execute": AsyncMock(return_value=result), "commit": AsyncMock()})()
    active = maximum = 0

    async def extract(_url, *, client, timeout=8.0):
        nonlocal active, maximum
        active += 1
        maximum = max(maximum, active)
        await asyncio.sleep(0)
        active -= 1
        return None

    monkeypatch.setattr(service, "_extract_og_image", extract)
    await service._recover_thumbnails(session)

    assert session.execute.await_args.args[1]["limit"] == 20
    assert maximum == 4



@pytest.mark.asyncio
async def test_per_ticker_ingestion_does_not_block_on_og_recovery(monkeypatch):
    class Article:
        def __init__(self, url):
            self.article_url = url
            self.thumbnail_url = None
            self.title = "title"; self.summary = "summary"
            self.finnhub_id = url; self.pub_date = None

    fake_client = type("FinnhubClient", (), {"company_news": lambda self, *_args, **_kwargs: [{}, {}]})()
    monkeypatch.setattr(finnhub_service, "_rate_limiter", AsyncMock())
    monkeypatch.setattr(service, "get_finnhub_client", lambda: fake_client)
    monkeypatch.setattr(service, "normalize_finnhub_article", lambda _raw, ticker: Article(f"https://example/{ticker}"))
    monkeypatch.setattr(service, "batch_ingest_articles", AsyncMock(return_value=service.ArticlePersistResult([], 2, 1)))
    monkeypatch.setattr(service.ticker_extractor, "extract", lambda **_kwargs: set())
    extract = AsyncMock()
    monkeypatch.setattr(service, "_extract_og_image", extract)

    assert await service.fetch_and_ingest_news("spy", object(), limit=2) == 0
    extract.assert_not_awaited()


def _provider_counters():
    return {
        "provider_requests": 0,
        "provider_successes": 0,
        "provider_timeouts": 0,
        "provider_failures": 0,
        "consecutive_timeouts": 0,
        "provider_timeout_breaker_open": False,
        "tickers_skipped_provider_timeout": 0,
    }


@pytest.mark.asyncio
async def test_finnhub_company_news_uses_to_thread(monkeypatch):
    calls = []

    class Client:
        def company_news(self, ticker, *, _from, to):
            calls.append((ticker, _from, to))
            return []

    async def to_thread(fn, *args, **kwargs):
        assert fn is service._fetch_finnhub_company_news
        return fn(*args, **kwargs)

    monkeypatch.setattr(finnhub_service, "_rate_limiter", AsyncMock())
    monkeypatch.setattr(service, "get_finnhub_client", lambda: Client())
    monkeypatch.setattr(service.asyncio, "to_thread", to_thread)
    counters = _provider_counters()
    state = {}

    assert await service.fetch_and_ingest_news(
        "spy", object(), _provider_counters=counters, _provider_state=state
    ) == 0

    assert calls and calls[0][0] == "SPY"
    assert counters["provider_requests"] == 1
    assert counters["provider_successes"] == 1
    assert state["last_outcome"] == "success"


@pytest.mark.asyncio
async def test_finnhub_blocking_call_does_not_block_event_loop(monkeypatch):
    started = threading.Event()
    release = threading.Event()

    class Client:
        def company_news(self, *_args, **_kwargs):
            started.set()
            release.wait(timeout=1)
            return []

    monkeypatch.setattr(finnhub_service, "_rate_limiter", AsyncMock())
    monkeypatch.setattr(service, "get_finnhub_client", lambda: Client())

    task = asyncio.create_task(service.fetch_and_ingest_news("spy", object()))
    for _ in range(20):
        if started.is_set():
            break
        await asyncio.sleep(0.01)

    advanced = asyncio.Event()

    async def heartbeat():
        await asyncio.sleep(0)
        advanced.set()

    heartbeat_task = asyncio.create_task(heartbeat())
    assert started.is_set() and not task.done()
    await asyncio.wait_for(advanced.wait(), timeout=0.1)
    assert not task.done()
    release.set()

    assert await task == 0
    await heartbeat_task


@pytest.mark.asyncio
async def test_timeout_breaker_stops_after_three_sequential_requests(monkeypatch):
    seen = []

    async def timeout_fetch(ticker, _session, **kwargs):
        seen.append(ticker)
        kwargs["_provider_counters"]["provider_requests"] += 1
        kwargs["_provider_counters"]["provider_timeouts"] += 1
        kwargs["_provider_state"]["last_outcome"] = "timeout"
        return 0

    monkeypatch.setattr(service, "fetch_and_ingest_news", timeout_fetch)
    monkeypatch.setattr(service.asyncio, "sleep", AsyncMock())
    counters = _provider_counters()

    result = await service.fetch_and_ingest_many(
        [f"T{i}" for i in range(16)], object(), _provider_counters=counters
    )

    assert list(result) == ["T0", "T1", "T2"]
    assert seen == ["T0", "T1", "T2"]
    assert counters["provider_requests"] == 3
    assert counters["provider_timeouts"] == 3
    assert counters["consecutive_timeouts"] == 3
    assert counters["provider_timeout_breaker_open"] is True
    assert counters["tickers_skipped_provider_timeout"] == 13


@pytest.mark.asyncio
async def test_success_resets_consecutive_timeout_count(monkeypatch):
    outcomes = iter(["timeout", "success", "timeout", "timeout"])

    async def fetch(ticker, _session, **kwargs):
        outcome = next(outcomes)
        kwargs["_provider_counters"]["provider_requests"] += 1
        kwargs["_provider_counters"][f"provider_{outcome}es" if outcome == "success" else "provider_timeouts"] += 1
        kwargs["_provider_state"]["last_outcome"] = outcome
        return 0

    monkeypatch.setattr(service, "fetch_and_ingest_news", fetch)
    monkeypatch.setattr(service.asyncio, "sleep", AsyncMock())
    counters = _provider_counters()

    await service.fetch_and_ingest_many(["A", "B", "C", "D"], object(), _provider_counters=counters)

    assert counters["provider_successes"] == 1
    assert counters["provider_timeouts"] == 3
    assert counters["consecutive_timeouts"] == 2
    assert counters["provider_timeout_breaker_open"] is False


@pytest.mark.asyncio
async def test_new_many_call_starts_with_fresh_timeout_state(monkeypatch):
    async def timeout_fetch(_ticker, _session, **kwargs):
        kwargs["_provider_counters"]["provider_requests"] += 1
        kwargs["_provider_counters"]["provider_timeouts"] += 1
        kwargs["_provider_state"]["last_outcome"] = "timeout"
        return 0

    monkeypatch.setattr(service, "fetch_and_ingest_news", timeout_fetch)
    monkeypatch.setattr(service.asyncio, "sleep", AsyncMock())

    first = _provider_counters()
    second = _provider_counters()
    await service.fetch_and_ingest_many(["A", "B", "C", "D"], object(), _provider_counters=first)
    await service.fetch_and_ingest_many(["E", "F", "G", "H"], object(), _provider_counters=second)

    assert first["tickers_skipped_provider_timeout"] == 1
    assert second["tickers_skipped_provider_timeout"] == 1
    assert second["consecutive_timeouts"] == 3


@pytest.mark.asyncio
async def test_non_timeout_provider_failure_does_not_open_breaker(monkeypatch):
    async def failing_fetch(_ticker, _session, **kwargs):
        kwargs["_provider_counters"]["provider_requests"] += 1
        kwargs["_provider_counters"]["provider_failures"] += 1
        kwargs["_provider_state"]["last_outcome"] = "failure"
        return 0

    monkeypatch.setattr(service, "fetch_and_ingest_news", failing_fetch)
    monkeypatch.setattr(service.asyncio, "sleep", AsyncMock())
    counters = _provider_counters()

    result = await service.fetch_and_ingest_many(["A", "B", "C", "D"], object(), _provider_counters=counters)

    assert len(result) == 4
    assert counters["provider_failures"] == 4
    assert counters["consecutive_timeouts"] == 0
    assert counters["provider_timeout_breaker_open"] is False


@pytest.mark.asyncio
async def test_provider_cancellation_propagates_without_failure_counter(monkeypatch):
    class Client:
        def company_news(self, *_args, **_kwargs):
            return []

    async def cancelled_to_thread(*_args, **_kwargs):
        raise asyncio.CancelledError()

    monkeypatch.setattr(finnhub_service, "_rate_limiter", AsyncMock())
    monkeypatch.setattr(service, "get_finnhub_client", lambda: Client())
    monkeypatch.setattr(service.asyncio, "to_thread", cancelled_to_thread)
    counters = _provider_counters()

    with pytest.raises(asyncio.CancelledError):
        await service.fetch_and_ingest_news("spy", object(), _provider_counters=counters)

    assert counters["provider_requests"] == 1
    assert counters["provider_timeouts"] == 0
    assert counters["provider_failures"] == 0


@pytest.mark.asyncio
async def test_zero_fetched_articles_skips_thumbnail_recovery(monkeypatch):
    monkeypatch.setattr(type(service.settings), "MEMORY_DIAGNOSTICS_ENABLED", property(lambda _self: False))
    monkeypatch.setattr(service, "fetch_and_ingest_many", AsyncMock(return_value={"SPY": 0}))
    recover = AsyncMock(return_value=0)
    monkeypatch.setattr(service, "_recover_thumbnails", recover)

    class SessionContext:
        async def __aenter__(self): return object()
        async def __aexit__(self, *_args): return False

    class Manager:
        broadcast = AsyncMock()

    async def stop_after_cycle(_):
        raise asyncio.CancelledError()

    monkeypatch.setattr(service.asyncio, "sleep", stop_after_cycle)
    with pytest.raises(asyncio.CancelledError):
        await service._scheduled_ingest_loop(lambda: SessionContext(), AsyncMock(return_value=["SPY"]), Manager())

    recover.assert_not_awaited()


def test_timeout_classifier_handles_requests_urllib3_and_chained_errors():
    assert service._is_finnhub_timeout(ReadTimeout("read timed out"))
    assert service._is_finnhub_timeout(ConnectTimeout("connect timed out"))
    assert service._is_finnhub_timeout(ReadTimeoutError(None, "host", "read timed out"))

    wrapped = RuntimeError("SDK wrapper")
    wrapped.__cause__ = ReadTimeout("read timed out")
    assert service._is_finnhub_timeout(wrapped)
    assert not service._is_finnhub_timeout(RuntimeError("unauthorized"))


@pytest.mark.asyncio
async def test_finnhub_requests_remain_sequential(monkeypatch):
    real_sleep = asyncio.sleep
    active = maximum = 0
    guard = threading.Lock()
    calls = []

    class Client:
        def company_news(self, ticker, **_kwargs):
            nonlocal active, maximum
            with guard:
                active += 1
                maximum = max(maximum, active)
                calls.append(ticker)
            time.sleep(0.02)
            with guard:
                active -= 1
            return []

    async def no_delay(_seconds):
        await real_sleep(0)

    monkeypatch.setattr(finnhub_service, "_rate_limiter", AsyncMock())
    monkeypatch.setattr(service, "get_finnhub_client", lambda: Client())
    monkeypatch.setattr(service.asyncio, "sleep", no_delay)

    result = await service.fetch_and_ingest_many(["spy", "qqq", "iwm"], object())

    assert result == {"SPY": 0, "QQQ": 0, "IWM": 0}
    assert calls == ["SPY", "QQQ", "IWM"]
    assert maximum == 1
