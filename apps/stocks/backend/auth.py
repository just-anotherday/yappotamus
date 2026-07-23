"""Single-user access token authentication.

Lightweight Bearer-token gate for a single-user portfolio deployment.
Not a user account system, not OAuth/JWT - just a shared password that
protects the API (and therefore AI generation costs) from public access.

Supports multiple configured tokens via ``APP_ACCESS_TOKEN`` and
``APP_ACCESS_TOKENS`` environment variables.

Usage:
    from backend.auth import verify_app_access_token, is_valid_access_token

    app.include_router(some_router, dependencies=[Depends(verify_app_access_token)])
"""

import secrets

from fastapi import Header, HTTPException

from backend.config.settings import settings


def is_valid_access_token(token: str) -> bool:
    """Check whether *token* matches any configured access token.

    Rejects non-string and empty submitted values.  Compares each
    configured token using ``secrets.compare_digest`` so the check is
    constant-time and case-sensitive.  Returns ``False`` when no tokens
    are configured (fail-closed).
    """
    if not isinstance(token, str) or not token:
        return False

    matched = False

    for configured in settings.APP_ACCESS_TOKENS:
        comparison = secrets.compare_digest(token, configured)
        matched = matched or comparison

    return matched


async def verify_app_access_token(authorization: str | None = Header(None)) -> None:
    """FastAPI dependency: requires ``Authorization: Bearer <token>``."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    token = authorization[len("Bearer "):].strip()
    if not is_valid_access_token(token):
        raise HTTPException(status_code=401, detail="Invalid access token")
