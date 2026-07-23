"""Single-user access token authentication.

Lightweight Bearer-token gate for a single-user portfolio deployment.
Not a user account system, not OAuth/JWT - just a shared password that
protects the API (and therefore AI generation costs) from public access.

Usage:
    from backend.auth import verify_app_access_token

    app.include_router(some_router, dependencies=[Depends(verify_app_access_token)])
"""

import secrets

from fastapi import Header, HTTPException

from backend.config.settings import settings


async def verify_app_access_token(authorization: str | None = Header(None)) -> None:
    """FastAPI dependency: requires `Authorization: Bearer <APP_ACCESS_TOKEN>`."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    token = authorization[len("Bearer "):].strip()
    if not secrets.compare_digest(token, settings.APP_ACCESS_TOKEN or ""):
        raise HTTPException(status_code=401, detail="Invalid access token")
