"""Regression tests for bounded maintenance request-body consumption."""

import json
from collections.abc import Iterable
from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI

from backend.config.database import get_async_session
from backend.maintenance.article_intelligence.contracts import ImportOutcome
from backend.maintenance.article_intelligence.services import MaintenanceImportService
from backend.routers.maintenance_intelligence import router as maintenance_router


MAINTENANCE_PATH = "/api/maintenance/article-intelligence/v1/imports"
AUTHORIZATION = (b"authorization", b"Bearer maintenance-secret")


async def _asgi_post(
    app: FastAPI,
    chunks: Iterable[bytes],
    *,
    headers: list[tuple[bytes, bytes]] | None = None,
) -> tuple[int, bytes, int]:
    """POST synthetic chunks and report how many receive calls the app made."""
    bodies = list(chunks)
    messages = [
        {
            "type": "http.request",
            "body": body,
            "more_body": index < len(bodies) - 1,
        }
        for index, body in enumerate(bodies)
    ]
    if not messages:
        messages.append({"type": "http.request", "body": b"", "more_body": False})

    receive_calls = 0
    sent: list[dict] = []

    async def receive():
        nonlocal receive_calls
        receive_calls += 1
        if messages:
            return messages.pop(0)
        return {"type": "http.disconnect"}

    async def send(message):
        sent.append(message)

    request_headers = [(b"host", b"test"), (b"content-type", b"application/json")]
    request_headers.extend(headers or [])
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": MAINTENANCE_PATH,
        "raw_path": MAINTENANCE_PATH.encode("ascii"),
        "query_string": b"",
        "headers": request_headers,
        "client": ("127.0.0.1", 12345),
        "server": ("test", 80),
    }
    await app(scope, receive, send)

    status = next(message["status"] for message in sent if message["type"] == "http.response.start")
    body = b"".join(message.get("body", b"") for message in sent if message["type"] == "http.response.body")
    return status, body, receive_calls


def _maintenance_app(monkeypatch, *, maximum: int, enabled: bool = True) -> FastAPI:
    monkeypatch.setenv("MAINTENANCE_API_ENABLED", "true" if enabled else "false")
    monkeypatch.setenv("MAINTENANCE_API_TOKEN", "maintenance-secret")
    monkeypatch.setenv("MAINTENANCE_MAX_REQUEST_BYTES", str(maximum))
    app = FastAPI()
    app.include_router(maintenance_router)
    return app


def _valid_import_body() -> tuple[bytes, str]:
    artifact_client_id = str(uuid4())
    payload = {
        "schema_version": "article-intelligence-maintenance.v1",
        "batch_id": str(uuid4()),
        "client_publish_id": str(uuid4()),
        "artifacts": [
            {
                "artifact_client_id": artifact_client_id,
                "stable_article_identity": {"kind": "finnhub_id", "value": "123"},
                "ticker": "SPY",
                "source_content_hash": "a" * 64,
                "prompt_version": "article-intelligence.v2",
                "prompt_hash": "b" * 64,
                "input_hash": "c" * 64,
                "export_revision_hint": 1,
                "provider": "ollama",
                "model": "llama3.2",
                "generated_at": "2026-10-02T12:00:00Z",
                "status": "completed",
                "output": {
                    "summary": "Generated summary",
                    "sentiment": "neutral",
                    "confidence": 7,
                    "importance_score": 6,
                    "market_impact": "Impact",
                    "short_term_outlook": "Short",
                    "long_term_outlook": "Long",
                },
                "quality_metrics": {},
                "evaluation_metadata": {},
            }
        ],
    }
    return json.dumps(payload, separators=(",", ":")).encode("utf-8"), artifact_client_id


async def test_declared_oversized_body_is_rejected_without_consumption(monkeypatch):
    app = _maintenance_app(monkeypatch, maximum=10)

    status, _, receive_calls = await _asgi_post(
        app,
        [b"01234567890"],
        headers=[AUTHORIZATION, (b"content-length", b"11")],
    )

    assert status == 413
    assert receive_calls == 0


async def test_chunked_oversized_body_stops_on_crossing_chunk(monkeypatch):
    app = _maintenance_app(monkeypatch, maximum=10)

    status, _, receive_calls = await _asgi_post(
        app,
        [b"012345", b"67890", b"unread-later-chunk"],
        headers=[AUTHORIZATION],
    )

    assert status == 413
    assert receive_calls == 2


async def test_unauthorized_oversized_body_is_not_consumed(monkeypatch):
    app = _maintenance_app(monkeypatch, maximum=10)

    status, response_body, receive_calls = await _asgi_post(
        app,
        [b"012345", b"67890", b"unread-later-chunk"],
    )

    assert status == 401
    assert json.loads(response_body) == {"detail": "Missing or invalid maintenance authorization"}
    assert receive_calls == 0


async def test_exact_limit_preserves_valid_import_and_pydantic_parsing(monkeypatch):
    body, artifact_client_id = _valid_import_body()
    app = _maintenance_app(monkeypatch, maximum=len(body))
    captured = {}

    async def session_override():
        yield object()

    async def publish(_service, batch_id, client_publish_id, candidates, *, dry_run):
        captured["batch_id"] = batch_id
        captured["client_publish_id"] = client_publish_id
        captured["candidates"] = candidates
        captured["dry_run"] = dry_run
        return SimpleNamespace(id=batch_id), [
            ImportOutcome(artifact_client_id=candidates[0].artifact_client_id, outcome="created")
        ]

    app.dependency_overrides[get_async_session] = session_override
    monkeypatch.setattr(MaintenanceImportService, "publish", publish)

    midpoint = len(body) // 2
    status, response_body, receive_calls = await _asgi_post(
        app,
        [body[:midpoint], body[midpoint:]],
        headers=[AUTHORIZATION],
    )

    assert status == 200
    assert receive_calls == 2
    assert captured["dry_run"] is False
    assert str(captured["candidates"][0].artifact_client_id) == artifact_client_id
    assert captured["candidates"][0].output.summary == "Generated summary"
    assert json.loads(response_body)["outcomes"][0]["outcome"] == "created"


async def test_one_byte_over_limit_is_rejected_before_endpoint(monkeypatch):
    body, _ = _valid_import_body()
    app = _maintenance_app(monkeypatch, maximum=len(body))
    publish_called = False

    async def publish(*args, **kwargs):
        nonlocal publish_called
        publish_called = True
        raise AssertionError("oversized request reached the endpoint")

    monkeypatch.setattr(MaintenanceImportService, "publish", publish)
    status, _, receive_calls = await _asgi_post(
        app,
        [body, b" "],
        headers=[AUTHORIZATION],
    )

    assert status == 413
    assert receive_calls == 2
    assert publish_called is False


async def test_disabled_maintenance_rejects_without_consuming_body(monkeypatch):
    app = _maintenance_app(monkeypatch, maximum=10, enabled=False)

    status, response_body, receive_calls = await _asgi_post(
        app,
        [b"012345", b"67890", b"unread-later-chunk"],
        headers=[AUTHORIZATION],
    )

    assert status == 404
    assert json.loads(response_body) == {"detail": "Maintenance API is disabled"}
    assert receive_calls == 0


async def test_malformed_content_length_preserves_400_without_consumption(monkeypatch):
    app = _maintenance_app(monkeypatch, maximum=10)

    status, response_body, receive_calls = await _asgi_post(
        app,
        [b"{}"],
        headers=[AUTHORIZATION, (b"content-length", b"not-an-integer")],
    )

    assert status == 400
    assert json.loads(response_body) == {"detail": "Invalid Content-Length header"}
    assert receive_calls == 0
