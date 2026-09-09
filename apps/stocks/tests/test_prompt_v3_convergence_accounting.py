"""Offline regression coverage for correction convergence telemetry."""

import json
from types import SimpleNamespace

import pytest

from backend.models.analysis import GroundingViolation
from backend.services import ollama_service
from backend.services.ai.exceptions import AISemanticGroundingError
from test_semantic_grounding import _install_client, _report, _request, _synthetic_review_for_report


def _violation(segment_id, *, rule="unsupported_company_specific_claim", issue="Initial finding"):
    return GroundingViolation(
        section="executive_summary",
        rule=rule,
        issue=issue,
        coverage_segment_id=segment_id,
        patch_target_id=segment_id,
    )


def _plan(origins, *, changed=(), new=(), evidence_changed=(), unreconciled=(), deleted=()):
    return SimpleNamespace(
        initial_segment_ids_by_final_segment=origins,
        changed_segment_ids=changed,
        new_segment_ids=new,
        evidence_changed_segment_ids=evidence_changed,
        unreconciled_segment_ids=unreconciled,
        deleted_initial_segment_ids=deleted,
    )


def test_replacement_still_blocking_is_not_reported_resolved(caplog):
    initial = [_violation("executive_summary.segment_2")]
    final = [_violation(
        "executive_summary.segment_1",
        rule="causal_mechanism_grounding",
        issue="Different reviewer wording and rule after replacement",
    )]
    plan = _plan(
        {"executive_summary.segment_1": ("executive_summary.segment_2",)},
        changed=("executive_summary.segment_1",),
    )
    summary = ollama_service._summarize_grounding_delta(initial, final, plan)
    assert summary["resolved_count"] == 0
    assert summary["remaining_count"] == 1
    assert summary["changed_blocker_count"] == 1
    assert summary["new_count"] == 0
    assert summary["final_blocker_count"] == 1
    with caplog.at_level("INFO", logger="backend.services.ollama_service"):
        ollama_service._log_grounding_delta(initial, final, plan)
    assert "resolved_count=0 remaining_count=1 new_count=0" in caplog.text
    assert "final_blocker_count=1" in caplog.text
    assert "Different reviewer wording" not in caplog.text


def test_delete_does_not_confuse_reused_position_with_deleted_blocker():
    initial = [_violation("executive_summary.segment_0"), _violation("executive_summary.segment_1")]
    final = [_violation("executive_summary.segment_0", issue="Surviving blocker")]
    plan = _plan(
        {"executive_summary.segment_0": ("executive_summary.segment_1",)},
        deleted=("executive_summary.segment_0",),
    )
    summary = ollama_service._summarize_grounding_delta(initial, final, plan)
    assert summary["resolved_count"] == 1
    assert summary["remaining_count"] == 1
    assert summary["resolved_ids"] == ollama_service._violation_ids(initial[:1])
    assert summary["remaining_ids"] == ollama_service._violation_ids(initial[1:])


def test_initial_blocker_only_resolves_when_every_descendant_is_clear():
    initial = [_violation("executive_summary.segment_0")]
    plan = _plan({
        "executive_summary.segment_0": ("executive_summary.segment_0",),
        "executive_summary.segment_1": ("executive_summary.segment_0",),
    }, changed=("executive_summary.segment_0", "executive_summary.segment_1"))
    blocked = ollama_service._summarize_grounding_delta(
        initial, [_violation("executive_summary.segment_1")], plan
    )
    assert blocked["remaining_count"] == 1
    assert blocked["resolved_count"] == 0
    clear = ollama_service._summarize_grounding_delta(initial, [], plan)
    assert clear["resolved_count"] == 1
    assert clear["remaining_count"] == 0


def test_recombined_blocker_keeps_both_initial_origins_unresolved():
    initial = [_violation("executive_summary.segment_0"), _violation("executive_summary.segment_2")]
    plan = _plan(
        {"executive_summary.segment_0": (
            "executive_summary.segment_0", "executive_summary.segment_2"
        )},
        unreconciled=("executive_summary.segment_0",),
    )
    summary = ollama_service._summarize_grounding_delta(
        initial, [_violation("executive_summary.segment_0")], plan
    )
    assert summary["remaining_count"] == 2
    assert summary["final_blocker_count"] == 1
    assert summary["unreconciled_blocker_count"] == 1
    assert summary["resolved_count"] == 0


def test_missing_lineage_is_unknown_instead_of_assumed_deleted():
    initial = [_violation("executive_summary.segment_0")]
    summary = ollama_service._summarize_grounding_delta(initial, [], _plan({}))
    assert summary["resolved_count"] == 0
    assert summary["remaining_count"] == 0
    assert summary["unresolved_initial_count"] == 1


def test_new_number_with_existing_ancestry_is_not_a_genuine_new_blocker():
    segment_id = "executive_summary.segment_9"
    plan = _plan(
        {segment_id: ("executive_summary.segment_0",)}, new=(segment_id,)
    )
    summary = ollama_service._summarize_grounding_delta([], [_violation(segment_id)], plan)
    assert summary["new_count"] == 0
    assert summary["final_blocker_count"] == 1


def test_only_proven_new_origin_counts_as_new():
    new_id = "executive_summary.segment_1"
    unknown_id = "executive_summary.segment_2"
    plan = _plan(
        {new_id: (), unknown_id: ()}, new=(new_id, unknown_id), unreconciled=(unknown_id,)
    )
    summary = ollama_service._summarize_grounding_delta(
        [], [_violation(new_id), _violation(unknown_id)], plan
    )
    assert summary["new_count"] == 1
    assert summary["unreconciled_blocker_count"] == 1
    assert summary["final_blocker_count"] == 2


def test_evidence_changed_blocker_is_counted_separately():
    segment_id = "executive_summary.segment_0"
    initial = [_violation(segment_id)]
    plan = _plan({segment_id: (segment_id,)}, evidence_changed=(segment_id,))
    summary = ollama_service._summarize_grounding_delta(initial, initial, plan)
    assert summary["evidence_changed_blocker_count"] == 1
    assert summary["changed_blocker_count"] == 0
    assert summary["remaining_count"] == 1
    assert summary["resolved_count"] == 0


def test_lineage_diagnostics_show_hashes_and_positions_without_report_text(caplog):
    initial_id = "executive_summary.segment_2"
    final_id = "executive_summary.segment_1"
    private_text = "PRIVATE REPORT CONTENT MUST NOT BE LOGGED"
    identity = SimpleNamespace(
        coverage_segment_id=final_id,
        review_unit_id="executive_summary",
        fingerprint="safe-durable-fingerprint",
        normalized_text=private_text,
    )
    entry = SimpleNamespace(identity=identity, passed=True)
    plan = _plan({final_id: (initial_id,)})
    plan.carried_entries = (entry,)
    plan.review_segments = ()
    plan.final_identities_by_segment_id = {final_id: identity}
    plan.initial_identities_by_segment_id = {initial_id: identity}
    ledger = SimpleNamespace(entries_by_fingerprint={identity.fingerprint: entry})
    final = SimpleNamespace(violations=[])
    with caplog.at_level("INFO", logger="backend.services.ollama_service"):
        ollama_service._log_final_review_reconciliation(ledger, plan, final)
    message = next(record.message for record in caplog.records if "[GroundingLineage]" in record.message)
    trace = json.loads(message.split("[GroundingLineage] ", 1)[1])
    assert trace["initial_segment_ids"] == [initial_id]
    assert trace["final_segment_id"] == final_id
    assert trace["final_fingerprint"] == "safe-durable-fingerprint"
    assert trace["initial_fingerprints"] == ["safe-durable-fingerprint"]
    assert trace["reason"] == "carried_pass"
    assert trace["generatively_reviewed"] is False
    assert private_text not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["DELETE", "REPLACE"])
async def test_pipeline_uses_merge_lineage_and_rejects_remaining_blocker_without_retry(
    monkeypatch, caplog, operation,
):
    payload = _report(corrected=True)
    payload["article_indices_used"] = [1]
    payload["market_reaction_analysis"] = "Disputed claim. Surviving fact."
    target_id = "market_reaction_analysis.segment_0"
    patch = {"target_id": target_id, "operation": operation}
    if operation == "REPLACE":
        patch["replacement"] = "Still disputed claim."
    provider_calls = []

    class OfflineClient:
        async def generate(self, **kwargs):
            provider_calls.append(kwargs)
            assert len(provider_calls) <= 2, "No hidden correction or repair generation"
            if len(provider_calls) == 1:
                return json.dumps(payload)
            assert kwargs["system_prompt"] == ollama_service.PATCH_CORRECTION_SYSTEM_PROMPT
            assert kwargs["max_attempts"] == 1
            return json.dumps({"patches": [patch]})

    review_phases = []

    async def offline_review(ai, request, result, selected_indices, model, *, stage="initial_review", review_segments=None):
        review_phases.append(stage)
        if stage == "initial_review":
            return _synthetic_review_for_report(request, result, blocking_segment_ids={target_id})
        assert operation == "REPLACE", "Renumbered surviving PASS must not reach the reviewer"
        assert [segment.coverage_segment_id for segment in review_segments] == [target_id]
        review = _synthetic_review_for_report(request, result, blocking_segment_ids={target_id})
        return review.model_copy(update={
            "claims": [claim for claim in review.claims if claim.coverage_segment_id == target_id],
            "violations": [violation for violation in review.violations if violation.coverage_segment_id == target_id],
            "valid": False,
        })

    await _install_client(monkeypatch, "ollama", OfflineClient())
    monkeypatch.setattr(ollama_service, "_run_grounding_review", offline_review)
    with caplog.at_level("INFO", logger="backend.services.ollama_service"):
        if operation == "DELETE":
            result = await ollama_service.generate_analysis(_request(), provider="ollama", model="test-model")
            assert result.market_reaction_analysis == "Surviving fact."
            assert review_phases == ["initial_review"]
            assert "resolved_count=1 remaining_count=0 new_count=0" in caplog.text
        else:
            with pytest.raises(AISemanticGroundingError) as caught:
                await ollama_service.generate_analysis(_request(), provider="ollama", model="test-model")
            assert caught.value.details["failure_kind"] == "semantic_grounding_rejected"
            assert review_phases == ["initial_review", "final_review"]
            assert "resolved_count=0 remaining_count=1 new_count=0" in caplog.text
    assert len(provider_calls) == 2
