"""FastAPI Application Entry Point — YapVibes Backend

Lifespan events handle startup/shutdown lifecycle for:
  - Database initialization
  - Watchlist seeding + asset sync
  - Market data WebSocket service
  - News ingestion scheduler (every 15 min)
  - AI Worker (background job processor)
"""

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Literal

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from backend.auth import verify_app_access_token
from backend.config.settings import settings
from backend.config.database import init_db, async_session_factory, sanitize_database_error
from backend.services.market_data_service import MarketDataService, set_event_loop
from backend.services.watchlist_service import seed_defaults, get_all_tickers
from backend.services.connection_manager import ConnectionManager
from backend.services.news_ingestion_service import start_scheduler, stop_scheduler
from backend.services.ai_worker import AIWorker, enqueue_job, _daily_market_report_loop
from backend.services.asset_sync import sync_watchlist_to_assets
from backend.services.post_market_service import _post_market_fetch_loop
from backend.services.ticker_extractor import ticker_extractor
from backend.services.yfinance_cache import configure_yfinance_cache
from backend.services.hybrid_data_service import shutdown_hybrid_data_service
from backend.services.market_data_observability import (
    market_data_correlation,
    normalize_correlation_id,
)
from backend.services.memory_diagnostics import log_memory
from backend.exceptions import _configured_cors_headers, register_exception_handlers

from backend.routers import stock as stock_router
from backend.routers import watchlist as watchlist_router
from backend.routers import news as news_router
from backend.routers import websocket as websocket_router
from backend.routers import analysis as analysis_router
from backend.routers import analysis_reports as analysis_reports_router
from backend.routers import markets as markets_router
from backend.routers import auth as auth_router
from backend.routers import intelligence as intelligence_router
from backend.routers import maintenance_intelligence as maintenance_intelligence_router
from backend.routers import internal_jobs as internal_jobs_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Suppress noisy third-party logs (uvicorn connection churn, watchfiles, etc.)
for _noisy_logger in ("uvicorn.error", "uvicorn.access", "watchfiles.main"):
    logging.getLogger(_noisy_logger).setLevel(logging.WARNING)

# ---------- Centralized environment validation (fail-fast on missing required env vars) ----------
settings.validate()

# CORS middleware for Next.js frontend (env-based origins)
allow_origins_list = settings.CORS_ORIGINS

# ---------- Rate Limiting config ----------
_RATE_LIMIT_WINDOW = settings.RATE_LIMIT_WINDOW_S
_RATE_LIMIT_MAX_REQS = settings.RATE_LIMIT_MAX_REQUESTS
_rate_limit_store: dict[str, list[float]] = {}
_rate_limit_lock = asyncio.Lock()


class HealthLiveResponse(BaseModel):
    """Lightweight process health plus optional deployment provenance."""

    status: Literal["healthy"] = "healthy"
    git_commit: str | None = None
    git_branch: str | None = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan context manager for startup/shutdown."""

    # ---- Startup ----
    configure_yfinance_cache()
    set_event_loop(asyncio.get_running_loop())

    # Initialize PostgreSQL tables
    try:
        await init_db()
        logger.info("[Startup] PostgreSQL database initialized.")
    except Exception as e:
        logger.warning("[Startup] Database initialization failed: %s", e)

    # Seed watchlist defaults if table is empty
    try:
        async with async_session_factory() as session:
            await seed_defaults(session)
        logger.info("[Startup] Watchlist table seeded (or already populated).")
    except Exception as e:
        logger.warning("[Startup] Failed to seed watchlist: %s", e)

    # Load actual watchlist tickers from DB and subscribe to WebSocket
    db_tickers = []
    try:
        async with async_session_factory() as session:
            db_tickers = await get_all_tickers(session)
        logger.info("[Startup] Loaded %d tickers from watchlist DB: %s", len(db_tickers), db_tickers)

        # Sync watchlist tickers to Asset entities
        try:
            async with async_session_factory() as session:
                created = await sync_watchlist_to_assets(session, db_tickers)
            logger.info("[Startup] Asset sync complete: %d asset records processed.", created)
        except Exception as e:
            logger.warning("[Startup] Asset sync failed (non-fatal): %s", e)

        # Load ticker cache for extractor
        try:
            async with async_session_factory() as session:
                await ticker_extractor.load_tickers_from_db(session)
            logger.info("[Startup] Ticker extractor cache loaded.")
        except Exception as e:
            logger.warning("[Startup] Failed to load ticker extractor cache: %s", e)

        market_data = MarketDataService.get_instance()
        market_data.set_connection_manager(app.state.connection_manager)
        market_data.start(db_tickers if db_tickers else [])
        logger.info(
            "[Startup] Market data service started with %d tickers subscribed to WebSocket.",
            len(db_tickers),
        )
    except Exception as e:
        logger.warning("[Startup] Failed to subscribe watchlist tickers to WebSocket: %s", e)
        market_data = MarketDataService.get_instance()
        market_data.set_connection_manager(app.state.connection_manager)
        market_data.start([])

    # Production collection is externally triggered. Keep this only as an
    # opt-in local-development convenience so web-process sleep cannot stop news.
    if settings.NEWS_SCHEDULER_ENABLED:
        try:
            async def fetch_tickers():
                async with async_session_factory() as session:
                    return await get_all_tickers(session)

            start_scheduler(async_session_factory, fetch_tickers, app.state.connection_manager)
            logger.info("[Startup] Local news ingestion scheduler started (every 15 min).")
        except Exception as e:
            logger.warning("[Startup] Failed to start local news scheduler: %s", e)
    else:
        logger.info("[Startup] In-process news scheduler disabled; external trigger is authoritative.")

    # Start AI Worker (background job processor)
    try:
        app.state.ai_worker = AIWorker(
            get_session_factory=async_session_factory,
            poll_interval=settings.AI_WORKER_POLL_INTERVAL_S,
            max_concurrent=settings.AI_WORKER_MAX_CONCURRENT,
        )
        asyncio.create_task(app.state.ai_worker.start())
        logger.info("[Startup] AI Worker started (background job processor).")
    except Exception as e:
        logger.warning("[Startup] Failed to start AI Worker: %s", e)

    # Start daily market report scheduler (enqueues once per day at ~4 PM EST)
    try:
        app.state._market_report_task = asyncio.create_task(
            _daily_market_report_loop(async_session_factory)
        )
        logger.info("[Startup] Daily market report scheduler started.")
    except Exception as e:
        logger.warning("[Startup] Failed to start market report scheduler: %s", e)

    # Start post-market price fetch loop (fetches at 4:01 PM ET on weekdays)
    try:
        app.state._post_market_task = asyncio.create_task(
            _post_market_fetch_loop(async_session_factory)
        )
        logger.info("[Startup] Post-market price fetch loop started.")
    except Exception as e:
        logger.warning("[Startup] Failed to start post-market fetch loop: %s", e)

    # ---- Memory diagnostic at startup completion ----
    if settings.MEMORY_DIAGNOSTICS_ENABLED:
        log_memory(
            "application_startup_complete",
            logger_to_use=logger,
            enabled=settings.MEMORY_DIAGNOSTICS_ENABLED,
        )

    yield

    # ---- Shutdown ----
    await shutdown_hybrid_data_service()

    try:
        market_data = MarketDataService.get_instance()
        market_data.stop()
        logger.info("[Shutdown] Market data service stopped.")
    except Exception as e:
        logger.warning("[Shutdown] Failed to stop market data service: %s", e)

    if settings.NEWS_SCHEDULER_ENABLED:
        try:
            stop_scheduler()
            logger.info("[Shutdown] News ingestion scheduler stopped.")
        except Exception as e:
            logger.warning("[Shutdown] Failed to stop news scheduler: %s", e)

    # Stop AI Worker
    try:
        if app.state.ai_worker:
            app.state.ai_worker.stop()
            logger.info("[Shutdown] AI Worker stopped.")
    except Exception as e:
        logger.warning("[Shutdown] Failed to stop AI Worker: %s", e)

    for task_name in ("_post_market_task", "_market_report_task"):
        task = getattr(app.state, task_name, None)
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


def create_app() -> FastAPI:
    """Factory function to create the FastAPI application."""

    app = FastAPI(title="Stock Dashboard", lifespan=lifespan)

    # Register centralized exception handlers
    register_exception_handlers(app)

    # Global connection manager (shared with MarketDataService)
    app.state.connection_manager = ConnectionManager()

    # Global AI worker instance
    app.state.ai_worker: AIWorker | None = None

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "Accept", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )
    app.state.started_at = time.time()

    # ---------- Rate Limiting Middleware (SEC-003 / TD-004) ----------
    @app.middleware("http")
    async def rate_limit_middleware(request: Request, call_next):
        """In-memory rate limiter with thread-safe access and bounded memory."""
        client_ip = request.client.host if request.client else "unknown"

        # Skip rate limit for localhost during development
        if client_ip in ("127.0.0.1", "localhost", "::1"):
            return await call_next(request)

        if request.url.path in ("/ws", "/health", "/health/live", "/health/ready"):
            return await call_next(request)

        now = time.time()
        async with _rate_limit_lock:
            if client_ip not in _rate_limit_store:
                _rate_limit_store[client_ip] = []

            timestamps = [t for t in _rate_limit_store[client_ip] if now - t < _RATE_LIMIT_WINDOW]
            _rate_limit_store[client_ip] = timestamps

            if len(timestamps) >= _RATE_LIMIT_MAX_REQS:
                logger.warning("[RateLimit] %s exceeded %d req/%ds", client_ip, _RATE_LIMIT_MAX_REQS, _RATE_LIMIT_WINDOW)
                headers = _configured_cors_headers(request)
                headers["Retry-After"] = str(_RATE_LIMIT_WINDOW)
                if headers:
                    headers["Access-Control-Expose-Headers"] = (
                        "X-Request-ID, Retry-After"
                    )
                # HTTPException raised from user middleware bypasses FastAPI's
                # registered handler and would otherwise become a wire 500.
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": "Too many requests. Please slow down.",
                        "status_code": 429,
                    },
                    headers=headers,
                )

            timestamps.append(now)

            if len(_rate_limit_store) > 10000:
                stale = [ip for ip, ts_list in _rate_limit_store.items()
                         if now - max(ts_list, default=now) > _RATE_LIMIT_WINDOW * 2]
                for ip in stale:
                    del _rate_limit_store[ip]

        response = await call_next(request)
        return response

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        """Log every request with method, path, status code, and latency."""
        correlation_id = normalize_correlation_id(request.headers.get("X-Request-ID"))
        start = time.perf_counter()
        with market_data_correlation(correlation_id):
            response = await call_next(request)
        elapsed = time.perf_counter() - start
        response.headers["X-Request-ID"] = correlation_id
        logger.info(
            "[Request] correlation_id=%s %s %s -> %s (%.0fms)",
            correlation_id,
            request.method,
            request.url.path,
            response.status_code,
            elapsed * 1000,
        )
        return response

    # ---------- Health Check Endpoint ----------
    @app.get("/health/live", tags=["health"], response_model=HealthLiveResponse)
    async def health_live() -> HealthLiveResponse:
        """Process-only probe; intentionally performs no network I/O."""
        return HealthLiveResponse(
            git_commit=os.getenv("RENDER_GIT_COMMIT"),
            git_branch=os.getenv("RENDER_GIT_BRANCH"),
        )

    @app.get("/health", tags=["health"])
    @app.get("/health/ready", tags=["health"])
    async def health_check():
        """Minimal public readiness probe for hosting health checks."""
        from sqlalchemy import text

        database_reachable = False
        try:
            async with asyncio.timeout(2):
                async with async_session_factory() as session:
                    await session.execute(text("SELECT 1"))
            database_reachable = True
        except Exception as exc:
            logger.warning(
                "[Health] readiness database check failed exception_type=%s message=%s",
                type(exc).__name__,
                sanitize_database_error(exc),
                extra={"event": "readiness_failed", "dependency": "database"},
            )

        payload = {
            "status": "ready" if database_reachable else "not_ready",
            "database": "reachable" if database_reachable else "unreachable",
        }
        return JSONResponse(
            status_code=200 if database_reachable else 503,
            content=payload,
        )

    @app.get(
        "/api/operations/status",
        tags=["operations"],
        dependencies=[Depends(verify_app_access_token)],
    )
    async def operations_status():
        """Authenticated operational diagnostics without secret values."""
        from sqlalchemy import func, select, text
        from backend.models.ai_job_queue import AIJobQueue
        from backend.services.ai import ProviderRegistry

        started = time.perf_counter()
        database = {"status": "unhealthy", "latency_ms": None}
        workers = {
            "status": "unhealthy", "queued_jobs": 0, "running_jobs": 0,
            "failed_jobs": 0, "last_success_at": None, "last_failure_at": None,
        }
        news_ingestion = {
            "status": "unavailable", "stale": True, "running": False,
            "last_attempted_at": None, "last_successful_at": None,
            "consecutive_failures": 0, "metrics": {},
        }
        try:
            db_started = time.perf_counter()
            async with asyncio.timeout(2):
                async with async_session_factory() as session:
                    await session.execute(text("SELECT 1"))
                    counts = dict((await session.execute(
                        select(AIJobQueue.status, func.count(AIJobQueue.id)).group_by(AIJobQueue.status)
                    )).all())
                    latest_success = (await session.execute(
                        select(AIJobQueue.completed_at).where(AIJobQueue.status == "completed")
                        .order_by(AIJobQueue.completed_at.desc()).limit(1)
                    )).scalar_one_or_none()
                    latest_failure = (await session.execute(
                        select(AIJobQueue.completed_at).where(AIJobQueue.status == "failed")
                        .order_by(AIJobQueue.completed_at.desc()).limit(1)
                    )).scalar_one_or_none()
                    try:
                        from backend.services.news_ingestion_service import get_news_ingestion_health
                        news_ingestion = await get_news_ingestion_health(session)
                    except Exception:
                        logger.warning("[Health] News ingestion state check failed", exc_info=True)
            database = {"status": "healthy", "latency_ms": round((time.perf_counter() - db_started) * 1000, 1)}
            worker_running = bool(getattr(app.state, "ai_worker", None) and app.state.ai_worker._running)
            workers = {
                "status": "healthy" if worker_running else "degraded",
                "queued_jobs": counts.get("pending", 0), "running_jobs": counts.get("processing", 0),
                "failed_jobs": counts.get("failed", 0),
                "last_success_at": latest_success.isoformat() if latest_success else None,
                "last_failure_at": latest_failure.isoformat() if latest_failure else None,
            }
        except Exception:
            logger.warning("[Health] Database/queue check failed", exc_info=True)

        provider_status = {}
        for provider_id in ("openai", "ollama"):
            try:
                provider_class = ProviderRegistry.get(provider_id)
                if provider_class is None:
                    raise LookupError(f"AI provider is not registered: {provider_id}")
                provider = provider_class()
                available = await asyncio.wait_for(provider.is_available(), timeout=1.5)
                provider_status[provider_id] = {"status": "available" if available else "unavailable"}
            except Exception:
                provider_status[provider_id] = {"status": "unavailable"}

        usable_ai = any(p["status"] == "available" for p in provider_status.values())
        if database["status"] != "healthy":
            overall = "unhealthy"
        elif (
            not usable_ai
            or workers["status"] != "healthy"
            or news_ingestion.get("stale", True)
            or news_ingestion["status"] in {"never_run", "stale", "degraded", "unavailable"}
        ):
            overall = "degraded"
        else:
            overall = "healthy"

        return {
            "status": overall,
            "application": {
                "version": settings.APP_VERSION, "environment": settings.ENVIRONMENT,
                "uptime_seconds": round(time.time() - app.state.started_at, 1),
                "check_latency_ms": round((time.perf_counter() - started) * 1000, 1),
            },
            "dependencies": {
                "database": database,
                "supabase": {"status": database["status"] if "supabase" in (settings.DATABASE_URL or "").lower() else "not_configured"},
                "market_data": {"status": "configured" if settings.FINNHUB_API_KEY else "unconfigured"},
                **provider_status,
            },
            "workers": workers,
            "news_ingestion": news_ingestion,
            "websocket": {"status": "available", "authentication": "required"},
        }

    # ---------- Mount routers ----------
    # All REST routers require the single-user access token. The websocket
    # router performs equivalent authentication during its handshake because
    # browsers cannot set a custom Authorization header for WebSockets.
    _auth_dep = [Depends(verify_app_access_token)]
    app.include_router(auth_router.router, dependencies=_auth_dep)
    app.include_router(stock_router.router, dependencies=_auth_dep)
    app.include_router(watchlist_router.router, dependencies=_auth_dep)
    app.include_router(news_router.router, dependencies=_auth_dep)
    app.include_router(websocket_router.router)
    app.include_router(analysis_router.router, dependencies=_auth_dep)
    app.include_router(analysis_reports_router.router, dependencies=_auth_dep)
    app.include_router(markets_router.router, prefix="/api/markets", dependencies=_auth_dep)
    app.include_router(intelligence_router.router, dependencies=_auth_dep)
    app.include_router(maintenance_intelligence_router.router)
    app.include_router(internal_jobs_router.router)

    return app


# Module-level app instance for uvicorn
app = create_app()
