"""Authenticated machine-to-machine operational job triggers."""

import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.auth import verify_internal_job_token
from backend.config.database import async_session_factory
from backend.services.news_ingestion_service import fetch_and_ingest_watchlist_once

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/internal/jobs", tags=["internal-jobs"])


@router.post("/news-ingest", dependencies=[Depends(verify_internal_job_token)])
async def ingest_news_once(
    force: bool = Query(False),
    trigger_kind: Literal["auto", "hourly", "quarter_hour"] = Query("auto"),
):
    """Execute the externally scheduled one-shot watchlist news collection."""
    try:
        summary = await fetch_and_ingest_watchlist_once(
            async_session_factory,
            force=force,
            trigger_kind=trigger_kind,
        )
        if summary.get("status") == "partial":
            # 424 makes the workflow fail without asking curl to immediately
            # replay a full provider fan-out after a partial dependency result.
            raise HTTPException(status_code=424, detail=summary)
        if summary.get("status") == "skipped_overlap":
            # Do not let a curl retry turn an earlier timed-out request into an
            # apparent success while that request still owns the durable lease.
            raise HTTPException(status_code=409, detail=summary)
        return summary
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("[InternalJob] job=news-ingest failed exception_type=%s", type(exc).__name__, exc_info=True)
        raise HTTPException(status_code=503, detail="News ingestion job failed") from exc
