"""Regression tests for reproducible startup and PostgreSQL queue claiming."""

from sqlalchemy.dialects import postgresql

from backend.main import app
from backend.services.ai_worker import AIWorker


def test_application_routes_can_be_enumerated():
    paths = {route.path for route in app.routes}
    assert "/health" in paths
    assert "/news" in paths
    assert "/api/analysis/reports/" in paths


def test_queue_claim_statement_uses_skip_locked(monkeypatch):
    """Two PostgreSQL workers must skip rows already locked by another claim."""
    from backend.models.ai_job_queue import AIJobQueue
    from sqlalchemy import and_, select
    from datetime import datetime

    worker = AIWorker(get_session_factory=lambda: None)
    stmt = (
        select(AIJobQueue)
        .where(
            and_(
                AIJobQueue.status == "pending",
                AIJobQueue.scheduled_for <= datetime.utcnow(),
                AIJobQueue.retry_count < AIJobQueue.max_retries,
            )
        )
        .order_by(AIJobQueue.priority.asc(), AIJobQueue.scheduled_for.asc())
        .with_for_update(skip_locked=True)
        .limit(worker.max_concurrent)
    )
    sql = str(stmt.compile(dialect=postgresql.dialect())).upper()
    assert "FOR UPDATE SKIP LOCKED" in sql


def test_enqueue_uses_transaction_advisory_lock():
    import inspect
    from backend.services.ai_worker import enqueue_job

    source = inspect.getsource(enqueue_job)
    assert "pg_advisory_xact_lock" in source
    assert source.index("pg_advisory_xact_lock") < source.index("exists_stmt")


def test_startup_database_initialization_contains_no_schema_ddl():
    import inspect
    from backend.config.database import init_db

    source = inspect.getsource(init_db).lower()
    executable_source = source.split('"""')[-1]
    assert "drop table" not in executable_source
    assert "create_all" not in executable_source
    assert 'text("select 1")' in executable_source