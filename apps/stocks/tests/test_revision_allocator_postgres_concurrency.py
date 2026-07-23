"""Focused real-PostgreSQL gate for production revision allocation concurrency."""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import asdict, dataclass
from time import perf_counter
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.maintenance.article_intelligence.revision import PostgreSQLRevisionAllocator
from backend.models.intelligence import ArticleIntelligence
from backend.models.news import NewsArticle  # noqa: F401 - registers the ORM FK target


DATABASE_URL = os.getenv("PHASE7_POSTGRES_URL")
WORKERS = 6
REPETITIONS = 3
LOCK_TIMEOUT_MS = 5_000
STATEMENT_TIMEOUT_MS = 10_000

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DATABASE_URL,
        reason="PHASE7_POSTGRES_URL is required for the disposable PostgreSQL concurrency gate",
    ),
]


@dataclass
class WorkerEvidence:
    worker: str
    backend_pid: int | None = None
    transaction_started: float | None = None
    allocation_started: float | None = None
    allocated: float | None = None
    revision: int | None = None
    lock_wait_ms: float | None = None
    lock_granted_after_allocate: bool | None = None
    committed: float | None = None
    rolled_back: float | None = None
    completed: float | None = None


async def _insert_article(engine, marker: str) -> int:
    async with engine.begin() as connection:
        return (await connection.execute(
            text(
                "INSERT INTO news_articles (finnhub_id, ticker, title, article_url) "
                "VALUES (:marker, 'SPY', 'revision concurrency gate', :url) RETURNING id"
            ),
            {"marker": marker, "url": f"https://phase7.invalid/{marker}"},
        )).scalar_one()


async def _cleanup(engine, article_id: int) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            text("DELETE FROM article_intelligence WHERE article_id = :article_id"),
            {"article_id": article_id},
        )
        await connection.execute(
            text("DELETE FROM news_articles WHERE id = :article_id"),
            {"article_id": article_id},
        )


async def _committed_revisions(engine, article_id: int) -> list[int]:
    async with engine.connect() as connection:
        return list((await connection.execute(
            select(ArticleIntelligence.generation_revision)
            .where(ArticleIntelligence.article_id == article_id)
            .order_by(ArticleIntelligence.generation_revision)
        )).scalars())


async def _remaining_advisory_locks(engine, backend_pids: list[int]) -> int:
    async with engine.connect() as connection:
        return (await connection.execute(
            text(
                "SELECT count(*) FROM pg_locks "
                "WHERE locktype = 'advisory' AND pid = ANY(:backend_pids)"
            ),
            {"backend_pids": backend_pids},
        )).scalar_one()


async def _worker(
    session_factory,
    barrier: asyncio.Barrier,
    article_id: int,
    evidence: WorkerEvidence,
    *,
    roll_back: bool = False,
    hold_lock_ms: int = 40,
) -> None:
    async with session_factory() as session:
        try:
            async with session.begin():
                await session.execute(text(f"SET LOCAL lock_timeout = '{LOCK_TIMEOUT_MS}ms'"))
                await session.execute(text(f"SET LOCAL statement_timeout = '{STATEMENT_TIMEOUT_MS}ms'"))
                evidence.backend_pid = (await session.execute(text("SELECT pg_backend_pid()"))).scalar_one()
                evidence.transaction_started = perf_counter()
                await barrier.wait()
                evidence.allocation_started = perf_counter()
                evidence.revision = await PostgreSQLRevisionAllocator(session).allocate(
                    article_id=article_id,
                    source_content_hash="s" * 64,
                    prompt_hash="p" * 64,
                    input_hash="i" * 64,
                )
                evidence.allocated = perf_counter()
                evidence.lock_wait_ms = (evidence.allocated - evidence.allocation_started) * 1_000
                evidence.lock_granted_after_allocate = bool((await session.execute(
                    text(
                        "SELECT bool_and(granted) FROM pg_locks "
                        "WHERE pid = pg_backend_pid() AND locktype = 'advisory'"
                    )
                )).scalar_one())
                await session.execute(text(
                    "INSERT INTO article_intelligence ("
                    "article_id, ticker, status, provider, model, prompt_version, prompt_hash, "
                    "source_content_hash, input_hash, generation_revision"
                    ") VALUES ("
                    ":article_id, 'SPY', 'completed', 'phase7-gate', 'production-flow', "
                    "'phase7', :prompt_hash, :source_hash, :input_hash, :revision)"
                ), {
                    "article_id": article_id,
                    "prompt_hash": "p" * 64,
                    "source_hash": "s" * 64,
                    "input_hash": "i" * 64,
                    "revision": evidence.revision,
                })
                await asyncio.sleep(hold_lock_ms / 1_000)
                if roll_back:
                    await session.rollback()
                    evidence.rolled_back = perf_counter()
                else:
                    evidence.committed = perf_counter()  # finalized on context exit
            if evidence.committed is not None:
                evidence.committed = perf_counter()
        finally:
            evidence.completed = perf_counter()


def _print_evidence(scenario: str, evidence: list[WorkerEvidence], revisions: list[int], locks: int) -> None:
    print("PHASE7_REVISION_EVIDENCE=" + json.dumps({
        "scenario": scenario,
        "worker_count": len(evidence),
        "allocated_revision_sequence": [row.revision for row in sorted(evidence, key=lambda row: row.allocated or 0)],
        "committed_revisions": revisions,
        "remaining_advisory_locks": locks,
        "workers": [asdict(row) for row in evidence],
    }, sort_keys=True))


async def test_production_allocator_serializes_repeated_concurrent_transactions():
    engine = create_async_engine(DATABASE_URL, pool_size=WORKERS + 2, max_overflow=0)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        for repetition in range(REPETITIONS):
            article_id = await _insert_article(engine, f"phase7-revision-{uuid4().hex}")
            evidence = [WorkerEvidence(f"repeat-{repetition}-worker-{index}") for index in range(WORKERS)]
            barrier = asyncio.Barrier(WORKERS)
            try:
                await asyncio.wait_for(asyncio.gather(*(
                    _worker(session_factory, barrier, article_id, row) for row in evidence
                )), timeout=STATEMENT_TIMEOUT_MS / 1_000 + 5)
                revisions = await _committed_revisions(engine, article_id)
                locks = await _remaining_advisory_locks(engine, [row.backend_pid for row in evidence])
                _print_evidence(f"normal-repeat-{repetition}", evidence, revisions, locks)
                assert revisions == list(range(1, WORKERS + 1))
                assert sorted(row.revision for row in evidence) == revisions
                assert all(row.lock_granted_after_allocate for row in evidence)
                assert locks == 0
            finally:
                await _cleanup(engine, article_id)
    finally:
        await engine.dispose()


async def test_rollback_releases_lock_and_reuses_uncommitted_revision_without_gap():
    engine = create_async_engine(DATABASE_URL, pool_size=WORKERS + 2, max_overflow=0)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    article_id = await _insert_article(engine, f"phase7-rollback-{uuid4().hex}")
    evidence = [WorkerEvidence(f"rollback-worker-{index}") for index in range(WORKERS)]
    barrier = asyncio.Barrier(WORKERS)
    try:
        await asyncio.wait_for(asyncio.gather(*(
            _worker(session_factory, barrier, article_id, row, roll_back=index == 0)
            for index, row in enumerate(evidence)
        )), timeout=STATEMENT_TIMEOUT_MS / 1_000 + 5)
        revisions = await _committed_revisions(engine, article_id)
        locks = await _remaining_advisory_locks(engine, [row.backend_pid for row in evidence])
        _print_evidence("one-rollback", evidence, revisions, locks)
        assert revisions == list(range(1, WORKERS))
        assert sum(row.rolled_back is not None for row in evidence) == 1
        assert all(row.lock_granted_after_allocate for row in evidence)
        assert locks == 0
    finally:
        await _cleanup(engine, article_id)
        await engine.dispose()