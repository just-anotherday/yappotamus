// ==============================================================================
// TYPES / INTERFACES
// ==============================================================================

export type DataSource = "fh" | "yf";

export type SecurityType = "STOCK" | "ETF" | "INDEX" | "CRYPTO" | "ADR" | "UNKNOWN";

export interface StockData {
  ticker: string;
  symbol: string;
  company_name: string;
  current_price: number;
  previous_close: number;
  change: number;
  change_percent: number;
  market_cap: number;
  fifty_two_week_high: number;
  fifty_two_week_low: number;
  volume: number;
  pe_ratio: number | null;
  currency: string;
  data_source?: DataSource;
  yf_enriched_fields?: string[];
  security_type?: SecurityType;
}

export interface ETFData {
  fund_family?: string | null;
  expense_ratio?: number | null;
  net_assets?: number | null;             // AUM
  inception_date?: string | null;
  dividend_yield?: number | null;
  distribution_frequency?: string | null;
  index_tracked?: string | null;
  category?: string | null;
  holdings_count?: number | null;
  top_holdings?: Array<{ name: string; ticker: string; weight: number }> | null;
  sector_allocation?: Array<{ sector: string; weight: number }> | null;
  geographic_allocation?: Array<{ region: string; weight: number }> | null;
}

export interface WatchlistItem {
  // Identity
  ticker: string;
  symbol: string;
  company_name: string;
  ceo_name?: string | null;
  exchange?: string | null;
  sector?: string | null;
  industry?: string | null;
  long_business_summary?: string | null;
  website?: string | null;
  full_time_employees?: number | null;
  average_analyst_rating?: string | null;
  forward_pe?: number | null;

  // Security Classification
  security_type?: SecurityType;

  // Price Data
  current_price: number;
  open_price: number;
  previous_close: number;
  day_low: number;
  day_high: number;
  fifty_two_week_high: number;
  fifty_two_week_low: number;
  change: number;
  change_percent: number;
  market_cap: number;

  // Share Structure (STOCK only)
  shares_outstanding?: number;
  float_shares?: number;
  insider_percent?: number;
  institution_percent?: number;

  // Risk & Demand Signals (computed heuristic, 0-10 scale)
  beta: number;
  short_percent_of_float?: number;
  shares_short?: number;
  overall_risk: number;

  // Analyst Targets (STOCK only)
  target_mean_price?: number | null;
  target_median_price?: number | null;
  target_high_price?: number | null;
  target_low_price?: number | null;
  recommendation_key: string;
  number_of_analysts?: number;

  // ETF-Specific Data (optional)
  etf_data?: ETFData;

  // After-Hours Price (from yfinance, only during after-hours trading)
  post_market_price?: number | null;
  post_market_change?: number | null;
  post_market_change_percent?: number | null;

  // Data Source Tag (fh = Finnhub, yf = yfinance fallback)
  data_source?: DataSource;
  // Fields filled by yfinance enrichment (when primary is Finnhub)
  yf_enriched_fields?: string[];
}

export interface LiveQuote {
  ticker: string;
  price: number | null;
  change: number | null;
  change_percent: number | null;
  volume: number;
}

export interface StockNews {
  title: string;
  summary: string;
  url: string;
  provider: string;
  published: string;
  thumbnail?: string;
}

/** News article persisted in PostgreSQL (news_articles table) */
export interface NewsArticle {
  id: number;
  finnhub_id?: string | null;
  ticker: string | null;
  title: string | null;
  summary: string | null;
  provider_name: string | null;  // Original publisher (Yahoo Finance, CNBC, Benzinga, etc.)
  data_source?: string | null;   // 'fh' | 'yf' - which data source fetched this article
  author?: string | null;        // Article author (from metadata or parsed from summary)
  pub_date: string | null;       // ISO timestamp from backend
  article_url: string | null;
  thumbnail_url: string | null;
  imported_at: string | null;
}

// ==============================================================================
// CONFIG INTERFACE (fetched from backend /api/watchlist/config)
// ==============================================================================

export interface WatchlistConfig {
  default_tickers: string[];
  max_watchlist_size: number;
  version: number;
}

// ==============================================================================
// CONSTANTS
// ==============================================================================

// ==============================================================================
// API ERROR TYPES (TD-FE-005 fix)
// ==============================================================================

/** Standardized API error response shape */
export interface ApiError {
  detail: string;
  status_code?: number;
}

/** Error returned from stock lookup endpoints when ticker is invalid or data unavailable */
export interface StockError extends ApiError {
  ticker: string;
}

// ==============================================================================
// PAGINATION TYPES (TD-FE-003 fix)
// ==============================================================================

/** Pagination metadata for any paginated response */
export interface PaginationMeta {
  page: number;
  total_pages: number;
  total_items: number;
  first_page_size: number;
  subsequent_page_size: number;
}

/** Generic paginated response wrapper */
export interface PaginatedResponse<T> {
  items: T[];
  pagination: PaginationMeta;
}

// ==============================================================================
// LOADING STATE TYPES (TD-FE-005 fix)
// ==============================================================================

export type LoadingState = 'idle' | 'loading' | 'success' | 'error';

/** Hook return shape for async data fetching */
export interface AsyncDataState<T> {
  data: T[];
  loading: boolean;
  error: string | null;
  refetch: () => Promise<void>;
}

// ==============================================================================
// CONSTANTS
// ==============================================================================

// Environment-variable-based API configuration for production deployment
export const API_BASE = process.env.NEXT_PUBLIC_API_BASE || 'http://localhost:8000';
export const WS_URL = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8000/ws';

// ==============================================================================
// AI RESEARCH PROFILE (for Bull/Bear case generation)
// ==============================================================================

export interface TickerResearchProfile {
  ticker: string;
  securityType: SecurityType;

  fundamentals: Record<string, any>;
  valuation: Record<string, any>;
  ownership: Record<string, any>;
  analystData: Record<string, any>;
  technicals: Record<string, any>;

  etfData?: Record<string, any>;
  cryptoData?: Record<string, any>;

  news: Array<{
    title: string;
    summary: string;
    url: string;
    author: string;
    published: string;
    sentiment?: 'bullish' | 'bearish' | 'neutral';
  }>;

  bullFactors: string[];
  bearFactors: string[];
}

// ==============================================================================
// FINANCIAL ANALYSIS (Ollama AI-powered analysis)
// ==============================================================================

export interface PriceDataRequest {
  current_price: number;
  daily_change_percent: number;
  weekly_change_percent?: number | null;
  monthly_change_percent?: number | null;
  fifty_two_week_high: number;
  fifty_two_week_low: number;
  trading_volume: number;
  beta?: number | null;
  support_level?: number | null;
  resistance_level?: number | null;
  moving_average_50?: number | null;
  moving_average_200?: number | null;
  market_cap?: number | null;
}

export interface NewsArticleRequest {
  title: string;
  summary?: string | null;
  published_at?: string | null;
  source?: string | null;
  url?: string | null;
}

export interface FinancialAnalysisRequestPayload {
  ticker: string;
  company_name?: string | null;
  news_articles: NewsArticleRequest[];
  price_data: PriceDataRequest;
  analysis_date?: string | null;
}

export interface AnalyzeTickerRequestBody {
  ticker: string;
  max_articles?: number;
  days_back?: number;
  model?: string | null;
  article_ids?: number[] | null;
}

export interface KeyRisk {
  risk: string;
  severity: "Low" | "Medium" | "High";
}

export interface TechnicalAnalysisData {
  trend: string;
  support_levels: string[];
  resistance_levels: string[];
  breakout_level: string;
  breakdown_level: string;
}

export interface OutlookData {
  short_term: string;
  medium_term: string;
  long_term: string;
}

export interface ArticleReference {
  title: string;
  url?: string | null;
  published_at?: string | null;
}

export interface FinancialAnalysisReport {
  asset: string;
  overall_sentiment: "Very Bullish" | "Bullish" | "Neutral" | "Bearish" | "Very Bearish";
  confidence_score: number;
  articles_used: ArticleReference[];
  news_summary: string[];
  key_catalysts: string[];
  key_risks: KeyRisk[];
  market_reaction_analysis: string;
  technical_analysis: TechnicalAnalysisData;
  outlook: OutlookData;
  actionable_insights: string[];
  executive_summary: string;
  current_price_at_analysis?: number | null;
}

export interface OllamaModelInfo {
  name: string;
  size: number;
  modified_at?: string | null;
}

export interface OllamaConfigStatus {
  ollama_url: string;
  default_model: string;
  available_models: OllamaModelInfo[];
  connected: boolean;
}

// ==============================================================================
// ANALYSIS REPORT TYPES (saved reports in database)
// ==============================================================================

export interface ReportSummary {
  id: number;
  report_number: number; // Consecutive rank (1=newest when sorted desc)
  ticker: string;
  overall_sentiment: string;
  confidence_score: number;
  articles_count: number;
  current_price_at_analysis: number | null;
  model_used: string;
  created_at: string; // ISO timestamp
}

export interface ReportPaginationResponse {
  items: ReportSummary[];
  total: number;
  page: number;
  limit: number;
  has_more: boolean;
}

export interface ReportDetail {
  id: number;
  ticker: string;
  report_data: FinancialAnalysisReport;
  articles_count: number;
  days_back: number;
  model_used: string;
  prompt_version: string;
  current_price_at_analysis: number | null;
  created_at: string; // ISO timestamp
}

// ==============================================================================
// CACHED INTELLIGENCE (event-driven pipeline output)
// ==============================================================================

/** Response from GET /api/analysis/reports/company/{ticker} */
export interface CachedCompanyReport {
  id: number;
  ticker: string;
  asset_id: number;
  report_data: FinancialAnalysisReport;
  overall_sentiment: string;
  confidence_score: number;
  articles_count: number;
  model_used: string;
  prompt_version: string;
  price_snapshot: number | null;
  last_updated: string | null; // ISO timestamp
}

/** Response from GET /api/analysis/reports/queue/status */
export interface AIQueueStatus {
  pending_processing_count: number;
  breakdown: Record<string, number | string>;
}

/** Response from GET /api/analysis/reports/market/latest */
export interface CachedMarketReport {
  id: number;
  report_date: string | null;
  report_data: Record<string, any>;
  overall_sentiment: string;
  risk_level: string;
  confidence_score: number | null;
  model_used: string;
  last_generated: string | null;
}

// ==============================================================================
// PIPELINE STATUS (comprehensive pipeline monitor)
// ==============================================================================

export interface PipelineStatus {
  news: {
    total_articles: number;
    articles_today: number;
    tickers_with_news: number;
    recent_articles?: Array<{ id: number; title: string; ticker: string | null; pub_date: string | null; article_url: string | null }>;
    ticker_status?: Array<{ ticker: string; articles_today: number; has_report: boolean }>;
  };
  company_reports: {
    total_reports: number;
    tickers_covered: number;
  };
  sector_reports: {
    total_reports: number;
    sectors_covered: number;
  };
  market_reports: {
    total_reports: number;
  };
  job_queue: {
    pending: number;
    processing: number;
    completed: number;
    failed: number;
    total: number;
    by_type: Record<string, Record<string, number>>;
    processing_tasks?: Array<{ job_type: string; target_id: number; started_at: string | null }>;
  };
  watchlist: {
    tickers: number;
  };
  assets: {
    total: number;
  };
}

// ==============================================================================
// RISK DASHBOARD — Market Tracker + Risk Signal Types
// ==============================================================================

/** Single OHLCV price point returned from /api/markets/{ticker}/prices */
export interface OhlcvPoint {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

/** Summary stats block inside market tracker detail */
export interface MarketSummaryStats {
  historical_volatility_1y: number;
  momentum_20d_pct: number;
  max_drawdown_pct: number;
  var_95_daily_pct: number;
}

/** Risk signal computed by backend/lib/risk_engine.py */
export interface MarketRiskSignal {
  composite_score: number;         // 0–10
  buy_signal: boolean;
  sell_signal: boolean;
  volatility_score: number;        // 0–10
  momentum_score: number;          // 0–10
  var_score: number;              // 0–10
  drawdown_score: number;         // 0–10
  regime_adjustment?: string;     // "BULLISH" | "NEUTRAL" | "BEARISH"
  // Enriched factor descriptions (from backend _flatten_risk_signal)
  volatility_label?: string;
  volatility_detail?: string;
  momentum_label?: string;
  momentum_detail?: string;
  var_label?: string;
  var_detail?: string;
  drawdown_label?: string;
  drawdown_detail?: string;
  dominant_risk_factor?: string;
}

/** Single market tracker entry from GET /api/markets/ */
export interface MarketTracker {
  ticker: string;
  display_name: string;
  description: string;
  coverage_scope: string;
  what_it_measures: string;
  top_sectors: Array<{ sector: string; weight_pct: number }>;
  key_constituents: string[];
  status: 'STRONG_UP' | 'UP' | 'SIDEWAYS' | 'DOWN' | 'STRONG_DOWN' | 'INSUFFICIENT_DATA';
  current_price: number | null;
  change_5d: number | null;
  change_20d: number | null;
  trend: string | null;
}

/** Market regime from GET /api/markets/regime */
export interface MarketRegime {
  regime: 'BULLISH' | 'NEUTRAL' | 'BEARISH';
  tracker_trends: Record<string, string>;
  bullish_count: number;
  bearish_count: number;
}

/** Full market tracker detail from GET /api/markets/{ticker} */
export interface MarketTrackerDetail extends MarketTracker {
  data_points: number;
  summary_stats: MarketSummaryStats;
  signal: MarketRiskSignal | null;
}

/** Advanced statistical risk metrics from GET /api/markets/{ticker}/risk */
export interface AdvancedRiskMetrics {
  // Data quality
  error: boolean;
  warnings: string[];
  data_points: number;

  // Volatility (annualized, %)
  volatility_annualized: number | null;

  // Value at Risk (daily, %)
  var_95: number | null;

  // Expected Shortfall / CVaR (daily, %)
  cvar_95: number | null;

  // Drawdown (%)
  max_drawdown_pct: number | null;

  // Risk-adjusted returns (annualized)
  sharpe_ratio: number | null;
  sortino_ratio: number | null;

  // Benchmark metrics
  beta: number | null;
  alpha: number | null;
}

/** Per-ticker refresh result from POST /api/markets/refresh */
export interface TrackerRefreshResult {
  status: "ok" | "error";
  records?: number;
  message?: string;
}

export interface MarketRefreshResponse {
  status: "success" | "partial";
  trackers_processed: number;
  succeeded: number;
  failed: number;
  total_records: number;
  results: Record<string, TrackerRefreshResult>;
}

// ==============================================================================
// DAILY MARKET REPORT (Part B - Daily Market Summary)
// ==============================================================================

/** Daily market-wide report generated by the scheduler */
export interface MarketReport {
  id: number;
  report_date: string; // ISO date
  overall_market_sentiment: "Very Bullish" | "Bullish" | "Neutral" | "Bearish" | "Very Bearish";
  key_headlines: string[];
  sector_performance: Array<{ sector: string; change_pct: number }>;
  top_gainers: Array<{ ticker: string; change_pct: number }>;
  top_losers: Array<{ ticker: string; change_pct: number }>;
  economic_events: string[];
  market_indices: Record<string, { value: number; change_pct: number }>;
  summary_text: string;
  created_at: string; // ISO timestamp
}

/** Summary card shown on intelligence page */
export interface MarketReportCard {
  id: number;
  report_date: string;
  overall_market_sentiment: string;
  summary_text_preview: string; // First 200 chars
  key_headlines_count: number;
  created_at: string;
}

/** Paginated market report list */
export interface MarketReportListResponse {
  items: MarketReport[];
  total: number;
  page: number;
  limit: number;
  has_more: boolean;
}

// ==============================================================================
// UNIFIED INTELLIGENCE BROWSER (Part C - All Reports in One Place)
// ==============================================================================

/** Single entry in the unified browser combining all report types */
export interface UnifiedReportEntry {
  id: number;
  ticker: string;
  company_name?: string | null;
  report_type: "company" | "sector" | "market";
  overall_sentiment: string;
  confidence_score: number | null;
  articles_count: number | null;
  summary_preview: string; // First 150 chars of executive_summary or summary_text
  price_snapshot: number | null;
  created_at: string;
  model_used: string | null;
}

/** Filter options for the unified browser */
export interface UnifiedReportFilters {
  ticker?: string;
  report_type?: "company" | "sector" | "market";
  sentiment?: string;
  date_from?: string;
  date_to?: string;
}
