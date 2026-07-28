"""Read-only Render diagnostic for the AI queue.

This script intentionally imports no ORM models, because its purpose is to
inspect deployments that may be behind the current migration head.
"""

import asyncio
import json
import os
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool


TABLE_NAME = "ai_job_queue"
OPTIONAL_COLUMNS = {
    "created_at",
    "started_at",
    "updated_at",
    "retry_count",
    "attempt_count",
    "worker_id",
    "lease_owner",
    "lease_id",
    "lease_expires_at",
    "dedupe_key",
}


def _redact(value: str | None) -> str:
    if not value:
        return "unknown"
    if len(value) <= 2:
        return "*" * len(value)
    return f"{value[0]}***{value[-1]}"


def _async_database_url(raw_url: str) -> str:
    if raw_url.startswith("postgresql://"):
        return raw_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if raw_url.startswith("postgres://"):
        return raw_url.replace("postgres://", "postgresql+asyncpg://", 1)
    return raw_url


def _json_default(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    raise TypeError(f"Unsupported diagnostic value: {type(value).__name__}")


def _column_or_null(columns: set[str], name: str) -> str:
    return f'"{name}"' if name in columns else f"NULL AS {name}"


async def inspect_queue() -> dict:
    raw_url = os.getenv("DATABASE_URL")
    if not raw_url:
        raise RuntimeError("DATABASE_URL is not configured")

    parsed = make_url(raw_url)
    if not parsed.drivername.startswith(("postgresql", "postgres")):
        raise RuntimeError("The queue diagnostic supports PostgreSQL only")

    output = {
        "database": {
            "host_redacted": _redact(parsed.host),
            "name_redacted": _redact(parsed.database),
        },
        "current_alembic_revision": [],
        "job_counts_by_status": {},
        "dedupe_key_column_present": False,
        "processing_jobs": [],
    }

    engine = create_async_engine(
        _async_database_url(raw_url),
        poolclass=NullPool,
        connect_args={"command_timeout": 15},
    )
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            try:
                await connection.execute(text("SET TRANSACTION READ ONLY"))
                read_only = (
                    await connection.execute(text("SHOW transaction_read_only"))
                ).scalar_one()
                if read_only != "on":
                    raise RuntimeError("Could not establish a read-only transaction")

                alembic_exists = (
                    await connection.execute(
                        text(
                            "SELECT to_regclass('public.alembic_version') IS NOT NULL"
                        )
                    )
                ).scalar_one()
                if alembic_exists:
                    revisions = await connection.execute(
                        text("SELECT version_num FROM alembic_version ORDER BY version_num")
                    )
                    output["current_alembic_revision"] = [
                        row.version_num for row in revisions
                    ]

                columns_result = await connection.execute(
                    text(
                        """
                        SELECT column_name
                        FROM information_schema.columns
                        WHERE table_schema = current_schema()
                          AND table_name = :table_name
                        """
                    ),
                    {"table_name": TABLE_NAME},
                )
                columns = {row.column_name for row in columns_result}
                output["dedupe_key_column_present"] = "dedupe_key" in columns
                if not {"id", "status"}.issubset(columns):
                    return output

                counts = await connection.execute(
                    text(
                        'SELECT "status", COUNT(*) AS job_count '
                        'FROM "ai_job_queue" GROUP BY "status" ORDER BY "status"'
                    )
                )
                output["job_counts_by_status"] = {
                    row.status: row.job_count for row in counts
                }

                inspected_optional = columns.intersection(OPTIONAL_COLUMNS)
                if "attempt_count" in inspected_optional:
                    attempt_expression = '"attempt_count"'
                elif "retry_count" in inspected_optional:
                    attempt_expression = 'COALESCE("retry_count", 0) + 1'
                else:
                    attempt_expression = "NULL"

                age_columns = [
                    f'"{name}"'
                    for name in ("updated_at", "started_at", "created_at")
                    if name in inspected_optional
                ]
                age_expression = (
                    "EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - COALESCE("
                    + ", ".join(age_columns)
                    + ")))"
                    if age_columns
                    else "NULL"
                )

                worker_column = next(
                    (
                        name
                        for name in ("worker_id", "lease_owner", "lease_id")
                        if name in inspected_optional
                    ),
                    None,
                )
                worker_expression = (
                    f'"{worker_column}" AS worker_or_lease_identifier'
                    if worker_column
                    else "NULL AS worker_or_lease_identifier"
                )
                dedupe_expression = (
                    '"dedupe_key" IS NOT NULL AS dedupe_key_present'
                    if "dedupe_key" in inspected_optional
                    else "FALSE AS dedupe_key_present"
                )

                processing_sql = f"""
                    SELECT
                        "id",
                        {_column_or_null(columns, "created_at")},
                        {_column_or_null(columns, "started_at")},
                        {_column_or_null(columns, "updated_at")},
                        {attempt_expression} AS attempt_count,
                        {worker_expression},
                        {_column_or_null(columns, "lease_expires_at")},
                        {dedupe_expression},
                        {age_expression} AS age_seconds
                    FROM "ai_job_queue"
                    WHERE "status" = :processing_status
                    ORDER BY "id"
                """
                processing = await connection.execute(
                    text(processing_sql),
                    {"processing_status": "processing"},
                )
                output["processing_jobs"] = [
                    {
                        "id": row.id,
                        "created_at": row.created_at,
                        "started_at": row.started_at,
                        "updated_at": row.updated_at,
                        "attempt_count": row.attempt_count,
                        "worker_or_lease_identifier": row.worker_or_lease_identifier,
                        "lease_expires_at": row.lease_expires_at,
                        "dedupe_key_present": row.dedupe_key_present,
                        "age_seconds": (
                            round(float(row.age_seconds), 1)
                            if row.age_seconds is not None
                            else None
                        ),
                    }
                    for row in processing
                ]
                return output
            finally:
                await transaction.rollback()
    finally:
        await engine.dispose()


def main() -> None:
    try:
        result = asyncio.run(inspect_queue())
    except Exception:
        # Never print the exception string: database drivers can include host,
        # username, or connection details in it.
        result = {
            "database": {
                "host_redacted": "unavailable",
                "name_redacted": "unavailable",
            },
            "current_alembic_revision": [],
            "job_counts_by_status": {},
            "dedupe_key_column_present": False,
            "processing_jobs": [],
        }
    print(json.dumps(result, indent=2, default=_json_default))


if __name__ == "__main__":
    main()
