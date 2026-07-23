"""Disposable-PostgreSQL coverage for migration bootstrap compatibility."""

from __future__ import annotations

import os
import subprocess
import uuid
from pathlib import Path
from urllib.parse import urlparse

import pytest


STOCKS_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = STOCKS_ROOT.parents[1]
ALEMBIC_INI = STOCKS_ROOT / "alembic.ini"
PYTHON = STOCKS_ROOT / ".venv" / "Scripts" / "python.exe"
ADMIN_URL = os.getenv("PHASE7_POSTGRES_ADMIN_URL")
POSTGRES_CONTAINER = os.getenv(
    "PHASE7_POSTGRES_CONTAINER", "yapvibes-phase7-postgres"
)


pytestmark = pytest.mark.skipif(
    not ADMIN_URL,
    reason="PHASE7_POSTGRES_ADMIN_URL is required for disposable PostgreSQL migration tests",
)


def _run(*args: str, database_url: str | None = None, check: bool = True):
    env = os.environ.copy()
    if database_url:
        env["DATABASE_URL"] = database_url
    return subprocess.run(
        args,
        cwd=REPO_ROOT,
        env=env,
        check=check,
        capture_output=True,
        text=True,
    )


def _psql(url: str, sql: str, *, check: bool = True):
    parsed = urlparse(url)
    return _run(
        "docker",
        "exec",
        POSTGRES_CONTAINER,
        "psql",
        "-U",
        parsed.username,
        "-d",
        parsed.path.lstrip("/"),
        "-v",
        "ON_ERROR_STOP=1",
        "-Atc",
        sql,
        check=check,
    )


def _alembic(url: str, *args: str, check: bool = True):
    return _run(
        str(PYTHON),
        "-m",
        "alembic",
        "-c",
        str(ALEMBIC_INI),
        *args,
        database_url=url.replace("postgresql://", "postgresql+asyncpg://", 1),
        check=check,
    )


@pytest.fixture
def disposable_database():
    name = f"phase7_migration_{uuid.uuid4().hex}"
    _psql(ADMIN_URL, f'CREATE DATABASE "{name}"')
    url = ADMIN_URL.rsplit("/", 1)[0] + f"/{name}"
    try:
        yield url
    finally:
        _psql(
            ADMIN_URL,
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            f"WHERE datname = '{name}' AND pid <> pg_backend_pid()",
        )
        _psql(ADMIN_URL, f'DROP DATABASE IF EXISTS "{name}"')


COMPATIBLE_NEWS = """
CREATE TABLE news_articles (
    id BIGSERIAL PRIMARY KEY,
    finnhub_id TEXT UNIQUE,
    ticker TEXT,
    title TEXT,
    summary TEXT,
    provider_name TEXT,
    article_url TEXT UNIQUE,
    thumbnail_url TEXT,
    pub_date TIMESTAMP WITHOUT TIME ZONE,
    raw_json JSONB,
    imported_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL
)
"""


@pytest.mark.parametrize("version_width", [None, 32, 128])
def test_version_table_starting_states_are_widened(disposable_database, version_width):
    if version_width:
        _psql(
            disposable_database,
            "CREATE TABLE alembic_version ("
            f"version_num VARCHAR({version_width}) NOT NULL, "
            "CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num))",
        )

    _alembic(disposable_database, "upgrade", "6be1956192ed")

    result = _psql(
        disposable_database,
        "SELECT version_num FROM alembic_version; "
        "SELECT character_maximum_length FROM information_schema.columns "
        "WHERE table_schema='public' AND table_name='alembic_version' "
        "AND column_name='version_num'; "
        "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
        "WHERE conrelid='public.alembic_version'::regclass AND contype='p'",
    ).stdout.splitlines()
    assert result == ["6be1956192ed", "128", "PRIMARY KEY (version_num)"]


def test_compatible_preexisting_news_table_is_adopted_without_data_loss(
    disposable_database,
):
    _psql(
        disposable_database,
        COMPATIBLE_NEWS
        + "; INSERT INTO news_articles (finnhub_id) VALUES ('preserved')",
    )

    _alembic(disposable_database, "upgrade", "2026_07_21_intelligence")
    _alembic(disposable_database, "downgrade", "base")

    result = _psql(
        disposable_database,
        "SELECT to_regclass('public.news_articles'); "
        "SELECT count(*) FROM news_articles WHERE finnhub_id='preserved'",
    ).stdout.splitlines()
    assert result == ["news_articles", "1"]


def test_incompatible_preexisting_news_table_fails_clearly_and_rolls_back(
    disposable_database,
):
    _psql(disposable_database, "CREATE TABLE news_articles (id INTEGER PRIMARY KEY)")

    result = _alembic(
        disposable_database, "upgrade", "6be1956192ed", check=False
    )

    assert result.returncode != 0
    assert "Incompatible preexisting public.news_articles columns" in result.stderr
    state = _psql(
        disposable_database,
        "SELECT to_regclass('public.alembic_version'); "
        "SELECT data_type FROM information_schema.columns "
        "WHERE table_schema='public' AND table_name='news_articles' AND column_name='id'; "
        "SELECT count(*) FROM information_schema.columns "
        "WHERE table_schema='public' AND table_name='news_articles'",
    ).stdout.splitlines()
    assert state == ["", "integer", "1"]


def test_clean_upgrade_downgrade_reupgrade_preserves_foundation(
    disposable_database,
):
    _alembic(disposable_database, "upgrade", "2026_07_21_maintenance")
    _alembic(disposable_database, "downgrade", "2026_07_21_intelligence")
    middle = _psql(
        disposable_database,
        "SELECT version_num FROM alembic_version; "
        "SELECT to_regclass('public.news_articles'); "
        "SELECT count(*) FROM pg_tables WHERE schemaname='public' "
        "AND tablename LIKE 'article_intelligence_maintenance_%'",
    ).stdout.splitlines()
    assert middle == ["2026_07_21_intelligence", "news_articles", "0"]

    _alembic(disposable_database, "upgrade", "2026_07_21_maintenance")
    final = _psql(
        disposable_database,
        "SELECT version_num FROM alembic_version; "
        "SELECT character_maximum_length FROM information_schema.columns "
        "WHERE table_schema='public' AND table_name='alembic_version' "
        "AND column_name='version_num'; "
        "SELECT count(*) FROM pg_tables WHERE schemaname='public' "
        "AND tablename LIKE 'article_intelligence_maintenance_%'",
    ).stdout.splitlines()
    assert final == ["2026_07_21_maintenance", "128", "3"]