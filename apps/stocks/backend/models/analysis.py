"""
Pydantic models for the AI Financial Analysis endpoint.

Defines the request payload (news articles + price data) and the structured
JSON response schema that Ollama must conform to.
"""

from typing import Any, List, Literal, Optional

from typing_extensions import Annotated
from pydantic import BaseModel, BeforeValidator, Field


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
    fifty_two_week_high: float
    fifty_two_week_low: float
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
    support_levels: List[StrOrNum] = []
    resistance_levels: List[StrOrNum] = []
    breakout_level: StrOrNum = ""
    breakdown_level: StrOrNum = ""


class OutlookResponse(BaseModel):
    """Multi-timeframe outlook."""

    short_term: str = Field(description="1-7 days outlook (Bullish/Neutral/Bearish + explanation)")
    medium_term: str = Field(description="1-3 months outlook")
    long_term: str = Field(description="6-12 months outlook")


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
    news_summary: List[str] = []
    key_catalysts: List[str] = []
    key_risks: List[KeyRisk] = []
    bull_case: List[str] = Field(default_factory=list, description="Evidence-based reasons the stock could outperform")
    bear_case: List[str] = Field(default_factory=list, description="Evidence-based reasons the stock could decline")
    market_reaction_analysis: Optional[str] = None
    technical_analysis: Optional[TechnicalAnalysisResponse] = None
    outlook: Optional[OutlookResponse] = None
    actionable_insights: List[str] = []
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
    models: List[ModelInfo] = []


class ProviderConfigResponse(BaseModel):
    """Unified provider-aware configuration status."""

    providers: List[ProviderInfo] = []
    default_provider: str = "ollama"
    default_model: str = ""


# Backward-compat alias
class OllamaConfigResponse(BaseModel):
    """Current Ollama configuration status (legacy)."""

    ollama_url: str
    default_model: str
    available_models: List[ModelInfo] = []
    connected: bool = False
