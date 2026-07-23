"""Focused real-PostgreSQL gate for maintenance request and item replay/idempotency."""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
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
    ArticleIntelligenceMaintenanceExportItem,
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
from backend.maintenance.article_intelligence.contracts import (
    ExportSessionCreate,
    ImportCandidate,
    StableArticleIdentity,
)
from backend.maintenance.article_intelligence.prompts import REGISTRY_REVISION
from backend.maintenance.article_intelligence.services import (
    MaintenanceExportService,
    MaintenanceImportService,
)


DATABASE_URL = os.getenv("PHASE7_POSTGRES_URL")
LOCK_TIMEOUT_MS = 5_000
STATEMENT_TIMEOUT_MS = 10_000
OPERATION_TIMEOUT_SECONDS = 15

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DATABASE_URL,
        reason="PHASE7_POSTGRES_URL is required for disposable PostgreSQL replay/idempotency tests",
    ),
]


async def _limits(session) -> None:
    await session.execute(text(f"SET LOCAL lock_timeout='{LOCK_TIMEOUT_MS}ms'"))
    await session.execute(text(f"SET LOCAL statement_timeout='{STATEMENT_TIMEOUT_MS}ms'"))


async def _setup(engine, *, batch: bool = True) -> tuple[int, UUID | None, ImportCandidate]:
    marker = uuid4().hex
    published_at = datetime.now(timezone.utc).replace(tzinfo=None)
    batch_id = uuid4() if batch else None
    async with engine.begin() as connection:
        article_id = (await connection.execute(text(
            "INSERT INTO news_articles (finnhub_id, ticker, title, summary, article_url, pub_date) "
            "VALUES (:external_id, 'SPY', 'replay gate', 'idempotency source', :url, :published_at) "
            "RETURNING id"
        ), {
            "external_id": marker,
            "url": f"https://phase7.invalid/replay/{marker}",
            "published_at": published_at,
        })).scalar_one()
        if batch_id is not None:
            await connection.execute(text(
                "INSERT INTO article_intelligence_maintenance_batches ("
                "id, client_request_id, schema_version, state, requested_tickers, requested_count, "
                "exported_count, prompt_version, prompt_hash, registry_revision, expires_at"
                ") VALUES ("
                ":id, :request_id, 'article-intelligence-maintenance.v1', 'GENERATING', '[\"SPY\"]', 1, "
                "1, :prompt_version, :prompt_hash, :registry_revision, now() + interval '1 day')"
            ), {
                "id": batch_id,
                "request_id": uuid4(),
                "prompt_version": ARTICLE_PROMPT_VERSION,
                "prompt_hash": ARTICLE_PROMPT_HASH,
                "registry_revision": REGISTRY_REVISION,
            })
    article = NewsArticle(
        id=article_id,
        finnhub_id=marker,
        ticker="SPY",
        title="replay gate",
        summary="idempotency source",
        article_url=f"https://phase7.invalid/replay/{marker}",
        pub_date=published_at,
    )
    source_hash = article_source_content_hash(article)
    candidate = ImportCandidate(
        artifact_client_id=uuid4(),
        stable_article_identity=StableArticleIdentity(kind="finnhub_id", value=marker),
        ticker="SPY",
        source_content_hash=source_hash,
        prompt_version=ARTICLE_PROMPT_VERSION,
        prompt_hash=ARTICLE_PROMPT_HASH,
        input_hash=canonical_hash({"source": source_hash, "prompt": ARTICLE_PROMPT_HASH}),
        export_revision_hint=1,
        provider="ollama",
        model="llama3.1:8b",
        generated_at=datetime.now(timezone.utc),
        status="completed",
        output=ArticleIntelligenceOutput(
            summary="Replay output",
            sentiment="neutral",
            confidence=7,
            importance_score=6,
            market_impact="Impact",
            short_term_outlook="Short",
            long_term_outlook="Long",
        ),
    )
    return article_id, batch_id, candidate


async def _snapshot(engine, article_id: int, batch_id: UUID) -> dict:
    async with engine.connect() as connection:
        artifacts = (await connection.execute(text(
            "SELECT id, generation_revision FROM article_intelligence "
            "WHERE article_id=:article_id ORDER BY id"
        ), {"article_id": article_id})).mappings().all()
        imports = (await connection.execute(text(
            "SELECT id, artifact_client_id, client_publish_id, publish_request_hash, is_dry_run, "
            "article_intelligence_id, candidate_fingerprint, outcome FROM "
            "article_intelligence_maintenance_import_items WHERE batch_id=:batch_id ORDER BY id"
        ), {"batch_id": batch_id})).mappings().all()
        batch = (await connection.execute(text(
            "SELECT id, client_request_id, client_publish_id, state, imported_count, "
            "already_exists_count, rejected_count FROM article_intelligence_maintenance_batches "
            "WHERE id=:batch_id"
        ), {"batch_id": batch_id})).mappings().one()
    return {
        "artifacts": [dict(row) for row in artifacts],
        "imports": [{key: str(value) if isinstance(value, UUID) else value for key, value in row.items()} for row in imports],
        "batch": {key: str(value) if isinstance(value, UUID) else value for key, value in batch.items()},
    }


async def _cleanup(engine, article_id: int, batch_ids: list[UUID]) -> None:
    async with engine.begin() as connection:
        if batch_ids:
            await connection.execute(text(
                "DELETE FROM article_intelligence_maintenance_batches WHERE id = ANY(:batch_ids)"
            ), {"batch_ids": batch_ids})
        await connection.execute(text(
            "DELETE FROM article_intelligence WHERE article_id=:article_id"
        ), {"article_id": article_id})
        await connection.execute(text(
            "DELETE FROM news_articles WHERE id=:article_id"
        ), {"article_id": article_id})


def _emit(scenario: str, evidence: dict) -> None:
    print("PHASE7_REPLAY_IDEMPOTENCY=" + json.dumps({
        "scenario": scenario,
        **evidence,
    }, sort_keys=True, default=str))


async def test_client_request_id_exact_replay_is_stable_and_mismatch_is_rejected():
    engine = create_async_engine(DATABASE_URL, pool_size=2, max_overflow=0)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    article_id, _, _ = await _setup(engine, batch=False)
    request_id = uuid4()
    batch_ids: list[UUID] = []
    try:
        request = ExportSessionCreate(client_request_id=request_id, tickers=["SPY"], max_items=1)
        async with sessions() as session:
            await _limits(session)
            first = await asyncio.wait_for(
                MaintenanceExportService(session).create(request),
                timeout=OPERATION_TIMEOUT_SECONDS,
            )
            batch_ids.append(first.id)
        async with sessions() as session:
            await _limits(session)
            replay = await asyncio.wait_for(
                MaintenanceExportService(session).create(request),
                timeout=OPERATION_TIMEOUT_SECONDS,
            )
        assert replay.id == first.id

        async with sessions() as session:
            await _limits(session)
            with pytest.raises(ValueError, match="client_request_id replay payload does not match"):
                await asyncio.wait_for(
                    MaintenanceExportService(session).create(ExportSessionCreate(
                        client_request_id=request_id,
                        tickers=["SPY"],
                        max_items=2,
                    )),
                    timeout=OPERATION_TIMEOUT_SECONDS,
                )

        async with engine.connect() as connection:
            batches = (await connection.execute(text(
                "SELECT id, client_request_id, requested_tickers, requested_count, exported_count, state "
                "FROM article_intelligence_maintenance_batches WHERE client_request_id=:request_id"
            ), {"request_id": request_id})).mappings().all()
            exports = (await connection.execute(text(
                "SELECT id, batch_id, ordinal, article_id FROM article_intelligence_maintenance_export_items "
                "WHERE batch_id=:batch_id ORDER BY id"
            ), {"batch_id": first.id})).mappings().all()
        _emit("client-request-replay", {"batches": batches, "exports": exports})
        assert len(batches) == 1
        assert batches[0]["id"] == first.id
        assert batches[0]["requested_count"] == 1
        assert batches[0]["exported_count"] == 1
        assert batches[0]["state"] == "GENERATING"
        assert len(exports) == 1
    finally:
        await _cleanup(engine, article_id, batch_ids)
        await engine.dispose()


async def test_exact_publication_replay_preserves_original_outcome_and_rejects_payload_change():
    engine = create_async_engine(DATABASE_URL, pool_size=2, max_overflow=0)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    article_id, batch_id, candidate = await _setup(engine)
    assert batch_id is not None
    publish_id = uuid4()
    try:
        async with sessions() as session:
            await _limits(session)
            _, first = await asyncio.wait_for(
                MaintenanceImportService(session).publish(batch_id, publish_id, [candidate], dry_run=False),
                timeout=OPERATION_TIMEOUT_SECONDS,
            )
        before = await _snapshot(engine, article_id, batch_id)

        async with sessions() as session:
            await _limits(session)
            _, replay = await asyncio.wait_for(
                MaintenanceImportService(session).publish(batch_id, publish_id, [candidate], dry_run=False),
                timeout=OPERATION_TIMEOUT_SECONDS,
            )
        after_replay = await _snapshot(engine, article_id, batch_id)
        assert first[0].outcome == replay[0].outcome == "created"
        assert first[0].production_artifact_id == replay[0].production_artifact_id
        assert after_replay == before

        changed = candidate.model_copy(update={"quality_metrics": {"changed": True}})
        async with sessions() as session:
            await _limits(session)
            with pytest.raises(ValueError, match="client_publish_id replay payload does not match the original request"):
                await asyncio.wait_for(
                    MaintenanceImportService(session).publish(batch_id, publish_id, [changed], dry_run=False),
                    timeout=OPERATION_TIMEOUT_SECONDS,
                )
        after_mismatch = await _snapshot(engine, article_id, batch_id)
        _emit("exact-publication-replay", {
            "first_outcome": first[0],
            "replay_outcome": replay[0],
            "database": after_mismatch,
        })
        assert after_mismatch == before
        assert len(after_mismatch["artifacts"]) == 1
        assert len(after_mismatch["imports"]) == 1
        assert after_mismatch["batch"]["state"] == "COMPLETED"
        assert after_mismatch["batch"]["imported_count"] == 1
    finally:
        await _cleanup(engine, article_id, [batch_id])
        await engine.dispose()


async def test_failed_item_is_replaced_by_fresh_publication_retry_without_duplicate_audit():
    engine = create_async_engine(DATABASE_URL, pool_size=2, max_overflow=0)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    article_id, batch_id, candidate = await _setup(engine)
    assert batch_id is not None
    first_publish_id = uuid4()
    retry_publish_id = uuid4()
    rejected = candidate.model_copy(update={
        "stable_article_identity": StableArticleIdentity(kind="finnhub_id", value=uuid4().hex),
    })
    try:
        async with sessions() as session:
            await _limits(session)
            _, first = await asyncio.wait_for(
                MaintenanceImportService(session).publish(batch_id, first_publish_id, [rejected], dry_run=False),
                timeout=OPERATION_TIMEOUT_SECONDS,
            )
        partial = await _snapshot(engine, article_id, batch_id)
        assert first[0].outcome == "rejected_unknown_article"
        assert partial["batch"]["state"] == "PARTIAL"
        assert partial["batch"]["rejected_count"] == 1
        assert len(partial["imports"]) == 1

        async with sessions() as session:
            await _limits(session)
            _, retry = await asyncio.wait_for(
                MaintenanceImportService(session).publish(batch_id, retry_publish_id, [candidate], dry_run=False),
                timeout=OPERATION_TIMEOUT_SECONDS,
            )
        completed = await _snapshot(engine, article_id, batch_id)
        _emit("item-retry", {
            "initial_outcome": first[0],
            "retry_outcome": retry[0],
            "partial": partial,
            "completed": completed,
        })
        assert retry[0].outcome == "created"
        assert len(completed["artifacts"]) == 1
        assert len(completed["imports"]) == 1
        assert completed["imports"][0]["id"] == partial["imports"][0]["id"]
        assert completed["imports"][0]["client_publish_id"] == str(retry_publish_id)
        assert completed["imports"][0]["outcome"] == "created"
        assert completed["batch"]["state"] == "COMPLETED"
        assert completed["batch"]["imported_count"] == 1
        assert completed["batch"]["rejected_count"] == 0
    finally:
        await _cleanup(engine, article_id, [batch_id])
        await engine.dispose()


async def test_dry_run_and_real_publication_use_separate_item_idempotency_keys():
    engine = create_async_engine(DATABASE_URL, pool_size=2, max_overflow=0)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    article_id, batch_id, candidate = await _setup(engine)
    assert batch_id is not None
    dry_publish_id = uuid4()
    real_publish_id = uuid4()
    try:
        async with sessions() as session:
            await _limits(session)
            _, dry = await asyncio.wait_for(
                MaintenanceImportService(session).publish(batch_id, dry_publish_id, [candidate], dry_run=True),
                timeout=OPERATION_TIMEOUT_SECONDS,
            )
        after_dry = await _snapshot(engine, article_id, batch_id)
        assert dry[0].outcome == "created"
        assert len(after_dry["artifacts"]) == 0
        assert len(after_dry["imports"]) == 1
        assert after_dry["imports"][0]["is_dry_run"] is True
        assert after_dry["batch"]["state"] == "GENERATING"

        async with sessions() as session:
            await _limits(session)
            _, real = await asyncio.wait_for(
                MaintenanceImportService(session).publish(batch_id, real_publish_id, [candidate], dry_run=False),
                timeout=OPERATION_TIMEOUT_SECONDS,
            )
        final = await _snapshot(engine, article_id, batch_id)
        _emit("dry-run-real-item-keys", {
            "dry_outcome": dry[0],
            "real_outcome": real[0],
            "database": final,
        })
        assert real[0].outcome == "created"
        assert len(final["artifacts"]) == 1
        assert len(final["imports"]) == 2
        assert {row["is_dry_run"] for row in final["imports"]} == {False, True}
        assert len({row["artifact_client_id"] for row in final["imports"]}) == 1
        assert final["batch"]["state"] == "COMPLETED"
        assert final["batch"]["imported_count"] == 1
        assert final["batch"]["already_exists_count"] == 0
        assert final["batch"]["rejected_count"] == 0
    finally:
        await _cleanup(engine, article_id, [batch_id])
        await engine.dispose()