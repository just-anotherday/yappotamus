import asyncio
import selectors
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ---------------------------------------------------------------------
# Import ALL models so Alembic can autogenerate against the full schema.
# Order matters: each import must register its table on Base.metadata.
# ---------------------------------------------------------------------
from backend.config.database import Base, DATABASE_URL
from backend.models.news import NewsArticle  # noqa: F401
from backend.models.watchlist import WatchlistModel  # noqa: F401
from backend.models.report import AnalysisReportModel  # noqa: F401

# New models for event-driven architecture
from backend.models.asset import Asset, AssetTicker  # noqa: F401
from backend.models.ai_job_queue import AIJobQueue  # noqa: F401
from backend.models.ai_reports import AICompanyReport, AISectorReport, AIMarketReport  # noqa: F401

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode using async engine."""
    connectable = create_async_engine(
        DATABASE_URL,
        poolclass=pool.NullPool,
    )

    async def do_run():
        from sqlalchemy.ext.asyncio import AsyncTransaction
        async with connectable.connect() as connection:
            transaction: AsyncTransaction | None = None
            try:
                await connection.run_sync(
                    lambda sync_conn: context.configure(
                        connection=sync_conn,
                        target_metadata=target_metadata,
                        compare_type=True,
                        render_as_batch=False,
                    )
                )
                transaction = await connection.begin()
                await connection.run_sync(lambda _: context.run_migrations())
                await transaction.commit()
            except Exception:
                if transaction:
                    await transaction.rollback()
                raise

    asyncio.run(do_run(), loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()))


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
