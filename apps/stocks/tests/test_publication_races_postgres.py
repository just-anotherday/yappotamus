"""Focused real-PostgreSQL gate for maintenance publication races."""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from time import perf_counter
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

# Register the complete relationship graph used by production ORM queries.
from backend.models.ai_reports import AICompanyReport  # noqa: F401
from backend.models.asset import Asset  # noqa: F401
from backend.models.intelligence import ArticleIntelligence  # noqa: F401
from backend.models.maintenance import (  # noqa: F401
    ArticleIntelligenceMaintenanceBatch,
    ArticleIntelligenceMaintenanceImportItem,
)
from backend.models.news import NewsArticle  # noqa: F401

from backend.intelligence.article_service import (
    ARTICLE_PROMPT_HASH,
    ARTICLE_PROMPT_VERSION,
    article_source_content_hash,
)
from backend.intelligence.hashing import canonical_hash
from backend.intelligence.schemas import ArticleIntelligenceOutput
from backend.maintenance.article_intelligence.contracts import ImportCandidate, StableArticleIdentity
from backend.maintenance.article_intelligence.prompts import REGISTRY_REVISION
from backend.maintenance.article_intelligence.services import MaintenanceImportService


DATABASE_URL = os.getenv("PHASE7_POSTGRES_URL")
WORKERS = 4
REPETITIONS = 3
LOCK_TIMEOUT_MS = 5_000
STATEMENT_TIMEOUT_MS = 10_000

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DATABASE_URL,
        reason="PHASE7_POSTGRES_URL is required for disposable PostgreSQL publication races",
    ),
]


@dataclass
class WorkerEvidence:
    worker: str
    batch_id: str
    client_publish_id: str
    transaction_started: float | None = None
    publish_started: float | None = None
    publish_returned: float | None = None
    completed: float | None = None
    outcome: str | None = None
    revision: int | None = None
    error_type: str | None = None
    error: str | None = None


async def _setup(engine, batch_count: int) -> tuple[int, list[UUID], ImportCandidate]:
    marker = uuid4().hex
    published_at = datetime.now(timezone.utc).replace(tzinfo=None)
    async with engine.begin() as connection:
        article_id = (await connection.execute(text(
            "INSERT INTO news_articles (finnhub_id, ticker, title, summary, article_url, pub_date) "
            "VALUES (:external_id, 'SPY', 'publication race', 'same logical source', :url, :published_at) "
            "RETURNING id"
        ), {
            "external_id": marker, "url": f"https://phase7.invalid/publication/{marker}",
            "published_at": published_at,
        })).scalar_one()
        article = NewsArticle(
            id=article_id, finnhub_id=marker, ticker="SPY", title="publication race",
            summary="same logical source", article_url=f"https://phase7.invalid/publication/{marker}",
            pub_date=published_at,
        )
        source_hash = article_source_content_hash(article)
        input_hash = canonical_hash({"source": source_hash, "prompt": ARTICLE_PROMPT_HASH})
        batch_ids: list[UUID] = []
        for _ in range(batch_count):
            batch_id = uuid4()
            batch_ids.append(batch_id)
            await connection.execute(text(
                "INSERT INTO article_intelligence_maintenance_batches ("
                "id, client_request_id, schema_version, state, requested_tickers, requested_count, "
                "exported_count, prompt_version, prompt_hash, registry_revision, expires_at"
                ") VALUES ("
                ":id, :request_id, 'article-intelligence-maintenance.v1', 'GENERATING', '[\"SPY\"]', 1, "
                "1, :prompt_version, :prompt_hash, :registry_revision, now() + interval '1 day')"
            ), {
                "id": batch_id, "request_id": uuid4(), "prompt_version": ARTICLE_PROMPT_VERSION,
                "prompt_hash": ARTICLE_PROMPT_HASH, "registry_revision": REGISTRY_REVISION,
            })
    candidate = ImportCandidate(
        artifact_client_id=uuid4(),
        stable_article_identity=StableArticleIdentity(kind="finnhub_id", value=marker),
        ticker="SPY", source_content_hash=source_hash, prompt_version=ARTICLE_PROMPT_VERSION,
        prompt_hash=ARTICLE_PROMPT_HASH, input_hash=input_hash, export_revision_hint=1,
        provider="ollama", model="llama3.1:8b", generated_at=datetime.now(timezone.utc),
        status="completed", output=ArticleIntelligenceOutput(
            summary="Race output", sentiment="neutral", confidence=7, importance_score=6,
            market_impact="Impact", short_term_outlook="Short", long_term_outlook="Long",
        ),
    )
    return article_id, batch_ids, candidate


async def _cleanup(engine, article_id: int, batch_ids: list[UUID]) -> None:
    async with engine.begin() as connection:
        await connection.execute(text(
            "DELETE FROM article_intelligence_maintenance_batches WHERE id = ANY(:batch_ids)"
        ), {"batch_ids": batch_ids})
        await connection.execute(text(
            "DELETE FROM article_intelligence WHERE article_id = :article_id"
        ), {"article_id": article_id})
        await connection.execute(text("DELETE FROM news_articles WHERE id = :article_id"), {"article_id": article_id})


async def _snapshot(engine, article_id: int, batch_ids: list[UUID]) -> dict:
    async with engine.connect() as connection:
        artifacts = (await connection.execute(text(
            "SELECT id, generation_revision, status FROM article_intelligence "
            "WHERE article_id=:article_id ORDER BY generation_revision"
        ), {"article_id": article_id})).mappings().all()
        imports = (await connection.execute(text(
            "SELECT batch_id, artifact_client_id, client_publish_id, candidate_fingerprint, outcome, "
            "article_intelligence_id FROM article_intelligence_maintenance_import_items "
            "WHERE batch_id = ANY(:batch_ids) ORDER BY id"
        ), {"batch_ids": batch_ids})).mappings().all()
        batches = (await connection.execute(text(
            "SELECT id, client_publish_id, state, imported_count, already_exists_count, rejected_count "
            "FROM article_intelligence_maintenance_batches WHERE id = ANY(:batch_ids) ORDER BY id"
        ), {"batch_ids": batch_ids})).mappings().all()
        locks = (await connection.execute(text(
            "SELECT count(*) FROM pg_locks WHERE locktype='advisory' AND "
            "classid=hashtext('article_intelligence_generation')::oid"
        ))).scalar_one()
    return {
        "artifacts": [dict(row) for row in artifacts],
        "imports": [{key: str(value) if isinstance(value, UUID) else value for key, value in row.items()} for row in imports],
        "batches": [{key: str(value) if isinstance(value, UUID) else value for key, value in row.items()} for row in batches],
        "remaining_advisory_locks": locks,
    }


async def _publish_worker(session_factory, barrier, batch_id, publish_id, candidate, evidence):
    async with session_factory() as session:
        evidence.transaction_started = perf_counter()
        await session.execute(text(f"SET LOCAL lock_timeout='{LOCK_TIMEOUT_MS}ms'"))
        await session.execute(text(f"SET LOCAL statement_timeout='{STATEMENT_TIMEOUT_MS}ms'"))
        await barrier.wait()
        evidence.publish_started = perf_counter()
        try:
            _, outcomes = await MaintenanceImportService(session).publish(
                batch_id, publish_id, [candidate], dry_run=False,
            )
            evidence.publish_returned = perf_counter()
            evidence.outcome = outcomes[0].outcome
            evidence.revision = outcomes[0].generation_revision
        except Exception as exc:
            evidence.error_type = type(exc).__name__
            evidence.error = str(exc)
        finally:
            evidence.completed = perf_counter()


def _emit(scenario: str, evidence: list[WorkerEvidence], snapshot: dict) -> None:
    print("PHASE7_PUBLICATION_RACE=" + json.dumps({
        "scenario": scenario, "worker_count": len(evidence),
        "workers": [asdict(row) for row in evidence], "database": snapshot,
    }, sort_keys=True, default=str))


async def test_same_logical_artifact_across_batches_is_created_once():
    engine = create_async_engine(DATABASE_URL, pool_size=WORKERS + 2, max_overflow=0)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        for repetition in range(REPETITIONS):
            article_id, batch_ids, candidate = await _setup(engine, WORKERS)
            barrier = asyncio.Barrier(WORKERS)
            evidence = [WorkerEvidence(
                worker=f"logical-{repetition}-{index}", batch_id=str(batch_id),
                client_publish_id=str(uuid4()),
            ) for index, batch_id in enumerate(batch_ids)]
            try:
                await asyncio.wait_for(asyncio.gather(*(
                    _publish_worker(sessions, barrier, batch_id, UUID(row.client_publish_id), candidate, row)
                    for batch_id, row in zip(batch_ids, evidence)
                )), timeout=15)
                snapshot = await _snapshot(engine, article_id, batch_ids)
                _emit(f"same-logical-artifact-{repetition}", evidence, snapshot)
                assert all(row.error is None for row in evidence)
                assert len(snapshot["artifacts"]) == 1
                assert [row.outcome for row in evidence].count("created") == 1
                assert [row.outcome for row in evidence].count("already_exists") == WORKERS - 1
                assert len(snapshot["imports"]) == WORKERS
                assert len({row["candidate_fingerprint"] for row in snapshot["imports"]}) == 1
                assert len({row["article_intelligence_id"] for row in snapshot["imports"]}) == 1
                assert [row["outcome"] for row in snapshot["imports"]].count("created") == 1
                assert [row["outcome"] for row in snapshot["imports"]].count("already_exists") == WORKERS - 1
                assert all(row["state"] == "COMPLETED" for row in snapshot["batches"])
                assert sum(row["imported_count"] for row in snapshot["batches"]) == 1
                assert sum(row["already_exists_count"] for row in snapshot["batches"]) == WORKERS - 1
                assert sum(row["rejected_count"] for row in snapshot["batches"]) == 0
                assert snapshot["remaining_advisory_locks"] == 0
            finally:
                await _cleanup(engine, article_id, batch_ids)
    finally:
        await engine.dispose()


async def test_same_client_publish_id_has_one_winner_and_safe_retry():
    engine = create_async_engine(DATABASE_URL, pool_size=WORKERS + 2, max_overflow=0)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        for repetition in range(REPETITIONS):
            article_id, batch_ids, candidate = await _setup(engine, WORKERS)
            shared_publish_id = uuid4()
            barrier = asyncio.Barrier(WORKERS)
            evidence = [WorkerEvidence(
                worker=f"shared-id-{repetition}-{index}", batch_id=str(batch_id),
                client_publish_id=str(shared_publish_id),
            ) for index, batch_id in enumerate(batch_ids)]
            try:
                await asyncio.wait_for(asyncio.gather(*(
                    _publish_worker(sessions, barrier, batch_id, shared_publish_id, candidate, row)
                    for batch_id, row in zip(batch_ids, evidence)
                )), timeout=15)
                race_snapshot = await _snapshot(engine, article_id, batch_ids)
                _emit(f"shared-client-publish-id-{repetition}", evidence, race_snapshot)

                winners = [row for row in evidence if row.error is None]
                losers = [row for row in evidence if row.error is not None]
                assert len(winners) == 1
                assert winners[0].outcome == "created"
                assert len(losers) == WORKERS - 1
                assert all(row.error_type == "ValueError" for row in losers)
                assert all(
                    row.error == "publication conflicted with a concurrent request; retry safely"
                    for row in losers
                )
                assert len(race_snapshot["artifacts"]) == 1
                assert len(race_snapshot["imports"]) == 1
                assert sum(row["state"] == "COMPLETED" for row in race_snapshot["batches"]) == 1
                assert sum(row["state"] == "GENERATING" for row in race_snapshot["batches"]) == WORKERS - 1
                assert sum(row["imported_count"] for row in race_snapshot["batches"]) == 1
                assert sum(row["already_exists_count"] for row in race_snapshot["batches"]) == 0
                assert sum(row["rejected_count"] for row in race_snapshot["batches"]) == 0
                assert race_snapshot["remaining_advisory_locks"] == 0

                retry_evidence = []
                for index, loser in enumerate(losers):
                    fresh_publish_id = uuid4()
                    row = WorkerEvidence(
                        worker=f"shared-id-{repetition}-retry-{index}",
                        batch_id=loser.batch_id,
                        client_publish_id=str(fresh_publish_id),
                    )
                    retry_evidence.append(row)
                    await asyncio.wait_for(
                        _publish_worker(
                            sessions, asyncio.Barrier(1), UUID(loser.batch_id),
                            fresh_publish_id, candidate, row,
                        ),
                        timeout=15,
                    )

                final_snapshot = await _snapshot(engine, article_id, batch_ids)
                _emit(f"shared-client-publish-id-{repetition}-loser-retries", retry_evidence, final_snapshot)
                assert all(row.error is None for row in retry_evidence)
                assert all(row.outcome == "already_exists" for row in retry_evidence)
                assert len(final_snapshot["artifacts"]) == 1
                assert len(final_snapshot["imports"]) == WORKERS
                assert [row["outcome"] for row in final_snapshot["imports"]].count("created") == 1
                assert [row["outcome"] for row in final_snapshot["imports"]].count("already_exists") == WORKERS - 1
                assert all(row["state"] == "COMPLETED" for row in final_snapshot["batches"])
                assert sum(row["imported_count"] for row in final_snapshot["batches"]) == 1
                assert sum(row["already_exists_count"] for row in final_snapshot["batches"]) == WORKERS - 1
                assert sum(row["rejected_count"] for row in final_snapshot["batches"]) == 0
                assert final_snapshot["remaining_advisory_locks"] == 0
            finally:
                await _cleanup(engine, article_id, batch_ids)
    finally:
        await engine.dispose()