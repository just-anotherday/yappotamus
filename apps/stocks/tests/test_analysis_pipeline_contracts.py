"""Deterministic contracts for Prompt v3 analysis-pipeline identity handoffs.

This suite intentionally keeps ReviewContext test-side in Phase A. Production
``GroundingViolation.target_scope`` is internal-only and makes intentional GLOBAL
failures distinguishable from accidental proposition-identity loss.

Reviewer-derived and deterministic proposition violations must both preserve
``coverage_segment_id``, normalized ``atomic_proposition``, and the patch target
resolved through the current request-local registry.
"""

from dataclasses import dataclass
from types import MappingProxyType, SimpleNamespace
from typing import Mapping, Optional
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from backend.models.analysis import (
    CorrectionPatch,
    CorrectionPatchSet,
    CorrectionPatchTarget,
    CorrectionTargetRegistry,
    FinancialAnalysisLLMResponse,
    FinancialAnalysisRequest,
    FinancialAnalysisResponse,
    GroundingClaimFinding,
    GroundingReviewWireFinding,
    GroundingReviewWireResponse,
    GroundingViolation,
    NewsArticleRequest,
    NormalizedGroundingClaimFinding,
    PriceDataRequest,
    ReviewCoverageSegment,
    ReviewableClaimUnit,
)
from backend.routers import analysis as analysis_router
from backend.services import ollama_service
from backend.services.ai.exceptions import AISemanticGroundingError


class PipelineContractError(AssertionError):
    """Raised at the first lossy pipeline identity handoff."""


@dataclass(frozen=True)
class ScopedBlockingViolation:
    violation: GroundingViolation
    review_unit_id: Optional[str] = None


@dataclass(frozen=True)
class AnalysisReviewContext:
    """Typed, immutable-by-convention request-local review state for tests."""

    candidate_report: FinancialAnalysisLLMResponse
    review_units: tuple[ReviewableClaimUnit, ...]
    coverage_segments: tuple[ReviewCoverageSegment, ...]
    segment_lookup: Mapping[str, ReviewCoverageSegment]
    correction_target_registry: CorrectionTargetRegistry

    @classmethod
    def build(cls, report: FinancialAnalysisLLMResponse) -> "AnalysisReviewContext":
        units = ollama_service._build_reviewable_claim_units(report)
        segments = ollama_service._build_review_coverage_segments(units)
        return cls(
            candidate_report=report,
            review_units=tuple(units),
            coverage_segments=tuple(segments),
            segment_lookup=MappingProxyType(
                {segment.coverage_segment_id: segment for segment in segments}
            ),
            correction_target_registry=ollama_service.build_correction_target_registry(
                units, segments
            ),
        )


def _request(*, articles: Optional[list[NewsArticleRequest]] = None) -> FinancialAnalysisRequest:
    return FinancialAnalysisRequest(
        ticker="AMD",
        company_name="Advanced Micro Devices",
        analysis_date="2026-08-28T12:00:00Z",
        news_articles=articles
        or [
            NewsArticleRequest(
                title="AMD announces a packaging investment",
                summary="AMD announced a strategic packaging investment.",
                source="Trusted Wire",
                published_at="2026-08-28T10:00:00Z",
                url="https://trusted.example/amd-investment",
            ),
            NewsArticleRequest(
                title="AMD shares trade higher",
                summary="AMD shares rose 3% during the session.",
                source="Trusted Market Wire",
                published_at="2026-08-28T11:00:00Z",
                url="https://trusted.example/amd-price",
            ),
        ],
        price_data=PriceDataRequest(
            current_price=100.0,
            daily_change_percent=3.0,
            fifty_two_week_high=120.0,
            fifty_two_week_low=70.0,
            trading_volume=1_000_000,
        ),
    )


def _report_payload(
    *,
    trend: str = (
        "The current price of $100 is between the 52-week high of $120 and low "
        "of $70. Price position implies a range-bound trend."
    ),
) -> dict:
    return {
        "asset": "AMD",
        "overall_sentiment": "Neutral",
        "confidence_score": 62,
        "investment_rating": "Hold",
        "articles_used": [
            {
                "title": "PROVIDER FORGERY",
                "url": "https://evil.invalid/forged",
                "published_at": "1900-01-01T00:00:00Z",
            }
        ],
        "news_summary": ["AMD announced a strategic packaging investment."],
        "key_catalysts": ["Execution could support the company."],
        "key_risks": [{"risk": "Execution risk remains.", "severity": "Medium"}],
        "bull_case": ["Successful execution could support the outlook."],
        "bear_case": ["Execution setbacks could pressure the outlook."],
        "market_reaction_analysis": "AMD shares rose 3% during the session.",
        "technical_analysis": {
            "trend": trend,
            "support_levels": [],
            "resistance_levels": [],
            "breakout_level": "N/A",
            "breakdown_level": "N/A",
        },
        "outlook": {
            "short_term": "Neutral — supplied evidence is mixed.",
            "medium_term": "Neutral — execution remains the key variable.",
            "long_term": "Neutral — long-term evidence remains limited.",
        },
        "actionable_insights": ["Monitor execution against supplied evidence."],
        "portfolio_fit": "Potential satellite exposure with execution risk.",
        "executive_summary": "The supplied evidence supports a neutral stance.",
        "article_indices_used": [1],
    }


def _report(**kwargs) -> FinancialAnalysisLLMResponse:
    return FinancialAnalysisLLMResponse(**_report_payload(**kwargs))


def _unit_lookup(context: AnalysisReviewContext) -> dict[str, ReviewableClaimUnit]:
    return {unit.review_unit_id: unit for unit in context.review_units}


def assert_review_context_identity(context: AnalysisReviewContext) -> None:
    """Validate source, ordinal, segment, and registry identity as one contract."""

    units = _unit_lookup(context)
    if len(units) != len(context.review_units):
        raise PipelineContractError("DUPLICATE_REVIEW_UNIT_ID")
    segment_ids = [item.coverage_segment_id for item in context.coverage_segments]
    if len(segment_ids) != len(set(segment_ids)):
        raise PipelineContractError("DUPLICATE_COVERAGE_SEGMENT_ID")

    expected_ordinals: dict[str, int] = {}
    for segment in context.coverage_segments:
        unit = units.get(segment.review_unit_id)
        if unit is None:
            raise PipelineContractError("UNKNOWN_REVIEW_UNIT")
        expected = expected_ordinals.get(segment.review_unit_id, 0)
        if segment.segment_ordinal != expected:
            raise PipelineContractError("SEGMENT_ORDINAL_DIVERGENCE")
        expected_ordinals[segment.review_unit_id] = expected + 1
        if not (
            0 <= segment.source_start < segment.source_end <= len(unit.candidate_text)
        ):
            raise PipelineContractError("INVALID_SEGMENT_OFFSETS")
        if not unit.candidate_text[segment.source_start : segment.source_end]:
            raise PipelineContractError("EMPTY_SEGMENT_SOURCE_SLICE")

    registry_ids = {
        target.patch_target_id
        for target in context.correction_target_registry.targets
    }
    for target in context.correction_target_registry.targets:
        segment = context.segment_lookup.get(target.patch_target_id)
        unit = units.get(target.source_path)
        if segment is None or unit is None:
            raise PipelineContractError("TARGET_SOURCE_IDENTITY_MISSING")
        if segment.review_unit_id != target.source_path:
            raise PipelineContractError("TARGET_SOURCE_PATH_DIVERGENCE")
        if target.section != unit.section:
            raise PipelineContractError("TARGET_SECTION_DIVERGENCE")
        if (target.source_start, target.source_end) != (
            segment.source_start,
            segment.source_end,
        ):
            raise PipelineContractError("TARGET_OFFSET_DIVERGENCE")
        if (
            unit.candidate_text[target.source_start : target.source_end]
            != target.original_target_text
        ):
            raise PipelineContractError("STALE_TARGET_SOURCE_SLICE")
        if context.correction_target_registry.get(target.patch_target_id) is not target:
            raise PipelineContractError("REGISTRY_LOOKUP_DIVERGENCE")
    if len(registry_ids) != len(context.correction_target_registry.targets):
        raise PipelineContractError("DUPLICATE_PATCH_TARGET_ID")


def assert_proposition_targetability(
    context: AnalysisReviewContext,
    scoped: ScopedBlockingViolation,
) -> None:
    """Generalized targetability invariant for every proposition blocker."""

    if scoped.violation.target_scope == "GLOBAL":
        return
    violation = scoped.violation
    if not violation.coverage_segment_id:
        raise PipelineContractError("BUG_UNMAPPABLE: missing coverage_segment_id")
    if not violation.atomic_proposition:
        raise PipelineContractError("BUG_UNMAPPABLE: missing atomic_proposition")
    segment = context.segment_lookup.get(violation.coverage_segment_id)
    if segment is None:
        raise PipelineContractError("BUG_UNMAPPABLE: unknown coverage_segment_id")
    if scoped.review_unit_id and segment.review_unit_id != scoped.review_unit_id:
        raise PipelineContractError("BUG_UNMAPPABLE: review_unit_id mismatch")
    target = context.correction_target_registry.get(violation.coverage_segment_id)
    if target is None:
        raise PipelineContractError("BUG_UNMAPPABLE: registry lookup failed")
    if violation.patch_target_id != target.patch_target_id:
        raise PipelineContractError("BUG_UNMAPPABLE: patch_target_id mismatch")
    if target not in context.correction_target_registry.targets:
        raise PipelineContractError("BUG_UNMAPPABLE: foreign request-local target")
    unit = _unit_lookup(context).get(target.source_path)
    if unit is None:
        raise PipelineContractError("BUG_UNMAPPABLE: trusted source path missing")
    if not (0 <= target.source_start < target.source_end <= len(unit.candidate_text)):
        raise PipelineContractError("BUG_UNMAPPABLE: invalid target offsets")
    source_slice = unit.candidate_text[target.source_start : target.source_end]
    if source_slice != target.original_target_text:
        raise PipelineContractError("BUG_UNMAPPABLE: stale target text")
    if not violation.atomic_proposition.strip():
        raise PipelineContractError("BUG_UNMAPPABLE: empty proposition identity")


def _scoped(
    violation: GroundingViolation,
    context: AnalysisReviewContext,
) -> ScopedBlockingViolation:
    target = (
        context.correction_target_registry.get(violation.patch_target_id)
        if violation.patch_target_id
        else None
    )
    return ScopedBlockingViolation(
        violation=violation,
        review_unit_id=target.source_path if target else None,
    )


def _violation_for_target(
    context: AnalysisReviewContext,
    target_id: str,
    *,
    rule: str = "unsupported_company_specific_claim",
) -> GroundingViolation:
    target = context.correction_target_registry.get(target_id)
    assert target is not None
    return GroundingViolation(
        rule=rule,
        section=target.section,
        issue="Synthetic deterministic proposition blocker.",
        coverage_segment_id=target.patch_target_id,
        atomic_proposition=target.original_target_text,
        patch_target_id=target.patch_target_id,
    )


def _failure_kind(callable_) -> str:
    with pytest.raises(AISemanticGroundingError) as exc_info:
        callable_()
    return exc_info.value.details["failure_kind"]


def _patch(
    target_id: str,
    *,
    operation: str = "REPLACE",
    replacement: Optional[str] = "Supported replacement.",
    indices: Optional[list[int]] = None,
) -> dict:
    return {
        "target_id": target_id,
        "operation": operation,
        "replacement": replacement,
        "article_indices_used": [] if indices is None else indices,
    }


def test_review_context_uses_production_segmentation_and_preserves_all_identity():
    context = AnalysisReviewContext.build(_report())

    assert_review_context_identity(context)
    assert context.segment_lookup["technical_analysis.trend.segment_0"]
    assert context.segment_lookup["technical_analysis.trend.segment_1"]
    for segment in context.coverage_segments:
        unit = _unit_lookup(context)[segment.review_unit_id]
        assert unit.candidate_text[segment.source_start : segment.source_end].strip()


def test_registry_identity_is_backend_owned_context_independent_and_unique():
    context = AnalysisReviewContext.build(_report())
    target = context.correction_target_registry.get(
        "technical_analysis.trend.segment_1"
    )
    assert target is not None
    changed_context = target.model_copy(
        update={"previous_context": "changed", "next_context": "also changed"}
    )
    assert changed_context.patch_target_id == target.patch_target_id
    assert changed_context.source_path == target.source_path
    assert changed_context.source_start == target.source_start
    assert changed_context.source_end == target.source_end

    with pytest.raises(ValidationError, match="unique"):
        CorrectionTargetRegistry(targets=[target, target.model_copy()])


def test_target_scope_remains_internal_and_absent_from_public_and_wire_schemas():
    assert "target_scope" in GroundingViolation.model_fields
    assert "target_scope" not in FinancialAnalysisResponse.model_fields
    assert "target_scope" not in GroundingReviewWireFinding.model_fields


def test_historical_range_fact_survives_while_range_to_trend_is_exactly_targeted():
    request = _request()
    report = _report()
    context = AnalysisReviewContext.build(report)
    violations = ollama_service._deterministic_grounding_violations(
        request, report, [1]
    )

    assert len(violations) == 1
    violation = violations[0]
    assert violation.rule == "historical_range_not_technical_level"
    assert violation.patch_target_id == "technical_analysis.trend.segment_1"
    assert violation.atomic_proposition == "Price position implies a range-bound trend."
    assert "current price" not in violation.atomic_proposition.lower()
    assert_proposition_targetability(context, _scoped(violation, context))
    assert ollama_service.derive_required_patch_targets(violations) == [
        "technical_analysis.trend.segment_1"
    ]


def test_general_contract_catches_pre_repair_historical_bug_as_bug_unmappable():
    context = AnalysisReviewContext.build(_report())
    pre_repair = GroundingViolation(
        rule="historical_range_not_technical_level",
        section="technical_analysis",
        issue="Range position was used as trend.",
    )

    with pytest.raises(PipelineContractError, match="BUG_UNMAPPABLE"):
        assert_proposition_targetability(
            context,
            ScopedBlockingViolation(pre_repair),
        )


def test_explicit_global_unmappable_control_never_invents_a_target():
    context = AnalysisReviewContext.build(_report())
    global_violation = GroundingViolation(
        rule="scope_preservation",
        section="multiple_sections",
        issue="Synthetic request-global consistency failure.",
        target_scope="GLOBAL",
    )
    scoped = ScopedBlockingViolation(global_violation)

    assert global_violation.target_scope == "GLOBAL"
    assert_proposition_targetability(context, scoped)
    assert global_violation.patch_target_id is None
    assert _failure_kind(
        lambda: ollama_service.derive_required_patch_targets([global_violation])
    ) == "correction_patch_unmappable_violation"


@pytest.mark.asyncio
async def test_true_unmappable_fails_closed_before_provider_correction():
    context = AnalysisReviewContext.build(_report())
    provider = SimpleNamespace(generate=AsyncMock(side_effect=AssertionError("no call")))
    violation = GroundingViolation(
        rule="scope_preservation",
        section="multiple_sections",
        issue="Global blocker.",
        target_scope="GLOBAL",
    )

    with pytest.raises(AISemanticGroundingError) as exc_info:
        await ollama_service.generate_correction_patch_set(
            provider,
            _request(),
            context.correction_target_registry,
            [violation],
            None,
            provider="ollama",
            model="fixture-model",
        )
    assert exc_info.value.details["failure_kind"] == (
        "correction_patch_unmappable_violation"
    )
    provider.generate.assert_not_awaited()


def test_same_target_multiple_rules_deduplicates_required_patch_identity():
    context = AnalysisReviewContext.build(_report())
    target_id = "technical_analysis.trend.segment_1"
    violations = [
        _violation_for_target(
            context, target_id, rule="historical_range_not_technical_level"
        ),
        _violation_for_target(
            context, target_id, rule="unsupported_company_specific_claim"
        ),
    ]
    for violation in violations:
        assert_proposition_targetability(context, _scoped(violation, context))

    assert ollama_service.derive_required_patch_targets(violations) == [target_id]


def test_multiple_targets_survive_independently_and_only_exact_targets_are_required():
    context = AnalysisReviewContext.build(_report())
    target_ids = [
        "bull_case[0].segment_0",
        "bear_case[0].segment_0",
        "technical_analysis.trend.segment_1",
    ]
    violations = [_violation_for_target(context, item) for item in target_ids]
    for violation in violations:
        assert_proposition_targetability(context, _scoped(violation, context))

    assert ollama_service.derive_required_patch_targets(violations) == sorted(
        target_ids
    )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda violation: violation.model_copy(
                update={"coverage_segment_id": None}
            ),
            "missing coverage_segment_id",
        ),
        (
            lambda violation: violation.model_copy(
                update={"coverage_segment_id": "unknown.segment_9"}
            ),
            "unknown coverage_segment_id",
        ),
            (
                lambda violation: violation.model_copy(
                    update={"atomic_proposition": " "}
                ),
                "empty proposition identity",
            ),
    ],
)
def test_coverage_identity_failure_injection_fails_at_general_boundary(
    mutation, message
):
    context = AnalysisReviewContext.build(_report())
    valid = _violation_for_target(context, "bull_case[0].segment_0")

    with pytest.raises(PipelineContractError, match=message):
        assert_proposition_targetability(context, _scoped(mutation(valid), context))


def test_segment_belonging_to_wrong_review_unit_fails_at_general_boundary():
    context = AnalysisReviewContext.build(_report())
    violation = _violation_for_target(context, "bull_case[0].segment_0")

    with pytest.raises(PipelineContractError, match="review_unit_id mismatch"):
        assert_proposition_targetability(
            context,
            ScopedBlockingViolation(
                violation, review_unit_id="bear_case[0]"
            ),
        )


def test_stale_request_local_segment_identity_is_rejected():
    initial = AnalysisReviewContext.build(_report())
    corrected = AnalysisReviewContext.build(
        _report(trend="The current price remains within the supplied 52-week range.")
    )
    stale = _violation_for_target(initial, "technical_analysis.trend.segment_1")

    with pytest.raises(PipelineContractError, match="unknown coverage_segment_id"):
        assert_proposition_targetability(corrected, _scoped(stale, corrected))


@pytest.mark.parametrize(
    ("patches", "required", "expected"),
    [
        (
            [_patch("unknown.segment_0")],
            ["unknown.segment_0"],
            "correction_patch_unknown_target",
        ),
        (
            [_patch("bull_case[0].segment_0")],
            ["bear_case[0].segment_0"],
            "correction_patch_unauthorized_target",
        ),
        (
            [
                _patch("bull_case[0].segment_0"),
                _patch("bull_case[0].segment_0"),
            ],
            ["bull_case[0].segment_0"],
            "correction_patch_duplicate_target",
        ),
        (
            [_patch("bull_case[0].segment_0")],
            ["bull_case[0].segment_0", "bear_case[0].segment_0"],
            "correction_patch_incomplete_target_set",
        ),
        (
            [
                _patch("bull_case[0].segment_0"),
                _patch("bear_case[0].segment_0"),
            ],
            ["bull_case[0].segment_0"],
            "correction_patch_unauthorized_target",
        ),
    ],
)
def test_patch_target_failure_kinds_are_exact(patches, required, expected):
    registry = AnalysisReviewContext.build(_report()).correction_target_registry
    assert _failure_kind(
        lambda: ollama_service.validate_correction_patch_set(
            {"patches": patches}, registry, required
        )
    ) == expected


@pytest.mark.parametrize(
    "patch",
    [
        _patch(
            "bull_case[0].segment_0",
            operation="DELETE",
            replacement="not allowed",
        ),
        _patch("bull_case[0].segment_0", replacement=None),
        _patch("bull_case[0].segment_0", replacement=" padded "),
        _patch("bull_case[0].segment_0", replacement="line one\nline two"),
        _patch(
            "bull_case[0].segment_0",
            replacement="First proposition. Second proposition.",
        ),
        _patch("bull_case[0].segment_0", replacement="x" * 401),
        _patch("bull_case[0].segment_0", indices=[0]),
        _patch("bull_case[0].segment_0", indices=[1, 1]),
    ],
)
def test_patch_operation_contract_rejects_invalid_provider_values(patch):
    context = AnalysisReviewContext.build(_report())
    target_id = "bull_case[0].segment_0"
    assert _failure_kind(
        lambda: ollama_service.validate_correction_patch_set(
            {"patches": [patch]},
            context.correction_target_registry,
            [target_id],
            article_count=2,
        )
    ) in {
        "correction_patch_schema_invalid",
        "correction_patch_attribution_invalid",
    }


def test_delete_and_replace_operation_and_attribution_contracts():
    context = AnalysisReviewContext.build(_report())
    replace_id = "bull_case[0].segment_0"
    delete_id = "key_catalysts[0].segment_0"
    patch_set = ollama_service.validate_correction_patch_set(
        {
            "patches": [
                _patch(replace_id, replacement="Conditional support remains.", indices=[2]),
                _patch(
                    delete_id,
                    operation="DELETE",
                    replacement=None,
                    indices=[],
                ),
            ]
        },
        context.correction_target_registry,
        [replace_id, delete_id],
        article_count=2,
    )

    assert patch_set.patches[0].replacement == "Conditional support remains."
    assert patch_set.patches[0].article_indices_used == [2]
    assert patch_set.patches[1].replacement is None
    assert patch_set.patches[1].article_indices_used == []
    assert set(CorrectionPatch.model_fields) == {
        "target_id",
        "operation",
        "replacement",
        "article_indices_used",
    }
    with pytest.raises(ValidationError):
        CorrectionPatch(
            target_id=replace_id,
            operation="REPLACE",
            replacement="Valid text.",
            article_indices_used=[],
            source_path="provider.controlled",
            source_start=0,
        )


@pytest.mark.parametrize("mode", ["stale_text", "invalid_offsets", "out_of_bounds"])
def test_source_span_failure_injection_rejects_atomically(mode):
    report = _report()
    context = AnalysisReviewContext.build(report)
    target_id = "bull_case[0].segment_0"
    target = context.correction_target_registry.get(target_id)
    assert target is not None
    if mode == "stale_text":
        forged = target.model_copy(update={"original_target_text": "stale"})
    elif mode == "invalid_offsets":
        forged = target.model_copy(
            update={"source_start": target.source_start + 1}
        )
    else:
        forged = target.model_copy(update={"source_end": 99_999})
    registry = CorrectionTargetRegistry(
        targets=[
            forged if item.patch_target_id == target_id else item
            for item in context.correction_target_registry.targets
        ]
    )
    original = report.model_dump(mode="python")

    assert _failure_kind(
        lambda: ollama_service.merge_correction_patch_set(
            report,
            registry,
            [target_id],
            {"patches": [_patch(target_id)]},
        )
    ) == "correction_patch_merge_failure"
    assert report.model_dump(mode="python") == original


def test_overlapping_patch_spans_are_rejected_without_mutating_primary():
    report = _report()
    context = AnalysisReviewContext.build(report)
    first_id = "technical_analysis.trend.segment_0"
    second_id = "technical_analysis.trend.segment_1"
    first = context.correction_target_registry.get(first_id)
    second = context.correction_target_registry.get(second_id)
    assert first is not None and second is not None
    source = report.technical_analysis.trend
    overlap = second.model_copy(
        update={
            "source_start": first.source_start + 1,
            "source_end": first.source_end,
            "original_target_text": source[first.source_start + 1 : first.source_end],
        }
    )
    registry = CorrectionTargetRegistry(
        targets=[
            overlap if item.patch_target_id == second_id else item
            for item in context.correction_target_registry.targets
        ]
    )
    original = report.model_dump(mode="python")

    assert _failure_kind(
        lambda: ollama_service.merge_correction_patch_set(
            report,
            registry,
            [first_id, second_id],
            {"patches": [_patch(first_id), _patch(second_id)]},
        )
    ) == "correction_patch_merge_failure"
    assert report.model_dump(mode="python") == original


def _normalized_finding(
    context: AnalysisReviewContext,
    target_id: str,
    proposition: str,
    *,
    rule: str,
) -> NormalizedGroundingClaimFinding:
    target = context.correction_target_registry.get(target_id)
    assert target is not None
    return NormalizedGroundingClaimFinding(
        review_unit_id=target.source_path,
        coverage_segment_id=target_id,
        atomic_ordinal=0,
        atomic_claim_id=f"{target.source_path}.atomic_0",
        section=target.section,
        claim_role="interpretation",
        atomic_proposition=proposition,
        classification="supported_interpretation",
        supporting_article_indices=[1],
        supporting_selected_indices=[1],
        supporting_unselected_indices=[],
        supporting_market_data_fields=[],
        rule=rule,
    )


@pytest.mark.parametrize(
    ("summary", "proposition", "rule", "missing_relationship"),
    [
        (
            "AMD announced a strategic packaging investment. AMD shares rose 3% today.",
            "AMD shares rose after the packaging investment.",
            "event_price_impact_grounding",
            ollama_service.EVENT_PRICE_LINK,
        ),
        (
            "AMD shares rose 3% today.",
            "Investors welcomed the move.",
            "investor_motive_grounding",
            ollama_service.INVESTOR_MOTIVE_LINK,
        ),
    ],
)
def test_relationship_continuity_is_proposition_scoped_and_does_not_bleed(
    summary, proposition, rule, missing_relationship
):
    request = _request(
        articles=[NewsArticleRequest(title="AMD update", summary=summary)]
    )
    report = _report()
    context = AnalysisReviewContext.build(report)
    target_id = "market_reaction_analysis.segment_0"
    finding = _normalized_finding(context, target_id, proposition, rule=rule)
    manifest = ollama_service._build_article_relationship_manifest(request)
    relationship_types = {
        item.relationship_type for item in manifest.get(1, [])
    }
    violations = ollama_service._claim_findings_to_violations(
        [finding], manifest, context.correction_target_registry
    )

    assert missing_relationship not in relationship_types
    assert len(violations) == 1
    assert violations[0].rule == rule
    assert violations[0].coverage_segment_id == target_id
    assert violations[0].atomic_proposition == proposition
    assert violations[0].patch_target_id == target_id
    assert_proposition_targetability(context, _scoped(violations[0], context))


@pytest.mark.parametrize(
    ("proposition", "expected_fields"),
    [
        ("AMD is trading at $100", ["current_price"]),
        ("AMD's daily change is +3%", ["daily_change_percent"]),
        (
            "AMD is trading at $100 within its 52-week range of $70 to $120",
            ["current_price", "fifty_two_week_low", "fifty_two_week_high"],
        ),
    ],
)
def test_structured_market_facts_keep_exact_field_associations(
    proposition, expected_fields
):
    claim = GroundingClaimFinding(
        review_unit_id="_legacy_technical_analysis",
        coverage_segment_id="_legacy_technical_analysis.segment_0",
        atomic_ordinal=0,
        claim_role="fact",
        atomic_proposition=proposition,
        classification="unsupported_by_any_evidence",
        supporting_article_indices=[],
        supporting_market_data_fields=[],
        rule="unsupported_company_specific_claim",
    )
    ollama_service._validate_reviewer_finding_metadata([claim], _request())
    normalized = ollama_service._normalize_claim_findings([claim], [1])

    assert normalized[0].backend_derived_market_fields == expected_fields
    assert not ollama_service._claim_findings_to_violations(normalized)


@pytest.mark.parametrize(
    "proposition",
    [
        "The 52-week range proves a range-bound trend.",
        "The +3% move proves investors welcomed the announcement.",
    ],
)
def test_structured_market_data_never_rescues_inference_or_investor_motive(
    proposition
):
    claim = GroundingClaimFinding(
        review_unit_id="_legacy_market_reaction_analysis",
        coverage_segment_id="_legacy_market_reaction_analysis.segment_0",
        atomic_ordinal=0,
        claim_role="interpretation",
        atomic_proposition=proposition,
        classification="unsupported_by_any_evidence",
        supporting_article_indices=[],
        supporting_market_data_fields=[],
        rule="unsupported_company_specific_claim",
    )
    ollama_service._validate_reviewer_finding_metadata([claim], _request())
    normalized = ollama_service._normalize_claim_findings([claim], [1])

    assert normalized[0].backend_derived_market_fields == []
    assert ollama_service._claim_findings_to_violations(normalized)


def test_article_attribution_is_sanitized_mapped_and_conservatively_unioned():
    request = _request()
    primary = ollama_service._sanitize_article_indices(
        [2, 1, 2, 0, 99, True], len(request.news_articles)
    )
    context = AnalysisReviewContext.build(_report())
    replace_id = "bull_case[0].segment_0"
    delete_id = "key_catalysts[0].segment_0"
    patch_set = CorrectionPatchSet(
        patches=[
            CorrectionPatch(
                target_id=replace_id,
                operation="REPLACE",
                replacement="Conditional support remains.",
                article_indices_used=[2],
            ),
            CorrectionPatch(
                target_id=delete_id,
                operation="DELETE",
                replacement=None,
                article_indices_used=[],
            ),
        ]
    )
    ollama_service.validate_correction_patch_set(
        patch_set,
        context.correction_target_registry,
        [replace_id, delete_id],
        article_count=2,
    )
    patch_indices = ollama_service._patch_article_indices(patch_set, 2)
    final = ollama_service._merge_citation_indices(primary, patch_indices, 2)
    trusted = ollama_service._resolve_articles_used(final, request.news_articles)

    assert primary == [2, 1]
    assert patch_indices == [2]
    assert final == [2, 1]
    assert [item.title for item in trusted] == [
        request.news_articles[1].title,
        request.news_articles[0].title,
    ]
    assert [item.url for item in trusted] == [
        request.news_articles[1].url,
        request.news_articles[0].url,
    ]
    assert set(type(trusted[0]).model_fields) == {"title", "url", "published_at"}


def test_reviewer_derived_violation_preserves_generalized_contract_identity():
    context = AnalysisReviewContext.build(_report())
    target_id = "bear_case[0].segment_0"
    target = context.correction_target_registry.get(target_id)
    assert target is not None
    finding = NormalizedGroundingClaimFinding(
        review_unit_id=target.source_path,
        coverage_segment_id=target_id,
        atomic_ordinal=0,
        atomic_claim_id="bear_case[0].atomic_0",
        section="bear_case",
        claim_role="fact",
        atomic_proposition=target.original_target_text,
        classification="unsupported_by_any_evidence",
        supporting_article_indices=[],
        supporting_selected_indices=[],
        supporting_unselected_indices=[],
        supporting_market_data_fields=[],
        rule="unsupported_company_specific_claim",
    )
    reviewer_violation = ollama_service._claim_findings_to_violations(
        [finding], registry=context.correction_target_registry
    )[0]

    assert reviewer_violation.target_scope == "PROPOSITION"
    assert reviewer_violation.patch_target_id == target_id
    assert reviewer_violation.coverage_segment_id == target_id
    assert reviewer_violation.atomic_proposition == target.original_target_text
    assert_proposition_targetability(
        context,
        ScopedBlockingViolation(
            reviewer_violation,
            review_unit_id=target.source_path,
        ),
    )


def _blocking_finding(
    context: AnalysisReviewContext,
    target_id: str,
    proposition: str,
    *,
    atomic_ordinal: int = 0,
) -> NormalizedGroundingClaimFinding:
    target = context.correction_target_registry.get(target_id)
    assert target is not None
    return NormalizedGroundingClaimFinding(
        review_unit_id=target.source_path,
        coverage_segment_id=target_id,
        atomic_ordinal=atomic_ordinal,
        atomic_claim_id=f"{target.source_path}.atomic_{atomic_ordinal}",
        section=target.section,
        claim_role="interpretation",
        atomic_proposition=proposition,
        classification="unsupported_by_any_evidence",
        supporting_article_indices=[],
        supporting_selected_indices=[],
        supporting_unselected_indices=[],
        supporting_market_data_fields=[],
        rule="unsupported_company_specific_claim",
    )


def test_deterministic_and_reviewer_violations_share_one_generalized_contract():
    report = _report()
    context = AnalysisReviewContext.build(report)
    deterministic = ollama_service._deterministic_grounding_violations(
        _request(), report, [1]
    )[0]
    target_id = deterministic.patch_target_id
    assert target_id is not None
    target = context.correction_target_registry.get(target_id)
    assert target is not None
    reviewer = ollama_service._claim_findings_to_violations(
        [_blocking_finding(context, target_id, target.original_target_text)],
        registry=context.correction_target_registry,
    )[0]

    for violation in (deterministic, reviewer):
        assert_proposition_targetability(context, _scoped(violation, context))
        assert violation.coverage_segment_id == target_id
        assert violation.patch_target_id == target_id
    assert ollama_service.derive_required_patch_targets(
        [deterministic, reviewer]
    ) == [target_id]


def test_multiple_atomic_findings_share_segment_without_losing_proposition_identity():
    context = AnalysisReviewContext.build(_report())
    target_id = "executive_summary.segment_0"
    findings = [
        _blocking_finding(
            context, target_id, "First unsupported atomic proposition.", atomic_ordinal=0
        ),
        _blocking_finding(
            context, target_id, "Second unsupported atomic proposition.", atomic_ordinal=1
        ),
    ]
    violations = ollama_service._claim_findings_to_violations(
        findings, registry=context.correction_target_registry
    )

    assert [item.atomic_proposition for item in violations] == [
        finding.atomic_proposition for finding in findings
    ]
    assert {item.coverage_segment_id for item in violations} == {target_id}
    assert {item.patch_target_id for item in violations} == {target_id}
    for violation in violations:
        assert_proposition_targetability(context, _scoped(violation, context))
    assert ollama_service.derive_required_patch_targets(violations) == [target_id]


def test_multiple_rules_on_same_atomic_claim_keep_one_normalized_target():
    context = AnalysisReviewContext.build(_report())
    target_id = "bear_case[0].segment_0"
    base = ollama_service._claim_findings_to_violations(
        [
            _blocking_finding(
                context,
                target_id,
                "Execution setbacks could pressure the outlook.",
            )
        ],
        registry=context.correction_target_registry,
    )[0]
    violations = [
        base,
        base.model_copy(update={"rule": "scope_preservation"}),
    ]

    assert len({item.coverage_segment_id for item in violations}) == 1
    assert len({item.atomic_proposition for item in violations}) == 1
    assert len({item.patch_target_id for item in violations}) == 1
    assert ollama_service.derive_required_patch_targets(violations) == [target_id]


def test_cross_batch_alias_fails_before_violation_identity_can_be_created():
    context = AnalysisReviewContext.build(_report())
    segments = list(context.coverage_segments[:2])
    aliases = ollama_service._build_coverage_segment_aliases(segments)
    second_batch = {"s1": aliases["s1"]}
    forged = GroundingReviewWireResponse(
        f={
            "s0": [{
                "r": "F",
                "p": "Unsupported proposition.",
                "c": "UE",
                "a": [],
                "m": [],
                "g": "UC",
            }]
        }
    )

    with pytest.raises(
        ollama_service.ReviewerMetadataError,
        match="unknown_coverage_segment_alias",
    ):
        ollama_service._decode_grounding_review_wire_response(
            forged, second_batch, []
        )


def test_reviewer_blocker_uses_normal_patch_merge_and_fresh_context_flow():
    payload = _report_payload()
    payload["executive_summary"] = (
        "Unsupported company claim. Preserve this supported proposition."
    )
    report = FinancialAnalysisLLMResponse(**payload)
    initial = AnalysisReviewContext.build(report)
    target_id = "executive_summary.segment_0"
    violation = ollama_service._claim_findings_to_violations(
        [
            _blocking_finding(
                initial, target_id, "Unsupported company claim."
            )
        ],
        registry=initial.correction_target_registry,
    )[0]
    assert_proposition_targetability(initial, _scoped(violation, initial))
    required = ollama_service.derive_required_patch_targets([violation])

    merged = ollama_service.merge_correction_patch_set(
        report,
        initial.correction_target_registry,
        required,
        {
            "patches": [
                _patch(
                    target_id,
                    replacement="Supported company-specific limitation.",
                    indices=[1],
                )
            ]
        },
    )
    fresh = AnalysisReviewContext.build(merged.report)

    assert report.executive_summary.startswith("Unsupported company claim.")
    assert merged.report.executive_summary == (
        "Supported company-specific limitation. Preserve this supported proposition."
    )
    assert merged.review_units == list(fresh.review_units)
    assert merged.coverage_segments == list(fresh.coverage_segments)
    assert_review_context_identity(fresh)


class _DeterministicPipelineClient:
    """No-network provider fixture that emits schema-valid deterministic JSON."""

    def __init__(self):
        self.review_payloads: list[dict] = []
        self.patch_calls = 0

    async def generate(self, **kwargs):
        import json

        system_prompt = kwargs["system_prompt"]
        if system_prompt == ollama_service.SYSTEM_PROMPT:
            payload = _report_payload()
            payload["article_indices_used"] = [1, 1, 0, 99]
            return json.dumps(payload)
        if system_prompt == ollama_service.PATCH_CORRECTION_SYSTEM_PROMPT:
            self.patch_calls += 1
            correction = json.loads(
                kwargs["user_prompt"].split("Correction request (JSON):\n", 1)[1]
            )
            assert [item["target_id"] for item in correction["targets"]] == [
                "technical_analysis.trend.segment_1"
            ]
            return json.dumps(
                {
                    "patches": [
                        {
                            "target_id": "technical_analysis.trend.segment_1",
                            "operation": "DELETE",
                            "replacement": None,
                            "article_indices_used": [],
                        }
                    ]
                }
            )

        review_payload = json.loads(kwargs["user_prompt"].split("\n", 1)[1])
        self.review_payloads.append(review_payload)
        return json.dumps(
            {
                "f": {
                    segment["s"]: [{
                        "r": "F",
                        "p": segment["segment_text"][:120],
                        "c": "DS",
                        "a": [1],
                        "m": [],
                        "g": "AS",
                    }]
                    for segment in review_payload["review_coverage_segments"]
                }
            }
        )


@pytest.mark.asyncio
async def test_end_to_end_no_ai_pipeline_carries_unchanged_review_and_trusted_citations(
    monkeypatch,
):
    client = _DeterministicPipelineClient()

    async def validate_provider_model(provider_id, model_name):
        assert provider_id == "ollama"
        assert model_name == "fixture-model"
        return provider_id, model_name, client

    monkeypatch.setattr(
        "backend.services.ai.ai_service.validate_provider_model",
        validate_provider_model,
    )
    result = await ollama_service.generate_analysis(
        _request(), provider="ollama", model="fixture-model"
    )

    assert client.patch_calls == 1
    assert len(client.review_payloads) == 1
    initial = client.review_payloads[0]
    initial_texts = [
        item["segment_text"] for item in initial["review_coverage_segments"]
    ]
    invalid = "Price position implies a range-bound trend."
    assert invalid in initial_texts
    assert invalid in initial["report_under_review"]["technical_analysis"]["trend"]
    assert result.technical_analysis.trend == (
        "The current price of $100 is between the 52-week high of $120 and low of $70."
    )
    assert [article.title for article in result.articles_used] == [
        _request().news_articles[0].title
    ]
    assert result.articles_used[0].url == _request().news_articles[0].url
    assert result.articles_used[0].title != "PROVIDER FORGERY"
    assert result.articles_used[0].url != "https://evil.invalid/forged"


def _route_state(monkeypatch, generated):
    article = SimpleNamespace(
        id=1,
        title="Trusted route article",
        summary="Trusted route summary.",
        provider_name="Trusted Route Wire",
        article_url="https://trusted.example/route",
        pub_date=None,
    )

    async def execute(_statement):
        return SimpleNamespace(
            scalars=lambda: SimpleNamespace(all=lambda: [article])
        )

    session = SimpleNamespace(execute=execute, commit=AsyncMock())
    generate = AsyncMock(side_effect=generated) if isinstance(generated, Exception) else AsyncMock(return_value=generated)
    persist = AsyncMock(return_value=77)
    pipeline = SimpleNamespace(
        version="3.0",
        generate=generate,
        prompt_hash=lambda _request: "hash",
    )
    monkeypatch.setattr(
        analysis_router,
        "get_current_analysis_prompt_pipeline",
        lambda: pipeline,
    )
    monkeypatch.setattr(analysis_router, "create_report", persist)
    monkeypatch.setattr(
        analysis_router,
        "get_hybrid_stock_price",
        AsyncMock(
            return_value={
                "current_price": 100.0,
                "previous_close": 97.0,
                "fifty_two_week_high": 120.0,
                "fifty_two_week_low": 70.0,
                "volume": 1_000_000,
                "company_name": "Advanced Micro Devices",
            }
        ),
    )
    monkeypatch.setattr(
        analysis_router, "resolve_provider_model", lambda *_: ("ollama", "fixture-model")
    )
    monkeypatch.setattr(analysis_router, "_get_timeout_for_model", lambda *_: 30)
    return session, generate, persist


async def _call_route(session):
    return await analysis_router.analysis_analyze_ticker(
        ticker="AMD",
        max_articles=1,
        days_back=3,
        model=None,
        provider=None,
        article_ids=[1],
        session=session,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure_kind",
    [
        "primary_validation_failed",
        "correction_patch_unmappable_violation",
        "correction_patch_schema_invalid",
        "correction_patch_merge_failure",
        "semantic_grounding_rejected",
    ],
)
async def test_persistence_gate_rejects_every_pre_acceptance_failure(
    monkeypatch, failure_kind
):
    error = AISemanticGroundingError(
        "deterministic fixture failure", details={"failure_kind": failure_kind}
    )
    session, _generate, persist = _route_state(monkeypatch, error)

    with pytest.raises(AISemanticGroundingError):
        await _call_route(session)
    persist.assert_not_awaited()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_persistence_gate_opens_only_after_semantic_acceptance(monkeypatch):
    accepted = _report(
        trend="The current price remains within the supplied 52-week range."
    )
    session, generate, persist = _route_state(monkeypatch, accepted)

    result = await _call_route(session)

    generate.assert_awaited_once()
    persist.assert_awaited_once()
    session.commit.assert_awaited_once()
    assert result.report_id == 77
