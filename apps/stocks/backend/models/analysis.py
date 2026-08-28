"""
Pydantic models for the AI Financial Analysis endpoint.

Defines the request payload (news articles + price data) and the structured
JSON response schema that Ollama must conform to.
"""

import math
import re
from typing import Any, List, Literal, Optional

from typing_extensions import Annotated
from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StrictInt,
    field_validator,
    model_validator,
)


def _coerce_to_str(v: Any) -> str:
    """Coerce numeric values to strings for technical analysis price levels."""
    if isinstance(v, str):
        return v
    return str(v)


StrOrNum = Annotated[str, BeforeValidator(_coerce_to_str)]


# ==============================================================================
# REQUEST MODELS
# ==============================================================================

class PriceDataRequest(BaseModel):
    """Market price information for the analyzed asset."""

    current_price: float
    daily_change_percent: float = Field(description="Daily change %")
    weekly_change_percent: Optional[float] = None
    monthly_change_percent: Optional[float] = None
    fifty_two_week_high: Optional[float] = None
    fifty_two_week_low: Optional[float] = None
    trading_volume: int
    beta: Optional[float] = None
    support_level: Optional[float] = None
    resistance_level: Optional[float] = None
    moving_average_50: Optional[float] = None
    moving_average_200: Optional[float] = None
    market_cap: Optional[float] = None


class NewsArticleRequest(BaseModel):
    """Single news article to include in the analysis prompt."""

    title: str
    summary: Optional[str] = None
    published_at: Optional[str] = None
    source: Optional[str] = None
    url: Optional[str] = None


class FinancialAnalysisRequest(BaseModel):
    """Full request payload for generating a financial analysis report."""

    ticker: str = Field(description="Stock ticker symbol")
    company_name: Optional[str] = None
    news_articles: List[NewsArticleRequest] = Field(
        description="List of news articles to analyze",
    )
    price_data: PriceDataRequest
    analysis_date: Optional[str] = Field(
        default=None,
        description="Reference date for the analysis (ISO format)",
    )


# ==============================================================================
# RESPONSE MODELS (matches JSON schema from spec)
# ==============================================================================

class ArticleReference(BaseModel):
    """Reference to a news article used in the analysis."""

    title: str = Field(description="Article title")
    url: Optional[str] = Field(default=None, description="Link to the full article")
    published_at: Optional[str] = Field(default=None, description="ISO publish date")


class KeyRisk(BaseModel):
    """Individual risk factor with severity level."""

    risk: str = Field(description="Description of the risk")
    severity: Literal["Low", "Medium", "High"] = Field(description="Risk severity level")


class TechnicalAnalysisResponse(BaseModel):
    """Technical analysis section of the report."""

    trend: str
    support_levels: List[StrOrNum] = Field(default_factory=list)
    resistance_levels: List[StrOrNum] = Field(default_factory=list)
    breakout_level: StrOrNum = ""
    breakdown_level: StrOrNum = ""


class FinancialAnalysisLLMTechnicalResponse(TechnicalAnalysisResponse):
    """Internal generated-technical contract requiring every nested output key."""

    trend: str = Field(min_length=1)
    support_levels: List[StrOrNum]
    resistance_levels: List[StrOrNum]
    breakout_level: StrOrNum = Field(min_length=1)
    breakdown_level: StrOrNum = Field(min_length=1)

    @field_validator("support_levels", "resistance_levels", mode="before")
    @classmethod
    def reject_malformed_level_lists(cls, value: Any) -> Any:
        """Require arrays containing only finite numeric or nonempty string levels."""
        if not isinstance(value, list):
            raise ValueError("technical levels must be returned as an array")
        for item in value:
            if isinstance(item, bool) or not isinstance(item, (str, int, float)):
                raise ValueError("technical levels must be strings or finite numbers")
            if isinstance(item, str) and not item.strip():
                raise ValueError("technical levels must not contain empty strings")
            if isinstance(item, float) and not math.isfinite(item):
                raise ValueError("technical levels must contain finite numbers")
        return value

    @field_validator("breakout_level", "breakdown_level", mode="before")
    @classmethod
    def normalize_or_reject_malformed_scalar_levels(cls, value: Any) -> Any:
        """Normalize unavailable scalar levels and reject non-scalar inventions."""
        if value is None:
            return "N/A"
        if isinstance(value, bool) or not isinstance(value, (str, int, float)):
            raise ValueError("technical level must be a string or finite number")
        if isinstance(value, str) and not value.strip():
            raise ValueError("technical level must not be empty")
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("technical level must be finite")
        return value


class OutlookResponse(BaseModel):
    """Multi-timeframe outlook."""

    short_term: str = Field(description="1-7 days outlook (Bullish/Neutral/Bearish + explanation)")
    medium_term: str = Field(description="1-3 months outlook")
    long_term: str = Field(description="6-12 months outlook")


class FinancialAnalysisLLMOutlookResponse(OutlookResponse):
    """Internal generated-outlook contract that rejects copied horizon labels."""

    @field_validator("short_term", "medium_term", "long_term")
    @classmethod
    def reject_horizon_placeholders(cls, value: str) -> str:
        """Reject labels copied from the schema in place of actual analysis."""
        normalized = value.strip()
        if normalized.lower() in {"1-7d", "1-3m", "6-12m"}:
            raise ValueError("outlook must contain analysis, not only a time-horizon label")
        if not re.match(
            r"^(Bullish|Neutral|Bearish)(?:\s+|:\s*|[-—]\s*).+\S$",
            normalized,
        ):
            raise ValueError(
                "outlook must start with Bullish, Neutral, or Bearish and include an explanation"
            )
        return value


class FinancialAnalysisResponse(BaseModel):
    """Complete financial analysis report returned by the LLM."""

    asset: str
    overall_sentiment: Literal["Very Bullish", "Bullish", "Neutral", "Bearish", "Very Bearish"]
    confidence_score: int = Field(ge=0, le=100)
    investment_rating: Optional[Literal["Strong Buy", "Buy", "Hold", "Sell", "Strong Sell"]] = Field(
        default=None,
        description="Actionable stance derived from the evidence, distinct from sentiment",
    )
    articles_used: List[ArticleReference] = Field(default_factory=list, description="Articles included in the analysis")
    news_summary: List[str] = Field(default_factory=list)
    key_catalysts: List[str] = Field(default_factory=list)
    key_risks: List[KeyRisk] = Field(default_factory=list)
    bull_case: List[str] = Field(default_factory=list, description="Evidence-based reasons the stock could outperform")
    bear_case: List[str] = Field(default_factory=list, description="Evidence-based reasons the stock could decline")
    market_reaction_analysis: Optional[str] = None
    technical_analysis: Optional[TechnicalAnalysisResponse] = None
    outlook: Optional[OutlookResponse] = None
    actionable_insights: List[str] = Field(default_factory=list)
    portfolio_fit: Optional[str] = Field(
        default=None,
        description="Which investor profiles this fits and what portfolio role it could play",
    )
    executive_summary: Optional[str] = None
    current_price_at_analysis: Optional[float] = Field(
        default=None,
        description="Current market price when the analysis was generated",
    )
    report_id: Optional[int] = Field(default=None, description="Saved report ID in database")


class FinancialAnalysisLLMResponse(FinancialAnalysisResponse):
    """Internal LLM parse contract with transient article attribution indexes."""

    investment_rating: Literal["Strong Buy", "Buy", "Hold", "Sell", "Strong Sell"]
    news_summary: List[str] = Field(min_length=1)
    key_catalysts: List[str]
    key_risks: List[KeyRisk]
    bull_case: List[str] = Field(min_length=1)
    bear_case: List[str] = Field(min_length=1)
    market_reaction_analysis: str = Field(min_length=1)
    technical_analysis: FinancialAnalysisLLMTechnicalResponse
    outlook: FinancialAnalysisLLMOutlookResponse
    actionable_insights: List[str] = Field(min_length=1)
    portfolio_fit: str = Field(min_length=1)
    executive_summary: str = Field(min_length=1)
    article_indices_used: List[int] = Field(
        exclude=True,
        description="One-based indexes of input articles materially used by the analysis",
    )

    @field_validator("article_indices_used", mode="before")
    @classmethod
    def ignore_malformed_article_indices(cls, value: Any) -> List[int]:
        """Keep only genuine integer indexes; range checks happen during mapping."""
        if not isinstance(value, list):
            return []
        return [
            item
            for item in value
            if isinstance(item, int) and not isinstance(item, bool)
        ]


GroundingRule = Literal[
    "historical_range_not_technical_level",
    "prospective_event_treated_as_completed",
    "unsupported_numeric_precision",
    "unsupported_valuation_claim",
    "fact_scenario_confusion",
    "unsupported_financing_mechanics",
    "unsupported_acquisition_mechanics",
    "unsupported_company_specific_claim",
    "selected_evidence_attribution_boundary",
    "scope_preservation",
    "event_status_preservation",
    "causal_mechanism_grounding",
    "technical_role_grounding",
    "fact_interpretation_separation",
    "investor_motive_grounding",
    "event_price_impact_grounding",
    "portfolio_role_grounding",
]

GroundingSection = Literal[
    "overall_sentiment",
    "confidence_score",
    "investment_rating",
    "news_summary",
    "key_catalysts",
    "key_risks",
    "bull_case",
    "bear_case",
    "market_reaction_analysis",
    "technical_analysis",
    "outlook",
    "actionable_insights",
    "portfolio_fit",
    "executive_summary",
    "multiple_sections",
]


class GroundingViolation(BaseModel):
    """Internal-only description of a scoped semantic-grounding failure."""

    model_config = ConfigDict(extra="forbid")

    rule: GroundingRule
    section: GroundingSection
    issue: str = Field(min_length=1, max_length=500)
    # Deterministic rules preserve the same source identity that reviewer
    # findings carry. Target enrichment remains registry-owned.
    coverage_segment_id: Optional[str] = Field(default=None, min_length=1, max_length=240)
    atomic_proposition: Optional[str] = Field(default=None, min_length=1, max_length=300)
    patch_target_id: Optional[str] = Field(default=None, min_length=1, max_length=240)


CorrectionPatchOperation = Literal["DELETE", "REPLACE"]


class CorrectionPatch(BaseModel):
    """Internal-only proposition correction requested from a provider."""

    model_config = ConfigDict(extra="forbid")

    target_id: str = Field(min_length=1, max_length=240)
    operation: CorrectionPatchOperation
    replacement: Optional[str] = None
    article_indices_used: List[StrictInt] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_operation_payload(self) -> "CorrectionPatch":
        if self.operation == "DELETE" and self.replacement is not None:
            raise ValueError("DELETE patches must not include replacement text")
        if self.operation == "REPLACE" and (
            self.replacement is None or not self.replacement.strip()
        ):
            raise ValueError("REPLACE patches require non-empty replacement text")
        return self


class CorrectionPatchSet(BaseModel):
    """Internal-only correction response; authorization is validated later."""

    model_config = ConfigDict(extra="forbid")

    patches: List[CorrectionPatch]


class CorrectionPatchTarget(BaseModel):
    """Backend-owned request-local anchor for one patchable text segment."""

    model_config = ConfigDict(extra="forbid")

    patch_target_id: str = Field(min_length=1, max_length=240)
    section: GroundingSection
    source_path: str = Field(min_length=1, max_length=200)
    source_start: StrictInt = Field(ge=0)
    source_end: StrictInt = Field(gt=0)
    original_target_text: str = Field(min_length=1)
    target_strategy: Literal["text_segment", "list_item"] = "text_segment"
    previous_context: Optional[str] = None
    next_context: Optional[str] = None
    applicable_violation_rules: List[GroundingRule] = Field(default_factory=list)


class CorrectionTargetRegistry(BaseModel):
    """Ephemeral lookup table for targets belonging to one report cycle."""

    model_config = ConfigDict(extra="forbid")

    targets: List[CorrectionPatchTarget]

    @model_validator(mode="after")
    def require_unique_target_ids(self) -> "CorrectionTargetRegistry":
        target_ids = [target.patch_target_id for target in self.targets]
        if len(target_ids) != len(set(target_ids)):
            raise ValueError("correction patch target IDs must be unique")
        return self

    def get(self, patch_target_id: str) -> Optional[CorrectionPatchTarget]:
        return next(
            (
                target
                for target in self.targets
                if target.patch_target_id == patch_target_id
            ),
            None,
        )


ClaimEvidenceClassification = Literal[
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

# The role answers what a proposition asserts.  It deliberately remains
# independent from ClaimEvidenceClassification, which answers how it is
# grounded (or why it fails grounding).
GroundingClaimRole = Literal[
    "fact",
    "interpretation",
    "investment_implication",
]

ClaimEvidenceRule = Literal[
    "historical_range_not_technical_level",
    "prospective_event_treated_as_completed",
    "unsupported_numeric_precision",
    "unsupported_valuation_claim",
    "fact_scenario_confusion",
    "unsupported_financing_mechanics",
    "unsupported_acquisition_mechanics",
    "unsupported_company_specific_claim",
    "scope_preservation",
    "event_status_preservation",
    "causal_mechanism_grounding",
    "technical_role_grounding",
    "fact_interpretation_separation",
    "investor_motive_grounding",
    "event_price_impact_grounding",
    "portfolio_role_grounding",
    "structured_market_data_support",
    "selected_article_support",
]

StructuredMarketDataField = Literal[
    "current_price",
    "daily_change_percent",
    "weekly_change_percent",
    "monthly_change_percent",
    "fifty_two_week_high",
    "fifty_two_week_low",
    "trading_volume",
    "beta",
    "support_level",
    "resistance_level",
    "moving_average_50",
    "moving_average_200",
    "market_cap",
]


class ReviewableClaimUnit(BaseModel):
    """Backend-owned, deterministic text container for semantic review only."""

    model_config = ConfigDict(extra="forbid")

    review_unit_id: str = Field(min_length=1, max_length=200)
    section: GroundingSection
    candidate_text: str = Field(min_length=1)


class ReviewCoverageSegment(BaseModel):
    """Backend-owned source anchor within one reviewable claim unit."""

    model_config = ConfigDict(extra="forbid")

    review_unit_id: str = Field(min_length=1, max_length=200)
    coverage_segment_id: str = Field(min_length=1, max_length=240)
    segment_ordinal: StrictInt = Field(ge=0)
    source_start: StrictInt = Field(ge=0)
    source_end: StrictInt = Field(gt=0)


class GroundingClaimFinding(BaseModel):
    """One reviewer-decomposed atomic proposition and its asserted evidence."""

    model_config = ConfigDict(extra="forbid")

    # review_unit_id is narrowed to the candidate's exact unit set in the
    # request-local JSON schema.  The backend derives section and claim ID.
    review_unit_id: str = Field(min_length=1, max_length=200)
    coverage_segment_id: str = Field(min_length=1, max_length=240)
    atomic_ordinal: StrictInt = Field(ge=0)
    claim_role: GroundingClaimRole
    atomic_proposition: str = Field(min_length=1, max_length=300)
    classification: ClaimEvidenceClassification
    supporting_article_indices: List[StrictInt]
    supporting_market_data_fields: List[StructuredMarketDataField]
    # Provider-declared request-context evidence. This remains distinct from
    # backend-derived context recorded below.
    supporting_input_context: List[Literal["fundamentals_not_supplied"]] = Field(default_factory=list)
    backend_derived_input_context: List[Literal["fundamentals_not_supplied"]] = Field(default_factory=list)
    backend_derived_market_fields: List[StructuredMarketDataField] = Field(default_factory=list)
    rule: ClaimEvidenceRule

    @model_validator(mode="before")
    @classmethod
    def reject_legacy_claim_identity_at_provider_boundary(cls, value: Any) -> Any:
        """Keep old persisted/test fixtures parseable; provider schema exposes no legacy fields.

        The runtime reviewer path still rejects these synthetic IDs because they
        are not in its request-local review-unit enum.
        """
        if not isinstance(value, dict):
            return value
        if "review_unit_id" in value and "coverage_segment_id" not in value:
            # Compatibility for local legacy fixtures only. Runtime provider
            # schema still requires the field and narrows it to backend IDs.
            value["coverage_segment_id"] = f"{value['review_unit_id']}.segment_0"
            return value
        if "review_unit_id" in value:
            return value
        section = value.pop("section", "legacy")
        proposition = value.pop("claim", "")
        value.update({
            "review_unit_id": f"_legacy_{section}",
            "coverage_segment_id": f"_legacy_{section}.segment_0",
            "atomic_ordinal": 0,
            "claim_role": "fact",
            "atomic_proposition": proposition,
        })
        return value


class GroundingReviewResult(BaseModel):
    """Strict compact contract returned by the semantic grounding reviewer."""

    model_config = ConfigDict(extra="forbid")

    claims: List[GroundingClaimFinding] = Field(min_length=1)


# Compact models are intentionally provider-boundary only.  The semantic
# enforcement pipeline decodes these values into GroundingClaimFinding before
# applying its existing readable, fail-closed validation.
GroundingReviewWireRole = Literal["F", "I", "P"]
GroundingReviewWireClassification = Literal[
    "DS", "SM", "SI", "CS", "UE", "SC", "ES", "UM", "TM"
]
GroundingReviewWireRule = Literal[
    "HR", "PE", "NP", "UV", "FC", "FM", "AM", "UC", "SP", "ES",
    "CM", "TR", "FI", "IM", "EI", "PR", "MD", "AS",
]
GroundingReviewWireMarketField = Literal[
    "CP", "DC", "WC", "MC", "52H", "52L", "TV", "B", "SL", "RL",
    "MA50", "MA200", "CAP",
]
GroundingReviewWireInputContext = Literal["FN"]


class GroundingReviewWireFinding(BaseModel):
    """Compact provider response; never persisted or exposed publicly."""

    model_config = ConfigDict(extra="forbid")

    s: str = Field(min_length=2, max_length=16)
    r: GroundingReviewWireRole
    p: str = Field(min_length=1, max_length=120)
    c: GroundingReviewWireClassification
    a: List[StrictInt]
    m: List[GroundingReviewWireMarketField]
    i: List[GroundingReviewWireInputContext] = Field(default_factory=list)
    g: GroundingReviewWireRule

    @field_validator("p")
    @classmethod
    def proposition_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("atomic proposition must not be blank")
        return value


class GroundingReviewWireResponse(BaseModel):
    """Compact root object used by both Ollama and OpenAI reviewer calls."""

    model_config = ConfigDict(extra="forbid")

    f: List[GroundingReviewWireFinding] = Field(min_length=1)


class NormalizedGroundingClaimFinding(GroundingClaimFinding):
    """Backend-normalized finding with deterministic citation partitioning."""

    section: GroundingSection
    atomic_claim_id: str = Field(min_length=1, max_length=240)
    supporting_selected_indices: List[StrictInt]
    supporting_unselected_indices: List[StrictInt]


class GroundingEnforcementResult(BaseModel):
    """Backend-owned effective semantic review result."""

    model_config = ConfigDict(extra="forbid")

    valid: bool
    claims: List[NormalizedGroundingClaimFinding] = Field(min_length=1)
    violations: List[GroundingViolation]


# ==============================================================================
# MODEL MANAGEMENT (provider-aware)
# ==============================================================================

class ModelInfo(BaseModel):
    """Information about an available model."""

    name: str
    size: int = 0
    modified_at: Optional[str] = None


# Kept for backward compatibility
OllamaModelInfo = ModelInfo


class ProviderInfo(BaseModel):
    """Information about an available AI provider."""

    id: str  # "ollama", "openai", etc.
    name: str  # Display name, e.g. "Ollama", "OpenAI"
    available: bool
    models: List[ModelInfo] = Field(default_factory=list)


class ProviderConfigResponse(BaseModel):
    """Unified provider-aware configuration status."""

    providers: List[ProviderInfo] = Field(default_factory=list)
    default_provider: str = "ollama"
    default_model: str = ""


# Backward-compat alias
class OllamaConfigResponse(BaseModel):
    """Current Ollama configuration status (legacy)."""

    ollama_url: str
    default_model: str
    available_models: List[ModelInfo] = Field(default_factory=list)
    connected: bool = False
