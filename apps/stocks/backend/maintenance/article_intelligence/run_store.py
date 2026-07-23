"""Durable standard-library SQLite run store for resumable local maintenance."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from backend.maintenance.article_intelligence.contracts import ExportArticle, ImportCandidate, ImportOutcome


_UNSET = object()


@dataclass(frozen=True)
class LocalRun:
    run_id: UUID
    client_request_id: UUID
    batch_id: UUID | None
    state: str
    model: str
    prompt_version: str | None
    prompt_hash: str | None
    registry_revision: str | None
    pending_publish_id: UUID | None
    pending_publish_dry_run: bool | None
    last_error: str | None


@dataclass(frozen=True)
class LocalRunItem:
    ordinal: int
    export: ExportArticle
    state: str
    candidate: ImportCandidate | None
    outcome: ImportOutcome | None
    attempts: int
    retryable: bool
    last_error: str | None


class SQLiteMaintenanceRunStore:
    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS maintenance_runs (
                    run_id TEXT PRIMARY KEY, client_request_id TEXT NOT NULL UNIQUE,
                    batch_id TEXT UNIQUE, state TEXT NOT NULL, model TEXT NOT NULL,
                    prompt_version TEXT, prompt_hash TEXT, registry_revision TEXT,
                    pending_publish_id TEXT, pending_publish_dry_run INTEGER,
                    last_error TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS maintenance_run_items (
                    run_id TEXT NOT NULL REFERENCES maintenance_runs(run_id) ON DELETE CASCADE,
                    ordinal INTEGER NOT NULL, artifact_client_id TEXT NOT NULL,
                    export_json TEXT NOT NULL, candidate_json TEXT, outcome_json TEXT,
                    state TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
                    retryable INTEGER NOT NULL DEFAULT 0, last_error TEXT,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (run_id, ordinal), UNIQUE (run_id, artifact_client_id)
                );
            """)

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def create_run(self, run_id: UUID, client_request_id: UUID, model: str) -> LocalRun:
        now = self._now()
        with self._connect() as db:
            db.execute("""INSERT OR IGNORE INTO maintenance_runs
                (run_id, client_request_id, state, model, created_at, updated_at)
                VALUES (?, ?, 'CREATED', ?, ?, ?)""",
                (str(run_id), str(client_request_id), model, now, now))
            row = db.execute(
                "SELECT * FROM maintenance_runs WHERE client_request_id = ?", (str(client_request_id),)
            ).fetchone()
        run = self._run(row) if row else None
        if run is None:
            raise RuntimeError("failed to create maintenance run")
        if run.model != model:
            raise ValueError("client_request_id already exists with a different model")
        return run

    def get_run(self, run_id: UUID) -> LocalRun | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM maintenance_runs WHERE run_id = ?", (str(run_id),)).fetchone()
        return self._run(row) if row else None

    def update_run(self, run_id: UUID, *, state: str | None = None, batch_id: UUID | None = None,
                   prompt_version: str | None = None, prompt_hash: str | None = None,
                   registry_revision: str | None = None, last_error: str | None | object = _UNSET) -> LocalRun:
        values = {
            "state": state, "batch_id": str(batch_id) if batch_id else None,
            "prompt_version": prompt_version, "prompt_hash": prompt_hash,
            "registry_revision": registry_revision, "last_error": last_error,
        }
        assignments = [
            f"{key} = ?" for key, value in values.items()
            if (value is not None and value is not _UNSET) or (key == "last_error" and value is None)
        ]
        params = [
            value for key, value in values.items()
            if (value is not None and value is not _UNSET) or (key == "last_error" and value is None)
        ]
        assignments.append("updated_at = ?"); params.append(self._now()); params.append(str(run_id))
        with self._connect() as db:
            db.execute(f"UPDATE maintenance_runs SET {', '.join(assignments)} WHERE run_id = ?", params)
        run = self.get_run(run_id)
        if run is None:
            raise KeyError(run_id)
        return run

    def set_pending_publish(self, run_id: UUID, publish_id: UUID, *, dry_run: bool) -> LocalRun:
        with self._connect() as db:
            db.execute("""UPDATE maintenance_runs SET pending_publish_id = ?,
                pending_publish_dry_run = ?, updated_at = ? WHERE run_id = ?""",
                (str(publish_id), int(dry_run), self._now(), str(run_id)))
        return self.get_run(run_id)

    def clear_pending_publish(self, run_id: UUID) -> LocalRun:
        with self._connect() as db:
            db.execute("""UPDATE maintenance_runs SET pending_publish_id = NULL,
                pending_publish_dry_run = NULL, updated_at = ? WHERE run_id = ?""",
                (self._now(), str(run_id)))
        return self.get_run(run_id)

    def save_exports(self, run_id: UUID, exports: list[ExportArticle]) -> None:
        now = self._now()
        with self._connect() as db:
            for ordinal, item in enumerate(exports):
                artifact_id = str(UUID(item.input_hash[:32]))
                db.execute("""INSERT OR IGNORE INTO maintenance_run_items
                    (run_id, ordinal, artifact_client_id, export_json, state, updated_at)
                    VALUES (?, ?, ?, ?, 'EXPORTED', ?)""",
                    (str(run_id), ordinal, artifact_id, item.model_dump_json(), now))

    def items(self, run_id: UUID) -> list[LocalRunItem]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT * FROM maintenance_run_items WHERE run_id = ? ORDER BY ordinal", (str(run_id),)
            ).fetchall()
        return [self._item(row) for row in rows]

    def save_candidate(self, run_id: UUID, ordinal: int, candidate: ImportCandidate) -> None:
        with self._connect() as db:
            db.execute("""UPDATE maintenance_run_items SET candidate_json = ?, state = 'GENERATED',
                attempts = attempts + 1, retryable = 0, last_error = NULL, updated_at = ?
                WHERE run_id = ? AND ordinal = ?""",
                (candidate.model_dump_json(), self._now(), str(run_id), ordinal))

    def save_generation_error(self, run_id: UUID, ordinal: int, error: str, *, retryable: bool) -> None:
        with self._connect() as db:
            db.execute("""UPDATE maintenance_run_items SET state = 'GENERATION_FAILED',
                attempts = attempts + 1, retryable = ?, last_error = ?, updated_at = ?
                WHERE run_id = ? AND ordinal = ?""",
                (int(retryable), error[:1000], self._now(), str(run_id), ordinal))

    def save_outcomes(self, run_id: UUID, outcomes: list[ImportOutcome], *, dry_run: bool) -> None:
        state_prefix = "DRY_RUN_" if dry_run else "PUBLISHED_"
        with self._connect() as db:
            for outcome in outcomes:
                retryable = outcome.retryable
                db.execute("""UPDATE maintenance_run_items SET outcome_json = ?, state = ?, retryable = ?,
                    last_error = ?, updated_at = ? WHERE run_id = ? AND artifact_client_id = ?""",
                    (outcome.model_dump_json(), state_prefix + outcome.outcome.upper(), int(retryable),
                     outcome.reason_code, self._now(), str(run_id), str(outcome.artifact_client_id)))

    @staticmethod
    def _run(row: sqlite3.Row) -> LocalRun:
        return LocalRun(
            run_id=UUID(row["run_id"]), client_request_id=UUID(row["client_request_id"]),
            batch_id=UUID(row["batch_id"]) if row["batch_id"] else None, state=row["state"],
            model=row["model"], prompt_version=row["prompt_version"], prompt_hash=row["prompt_hash"],
            registry_revision=row["registry_revision"],
            pending_publish_id=UUID(row["pending_publish_id"]) if row["pending_publish_id"] else None,
            pending_publish_dry_run=bool(row["pending_publish_dry_run"]) if row["pending_publish_dry_run"] is not None else None,
            last_error=row["last_error"],
        )

    @staticmethod
    def _item(row: sqlite3.Row) -> LocalRunItem:
        return LocalRunItem(
            ordinal=row["ordinal"], export=ExportArticle.model_validate_json(row["export_json"]),
            state=row["state"],
            candidate=ImportCandidate.model_validate_json(row["candidate_json"]) if row["candidate_json"] else None,
            outcome=ImportOutcome.model_validate_json(row["outcome_json"]) if row["outcome_json"] else None,
            attempts=row["attempts"], retryable=bool(row["retryable"]), last_error=row["last_error"],
        )