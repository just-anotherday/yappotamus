"""Phase 1 maintenance protocol and authority-boundary tests."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from backend.intelligence.schemas import ArticleIntelligenceOutput
from backend.maintenance.article_intelligence.contracts import ImportCandidate, StableArticleIdentity
from backend.maintenance.article_intelligence.identity import candidate_fingerprint, stable_article_identity
from backend.maintenance.article_intelligence.lifecycle import BatchState, transition_batch
from backend.maintenance.article_intelligence.composition import build_maintenance_provider
from backend.maintenance.article_intelligence.prompts import PromptCompatibilityRegistry
from backend.models.news import NewsArticle
from backend.models.maintenance import (
    ArticleIntelligenceMaintenanceBatch,
    ArticleIntelligenceMaintenanceExportItem,
    ArticleIntelligenceMaintenanceImportItem,
)


def _output() -> ArticleIntelligenceOutput:
    return ArticleIntelligenceOutput(
        summary="Summary", sentiment="neutral", confidence=7, importance_score=6,
        market_impact="Impact", short_term_outlook="Short", long_term_outlook="Long",
    )


def test_import_candidate_is_strict_ollama_only_and_has_no_authoritative_revision():
    payload = {
        "artifact_client_id": uuid4(), "stable_article_identity": {"kind": "finnhub_id", "value": "123"},
        "ticker": "SPY", "source_content_hash": "a" * 64,
        "prompt_version": "article-intelligence-v1", "prompt_hash": "b" * 64,
        "input_hash": "c" * 64, "provider": "ollama", "model": "local-model",
        "generated_at": datetime.now(timezone.utc), "status": "completed", "output": _output(),
    }
    candidate = ImportCandidate.model_validate(payload)
    assert "generation_revision" not in type(candidate).model_fields
    with pytest.raises(ValidationError):
        ImportCandidate.model_validate({**payload, "provider": "openai"})
    with pytest.raises(ValidationError):
        ImportCandidate.model_validate({**payload, "generation_revision": 9})


def test_stable_article_identity_prefers_external_id_and_never_uses_database_id():
    article = NewsArticle(id=999, finnhub_id=" external-42 ", article_url="https://Example.com/a#fragment")
    assert stable_article_identity(article) == StableArticleIdentity(kind="finnhub_id", value="external-42")
    article.finnhub_id = None
    fallback = stable_article_identity(article)
    assert fallback.kind == "article_url_hash"
    assert fallback.value != "999"


def test_candidate_fingerprint_is_deterministic_and_output_sensitive():
    values = dict(
        stable_identity=StableArticleIdentity(kind="finnhub_id", value="42"),
        source_content_hash="a" * 64, prompt_hash="b" * 64, input_hash="c" * 64,
        provider="ollama", model="local", output=_output(),
    )
    assert candidate_fingerprint(**values) == candidate_fingerprint(**values)
    changed = {**values, "output": _output().model_copy(update={"summary": "Different"})}
    assert candidate_fingerprint(**values) != candidate_fingerprint(**changed)


def test_batch_lifecycle_requires_valid_transitions_and_explicit_recovery():
    assert transition_batch(BatchState.CREATED, BatchState.EXPORTING) == BatchState.EXPORTING
    assert transition_batch(BatchState.PARTIAL, BatchState.PUBLISHING) == BatchState.PUBLISHING
    with pytest.raises(ValueError, match="invalid maintenance batch transition"):
        transition_batch(BatchState.CREATED, BatchState.COMPLETED)
    with pytest.raises(ValueError):
        transition_batch(BatchState.FAILED, BatchState.GENERATING)
    assert transition_batch(BatchState.FAILED, BatchState.GENERATING, recovery=True) == BatchState.GENERATING
    with pytest.raises(ValueError):
        transition_batch(BatchState.COMPLETED, BatchState.PUBLISHING, recovery=True)


def test_prompt_registry_is_production_owned_and_rejects_mismatch():
    registry = PromptCompatibilityRegistry()
    compatibility = registry.compatibility()
    assert compatibility.current in compatibility.accepted_versions
    assert registry.require_compatible(
        compatibility.current.version, compatibility.current.hash,
    ) == compatibility.current
    with pytest.raises(ValueError, match="production-compatible"):
        registry.require_compatible(compatibility.current.version, "0" * 64)


def test_maintenance_composition_is_structurally_ollama_only(monkeypatch):
    monkeypatch.setenv("MAINTENANCE_AI_PROVIDER", "ollama")
    monkeypatch.setenv("OLLAMA_MODEL", "local-model")
    monkeypatch.setenv("MAINTENANCE_OLLAMA_ALLOWED_MODELS", "local-model")
    providers, policy = build_maintenance_provider()
    assert set(providers) == {"ollama"}
    assert "openai" not in providers
    assert policy._profiles["maintenance"].fallback_chain == ()
    monkeypatch.setenv("MAINTENANCE_AI_PROVIDER", "openai")
    with pytest.raises(ValueError, match="must be ollama"):
        build_maintenance_provider()


def test_maintenance_persistence_has_idempotency_and_snapshot_constraints():
    batch_constraints = {item.name for item in ArticleIntelligenceMaintenanceBatch.__table__.constraints}
    export_constraints = {item.name for item in ArticleIntelligenceMaintenanceExportItem.__table__.constraints}
    import_constraints = {item.name for item in ArticleIntelligenceMaintenanceImportItem.__table__.constraints}
    assert "client_request_id" in ArticleIntelligenceMaintenanceBatch.__table__.columns
    assert "uq_ai_maintenance_export_article" in export_constraints
    assert "uq_ai_maintenance_export_ordinal" in export_constraints
    assert "uq_ai_maintenance_import_client_item" in import_constraints
    assert ArticleIntelligenceMaintenanceBatch.__table__.c.client_request_id.unique