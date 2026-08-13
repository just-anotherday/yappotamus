"""Authenticated machine-to-machine operational job triggers."""

import logging

from fastapi import APIRouter, Depends, HTTPException

from backend.auth import verify_internal_job_token
from backend.config.database import async_session_factory
from backend.services.news_ingestion_service import fetch_and_ingest_watchlist_once

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/internal/jobs", tags=["internal-jobs"])


@router.post("/news-ingest", dependencies=[Depends(verify_internal_job_token)])
async def ingest_news_once():
    """Execute the externally scheduled one-shot watchlist news collection."""
    try:
        return await fetch_and_ingest_watchlist_once(async_session_factory)
    except Exception as exc:
        logger.error("[InternalJob] job=news-ingest failed exception_type=%s", type(exc).__name__, exc_info=True)
        raise HTTPException(status_code=503, detail="News ingestion job failed") from exc
