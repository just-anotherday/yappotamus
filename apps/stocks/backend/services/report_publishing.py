"""One-way report publishing. No cloud-to-local database connection is required."""
import asyncio
import hashlib
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from backend.config.database import async_session_factory
from backend.config.settings import settings
from backend.lib.timestamps import utc_now_naive
from backend.models.report import AnalysisReportModel
from backend.models.report_publication import ReportPublication, ReportPublicationReceipt

logger = logging.getLogger(__name__)
MAX_PUBLICATION_BYTES = 2 * 1024 * 1024
PUBLICATION_TIMEOUT = httpx.Timeout(20.0, connect=10.0, read=90.0)
PUBLICATION_ATTEMPT_SECONDS = 110
PUBLICATION_PASS_SECONDS = 240


async def _upload_report(client, url, body):
    """Allow a slow receiver and retry transient failures with the same UUID."""
    for attempt in range(2):
        try:
            # HTTPX read timeouts apply between chunks; also cap total elapsed time.
            async with asyncio.timeout(PUBLICATION_ATTEMPT_SECONDS):
                response = await client.put(
                    url, content=body,
                    headers={"Authorization": f"Bearer {settings.REPORT_PUBLISH_TOKEN}", "Content-Type": "application/json"},
                )
                response.raise_for_status()
                return response
        except (httpx.TransportError, TimeoutError):
            if attempt:
                raise
        except httpx.HTTPStatusError as exc:
            if attempt or exc.response.status_code not in {502, 503, 504}:
                raise
        await asyncio.sleep(2)


class PublishedReport(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    ticker: str = Field(pattern=r"^[A-Z][A-Z0-9.\-^=]{0,19}$")
    report_data: dict
    overall_sentiment: str = Field(min_length=1, max_length=20)
    confidence_score: int = Field(ge=0, le=100)
    articles_count: int = Field(ge=0)
    model_used: str = Field(max_length=50)
    prompt_version: str = Field(max_length=20)
    prompt_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    current_price_at_analysis: float | None = None
    created_at: datetime

    @field_validator("report_data")
    @classmethod
    def require_json_values(cls, value):
        # JSONB and the publication hash both require finite JSON values.
        try:
            json.dumps(value, allow_nan=False)
        except (ValueError, TypeError) as exc:
            raise ValueError("report_data requires finite JSON values") from exc
        return value

    @field_validator("created_at")
    @classmethod
    def require_utc(cls, value):
        if value.tzinfo is None:
            raise ValueError("created_at requires a timezone")
        return value.astimezone(timezone.utc)


def publishing_target() -> str:
    """Validate before using a destination or sending any credential."""
    value = settings.REPORT_PUBLISH_URL.rstrip("/")
    if not value:
        return ""
    parsed = urlsplit(value)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username
            or parsed.password or parsed.query or parsed.fragment or parsed.path not in {"", "/"}):
        raise ValueError("REPORT_PUBLISH_URL must be an HTTPS API origin without a path")
    if not settings.REPORT_PUBLISH_TOKEN or len(settings.REPORT_PUBLISH_TOKEN) < 32:
        raise ValueError("REPORT_PUBLISH_TOKEN must contain at least 32 characters")
    return value


def report_payload(report: AnalysisReportModel) -> dict:
    values = {key: getattr(report, key) for key in PublishedReport.model_fields}
    values["created_at"] = report.created_at.replace(tzinfo=report.created_at.tzinfo or timezone.utc)
    return PublishedReport(**values).model_dump(mode="json")


async def queue_report(session, report: AnalysisReportModel) -> None:
    target = publishing_target()
    if not target:
        return
    # Same transaction as the report. Rollbacks remove both together.
    await session.execute(insert(ReportPublication).values(
        id=uuid4(), report_id=report.id, target_url=target,
        payload=report_payload(report), attempts=0, next_attempt_at=utc_now_naive(),
    ).on_conflict_do_nothing(index_elements=[ReportPublication.report_id]))


async def receive_report(session, publication_id: UUID, payload: PublishedReport) -> dict:
    values = payload.model_dump(mode="json")
    digest = hashlib.sha256(json.dumps(values, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    receipt = (await session.execute(insert(ReportPublicationReceipt).values(
        id=publication_id, payload_hash=digest,
    ).on_conflict_do_nothing(index_elements=[ReportPublicationReceipt.id]).returning(ReportPublicationReceipt.id))).scalar_one_or_none()
    if receipt is None:
        existing = await session.get(ReportPublicationReceipt, publication_id)
        if existing.payload_hash != digest:
            from fastapi import HTTPException
            raise HTTPException(409, "Publication ID already belongs to another payload")
        return {"publication_id": str(publication_id), "report_id": existing.report_id, "status": "duplicate"}

    values["created_at"] = payload.created_at.replace(tzinfo=None)
    # Cloud IDs belong to the cloud; local article IDs are not database references here.
    values["report_data"] = {**values["report_data"], "report_id": None}
    report = AnalysisReportModel(**values)
    session.add(report)
    await session.flush()
    stored = await session.get(ReportPublicationReceipt, publication_id)
    stored.report_id = report.id
    return {"publication_id": str(publication_id), "report_id": report.id, "status": "published"}


async def publish_pending(*, session_factory=async_session_factory, transport=None, limit=50) -> dict:
    target = publishing_target()
    result = {"published": 0, "failed": 0}
    if not target:
        return result
    deadline = time.monotonic() + PUBLICATION_PASS_SECONDS
    async with httpx.AsyncClient(timeout=PUBLICATION_TIMEOUT, follow_redirects=False, transport=transport) as client:
        for _ in range(limit):
            if time.monotonic() >= deadline:
                break
            # Lock through acknowledgement: parallel local processes cannot send the same row.
            # If a process dies after remote commit, the next delivery uses the same UUID.
            async with session_factory() as session:
                async with session.begin():
                    item = (await session.execute(select(ReportPublication).where(
                        ReportPublication.published_at.is_(None),
                        ReportPublication.next_attempt_at <= utc_now_naive(),
                    ).order_by(ReportPublication.next_attempt_at).limit(1).with_for_update(skip_locked=True))).scalar_one_or_none()
                    if item is None:
                        break
                    item.attempts += 1
                    try:
                        if item.target_url != target:
                            raise ValueError("destination_changed")
                        body = json.dumps(item.payload, allow_nan=False).encode()
                        if len(body) > MAX_PUBLICATION_BYTES:
                            raise ValueError("payload_too_large")
                        response = await _upload_report(client,
                            f"{target}/api/internal/report-publications/{item.id}",
                            body,
                        )
                        ack = response.json()
                        if ack.get("publication_id") != str(item.id) or ack.get("status") not in {"published", "duplicate"}:
                            raise ValueError("invalid_acknowledgement")
                        remote_id = ack.get("report_id")
                        if remote_id is not None and (type(remote_id) is not int or remote_id < 1):
                            raise ValueError("invalid_report_id")
                        item.remote_report_id = remote_id
                        item.published_at = utc_now_naive()
                        item.last_error = None
                        result["published"] += 1
                    except (httpx.HTTPError, TimeoutError, ValueError, TypeError, AttributeError) as exc:
                        # Never persist/log response bodies, URLs, tokens, or report text.
                        item.last_error = f"http_{exc.response.status_code}" if isinstance(exc, httpx.HTTPStatusError) else type(exc).__name__
                        item.next_attempt_at = utc_now_naive() + timedelta(seconds=min(3600, 30 * 2 ** min(item.attempts - 1, 7)))
                        result["failed"] += 1
                        # An unavailable receiver or credential affects every report.
                        # Commit this retry and let the next pass handle the backlog.
                        if isinstance(exc, (httpx.HTTPError, TimeoutError)):
                            break
    return result


async def publishing_loop():
    while True:
        try:
            result = await publish_pending()
            if result["published"] or result["failed"]:
                logger.info("[Report publishing] published=%d failed=%d", result["published"], result["failed"])
        except Exception as exc:
            logger.warning("[Report publishing] pass failed: %s", type(exc).__name__)
        await asyncio.sleep(30)
