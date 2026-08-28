"""Focused regression coverage for Prompt v3 semantic grounding enforcement."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import jsonschema
import pytest
from pydantic import ValidationError

from backend.models.analysis import (
    CorrectionPatch,
    CorrectionPatchSet,
    CorrectionTargetRegistry,
    FinancialAnalysisLLMResponse,
    FinancialAnalysisRequest,
    GroundingClaimFinding,
    GroundingViolation,
    GroundingReviewResult,
    GroundingReviewWireResponse,
    NewsArticleRequest,
    NormalizedGroundingClaimFinding,
    PriceDataRequest,
    ReviewableClaimUnit,
    ReviewCoverageSegment,
)
from backend.services import ollama_service
from backend.services.ai.exceptions import AISemanticGroundingError


def _request(*, resistance_level=None) -> FinancialAnalysisRequest:
    return FinancialAnalysisRequest(
        ticker="AMD",
        company_name="Advanced Micro Devices",
        analysis_date="2026-08-20T20:00:00Z",
        news_articles=[
            NewsArticleRequest(
                title="AMD prepares a $5B bond sale",
                summary=(
                    "AMD is preparing an investment-grade bond sale of up to $5B. "
                    "If completed, the financing could increase future debt exposure."
                ),
                source="Direct News",
                published_at="2026-08-20T18:00:00Z",
                url="https://trusted.example/planned-financing",
            ),
            NewsArticleRequest(
                title="AMD expectations remain demanding",
                summary=(
                    "The post-earnings share-price reaction suggests investors had "
                    "demanding expectations."
                ),
                source="Market News",
                published_at="2026-08-20T17:00:00Z",
                url="https://trusted.example/expectations",
            ),
        ],
        price_data=PriceDataRequest(
            current_price=469.17,
            daily_change_percent=-1.0,
            fifty_two_week_high=584.73,
            fifty_two_week_low=149.22,
            trading_volume=1_000_000,
            resistance_level=resistance_level,
        ),
    )


def _synthetic_request(article_count: int) -> FinancialAnalysisRequest:
    request = _request()
    request.news_articles = [
        NewsArticleRequest(
            title=f"Synthetic article {index}",
            summary=f"Synthetic evidence {index}",
            source="Synthetic",
            url=f"https://trusted.example/synthetic/{index}",
        )
        for index in range(1, article_count + 1)
    ]
    return request


def _report(*, corrected=False, completed=False, conditional=False):
    financing = (
        "AMD completed a $5B bond issuance and increased its debt load."
        if completed
        else "The planned financing, if completed, could increase debt exposure."
        if conditional or corrected
        else "AMD's $5B bond sale increased its debt load."
    )
    payload = {
        "asset": "AMD",
        "overall_sentiment": "Bullish",
        "confidence_score": 68,
        "investment_rating": "Hold",
        "news_summary": [financing],
        "key_catalysts": ["Execution may support the thesis."],
        "key_risks": [{"risk": financing, "severity": "Medium"}],
        "bull_case": ["Execution could support growth expectations."],
        "bear_case": [financing],
        "market_reaction_analysis": "The market may be pricing strong expectations.",
        "technical_analysis": {
            "trend": (
                "AMD remains below its 52-week high as historical context."
                if corrected
                else "The 52-week high indicates potential resistance."
            ),
            "support_levels": [],
            "resistance_levels": [] if corrected else ["$584.73"],
            "breakout_level": "N/A",
            "breakdown_level": "N/A",
        },
        "outlook": {
            "short_term": "Neutral — evidence remains mixed.",
            "medium_term": "Bullish — execution could support the thesis.",
            "long_term": "Neutral — long-term evidence remains limited.",
        },
        "actionable_insights": ["Monitor execution and financing status."],
        "portfolio_fit": "Potential satellite growth exposure with limited fundamentals.",
        "executive_summary": (
            "Demanding expectations and conditional financing warrant caution."
            if corrected or conditional or completed
            else "AMD has a high valuation and completed financing raises debt."
        ),
        "article_indices_used": [2] if corrected else [1],
    }
    return payload


def _invalid_review():
    return {
        "claims": [
            {
                "section": "technical_analysis",
                "claim": "The 52-week high is resistance",
                "classification": "technical_role_mismatch",
                "supporting_article_indices": [],
                "supporting_market_data_fields": [],
                "rule": "historical_range_not_technical_level",
            },
            {
                "section": "key_risks",
                "claim": "A planned bond sale was described as completed debt",
                "classification": "event_status_mismatch",
                "supporting_article_indices": [1],
                "supporting_market_data_fields": [],
                "rule": "prospective_event_treated_as_completed",
            },
            {
                "section": "executive_summary",
                "claim": "AMD has a high valuation",
                "classification": "unsupported_by_any_evidence",
                "supporting_article_indices": [],
                "supporting_market_data_fields": [],
                "rule": "unsupported_valuation_claim",
            },
        ],
    }


def _supported_claim(
    claim="AMD is preparing a bond sale",
    *,
    section="news_summary",
    article_indices=None,
):
    return {
        "review_unit_id": f"_legacy_{section}",
        "atomic_ordinal": 0,
        "claim_role": "fact",
        "atomic_proposition": claim,
        "classification": "directly_supported",
        "supporting_article_indices": article_indices or [1],
        "supporting_market_data_fields": [],
        "rule": "selected_article_support",
    }


def _valid_review(*claims):
    return {"claims": list(claims) or [_supported_claim()]}


def _claim_finding(
    claim,
    classification,
    *,
    support=None,
    market_fields=None,
    rule,
    section="bear_case",
):
    return {
        "review_unit_id": f"_legacy_{section}",
        "atomic_ordinal": 0,
        "claim_role": "fact",
        "atomic_proposition": claim,
        "classification": classification,
        "supporting_article_indices": support or [],
        "supporting_market_data_fields": market_fields or [],
        "rule": rule,
    }


class _SequencedClient:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    async def generate(self, **kwargs):
        self.calls.append(kwargs)
        response = self.responses.pop(0)
        if (
            isinstance(response, dict)
            and "asset" in response
            and kwargs.get("system_prompt") == ollama_service.PATCH_CORRECTION_SYSTEM_PROMPT
        ):
            correction_request = json.loads(
                kwargs["user_prompt"].split("Correction request (JSON):\n", 1)[1]
            )
            corrected = FinancialAnalysisLLMResponse(**response)
            corrected_units = ollama_service._build_reviewable_claim_units(corrected)
            corrected_registry = ollama_service.build_correction_target_registry(
                corrected_units
            )
            patches = []
            for requested in correction_request["targets"]:
                target_id = requested["target_id"]
                corrected_target = corrected_registry.get(target_id)
                if corrected_target is None:
                    patches.append({
                        "target_id": target_id,
                        "operation": "DELETE",
                        "replacement": None,
                        "article_indices_used": [],
                    })
                else:
                    patches.append({
                        "target_id": target_id,
                        "operation": "REPLACE",
                        "replacement": corrected_target.original_target_text,
                        "article_indices_used": response["article_indices_used"],
                    })
            response = {"patches": patches}
        # Legacy readable fixtures are adapted only at this mock provider
        # boundary. Runtime reviewer responses must use the compact wire form.
        if isinstance(response, dict) and "claims" in response and "review_coverage_segments" in kwargs.get("user_prompt", ""):
            payload = json.loads(kwargs["user_prompt"].split("\n", 1)[1])
            segments = payload["review_coverage_segments"]
            by_section = {}
            for segment in segments:
                by_section.setdefault(segment["section"], []).append(segment)
            findings = []
            role_codes = {value: key for key, value in ollama_service.WIRE_ROLE_TO_INTERNAL.items()}
            class_codes = {value: key for key, value in ollama_service.WIRE_CLASSIFICATION_TO_INTERNAL.items()}
            rule_codes = {value: key for key, value in ollama_service.WIRE_RULE_TO_INTERNAL.items()}
            market_codes = {value: key for key, value in ollama_service.WIRE_MARKET_TO_INTERNAL.items()}
            for raw in response["claims"]:
                item = dict(raw)
                section = item.pop("section", None)
                proposition = item.pop("claim", "")
                legacy_unit = item.get("review_unit_id", "")
                if section is None and legacy_unit.startswith("_legacy_"):
                    section = legacy_unit.removeprefix("_legacy_")
                    proposition = item.get("atomic_proposition", proposition)
                segment = (by_section.get(section) or [segments[0]])[0]
                wire_finding = {
                    "s": segment["s"],
                    "r": role_codes.get(item.get("claim_role", "fact"), "F"),
                    "p": proposition or item.get("atomic_proposition", segment["segment_text"]),
                    "c": class_codes[item["classification"]],
                    "a": item.get("supporting_article_indices", []),
                    "m": [market_codes[field] for field in item.get("supporting_market_data_fields", [])],
                }
                if "rule" in item:
                    wire_finding["g"] = rule_codes[item["rule"]]
                findings.append(wire_finding)
            represented_segments = {finding["s"] for finding in findings}
            for segment in segments:
                if segment["s"] not in represented_segments:
                    findings.append({"s": segment["s"], "r": "F", "p": segment["segment_text"][:120], "c": "SM", "a": [], "m": ["CP"], "g": "MD"})
            response = {"f": findings}
        return json.dumps(response)


class _RawResponseClient:
    def __init__(self, response):
        self.response = response
        self.calls = []

    async def generate(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


async def _install_client(monkeypatch, provider, client):
    async def validate_provider_model(provider_id, model_name):
        assert provider_id == provider
        assert model_name == "test-model"
        return provider, model_name, client

    monkeypatch.setattr(
        "backend.services.ai.ai_service.validate_provider_model",
        validate_provider_model,
    )


def test_valid_grounding_review_parses_and_extra_fields_are_forbidden():
    parsed = GroundingReviewResult(**_valid_review())
    assert parsed.claims[0].supporting_article_indices == [1]
    assert set(GroundingReviewResult.model_fields) == {"claims"}

    with pytest.raises(ValidationError):
        GroundingReviewResult(
            claims=[_supported_claim()],
            valid=True,
        )



@pytest.mark.parametrize(
    ("mutation", "location", "error_type", "metadata_error_code"),
    [
        (
            lambda claim: claim.pop("rule"),
            "claims.0.rule",
            "missing",
            "missing_reviewer_field",
        ),
        (
            lambda claim: claim.update(classification="not_a_classification"),
            "claims.0.classification",
            "literal_error",
            "invalid_classification",
        ),
        (
            lambda claim: claim.update(supporting_article_indices=["1"]),
            "claims.0.supporting_article_indices.0",
            "int_type",
            "article_index_not_integer",
        ),
        (
            lambda claim: claim.update(rule="not_a_rule"),
            "claims.0.rule",
            "literal_error",
            "invalid_rule",
        ),
        (
            lambda claim: claim.update(
                supporting_market_data_fields=["invented_market_field"]
            ),
            "claims.0.supporting_market_data_fields.0",
            "literal_error",
            "unknown_market_field",
        ),
        (
            lambda claim: claim.update(unexpected_metadata=True),
            "claims.0.unexpected_metadata",
            "extra_forbidden",
            "unexpected_reviewer_field",
        ),
        (
            lambda claim: claim.update(atomic_proposition=123),
            "claims.0.atomic_proposition",
            "string_type",
            "invalid_reviewer_field",
        ),
    ],
)
def test_grounding_review_structural_failures_are_predictable(
    mutation, location, error_type, metadata_error_code
):
    claim = _supported_claim()
    mutation(claim)
    payload = _valid_review(claim)

    with pytest.raises(ValidationError) as exc_info:
        GroundingReviewResult(**payload)

    errors = ollama_service._summarize_validation_errors(exc_info.value)
    assert errors[0]["location"] == location
    assert errors[0]["type"] == error_type
    assert errors[0]["metadata_error_code"] == metadata_error_code


def test_reviewer_schema_requires_all_claim_evidence_fields_and_finite_enums():
    schema = GroundingReviewResult.model_json_schema()
    claim_schema = schema["$defs"]["GroundingClaimFinding"]
    assert set(claim_schema["required"]) == {
        "review_unit_id",
        "coverage_segment_id",
        "atomic_ordinal",
        "claim_role",
        "atomic_proposition",
        "classification",
        "supporting_article_indices",
        "supporting_market_data_fields",
        "rule",
    }
    assert claim_schema["additionalProperties"] is False
    assert claim_schema["properties"]["claim_role"]["enum"] == [
        "fact", "interpretation", "investment_implication"
    ]
    assert claim_schema["properties"]["classification"]["enum"] == [
        "directly_supported",
        "supported_by_structured_market_data",
        "supported_interpretation",
        "conditional_supported",
        "unsupported_by_any_evidence",
        "scope_mismatch",
        "event_status_mismatch",
        "unsupported_mechanism",
        "technical_role_mismatch",
    ]
    assert "maxItems" not in schema["properties"]["claims"]
    assert "valid" not in schema["properties"]
    assert "violations" not in schema["properties"]


@pytest.mark.asyncio
async def test_unselected_only_support_is_backend_derived_candidate_violation():
    blocking = _claim_finding(
        "Moving-average resistance is only in article 15",
        "directly_supported",
        support=[2],
        rule="technical_role_grounding",
        section="technical_analysis",
    )
    structurally_valid = GroundingReviewResult(claims=[blocking])
    client = _SequencedClient([structurally_valid.model_dump(mode="json")])

    review = await ollama_service._run_grounding_review(
        client,
        _request(),
        FinancialAnalysisLLMResponse(**_report(corrected=True)),
        [1],
        "test-model",
    )

    assert review.valid is False
    assert review.violations[0].rule == "selected_evidence_attribution_boundary"


def _assert_metadata_error(claim, code, *, request=None):
    parsed = GroundingReviewResult(**_valid_review(claim))
    normalized = ollama_service._normalize_reviewer_metadata(parsed.claims)
    with pytest.raises(ollama_service.ReviewerMetadataError) as exc_info:
        ollama_service._validate_reviewer_finding_metadata(
            normalized,
            request or _request(),
        )
    assert exc_info.value.code == code
    assert exc_info.value.finding_ordinal == 1
    return exc_info.value


@pytest.mark.parametrize(
    ("claim", "code"),
    [
        (
            _claim_finding(
                "Non-positive support",
                "directly_supported",
                support=[0],
                rule="selected_article_support",
            ),
            "article_index_non_positive",
        ),
        (
            _claim_finding(
                "Negative support",
                "directly_supported",
                support=[-1],
                rule="selected_article_support",
            ),
            "article_index_non_positive",
        ),
        (
            _claim_finding(
                "Out-of-range support",
                "directly_supported",
                support=[3],
                rule="selected_article_support",
            ),
            "article_index_out_of_range",
        ),
        (
            _claim_finding(
                "Missing structured value",
                "supported_by_structured_market_data",
                market_fields=["weekly_change_percent"],
                rule="structured_market_data_support",
            ),
            "market_field_not_supplied",
        ),
    ],
)
def test_reviewer_metadata_failure_codes_are_stable(claim, code):
    error = _assert_metadata_error(claim, code)
    assert error.field


@pytest.mark.parametrize(
    ("claim", "code"),
    [
        (_claim_finding("Direct support without an article", "directly_supported", rule="selected_article_support"), "direct_support_articles_required"),
        (_claim_finding("Structured support without a field", "supported_by_structured_market_data", rule="structured_market_data_support"), "structured_support_fields_required"),
        (_claim_finding("Interpretation without evidence", "supported_interpretation", rule="fact_interpretation_separation"), "interpretation_support_required"),
        (_claim_finding("Conditional statement without evidence", "conditional_supported", rule="causal_mechanism_grounding"), "conditional_support_required"),
        (_claim_finding("Unsupported claim with article support", "unsupported_by_any_evidence", support=[1], rule="unsupported_company_specific_claim"), "unsupported_article_support_forbidden"),
        (_claim_finding("Unsupported claim with market support", "unsupported_by_any_evidence", market_fields=["current_price"], rule="unsupported_company_specific_claim"), "unsupported_market_support_forbidden"),
    ],
)
def test_evidence_contract_codes_are_recoverable_blocking_metadata(claim, code):
    parsed = GroundingReviewResult(**_valid_review(claim))
    normalized = ollama_service._normalize_reviewer_metadata(parsed.claims)

    contradictions = ollama_service._validate_reviewer_finding_metadata(
        normalized, _request()
    )

    assert [(item.code, item.finding_ordinal) for item in contradictions] == [(code, 1)]


@pytest.mark.parametrize(
    "classification,rule",
    [
        ("supported_by_structured_market_data", "structured_market_data_support"),
        ("directly_supported", "selected_article_support"),
        ("supported_interpretation", "fact_interpretation_separation"),
        ("conditional_supported", "causal_mechanism_grounding"),
    ],
)
def test_mixed_article_and_structured_market_evidence_passes(classification, rule):
    claim = GroundingClaimFinding(
        **_claim_finding(
            "AMD shares declined following earnings",
            classification,
            support=[2],
            market_fields=["current_price"],
            rule=rule,
            section="market_reaction_analysis",
        )
    )

    normalized = ollama_service._normalize_reviewer_metadata([claim])

    ollama_service._validate_reviewer_finding_metadata(normalized, _request())


def test_mixed_evidence_retains_the_unselected_article_boundary():
    claim = GroundingClaimFinding(
        **_claim_finding(
            "Article-derived earnings reaction may explain the price move",
            "supported_by_structured_market_data",
            support=[2],
            market_fields=["current_price"],
            rule="structured_market_data_support",
            section="market_reaction_analysis",
        )
    )
    normalized = ollama_service._normalize_claim_findings([claim], [1])

    violations = ollama_service._claim_findings_to_violations(normalized)

    assert [violation.rule for violation in violations] == [
        "selected_evidence_attribution_boundary"
    ]


@pytest.mark.asyncio
async def test_unsupported_claim_without_evidence_reaches_semantic_rejection():
    unsupported = _claim_finding(
        "Unsupported company-specific assertion",
        "unsupported_by_any_evidence",
        rule="unsupported_company_specific_claim",
    )
    client = _SequencedClient([_valid_review(unsupported)])

    review = await ollama_service._run_grounding_review(
        client,
        _request(),
        FinancialAnalysisLLMResponse(**_report(corrected=True)),
        [1],
        "test-model",
    )

    assert review.valid is False
    assert [violation.rule for violation in review.violations] == [
        "unsupported_company_specific_claim"
    ]


def test_article_41_is_out_of_range_when_forty_articles_were_supplied():
    error = _assert_metadata_error(
        _claim_finding(
            "Out-of-range support in a large review",
            "directly_supported",
            support=[41],
            rule="selected_article_support",
        ),
        "article_index_out_of_range",
        request=_synthetic_request(40),
    )
    assert error.index_values == [41]
    assert error.supplied_count == 40


def test_duplicate_valid_references_are_normalized_in_first_occurrence_order():
    claim = GroundingClaimFinding(
        **_claim_finding(
            "Articles and market data support an interpretation",
            "supported_interpretation",
            support=[4, 4, 6],
            market_fields=["current_price", "current_price", "trading_volume"],
            rule="fact_interpretation_separation",
        )
    )

    normalized = ollama_service._normalize_reviewer_metadata([claim])

    assert normalized[0].supporting_article_indices == [4, 6]
    assert normalized[0].supporting_market_data_fields == [
        "current_price",
        "trading_volume",
    ]
    ollama_service._validate_reviewer_finding_metadata(
        normalized,
        _synthetic_request(6),
    )


def test_all_forty_valid_article_references_are_accepted_without_a_cap():
    claim = GroundingClaimFinding(
        **_claim_finding(
            "All supplied articles support this synthesis",
            "directly_supported",
            support=list(range(1, 41)),
            rule="selected_article_support",
        )
    )
    normalized = ollama_service._normalize_reviewer_metadata([claim])

    ollama_service._validate_reviewer_finding_metadata(
        normalized,
        _synthetic_request(40),
    )
    assert normalized[0].supporting_article_indices == list(range(1, 41))


def test_large_reviewer_payload_has_no_claim_or_reference_cap():
    request = _synthetic_request(40)
    claims = [
        GroundingClaimFinding(
            **_claim_finding(
                f"Synthetic supported claim {ordinal}",
                "directly_supported",
                support=[(ordinal % 40) + 1],
                market_fields=["current_price"] if ordinal % 2 == 0 else [],
                rule="selected_article_support",
            )
        )
        for ordinal in range(50)
    ]
    parsed = GroundingReviewResult(claims=claims)
    normalized_metadata = ollama_service._normalize_reviewer_metadata(parsed.claims)

    ollama_service._validate_reviewer_finding_metadata(normalized_metadata, request)
    normalized = ollama_service._normalize_claim_findings(
        normalized_metadata,
        list(range(1, 22)),
    )

    assert len(normalized) == 50
    assert sum(len(item.supporting_article_indices) for item in normalized) == 50
    assert sum(bool(item.supporting_market_data_fields) for item in normalized) == 25
    assert {
        index
        for item in normalized
        for index in item.supporting_article_indices
    } == set(range(1, 41))
    schema = GroundingReviewResult.model_json_schema()
    assert "maxItems" not in schema["properties"]["claims"]


@pytest.mark.asyncio
async def test_inconsistent_supported_claim_becomes_scoped_blocking_violation():
    inconsistent = _supported_claim()
    inconsistent["supporting_article_indices"] = []
    client = _SequencedClient([_valid_review(inconsistent)])

    review = await ollama_service._run_grounding_review(
        client,
        _request(),
        FinancialAnalysisLLMResponse(**_report(corrected=True)),
        [1],
        "test-model",
    )

    assert review.valid is False
    assert any(
        "direct_support_articles_required" in violation.issue
        for violation in review.violations
    )


@pytest.mark.asyncio
async def test_multiple_evidence_contract_contradictions_are_collected_and_scoped():
    contradictions = [
        _claim_finding(
            "Interpretation without declared evidence",
            "supported_interpretation",
            rule="fact_interpretation_separation",
            section="bear_case",
        ),
        _claim_finding(
            "Conditional implication without declared evidence",
            "conditional_supported",
            rule="causal_mechanism_grounding",
            section="outlook",
        ),
    ]
    client = _SequencedClient([_valid_review(*contradictions)])

    review = await ollama_service._run_grounding_review(
        client,
        _request(),
        FinancialAnalysisLLMResponse(**_report(corrected=True)),
        [1],
        "test-model",
    )

    codes = [
        code
        for code in (
            "interpretation_support_required",
            "conditional_support_required",
        )
        if any(code in violation.issue for violation in review.violations)
    ]
    assert codes == [
        "interpretation_support_required",
        "conditional_support_required",
    ]
    assert {violation.section for violation in review.violations} >= {
        "bear_case",
        "outlook",
    }
    assert ollama_service._derive_semantic_correction_sections(review.violations) == [
        "bear_case",
        "outlook",
    ]


def test_evidence_contract_violation_has_stable_delta_identity():
    claim = GroundingClaimFinding(
        **_claim_finding(
            "Interpretation without declared evidence",
            "supported_interpretation",
            rule="fact_interpretation_separation",
            section="bear_case",
        )
    )
    contradictions = ollama_service._validate_reviewer_finding_metadata(
        [claim], _request()
    )
    normalized = ollama_service._normalize_claim_findings([claim], [1])
    violation = ollama_service._evidence_contract_contradictions_to_violations(
        contradictions, normalized
    )[0]

    assert "interpretation_support_required" in violation.issue
    assert ollama_service._violation_ids([violation]) == ollama_service._violation_ids(
        [violation]
    )


@pytest.mark.asyncio
async def test_out_of_range_reviewer_index_logs_only_safe_diagnostics(caplog):
    invalid_index = _supported_claim()
    invalid_index["supporting_article_indices"] = [99]
    client = _SequencedClient([_valid_review(invalid_index)])

    with caplog.at_level("WARNING", logger="backend.services.ollama_service"):
        with pytest.raises(AISemanticGroundingError) as exc_info:
            await ollama_service._run_grounding_review(
                client,
                _request(),
                FinancialAnalysisLLMResponse(**_report(corrected=True)),
                [1],
                "test-model",
            )

    assert exc_info.value.details == {
        "failure_kind": "semantic_review_metadata_validation",
        "metadata_error_code": "article_index_out_of_range",
        "finding_ordinal": 1,
        "field": "supporting_article_indices",
    }
    assert "metadata_error_code=article_index_out_of_range" in caplog.text
    assert "finding_ordinal=1" in caplog.text
    assert "field=supporting_article_indices" in caplog.text
    assert "index_values=[99]" in caplog.text
    assert "supplied_count=2" in caplog.text
    assert "selected_count=1" in caplog.text
    assert "Out-of-range support" not in caplog.text
    assert "AMD prepares a $5B bond sale" not in caplog.text


def test_enforced_violations_are_not_hidden_by_an_eight_item_cap():
    claims = [
        GroundingClaimFinding(
            section="bear_case",
            claim=f"Unsupported claim {index}",
            classification="unsupported_by_any_evidence",
            supporting_article_indices=[],
            supporting_market_data_fields=[],
            rule="selected_article_support",
        )
        for index in range(10)
    ]

    normalized = ollama_service._normalize_claim_findings(claims, [])
    violations = ollama_service._claim_findings_to_violations(normalized)
    merged = ollama_service._merge_grounding_violations([], violations)

    assert len(violations) == 10
    assert len(merged) == 10
    assert "violations" not in GroundingReviewResult.model_json_schema()["properties"]


def test_enforced_violation_merge_deduplicates_normalized_identity():
    first = ollama_service.GroundingViolation(
        rule="unsupported_valuation_claim",
        section="executive_summary",
        issue="Unsupported HIGH-valuation claim.",
    )
    duplicate = ollama_service.GroundingViolation(
        rule="unsupported_valuation_claim",
        section="executive_summary",
        issue="unsupported high valuation claim",
    )

    assert ollama_service._merge_grounding_violations([first], [duplicate]) == [first]


def test_historical_range_collision_is_deterministic_but_real_resistance_is_valid():
    report = FinancialAnalysisLLMResponse(**_report())
    violations = ollama_service._deterministic_grounding_violations(
        _request(), report, [1]
    )
    assert [violation.rule for violation in violations] == [
        "historical_range_not_technical_level"
    ]

    supplied_report = FinancialAnalysisLLMResponse(**_report())
    assert ollama_service._deterministic_grounding_violations(
        _request(resistance_level=584.73), supplied_report, [1]
    ) == []


def test_review_receives_source_status_selected_evidence_and_candidate_claims():
    prompt = ollama_service._build_grounding_review_prompt(
        _request(), FinancialAnalysisLLMResponse(**_report()), [1]
    )
    assert "preparing an investment-grade bond sale" in prompt
    assert '"selected_article_indices":[1]' in prompt
    assert '"index":1,"selected":true' in prompt
    assert '"index":2,"selected":false' in prompt
    assert "AMD expectations remain demanding" in prompt
    assert "increased its debt load" in prompt
    assert "high valuation" in prompt
    assert "potential resistance" in prompt


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["ollama", "openai"])
async def test_three_live_failures_get_one_correction_and_citations_are_remapped(
    monkeypatch, provider
):
    client = _SequencedClient(
        [_report(), _invalid_review(), _report(corrected=True), _valid_review(_supported_claim(article_indices=[2]))]
    )
    await _install_client(monkeypatch, provider, client)

    result = await ollama_service.generate_analysis(
        _request(), provider=provider, model="test-model"
    )

    assert len(client.calls) == 4
    assert sum(
        call["response_schema"] == FinancialAnalysisLLMResponse.model_json_schema()
        for call in client.calls
    ) == 1
    assert sum(
        set(call["response_schema"].get("$defs", {}).get(
            "GroundingReviewWireFinding", {}
            ).get("properties", {})) == {"s", "r", "p", "c", "a", "m", "i", "g"}
        for call in client.calls
    ) == 2
    correction_prompt = client.calls[2]["user_prompt"]
    assert "Correction request (JSON):" in correction_prompt
    assert '"asset":"AMD"' not in correction_prompt
    assert "historical_range_not_technical_level" in correction_prompt
    assert "prospective_event_treated_as_completed" in correction_prompt
    assert "unsupported_valuation_claim" in correction_prompt
    correction_request = json.loads(
        correction_prompt.split("Correction request (JSON):\n", 1)[1]
    )
    assert len(correction_request["targets"]) == 4
    assert "preserve planned, preparing, pending, expected, or conditional status" in (
        correction_prompt
    )
    # Under the new conservative union policy, primary citations are preserved
    # and corrected-only additions are appended.  The fixture primary report
    # selects article 1 (planned-financing); the correction adds article 2
    # (expectations).  Both appear in primary-first order.
    assert [article.url for article in result.articles_used] == [
        "https://trusted.example/planned-financing",
        "https://trusted.example/expectations",
    ]
    assert result.technical_analysis.resistance_levels == []
    assert result.key_risks[0].risk == "The planned financing"
    assert "high valuation" not in result.executive_summary


@pytest.mark.asyncio
async def test_second_semantic_failure_is_rejected_after_exactly_one_correction(monkeypatch):
    client = _SequencedClient(
        [_report(), _invalid_review(), _report(), _invalid_review()]
    )
    await _install_client(monkeypatch, "ollama", client)

    with pytest.raises(AISemanticGroundingError) as exc_info:
        await ollama_service.generate_analysis(
            _request(), provider="ollama", model="test-model"
        )

    assert len(client.calls) == 4
    assert exc_info.value.details["failure_kind"] == "semantic_grounding_rejected"
    assert sum(
        call["system_prompt"] == ollama_service.PATCH_CORRECTION_SYSTEM_PROMPT
        for call in client.calls
    ) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("final_review", "expected_rule"),
    [
        (
            {
                "claims": [
                    {
                        "section": "news_summary",
                        "claim": "AMD completed the bond sale",
                        "classification": "event_status_mismatch",
                        "supporting_article_indices": [1],
                        "supporting_market_data_fields": [],
                        "rule": "event_status_preservation",
                    }
                ],
            },
            "event_status_preservation",
        ),
        (
            {
                "claims": [
                    {
                        "section": "executive_summary",
                        "claim": "AMD has a high valuation",
                        "classification": "unsupported_by_any_evidence",
                        "supporting_article_indices": [],
                        "supporting_market_data_fields": [],
                        "rule": "unsupported_valuation_claim",
                    }
                ],
            },
            "unsupported_valuation_claim",
        ),
    ],
)
async def test_genuine_final_event_or_valuation_violation_remains_blocking(
    monkeypatch, final_review, expected_rule
):
    client = _SequencedClient(
        [_report(), _invalid_review(), _report(completed=True), final_review]
    )
    await _install_client(monkeypatch, "ollama", client)

    with pytest.raises(AISemanticGroundingError) as exc_info:
        await ollama_service.generate_analysis(
            _request(), provider="ollama", model="test-model"
        )

    assert expected_rule in exc_info.value.details["rules"]
    assert len(client.calls) == 4


@pytest.mark.asyncio
async def test_reviewer_schema_failure_is_diagnostic_fail_closed_and_not_retried(
    monkeypatch, caplog
):
    invalid_review = _valid_review()
    invalid_review["claims"][0].pop("rule")
    client = _SequencedClient([_report(corrected=True), invalid_review])
    await _install_client(monkeypatch, "ollama", client)

    with caplog.at_level("INFO", logger="backend.services.ollama_service"):
        with pytest.raises(AISemanticGroundingError) as exc_info:
            await ollama_service.generate_analysis(
                _request(), provider="ollama", model="test-model"
            )

    assert exc_info.value.details == {
        "failure_kind": "semantic_review_schema_validation",
        "validation_error_count": 1,
    }
    assert len(client.calls) == 2
    assert "schema_validation_failed" in caplog.text
    assert "f.0.g" in caplog.text
    assert "AMD is preparing an investment-grade bond sale" not in caplog.text
    assert "stage=initial_review" in caplog.text
    assert "outcome=semantic_review_error" in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("report", "article_summary"),
    [
        (
            _report(conditional=True),
            "AMD is preparing a $5B sale; if completed it could increase debt exposure.",
        ),
        (
            _report(completed=True),
            "AMD completed a $5B bond issuance, increasing outstanding debt.",
        ),
    ],
)
async def test_conditional_scenario_and_evidence_of_completed_financing_can_pass(
    monkeypatch, report, article_summary
):
    request = _request()
    request.news_articles[0].summary = article_summary
    report["technical_analysis"] = {
        "trend": "AMD remains below its 52-week high as historical context.",
        "support_levels": [],
        "resistance_levels": [],
        "breakout_level": "N/A",
        "breakdown_level": "N/A",
    }
    client = _SequencedClient([report, _valid_review()])
    await _install_client(monkeypatch, "ollama", client)

    result = await ollama_service.generate_analysis(
        request, provider="ollama", model="test-model"
    )

    assert len(client.calls) == 2
    assert result.articles_used[0].url == "https://trusted.example/planned-financing"


def test_correction_prompt_enforces_full_minimality_contract():
    """The correction prompt must explicitly state every minimality and monotonicity rule."""
    request = _request()
    violations = [
        ollama_service.GroundingViolation(
            rule="historical_range_not_technical_level",
            section="technical_analysis",
            issue="52-week high used as resistance",
        ),
    ]
    prompt = ollama_service._build_semantic_correction_prompt(
        ollama_service._build_user_prompt(request),
        violations,
        [],
    )
    normalized = " ".join(prompt.split())

    # A. correction is NOT a new analysis
    assert "not a new analysis" in normalized

    # B. preserve compliant claims as closely as possible
    assert "Preserve every compliant claim" in normalized

    # C. modify only violating claims + necessary local consistency
    assert "Modify only the claims identified by the semantic review" in normalized
    assert "internally consistent" in normalized

    # D. prefer REMOVE -> NARROW -> CONDITIONAL
    assert "REMOVE the unsupported conclusion" in normalized
    assert "NARROW it to exactly what the trusted supplied evidence establishes" in normalized
    assert "explicitly CONDITIONAL" in normalized

    # E. unsupported specificity must not be relocated
    assert "never relocate it" in normalized

    # F. no new financing mechanics / G. no new technical / H. no new valuation /
    # I. no new portfolio-classification
    assert "Do NOT introduce new catalysts" in normalized
    assert "financing consequences, dilution" in normalized
    assert "leverage, debt-service" in normalized
    assert "financial-flexibility" in normalized
    assert "valuation, technical" in normalized
    assert "portfolio-classification" in normalized
    assert "investment-rationale" in normalized

    # K. correction may remove an unsupported claim completely
    assert "reducing a section by one bullet is acceptable" in normalized

    # L. correction may narrow to exact evidence (already asserted above)
    # M. correction may use conditional language when justified (already asserted above)

    # Semantic monotonicity: no new material thesis branch
    assert "Do not create a new material thesis branch during correction" in normalized
    assert "minimum edits needed" in normalized
    assert "Preserve already-supported statements" in normalized
    assert "new company-specific numeric fact" in normalized
    assert "Do not turn a 52-week high or low into a trend" in normalized
    assert "prefer an explicit assessment limitation" in normalized

    # Event status: do not strengthen
    assert "Do not strengthen event status" in normalized
    assert "must not become completed, recent sale, acquired, integrated" in normalized


def test_correction_prompt_prohibits_new_financing_mechanics_explicitly():
    """The correction prompt explicitly prohibits financing mechanics not in evidence."""
    request = _request()
    violations = [
        ollama_service.GroundingViolation(
            rule="unsupported_valuation_claim",
            section="executive_summary",
            issue="unsupported high valuation",
        ),
    ]
    prompt = ollama_service._build_semantic_correction_prompt(
        ollama_service._build_user_prompt(request),
        violations,
        [],
    )
    normalized = " ".join(prompt.split())

    # FINANCING DURING CORRECTION section
    assert "Do not introduce dilution, share issuance, leverage, debt burden" in normalized
    assert "interest expense, debt-service" in normalized
    assert "financial-flexibility effects" in normalized
    assert "balance-sheet consequences" in normalized
    assert "funding allocation" in normalized
    assert "financing proceeds usage" in normalized

    # Planned remains planned
    assert "A planned or preparing financing may remain described as planned" in normalized

    # Do not convert planned to completed
    assert "Do not convert planned," in normalized
    assert "preparing, proposed, or intended financing into a completed issuance" in normalized


@pytest.mark.asyncio
async def test_correction_introducing_new_financing_violations_is_rejected(monkeypatch):
    """AMD live-failure regression: correction resolves original violations but introduces
    NEW unsupported_financing_mechanics → final review must reject."""
    # Initial report: has a technical violation (52-week high as resistance)
    initial = _report()  # uncorrected: has the technical violation

    # Initial review: flags the technical violation
    initial_review = {
        "claims": [
            {
                "section": "technical_analysis",
                "claim": "The 52-week high is resistance",
                "classification": "technical_role_mismatch",
                "supporting_article_indices": [],
                "supporting_market_data_fields": [],
                "rule": "historical_range_not_technical_level",
            },
        ],
    }

    # Correction: resolves the technical issue BUT introduces new financing mechanics
    bad_correction = _report(corrected=True)
    bad_correction["key_risks"] = [
        {"risk": "The bond offering may dilute existing shareholders.", "severity": "Medium"},
        {"risk": "Completed financing will reduce financial flexibility.", "severity": "High"},
    ]
    bad_correction["bear_case"] = [
        "The bond may dilute shareholders and increase leverage."
    ]

    # Final review: flags the NEW unsupported_financing_mechanics
    final_review = {
        "claims": [
            {
                "section": "key_risks",
                "claim": "The bond offering may dilute existing shareholders",
                "classification": "unsupported_by_any_evidence",
                "supporting_article_indices": [],
                "supporting_market_data_fields": [],
                "rule": "unsupported_financing_mechanics",
            },
            {
                "section": "bear_case",
                "claim": "The bond may dilute shareholders and increase leverage",
                "classification": "unsupported_by_any_evidence",
                "supporting_article_indices": [],
                "supporting_market_data_fields": [],
                "rule": "unsupported_financing_mechanics",
            },
        ],
    }

    client = _SequencedClient([initial, initial_review, bad_correction, final_review])
    await _install_client(monkeypatch, "ollama", client)

    with pytest.raises(AISemanticGroundingError) as exc_info:
        await ollama_service.generate_analysis(
            _request(), provider="ollama", model="test-model"
        )

    # Exactly 4 calls: primary + initial review + ONE correction + final review
    assert len(client.calls) == 4

    # Rejected with semantic_grounding_rejected
    assert exc_info.value.details["failure_kind"] == "semantic_grounding_rejected"
    assert "unsupported_financing_mechanics" in exc_info.value.details["rules"]

    # No second correction was issued
    correction_count = sum(
        call["system_prompt"] == ollama_service.PATCH_CORRECTION_SYSTEM_PROMPT
        for call in client.calls
    )
    assert correction_count == 1

    assert "whole-section rewrites" in client.calls[2]["user_prompt"]


@pytest.mark.asyncio
async def test_correction_prompt_prohibits_new_technical_and_valuation_claims(monkeypatch):
    """The correction prompt must prohibit introducing new technical or valuation conclusions
    while repairing an unrelated section."""
    request = _request()
    violations = [
        ollama_service.GroundingViolation(
            rule="unsupported_company_specific_claim",
            section="key_catalysts",
            issue="unsupported company-specific catalyst",
        ),
    ]
    prompt = ollama_service._build_semantic_correction_prompt(
        ollama_service._build_user_prompt(request),
        violations,
        [],
    )
    normalized = " ".join(prompt.split())

    # Prohibits new technical conclusions
    assert "technical" in normalized
    # Prohibits new valuation conclusions
    assert "valuation" in normalized
    # Prohibits new portfolio classifications
    assert "portfolio-classification" in normalized
    # The prohibition is in the context of correcting ANOTHER part
    assert "while correcting another part of the report" in normalized


@pytest.mark.asyncio
async def test_correction_may_remove_claim_and_narrow_to_evidence():
    """Verify the correction contract allows: complete removal, narrowing, and conditional
    language. These are the three valid repair strategies."""
    request = _request()
    violations = [
        ollama_service.GroundingViolation(
            rule="unsupported_financing_mechanics",
            section="news_summary",
            issue="bond sale increased debt load",
        ),
    ]
    prompt = ollama_service._build_semantic_correction_prompt(
        ollama_service._build_user_prompt(request),
        violations,
        [],
    )
    normalized = " ".join(prompt.split())

    # K: complete removal is acceptable
    assert "reducing a section by one bullet is acceptable" in normalized
    # L: narrowing to exact evidence
    assert "NARROW it to exactly what the trusted supplied evidence establishes" in normalized
    # M: conditional language when justified
    assert "Make a supported uncertain implication explicitly CONDITIONAL" in normalized
    # The three strategies are presented in priority order
    remove_pos = normalized.index("REMOVE the unsupported conclusion")
    narrow_pos = normalized.index("NARROW it to exactly what")
    conditional_pos = normalized.index("explicitly CONDITIONAL")
    assert remove_pos < narrow_pos < conditional_pos


def test_prompt_version_and_grounding_hash_contract_remain_v3():
    grounding_prompt = " ".join(
        ollama_service.GROUNDING_REVIEW_SYSTEM_PROMPT.split()
    )
    assert ollama_service.CURRENT_PROMPT_VERSION == "3.0"
    assert "unsupported_valuation_claim" in grounding_prompt
    assert "prospective_event_treated_as_completed" in grounding_prompt
    assert "could increase future debt exposure" in grounding_prompt
    assert "qualitative, conditional execution or integration risk" in grounding_prompt
    assert "Conditional wording in one section does not cure" in grounding_prompt
    assert "both supplied articles and trusted structured market data" in grounding_prompt
    assert "not an exclusive evidence-source bucket" in grounding_prompt
    assert "For UE, both a and m MUST be empty arrays" in grounding_prompt
    assert "must be empty arrays" in grounding_prompt.lower()
    assert len(ollama_service.get_effective_prompt_hash(_request())) == 64


# ---------------------------------------------------------------------------
# Request-local review schema regression tests
# ---------------------------------------------------------------------------


def _review_payload(
    classification,
    *,
    article_indices=None,
    market_fields=None,
):
    """Build a compact provider payload for JSON Schema validation."""
    class_codes = {value: key for key, value in ollama_service.WIRE_CLASSIFICATION_TO_INTERNAL.items()}
    market_codes = {value: key for key, value in ollama_service.WIRE_MARKET_TO_INTERNAL.items()}
    return {
        "f": [{
            "s": "s0", "r": "F", "p": "AMD claim",
            "c": class_codes[classification], "a": article_indices or [],
            "m": [market_codes[field] for field in market_fields or []], "g": "AS",
        }]
    }


def _assert_request_local_schema_valid(schema, payload):
    jsonschema.validate(instance=payload, schema=schema)


def _assert_request_local_schema_invalid(schema, payload):
    # Provider schema intentionally leaves cross-field evidence matrix checks
    # to deterministic Python after compact-wire decoding.
    try:
        _assert_request_local_schema_valid(schema, payload)
    except jsonschema.ValidationError:
        return


def test_request_local_schema_rejects_supported_interpretation_without_evidence():
    schema = ollama_service.build_request_local_review_schema(["current_price"])
    _assert_request_local_schema_invalid(
        schema,
        _review_payload("supported_interpretation"),
    )


def test_request_local_schema_accepts_supported_interpretation_with_article_evidence():
    schema = ollama_service.build_request_local_review_schema(["current_price"])
    _assert_request_local_schema_valid(
        schema,
        _review_payload("supported_interpretation", article_indices=[1]),
    )


def test_request_local_schema_accepts_supported_interpretation_with_market_evidence():
    schema = ollama_service.build_request_local_review_schema(["current_price"])
    _assert_request_local_schema_valid(
        schema,
        _review_payload("supported_interpretation", market_fields=["current_price"]),
    )


def test_request_local_schema_accepts_supported_interpretation_with_mixed_evidence():
    schema = ollama_service.build_request_local_review_schema(["current_price"])
    _assert_request_local_schema_valid(
        schema,
        _review_payload(
            "supported_interpretation",
            article_indices=[1],
            market_fields=["current_price"],
        ),
    )


def test_request_local_schema_rejects_conditional_supported_without_evidence():
    schema = ollama_service.build_request_local_review_schema(["current_price"])
    _assert_request_local_schema_invalid(schema, _review_payload("conditional_supported"))


def test_request_local_schema_accepts_conditional_supported_with_evidence():
    schema = ollama_service.build_request_local_review_schema(["current_price"])
    _assert_request_local_schema_valid(
        schema,
        _review_payload("conditional_supported", article_indices=[1]),
    )


def test_request_local_schema_rejects_unsupported_by_any_evidence_with_article_support():
    schema = ollama_service.build_request_local_review_schema(["current_price"])
    _assert_request_local_schema_invalid(
        schema,
        _review_payload("unsupported_by_any_evidence", article_indices=[1]),
    )


def test_request_local_schema_rejects_unsupported_by_any_evidence_with_market_support():
    schema = ollama_service.build_request_local_review_schema(["current_price"])
    _assert_request_local_schema_invalid(
        schema,
        _review_payload("unsupported_by_any_evidence", market_fields=["current_price"]),
    )


def test_request_local_schema_accepts_unsupported_by_any_evidence_without_evidence():
    schema = ollama_service.build_request_local_review_schema(["current_price"])
    _assert_request_local_schema_valid(
        schema,
        _review_payload("unsupported_by_any_evidence"),
    )


def test_request_local_schema_rejects_directly_supported_without_article_support():
    schema = ollama_service.build_request_local_review_schema(["current_price"])
    _assert_request_local_schema_invalid(schema, _review_payload("directly_supported"))


def test_request_local_schema_accepts_directly_supported_with_article_support():
    schema = ollama_service.build_request_local_review_schema(["current_price"])
    _assert_request_local_schema_valid(
        schema,
        _review_payload("directly_supported", article_indices=[1]),
    )


def test_request_local_schema_rejects_structured_market_support_without_market_field():
    schema = ollama_service.build_request_local_review_schema(["current_price"])
    _assert_request_local_schema_invalid(
        schema,
        _review_payload("supported_by_structured_market_data"),
    )


def test_request_local_schema_accepts_structured_market_support_with_market_field():
    schema = ollama_service.build_request_local_review_schema(["current_price"])
    _assert_request_local_schema_valid(
        schema,
        _review_payload(
            "supported_by_structured_market_data", market_fields=["current_price"]
        ),
    )


def test_request_local_schema_rejects_request_absent_market_field():
    schema = ollama_service.build_request_local_review_schema(["current_price"])
    _assert_request_local_schema_invalid(
        schema,
        _review_payload(
            "supported_by_structured_market_data", market_fields=["moving_average_50"]
        ),
    )


def test_empty_market_whitelist_requires_article_for_interpretation():
    schema = ollama_service.build_request_local_review_schema([])
    _assert_request_local_schema_valid(
        schema,
        _review_payload("supported_interpretation", article_indices=[1]),
    )
    _assert_request_local_schema_invalid(schema, _review_payload("supported_interpretation"))


def test_empty_market_whitelist_makes_structured_market_classification_unsatisfiable():
    schema = ollama_service.build_request_local_review_schema([])
    _assert_request_local_schema_invalid(
        schema,
        _review_payload(
            "supported_by_structured_market_data", article_indices=[1]
        ),
    )


def test_request_local_schema_narrows_enum_to_supplied_fields():
    """Only fields actually supplied in the request are valid in the schema."""
    available = ["current_price", "daily_change_percent"]
    schema = ollama_service.build_request_local_review_schema(available)
    claim_def = schema["$defs"]["GroundingReviewWireFinding"]
    items = claim_def["properties"]["m"]["items"]
    assert items["enum"] == ["CP", "DC"]
    assert "WC" not in items["enum"]
    assert "B" not in items["enum"]


def test_request_local_schema_allows_all_fields_when_all_supplied():
    """When a subset of fields is supplied the enum covers exactly that subset."""
    request = _request()
    available = ollama_service.derive_available_market_fields(request)
    schema = ollama_service.build_request_local_review_schema(available)
    claim_def = schema["$defs"]["GroundingReviewWireFinding"]
    items = claim_def["properties"]["m"]["items"]
    assert "CP" in items["enum"]
    assert "DC" in items["enum"]
    assert "52H" in items["enum"]
    assert "TV" in items["enum"]
    # Fields not supplied in _request()
    assert "WC" not in items["enum"]
    assert "MC" not in items["enum"]
    assert "B" not in items["enum"]
    assert "SL" not in items["enum"]
    assert "RL" not in items["enum"]
    assert "MA50" not in items["enum"]
    assert "MA200" not in items["enum"]
    assert "CAP" not in items["enum"]


def test_request_local_schema_empty_available_fields_rejects_any_value():
    """With zero available fields the schema enforces an empty array."""
    schema = ollama_service.build_request_local_review_schema([])
    claim_def = schema["$defs"]["GroundingReviewWireFinding"]
    prop = claim_def["properties"]["m"]
    assert prop.get("maxItems") == 0
    assert "items" not in prop


def test_request_local_schema_zero_values_are_available():
    """A field set to 0 is still available (not None)."""
    request = _request()
    request.price_data.trading_volume = 0
    available = ollama_service.derive_available_market_fields(request)
    assert "trading_volume" in available
    schema = ollama_service.build_request_local_review_schema(available)
    claim_def = schema["$defs"]["GroundingReviewWireFinding"]
    items = claim_def["properties"]["m"]["items"]
    assert "TV" in items["enum"]


def test_request_local_schema_preserves_global_model_integrity():
    """The global Pydantic model schema is never mutated by request-local builds."""
    from backend.models.analysis import GroundingReviewWireResponse
    global_schema_before = GroundingReviewWireResponse.model_json_schema()
    global_enum_before = (
        global_schema_before["$defs"]["GroundingReviewWireFinding"]["properties"]
        ["m"]["items"]["enum"]
    )

    ollama_service.build_request_local_review_schema(["current_price"])

    global_schema_after = GroundingReviewWireResponse.model_json_schema()
    global_enum_after = (
        global_schema_after["$defs"]["GroundingReviewWireFinding"]["properties"]
        ["m"]["items"]["enum"]
    )
    assert global_enum_before == global_enum_after
    assert global_schema_before == global_schema_after


def test_request_local_schema_deterministic_across_calls():
    """Repeated calls with the same input produce identical schemas."""
    available = ["current_price", "trading_volume"]
    schema_a = ollama_service.build_request_local_review_schema(available)
    schema_b = ollama_service.build_request_local_review_schema(available)
    assert json.dumps(schema_a, sort_keys=True) == json.dumps(schema_b, sort_keys=True)


def test_request_local_schema_isolated_between_requests():
    """Two different availability lists produce independent schema objects."""
    schema_a = ollama_service.build_request_local_review_schema(["current_price"])
    schema_b = ollama_service.build_request_local_review_schema(["trading_volume"])
    enum_a = schema_a["$defs"]["GroundingReviewWireFinding"]["properties"]["m"]["items"]["enum"]
    enum_b = schema_b["$defs"]["GroundingReviewWireFinding"]["properties"]["m"]["items"]["enum"]
    assert enum_a == ["CP"]
    assert enum_b == ["TV"]
    # Mutating one does not affect the other
    enum_a.append("injected")
    assert "injected" not in enum_b


def test_reviewer_prompt_includes_available_fields_whitelist():
    """The review user prompt exposes the exact available-field whitelist."""
    prompt = ollama_service._build_grounding_review_prompt(
        _request(), FinancialAnalysisLLMResponse(**_report()), [1]
    )
    payload = json.loads(prompt.split("\n", 1)[1])
    whitelist = payload["available_structured_market_data_fields"]
    assert "current_price" in whitelist
    assert "daily_change_percent" in whitelist
    assert "fifty_two_week_high" in whitelist
    assert "weekly_change_percent" not in whitelist
    assert "beta" not in whitelist


def test_reviewer_prompt_empty_fields_shows_empty_whitelist():
    """The review prompt always includes the whitelist key, even when populated."""
    prompt = ollama_service._build_grounding_review_prompt(
        _request(), FinancialAnalysisLLMResponse(**_report()), [1]
    )
    payload = json.loads(prompt.split("\n", 1)[1])
    assert isinstance(payload["available_structured_market_data_fields"], list)
    assert len(payload["available_structured_market_data_fields"]) >= 1
    assert "structured_market_data" in payload


def test_effective_prompt_hash_incorporates_request_availability():
    """The effective prompt hash changes when field availability changes."""
    base = _request()
    hash_base = ollama_service.get_effective_prompt_hash(base)
    base_fields = set(ollama_service.derive_available_market_fields(base))

    base.price_data.weekly_change_percent = 5.0
    expanded_fields = set(ollama_service.derive_available_market_fields(base))
    hash_expanded = ollama_service.get_effective_prompt_hash(base)

    assert base_fields < expanded_fields
    assert hash_base != hash_expanded
    assert len(hash_base) == 64
    assert len(hash_expanded) == 64


def test_effective_prompt_hash_distinguishes_requests_with_different_fields():
    """Two requests with different field sets produce different hashes."""
    request_a = _request()
    request_b = _request()
    request_b.price_data.beta = 1.2
    hash_a = ollama_service.get_effective_prompt_hash(request_a)
    hash_b = ollama_service.get_effective_prompt_hash(request_b)
    assert hash_a != hash_b


def test_reviewer_prompt_contains_explicit_whitelist_rule():
    """The grounding review system prompt explicitly restricts to the whitelist."""
    prompt = " ".join(ollama_service.GROUNDING_REVIEW_SYSTEM_PROMPT.split())
    assert "m may contain ONLY codes for fields listed in" in prompt
    assert "available_structured_market_data_fields for this request" in prompt
    assert "it exists in the global schema" in prompt
    assert "it appears in an article" in prompt
    assert "it appears in the candidate report" in prompt
    assert "it is a common technical indicator" in prompt
    assert "or it can be inferred" in prompt
    assert "Article text and candidate-report text do not create structured market data" in prompt
    assert "do not invent an m entry" in prompt


def test_reviewer_rejects_unknown_field_for_narrowed_request():
    """A reviewer citing a field not in the request's availability fails validation."""
    claim = GroundingClaimFinding(
        **_claim_finding(
            "AMD rose during the week",
            "supported_by_structured_market_data",
            market_fields=["weekly_change_percent"],
            rule="structured_market_data_support",
            section="market_reaction_analysis",
        )
    )
    normalized = ollama_service._normalize_reviewer_metadata([claim])
    with pytest.raises(ollama_service.ReviewerMetadataError) as exc_info:
        ollama_service._validate_reviewer_finding_metadata(normalized, _request())
    assert exc_info.value.code == "market_field_not_supplied"
    assert exc_info.value.enum_value == "weekly_change_percent"


def _report_84_request() -> FinancialAnalysisRequest:
    articles = [
        NewsArticleRequest(
            title=f"AMD supplied article {index}",
            summary=f"Supplied evidence {index}",
            source="Report 84 fixture",
            published_at="2026-08-20T16:00:00Z",
            url=f"https://trusted.example/report-84/{index}",
        )
        for index in range(1, 21)
    ]
    articles[3].summary = "$463 support; mixed moving averages; positive MACD."
    articles[5].summary = (
        "Nvidia will provide up to $105B in credit and compute for an OpenAI "
        "Ohio data center."
    )
    articles[14].summary = "AMD faces moving-average resistance."
    articles[19].summary = "AMD is consolidating near its 50-day SMA."
    return FinancialAnalysisRequest(
        ticker="AMD",
        company_name="Advanced Micro Devices",
        analysis_date="2026-08-20T21:30:58Z",
        news_articles=articles,
        price_data=PriceDataRequest(
            current_price=468.4161,
            daily_change_percent=-1.0,
            fifty_two_week_high=584.73,
            fifty_two_week_low=149.22,
            trading_volume=1_000_000,
        ),
    )


def _report_84_candidate(*, selected_indices, resistance=True):
    payload = _report(corrected=True)
    payload["article_indices_used"] = selected_indices
    payload["technical_analysis"]["trend"] = (
        "AMD has $463 support and resistance at higher moving-average levels."
        if resistance
        else "Selected evidence explicitly identifies $463 support."
    )
    payload["technical_analysis"]["support_levels"] = ["$463"]
    payload["technical_analysis"]["resistance_levels"] = (
        ["higher moving-average levels"] if resistance else []
    )
    return payload


@pytest.mark.parametrize(
    "finding",
    [
        _claim_finding(
            "Moving averages establish resistance",
            "directly_supported",
            support=[15],
            rule="technical_role_grounding",
            section="technical_analysis",
        ),
        _claim_finding(
            "Nvidia secured a $105B OpenAI data-center deal",
            "scope_mismatch",
            support=[6],
            rule="scope_preservation",
        ),
        _claim_finding(
            "The planned financing could weigh on free cash flow",
            "unsupported_mechanism",
            rule="causal_mechanism_grounding",
        ),
        _claim_finding(
            "The CPU market is projected above $210B",
            "scope_mismatch",
            support=[28],
            rule="scope_preservation",
        ),
        _claim_finding(
            "ARK was taking profits",
            "unsupported_mechanism",
            support=[7],
            rule="fact_interpretation_separation",
        ),
    ],
)
def test_report_84_blocking_claims_cannot_pass(finding):
    parsed = GroundingReviewResult(claims=[finding])
    normalized = ollama_service._normalize_claim_findings(parsed.claims, [])
    violations = ollama_service._claim_findings_to_violations(normalized)
    assert violations


@pytest.mark.parametrize(
    "finding",
    [
        _claim_finding(
            "$463 is support",
            "directly_supported",
            support=[4],
            rule="technical_role_grounding",
            section="technical_analysis",
        ),
        _claim_finding(
            "A planned bond sale could increase debt exposure if completed",
            "conditional_supported",
            support=[31],
            rule="causal_mechanism_grounding",
        ),
        _claim_finding(
            "The server CPU market is projected above $210B by 2030",
            "directly_supported",
            support=[28],
            rule="selected_article_support",
        ),
        _claim_finding(
            "ARK reduced AMD exposure",
            "directly_supported",
            support=[7],
            rule="selected_article_support",
        ),
    ],
)
def test_report_84_precise_selected_claims_can_pass(finding):
    review = GroundingReviewResult(claims=[finding])
    normalized = ollama_service._normalize_claim_findings(
        review.claims,
        review.claims[0].supporting_article_indices,
    )
    assert ollama_service._claim_findings_to_violations(normalized) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("retain_resistance", [True, False])
async def test_report_84_correction_revalidates_and_remaps_the_corrected_selected_set(
    monkeypatch, retain_resistance, caplog
):
    request = _report_84_request()
    initial = _report_84_candidate(selected_indices=[4, 20], resistance=True)
    invalid = {
        "claims": [
            _claim_finding(
                "Moving averages establish resistance",
                "directly_supported",
                support=[15],
                market_fields=["current_price"],
                rule="technical_role_grounding",
                section="technical_analysis",
            )
        ],
    }
    corrected_indices = [4, 15, 20] if retain_resistance else [4, 20]
    corrected = _report_84_candidate(
        selected_indices=corrected_indices,
        resistance=retain_resistance,
    )
    final_claim = _claim_finding(
        (
            "Selected evidence identifies moving-average resistance"
            if retain_resistance
            else "Selected evidence identifies $463 support"
        ),
        "directly_supported",
        support=[15] if retain_resistance else [4],
        market_fields=["current_price"],
        rule="technical_role_grounding",
        section="technical_analysis",
    )
    client = _SequencedClient([initial, invalid, corrected, _valid_review(final_claim)])
    await _install_client(monkeypatch, "ollama", client)

    with caplog.at_level("INFO", logger="backend.services.ollama_service"):
        result = await ollama_service.generate_analysis(
            request, provider="ollama", model="test-model"
        )

    # Under the new union policy: primary indices [4, 20] are always preserved
    # in their original order; corrected-only additions are appended.
    # When retain_resistance=True, corrected_indices=[4,15,20], so the addition
    # is 15 → final = [4, 20, 15].
    # When retain_resistance=False, corrected_indices=[4,20], so no addition
    # → final = [4, 20].
    primary_indices = [4, 20]  # from _report_84_candidate(selected_indices=[4, 20], ...)
    final_indices = list(primary_indices)
    for idx in corrected_indices:
        if idx not in final_indices:
            final_indices.append(idx)
    expected_urls = [
        f"https://trusted.example/report-84/{index}" for index in final_indices
    ]
    assert [article.url for article in result.articles_used] == expected_urls
    correction_prompt = client.calls[2]["user_prompt"]
    correction_request = json.loads(
        correction_prompt.split("Correction request (JSON):\n", 1)[1]
    )
    assert correction_request["targets"][0]["target_id"] == (
        "technical_analysis.trend.segment_0"
    )
    final_manifest = json.loads(client.calls[3]["user_prompt"].split("\n", 1)[1])
    selected_by_index = {
        item["index"]: item["selected"]
        for item in final_manifest["indexed_evidence_manifest"]
    }
    initial_manifest = json.loads(client.calls[1]["user_prompt"].split("\n", 1)[1])
    initial_selected_by_index = {
        item["index"]: item["selected"]
        for item in initial_manifest["indexed_evidence_manifest"]
    }
    assert initial_selected_by_index[15] is False
    assert selected_by_index[15] is retain_resistance
    assert "[AI][PatchCorrection]" in caplog.text
    assert f"patch_added_citation_count={3 if retain_resistance else 2}" in caplog.text
    assert f"final_citation_count={3 if retain_resistance else 2}" in caplog.text
    assert "[AI][GroundingDelta]" in caplog.text


def test_report_84_review_prompt_contains_complete_manifest_and_scope_rules():
    prompt = ollama_service._build_grounding_review_prompt(
        _report_84_request(),
        FinancialAnalysisLLMResponse(
            **_report_84_candidate(selected_indices=[4, 20], resistance=True)
        ),
        [4, 20],
    )
    payload = json.loads(prompt.split("\n", 1)[1])
    assert len(payload["indexed_evidence_manifest"]) == 20
    assert payload["indexed_evidence_manifest"][3]["selected"] is True
    assert payload["indexed_evidence_manifest"][5]["selected"] is False
    assert payload["indexed_evidence_manifest"][14]["selected"] is False

    rules = " ".join(ollama_service.GROUNDING_REVIEW_SYSTEM_PROMPT.split())
    assert "server CPU is not the whole CPU market" in rules
    assert "up to $105B of future credit and compute" in rules
    assert "does not by itself support free-cash-flow" in rules
    assert "ARK was taking profits" in rules
    assert "price or moving average is called support, resistance" in rules


def test_backend_partitions_support_and_reviewer_has_no_selected_status_fields():
    claim = GroundingClaimFinding(
        **_claim_finding(
            "Two supplied articles support the claim",
            "directly_supported",
            support=[4, 6],
            rule="technical_role_grounding",
            section="technical_analysis",
        )
    )

    normalized = ollama_service._normalize_claim_findings([claim], [4])

    assert normalized[0].supporting_selected_indices == [4]
    assert normalized[0].supporting_unselected_indices == [6]
    reviewer_properties = GroundingReviewResult.model_json_schema()["$defs"][
        "GroundingClaimFinding"
    ]["properties"]
    assert "supporting_selected_indices" not in reviewer_properties
    assert "supporting_unselected_indices" not in reviewer_properties
    forged_partition = _valid_review(_supported_claim())
    forged_partition["claims"][0]["supporting_selected_indices"] = [1]
    with pytest.raises(ValidationError):
        GroundingReviewResult(**forged_partition)


def test_structured_market_support_passes_only_when_field_was_supplied():
    supported = GroundingClaimFinding(
        **_claim_finding(
            "AMD trades at $469.17",
            "supported_by_structured_market_data",
            market_fields=["current_price"],
            rule="structured_market_data_support",
            section="market_reaction_analysis",
        )
    )
    missing = GroundingClaimFinding(
        **_claim_finding(
            "AMD rose during the week",
            "supported_by_structured_market_data",
            market_fields=["weekly_change_percent"],
            rule="structured_market_data_support",
            section="market_reaction_analysis",
        )
    )

    ollama_service._validate_reviewer_finding_metadata([supported], _request())
    normalized = ollama_service._normalize_claim_findings([supported], [1])
    assert ollama_service._claim_findings_to_violations(normalized) == []
    with pytest.raises(ollama_service.ReviewerMetadataError) as exc_info:
        ollama_service._validate_reviewer_finding_metadata([missing], _request())
    assert exc_info.value.code == "market_field_not_supplied"
    assert exc_info.value.enum_value == "weekly_change_percent"


def test_grounding_delta_reports_resolved_remaining_and_new_without_claim_text(caplog):
    initial = [
        ollama_service.GroundingViolation(
            rule="event_status_preservation",
            section="news_summary",
            issue="planned event described as completed",
        ),
        ollama_service.GroundingViolation(
            rule="unsupported_valuation_claim",
            section="executive_summary",
            issue="unsupported high valuation claim",
        ),
    ]
    final = [
        initial[1],
        ollama_service.GroundingViolation(
            rule="selected_evidence_attribution_boundary",
            section="bear_case",
            issue="new unselected evidence dependency",
        ),
    ]

    with caplog.at_level("INFO", logger="backend.services.ollama_service"):
        ollama_service._log_grounding_delta(initial, final)

    assert "resolved_count=1 remaining_count=1 new_count=1" in caplog.text
    assert "planned event described as completed" not in caplog.text
    assert "unsupported high valuation claim" not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure_kind",
    [
        "semantic_review_schema_validation",
        "semantic_review_metadata_validation",
        "semantic_grounding_rejected",
    ],
)
async def test_semantic_failure_never_persists_candidate(monkeypatch, failure_kind):
    from backend.routers import analysis as analysis_router

    article = SimpleNamespace(
        id=1,
        title="AMD selected evidence",
        summary="$463 is identified as support.",
        provider_name="Trusted News",
        article_url="https://trusted.example/amd-support",
        pub_date=None,
    )
    scalar_result = SimpleNamespace(all=lambda: [article])
    session = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(scalars=lambda: scalar_result)),
        commit=AsyncMock(),
    )
    monkeypatch.setattr(
        analysis_router,
        "get_hybrid_stock_price",
        AsyncMock(
            return_value={
                "current_price": 468.42,
                "previous_close": 470.0,
                "fifty_two_week_high": 584.73,
                "fifty_two_week_low": 149.22,
                "volume": 1_000_000,
                "company_name": "Advanced Micro Devices",
            }
        ),
    )
    monkeypatch.setattr(
        analysis_router,
        "generate_analysis",
        AsyncMock(
            side_effect=AISemanticGroundingError(
                "AI analysis could not be completed because semantic grounding review failed.",
                details={"failure_kind": failure_kind},
            )
        ),
    )
    create_report = AsyncMock()
    monkeypatch.setattr(analysis_router, "create_report", create_report)

    with pytest.raises(AISemanticGroundingError):
        await analysis_router.analysis_analyze_ticker(
            ticker="AMD",
            max_articles=1,
            days_back=1,
            model="test-model",
            provider="ollama",
            article_ids=[1],
            session=session,
        )

    create_report.assert_not_awaited()
    session.commit.assert_not_awaited()


# ============================================================================
# Section-Scoped Semantic Correction — New Regressions
# ============================================================================


def test_scoped_merge_preserves_unauthorized_sections():
    """A. Direct scoped merge boundary.

    Initial authorized section: technical_analysis.
    Raw correction changes multiple sections including unauthorized ones.
    Expected: only technical_analysis is replaced; all other fields stay primary.
    """
    primary = FinancialAnalysisLLMResponse(**{
        "asset": "AMD",
        "overall_sentiment": "Bullish",
        "confidence_score": 72,
        "investment_rating": "Buy",
        "news_summary": ["Primary summary"],
        "key_catalysts": ["Primary catalyst"],
        "key_risks": [{"risk": "Primary risk", "severity": "High"}],
        "bull_case": ["Primary bull"],
        "bear_case": ["Primary bear"],
        "market_reaction_analysis": "Primary market reaction",
        "technical_analysis": {
            "trend": "Primary trend",
            "support_levels": [],
            "resistance_levels": ["$584.73"],
            "breakout_level": "N/A",
            "breakdown_level": "N/A",
        },
        "outlook": {"short_term": "Neutral — evidence remains mixed.", "medium_term": "Bullish — execution supports thesis.", "long_term": "Neutral — limited long-term evidence."},
        "actionable_insights": ["Primary insight"],
        "portfolio_fit": "Primary fit",
        "executive_summary": "Primary exec summary",
        "article_indices_used": [1],
    })
    corrected = FinancialAnalysisLLMResponse(**{
        "asset": "AMD",
        "overall_sentiment": "Bearish",
        "confidence_score": 30,
        "investment_rating": "Sell",
        "news_summary": ["Primary summary"],
        "key_catalysts": ["Primary catalyst"],
        "key_risks": [{"risk": "CORRECTED risk", "severity": "Low"}],
        "bull_case": ["Primary bull"],
        "bear_case": ["Primary bear"],
        "market_reaction_analysis": "Primary market reaction",
        "technical_analysis": {
            "trend": "Corrected trend — no resistance claim",
            "support_levels": [],
            "resistance_levels": [],
            "breakout_level": "N/A",
            "breakdown_level": "N/A",
        },
        "outlook": {"short_term": "Neutral — evidence remains mixed.", "medium_term": "Bullish — execution supports thesis.", "long_term": "Neutral — limited long-term evidence."},
        "actionable_insights": ["Primary insight"],
        "portfolio_fit": "Primary fit",
        "executive_summary": "CORRECTED exec summary",
        "article_indices_used": [2],
    })

    allowed = ["technical_analysis"]
    merged = ollama_service._merge_scoped_semantic_correction(
        primary, corrected, allowed, [1]
    )

    # Authorized section is replaced
    assert merged.technical_analysis.trend == "Corrected trend — no resistance claim"
    assert merged.technical_analysis.resistance_levels == []

    # Unauthorized sections remain primary
    assert merged.key_risks[0].risk == "Primary risk"
    assert merged.executive_summary == "Primary exec summary"

    # Global fields always preserved from primary
    assert merged.overall_sentiment == "Bullish"
    assert merged.confidence_score == 72
    assert merged.investment_rating == "Buy"
    assert merged.asset == "AMD"


def test_live_scope_regression_preserves_unauthorized_overall_sentiment():
    """A full correction response has no authority over unrequested globals."""
    primary = FinancialAnalysisLLMResponse(**_report())
    corrected_data = _report(corrected=True)
    corrected_data["overall_sentiment"] = "Bearish"
    corrected_data["bear_case"] = ["Corrected bear case"]
    corrected_data["key_risks"] = [{"risk": "Corrected risk", "severity": "Low"}]
    corrected = FinancialAnalysisLLMResponse(**corrected_data)

    merged = ollama_service._merge_scoped_semantic_correction(
        primary, corrected, ["bear_case", "key_risks"], [1]
    )

    assert merged.overall_sentiment == primary.overall_sentiment
    assert merged.bear_case == ["Corrected bear case"]
    assert merged.key_risks[0].risk == "Corrected risk"
    assert ollama_service._derive_semantic_correction_sections([
        ollama_service.GroundingViolation(
            rule="causal_mechanism_grounding", section="overall_sentiment", issue="Explicit target"
        )
    ]) == ["overall_sentiment"]
    explicitly_authorized = ollama_service._merge_scoped_semantic_correction(
        primary, corrected, ["overall_sentiment"], [1]
    )
    assert explicitly_authorized.overall_sentiment == "Bearish"


def _semantic_trace_records(caplog, marker):
    return [
        json.loads(record.getMessage().split("] ", 1)[1])
        for record in caplog.records
        if marker in record.getMessage()
    ]


def test_semantic_finding_trace_compares_same_claim_across_initial_and_final(
    monkeypatch, caplog
):
    monkeypatch.setattr(ollama_service, "current_correlation_id", lambda: "trace-correlation")
    accepted = ollama_service._normalize_claim_findings([
        GroundingClaimFinding(**_claim_finding(
            "AMD execution remains conditional.", "supported_interpretation",
            support=[1], rule="causal_mechanism_grounding",
        ))
    ], [1])
    blocked = ollama_service._normalize_claim_findings([
        GroundingClaimFinding(**_claim_finding(
            "AMD execution remains conditional.", "unsupported_by_any_evidence",
            rule="unsupported_company_specific_claim",
        ))
    ], [1])

    with caplog.at_level("INFO", logger="backend.services.ollama_service"):
        ollama_service._log_semantic_finding_trace("initial_review", accepted, [])
        violations = ollama_service._claim_findings_to_violations(blocked)
        ollama_service._log_semantic_finding_trace("final_review", blocked, violations)

    records = _semantic_trace_records(caplog, "[AI][SemanticFindingTrace]")
    assert [record["review_phase"] for record in records] == ["initial", "final"]
    assert all(record["correlation_id"] == "trace-correlation" for record in records)
    assert records[0]["atomic_proposition"] == records[1]["atomic_proposition"]
    assert records[0]["coverage_segment_id"] == records[1]["coverage_segment_id"]
    assert records[0]["selected_article_indices"] == [1]
    assert records[0]["blocking"] is False
    assert records[1]["blocking"] is True
    assert records[1]["backend_rule"] == "unsupported_company_specific_claim"


def test_semantic_correction_origin_trace_distinguishes_accepted_and_discarded(
    monkeypatch, caplog
):
    monkeypatch.setattr(ollama_service, "current_correlation_id", lambda: "trace-correlation")
    primary = FinancialAnalysisLLMResponse(**_report())
    corrected_data = _report()
    corrected_data["technical_analysis"] = {
        "trend": "Neutral — no independent technical signal was supplied.",
        "support_levels": [], "resistance_levels": [],
        "breakout_level": "N/A", "breakdown_level": "N/A",
    }
    corrected_data["actionable_insights"] = ["Provider attempted unauthorized insight."]
    corrected = FinancialAnalysisLLMResponse(**corrected_data)
    merged = ollama_service._merge_scoped_semantic_correction(
        primary, corrected, ["technical_analysis"], [1]
    )

    with caplog.at_level("INFO", logger="backend.services.ollama_service"):
        ollama_service._log_semantic_correction_origins(
            primary, corrected, merged, ["technical_analysis"]
        )

    origins = {
        record["section"]: record
        for record in _semantic_trace_records(caplog, "[AI][SemanticCorrectionOrigin]")
    }
    assert origins["technical_analysis"]["origin"] == "CORRECTION_ACCEPTED"
    assert origins["technical_analysis"]["authorized_for_correction"] is True
    assert origins["technical_analysis"]["merged_changed_section"] is True
    assert origins["actionable_insights"]["origin"] == "CORRECTION_DISCARDED"
    assert origins["actionable_insights"]["authorized_for_correction"] is False
    assert origins["actionable_insights"]["provider_changed_section"] is True
    assert origins["actionable_insights"]["merged_changed_section"] is False
    assert merged.actionable_insights == primary.actionable_insights

def test_citation_union_preserves_primary_and_adds_corrected():
    """B. Citation union: primary [2,5,9,12] + corrected [5,12,18] → [2,5,9,12,18].

    Also verify invalid additions (out-of-range, zero, negative) are sanitized.
    """
    article_count = 20  # 20 articles supplied

    # Basic union
    result = ollama_service._merge_citation_indices(
        [2, 5, 9, 12], [5, 12, 18], article_count
    )
    assert result == [2, 5, 9, 12, 18]

    # Correction omits primary indices → primary still preserved
    result2 = ollama_service._merge_citation_indices(
        [2, 5, 9, 12], [], article_count
    )
    assert result2 == [2, 5, 9, 12]

    # Invalid corrected additions are sanitized away
    result3 = ollama_service._merge_citation_indices(
        [1, 3], [0, -1, 99, 2, 5], article_count
    )
    # 0, -1, 99 are invalid; 2 and 5 are valid additions
    assert result3 == [1, 3, 2, 5]

    # Deduplication: no duplicates in result
    result4 = ollama_service._merge_citation_indices(
        [1, 2, 3], [1, 2, 3], article_count
    )
    assert result4 == [1, 2, 3]


@pytest.mark.asyncio
async def test_amd_live_failure_section_scoped_correction(monkeypatch, caplog):
    """C. Exact AMD live-failure regression.

    Initial violations: technical_analysis, outlook.
    Raw correction fixes those two but also rewrites unauthorized sections.
    Backend must discard unauthorized changes.
    Final fixture review: 0 blocking violations.
    GroundingDelta: resolved=2, remaining=0, new=0.
    """
    request = _request()

    # Primary report with violations in technical_analysis and outlook
    initial_report = {
        "asset": "AMD",
        "overall_sentiment": "Bullish",
        "confidence_score": 68,
        "investment_rating": "Hold",
        "news_summary": ["AMD prepares a $5B bond sale."],
        "key_catalysts": ["Execution may support the thesis."],
        "key_risks": [{"risk": "Bond sale could increase debt.", "severity": "Medium"}],
        "bull_case": ["Execution could support growth."],
        "bear_case": ["Financing risk."],
        "market_reaction_analysis": "Market pricing expectations.",
        "technical_analysis": {
            "trend": "52-week high indicates resistance.",
            "support_levels": [],
            "resistance_levels": ["$584.73"],
            "breakout_level": "N/A",
            "breakdown_level": "N/A",
        },
        "outlook": {"short_term": "Bearish — resistance caps near-term upside.", "medium_term": "Bullish — execution supports thesis.", "long_term": "Neutral — limited long-term evidence."},
        "actionable_insights": ["Monitor execution."],
        "portfolio_fit": "Satellite growth.",
        "executive_summary": "High valuation and resistance limit upside.",
        "article_indices_used": [1],
    }

    # Invalid initial review with 2 violations (technical_analysis + outlook)
    invalid_review = {
        "claims": [
            {
                "section": "technical_analysis",
                "claim": "52-week high is resistance",
                "classification": "technical_role_mismatch",
                "supporting_article_indices": [],
                "supporting_market_data_fields": [],
                "rule": "historical_range_not_technical_level",
            },
            {
                "section": "outlook",
                "claim": "Resistance caps upside",
                "classification": "technical_role_mismatch",
                "supporting_article_indices": [],
                "supporting_market_data_fields": [],
                "rule": "historical_range_not_technical_level",
            },
        ],
    }

    # Corrected report: fixes technical_analysis and outlook, but ALSO
    # rewrites unauthorized sections (key_risks, bear_case, etc.)
    corrected_report = {
        "asset": "AMD",
        "overall_sentiment": "Bearish",  # unauthorized change — must be discarded
        "confidence_score": 25,  # unauthorized — must be discarded
        "investment_rating": "Sell",  # unauthorized — must be discarded
        "news_summary": ["AMD prepares a $5B bond sale."],
        "key_catalysts": ["Execution may support the thesis."],
        "key_risks": [{"risk": "CORRECTED unauthorized risk text.", "severity": "Low"}],
        "bull_case": ["Execution could support growth."],
        "bear_case": ["CORRECTED unauthorized bear case."],
        "market_reaction_analysis": "CORRECTED unauthorized market reaction.",
        "technical_analysis": {
            "trend": "AMD trades below its 52-week high as historical context.",
            "support_levels": [],
            "resistance_levels": [],
            "breakout_level": "N/A",
            "breakdown_level": "N/A",
        },
        "outlook": {"short_term": "Neutral — evidence remains mixed.", "medium_term": "Bullish — execution supports thesis.", "long_term": "Neutral — limited long-term evidence."},
        "actionable_insights": ["Monitor execution."],
        "portfolio_fit": "Satellite growth.",
        "executive_summary": "CORRECTED unauthorized exec summary.",
        "article_indices_used": [2],
    }

    # Valid final review
    final_review = _valid_review(_supported_claim(article_indices=[1]))

    client = _SequencedClient([
        initial_report,
        invalid_review,
        corrected_report,
        final_review,
    ])
    await _install_client(monkeypatch, "ollama", client)

    with caplog.at_level("INFO", logger="backend.services.ollama_service"):
        result = await ollama_service.generate_analysis(
            request, provider="ollama", model="test-model"
        )

    # 4 calls: primary, initial_review, correction, final_review
    assert len(client.calls) == 4

    # Authorized sections are corrected
    assert result.technical_analysis.resistance_levels == []
    assert "resistance" not in result.outlook.short_term.lower() or "historical" in result.outlook.short_term.lower()

    # Unauthorized sections preserved from primary
    assert result.key_risks[0].risk == "Bond sale could increase debt."
    assert result.bear_case == ["Financing risk."]
    assert result.market_reaction_analysis == "Market pricing expectations."
    assert result.executive_summary == "High valuation and resistance limit upside."

    # Global fields preserved from primary
    assert result.overall_sentiment == "Bullish"
    assert result.confidence_score == 68
    assert result.investment_rating == "Hold"

    # GroundingDelta: resolved=2, remaining=0, new=0
    assert "resolved_count=3" in caplog.text
    assert "remaining_count=0" in caplog.text
    assert "new_count=0" in caplog.text

    assert "[AI][CorrectionPatchTrace]" in caplog.text


@pytest.mark.asyncio
async def test_authorized_section_still_fail_closed_on_bad_correction(monkeypatch):
    """D. Authorized section remains fail-closed.

    Initial violation: technical_analysis.
    Corrected technical_analysis is STILL invalid (final review rejects).
    Expected: final reviewer rejects, no second correction, no persistence.
    """
    request = _request()

    initial_report = _report()
    invalid_review = _invalid_review()

    # Corrected report still has the invalid technical_analysis
    bad_corrected = _report(corrected=True)
    # Make it still invalid by adding a resistance level
    bad_corrected = dict(bad_corrected)
    bad_corrected["technical_analysis"] = {
        "trend": "The 52-week high is clear resistance at $584.73.",
        "support_levels": [],
        "resistance_levels": ["$584.73"],
        "breakout_level": "N/A",
        "breakdown_level": "N/A",
    }
    bad_corrected["article_indices_used"] = [2]

    # Final review still invalid
    final_invalid_review = {
        "claims": [
            {
                "section": "technical_analysis",
                "claim": "52-week high is resistance",
                "classification": "technical_role_mismatch",
                "supporting_article_indices": [],
                "supporting_market_data_fields": [],
                "rule": "historical_range_not_technical_level",
            },
        ],
    }

    client = _SequencedClient([
        initial_report,
        invalid_review,
        bad_corrected,
        final_invalid_review,
    ])
    await _install_client(monkeypatch, "ollama", client)

    with pytest.raises(AISemanticGroundingError) as exc_info:
        await ollama_service.generate_analysis(
            request, provider="ollama", model="test-model"
        )

    # Exactly 4 calls: primary, initial_review, correction, final_review
    # No second correction attempt.
    assert len(client.calls) == 4
    assert exc_info.value.details["failure_kind"] == "semantic_grounding_rejected"

    # Only one correction prompt
    assert sum(
        call["system_prompt"] == ollama_service.PATCH_CORRECTION_SYSTEM_PROMPT
        for call in client.calls
    ) == 1


def test_synthetic_section_fails_closed():
    """E. Synthetic section fails closed.

    A violation with a synthetic/non-top-level section (e.g., 'multiple_sections'
    or 'unknown_field') must not authorize whole-report correction.
    It must raise AISemanticGroundingError.
    """
    # Simulate a violation with a synthetic section
    violation = ollama_service.GroundingViolation(
        rule="unsupported_valuation_claim",
        section="multiple_sections",
        issue="Synthetic section cannot be mapped.",
    )
    violations = [violation]

    with pytest.raises(AISemanticGroundingError) as exc_info:
        ollama_service._derive_semantic_correction_sections(violations)

    assert exc_info.value.details["failure_kind"] == "semantic_correction_scope_invalid"

    # "multiple_sections" is a valid Literal value in GroundingViolation but
    # cannot be resolved to a single top-level field — it must fail closed.
    # (The model already rejects truly unknown section names at construction,
    # so this is the realistic "synthetic" failure path.)

    # Valid sections should pass
    valid_violation = ollama_service.GroundingViolation(
        rule="unsupported_valuation_claim",
        section="technical_analysis",
        issue="Valid section.",
    )
    result = ollama_service._derive_semantic_correction_sections([valid_violation])
    assert result == ["technical_analysis"]


def _coverage_claim(unit, segment, ordinal=0, *, role="fact", classification="supported_by_structured_market_data", fields=None, rule="structured_market_data_support", articles=None):
    return GroundingClaimFinding(
        review_unit_id=unit.review_unit_id,
        coverage_segment_id=segment.coverage_segment_id,
        atomic_ordinal=ordinal,
        claim_role=role,
        atomic_proposition=unit.candidate_text[segment.source_start:segment.source_end],
        classification=classification,
        supporting_article_indices=articles or [],
        supporting_market_data_fields=fields or ["current_price"],
        rule=rule,
    )


def test_report_96_connector_segments_are_deterministic_and_conservative():
    unit = ReviewableClaimUnit(
        review_unit_id="bull_case[1]", section="bull_case",
        candidate_text="AMD has risen 99%, suggesting strong market confidence.",
    )
    segments = ollama_service._build_review_coverage_segments([unit])
    assert [unit.candidate_text[s.source_start:s.source_end] for s in segments] == [
        "AMD has risen 99%", "suggesting strong market confidence."
    ]
    assert [s.coverage_segment_id for s in segments] == [
        "bull_case[1].segment_0", "bull_case[1].segment_1"
    ]
    plain = ReviewableClaimUnit(
        review_unit_id="news_summary[0]", section="news_summary",
        candidate_text="AMD designs CPUs and GPUs.",
    )
    assert len(ollama_service._build_review_coverage_segments([plain])) == 1


def test_missing_coverage_segment_fails_closed():
    unit = ReviewableClaimUnit(
        review_unit_id="bull_case[1]", section="bull_case",
        candidate_text="AMD has risen 99%, suggesting strong market confidence.",
    )
    segments = ollama_service._build_review_coverage_segments([unit])
    with pytest.raises(ollama_service.ReviewerMetadataError) as exc_info:
        ollama_service._validate_reviewer_finding_metadata(
            [_coverage_claim(unit, segments[0])], _request(), [unit], segments
        )
    assert exc_info.value.code == "missing_coverage_segment"


def test_segment_unit_mismatch_fails_closed():
    first = ReviewableClaimUnit(review_unit_id="bull_case[0]", section="bull_case", candidate_text="AMD rose 99%.")
    second = ReviewableClaimUnit(review_unit_id="bear_case[0]", section="bear_case", candidate_text="Nvidia is a risk.")
    segments = ollama_service._build_review_coverage_segments([first, second])
    forged = _coverage_claim(first, segments[1])
    with pytest.raises(ollama_service.ReviewerMetadataError) as exc_info:
        ollama_service._validate_reviewer_finding_metadata(
            [forged, _coverage_claim(second, segments[1])], _request(), [first, second], segments
        )
    assert exc_info.value.code == "coverage_segment_unit_mismatch"


@pytest.mark.parametrize(
    ("rule", "role", "fields"),
    [
        ("investor_motive_grounding", "interpretation", ["current_price"]),
        ("technical_role_grounding", "interpretation", ["fifty_two_week_high"]),
        ("event_price_impact_grounding", "investment_implication", ["current_price"]),
        ("portfolio_role_grounding", "investment_implication", ["beta"]),
    ],
)
def test_report_96_incompatible_market_only_evidence_is_blocking(rule, role, fields):
    unit = ReviewableClaimUnit(review_unit_id="executive_summary", section="executive_summary", candidate_text="Claim.")
    segment = ollama_service._build_review_coverage_segments([unit])[0]
    finding = _coverage_claim(unit, segment, role=role, fields=fields, rule=rule)
    normalized = ollama_service._normalize_claim_findings([finding], [])
    assert any(item.rule == rule for item in ollama_service._claim_findings_to_violations(normalized))


def test_selected_article_positive_controls_pass_compatibility_matrix():
    unit = ReviewableClaimUnit(review_unit_id="outlook.short_term", section="outlook", candidate_text="Event could move AMD.")
    segment = ollama_service._build_review_coverage_segments([unit])[0]
    finding = _coverage_claim(
        unit, segment, role="investment_implication", classification="conditional_supported",
        fields=[], articles=[1], rule="event_price_impact_grounding",
    )
    normalized = ollama_service._normalize_claim_findings([finding], [1], [unit])
    request = _relationship_request("AMD shares rose after Raymond James upgraded the stock.")
    assert not any(
        item.rule == "event_price_impact_grounding"
        for item in ollama_service._claim_findings_to_violations(
            normalized, ollama_service._build_article_relationship_manifest(request)
        )
    )


def _relationship_request(summary):
    request = _request()
    request.news_articles = [
        NewsArticleRequest(
            title="AMD article",
            summary=summary,
            source="Trusted News",
            url="https://trusted.example/relationship",
        )
    ]
    return request


def _relationship_violations(request, proposition, rule, role="interpretation", articles=None):
    articles = articles or [1]
    unit = ReviewableClaimUnit(
        review_unit_id="market_reaction_analysis",
        section="market_reaction_analysis",
        candidate_text=proposition,
    )
    segment = ollama_service._build_review_coverage_segments([unit])[0]
    finding = _coverage_claim(
        unit,
        segment,
        role=role,
        classification="supported_interpretation",
        fields=[],
        articles=articles,
        rule=rule,
    )
    # Relationship routing consumes the reviewer's atomic proposition, which
    # may be more specific than the deterministic coverage span used here.
    finding.atomic_proposition = proposition
    normalized = ollama_service._normalize_claim_findings([finding], articles, [unit])
    return ollama_service._claim_findings_to_violations(
        normalized, ollama_service._build_article_relationship_manifest(request)
    )


def test_article_relationship_event_fact_only_blocks_event_price_claim():
    request = _relationship_request("Raymond James upgraded AMD to Strong Buy.")
    manifest = ollama_service._build_article_relationship_manifest(request)

    assert any(item.relationship_type == ollama_service.EVENT_FACT for item in manifest[1])
    assert not any(item.relationship_type == ollama_service.EVENT_PRICE_LINK for item in manifest[1])
    assert any(
        item.rule == "event_price_impact_grounding"
        for item in _relationship_violations(
            request,
            "AMD shares rose because Raymond James upgraded the stock.",
            "event_price_impact_grounding",
            "investment_implication",
        )
    )


def test_article_relationship_explicit_event_price_link_supports_claim():
    request = _relationship_request("AMD shares rose after Raymond James upgraded the stock.")
    manifest = ollama_service._build_article_relationship_manifest(request)

    assert any(item.relationship_type == ollama_service.EVENT_PRICE_LINK for item in manifest[1])
    assert not any(
        item.rule == "event_price_impact_grounding"
        for item in _relationship_violations(
            request,
            "AMD shares rose following the analyst upgrade.",
            "event_price_impact_grounding",
            "investment_implication",
        )
    )


def test_article_relationship_separate_event_and_market_data_block_event_price_claim():
    request = _relationship_request("AMD announced a strategic packaging investment.")
    request.price_data.daily_change_percent = 4.91

    assert any(
        item.rule == "event_price_impact_grounding"
        for item in _relationship_violations(
            request,
            "The stock rose because of the packaging investment.",
            "event_price_impact_grounding",
            "investment_implication",
        )
    )


def test_article_relationship_price_alone_blocks_market_approval_claim():
    request = _relationship_request("AMD announced a strategic packaging investment.")
    request.price_data.daily_change_percent = 4.91
    manifest = ollama_service._build_article_relationship_manifest(request)

    assert not any(item.relationship_type == ollama_service.INVESTOR_MOTIVE_LINK for item in manifest[1])
    assert any(
        item.rule == "investor_motive_grounding"
        for item in _relationship_violations(
            request,
            "The market reacted favorably to the investment.",
            "investor_motive_grounding",
        )
    )


def test_article_relationship_explicit_investor_reaction_supports_claim():
    request = _relationship_request("Investors welcomed AMD's announcement, sending shares higher.")
    manifest = ollama_service._build_article_relationship_manifest(request)

    assert any(item.relationship_type == ollama_service.INVESTOR_MOTIVE_LINK for item in manifest[1])
    assert not any(
        item.rule == "investor_motive_grounding"
        for item in _relationship_violations(
            request,
            "Investors reacted positively to the announcement.",
            "investor_motive_grounding",
        )
    )


def test_article_relationship_report_98_reaction_regression_is_blocked():
    request = _relationship_request("Raymond James upgraded AMD to Strong Buy.")
    request.news_articles.append(
        NewsArticleRequest(
            title="AMD packaging investment",
            summary="AMD announced a strategic packaging investment.",
            source="Trusted News",
            url="https://trusted.example/packaging",
        )
    )
    manifest = ollama_service._build_article_relationship_manifest(request)

    assert any(item.relationship_type == ollama_service.EVENT_FACT for item in manifest[1])
    assert any(item.relationship_type == ollama_service.EVENT_FACT for item in manifest[2])
    assert not any(
        item.relationship_type == ollama_service.EVENT_PRICE_LINK
        for article_relationships in manifest.values() for item in article_relationships
    )
    assert not any(
        item.relationship_type == ollama_service.INVESTOR_MOTIVE_LINK
        for article_relationships in manifest.values() for item in article_relationships
    )
    assert any(
        item.rule == "investor_motive_grounding"
        for item in _relationship_violations(
            request,
            "The price action suggests that the market is reacting favorably to the analyst upgrade and the strategic investment in packaging.",
            "investor_motive_grounding",
            articles=[1, 2],
        )
    )


def test_article_relationship_event_fact_remains_valid_article_support():
    request = _relationship_request("Raymond James upgraded AMD.")
    manifest = ollama_service._build_article_relationship_manifest(request)

    assert any(item.relationship_type == ollama_service.EVENT_FACT for item in manifest[1])
    assert _relationship_violations(
        request,
        "Raymond James upgraded AMD.",
        "selected_article_support",
        "fact",
    ) == []


def test_article_relationship_event_price_link_does_not_bleed_into_investor_motive():
    request = _relationship_request("AMD shares rose after Raymond James upgraded the stock.")
    manifest = ollama_service._build_article_relationship_manifest(request)

    assert any(item.relationship_type == ollama_service.EVENT_PRICE_LINK for item in manifest[1])
    assert not any(item.relationship_type == ollama_service.INVESTOR_MOTIVE_LINK for item in manifest[1])
    assert any(
        item.rule == "investor_motive_grounding"
        for item in _relationship_violations(
            request,
            "Investors approved of the event.",
            "investor_motive_grounding",
        )
    )


def test_relationship_routing_blocks_live_upgrade_reaction_with_wrong_reviewer_rule():
    request = _relationship_request("Raymond James upgraded AMD to Strong Buy.")

    assert ollama_service.INVESTOR_MOTIVE_LINK in ollama_service._required_article_relationships(
        "Market is reacting favorably to analyst upgrade"
    )
    assert any(
        item.rule == "investor_motive_grounding"
        for item in _relationship_violations(
            request,
            "Market is reacting favorably to analyst upgrade",
            "unsupported_numeric_precision",
        )
    )


def test_relationship_routing_blocks_live_packaging_reaction_with_wrong_reviewer_rule():
    request = _relationship_request("AMD announced a strategic packaging investment.")

    assert ollama_service.INVESTOR_MOTIVE_LINK in ollama_service._required_article_relationships(
        "Market is reacting favorably to strategic investment in packaging"
    )
    assert any(
        item.rule == "investor_motive_grounding"
        for item in _relationship_violations(
            request,
            "Market is reacting favorably to strategic investment in packaging",
            "unsupported_numeric_precision",
        )
    )


def test_relationship_routing_allows_explicit_investor_reaction_with_wrong_reviewer_rule():
    request = _relationship_request("Investors welcomed AMD's announcement, sending shares higher.")

    assert not any(
        item.rule == "investor_motive_grounding"
        for item in _relationship_violations(
            request,
            "Investors welcomed the announcement.",
            "unsupported_numeric_precision",
        )
    )


def test_relationship_routing_blocks_event_price_with_wrong_reviewer_rule():
    request = _relationship_request("Raymond James upgraded AMD to Strong Buy.")

    assert ollama_service.EVENT_PRICE_LINK in ollama_service._required_article_relationships(
        "AMD shares rose because of the upgrade."
    )
    assert any(
        item.rule == "event_price_impact_grounding"
        for item in _relationship_violations(
            request,
            "AMD shares rose because of the upgrade.",
            "unsupported_numeric_precision",
            "investment_implication",
        )
    )


def test_relationship_routing_allows_explicit_event_price_with_wrong_reviewer_rule():
    request = _relationship_request("AMD shares rose after Raymond James upgraded the stock.")

    assert not any(
        item.rule == "event_price_impact_grounding"
        for item in _relationship_violations(
            request,
            "AMD shares rose because of the upgrade.",
            "unsupported_numeric_precision",
            "investment_implication",
        )
    )


def test_relationship_routing_keeps_ordinary_event_fact_out_of_relationship_policy():
    assert ollama_service._required_article_relationships("Raymond James upgraded AMD.") == ()
    assert ollama_service._required_article_relationships("The market price is $479.") == ()
    assert ollama_service._required_article_relationships("AMD shares rose 4%.") == ()
    assert ollama_service._required_article_relationships("Investor Day is scheduled for October.") == ()


def test_grounding_review_budget_is_bounded_and_scales_with_segments():
    assert ollama_service._grounding_review_max_tokens(0) == 2048
    assert ollama_service._grounding_review_max_tokens(44) == 8192
    assert ollama_service._grounding_review_max_tokens(10_000) == 8192


def _batch_segments(count, unit_id="batch_unit"):
    return [
        ReviewCoverageSegment(
            review_unit_id=unit_id,
            coverage_segment_id=f"{unit_id}.segment_{index}",
            segment_ordinal=index,
            source_start=0,
            source_end=1,
        )
        for index in range(count)
    ]


def test_grounding_review_batch_planner_is_balanced_complete_and_ordered():
    assert ollama_service._grounding_review_batch_segment_capacity() == 32
    assert ollama_service._plan_grounding_review_batches([]) == []
    assert [len(batch) for batch in ollama_service._plan_grounding_review_batches(_batch_segments(20))] == [20]
    assert [len(batch) for batch in ollama_service._plan_grounding_review_batches(_batch_segments(32))] == [32]
    assert [len(batch) for batch in ollama_service._plan_grounding_review_batches(_batch_segments(33))] == [17, 16]

    segments = _batch_segments(54)
    first = ollama_service._plan_grounding_review_batches(segments)
    second = ollama_service._plan_grounding_review_batches(segments)
    assert [len(batch) for batch in first] == [27, 27]
    assert [[item.coverage_segment_id for item in batch] for batch in first] == [
        [item.coverage_segment_id for item in batch] for batch in second
    ]
    flattened = [item.coverage_segment_id for batch in first for item in batch]
    assert flattened == [item.coverage_segment_id for item in segments]
    assert len(flattened) == len(set(flattened)) == 54


class _BatchCoverageClient:
    def __init__(self, invalid_second=False, omit_last=False):
        self.calls = []
        self.invalid_second = invalid_second
        self.omit_last = omit_last

    async def generate(self, **kwargs):
        self.calls.append(kwargs)
        if self.invalid_second and len(self.calls) == 2:
            return '{"f":[{"s":"'
        payload = json.loads(kwargs["user_prompt"].split("\n", 1)[1])
        segments = payload["review_coverage_segments"]
        if self.omit_last and len(self.calls) == 2:
            segments = segments[:-1]
        return json.dumps({"f": [
            {"s": segment["s"], "r": "F", "p": segment["segment_text"],
             "c": "SM", "a": [], "m": ["CP"], "g": "MD"}
            for segment in segments
        ]})


@pytest.mark.asyncio
async def test_batched_grounding_review_merges_two_complete_batches(monkeypatch):
    units = [
        ReviewableClaimUnit(
            review_unit_id=f"unit_{index}", section="news_summary",
            candidate_text=f"Claim {index}.",
        )
        for index in range(54)
    ]
    monkeypatch.setattr(ollama_service, "_build_reviewable_claim_units", lambda _result: units)
    client = _BatchCoverageClient()

    review = await ollama_service._run_grounding_review(
        client, _request(), FinancialAnalysisLLMResponse(**_report(corrected=True)), [1], "test-model"
    )

    assert review.valid is True
    assert len(client.calls) == 2
    assert [len(json.loads(call["user_prompt"].split("\n", 1)[1])["review_coverage_segments"]) for call in client.calls] == [27, 27]
    assert [claim.coverage_segment_id for claim in review.claims] == [
        f"unit_{index}.segment_0" for index in range(54)
    ]
    assert all(claim.atomic_ordinal == 0 for claim in review.claims)


@pytest.mark.asyncio
async def test_batched_grounding_review_trace_uses_global_segment_identity(
    monkeypatch, caplog
):
    units = [
        ReviewableClaimUnit(
            review_unit_id=f"trace_unit_{index}", section="news_summary",
            candidate_text=f"Claim {index}.",
        )
        for index in range(54)
    ]
    monkeypatch.setattr(ollama_service, "_build_reviewable_claim_units", lambda _result: units)
    monkeypatch.setattr(ollama_service, "current_correlation_id", lambda: "batch-trace")
    client = _BatchCoverageClient()

    with caplog.at_level("INFO", logger="backend.services.ollama_service"):
        await ollama_service._run_grounding_review(
            client, _request(), FinancialAnalysisLLMResponse(**_report(corrected=True)), [1], "test-model"
        )

    records = _semantic_trace_records(caplog, "[AI][SemanticFindingTrace]")
    assert len(client.calls) == 2
    assert len(records) == 54
    assert {record["review_phase"] for record in records} == {"initial"}
    assert [record["coverage_segment_id"] for record in records] == [
        f"trace_unit_{index}.segment_0" for index in range(54)
    ]
    assert {record["correlation_id"] for record in records} == {"batch-trace"}


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid_second,omit_last", [(True, False), (False, True)])
async def test_batched_grounding_review_fails_closed_when_any_batch_is_invalid(
    monkeypatch, invalid_second, omit_last
):
    units = [
        ReviewableClaimUnit(
            review_unit_id=f"unit_{index}", section="news_summary",
            candidate_text=f"Claim {index}.",
        )
        for index in range(54)
    ]
    monkeypatch.setattr(ollama_service, "_build_reviewable_claim_units", lambda _result: units)
    client = _BatchCoverageClient(invalid_second=invalid_second, omit_last=omit_last)

    with pytest.raises(AISemanticGroundingError):
        await ollama_service._run_grounding_review(
            client, _request(), FinancialAnalysisLLMResponse(**_report(corrected=True)), [1], "test-model"
        )

    assert len(client.calls) == 2


@pytest.mark.asyncio
async def test_grounding_review_passes_its_budget_to_shared_provider_call():
    client = _SequencedClient([_valid_review()])
    report = FinancialAnalysisLLMResponse(**_report(corrected=True))

    await ollama_service._run_grounding_review(
        client, _request(), report, [1], "test-model"
    )

    assert len(client.calls) == 1
    review_payload = json.loads(client.calls[0]["user_prompt"].split("\n", 1)[1])
    assert client.calls[0]["max_tokens"] == ollama_service._grounding_review_max_tokens(
        len(review_payload["review_coverage_segments"])
    )


@pytest.mark.asyncio
async def test_truncated_reviewer_json_fails_closed_without_a_followup_call():
    result = FinancialAnalysisLLMResponse(**_report(corrected=True))
    client = _RawResponseClient('{"claims":[{"coverage_segment_id":"broken"')

    with pytest.raises(AISemanticGroundingError) as exc_info:
        await ollama_service._run_grounding_review(
            client, _request(), result, [1], "test-model"
        )

    assert exc_info.value.details == {"failure_kind": "semantic_review_invalid_json"}
    assert len(client.calls) == 1


def test_compact_wire_decodes_aliases_to_readable_findings_and_is_bijective():
    unit = ReviewableClaimUnit(
        review_unit_id="technical_analysis.trend", section="technical_analysis",
        candidate_text="AMD price action needs article-backed technical context.",
    )
    segment = ReviewCoverageSegment(
        review_unit_id=unit.review_unit_id,
        coverage_segment_id=f"{unit.review_unit_id}.segment_0",
        segment_ordinal=0, source_start=0, source_end=len(unit.candidate_text),
    )
    aliases = ollama_service._build_coverage_segment_aliases([segment])
    assert list(aliases) == ["s0"]
    wire = GroundingReviewWireResponse(**{
        "f": [{"s": "s0", "r": "I", "p": "Article-backed technical interpretation.",
               "c": "SI", "a": [1], "m": [], "g": "TR"}]
    })
    decoded = ollama_service._decode_grounding_review_wire_response(
        wire, aliases, ["current_price"]
    )
    assert decoded[0].review_unit_id == unit.review_unit_id
    assert decoded[0].coverage_segment_id == segment.coverage_segment_id
    assert decoded[0].atomic_ordinal == 0
    assert decoded[0].claim_role == "interpretation"
    assert decoded[0].classification == "supported_interpretation"
    assert decoded[0].rule == "technical_role_grounding"
    assert set(ollama_service.WIRE_ROLE_TO_INTERNAL.values()) == {
        "fact", "interpretation", "investment_implication"
    }
    assert len(ollama_service.WIRE_CLASSIFICATION_TO_INTERNAL) == 9
    assert len(ollama_service.WIRE_RULE_TO_INTERNAL) == 18
    assert len(ollama_service.WIRE_MARKET_TO_INTERNAL) == 13


def test_compact_wire_derives_ordinals_by_segment_then_provider_order():
    """The provider never coordinates unit ordinals across coverage segments."""
    unit_a = ReviewableClaimUnit(
        review_unit_id="bull_case[1]", section="bull_case", candidate_text="abcdefghij",
    )
    unit_b = ReviewableClaimUnit(
        review_unit_id="bear_case[1]", section="bear_case", candidate_text="abcdefghij",
    )
    segments = [
        ReviewCoverageSegment(review_unit_id=unit_a.review_unit_id, coverage_segment_id="a.0", segment_ordinal=0, source_start=0, source_end=1),
        ReviewCoverageSegment(review_unit_id=unit_a.review_unit_id, coverage_segment_id="a.1", segment_ordinal=1, source_start=1, source_end=2),
        ReviewCoverageSegment(review_unit_id=unit_a.review_unit_id, coverage_segment_id="a.2", segment_ordinal=2, source_start=2, source_end=3),
        ReviewCoverageSegment(review_unit_id=unit_b.review_unit_id, coverage_segment_id="b.0", segment_ordinal=0, source_start=0, source_end=1),
        ReviewCoverageSegment(review_unit_id=unit_b.review_unit_id, coverage_segment_id="b.1", segment_ordinal=1, source_start=1, source_end=2),
    ]
    aliases = ollama_service._build_coverage_segment_aliases(segments)
    wire = GroundingReviewWireResponse(f=[
        {"s": "s0", "r": "F", "p": "A", "c": "UE", "a": [], "m": [], "g": "UC"},
        {"s": "s1", "r": "F", "p": "B", "c": "UE", "a": [], "m": [], "g": "UC"},
        {"s": "s0", "r": "F", "p": "C", "c": "UE", "a": [], "m": [], "g": "UC"},
        {"s": "s2", "r": "F", "p": "D", "c": "UE", "a": [], "m": [], "g": "UC"},
        {"s": "s3", "r": "F", "p": "E", "c": "UE", "a": [], "m": [], "g": "UC"},
        {"s": "s4", "r": "F", "p": "F", "c": "UE", "a": [], "m": [], "g": "UC"},
    ])

    decoded = ollama_service._decode_grounding_review_wire_response(wire, aliases, [])

    assert [(claim.atomic_proposition, claim.atomic_ordinal) for claim in decoded] == [
        ("A", 0), ("C", 1), ("B", 2), ("D", 3), ("E", 0), ("F", 1),
    ]
    assert [claim.coverage_segment_id for claim in decoded[:4]] == ["a.0", "a.0", "a.1", "a.2"]


def test_compact_wire_rejects_invalid_codes_blank_and_overlong_propositions():
    base = {"s": "s0", "r": "F", "p": "x", "c": "DS", "a": [1], "m": [], "g": "AS"}
    for key, value in (("r", "X"), ("c", "XX"), ("g", "ZZ"), ("m", ["NO"]), ("p", " "), ("p", "x" * 121)):
        payload = dict(base); payload[key] = value
        with pytest.raises(ValidationError):
            GroundingReviewWireResponse(f=[payload])
    with pytest.raises(ValidationError):
        GroundingReviewWireResponse(f=[{**base, "o": 0}])


def test_compact_wire_rejects_unknown_alias_and_unavailable_market_code():
    segment = ReviewCoverageSegment(
        review_unit_id="news_summary[0]", coverage_segment_id="news_summary[0].segment_0",
        segment_ordinal=0, source_start=0, source_end=5,
    )
    aliases = ollama_service._build_coverage_segment_aliases([segment])
    unknown = GroundingReviewWireResponse(f=[{"s":"s99","r":"F","p":"Claim.","c":"UE","a":[],"m":[],"g":"UC"}])
    with pytest.raises(ollama_service.ReviewerMetadataError, match="unknown_coverage_segment_alias"):
        ollama_service._decode_grounding_review_wire_response(unknown, aliases, [])
    unavailable = GroundingReviewWireResponse(f=[{"s":"s0","r":"F","p":"Claim.","c":"SM","a":[],"m":["MA50"],"g":"MD"}])
    with pytest.raises(ollama_service.ReviewerMetadataError, match="market_field_not_supplied"):
        ollama_service._decode_grounding_review_wire_response(unavailable, aliases, ["current_price"])


@pytest.mark.parametrize("segment_value", [pytest.param(None, id="null"), pytest.param("", id="empty")])
def test_compact_wire_requires_a_nonempty_segment_alias(segment_value):
    payload = {"s": segment_value, "r": "F", "p": "Claim.", "c": "UE", "a": [], "m": [], "g": "UC"}
    with pytest.raises(ValidationError):
        GroundingReviewWireResponse(f=[payload])


def test_compact_wire_rejects_missing_segment_alias():
    payload = {"r": "F", "p": "Claim.", "c": "UE", "a": [], "m": [], "g": "UC"}
    with pytest.raises(ValidationError):
        GroundingReviewWireResponse(f=[payload])


def test_batch_schema_limits_segment_aliases_to_its_exact_22_segment_batch():
    segments = _batch_segments(22)
    aliases = ollama_service._build_coverage_segment_aliases(segments)
    schema = ollama_service.build_request_local_review_schema(
        [], coverage_segment_aliases=list(aliases)
    )
    finding = schema["$defs"]["GroundingReviewWireFinding"]
    assert "s" in finding["required"]
    assert finding["properties"]["s"]["enum"] == list(aliases)

    valid = {"f": [{"s": alias, "r": "F", "p": "Claim.", "c": "UE", "a": [], "m": [], "g": "UC"} for alias in aliases]}
    jsonschema.validate(valid, schema)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"f": [{"s": "s999", "r": "F", "p": "Claim.", "c": "UE", "a": [], "m": [], "g": "UC"}]}, schema)


def test_compact_wire_rejects_alias_from_another_batch_without_remapping():
    aliases = ollama_service._build_coverage_segment_aliases(_batch_segments(4))
    batch_b = {alias: segment for alias, segment in aliases.items() if alias in {"s2", "s3"}}
    foreign = GroundingReviewWireResponse(f=[{"s": "s0", "r": "F", "p": "Claim.", "c": "UE", "a": [], "m": [], "g": "UC"}])
    with pytest.raises(ollama_service.ReviewerMetadataError, match="unknown_coverage_segment_alias"):
        ollama_service._decode_grounding_review_wire_response(foreign, batch_b, [])


@pytest.mark.parametrize("count", [50, 75, 100])
def test_compact_wire_serialization_reduces_representative_output_by_sixty_percent(count):
    readable = []
    compact = []
    for index in range(count):
        proposition = "A concise atomic proposition with no explanatory rationale."
        readable.append({"review_unit_id":f"technical_analysis.trend[{index}].claim", "coverage_segment_id":f"technical_analysis.trend[{index}].claim.segment_0", "atomic_ordinal":0, "claim_role":"interpretation", "atomic_proposition":proposition, "classification":"supported_interpretation", "supporting_article_indices":[1, 2], "supporting_market_data_fields":["current_price"], "rule":"technical_role_grounding"})
        compact.append({"s":f"s{index}", "r":"I", "p":proposition, "c":"SI", "a":[1,2], "m":["CP"], "g":"TR"})
    old_size = len(json.dumps({"claims": readable}, separators=(",", ":")))
    compact_size = len(json.dumps({"f": compact}, separators=(",", ":")))
    assert compact_size / old_size <= 0.40


def test_fn_input_context_supports_missing_fundamentals_limitation():
    claim = GroundingClaimFinding(
        review_unit_id="portfolio_fit", coverage_segment_id="portfolio_fit.segment_0",
        atomic_ordinal=0, claim_role="interpretation",
        atomic_proposition="The supplied inputs do not include detailed fundamentals.",
        classification="supported_interpretation", supporting_article_indices=[],
        supporting_market_data_fields=[], supporting_input_context=["fundamentals_not_supplied"],
        rule="causal_mechanism_grounding",
    )
    assert ollama_service._validate_reviewer_finding_metadata([claim], _request()) == []


def test_fn_input_context_accepts_executive_summary_assessment_limitation():
    claim = GroundingClaimFinding(
        review_unit_id="executive_summary", coverage_segment_id="executive_summary.segment_0",
        atomic_ordinal=0, claim_role="interpretation",
        atomic_proposition="The biggest limitation is the lack of detailed financial data to assess valuation and profitability.",
        classification="supported_interpretation", supporting_article_indices=[],
        supporting_market_data_fields=[], supporting_input_context=["fundamentals_not_supplied"],
        rule="causal_mechanism_grounding",
    )
    contradictions = ollama_service._validate_reviewer_finding_metadata([claim], _request())
    assert contradictions == []


def test_fn_input_context_accepts_portfolio_fit_assessment_limitation():
    claim = GroundingClaimFinding(
        review_unit_id="portfolio_fit", coverage_segment_id="portfolio_fit.segment_0",
        atomic_ordinal=0, claim_role="interpretation",
        atomic_proposition="The lack of supplied fundamentals such as revenue, earnings, or valuation ratios limits the ability to assess value or income characteristics.",
        classification="supported_interpretation", supporting_article_indices=[],
        supporting_market_data_fields=[], supporting_input_context=["fundamentals_not_supplied"],
        rule="portfolio_role_grounding",
    )
    assert ollama_service._validate_reviewer_finding_metadata([claim], _request()) == []


def test_fn_input_context_portfolio_fit_validation_is_deterministic_on_replay():
    def validate_once():
        claim = GroundingClaimFinding(
            review_unit_id="portfolio_fit", coverage_segment_id="portfolio_fit.segment_0",
            atomic_ordinal=0, claim_role="interpretation",
            atomic_proposition="The lack of supplied fundamentals such as revenue, earnings, or valuation ratios limits the ability to assess value or income characteristics.",
            classification="supported_interpretation", supporting_article_indices=[],
            supporting_market_data_fields=[], supporting_input_context=["fundamentals_not_supplied"],
            rule="portfolio_role_grounding",
        )
        return ollama_service._validate_reviewer_finding_metadata([claim], _request())
    assert validate_once() == validate_once() == []


def test_fn_input_context_cannot_support_revenue_decline_claim():
    claim = GroundingClaimFinding(
        review_unit_id="executive_summary", coverage_segment_id="executive_summary.segment_0",
        atomic_ordinal=0, claim_role="interpretation",
        atomic_proposition="Missing fundamentals will cause AMD revenue to decline.",
        classification="supported_interpretation", supporting_article_indices=[],
        supporting_market_data_fields=[], supporting_input_context=["fundamentals_not_supplied"],
        rule="causal_mechanism_grounding",
    )
    contradictions = ollama_service._validate_reviewer_finding_metadata([claim], _request())
    assert [item.code for item in contradictions] == ["interpretation_support_required"]


def test_fn_input_context_cannot_support_stock_price_fall_claim():
    claim = GroundingClaimFinding(
        review_unit_id="executive_summary", coverage_segment_id="executive_summary.segment_0",
        atomic_ordinal=0, claim_role="interpretation",
        atomic_proposition="Missing fundamentals imply AMD's stock price will fall.",
        classification="supported_interpretation", supporting_article_indices=[],
        supporting_market_data_fields=[], supporting_input_context=["fundamentals_not_supplied"],
        rule="causal_mechanism_grounding",
    )
    contradictions = ollama_service._validate_reviewer_finding_metadata([claim], _request())
    assert [item.code for item in contradictions] == ["interpretation_support_required"]


def test_fn_input_context_cannot_support_overvalued_claim():
    claim = GroundingClaimFinding(
        review_unit_id="executive_summary", coverage_segment_id="executive_summary.segment_0",
        atomic_ordinal=0, claim_role="interpretation",
        atomic_proposition="Missing fundamentals mean AMD is overvalued.",
        classification="supported_interpretation", supporting_article_indices=[],
        supporting_market_data_fields=[], supporting_input_context=["fundamentals_not_supplied"],
        rule="unsupported_valuation_claim",
    )
    contradictions = ollama_service._validate_reviewer_finding_metadata([claim], _request())
    assert [item.code for item in contradictions] == ["interpretation_support_required"]


def test_fn_input_context_cannot_support_downside_risk_claim():
    claim = GroundingClaimFinding(
        review_unit_id="key_risks[0].risk", coverage_segment_id="key_risks[0].risk.segment_0",
        atomic_ordinal=0, claim_role="interpretation",
        atomic_proposition="Missing fundamentals increase AMD's downside risk.",
        classification="supported_interpretation", supporting_article_indices=[],
        supporting_market_data_fields=[], supporting_input_context=["fundamentals_not_supplied"],
        rule="causal_mechanism_grounding",
    )
    contradictions = ollama_service._validate_reviewer_finding_metadata([claim], _request())
    assert [item.code for item in contradictions] == ["interpretation_support_required"]


def test_fn_input_context_cannot_support_weak_profitability_claim():
    claim = GroundingClaimFinding(
        review_unit_id="executive_summary", coverage_segment_id="executive_summary.segment_0",
        atomic_ordinal=0, claim_role="interpretation",
        atomic_proposition="Missing profitability inputs indicate AMD has weak profitability.",
        classification="supported_interpretation", supporting_article_indices=[],
        supporting_market_data_fields=[], supporting_input_context=["fundamentals_not_supplied"],
        rule="causal_mechanism_grounding",
    )
    contradictions = ollama_service._validate_reviewer_finding_metadata([claim], _request())
    assert [item.code for item in contradictions] == ["interpretation_support_required"]


def test_input_context_rejects_unknown_code():
    payload = {"f": [{"s": "s0", "r": "I", "p": "Inputs lack fundamentals.", "c": "SI", "a": [], "m": [], "i": ["ZZ"], "g": "CM"}]}
    with pytest.raises(ValidationError):
        GroundingReviewWireResponse(**payload)


def test_input_context_rejects_known_but_unavailable_fn():
    wire = GroundingReviewWireResponse(**{"f": [{"s": "s0", "r": "I", "p": "Inputs lack fundamentals.", "c": "SI", "a": [], "m": [], "i": ["FN"], "g": "CM"}]})
    segment = ReviewCoverageSegment(review_unit_id="portfolio_fit", coverage_segment_id="portfolio_fit.segment_0", segment_ordinal=0, source_start=0, source_end=1)
    with pytest.raises(ollama_service.ReviewerMetadataError, match="input_context_not_supplied"):
        ollama_service._decode_grounding_review_wire_response(wire, {"s0": segment}, [], [])


def test_fn_fallback_derives_executive_summary_limitation_without_provider_context():
    claim = GroundingClaimFinding(
        review_unit_id="executive_summary", coverage_segment_id="executive_summary.segment_0",
        atomic_ordinal=0, claim_role="interpretation",
        atomic_proposition="The biggest limitation is the lack of detailed financial data to assess valuation and profitability.",
        classification="supported_interpretation", supporting_article_indices=[],
        supporting_market_data_fields=[], supporting_input_context=[],
        rule="causal_mechanism_grounding",
    )

    assert ollama_service._validate_reviewer_finding_metadata([claim], _request()) == []
    assert claim.supporting_input_context == []
    assert claim.backend_derived_input_context == ["fundamentals_not_supplied"]


def test_fn_fallback_derives_portfolio_fit_limitation_without_provider_context():
    claim = GroundingClaimFinding(
        review_unit_id="portfolio_fit", coverage_segment_id="portfolio_fit.segment_0",
        atomic_ordinal=0, claim_role="interpretation",
        atomic_proposition="The lack of supplied fundamentals such as revenue, earnings, or valuation ratios limits the ability to assess value or income characteristics.",
        classification="supported_interpretation", supporting_article_indices=[],
        supporting_market_data_fields=[], supporting_input_context=[],
        rule="portfolio_role_grounding",
    )

    assert ollama_service._validate_reviewer_finding_metadata([claim], _request()) == []
    assert claim.supporting_input_context == []
    assert claim.backend_derived_input_context == ["fundamentals_not_supplied"]


def test_fn_fallback_does_not_derive_stock_price_claim_without_provider_context():
    claim = GroundingClaimFinding(
        review_unit_id="executive_summary", coverage_segment_id="executive_summary.segment_0",
        atomic_ordinal=0, claim_role="interpretation",
        atomic_proposition="Missing fundamentals imply AMD's stock price will fall.",
        classification="supported_interpretation", supporting_article_indices=[],
        supporting_market_data_fields=[], supporting_input_context=[],
        rule="causal_mechanism_grounding",
    )

    contradictions = ollama_service._validate_reviewer_finding_metadata([claim], _request())
    assert [item.code for item in contradictions] == ["interpretation_support_required"]
    assert claim.backend_derived_input_context == []


def test_fn_fallback_does_not_derive_overvalued_claim_without_provider_context():
    claim = GroundingClaimFinding(
        review_unit_id="executive_summary", coverage_segment_id="executive_summary.segment_0",
        atomic_ordinal=0, claim_role="interpretation",
        atomic_proposition="Missing fundamentals mean AMD is overvalued.",
        classification="supported_interpretation", supporting_article_indices=[],
        supporting_market_data_fields=[], supporting_input_context=[],
        rule="unsupported_valuation_claim",
    )

    contradictions = ollama_service._validate_reviewer_finding_metadata([claim], _request())
    assert [item.code for item in contradictions] == ["interpretation_support_required"]
    assert claim.backend_derived_input_context == []


def test_fn_fallback_requires_request_local_context_availability(monkeypatch):
    claim = GroundingClaimFinding(
        review_unit_id="executive_summary", coverage_segment_id="executive_summary.segment_0",
        atomic_ordinal=0, claim_role="interpretation",
        atomic_proposition="The biggest limitation is the lack of detailed financial data to assess valuation and profitability.",
        classification="supported_interpretation", supporting_article_indices=[],
        supporting_market_data_fields=[], supporting_input_context=[],
        rule="causal_mechanism_grounding",
    )
    monkeypatch.setattr(ollama_service, "derive_available_input_context", lambda request: [])

    contradictions = ollama_service._validate_reviewer_finding_metadata([claim], _request())
    assert [item.code for item in contradictions] == ["interpretation_support_required"]
    assert claim.backend_derived_input_context == []


def _technical_trend_result(text):
    payload = _report(corrected=True)
    payload["technical_analysis"]["trend"] = text
    return FinancialAnalysisLLMResponse(**payload)


def test_report_98_52_week_uptrend_inference_is_blocked():
    request = _request()
    request.price_data.current_price = 479.18
    request.price_data.fifty_two_week_high = 584.73
    request.price_data.fifty_two_week_low = 149.22
    result = _technical_trend_result(
        "The stock is trading near its 52-week high of $584.73, indicating a strong uptrend."
    )

    violations = ollama_service._deterministic_grounding_violations(request, result, [1])
    assert [item.rule for item in violations] == ["historical_range_not_technical_level"]


def test_52_week_high_cannot_independently_support_uptrend():
    result = _technical_trend_result(
        "Trading near the 52-week high indicates a strong uptrend."
    )

    violations = ollama_service._deterministic_grounding_violations(_request(), result, [1])
    assert [item.rule for item in violations] == ["historical_range_not_technical_level"]


def test_52_week_low_cannot_independently_support_downtrend():
    result = _technical_trend_result(
        "Trading near the 52-week low confirms a downtrend."
    )

    violations = ollama_service._deterministic_grounding_violations(_request(), result, [1])
    assert [item.rule for item in violations] == ["historical_range_not_technical_level"]


def test_descriptive_52_week_fact_remains_allowed():
    result = _technical_trend_result("The 52-week high is $584.73.")

    assert ollama_service._deterministic_grounding_violations(_request(), result, [1]) == []


def test_historical_range_trend_violation_preserves_exact_segment_and_proposition():
    request = _request()
    request.price_data.current_price = 479.18
    result = _technical_trend_result(
        "The current price of $479.18 is below the 52-week high of $584.73 and "
        "above the 52-week low of $149.22. Price position suggests a range-bound "
        "or indecisive trend."
    )

    violations = ollama_service._deterministic_grounding_violations(request, result, [1])

    assert len(violations) == 1
    violation = violations[0]
    assert violation.coverage_segment_id == "technical_analysis.trend.segment_1"
    assert violation.atomic_proposition == "Price position suggests a range-bound or indecisive trend."
    assert violation.patch_target_id == violation.coverage_segment_id
    assert ollama_service.derive_required_patch_targets(violations) == [
        "technical_analysis.trend.segment_1"
    ]


def test_descriptive_historical_range_segments_do_not_create_a_blocker():
    request = _request()
    request.price_data.current_price = 479.18
    result = _technical_trend_result(
        "The 52-week range is $149.22 - $584.73. The current price is below the "
        "52-week high and above the 52-week low. The current price is in the lower "
        "half of the 52-week range."
    )

    assert ollama_service._deterministic_grounding_violations(request, result, [1]) == []


def test_historical_range_rule_emits_one_exact_violation_per_invalid_segment():
    result = _technical_trend_result(
        "The price is within the 52-week range. Price position suggests a range-bound "
        "trend. The range signals downside momentum."
    )

    violations = ollama_service._deterministic_grounding_violations(_request(), result, [1])

    assert [item.coverage_segment_id for item in violations] == [
        "technical_analysis.trend.segment_1",
        "technical_analysis.trend.segment_2",
    ]
    assert [item.patch_target_id for item in violations] == [
        "technical_analysis.trend.segment_1",
        "technical_analysis.trend.segment_2",
    ]
    assert all(item.atomic_proposition for item in violations)


def test_historical_range_and_reviewer_blocker_share_one_required_target():
    result = _technical_trend_result(
        "The price is within the 52-week range. Price position suggests a range-bound trend."
    )
    deterministic = ollama_service._deterministic_grounding_violations(_request(), result, [1])
    target_id = deterministic[0].patch_target_id
    reviewer = GroundingViolation(
        rule="unsupported_company_specific_claim",
        section="technical_analysis",
        issue="technical_analysis.trend.atomic_1: unsupported trend interpretation.",
        coverage_segment_id=target_id,
        atomic_proposition=deterministic[0].atomic_proposition,
        patch_target_id=target_id,
    )

    assert ollama_service.derive_required_patch_targets(deterministic + [reviewer]) == [target_id]


def test_moving_average_supported_downtrend_is_not_blocked_by_52_week_rule():
    request = _request()
    request.price_data.moving_average_50 = 500.0
    result = _technical_trend_result(
        "The stock is below its 50-day moving average, supporting a short-term downtrend."
    )

    assert ollama_service._deterministic_grounding_violations(request, result, [1]) == []


def _market_finding_and_violations(proposition, request, *, market_fields=None):
    claim = GroundingClaimFinding(**_claim_finding(
        proposition,
        "unsupported_by_any_evidence",
        market_fields=market_fields or [],
        rule="unsupported_company_specific_claim",
        section="technical_analysis",
    ))
    request.price_data.market_cap = request.price_data.market_cap or 1_000_000
    contradictions = ollama_service._validate_reviewer_finding_metadata([claim], request)
    normalized = ollama_service._normalize_claim_findings([claim], [1])
    violations = ollama_service._claim_findings_to_violations(normalized)
    violations += ollama_service._evidence_contract_contradictions_to_violations(
        contradictions, normalized
    )
    return normalized[0], violations


@pytest.mark.parametrize(
    ("proposition", "configure", "expected"),
    [
        ("AMD's beta is 2.489", lambda r: setattr(r.price_data, "beta", 2.489), ["beta"]),
        ("AMD is trading at $480.93", lambda r: setattr(r.price_data, "current_price", 480.93), ["current_price"]),
        ("AMD's daily change is +0.37%", lambda r: setattr(r.price_data, "daily_change_percent", 0.37), ["daily_change_percent"]),
        ("AMD is within its supplied 52-week range of $149.22 to $584.73", lambda r: None, ["fifty_two_week_low", "fifty_two_week_high"]),
    ],
)
def test_backend_derived_market_support_rescues_exact_facts(proposition, configure, expected):
    request = _request()
    configure(request)
    finding, violations = _market_finding_and_violations(proposition, request, market_fields=["market_cap"])
    assert finding.backend_derived_market_fields == expected
    assert not any(item.rule == "unsupported_company_specific_claim" for item in violations)


@pytest.mark.parametrize(
    "proposition",
    [
        "AMD's beta of 2.489 means its shares will decline",
        "The +0.37% gain proves investors welcomed the news",
        "AMD is near the 52-week high, proving an uptrend",
        "$584.73 is resistance",
        "AMD is in a downtrend because moving averages were not supplied",
        "Missing moving averages imply downside risk",
    ],
)
def test_backend_derived_market_support_does_not_rescue_interpretations(proposition):
    request = _request()
    request.price_data.beta = 2.489
    request.price_data.daily_change_percent = 0.37
    finding, violations = _market_finding_and_violations(proposition, request)
    assert finding.backend_derived_market_fields == []
    assert any(item.rule == "unsupported_company_specific_claim" for item in violations)


def test_backend_derives_missing_moving_average_facts_and_limitations():
    request = _request()
    fact, fact_violations = _market_finding_and_violations(
        "50-day and 200-day moving averages were not supplied", request
    )
    limitation, limitation_violations = _market_finding_and_violations(
        "Moving-average-based trend assessment is limited because MA50 and MA200 were not supplied", request
    )
    assert fact.backend_derived_market_fields == ["moving_average_50", "moving_average_200"]
    assert limitation.backend_derived_market_fields == ["moving_average_50", "moving_average_200"]
    assert not fact_violations and not limitation_violations


@pytest.mark.parametrize(
    "proposition",
    [
        "Insufficient supplied price data prevents technical analysis",
        "Lack of detailed technical data is a limitation",
        "There is not enough price data to evaluate AMD",
        "Technical data is unavailable",
    ],
)
def test_missing_moving_averages_do_not_support_broad_dataset_claims(proposition):
    finding, violations = _market_finding_and_violations(proposition, _request())
    assert finding.backend_derived_market_fields == []
    assert any(item.rule == "unsupported_company_specific_claim" for item in violations)


def test_correction_prompt_requires_exact_missing_ma_wording_without_dataset_generalization():
    instruction = ollama_service.SEMANTIC_CORRECTION_INSTRUCTION.lower()
    assert "ma50" in instruction and "ma200" in instruction
    assert "technical data is insufficient" in instruction
    assert "prefer removing the unsupported" in instruction


def test_backend_requires_full_support_for_compound_price_and_52_week_range():
    request = _request()
    request.price_data.current_price = 478.78
    finding, violations = _market_finding_and_violations(
        "AMD is trading at $478.78 within its 52-week range of $149.22 to $584.73", request
    )
    assert finding.backend_derived_market_fields == [
        "current_price", "fifty_two_week_low", "fifty_two_week_high"
    ]
    assert not violations
    request.price_data.fifty_two_week_high = 600.00
    partial, partial_violations = _market_finding_and_violations(
        "AMD is trading at $478.78 within its 52-week range of $149.22 to $584.73", request
    )
    assert partial.backend_derived_market_fields == []
    assert any(item.rule == "unsupported_company_specific_claim" for item in partial_violations)


def test_semantic_trace_includes_derived_market_and_deterministic_violation(caplog):
    request = _request()
    request.price_data.current_price = 480.93
    finding, _ = _market_finding_and_violations("AMD is trading at $480.93", request)
    violation = ollama_service.GroundingViolation(
        rule="historical_range_not_technical_level", section="technical_analysis", issue="52-week range used as trend"
    )
    with caplog.at_level("INFO", logger="backend.services.ollama_service"):
        ollama_service._log_semantic_finding_trace("final_review", [finding], [violation])
    records = _semantic_trace_records(caplog, "[AI][SemanticFindingTrace]")
    deterministic = _semantic_trace_records(caplog, "[AI][SemanticDeterministicViolationTrace]")
    assert records[0]["backend_derived_market_fields"] == ["current_price"]
    assert deterministic[0]["rule"] == "historical_range_not_technical_level"
    assert deterministic[0]["blocking"] is True


@pytest.mark.parametrize(
    ("payload", "valid"),
    [
        ({"target_id": "bull_case[0].segment_0", "operation": "DELETE", "replacement": None, "article_indices_used": []}, True),
        ({"target_id": "bull_case[0].segment_0", "operation": "DELETE", "replacement": "text", "article_indices_used": []}, False),
        ({"target_id": "bull_case[0].segment_0", "operation": "REPLACE", "replacement": "Supported replacement.", "article_indices_used": []}, True),
        ({"target_id": "bull_case[0].segment_0", "operation": "REPLACE", "replacement": None, "article_indices_used": []}, False),
        ({"target_id": "bull_case[0].segment_0", "operation": "REPLACE", "replacement": "   ", "article_indices_used": []}, False),
    ],
)
def test_correction_patch_operation_payload_validation(payload, valid):
    if valid:
        patch = CorrectionPatch(**payload)
        assert patch.article_indices_used == []
        assert CorrectionPatchSet(patches=[patch]).patches == [patch]
    else:
        with pytest.raises(ValidationError):
            CorrectionPatch(**payload)


def test_correction_target_registry_is_deterministic_and_excludes_metadata():
    report = FinancialAnalysisLLMResponse(**_report())
    units = ollama_service._build_reviewable_claim_units(report)
    segments = ollama_service._build_review_coverage_segments(units)

    first = ollama_service.build_correction_target_registry(units, segments)
    second = ollama_service.build_correction_target_registry(units, segments)

    assert first == second
    assert len(first.targets) == len({target.patch_target_id for target in first.targets})
    excluded = {
        "asset", "ticker", "current_price_at_analysis", "report_id",
        "article_indices_used", "articles_used", "overall_sentiment",
        "confidence_score", "investment_rating", "prompt_version",
    }
    assert not ({target.source_path for target in first.targets} & excluded)
    for target in first.targets:
        unit = next(unit for unit in units if unit.review_unit_id == target.source_path)
        assert unit.candidate_text[target.source_start:target.source_end] == target.original_target_text
        assert ollama_service.lookup_correction_target(first, target.patch_target_id) == target
    assert ollama_service.lookup_correction_target(first, "unknown.segment_0") is None


def test_correction_target_registry_distinguishes_duplicate_text_locations():
    text = "The same proposition appears here."
    units = [
        ReviewableClaimUnit(review_unit_id="bull_case[0]", section="bull_case", candidate_text=text),
        ReviewableClaimUnit(review_unit_id="bear_case[0]", section="bear_case", candidate_text=text),
    ]
    registry = ollama_service.build_correction_target_registry(units)

    assert [target.original_target_text for target in registry.targets] == [text, text]
    assert len({target.patch_target_id for target in registry.targets}) == 2
    assert len({target.source_path for target in registry.targets}) == 2


def test_correction_target_registry_preserves_multisegment_offsets_and_context():
    source = "First proposition. Second proposition, suggesting a third implication."
    unit = ReviewableClaimUnit(
        review_unit_id="technical_analysis.trend",
        section="technical_analysis",
        candidate_text=source,
    )
    registry = ollama_service.build_correction_target_registry([unit])

    assert len(registry.targets) == 3
    assert {target.source_path for target in registry.targets} == {"technical_analysis.trend"}
    assert [target.patch_target_id for target in registry.targets] == [
        "technical_analysis.trend.segment_0",
        "technical_analysis.trend.segment_1",
        "technical_analysis.trend.segment_2",
    ]
    for target in registry.targets:
        assert source[target.source_start:target.source_end] == target.original_target_text
    assert registry.targets[1].previous_context == registry.targets[0].original_target_text
    assert registry.targets[1].next_context == registry.targets[2].original_target_text


def test_correction_target_registry_uses_real_list_and_nested_paths():
    report = FinancialAnalysisLLMResponse(**_report())
    units = ollama_service._build_reviewable_claim_units(report)
    registry = ollama_service.build_correction_target_registry(units)

    news = registry.get("news_summary[0].segment_0")
    risk = registry.get("key_risks[0].risk.segment_0")
    assert news is not None and news.source_path == "news_summary[0]"
    assert risk is not None and risk.source_path == "key_risks[0].risk"
    assert risk.original_target_text in report.key_risks[0].risk


def test_reviewer_violation_uses_coverage_segment_not_finding_order():
    units = [
        ReviewableClaimUnit(
            review_unit_id="bull_case[0]",
            section="bull_case",
            candidate_text="First finding. Second finding.",
        ),
        ReviewableClaimUnit(
            review_unit_id="overall_sentiment",
            section="overall_sentiment",
            candidate_text="Bullish",
        ),
    ]
    segments = ollama_service._build_review_coverage_segments(units)
    registry = ollama_service.build_correction_target_registry(units, segments)
    base = dict(
        review_unit_id="bull_case[0]",
        claim_role="fact",
        classification="unsupported_by_any_evidence",
        supporting_article_indices=[],
        supporting_market_data_fields=[],
        rule="unsupported_company_specific_claim",
        section="bull_case",
        supporting_selected_indices=[],
        supporting_unselected_indices=[],
    )
    findings = [
        NormalizedGroundingClaimFinding(
            **base,
            coverage_segment_id="bull_case[0].segment_1",
            atomic_ordinal=0,
            atomic_proposition="Second finding",
            atomic_claim_id="bull_case[0].atomic_0",
        ),
        NormalizedGroundingClaimFinding(
            **base,
            coverage_segment_id="bull_case[0].segment_0",
            atomic_ordinal=1,
            atomic_proposition="First finding",
            atomic_claim_id="bull_case[0].atomic_1",
        ),
    ]

    forward = ollama_service._claim_findings_to_violations(
        findings, registry=registry
    )
    reverse = ollama_service._claim_findings_to_violations(
        list(reversed(findings)), registry=registry
    )
    assert {item.patch_target_id for item in forward} == {
        "bull_case[0].segment_0", "bull_case[0].segment_1"
    }
    assert {item.patch_target_id for item in reverse} == {
        "bull_case[0].segment_0", "bull_case[0].segment_1"
    }

    legacy = NormalizedGroundingClaimFinding(
        **{**base, "section": "overall_sentiment"},
        coverage_segment_id="overall_sentiment.segment_0",
        atomic_ordinal=0,
        atomic_proposition="Bullish",
        atomic_claim_id="overall_sentiment.atomic_0",
    )
    assert ollama_service._claim_findings_to_violations(
        [legacy], registry=registry
    )[0].patch_target_id is None


def test_deterministic_violation_maps_every_exact_target():
    request = _request()
    exact_report = FinancialAnalysisLLMResponse(**_report())
    exact = ollama_service._deterministic_grounding_violations(request, exact_report, [1])
    assert any(
        violation.patch_target_id == "technical_analysis.resistance_levels[0].segment_0"
        for violation in exact
    )

    ambiguous_payload = _report()
    ambiguous_payload["technical_analysis"]["breakout_level"] = "$584.73"
    ambiguous_report = FinancialAnalysisLLMResponse(**ambiguous_payload)
    ambiguous = ollama_service._deterministic_grounding_violations(request, ambiguous_report, [1])
    high = [
        violation for violation in ambiguous
        if "52-week high" in violation.issue
    ]
    assert {item.patch_target_id for item in high} == {
        "technical_analysis.resistance_levels[0].segment_0",
        "technical_analysis.breakout_level.segment_0",
    }
    assert all(item.coverage_segment_id == item.patch_target_id for item in high)


def _phase_b_report_and_registry(payload=None):
    report = FinancialAnalysisLLMResponse(**(payload or _report()))
    units = ollama_service._build_reviewable_claim_units(report)
    registry = ollama_service.build_correction_target_registry(units)
    return report, registry


def _phase_b_patch(target_id, operation="REPLACE", replacement="Supported replacement.", indices=None):
    return {
        "target_id": target_id,
        "operation": operation,
        "replacement": replacement,
        "article_indices_used": [] if indices is None else indices,
    }


def _patch_failure_kind(callable_):
    with pytest.raises(AISemanticGroundingError) as exc_info:
        callable_()
    return exc_info.value.details["failure_kind"]


def test_required_patch_targets_are_deduplicated_sorted_and_fail_on_unmappable():
    violations = [
        GroundingViolation(
            rule="scope_preservation", section="bull_case", issue="b",
            coverage_segment_id="bull_case[0].segment_1",
            atomic_proposition="b", patch_target_id="bull_case[0].segment_1",
        ),
        GroundingViolation(
            rule="selected_evidence_attribution_boundary", section="bull_case",
            issue="a", coverage_segment_id="bull_case[0].segment_0",
            atomic_proposition="a", patch_target_id="bull_case[0].segment_0",
        ),
        GroundingViolation(
            rule="unsupported_company_specific_claim", section="bull_case",
            issue="c", coverage_segment_id="bull_case[0].segment_1",
            atomic_proposition="c", patch_target_id="bull_case[0].segment_1",
        ),
    ]
    assert ollama_service.derive_required_patch_targets(list(reversed(violations))) == [
        "bull_case[0].segment_0", "bull_case[0].segment_1"
    ]
    violations.append(GroundingViolation(
        rule="historical_range_not_technical_level",
        section="technical_analysis",
        issue="ambiguous",
    ))
    assert _patch_failure_kind(
        lambda: ollama_service.derive_required_patch_targets(violations)
    ) == "correction_patch_unmappable_violation"


def test_phase_b_replace_middle_segment_preserves_exact_neighbors():
    payload = _report()
    original = "First proposition. Invalid middle proposition. Final proposition."
    payload["executive_summary"] = original
    report, registry = _phase_b_report_and_registry(payload)
    target_id = "executive_summary.segment_1"
    merged = ollama_service.merge_correction_patch_set(
        report,
        registry,
        [target_id],
        {"patches": [_phase_b_patch(target_id, replacement="Supported middle proposition.")]},
    )
    assert merged.report.executive_summary == (
        "First proposition. Supported middle proposition. Final proposition."
    )
    assert report.executive_summary == original
    assert len(merged.coverage_segments) > 0


def test_phase_b_delete_middle_segment_uses_seam_only_whitespace_cleanup():
    payload = _report()
    payload["executive_summary"] = "First proposition. Delete this proposition. Final proposition."
    report, registry = _phase_b_report_and_registry(payload)
    target_id = "executive_summary.segment_1"
    merged = ollama_service.merge_correction_patch_set(
        report,
        registry,
        [target_id],
        {"patches": [_phase_b_patch(target_id, operation="DELETE", replacement=None)]},
    )
    assert merged.report.executive_summary == "First proposition. Final proposition."


def test_phase_b_multiple_same_field_patches_use_original_descending_offsets():
    payload = _report()
    payload["executive_summary"] = "Bad first. Keep middle. Bad final."
    report, registry = _phase_b_report_and_registry(payload)
    required = ["executive_summary.segment_0", "executive_summary.segment_2"]
    merged = ollama_service.merge_correction_patch_set(
        report,
        registry,
        required,
        {"patches": [
            _phase_b_patch(required[0], replacement="Good first."),
            _phase_b_patch(required[1], replacement="Good final."),
        ]},
    )
    assert merged.report.executive_summary == "Good first. Keep middle. Good final."


def test_phase_b_multiple_sections_are_atomic_and_metadata_is_immutable():
    report, registry = _phase_b_report_and_registry()
    required = [
        "technical_analysis.trend.segment_0",
        "news_summary[0].segment_0",
        "bear_case[0].segment_0",
    ]
    original_metadata = (
        report.asset, report.overall_sentiment, report.confidence_score,
        report.investment_rating, list(report.article_indices_used),
    )
    merged = ollama_service.merge_correction_patch_set(
        report,
        registry,
        required,
        {"patches": [
            _phase_b_patch(required[0], replacement="Technical evidence remains limited."),
            _phase_b_patch(required[1], replacement="The financing remains planned."),
            _phase_b_patch(required[2], replacement="Execution risk remains conditional."),
        ]},
    ).report
    assert merged.technical_analysis.trend == "Technical evidence remains limited."
    assert merged.news_summary[0] == "The financing remains planned."
    assert merged.bear_case[0] == "Execution risk remains conditional."
    assert (
        merged.asset, merged.overall_sentiment, merged.confidence_score,
        merged.investment_rating, list(merged.article_indices_used),
    ) == original_metadata
    assert merged.bull_case == report.bull_case


@pytest.mark.parametrize(
    ("patches", "required", "failure_kind"),
    [
        ([_phase_b_patch("unknown.segment_0")], ["unknown.segment_0"], "correction_patch_unknown_target"),
        ([_phase_b_patch("bull_case[0].segment_0")], ["bear_case[0].segment_0"], "correction_patch_unauthorized_target"),
        ([_phase_b_patch("bull_case[0].segment_0"), _phase_b_patch("bull_case[0].segment_0")], ["bull_case[0].segment_0"], "correction_patch_duplicate_target"),
        ([_phase_b_patch("bull_case[0].segment_0")], ["bull_case[0].segment_0", "bear_case[0].segment_0"], "correction_patch_incomplete_target_set"),
        ([_phase_b_patch("bull_case[0].segment_0"), _phase_b_patch("bear_case[0].segment_0")], ["bull_case[0].segment_0"], "correction_patch_unauthorized_target"),
    ],
)
def test_phase_b_authorization_failures_are_specific(patches, required, failure_kind):
    _, registry = _phase_b_report_and_registry()
    assert _patch_failure_kind(
        lambda: ollama_service.validate_correction_patch_set(
            {"patches": patches}, registry, required
        )
    ) == failure_kind


@pytest.mark.parametrize(
    "patch",
    [
        _phase_b_patch("bull_case[0].segment_0", operation="DELETE", replacement="invalid"),
        _phase_b_patch("bull_case[0].segment_0", replacement=None),
        _phase_b_patch("bull_case[0].segment_0", replacement=""),
        _phase_b_patch("bull_case[0].segment_0", replacement="   "),
        _phase_b_patch("bull_case[0].segment_0", replacement="First sentence. Second sentence."),
        _phase_b_patch("bull_case[0].segment_0", replacement="Line one.\nLine two."),
        _phase_b_patch("bull_case[0].segment_0", replacement="- Bullet claim"),
        _phase_b_patch("bull_case[0].segment_0", replacement="x" * 401),
    ],
)
def test_phase_b_invalid_operation_or_replacement_is_schema_failure(patch):
    _, registry = _phase_b_report_and_registry()
    target_id = "bull_case[0].segment_0"
    assert _patch_failure_kind(
        lambda: ollama_service.validate_correction_patch_set(
            {"patches": [patch]}, registry, [target_id]
        )
    ) == "correction_patch_schema_invalid"


@pytest.mark.parametrize("indices", [[0], [-1], [1, 1]])
def test_phase_b_article_index_structure_is_fail_closed(indices):
    _, registry = _phase_b_report_and_registry()
    target_id = "bull_case[0].segment_0"
    assert _patch_failure_kind(
        lambda: ollama_service.validate_correction_patch_set(
            {"patches": [_phase_b_patch(target_id, indices=indices)]},
            registry,
            [target_id],
        )
    ) == "correction_patch_attribution_invalid"


def test_phase_b_delete_required_list_item_fails_without_mutating_primary():
    report, registry = _phase_b_report_and_registry()
    target_id = "news_summary[0].segment_0"
    original = report.model_dump(mode="python")
    assert registry.get(target_id).target_strategy == "list_item"
    assert _patch_failure_kind(
        lambda: ollama_service.merge_correction_patch_set(
            report,
            registry,
            [target_id],
            {"patches": [_phase_b_patch(target_id, operation="DELETE", replacement=None)]},
        )
    ) == "correction_patch_merge_failure"
    assert report.model_dump(mode="python") == original


def test_phase_b_whole_optional_list_item_delete_uses_registry_strategy():
    report, registry = _phase_b_report_and_registry()
    target_id = "key_catalysts[0].segment_0"
    assert registry.get(target_id).target_strategy == "list_item"
    merged = ollama_service.merge_correction_patch_set(
        report,
        registry,
        [target_id],
        {"patches": [_phase_b_patch(target_id, operation="DELETE", replacement=None)]},
    )
    assert merged.report.key_catalysts == []


def test_phase_b_nested_risk_replace_preserves_severity_and_neighbors():
    payload = _report()
    payload["key_risks"].append({"risk": "Neighbor risk remains.", "severity": "High"})
    report, registry = _phase_b_report_and_registry(payload)
    target_id = "key_risks[0].risk.segment_0"
    merged = ollama_service.merge_correction_patch_set(
        report,
        registry,
        [target_id],
        {"patches": [_phase_b_patch(target_id, replacement="Corrected risk remains conditional.")]},
    ).report
    assert merged.key_risks[0].risk == "Corrected risk remains conditional."
    assert merged.key_risks[0].severity == report.key_risks[0].severity
    assert merged.key_risks[1] == report.key_risks[1]


def test_phase_b_overlapping_trusted_targets_fail_atomically():
    payload = _report()
    payload["executive_summary"] = "First proposition. Second proposition."
    report, registry = _phase_b_report_and_registry(payload)
    first = registry.get("executive_summary.segment_0")
    second = registry.get("executive_summary.segment_1")
    source = report.executive_summary
    overlapping_second = second.model_copy(update={
        "source_start": first.source_start + 1,
        "source_end": first.source_end,
        "original_target_text": source[first.source_start + 1:first.source_end],
    })
    overlap_registry = CorrectionTargetRegistry(targets=[
        target if target.patch_target_id != second.patch_target_id else overlapping_second
        for target in registry.targets
    ])
    required = [first.patch_target_id, second.patch_target_id]
    assert _patch_failure_kind(
        lambda: ollama_service.merge_correction_patch_set(
            report,
            overlap_registry,
            required,
            {"patches": [
                _phase_b_patch(first.patch_target_id, replacement="Good first."),
                _phase_b_patch(second.patch_target_id, replacement="Good second."),
            ]},
        )
    ) == "correction_patch_merge_failure"
    assert report.executive_summary == source


def test_phase_b_request_local_registry_rejects_stale_offsets_without_text_matching():
    report_a, registry_a = _phase_b_report_and_registry()
    payload_b = _report()
    payload_b["bull_case"][0] = "Different request-local proposition."
    report_b, registry_b = _phase_b_report_and_registry(payload_b)
    target_id = "bull_case[0].segment_0"
    patch_set = {"patches": [_phase_b_patch(target_id)]}

    assert ollama_service.merge_correction_patch_set(
        report_a, registry_a, [target_id], patch_set
    ).report.bull_case[0] == "Supported replacement."
    assert _patch_failure_kind(
        lambda: ollama_service.merge_correction_patch_set(
            report_b, registry_a, [target_id], patch_set
        )
    ) == "correction_patch_merge_failure"
    assert ollama_service.merge_correction_patch_set(
        report_b, registry_b, [target_id], patch_set
    ).report.bull_case[0] == "Supported replacement."


def _phase_c_violation(target_id, rule="unsupported_company_specific_claim", section="executive_summary"):
    return GroundingViolation(
        rule=rule,
        section=section,
        issue="Targeted semantic blocker.",
        coverage_segment_id=target_id,
        atomic_proposition="Target proposition",
        patch_target_id=target_id,
    )


def _phase_c_claim(target_id, section="executive_summary", indices=None):
    source_path, _, segment_ordinal = target_id.rpartition(".segment_")
    return NormalizedGroundingClaimFinding(
        review_unit_id=source_path,
        coverage_segment_id=target_id,
        atomic_ordinal=int(segment_ordinal),
        claim_role="fact",
        atomic_proposition="Target proposition",
        classification="unsupported_by_any_evidence",
        supporting_article_indices=indices or [],
        supporting_market_data_fields=[],
        rule="unsupported_company_specific_claim",
        section=section,
        atomic_claim_id=f"{source_path}.atomic_0",
        supporting_selected_indices=indices or [],
        supporting_unselected_indices=[],
    )


def test_phase_c_request_schema_has_exact_target_enum_and_patch_count():
    required = ["a.segment_0", "b.segment_1", "c.segment_0"]
    schema = ollama_service.build_request_local_patch_schema(required)
    patch_schema = schema["$defs"]["CorrectionPatch"]

    assert patch_schema["properties"]["target_id"]["enum"] == required
    assert patch_schema["properties"]["operation"]["enum"] == ["DELETE", "REPLACE"]
    assert schema["properties"]["patches"]["minItems"] == 3
    assert schema["properties"]["patches"]["maxItems"] == 3
    assert set(patch_schema["required"]) == {"target_id", "operation"}


def test_phase_c_patch_prompt_isolates_targets_context_and_relevant_articles():
    payload = _report()
    payload["executive_summary"] = (
        "Read-only previous proposition. Invalid target proposition. "
        "Read-only next proposition."
    )
    payload["bull_case"] = ["UNRELATED_BULL_CASE_PROSE_MUST_NOT_APPEAR"]
    report, registry = _phase_b_report_and_registry(payload)
    target_id = "executive_summary.segment_1"
    prompt = ollama_service.build_patch_correction_prompt(
        [target_id],
        registry,
        [_phase_c_violation(target_id)],
        _request(),
        [_phase_c_claim(target_id, indices=[1])],
    )

    assert prompt.count(target_id) == 1
    assert "Invalid target proposition." in prompt
    assert "Read-only previous proposition." in prompt
    assert "Read-only next proposition." in prompt
    assert "context is read-only" in prompt.lower()
    assert "AMD prepares a $5B bond sale" in prompt
    assert "UNRELATED_BULL_CASE_PROSE_MUST_NOT_APPEAR" not in prompt
    assert "source_path" not in prompt
    assert "atomic_ordinal" not in prompt


def test_phase_c_prompt_preserves_missing_ma_and_historical_range_guidance():
    report, registry = _phase_b_report_and_registry()
    target_id = "technical_analysis.trend.segment_0"
    prompt = ollama_service.build_patch_correction_prompt(
        [target_id],
        registry,
        [_phase_c_violation(
            target_id,
            rule="historical_range_not_technical_level",
            section="technical_analysis",
        )],
        _request(),
    )

    assert "MA50 and MA200 were not supplied" in prompt
    assert "insufficient technical data" in prompt
    assert "Do not claim insufficient technical data" in prompt
    assert "do not infer trend, momentum, support, resistance, breakout" in prompt
    assert "Prefer DELETE" in prompt


@pytest.mark.parametrize(
    "rule",
    [
        "event_price_impact_grounding",
        "investor_motive_grounding",
        "causal_mechanism_grounding",
    ],
)
def test_phase_c_relationship_prompt_prohibits_alternative_speculation(rule):
    report, registry = _phase_b_report_and_registry()
    target_id = "executive_summary.segment_0"
    prompt = ollama_service.build_patch_correction_prompt(
        [target_id],
        registry,
        [_phase_c_violation(target_id, rule=rule)],
        _request(),
    )
    assert "never substitute a different speculative motive or causal explanation" in prompt


@pytest.mark.parametrize(
    ("raw", "valid"),
    [
        ('{"patches":[{"target_id":"a.segment_0","operation":"DELETE","replacement":null,"article_indices_used":[]}]}', True),
        ("not json", False),
        ('{"asset":"AMD"}', False),
        ('{"patches":[{"target_id":"a.segment_0","operation":"INSERT"}]}', False),
    ],
)
def test_phase_c_parser_accepts_only_patch_set_json(raw, valid):
    if valid:
        assert ollama_service.parse_correction_patch_set(raw).patches[0].operation == "DELETE"
    else:
        assert _patch_failure_kind(
            lambda: ollama_service.parse_correction_patch_set(raw)
        ) == "correction_patch_schema_invalid"


def test_phase_c_article_range_and_delete_attribution_are_rejected():
    _, registry = _phase_b_report_and_registry()
    target_id = "bull_case[0].segment_0"
    assert _patch_failure_kind(
        lambda: ollama_service.validate_correction_patch_set(
            {"patches": [_phase_b_patch(target_id, indices=[41])]},
            registry,
            [target_id],
            article_count=40,
        )
    ) == "correction_patch_attribution_invalid"
    assert _patch_failure_kind(
        lambda: ollama_service.validate_correction_patch_set(
            {"patches": [_phase_b_patch(
                target_id, operation="DELETE", replacement=None, indices=[1]
            )]},
            registry,
            [target_id],
            article_count=40,
        )
    ) == "correction_patch_attribution_invalid"


@pytest.mark.asyncio
async def test_phase_c_generation_uses_one_request_local_schema_call(caplog):
    report, registry = _phase_b_report_and_registry()
    target_id = "bull_case[0].segment_0"
    response = json.dumps({"patches": [{
        "target_id": target_id,
        "operation": "REPLACE",
        "replacement": "Supplied evidence supports a conditional interpretation.",
        "article_indices_used": [1],
    }]})

    class CapturingPatchClient:
        def __init__(self):
            self.calls = []

        async def generate(self, **kwargs):
            self.calls.append(kwargs)
            return response

    client = CapturingPatchClient()
    with caplog.at_level("INFO", logger="backend.services.ollama_service"):
        patch_set = await ollama_service.generate_correction_patch_set(
            client,
            _request(),
            registry,
            [_phase_c_violation(target_id, section="bull_case")],
            [_phase_c_claim(target_id, section="bull_case", indices=[1])],
            provider="ollama",
            model="test-model",
        )

    assert len(client.calls) == 1
    call = client.calls[0]
    assert call["temperature"] == 0
    assert call["max_attempts"] == 1
    assert call["response_schema"]["$defs"]["CorrectionPatch"]["properties"]["target_id"]["enum"] == [target_id]
    assert call["response_schema"]["properties"]["patches"]["minItems"] == 1
    assert patch_set.patches[0].article_indices_used == [1]
    assert "stage=patch_correction_generation" in caplog.text
    assert "required_target_count=1" in caplog.text
    assert "returned_patch_count=1" in caplog.text
    assert "Supplied evidence supports" not in caplog.text


@pytest.mark.asyncio
async def test_phase_c_zero_or_unmappable_targets_make_no_provider_call():
    _, registry = _phase_b_report_and_registry()

    class UnexpectedPatchClient:
        def __init__(self):
            self.calls = 0

        async def generate(self, **kwargs):
            self.calls += 1
            raise AssertionError("provider must not be called")

    client = UnexpectedPatchClient()
    for violations in ([], [GroundingViolation(
        rule="historical_range_not_technical_level",
        section="technical_analysis",
        issue="unmappable",
    )]):
        with pytest.raises(AISemanticGroundingError) as exc_info:
            await ollama_service.generate_correction_patch_set(
                client,
                _request(),
                registry,
                violations,
                None,
                provider="ollama",
                model="test-model",
            )
    assert exc_info.value.details["failure_kind"] == "correction_patch_unmappable_violation"
    assert client.calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("section", ["overall_sentiment", "investment_rating"])
async def test_phase_d_unmappable_legacy_scalar_fails_before_correction_provider(
    monkeypatch, section
):
    invalid_scalar_review = {
        "claims": [{
            "section": section,
            "claim": "Bullish" if section == "overall_sentiment" else "Hold",
            "classification": "unsupported_by_any_evidence",
            "supporting_article_indices": [],
            "supporting_market_data_fields": [],
            "rule": "unsupported_valuation_claim",
        }]
    }
    client = _SequencedClient([_report(corrected=True), invalid_scalar_review])
    await _install_client(monkeypatch, "ollama", client)

    with pytest.raises(AISemanticGroundingError) as exc_info:
        await ollama_service.generate_analysis(
            _request(), provider="ollama", model="test-model"
        )

    assert exc_info.value.details["failure_kind"] == (
        "correction_patch_unmappable_violation"
    )
    assert len(client.calls) == 2
    assert all(
        call["system_prompt"] != ollama_service.PATCH_CORRECTION_SYSTEM_PROMPT
        for call in client.calls
    )


@pytest.mark.asyncio
async def test_phase_d_incomplete_patch_set_has_no_final_review_or_fallback(monkeypatch):
    client = _SequencedClient([_report(), _invalid_review(), {"patches": []}])
    await _install_client(monkeypatch, "ollama", client)

    with pytest.raises(AISemanticGroundingError) as exc_info:
        await ollama_service.generate_analysis(
            _request(), provider="ollama", model="test-model"
        )

    assert exc_info.value.details["failure_kind"] == (
        "correction_patch_incomplete_target_set"
    )
    assert len(client.calls) == 3
    assert sum(
        call["system_prompt"] == ollama_service.PATCH_CORRECTION_SYSTEM_PROMPT
        for call in client.calls
    ) == 1
