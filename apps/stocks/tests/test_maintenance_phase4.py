"""Focused Phase 4 API, policy, replay, and reconciliation tests."""

from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI

from backend.config.settings import Settings
from backend.intelligence.composition import build_routing_policy
from backend.maintenance.article_intelligence.lifecycle import BatchState
from backend.maintenance.article_intelligence.prompts import (
    PromptCompatibilityRegistry, PromptHashMismatch, UnknownPromptVersion,
)
from backend.maintenance.article_intelligence.services import MaintenanceImportService, reconcile_batch
from backend.routers.maintenance_intelligence import router as maintenance_router


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.asyncio
async def test_maintenance_auth_is_separate_from_browser_auth(monkeypatch):
    monkeypatch.setenv("MAINTENANCE_API_ENABLED", "true")
    monkeypatch.setenv("MAINTENANCE_API_TOKEN", "maintenance-secret")
    monkeypatch.setenv("APP_ACCESS_TOKEN", "browser-secret")
    app = FastAPI()
    app.include_router(maintenance_router)
    transport = httpx.ASGITransport(app=app)
    url = "/api/maintenance/article-intelligence/v1/prompt-compatibility"
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        assert (await client.get(url)).status_code == 401
        assert (await client.get(url, headers={"Authorization": "Bearer browser-secret"})).status_code == 401
        response = await client.get(url, headers={"Authorization": "Bearer maintenance-secret"})
    assert response.status_code == 200
    assert response.json()["artifact_type"] == "article_intelligence"


@pytest.mark.asyncio
async def test_disabled_maintenance_api_is_not_exposed(monkeypatch):
    monkeypatch.setenv("MAINTENANCE_API_ENABLED", "false")
    monkeypatch.setenv("MAINTENANCE_API_TOKEN", "maintenance-secret")
    app = FastAPI()
    app.include_router(maintenance_router)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/maintenance/article-intelligence/v1/prompt-compatibility",
            headers={"Authorization": "Bearer maintenance-secret"},
        )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_export_and_import_routes_require_maintenance_authorization(monkeypatch):
    monkeypatch.setenv("MAINTENANCE_API_ENABLED", "true")
    monkeypatch.setenv("MAINTENANCE_API_TOKEN", "maintenance-secret")
    app = FastAPI()
    app.include_router(maintenance_router)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        assert (await client.post("/api/maintenance/article-intelligence/v1/export-sessions", json={})).status_code == 401
        assert (await client.post("/api/maintenance/article-intelligence/v1/imports", json={})).status_code == 401


@pytest.mark.asyncio
async def test_maintenance_request_size_is_bounded(monkeypatch):
    monkeypatch.setenv("MAINTENANCE_API_ENABLED", "true")
    monkeypatch.setenv("MAINTENANCE_API_TOKEN", "maintenance-secret")
    monkeypatch.setenv("MAINTENANCE_MAX_REQUEST_BYTES", "10")
    app = FastAPI()
    app.include_router(maintenance_router)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/maintenance/article-intelligence/v1/export-sessions",
            content=b"01234567890",
            headers={"Authorization": "Bearer maintenance-secret", "content-type": "application/json"},
        )
    assert response.status_code == 413


def test_maintenance_token_is_only_required_when_feature_enabled(monkeypatch):
    monkeypatch.setenv("APP_ACCESS_TOKEN", "browser")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://test/test")
    monkeypatch.delenv("MAINTENANCE_API_TOKEN", raising=False)
    monkeypatch.setenv("MAINTENANCE_API_ENABLED", "false")
    Settings().validate()
    monkeypatch.setenv("MAINTENANCE_API_ENABLED", "true")
    with pytest.raises(EnvironmentError, match="MAINTENANCE_API_TOKEN"):
        Settings().validate()


def test_manual_openai_remains_available_but_automatic_policy_is_blocked(monkeypatch):
    monkeypatch.setenv("INTELLIGENCE_ROUTING_PROFILE", "premium-only")
    monkeypatch.setenv("OPENAI_MANUAL_GENERATION_ENABLED", "true")
    monkeypatch.setenv("OPENAI_AUTOMATIC_GENERATION_ENABLED", "false")
    assert "premium-only" in build_routing_policy(automatic=False)._profiles
    with pytest.raises(ValueError, match="automatic OpenAI generation is disabled"):
        build_routing_policy(automatic=True)


def test_prompt_version_and_hash_failures_are_distinct():
    registry = PromptCompatibilityRegistry()
    current = registry.compatibility().current
    with pytest.raises(UnknownPromptVersion):
        registry.require_compatible("unknown-version", current.hash)
    with pytest.raises(PromptHashMismatch):
        registry.require_compatible(current.version, "0" * 64)


def test_batch_reconciliation_supports_partial_retry_then_completion():
    batch = SimpleNamespace(exported_count=2, imported_count=0, already_exists_count=0,
                            rejected_count=0, hash_mismatch_count=0, revision_conflict_count=0)
    partial_rows = [SimpleNamespace(outcome="created"), SimpleNamespace(outcome="rejected_source_hash_mismatch")]
    assert reconcile_batch(batch, partial_rows) == BatchState.PARTIAL
    assert (batch.imported_count, batch.rejected_count, batch.hash_mismatch_count) == (1, 1, 1)
    completed_rows = [SimpleNamespace(outcome="created"), SimpleNamespace(outcome="already_exists")]
    assert reconcile_batch(batch, completed_rows) == BatchState.COMPLETED
    assert (batch.imported_count, batch.already_exists_count, batch.rejected_count) == (1, 1, 0)


@pytest.mark.asyncio
async def test_exact_replay_preserves_created_while_later_duplicate_is_already_exists():
    artifact = SimpleNamespace(id=91, generation_revision=3)
    session = SimpleNamespace(get=lambda *args: None)

    async def get(*args):
        return artifact

    session.get = get
    prior = SimpleNamespace(
        artifact_client_id=uuid4(), article_intelligence_id=91, outcome="created",
        candidate_fingerprint="a" * 64, reason_code=None,
    )
    replay = await MaintenanceImportService._prior_outcome(session, prior, exact_replay=True)
    duplicate = await MaintenanceImportService._prior_outcome(session, prior)
    assert replay.outcome == "created"
    assert duplicate.outcome == "already_exists"


def test_dry_run_and_real_import_audits_have_separate_idempotency_keys():
    constraint = next(item for item in __import__(
        "backend.models.maintenance", fromlist=["ArticleIntelligenceMaintenanceImportItem"]
    ).ArticleIntelligenceMaintenanceImportItem.__table__.constraints
                      if item.name == "uq_ai_maintenance_import_client_item")
    assert [column.name for column in constraint.columns] == ["batch_id", "artifact_client_id", "is_dry_run"]


def test_publish_query_locks_batch_row_and_completed_batches_are_replay_only():
    import inspect

    source = inspect.getsource(MaintenanceImportService.publish)
    assert ".with_for_update()" in source
    assert "completed batch accepts exact request replays only" in source
    assert "publish_request_hash" in source


def test_publish_request_hash_is_persisted_for_full_payload_replay_detection():
    from backend.models.maintenance import ArticleIntelligenceMaintenanceImportItem

    column = ArticleIntelligenceMaintenanceImportItem.__table__.c.publish_request_hash
    assert not column.nullable
    assert column.type.length == 64
