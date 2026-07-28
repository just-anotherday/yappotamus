"""Deterministic tests for lease-based AI job recovery."""

import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import postgresql

from backend.services.ai_worker import (
    AIWorker,
    _stale_job_query,
    enqueue_job,
    recover_stale_jobs,
)


NOW = datetime(2026, 7, 27, 21, 0, 0)
STALE_SECONDS = 3600


def _job(
    *,
    job_id=1,
    status="processing",
    started_at=None,
    lease_expires_at=None,
    retry_count=0,
):
    return SimpleNamespace(
        id=job_id,
        job_type="company_report",
        target_type="asset",
        target_id=42,
        dedupe_key=None,
        status=status,
        started_at=started_at or NOW - timedelta(hours=2),
        scheduled_for=NOW - timedelta(hours=2),
        completed_at=None,
        created_at=NOW - timedelta(hours=3),
        updated_at=NOW - timedelta(hours=2),
        heartbeat_at=started_at or NOW - timedelta(hours=2),
        lease_expires_at=lease_expires_at,
        worker_id="worker-before-restart",
        retry_count=retry_count,
        max_retries=3,
        recovery_count=0,
        last_recovery_reason=None,
        error_message="prior provider error",
        payload={},
        priority=10,
        result=None,
    )


class _Result:
    def __init__(self, rows=None, scalar=None, rowcount=1):
        self.rows = rows or []
        self.scalar = scalar
        self.rowcount = rowcount

    def unique(self):
        return self

    def scalars(self):
        return self

    def all(self):
        return self.rows

    def scalar_one_or_none(self):
        return self.scalar


class _Session:
    def __init__(self, *results):
        self.results = list(results)
        self.commits = 0
        self.added = []
        self.statements = []

    async def execute(self, statement, params=None):
        self.statements.append(statement)
        return self.results.pop(0) if self.results else _Result()

    async def commit(self):
        self.commits += 1

    async def merge(self, job):
        return job

    def add(self, job):
        self.added.append(job)


@pytest.mark.asyncio
async def test_recent_processing_job_is_not_recovered():
    recent = _job(started_at=NOW - timedelta(minutes=10))
    session = _Session(_Result([recent]))

    recovered = await recover_stale_jobs(
        session,
        now=NOW,
        stale_threshold_seconds=STALE_SECONDS,
        recovery_worker_id="startup-worker",
    )

    assert recovered == []
    assert recent.status == "processing"
    assert recent.recovery_count == 0
    assert session.commits == 0


@pytest.mark.asyncio
async def test_old_job_with_live_lease_is_not_recovered():
    active = _job(lease_expires_at=NOW + timedelta(minutes=1))
    session = _Session(_Result([active]))

    recovered = await recover_stale_jobs(
        session,
        now=NOW,
        stale_threshold_seconds=STALE_SECONDS,
        recovery_worker_id="startup-worker",
    )

    assert recovered == []
    assert active.status == "processing"


@pytest.mark.asyncio
async def test_legacy_job_recently_touched_by_migration_is_not_recovered():
    active = _job(lease_expires_at=None)
    active.updated_at = NOW - timedelta(minutes=5)
    session = _Session(_Result([active]))

    recovered = await recover_stale_jobs(
        session,
        now=NOW,
        stale_threshold_seconds=STALE_SECONDS,
        recovery_worker_id="startup-worker",
    )

    assert recovered == []
    assert active.status == "processing"


@pytest.mark.asyncio
async def test_stale_processing_job_is_recovered_without_consuming_retry():
    stale = _job(lease_expires_at=NOW - timedelta(minutes=1), retry_count=1)
    session = _Session(_Result([stale]))

    recovered = await recover_stale_jobs(
        session,
        now=NOW,
        stale_threshold_seconds=STALE_SECONDS,
        recovery_worker_id="startup-worker",
    )

    assert recovered == [stale.id]
    assert stale.status == "pending"
    assert stale.retry_count == 1
    assert stale.recovery_count == 1
    assert stale.worker_id == "worker-before-restart"
    assert stale.scheduled_for == NOW
    assert "prior provider error" in stale.error_message
    assert "processing lease expired" in stale.last_recovery_reason
    assert session.commits == 1


@pytest.mark.asyncio
async def test_recovery_is_idempotent_when_run_repeatedly():
    stale = _job(lease_expires_at=NOW - timedelta(minutes=1))
    session = _Session(_Result([stale]), _Result([stale]))

    first = await recover_stale_jobs(
        session,
        now=NOW,
        stale_threshold_seconds=STALE_SECONDS,
        recovery_worker_id="worker-one",
    )
    second = await recover_stale_jobs(
        session,
        now=NOW,
        stale_threshold_seconds=STALE_SECONDS,
        recovery_worker_id="worker-two",
    )

    assert first == [stale.id]
    assert second == []
    assert stale.recovery_count == 1


@pytest.mark.asyncio
async def test_recovered_job_can_be_claimed_again():
    stale = _job(lease_expires_at=NOW - timedelta(minutes=1))
    recovery_session = _Session(_Result([stale]))
    await recover_stale_jobs(
        recovery_session,
        now=NOW,
        stale_threshold_seconds=STALE_SECONDS,
        recovery_worker_id="startup-worker",
    )

    worker = AIWorker(lambda: None, max_concurrent=2)
    claim_session = _Session(_Result([stale]))
    claimed = await worker._claim_pending_jobs(claim_session, limit=1)

    assert claimed == [stale]
    assert stale.status == "processing"
    assert stale.worker_id == worker.worker_id
    assert stale.heartbeat_at is not None
    assert stale.lease_expires_at > stale.heartbeat_at


@pytest.mark.asyncio
async def test_enqueue_recovers_stale_duplicate_without_adding_second_job(monkeypatch):
    monkeypatch.setenv("AI_STALE_JOB_RECOVERY_ENABLED", "true")
    stale = _job(lease_expires_at=NOW - timedelta(hours=1))
    session = _Session(
        _Result(),  # advisory lock
        _Result([stale]),  # targeted stale recovery
        _Result(scalar=stale.id),  # pending/processing deduplication
    )

    queued = await enqueue_job(
        session,
        job_type=stale.job_type,
        target_type=stale.target_type,
        target_id=stale.target_id,
        dedupe_key=stale.dedupe_key,
    )

    assert queued is False
    assert stale.status == "pending"
    assert stale.recovery_count == 1
    assert session.added == []


@pytest.mark.asyncio
async def test_disabled_recovery_does_not_mutate_stale_duplicate(monkeypatch):
    monkeypatch.setenv("AI_STALE_JOB_RECOVERY_ENABLED", "false")
    stale = _job(lease_expires_at=NOW - timedelta(hours=1))
    session = _Session(
        _Result(),  # advisory lock
        _Result(scalar=stale.id),  # pending/processing deduplication
    )

    queued = await enqueue_job(
        session,
        job_type=stale.job_type,
        target_type=stale.target_type,
        target_id=stale.target_id,
        dedupe_key=stale.dedupe_key,
    )

    assert queued is False
    assert stale.status == "processing"
    assert stale.recovery_count == 0
    assert session.added == []

@pytest.mark.asyncio
async def test_two_recovery_workers_cannot_transition_same_job_twice():
    stale = _job(lease_expires_at=NOW - timedelta(minutes=1))
    first_session = _Session(_Result([stale]))
    second_session = _Session(_Result([stale]))

    first, second = await asyncio.gather(
        recover_stale_jobs(
            first_session,
            now=NOW,
            stale_threshold_seconds=STALE_SECONDS,
            recovery_worker_id="worker-one",
        ),
        recover_stale_jobs(
            second_session,
            now=NOW,
            stale_threshold_seconds=STALE_SECONDS,
            recovery_worker_id="worker-two",
        ),
    )

    assert sorted((len(first), len(second))) == [0, 1]
    assert stale.recovery_count == 1
    sql = str(
        _stale_job_query(
            now=NOW,
            stale_threshold_seconds=STALE_SECONDS,
            limit=100,
        ).compile(dialect=postgresql.dialect())
    ).upper()
    assert "FOR UPDATE SKIP LOCKED" in sql
    assert "LEASE_EXPIRES_AT" in sql


@pytest.mark.asyncio
async def test_two_workers_cannot_claim_the_same_pending_job():
    pending = _job(status="pending")
    database_lock = asyncio.Lock()

    class SharedClaimSession(_Session):
        async def execute(self, statement, params=None):
            self.statements.append(statement)
            async with database_lock:
                rows = [pending] if pending.status == "pending" else []
                return _Result(rows)

        async def commit(self):
            self.commits += 1
            await asyncio.sleep(0)

    first_worker = AIWorker(lambda: None, max_concurrent=1)
    second_worker = AIWorker(lambda: None, max_concurrent=1)
    first_session = SharedClaimSession()
    second_session = SharedClaimSession()

    first, second = await asyncio.gather(
        first_worker._claim_pending_jobs(first_session, limit=1),
        second_worker._claim_pending_jobs(second_session, limit=1),
    )

    assert sorted((len(first), len(second))) == [0, 1]
    assert pending.status == "processing"
    assert pending.worker_id in {first_worker.worker_id, second_worker.worker_id}
