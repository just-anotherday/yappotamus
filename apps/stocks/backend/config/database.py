"""
Async PostgreSQL connection layer using SQLAlchemy + asyncpg.

Usage:
    from backend.config.database import get_async_session, Base

Environment:
    DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/news
"""

import logging
import re

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, InterfaceError, OperationalError
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from backend.config.settings import settings

logger = logging.getLogger(__name__)


def sanitize_database_error(exc: BaseException) -> str:
    """Keep diagnostic text useful without leaking credentials embedded in a DSN."""
    message = str(exc)
    message = re.sub(r"(postgres(?:ql)?(?:\+[\w]+)?://)[^\s@/]+@", r"\1***@", message)
    return message[:1000]

DATABASE_URL = settings.DATABASE_URL or "postgresql+asyncpg://postgres:postgres@localhost:5432/news"

# If the user provides a plain postgresql:// URL (no driver specified), default to asyncpg.
if DATABASE_URL.startswith("postgresql://") and "+psycopg" not in DATABASE_URL and "+asyncpg" not in DATABASE_URL:
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_size=settings.DB_POOL_SIZE,         # deployment-safe default via DB_POOL_SIZE env var
    max_overflow=settings.DB_MAX_OVERFLOW,    # deployment-safe default via DB_MAX_OVERFLOW env var
    pool_timeout=settings.DB_POOL_TIMEOUT,    # prevent hanging if pool exhausted
    pool_recycle=3600,
    pool_pre_ping=True,                       # health check before each checkout
)

async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""
    pass


def _is_connection_failure(exc: BaseException) -> bool:
    """Return whether a failed request may have left stale pooled connections."""
    return isinstance(exc, (OperationalError, InterfaceError)) or (
        isinstance(exc, DBAPIError) and exc.connection_invalidated
    )


async def _recover_session_after_failure(session: AsyncSession, exc: BaseException) -> None:
    """Rollback the request session and discard a pool only after connection loss."""
    try:
        await session.rollback()
    except Exception:
        logger.warning("[Database] rollback failed after request error", exc_info=True)

    if _is_connection_failure(exc):
        logger.warning(
            "[Database] connection failure; disposing pooled connections exception_type=%s message=%s",
            type(exc).__name__, sanitize_database_error(exc),
        )
        await engine.dispose()


async def get_async_session():
    """Yield a request session, rolling it back after errors and recovering stale pools."""
    async with async_session_factory() as session:
        try:
            yield session
        except Exception as exc:
            await _recover_session_after_failure(session, exc)
            raise
        finally:
            await session.close()


async def init_db():
    """Verify database connectivity without mutating the production schema.

    Schema creation and upgrades are owned exclusively by Alembic.  In
    particular, application startup must never drop tables or use
    ``Base.metadata.create_all`` as an implicit production migration.
    """
    import logging
    logger = logging.getLogger(__name__)
    logger.info("[DB] Verifying database connectivity...")
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    logger.info("[DB] Database connectivity verified; schema is managed by Alembic.")
