"""Opt-in transactional PostgreSQL test; all permission changes are rolled back."""
import importlib.util
import os
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine

URL = os.getenv("STOCKS_SECURITY_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="Explicit local security-test database required")


@pytest.mark.asyncio
async def test_private_migration_blocks_public_roles_and_preserves_backend_owner():
    path = Path(__file__).resolve().parents[1] / "alembic/versions/2026_10_23_private_app_tables.py"
    spec = importlib.util.spec_from_file_location("private_table_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_async_engine(URL, connect_args={"timeout": 10, "command_timeout": 10})
    try:
        async with engine.connect() as conn:
            transaction = await conn.begin()
            try:
                for role in ("anon", "authenticated"):
                    await conn.execute(text(f"""DO $$ BEGIN
                        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='{role}') THEN
                            CREATE ROLE {role} NOLOGIN;
                        END IF;
                    END $$;"""))
                await conn.execute(text("GRANT SELECT ON public.watchlist TO PUBLIC, anon, authenticated"))
                def apply(sync_conn):
                    with Operations.context(MigrationContext.configure(sync_conn)):
                        migration.upgrade()
                await conn.run_sync(apply)
                rows = (await conn.execute(text("""
                    SELECT c.relname, c.relrowsecurity,
                           has_table_privilege('anon', c.oid, 'SELECT') AS anon_read,
                           has_table_privilege('authenticated', c.oid, 'SELECT') AS user_read
                    FROM pg_class c JOIN pg_namespace n ON c.relnamespace=n.oid
                    WHERE n.nspname='public' AND c.relkind='r'
                """))).mappings().all()
                protected = [r for r in rows if r['relname'] in migration.PRIVATE_TABLES]
                assert protected
                assert all(r['relrowsecurity'] and not r['anon_read'] and not r['user_read'] for r in protected)
                # The owner connection used by the backend keeps access.
                await conn.execute(text("SELECT count(*) FROM public.watchlist"))
                await conn.execute(text("SET LOCAL ROLE anon"))
                with pytest.raises(DBAPIError) as denied:
                    await conn.execute(text("SELECT * FROM public.watchlist LIMIT 1"))
                assert denied.value.orig.sqlstate == "42501"
            finally:
                await transaction.rollback()
    finally:
        await engine.dispose()
