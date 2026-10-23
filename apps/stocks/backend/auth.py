"""Owner-only Supabase authentication and legacy local shared-token access.

AUTH_PROVIDER selects one mode; Supabase mode never accepts legacy app tokens.
The dedicated internal-job credential stays independent of user authentication.

Usage:
    from backend.auth import verify_app_access_token, is_valid_access_token

    app.include_router(some_router, dependencies=[Depends(verify_app_access_token)])
"""

import secrets
import httpx

from fastapi import Header, HTTPException

from backend.config.settings import settings


def is_valid_access_token(token: str) -> bool:
    """Check whether *token* matches any configured access token.

    Rejects non-string and empty submitted values.  Compares each
    configured token using ``secrets.compare_digest`` so the check is
    constant-time and case-sensitive.  Returns ``False`` when no tokens
    are configured (fail-closed).
    """
    if settings.AUTH_PROVIDER != "token" or not isinstance(token, str) or not token or not token.isascii():
        return False

    matched = False

    for configured in settings.APP_ACCESS_TOKENS:
        comparison = secrets.compare_digest(token.encode(), configured.encode())
        matched = matched or comparison

    return matched


async def verify_user_access_token(token: str) -> None:
    """Validate a user with Supabase itself, then enforce the owner allowlist.

    No locally decoded JWT fields are trusted. Legacy tokens are never accepted
    in Supabase mode, even if the old environment variables still exist.
    """
    if not isinstance(token, str) or not token or not token.isascii() or any(ord(c) < 32 or ord(c) == 127 for c in token):
        raise HTTPException(status_code=401, detail="Invalid access token")
    if settings.AUTH_PROVIDER == "token":
        if not is_valid_access_token(token):
            raise HTTPException(status_code=401, detail="Invalid access token")
        return
    if settings.AUTH_PROVIDER != "supabase" or not all((
        settings.SUPABASE_URL, settings.SUPABASE_PUBLISHABLE_KEY,
        settings.SUPABASE_ALLOWED_USER_ID,
    )):
        raise HTTPException(status_code=503, detail="Authentication is not configured")
    if not token:
        raise HTTPException(status_code=401, detail="Invalid access token")
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=False) as client:
            response = await client.get(
                f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1/user",
                headers={"apikey": settings.SUPABASE_PUBLISHABLE_KEY,
                         "Authorization": f"Bearer {token}"},
            )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="Authentication service unavailable") from exc
    if response.status_code in {401, 403}:
        raise HTTPException(status_code=401, detail="Session expired or invalid")
    if response.status_code != 200:
        raise HTTPException(status_code=503, detail="Authentication service unavailable")
    try:
        user = response.json()
    except ValueError as exc:
        raise HTTPException(status_code=503, detail="Authentication service unavailable") from exc
    if not isinstance(user, dict) or not user.get("id"):
        raise HTTPException(status_code=503, detail="Authentication service unavailable")
    if user["id"] != settings.SUPABASE_ALLOWED_USER_ID or user.get("is_anonymous", False):
        raise HTTPException(status_code=403, detail="This account does not have access")


async def verify_app_access_token(authorization: str | None = Header(None)) -> None:
    """FastAPI dependency: requires ``Authorization: Bearer <token>``."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    token = authorization[len("Bearer "):].strip()
    await verify_user_access_token(token)


async def verify_internal_job_token(authorization: str | None = Header(None)) -> None:
    """Require the dedicated machine-to-machine job token, fail closed if absent."""
    configured = settings.INTERNAL_JOB_TOKEN
    if not configured:
        raise HTTPException(status_code=503, detail="Internal job trigger is not configured")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    supplied = authorization[len("Bearer "):].strip()
    if not supplied.isascii() or not secrets.compare_digest(supplied.encode(), configured.encode()):
        raise HTTPException(status_code=401, detail="Invalid internal job token")
