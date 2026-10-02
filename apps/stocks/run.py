"""
Startup entry point for YapVibes Stocks Backend.

Development (local):
    python run.py

Production (Railway/Docker):
    uvicorn backend.main:app --host 0.0.0.0 --port 8000

On Windows, explicitly use SelectorEventLoop through Uvicorn's loop factory
so the same loop is used in development reload workers and production.
"""
import asyncio
import os
import sys

from dotenv import load_dotenv

# Load .env file in development; override=False ensures Railway-provided env vars
# (like DATABASE_URL) take precedence over values in the local .env file.
load_dotenv(override=False)


def new_selector_event_loop():
    """Create the Windows loop without the deprecated global policy API."""
    return asyncio.SelectorEventLoop()


def is_production():
    """Detect production environment."""
    # Railway sets RAILWAY_ENVIRONMENT, we also support standard NODE_ENV/ENV conventions
    return bool(os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("ENVIRONMENT") == "production")


if __name__ == "__main__":
    import uvicorn

    prod = is_production()
    port = int(os.getenv("PORT", 8000))

    print(
        f"[Startup] Environment: {'PRODUCTION' if prod else 'DEVELOPMENT'} | "
        f"AI Provider: {os.getenv('AI_PROVIDER', 'ollama')} | "
        f"Port: {port}"
    )

    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=port,
        reload=not prod,
        loop="run:new_selector_event_loop" if sys.platform == "win32" else "auto",
        log_level="info",
    )
