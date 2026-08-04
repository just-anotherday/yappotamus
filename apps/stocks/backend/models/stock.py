from pydantic import BaseModel, Field
from typing import Any, Dict, List, Literal, Optional


class StockResponse(BaseModel):
    ticker: str
    symbol: str
    company_name: str
    current_price: float
    previous_close: float
    change: float
    change_percent: float
    market_cap: float
    fifty_two_week_high: float
    fifty_two_week_low: float
    volume: int
    pe_ratio: Optional[float] = None
    currency: str = "USD"
    data_source: Literal["fh", "yf"] = "fh"
    yf_enriched_fields: List[str] = []
    security_type: Optional[str] = None


class ETFData(BaseModel):
    """ETF-specific fund data."""
    fund_family: Optional[str] = None
    expense_ratio: Optional[float] = None
    net_assets: Optional[int] = None
    inception_date: Optional[str] = None
    dividend_yield: Optional[float] = None
    distribution_frequency: Optional[str] = None
    index_tracked: Optional[str] = None
    category: Optional[str] = None
    holdings_count: Optional[int] = None
    top_holdings: Optional[List[Dict[str, Any]]] = None
    sector_allocation: Optional[List[Dict[str, Any]]] = None
    geographic_allocation: Optional[List[Dict[str, Any]]] = None


class WatchlistItem(BaseModel):
    """Analyst-grade watchlist item with price, share structure, and risk data."""

    # Identity
    ticker: str
    symbol: str
    company_name: str
    sector: Optional[str] = None
    industry: Optional[str] = None
    long_business_summary: Optional[str] = None
    website: Optional[str] = None
    full_time_employees: Optional[int] = None
    average_analyst_rating: Optional[str] = None
    forward_pe: Optional[float] = None
    ceo_name: Optional[str] = None
    exchange: Optional[str] = None

    # Security Classification
    security_type: Optional[str] = "UNKNOWN"

    # Price Data
    current_price: Optional[float] = None
    open_price: Optional[float] = None
    previous_close: Optional[float] = None
    day_low: Optional[float] = None
    day_high: Optional[float] = None
    fifty_two_week_high: Optional[float] = None
    fifty_two_week_low: Optional[float] = None
    change: Optional[float] = None
    change_percent: Optional[float] = None
    quote_timestamp: Optional[str] = None
    previous_close_timestamp: Optional[str] = None
    quote_provider: Optional[str] = None
    market_session: Optional[str] = None
    market_cap: Optional[float] = None
    fund_assets: Optional[float] = None
    etf_market_cap: Optional[float] = None
    market_size_value: Optional[float] = None
    market_size_type: Optional[Literal["market_cap", "fund_assets", "etf_market_cap"]] = None
    market_size_currency: Optional[str] = None
    market_size_source: Optional[str] = None
    market_size_fallback_used: bool = False
    market_size_status: Literal["available", "unsupported", "provider_failed", "rate_limited", "unauthorized", "stale_cache"] = "available"

    # Share Structure (STOCK only)
    shares_outstanding: Optional[int] = None
    float_shares: Optional[int] = None
    insider_percent: Optional[float] = None
    institution_percent: Optional[float] = None

    # Risk & Demand Signals (computed heuristic, 0-10 scale)
    beta: Optional[float] = None
    short_percent_of_float: Optional[float] = None
    shares_short: Optional[int] = None
    overall_risk: Optional[float] = None

    # Analyst Targets (STOCK only)
    target_mean_price: Optional[float] = None
    target_median_price: Optional[float] = None
    target_high_price: Optional[float] = None
    target_low_price: Optional[float] = None
    recommendation_key: Optional[str] = None
    number_of_analysts: Optional[int] = None

    # ETF-Specific Data (optional)
    etf_data: Optional[ETFData] = None

    # After-Hours / Post-Market Data (populated at 4:01 PM ET via yfinance)
    post_market_price: Optional[float] = None
    post_market_change: Optional[float] = None
    post_market_change_percent: Optional[float] = None

    # Data Source Tag (fh = Finnhub, yf = yfinance fallback)
    data_source: Literal["fh", "yf"] = "fh"
    # Fields that were filled by yfinance enrichment (when primary is Finnhub)
    yf_enriched_fields: List[str] = []
    data_status: Literal["complete", "partial", "stale", "unavailable"] = "partial"
    fundamentals_status: Optional[Literal["complete", "partial", "stale", "unavailable"]] = None
    fundamentals_as_of: Optional[str] = None
    fundamentals_is_stale: bool = False
    provider_status: Dict[str, Literal["healthy", "cooldown", "degraded", "unavailable"]] = Field(default_factory=dict)
    missing_fields: List[str] = Field(default_factory=list)
