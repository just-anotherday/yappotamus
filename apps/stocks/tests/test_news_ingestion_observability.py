"""Focused tests for company-report enqueue observability counters."""

from unittest.mock import AsyncMock

import pytest

from backend.services import news_ingestion_service


@pytest.mark.asyncio
async def test_enqueue_company_report_jobs_counts_created_and_deduplicated(monkeypatch):
    session = object()
    enqueue_mock = AsyncMock(side_effect=[True, False])
    monkeypatch.setattr(news_ingestion_service, "enqueue_job", enqueue_mock)

    result = await news_ingestion_service._enqueue_company_report_jobs(
        session,
        "spy",
        {101, 202},
    )

    assert result == {
        "report_candidates": 2,
        "enqueue_attempts": 2,
        "jobs_created": 1,
        "jobs_deduplicated": 1,
    }
    assert enqueue_mock.await_count == 2

    calls_by_target_id = {
        call.kwargs["target_id"]: call.kwargs
        for call in enqueue_mock.await_args_list
    }
    assert set(calls_by_target_id) == {101, 202}
    for target_id, kwargs in calls_by_target_id.items():
        assert kwargs == {
            "session": session,
            "job_type": "company_report",
            "target_type": "asset",
            "target_id": target_id,
            "payload": {"ticker": "SPY"},
            "priority": 10,
        }


@pytest.mark.asyncio
async def test_enqueue_company_report_jobs_returns_zero_counts_for_no_candidates(monkeypatch):
    enqueue_mock = AsyncMock()
    monkeypatch.setattr(news_ingestion_service, "enqueue_job", enqueue_mock)

    result = await news_ingestion_service._enqueue_company_report_jobs(
        object(),
        "spy",
        set(),
    )

    assert result == {
        "report_candidates": 0,
        "enqueue_attempts": 0,
        "jobs_created": 0,
        "jobs_deduplicated": 0,
    }
    enqueue_mock.assert_not_awaited()
