"""Machine publishing is separate from owner-only report viewing."""
import secrets
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import ValidationError
from sqlalchemy import func, select

from backend.auth import verify_app_access_token
from backend.config.database import get_async_session
from backend.config.settings import settings
from backend.models.report_publication import ReportPublication
from backend.services.report_publishing import MAX_PUBLICATION_BYTES, PublishedReport, receive_report

router = APIRouter(tags=["report publishing"])


async def verify_publishing_token(authorization: str | None = Header(None)):
    configured = settings.REPORT_PUBLISH_TOKEN
    if len(configured) < 32:
        raise HTTPException(503, "Report publishing is not configured")
    supplied = authorization[7:] if authorization and authorization.startswith("Bearer ") else ""
    if not supplied or not secrets.compare_digest(supplied.encode(), configured.encode()):
        raise HTTPException(401, "Invalid publishing credential")


@router.put("/api/internal/report-publications/{publication_id}", dependencies=[Depends(verify_publishing_token)])
async def import_report(publication_id: UUID, request: Request, session=Depends(get_async_session)):
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > MAX_PUBLICATION_BYTES:
            raise HTTPException(413, "Report exceeds publishing size limit")
    try:
        payload = PublishedReport.model_validate_json(bytes(body))
    except ValidationError:
        raise HTTPException(422, "Invalid report publication payload") from None
    result = await receive_report(session, publication_id, payload)
    await session.commit()
    return result


@router.get("/api/analysis/publishing/status", dependencies=[Depends(verify_app_access_token)])
async def publishing_status(session=Depends(get_async_session)):
    counts = (await session.execute(select(
        func.count().filter(ReportPublication.published_at.is_(None)).label("pending"),
        func.count().filter(ReportPublication.published_at.is_not(None)).label("published"),
        func.count().filter(ReportPublication.published_at.is_(None), ReportPublication.attempts > 0).label("retrying"),
        func.max(ReportPublication.published_at).label("last_published_at"),
    ))).one()._mapping
    from backend.lib.timestamps import utc_isoformat
    return {**dict(counts), "enabled": bool(settings.REPORT_PUBLISH_URL),
            "last_published_at": utc_isoformat(counts["last_published_at"])}
