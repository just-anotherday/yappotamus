"""Minimal single-user authentication verification endpoint."""

from fastapi import APIRouter


router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/verify")
async def verify_access():
    """Confirm the router-level Bearer dependency accepted the request.

    This endpoint intentionally performs no database or provider I/O and exposes
    no environment values or credentials.
    """
    return {"authenticated": True}