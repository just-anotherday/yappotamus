"""Dedicated maintenance authentication, separate from browser access."""

import secrets

from fastapi import Header, HTTPException

from backend.config.settings import settings


async def verify_maintenance_token(authorization: str | None = Header(None)) -> None:
    if not settings.MAINTENANCE_API_ENABLED:
        raise HTTPException(404, "Maintenance API is disabled")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing or invalid maintenance authorization")
    token = authorization.removeprefix("Bearer ").strip()
    if not secrets.compare_digest(token, settings.MAINTENANCE_API_TOKEN or ""):
        raise HTTPException(401, "Invalid maintenance credential")