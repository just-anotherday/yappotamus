"""Publishing boundary tests; opt-in PostgreSQL delivery tests use isolated schemas."""
import asyncio
import os
from datetime import timedelta
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from dotenv import dotenv_values
from fastapi import FastAPI
from pydantic import ValidationError
from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.config.database import Base, get_async_session
from backend.lib.timestamps import utc_now_naive
from backend.models.report import AnalysisReportModel
from backend.models.report_publication import ReportPublication, ReportPublicationReceipt
from backend.routers import report_publications as routes
from backend.services import report_publishing as publishing
from backend.services.report_service import create_report

TOKEN = "publishing-test-secret-" + "x" * 32
ORIGIN = "https://cloud.example.test"


def payload():
    return publishing.PublishedReport(
        ticker="AMD", report_data={"executive_summary": "Test report", "articles_used": [], "report_id": 999},
        overall_sentiment="Neutral", confidence_score=50, articles_count=0,
        model_used="test-local-model", prompt_version="3.0", prompt_hash="a" * 64,
        created_at="2026-10-29T20:30:00-04:00",
    )


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch):
    monkeypatch.setenv("REPORT_PUBLISH_TOKEN", TOKEN)
    monkeypatch.setenv("REPORT_PUBLISH_URL", "")


@pytest.mark.parametrize("url", ["http://cloud.test", "https://user:pass@cloud.test", "https://cloud.test/path", "https://cloud.test?token=bad", "https://cloud.test/#fragment"])
def test_unsafe_destination_is_rejected(monkeypatch, url):
    monkeypatch.setenv("REPORT_PUBLISH_URL", url)
    with pytest.raises(ValueError):
        publishing.publishing_target()


def test_destination_requires_dedicated_strong_credential(monkeypatch):
    monkeypatch.setenv("REPORT_PUBLISH_URL", ORIGIN)
    monkeypatch.setenv("REPORT_PUBLISH_TOKEN", "short")
    with pytest.raises(ValueError):
        publishing.publishing_target()


def test_timestamp_normalization_and_payload_validation():
    assert payload().created_at.isoformat() == "2026-10-30T00:30:00+00:00"
    values = payload().model_dump(mode="json")
    for change in ({"created_at": "2026-10-30T00:30:00"}, {"confidence_score": 101}, {"unexpected": "field"}, {"report_data": {"invalid": float("nan")}}):
        with pytest.raises(ValidationError):
            publishing.PublishedReport(**{**values, **change})


@pytest.mark.asyncio
async def test_disabled_publishing_never_opens_a_connection():
    def forbidden():
        raise AssertionError("Disabled publishing touched the database")
    assert await publishing.publish_pending(session_factory=forbidden) == {"published": 0, "failed": 0}


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["timeout", "connection", 502, 503, 504])
async def test_upload_retries_transient_failure_with_identical_request(monkeypatch, failure):
    calls = []
    pause = AsyncMock()
    monkeypatch.setattr(publishing.asyncio, "sleep", pause)

    def receiver(request):
        calls.append(request)
        assert request.extensions["timeout"]["read"] == 90
        assert request.extensions["timeout"]["connect"] == 10
        if len(calls) == 1:
            if failure == "timeout":
                raise httpx.ReadTimeout("slow receiver", request=request)
            if failure == "connection":
                raise httpx.ConnectError("unavailable", request=request)
            return httpx.Response(failure)
        return httpx.Response(200, json={"status": "published"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(receiver), timeout=publishing.PUBLICATION_TIMEOUT) as client:
        response = await publishing._upload_report(client, ORIGIN + "/api/internal/report-publications/" + str(uuid4()), b'{"report":"test"}')
    assert response.status_code == 200 and len(calls) == 2
    assert calls[0].url == calls[1].url and calls[0].content == calls[1].content
    pause.assert_awaited_once_with(2)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [307, 401, 403, 409, 422])
async def test_upload_does_not_retry_permanent_errors_or_follow_redirects(status):
    calls = []

    def receiver(request):
        calls.append(request)
        return httpx.Response(status, headers={"Location": "https://other.example.test"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(receiver), follow_redirects=False) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await publishing._upload_report(client, ORIGIN, b"test")
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_upload_total_timeout_is_bounded_and_retried_once(monkeypatch):
    calls = []
    monkeypatch.setattr(publishing, "PUBLICATION_ATTEMPT_SECONDS", 0.01)
    monkeypatch.setattr(publishing.asyncio, "sleep", AsyncMock())

    async def stalled(request):
        calls.append(request)
        await asyncio.Event().wait()

    async with httpx.AsyncClient(transport=httpx.MockTransport(stalled)) as client:
        with pytest.raises(TimeoutError):
            await publishing._upload_report(client, ORIGIN, b"test")
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_machine_auth_does_not_accept_owner_or_job_tokens(monkeypatch):
    from fastapi import HTTPException
    for supplied in (None, "Bearer test-app-token", "Bearer test-maintenance-token", "Bearer wrong"):
        with pytest.raises(HTTPException) as exc:
            await routes.verify_publishing_token(supplied)
        assert exc.value.status_code == 401
    await routes.verify_publishing_token("Bearer " + TOKEN)
    monkeypatch.setenv("REPORT_PUBLISH_TOKEN", "")
    with pytest.raises(HTTPException) as exc:
        await routes.verify_publishing_token("Bearer " + TOKEN)
    assert exc.value.status_code == 503


@pytest_asyncio.fixture
async def databases(monkeypatch):
    if os.getenv("RUN_REPORT_PUBLISH_DB_TESTS") != "1":
        pytest.skip("Set RUN_REPORT_PUBLISH_DB_TESTS=1 for isolated PostgreSQL delivery tests")
    values = dotenv_values(Path(__file__).resolve().parents[1] / ".env")
    url = os.getenv("REPORT_PUBLISH_TEST_DATABASE_URL") or values.get("DATABASE_URL")
    assert url, "A PostgreSQL integration database is required"
    url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    engine = create_async_engine(url, connect_args={"timeout": 5})
    schemas = ["publish_test_" + uuid4().hex for _ in range(2)]
    factories = []
    tables = [AnalysisReportModel.__table__, ReportPublication.__table__, ReportPublicationReceipt.__table__]
    created = []
    try:
        for schema in schemas:
            async with engine.begin() as connection:
                await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            created.append(schema)
            bound = engine.execution_options(schema_translate_map={None: schema})
            async with bound.begin() as connection:
                await connection.run_sync(lambda sync: Base.metadata.create_all(sync, tables=tables))
            factories.append(async_sessionmaker(bound, expire_on_commit=False))
        local, cloud = factories

        async def cloud_session():
            async with cloud() as session:
                yield session

        app = FastAPI()
        app.include_router(routes.router)
        app.dependency_overrides[get_async_session] = cloud_session
        monkeypatch.setenv("REPORT_PUBLISH_URL", ORIGIN)
        yield local, cloud, app
    finally:
        for schema in reversed(created):
            assert schema.startswith("publish_test_") and len(schema) == 45
            async with engine.begin() as connection:
                await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await engine.dispose()


async def enqueue(factory):
    async with factory() as session:
        values = payload()
        report_id = await create_report(
            session, values.ticker, values.report_data, values.articles_count,
            values.model_used, values.prompt_version, values.prompt_hash,
        )
        report = await session.get(AnalysisReportModel, report_id)
        # Freeze the original generation time for timestamp assertions.
        report.created_at = values.created_at.replace(tzinfo=None)
        item = await session.scalar(select(ReportPublication))
        item.payload = publishing.report_payload(report)
        await publishing.queue_report(session, report)
        await session.commit()
        return report.id


async def due_now(factory):
    async with factory() as session:
        item = await session.scalar(select(ReportPublication))
        item.next_attempt_at = utc_now_naive() - timedelta(seconds=1)
        await session.commit()


@pytest.mark.asyncio
async def test_delivery_lost_ack_retry_and_cloud_visibility(databases):
    local, cloud, app = databases
    await enqueue(local)
    asgi = httpx.ASGITransport(app)

    async def lost_ack(request):
        async with httpx.AsyncClient(transport=asgi, base_url=ORIGIN) as client:
            response = await client.send(request)
            assert response.status_code == 200
        raise httpx.ReadTimeout("Lost response", request=request)

    assert await publishing.publish_pending(session_factory=local, transport=httpx.MockTransport(lost_ack)) == {"published": 0, "failed": 1}
    async with local() as session:
        item = await session.scalar(select(ReportPublication))
        assert item.published_at is None and item.attempts == 1
        assert item.next_attempt_at > utc_now_naive()
    await due_now(local)
    assert await publishing.publish_pending(session_factory=local, transport=asgi) == {"published": 1, "failed": 0}
    async with cloud() as session:
        assert await session.scalar(select(func.count()).select_from(AnalysisReportModel)) == 1
        row = await session.scalar(select(AnalysisReportModel))
        assert row.ticker == "AMD" and row.prompt_hash == "a" * 64
        assert row.created_at.isoformat() == "2026-10-30T00:30:00"
        assert row.report_data["report_id"] is None
    async with local() as session:
        assert await session.scalar(select(func.count()).select_from(ReportPublication)) == 1
        item = await session.scalar(select(ReportPublication))
        assert item.published_at and item.last_error is None


@pytest.mark.asyncio
async def test_lost_ack_recovers_in_same_pass_without_duplicate(databases, monkeypatch):
    local, cloud, app = databases
    await enqueue(local)
    asgi = httpx.ASGITransport(app)
    calls = []
    monkeypatch.setattr(publishing.asyncio, "sleep", AsyncMock())

    async def receiver(request):
        calls.append(request)
        async with httpx.AsyncClient(transport=asgi, base_url=ORIGIN) as client:
            response = await client.send(request)
        if len(calls) == 1:
            raise httpx.ReadTimeout("Lost acknowledgement", request=request)
        return response

    assert await publishing.publish_pending(session_factory=local, transport=httpx.MockTransport(receiver)) == {"published": 1, "failed": 0}
    assert len(calls) == 2 and calls[0].url == calls[1].url
    async with cloud() as session:
        assert await session.scalar(select(func.count()).select_from(AnalysisReportModel)) == 1


@pytest.mark.asyncio
async def test_rollback_does_not_leave_publication(databases):
    local, _, _ = databases
    async with local() as session:
        values = payload().model_dump()
        values["created_at"] = values["created_at"].replace(tzinfo=None)
        report = AnalysisReportModel(**values)
        session.add(report)
        await session.flush()
        await publishing.queue_report(session, report)
        await session.rollback()
    async with local() as session:
        assert await session.scalar(select(func.count()).select_from(ReportPublication)) == 0
        assert await session.scalar(select(func.count()).select_from(AnalysisReportModel)) == 0


@pytest.mark.asyncio
async def test_receiver_auth_size_conflicts_and_deletion_receipts(databases):
    _, cloud, app = databases
    key = uuid4()
    path = f"/api/internal/report-publications/{key}"
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url=ORIGIN) as client:
        body = payload().model_dump(mode="json")
        assert (await client.put(path, json=body)).status_code == 401
        headers = {"Authorization": "Bearer " + TOKEN}
        assert (await client.put(path, content=b"x" * (publishing.MAX_PUBLICATION_BYTES + 1), headers=headers)).status_code == 413
        assert (await client.put(path, json={"bad": "data"}, headers=headers)).status_code == 422
        first = await client.put(path, json=body, headers=headers)
        assert first.status_code == 200
        assert (await client.put(path, json={**body, "ticker": "NVDA"}, headers=headers)).status_code == 409
        async with cloud() as session:
            await session.execute(delete(AnalysisReportModel))
            await session.commit()
        retry = await client.put(path, json=body, headers=headers)
        assert retry.json()["status"] == "duplicate" and retry.json()["report_id"] is None
        async with cloud() as session:
            assert await session.scalar(select(func.count()).select_from(AnalysisReportModel)) == 0


@pytest.mark.asyncio
async def test_parallel_senders_do_not_duplicate_reports(databases):
    local, cloud, app = databases
    await enqueue(local)
    await asyncio.gather(*(publishing.publish_pending(session_factory=local, transport=httpx.ASGITransport(app)) for _ in range(2)))
    async with cloud() as session:
        assert await session.scalar(select(func.count()).select_from(AnalysisReportModel)) == 1


@pytest.mark.asyncio
async def test_redirect_and_changed_target_do_not_leak_credentials(databases, monkeypatch):
    local, _, _ = databases
    await enqueue(local)
    calls = []
    def redirect(request):
        calls.append(request)
        return httpx.Response(307, headers={"Location": "https://other.example.test"})
    result = await publishing.publish_pending(session_factory=local, transport=httpx.MockTransport(redirect))
    assert result["failed"] == 1 and len(calls) == 1
    assert calls[0].url.host == "cloud.example.test"
    await due_now(local)
    monkeypatch.setenv("REPORT_PUBLISH_URL", "https://other.example.test")
    assert (await publishing.publish_pending(session_factory=local, transport=httpx.MockTransport(redirect)))["failed"] == 1
    assert len(calls) == 1
