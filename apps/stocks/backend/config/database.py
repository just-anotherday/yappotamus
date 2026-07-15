"""
Async PostgreSQL connection layer using SQLAlchemy + asyncpg.

Usage:
    from backend.config.database import get_async_session, Base

Environment:
    DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/news
"""

import os
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/news"
)

# If the user provides a plain postgresql:// URL (no driver specified), default to asyncpg.
if DATABASE_URL.startswith("postgresql://") and "+psycopg" not in DATABASE_URL and "+asyncpg" not in DATABASE_URL:
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_size=25,                # TD-017: increased for concurrent load
    max_overflow=30,
    pool_recycle=3600,
    pool_pre_ping=True,         # health check before each checkout
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


async def migrate_news_table():
    """
    Migration: drop old news_articles table if it has stale or missing columns
    and let SQLAlchemy recreate it with the Finnhub-aligned schema.
    
    Checks for:
      1. Old column "headline" (pre-Finnhub schema)
      2. Missing "title" column (intermediate state from partial migration)
    """
    import logging
    logger = logging.getLogger(__name__)

    # Ensure all models are registered with Base before create_all
    from backend.models.news import NewsArticle  # noqa: ensure model is registered
    from backend.models.report import AnalysisReportModel  # noqa: register analysis reports table

    async with engine.begin() as conn:
        # Check if the old column "headline" exists OR the required "title" column is missing
        result = await conn.execute(
            text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'news_articles' AND column_name IN ('headline', 'title')
            """)
        )
        columns = {row[0] for row in result.fetchall()}
        
        has_old_schema = "headline" in columns
        missing_title = "title" not in columns
        
        if has_old_schema or missing_title:
            reason = "old schema detected" if has_old_schema else "missing 'title' column"
            logger.info("[Migration] news_articles needs rebuild — %s. Dropping and recreating.", reason)
            
            # Drop the old table
            await conn.execute(text("DROP TABLE IF EXISTS news_articles CASCADE"))
            # SQLAlchemy will recreate it with the new schema via create_all
            await conn.run_sync(Base.metadata.create_all)
            logger.info("[Migration] news_articles recreated with Finnhub-aligned schema.")
        else:
            # Schema is already correct, just ensure tables exist
            await conn.run_sync(Base.metadata.create_all)


async def init_db():
    """Create all tables defined on Base (idempotent). Runs migration if needed."""
    import logging
    logging.getLogger(__name__).info("[DB] Initializing database...")
    await migrate_news_table()
