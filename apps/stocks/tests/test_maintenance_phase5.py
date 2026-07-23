"""Phase 5 local coordinator, durable run-store, and resume tests."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

import httpx
import pytest

from backend.intelligence.article_service import ARTICLE_PROMPT_HASH, ARTICLE_PROMPT_VERSION
from backend.intelligence.schemas import ArticleIntelligenceOutput
from backend.maintenance.article_intelligence.clients import (
    ExportClient, MaintenanceClientError, PromptCompatibilityClient,
)
from backend.maintenance.article_intelligence.contracts import ExportArticle, ImportOutcome, StableArticleIdentity
from backend.maintenance.article_intelligence.coordinator import MaintenanceCoordinator
from backend.maintenance.article_intelligence.prompts import PromptCompatibilityRegistry
from backend.maintenance.article_intelligence.run_store import SQLiteMaintenanceRunStore


def _export(index: int) -> ExportArticle:
    digit = f"{index:x}"
    return ExportArticle(
        stable_article_identity=StableArticleIdentity(kind="finnhub_id", value=str(index)),
        ticker="SPY", title=f"Article {index}", summary="Source", article_url=f"https://example.com/{index}",
        published_at=datetime.now(timezone.utc), source_content_hash=digit * 64,
        prompt_version=ARTICLE_PROMPT_VERSION, prompt_hash=ARTICLE_PROMPT_HASH,
        input_hash=f"{index + 8:x}" * 64, revision_hint=1,
    )


def _output(index: int) -> ArticleIntelligenceOutput:
    return ArticleIntelligenceOutput(
        summary=f"Generated {index}", sentiment="neutral", confidence=7, importance_score=6,
        market_impact="Impact", short_term_outlook="Short", long_term_outlook="Long",
    )


class Prompts:
    async def get(self):
        return PromptCompatibilityRegistry().compatibility()


class Exports:
    def __init__(self, items):
        self.batch_id = uuid4(); self._items = items; self.create_calls = 0; self.item_calls = 0

    async def create(self, request):
        self.create_calls += 1
        return {"batch_id": self.batch_id}

    async def items(self, batch_id):
        self.item_calls += 1
        return self._items


class Generator:
    def __init__(self, fail_once: set[str] | None = None):
        self.fail_once = fail_once or set(); self.calls = []

    async def generate(self, article, *, model, artifact_identity):
        self.calls.append(artifact_identity)
        if artifact_identity in self.fail_once:
            self.fail_once.remove(artifact_identity)
            raise ConnectionError("ollama interrupted")
        return _output(int(article.stable_article_identity.value)), {
            "metrics": {"quality": 1.0}, "attempt_number": 1, "duration_ms": 4,
            "validation": {"accepted": True},
        }


class Publisher:
    def __init__(self, interrupt_once: bool = False, reject_ids: set[UUID] | None = None):
        self.interrupt_once = interrupt_once; self.reject_ids = reject_ids or set(); self.requests = []

    async def publish(self, request, *, dry_run):
        self.requests.append((request, dry_run))
        if self.interrupt_once:
            self.interrupt_once = False
            raise MaintenanceClientError("network lost", retryable=True)
        return [ImportOutcome(
            artifact_client_id=item.artifact_client_id,
            outcome="rejected_source_hash_mismatch" if item.artifact_client_id in self.reject_ids else "created",
        ) for item in request.artifacts]


def _coordinator(tmp_path, exports, generator=None, publisher=None):
    return MaintenanceCoordinator(
        SQLiteMaintenanceRunStore(tmp_path / "runs.sqlite3"), Prompts(), exports,
        publisher or Publisher(), generator or Generator(),
    )


@pytest.mark.asyncio
async def test_run_store_is_durable_and_fetch_is_idempotent(tmp_path):
    exports = Exports([_export(1), _export(2)])
    coordinator = _coordinator(tmp_path, exports)
    run = coordinator.create_run(model="llama3.2")
    first = await coordinator.fetch(run.run_id)
    reopened = _coordinator(tmp_path, exports)
    second = await reopened.fetch(run.run_id)
    assert first.exported == second.exported == 2
    assert exports.create_calls == 1
    assert exports.item_calls == 1
    assert reopened.status(run.run_id).run.prompt_hash == ARTICLE_PROMPT_HASH


@pytest.mark.asyncio
async def test_generation_interruption_resumes_only_missing_item(tmp_path):
    items = [_export(1), _export(2)]
    generator = Generator({items[1].input_hash})
    coordinator = _coordinator(tmp_path, Exports(items), generator=generator)
    run = coordinator.create_run(model="llama3.2")
    await coordinator.fetch(run.run_id)
    partial = await coordinator.generate(run.run_id)
    assert (partial.generated, partial.retryable, partial.run.state) == (1, 1, "PARTIAL")
    resumed = await coordinator.resume(run.run_id)
    assert (resumed.generated, resumed.retryable, resumed.run.state) == (2, 0, "READY_TO_PUBLISH")
    assert generator.calls.count(items[0].input_hash) == 1
    assert generator.calls.count(items[1].input_hash) == 2


@pytest.mark.asyncio
async def test_publish_interruption_reuses_persisted_publish_id(tmp_path):
    publisher = Publisher(interrupt_once=True)
    coordinator = _coordinator(tmp_path, Exports([_export(1)]), publisher=publisher)
    run = coordinator.create_run(model="llama3.2")
    await coordinator.fetch(run.run_id); await coordinator.generate(run.run_id)
    with pytest.raises(MaintenanceClientError):
        await coordinator.publish(run.run_id)
    interrupted = coordinator.status(run.run_id).run
    assert interrupted.state == "PUBLISH_INTERRUPTED"
    assert interrupted.pending_publish_id is not None
    assert interrupted.last_error == "network lost"
    coordinator = _coordinator(tmp_path, Exports([_export(1)]), publisher=publisher)
    completed = await coordinator.resume(run.run_id, publish=True)
    assert completed.run.state == "COMPLETED"
    assert completed.run.last_error is None
    assert publisher.requests[0][0].client_publish_id == publisher.requests[1][0].client_publish_id
    assert coordinator.status(run.run_id).run.pending_publish_id is None


@pytest.mark.asyncio
async def test_dry_run_isolated_then_real_publish_completes(tmp_path):
    publisher = Publisher()
    coordinator = _coordinator(tmp_path, Exports([_export(1)]), publisher=publisher)
    run = coordinator.create_run(model="llama3.2")
    await coordinator.fetch(run.run_id); await coordinator.generate(run.run_id)
    dry = await coordinator.publish(run.run_id, dry_run=True)
    assert dry.run.state == "READY_TO_PUBLISH"
    assert dry.published == 0
    real = await coordinator.publish(run.run_id)
    assert real.run.state == "COMPLETED"
    assert real.published == 1
    assert [dry_run for _, dry_run in publisher.requests] == [True, False]


@pytest.mark.asyncio
async def test_partial_publication_retries_only_rejected_item(tmp_path):
    items = [_export(1), _export(2)]
    rejected_id = UUID(items[1].input_hash[:32])
    publisher = Publisher(reject_ids={rejected_id})
    coordinator = _coordinator(tmp_path, Exports(items), publisher=publisher)
    run = coordinator.create_run(model="llama3.2")
    await coordinator.fetch(run.run_id); await coordinator.generate(run.run_id)
    partial = await coordinator.publish(run.run_id)
    assert (partial.published, partial.rejected, partial.run.state) == (1, 1, "PARTIAL")
    publisher.reject_ids.clear()
    completed = await coordinator.publish(run.run_id)
    assert completed.run.state == "COMPLETED"
    assert len(publisher.requests[1][0].artifacts) == 1
    assert publisher.requests[1][0].artifacts[0].artifact_client_id == rejected_id


@pytest.mark.asyncio
async def test_prompt_mismatch_stops_before_local_generation(tmp_path):
    item = _export(1).model_copy(update={"prompt_hash": "0" * 64})
    generator = Generator()
    coordinator = _coordinator(tmp_path, Exports([item]), generator=generator)
    run = coordinator.create_run(model="llama3.2")
    with pytest.raises(ValueError, match="export session prompt"):
        await coordinator.fetch(run.run_id)
    assert not generator.calls


@pytest.mark.asyncio
async def test_generator_exhaustion_is_retryable_but_configuration_error_is_not(tmp_path):
    class Errors:
        def __init__(self): self.calls = 0
        async def generate(self, *args, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise ValueError("quality validation exhausted: provider unavailable")
            raise ValueError("maintenance Ollama model is not allowlisted")

    coordinator = _coordinator(tmp_path, Exports([_export(1), _export(2)]), generator=Errors())
    run = coordinator.create_run(model="bad-model")
    await coordinator.fetch(run.run_id)
    result = await coordinator.generate(run.run_id)
    assert result.retryable == 1
    stored = coordinator.store.items(run.run_id)
    assert stored[0].retryable
    assert not stored[1].retryable


@pytest.mark.asyncio
async def test_empty_export_completes_as_idempotent_noop(tmp_path):
    exports = Exports([])
    generator = Generator()
    publisher = Publisher()
    coordinator = _coordinator(tmp_path, exports, generator=generator, publisher=publisher)
    run = coordinator.create_run(model="llama3.2")
    completed = await coordinator.resume(run.run_id, publish=True)
    assert (completed.run.state, completed.exported, completed.generated, completed.published) == (
        "COMPLETED", 0, 0, 0,
    )
    assert not generator.calls
    assert not publisher.requests
    repeated = await coordinator.resume(run.run_id, publish=True)
    assert repeated.run.state == "COMPLETED"
    assert exports.create_calls == 1
    assert exports.item_calls == 1


def test_client_request_id_is_idempotent_and_model_is_immutable(tmp_path):
    coordinator = _coordinator(tmp_path, Exports([]))
    client_request_id = uuid4()
    first = coordinator.create_run(model="llama3.2", client_request_id=client_request_id)
    repeated = coordinator.create_run(
        model="llama3.2", client_request_id=client_request_id, run_id=uuid4(),
    )
    assert repeated == first
    with pytest.raises(ValueError, match="different model"):
        coordinator.create_run(model="other-model", client_request_id=client_request_id)


@pytest.mark.asyncio
async def test_http_clients_classify_retryable_and_non_json_errors():
    responses = iter([
        httpx.Response(503, json={"detail": "temporarily unavailable"}),
        httpx.Response(400, text="plain-text failure"),
    ])
    client = PromptCompatibilityClient(
        "https://production.example", "secret", transport=httpx.MockTransport(lambda request: next(responses)),
    )
    with pytest.raises(MaintenanceClientError) as retryable:
        await client.get()
    assert retryable.value.retryable
    assert retryable.value.status_code == 503
    assert str(retryable.value) == "temporarily unavailable"
    with pytest.raises(MaintenanceClientError) as terminal:
        await client.get()
    assert not terminal.value.retryable
    assert terminal.value.status_code == 400
    assert str(terminal.value) == "plain-text failure"


@pytest.mark.asyncio
async def test_export_client_paginates_and_generates_authorization_header():
    batch_id = uuid4()
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        offset = int(request.url.params["offset"])
        items = [_export(1), _export(2)] if offset == 0 else [_export(3)]
        return httpx.Response(200, json={"items": [item.model_dump(mode="json") for item in items]})

    client = ExportClient(
        "https://production.example/", "maintenance-token", transport=httpx.MockTransport(handler),
    )
    items = await client.items(batch_id, page_size=2)
    assert [item.stable_article_identity.value for item in items] == ["1", "2", "3"]
    assert [request.url.params["offset"] for request in requests] == ["0", "2"]
    assert all(request.headers["Authorization"] == "Bearer maintenance-token" for request in requests)


@pytest.mark.asyncio
async def test_prompt_compatibility_client_retrieves_typed_contract():
    expected = PromptCompatibilityRegistry().compatibility()
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=expected.model_dump(mode="json"))

    client = PromptCompatibilityClient(
        "https://production.example", "token", transport=httpx.MockTransport(handler),
    )
    actual = await client.get()
    assert actual == expected
    assert seen[0].url.path.endswith("/prompt-compatibility")
    assert seen[0].headers["Authorization"] == "Bearer token"
