"""Centralized exception handlers for consistent API error responses."""

import logging
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from backend.services.ai.exceptions import AIConnectionError, AIValidationError

logger = logging.getLogger(__name__)


def register_exception_handlers(app):
    """Register global exception handlers on the FastAPI app.

    All errors return a consistent JSON envelope:
        { "error": "<message>", "status_code": <int> }
    """

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        logger.warning(
            f"[Validation] {request.method} {request.url}: {exc.errors()}"
        )
        return JSONResponse(
            status_code=422,
            content={
                "error": "Request validation failed",
                "details": exc.errors(),
                "status_code": 422,
            },
        )

    @app.exception_handler(AIValidationError)
    async def ai_validation_exception_handler(request: Request, exc: AIValidationError):
        logger.warning(
            f"[AI][Validation] {request.method} {request.url}: {exc.message}"
        )
        return JSONResponse(
            status_code=400,
            content={"error": exc.message, "status_code": 400},
        )

    @app.exception_handler(AIConnectionError)
    async def ai_connection_exception_handler(request: Request, exc: AIConnectionError):
        logger.error(
            f"[AI][Connection] {request.method} {request.url}: {exc.message}"
        )
        return JSONResponse(
            status_code=503,
            content={"error": exc.message, "status_code": 503},
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        # Log 5xx server errors, warn on 4xx client errors
        if exc.status_code >= 500:
            logger.error(
                f"[HTTP] {exc.status_code} on {request.method} {request.url}: {exc.detail}"
            )
        else:
            logger.warning(
                f"[HTTP] {exc.status_code} on {request.method} {request.url}: {exc.detail}"
            )
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.detail, "status_code": exc.status_code},
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception):
        logger.error(
            f"[Unhandled] {request.method} {request.url}: {type(exc).__name__}: {exc}",
            exc_info=True,
        )
        return JSONResponse(
            status_code=500,
            content={
                "error": "Internal server error",
                "status_code": 500,
            },
        )
