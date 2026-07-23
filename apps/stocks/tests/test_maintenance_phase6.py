"""Phase 6 thin CLI, configuration, and coordinator delegation tests."""

from __future__ import annotations

import json
from io import StringIO
from uuid import uuid4

import pytest

from backend.maintenance.article_intelligence.cli import main
from backend.maintenance.article_intelligence.config import MaintenanceCLIConfig
from backend.maintenance.article_intelligence.coordinator import CoordinatorResult
from backend.maintenance.article_intelligence.run_store import LocalRun


def _result(run_id=None, *, state="READY_TO_PUBLISH") -> CoordinatorResult:
    run_id = run_id or uuid4()
    return CoordinatorResult(
        run=LocalRun(
            run_id=run_id, client_request_id=uuid4(), batch_id=uuid4(), state=state,
            model="llama3.2", prompt_version="article-v1", prompt_hash="a" * 64,
            registry_revision="registry-v1", pending_publish_id=None,
            pending_publish_dry_run=None, last_error=None,
        ),
        exported=2, generated=2, published=int(state == "COMPLETED"), rejected=0, retryable=0,
    )


class CoordinatorSpy:
    def __init__(self):
        self.calls = []

    async def start(self, **kwargs):
        self.calls.append(("start", kwargs))
        return _result()

    def status(self, run_id):
        self.calls.append(("status", {"run_id": run_id}))
        return _result(run_id)

    async def resume(self, run_id, **kwargs):
        self.calls.append(("resume", {"run_id": run_id, **kwargs}))
        return _result(run_id, state="COMPLETED" if kwargs.get("publish") and not kwargs.get("dry_run") else "READY_TO_PUBLISH")


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("resume", {}),
        ("dry-run", {"publish": True, "dry_run": True}),
        ("publish", {"publish": True}),
    ],
)
def test_resume_commands_delegate_workflow_to_coordinator(command, expected):
    coordinator = CoordinatorSpy()
    run_id = uuid4()
    stdout, stderr = StringIO(), StringIO()
    assert main([command, str(run_id)], coordinator=coordinator, stdout=stdout, stderr=stderr) == 0
    name, arguments = coordinator.calls[0]
    assert name == "resume"
    assert arguments.pop("run_id") == run_id
    assert arguments == expected
    assert json.loads(stdout.getvalue())["run_id"] == str(run_id)
    events = [json.loads(line) for line in stderr.getvalue().splitlines()]
    assert [event["event"] for event in events] == ["command_started", "command_completed"]


def test_start_delegates_filters_idempotency_and_dry_run():
    coordinator = CoordinatorSpy()
    request_id = uuid4()
    stdout, stderr = StringIO(), StringIO()
    code = main([
        "start", "--model", "llama3.2", "--client-request-id", str(request_id),
        "--ticker", "SPY", "--ticker", "QQQ", "--max-items", "12", "--dry-run",
    ], coordinator=coordinator, stdout=stdout, stderr=stderr)
    assert code == 0
    assert coordinator.calls == [("start", {
        "model": "llama3.2", "client_request_id": request_id, "tickers": ["SPY", "QQQ"],
        "max_items": 12, "publish": True, "dry_run": True,
    })]


def test_status_is_read_only_and_errors_are_machine_readable():
    coordinator = CoordinatorSpy()
    run_id = uuid4()
    stdout, stderr = StringIO(), StringIO()
    assert main(["status", str(run_id)], coordinator=coordinator, stdout=stdout, stderr=stderr) == 0
    assert coordinator.calls[0] == ("status", {"run_id": run_id})

    class Missing(CoordinatorSpy):
        def status(self, run_id):
            raise KeyError(f"unknown maintenance run: {run_id}")

    stdout, stderr = StringIO(), StringIO()
    assert main(["status", str(run_id)], coordinator=Missing(), stdout=stdout, stderr=stderr) == 1
    assert stdout.getvalue() == ""
    events = [json.loads(line) for line in stderr.getvalue().splitlines()]
    assert [event["event"] for event in events] == ["command_started", "command_failed"]


def test_configuration_loads_required_values_and_defaults(monkeypatch, tmp_path):
    monkeypatch.setenv("MAINTENANCE_PRODUCTION_URL", "https://production.example/")
    monkeypatch.setenv("MAINTENANCE_API_TOKEN", "secret")
    monkeypatch.setenv("MAINTENANCE_RUN_STORE_PATH", str(tmp_path / "runs.sqlite3"))
    monkeypatch.setenv("MAINTENANCE_OLLAMA_MODEL", "local-model")
    config = MaintenanceCLIConfig.load()
    assert config.production_url == "https://production.example/"
    assert config.api_token == "secret"
    assert config.run_store_path == tmp_path / "runs.sqlite3"
    assert config.model == "local-model"
    assert config.timeout == 30.0


def test_configuration_rejects_missing_credentials(monkeypatch):
    monkeypatch.delenv("MAINTENANCE_PRODUCTION_URL", raising=False)
    monkeypatch.delenv("MAINTENANCE_API_TOKEN", raising=False)
    with pytest.raises(EnvironmentError, match="MAINTENANCE_PRODUCTION_URL"):
        MaintenanceCLIConfig.load()
