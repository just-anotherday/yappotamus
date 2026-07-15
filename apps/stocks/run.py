"""
Startup entry point for YapVibes backend.

On Windows, uvicorn uses ProactorEventLoop by default which is incompatible
with psycopg3 async mode. This script forces SelectorEventLoop before starting
the server to resolve: psycopg.InterfaceError.

Usage:
    python run.py
"""
import asyncio
import sys
import selectors

# On Windows, force SelectorEventLoop for psycopg3 compatibility
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
