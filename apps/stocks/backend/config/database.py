"""
Async PostgreSQL connection layer using SQLAlchemy + asyncpg.

Usage:
    from backend.config.database import get_async_session, Base

Environment:
    DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/news
"""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from backend.config.settings import settings

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


async def get_async_session():
    """Dependency that yields an AsyncSession and auto-closes it."""
    async with async_session_factory() as session:
        try:
            yield session
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
