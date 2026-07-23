"""Validated structured outputs for hierarchical intelligence."""

from pydantic import BaseModel, Field


class ArticleIntelligenceOutput(BaseModel):
    summary: str = Field(min_length=1)
    sentiment: str
    confidence: int = Field(ge=1, le=10)
    importance_score: int = Field(ge=1, le=10)
    market_impact: str
    short_term_outlook: str
    long_term_outlook: str
    themes: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    catalysts: list[str] = Field(default_factory=list)
    opportunities: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    macro_factors: list[str] = Field(default_factory=list)
    financial_metrics: list[dict] = Field(default_factory=list)
    regulatory_impacts: list[str] = Field(default_factory=list)
    technology_impacts: list[str] = Field(default_factory=list)
    competitive_impacts: list[str] = Field(default_factory=list)
    key_takeaways: list[str] = Field(default_factory=list)


class DailyTickerIntelligenceOutput(BaseModel):
    overall_sentiment: str
    confidence: int = Field(ge=1, le=10)
    executive_summary: str = Field(min_length=1)
    positive_developments: list[str] = Field(default_factory=list)
    negative_developments: list[str] = Field(default_factory=list)
    catalysts: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    themes: list[str] = Field(default_factory=list)
    competitive_landscape: list[str] = Field(default_factory=list)
    industry_impact: list[str] = Field(default_factory=list)
    macro_impact: list[str] = Field(default_factory=list)
    short_term_outlook: str
    long_term_outlook: str
    important_articles: list[dict] = Field(default_factory=list)
    market_narrative: str
    final_conclusion: str