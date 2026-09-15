"""Offline regression tests for exact correction provenance and verdict stability."""

import pytest

from backend.models.analysis import FinancialAnalysisLLMResponse
from backend.services import ollama_service
from test_semantic_grounding import (
    _report,
    _request,
    _synthetic_review_for_report,
)


def _candidate(**fields):
    payload = _report(corrected=True)
    payload.update(fields)
    return FinancialAnalysisLLMResponse(**payload)


def _delete(target_id):
    return {"target_id": target_id, "operation": "DELETE"}


def _replace(target_id, replacement):
    return {
        "target_id": target_id,
        "operation": "REPLACE",
        "replacement": replacement,
    }


def _correct_and_plan(
    report,
    patches,
    *,
    blockers=(),
    final_request=None,
    final_selected=None,
):
    request = _request()
    review = _synthetic_review_for_report(
        request, report, blocking_segment_ids=blockers,
    )
    ledger = ollama_service._build_initial_proposition_review_ledger(
        request, report, [1], review,
    )
    registry = ollama_service.build_correction_target_registry(
        ollama_service._build_reviewable_claim_units(report),
    )
    touched = [patch["target_id"] for patch in patches]
    merged = ollama_service.merge_correction_patch_set(
        report, registry, touched, {"patches": patches},
    )
    plan = ollama_service._plan_final_proposition_review(
        request if final_request is None else final_request,
        merged.report,
        [1] if final_selected is None else final_selected,
        ledger,
        touched,
        proposition_lineage=merged.proposition_lineage,
    )
    return merged, plan


def _carried_by_segment(plan):
    return {
        entry.identity.coverage_segment_id: entry
        for entry in plan.carried_entries
    }


@pytest.mark.parametrize("survivor", ["indicating a volatile", "if AI demand remains strong."])
def test_connector_led_survivor_adjacent_to_deleted_segment_is_re_reviewed(survivor):
    report = _candidate(market_reaction_analysis=(
        f"Stable opening. {survivor} Deleted governing clause. Independent tail."
    ))
    prefix = "market_reaction_analysis.segment_"
    merged, plan = _correct_and_plan(report, [_delete(f"{prefix}2")])
    # The connector-led segment keeps its bytes but loses its governing neighbor.
    assert f"{prefix}1" in plan.changed_segment_ids
    assert f"{prefix}1" not in _carried_by_segment(plan)


def test_independent_survivor_adjacent_to_delete_still_carries_forward():
    report = _candidate(market_reaction_analysis="Revenue increased 15%. Management raised guidance.")
    prefix = "market_reaction_analysis.segment_"
    merged, plan = _correct_and_plan(report, [_delete(f"{prefix}1")])
    assert f"{prefix}0" in _carried_by_segment(plan)
    assert f"{prefix}0" not in plan.changed_segment_ids


def test_delete_reconstruction_removes_terminal_comma_seam():
    source = "The range is known. remove this, trailing text."
    start = source.index("remove this")
    end = source.index("trailing")
    repaired = ollama_service._delete_correction_text_span(source, start, end)
    assert ". ," not in repaired


@pytest.mark.parametrize("deleted_ordinal", [0, 1])
def test_sentence_delete_preserves_exact_survivor_verdicts_after_renumbering(
    deleted_ordinal,
):
    report = _candidate(
        market_reaction_analysis=(
            "First fact. Middle fact. Unsupported surviving fact. Last fact."
        ),
    )
    prefix = "market_reaction_analysis.segment_"
    merged, plan = _correct_and_plan(
        report,
        [_delete(f"{prefix}{deleted_ordinal}")],
        blockers={f"{prefix}{deleted_ordinal}", f"{prefix}2"},
    )

    survivors = [ordinal for ordinal in range(4) if ordinal != deleted_ordinal]
    carried = _carried_by_segment(plan)
    for final_ordinal, original_ordinal in enumerate(survivors):
        final_id = f"{prefix}{final_ordinal}"
        assert plan.initial_segment_ids_by_final_segment[final_id] == (
            f"{prefix}{original_ordinal}",
        )
        assert carried[final_id].passed is (original_ordinal != 2)
    assert not plan.review_segments
    assert not plan.changed_segment_ids
    assert not plan.new_segment_ids
    assert not plan.unreconciled_segment_ids
    assert set(plan.deleted_initial_segment_ids) == {f"{prefix}{deleted_ordinal}"}
    assert report.market_reaction_analysis == (
        "First fact. Middle fact. Unsupported surviving fact. Last fact."
    )
    assert merged.report.market_reaction_analysis.count("fact.") == 3

    final = ollama_service._assemble_reconciled_final_review(plan, None)
    assert not final.valid
    assert len(final.violations) == 1
    blocker = final.violations[0]
    assert blocker.coverage_segment_id == f"{prefix}1"
    assert blocker.patch_target_id == f"{prefix}1"
    assert blocker.issue.startswith("market_reaction_analysis.atomic_1:")
    final_claim = next(
        claim for claim in final.claims
        if claim.coverage_segment_id == blocker.coverage_segment_id
    )
    assert final_claim.review_unit_id == "market_reaction_analysis"
    assert final_claim.atomic_ordinal == 1
    assert final_claim.atomic_claim_id == "market_reaction_analysis.atomic_1"


@pytest.mark.parametrize("deleted_index", [0, 1])
def test_list_delete_keeps_duplicate_occurrences_distinct(deleted_index):
    report = _candidate(
        key_catalysts=["Repeated fact.", "Repeated fact.", "Tail fact."],
    )
    def initial_id(index):
        return f"key_catalysts[{index}].segment_0"

    merged, plan = _correct_and_plan(
        report,
        [_delete(initial_id(deleted_index))],
        blockers={initial_id(1)},
    )
    carried = _carried_by_segment(plan)
    surviving_duplicate_index = 1 - deleted_index

    assert merged.report.key_catalysts == ["Repeated fact.", "Tail fact."]
    assert plan.initial_segment_ids_by_final_segment[initial_id(0)] == (
        initial_id(surviving_duplicate_index),
    )
    assert plan.initial_segment_ids_by_final_segment[initial_id(1)] == (
        initial_id(2),
    )
    assert carried[initial_id(0)].passed is (surviving_duplicate_index == 0)
    assert carried[initial_id(1)].passed
    assert not plan.review_segments
    assert not plan.new_segment_ids

    final = ollama_service._assemble_reconciled_final_review(plan, None)
    assert final.valid is (surviving_duplicate_index == 0)
    duplicate_claim = next(
        claim for claim in final.claims
        if claim.coverage_segment_id == initial_id(0)
    )
    assert duplicate_claim.review_unit_id == "key_catalysts[0]"
    assert duplicate_claim.atomic_claim_id == "key_catalysts[0].atomic_0"
    if final.violations:
        blocker = final.violations[0]
        assert blocker.coverage_segment_id == initial_id(0)
        assert blocker.patch_target_id == initial_id(0)
        assert blocker.issue.startswith("key_catalysts[0].atomic_0:")


def test_multiple_list_deletes_keep_original_occurrence_ancestry():
    report = _candidate(
        key_catalysts=["First fact.", "Kept fact.", "Third fact.", "Tail fact."],
    )
    merged, plan = _correct_and_plan(
        report,
        [
            _delete("key_catalysts[0].segment_0"),
            _delete("key_catalysts[2].segment_0"),
        ],
    )

    assert merged.report.key_catalysts == ["Kept fact.", "Tail fact."]
    assert plan.initial_segment_ids_by_final_segment["key_catalysts[0].segment_0"] == (
        "key_catalysts[1].segment_0",
    )
    assert plan.initial_segment_ids_by_final_segment["key_catalysts[1].segment_0"] == (
        "key_catalysts[3].segment_0",
    )
    assert not plan.review_segments


def test_exhausted_bear_case_item_preserves_later_item_lineage_and_verdict():
    report = _candidate(bear_case=[
        "First surviving risk.",
        "Deleted first proposition. Deleted second proposition.",
        "Later blocked risk.",
    ])
    deleted_ids = ["bear_case[1].segment_0", "bear_case[1].segment_1"]
    merged, plan = _correct_and_plan(
        report,
        [_delete(target_id) for target_id in deleted_ids],
        blockers={"bear_case[2].segment_0"},
    )

    assert merged.report.bear_case == [
        "First surviving risk.", "Later blocked risk.",
    ]
    assert plan.initial_segment_ids_by_final_segment["bear_case[1].segment_0"] == (
        "bear_case[2].segment_0",
    )
    assert not _carried_by_segment(plan)["bear_case[1].segment_0"].passed
    assert set(plan.deleted_initial_segment_ids) == set(deleted_ids)
    assert not plan.review_segments
    assert not plan.changed_segment_ids
    assert not plan.new_segment_ids
    assert not plan.unreconciled_segment_ids


def test_exhausted_key_risk_item_preserves_later_object_lineage_and_verdict():
    report = _candidate(key_risks=[
        {"risk": "First surviving risk.", "severity": "Low"},
        {
            "risk": "Deleted first proposition. Deleted second proposition.",
            "severity": "High",
        },
        {"risk": "Later blocked risk.", "severity": "Medium"},
    ])
    deleted_ids = [
        "key_risks[1].risk.segment_0", "key_risks[1].risk.segment_1",
    ]
    merged, plan = _correct_and_plan(
        report,
        [_delete(target_id) for target_id in deleted_ids],
        blockers={"key_risks[2].risk.segment_0"},
    )

    assert [risk.model_dump() for risk in merged.report.key_risks] == [
        {"risk": "First surviving risk.", "severity": "Low"},
        {"risk": "Later blocked risk.", "severity": "Medium"},
    ]
    final_id = "key_risks[1].risk.segment_0"
    assert plan.initial_segment_ids_by_final_segment[final_id] == (
        "key_risks[2].risk.segment_0",
    )
    assert not _carried_by_segment(plan)[final_id].passed
    assert set(plan.deleted_initial_segment_ids) == set(deleted_ids)
    assert not plan.review_segments
    assert not plan.changed_segment_ids
    assert not plan.new_segment_ids
    assert not plan.unreconciled_segment_ids


def test_delete_that_recombines_neighbors_requires_fresh_review():
    report = _candidate(
        market_reaction_analysis="First fact, because disputed. Final fact.",
    )
    merged, plan = _correct_and_plan(
        report,
        [_delete("market_reaction_analysis.segment_1")],
    )

    assert merged.report.market_reaction_analysis == "First fact, Final fact."
    assert [segment.coverage_segment_id for segment in plan.review_segments] == [
        "market_reaction_analysis.segment_0",
    ]
    assert plan.initial_segment_ids_by_final_segment["market_reaction_analysis.segment_0"] == (
        "market_reaction_analysis.segment_0",
        "market_reaction_analysis.segment_2",
    )
    assert plan.changed_segment_ids == ("market_reaction_analysis.segment_0",)
    assert "market_reaction_analysis.segment_0" not in _carried_by_segment(plan)
    assert not plan.new_segment_ids


def test_spy_connector_delete_does_not_mutate_passing_left_survivor():
    report = _candidate(
        technical_analysis={
            "trend": (
                "SPY is trading near the upper end of its 52-week range "
                "($629.28 - $779.37) at $765.16, indicating a strong long-term "
                "uptrend. However, the recent 4-day slide and loss of short-term "
                "trend support suggest that short-term momentum is weakening."
            ),
            "support_levels": [],
            "resistance_levels": [],
            "breakout_level": "N/A",
            "breakdown_level": "N/A",
        },
    )
    target_prefix = "technical_analysis.trend.segment_"
    merged, plan = _correct_and_plan(
        report,
        [
            _delete(f"{target_prefix}1"),
            _replace(
                f"{target_prefix}2",
                "SPY and IWM lost short-term trend support.",
            ),
        ],
        blockers={f"{target_prefix}1"},
    )

    assert merged.report.technical_analysis.trend == (
        "SPY is trading near the upper end of its 52-week range "
        "($629.28 - $779.37) at $765.16. "
        "SPY and IWM lost short-term trend support."
    )
    assert plan.initial_segment_ids_by_final_segment[f"{target_prefix}0"] == (
        f"{target_prefix}0",
    )
    assert _carried_by_segment(plan)[f"{target_prefix}0"].passed
    assert [segment.coverage_segment_id for segment in plan.review_segments] == [
        f"{target_prefix}1",
    ]
    assert plan.changed_segment_ids == (f"{target_prefix}1",)


def test_replacement_is_reviewed_and_untouched_sibling_is_carried():
    report = _candidate(
        market_reaction_analysis="Disputed claim. Surviving fact.",
    )
    _, plan = _correct_and_plan(
        report,
        [_replace("market_reaction_analysis.segment_0", "Changed claim.")],
        blockers={"market_reaction_analysis.segment_0"},
    )

    assert [segment.coverage_segment_id for segment in plan.review_segments] == [
        "market_reaction_analysis.segment_0",
    ]
    assert plan.initial_segment_ids_by_final_segment["market_reaction_analysis.segment_0"] == (
        "market_reaction_analysis.segment_0",
    )
    assert _carried_by_segment(plan)["market_reaction_analysis.segment_1"].passed
    assert not plan.new_segment_ids


def test_delete_and_replace_use_original_list_positions_for_lineage():
    report = _candidate(
        key_catalysts=["Deleted claim.", "Disputed claim.", "Surviving fact."],
    )
    merged, plan = _correct_and_plan(
        report,
        [
            _delete("key_catalysts[0].segment_0"),
            _replace("key_catalysts[1].segment_0", "Changed claim."),
        ],
    )

    assert merged.report.key_catalysts == ["Changed claim.", "Surviving fact."]
    assert plan.initial_segment_ids_by_final_segment["key_catalysts[0].segment_0"] == (
        "key_catalysts[1].segment_0",
    )
    assert plan.initial_segment_ids_by_final_segment["key_catalysts[1].segment_0"] == (
        "key_catalysts[2].segment_0",
    )
    assert [segment.coverage_segment_id for segment in plan.review_segments] == [
        "key_catalysts[0].segment_0",
    ]
    assert _carried_by_segment(plan)["key_catalysts[1].segment_0"].passed
    assert not plan.new_segment_ids


def test_missing_provenance_is_reviewed_as_unreconciled_without_text_matching():
    request = _request()
    initial = _candidate(market_reaction_analysis="Original fact.")
    ledger = ollama_service._build_initial_proposition_review_ledger(
        request,
        initial,
        [1],
        _synthetic_review_for_report(request, initial),
    )
    # Equal text is not proof that this extra occurrence descended from the first.
    candidate = _candidate(market_reaction_analysis="Original fact. Original fact.")
    plan = ollama_service._plan_final_proposition_review(
        request, candidate, [1], ledger, [],
    )

    assert _carried_by_segment(plan)["market_reaction_analysis.segment_0"].passed
    assert plan.unreconciled_segment_ids == ("market_reaction_analysis.segment_1",)
    assert [segment.coverage_segment_id for segment in plan.review_segments] == [
        "market_reaction_analysis.segment_1",
    ]
    assert not plan.new_segment_ids


@pytest.mark.parametrize("evidence_change", ["selected_articles", "market_data"])
def test_surviving_text_is_reviewed_when_its_evidence_changes(evidence_change):
    report = _candidate(market_reaction_analysis="Deleted claim. Surviving fact.")
    final_request = _request()
    final_selected = [1]
    if evidence_change == "selected_articles":
        final_selected = [2]
    else:
        final_request.price_data.current_price += 1
    _, plan = _correct_and_plan(
        report,
        [_delete("market_reaction_analysis.segment_0")],
        final_request=final_request,
        final_selected=final_selected,
    )

    assert plan.initial_segment_ids_by_final_segment["market_reaction_analysis.segment_0"] == (
        "market_reaction_analysis.segment_1",
    )
    assert "market_reaction_analysis.segment_0" in plan.evidence_changed_segment_ids
    assert "market_reaction_analysis.segment_0" in {
        segment.coverage_segment_id for segment in plan.review_segments
    }
    assert not plan.carried_entries
    assert not plan.new_segment_ids
