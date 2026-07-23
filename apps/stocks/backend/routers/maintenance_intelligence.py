"""Dedicated maintenance APIs; never authenticated with browser credentials."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.routing import APIRoute
from starlette.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config.database import get_async_session
from backend.config.settings import settings
from backend.maintenance.auth import verify_maintenance_token
from backend.maintenance.article_intelligence.contracts import ExportSessionCreate, ImportBatchRequest
from backend.maintenance.article_intelligence.prompts import PromptCompatibilityRegistry
from backend.maintenance.article_intelligence.services import MaintenanceExportService, MaintenanceImportService
from backend.models.maintenance import ArticleIntelligenceMaintenanceBatch as Batch

class MaintenanceSizeLimitedRoute(APIRoute):
    def get_route_handler(self):
        original = super().get_route_handler()

        async def limited(request: Request) -> Response:
            content_length = request.headers.get("content-length")
            try:
                declared_size = int(content_length) if content_length else 0
            except ValueError:
                raise HTTPException(400, "Invalid Content-Length header") from None
            if declared_size > settings.MAINTENANCE_MAX_REQUEST_BYTES:
                raise HTTPException(413, "Maintenance request body is too large")
            if request.method in {"POST", "PUT", "PATCH"}:
                body = await request.body()
                if len(body) > settings.MAINTENANCE_MAX_REQUEST_BYTES:
                    raise HTTPException(413, "Maintenance request body is too large")
            return await original(request)

        return limited


router = APIRouter(prefix="/api/maintenance/article-intelligence/v1", tags=["maintenance"],
                   dependencies=[Depends(verify_maintenance_token)], route_class=MaintenanceSizeLimitedRoute)


@router.get("/prompt-compatibility")
async def prompt_compatibility():
    return PromptCompatibilityRegistry().compatibility()


@router.post("/export-sessions", status_code=201)
async def create_export(request: ExportSessionCreate, session: AsyncSession = Depends(get_async_session)):
    try:
        batch = await MaintenanceExportService(session).create(request)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"schema_version": batch.schema_version, "batch_id": batch.id, "state": batch.state,
            "exported_count": batch.exported_count, "expires_at": batch.expires_at}


@router.get("/export-sessions/{batch_id}")
async def export_status(batch_id: UUID, session: AsyncSession = Depends(get_async_session)):
    batch = await session.get(Batch, batch_id)
    if not batch: raise HTTPException(404, "export session not found")
    return {"batch_id": batch.id, "state": batch.state, "exported_count": batch.exported_count,
            "expires_at": batch.expires_at}


@router.get("/export-sessions/{batch_id}/items")
async def export_items(batch_id: UUID, offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=50),
                       session: AsyncSession = Depends(get_async_session)):
    if not await session.get(Batch, batch_id): raise HTTPException(404, "export session not found")
    return {"batch_id": batch_id, "offset": offset, "items": await MaintenanceExportService(session).items(batch_id, offset, limit)}


async def _publish(request: ImportBatchRequest, dry_run: bool, session: AsyncSession):
    try:
        batch, outcomes = await MaintenanceImportService(session).publish(
            request.batch_id, request.client_publish_id, request.artifacts, dry_run=dry_run,
        )
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"schema_version": request.schema_version, "batch_id": batch.id,
            "client_publish_id": request.client_publish_id, "dry_run": dry_run, "outcomes": outcomes}


@router.post("/imports/dry-run")
async def dry_run_import(request: ImportBatchRequest, session: AsyncSession = Depends(get_async_session)):
    return await _publish(request, True, session)


@router.post("/imports")
async def publish_import(request: ImportBatchRequest, session: AsyncSession = Depends(get_async_session)):
    return await _publish(request, False, session)