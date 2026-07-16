"""
Startup entry point for YapVibes Stocks Backend.

Development (local):
    python run.py

Production (Railway/Docker):
    uvicorn backend.main:app --host 0.0.0.0 --port 8000

On Windows, uvicorn uses ProactorEventLoop by default which is incompatible
with asyncpg. This script forces SelectorEventLoop before starting the server.
"""
import asyncio
import os
import sys
import selectors

from dotenv import load_dotenv

# Load .env file in development (ignored safely if not found)
load_dotenv()

# On Windows, force SelectorEventLoop for asyncpg compatibility
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


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
        log_level="info",
    )
