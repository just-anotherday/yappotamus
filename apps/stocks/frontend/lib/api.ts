// ==============================================================================
// API CLIENT
// ==============================================================================

import { API_BASE } from '@/types/stock';
import { apiFetch } from '@/lib/apiFetch';
import type {
  StockData,
  WatchlistItem,
  StockNews,
  WatchlistConfig,
  NewsArticle,
  CachedCompanyReport,
  CachedMarketReport,
  AIQueueStatus,
  PipelineStatus,
  MarketTracker,
  MarketTrackerDetail,
  MarketRegime,
  OhlcvPoint,
  AdvancedRiskMetrics,
  MarketRefreshResponse,
  UnifiedReportEntry,
  UnifiedReportFilters,
} from '@/types/stock';

export const fetchStock = async (ticker: string): Promise<StockData> => {
  const res = await apiFetch(`${API_BASE}/api/stock/${ticker.toUpperCase()}`);
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || 'Failed to fetch stock data');
  }
  return res.json();
};

export const fetchWatchlistData = async (tickers?: string): Promise<WatchlistItem[]> => {
  const url = tickers
    ? `${API_BASE}/api/watchlist?tickers=${tickers}`
    : `${API_BASE}/api/watchlist`;
  const res = await apiFetch(url);
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || 'Failed to fetch watchlist');
  }
  return res.json();
};

export interface PostMarketQuote {
  post_market_price: number;
  post_market_change: number;
  post_market_change_percent: number;
}

export interface WatchlistMutationResponse {
  success: boolean;
  message: string;
  data: WatchlistItem | null;
}

export const fetchPostMarketPrices = async (): Promise<Record<string, PostMarketQuote>> => {
  const res = await apiFetch(`${API_BASE}/api/watchlist/post-market`);
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || 'Failed to fetch after-hours prices');
  }
  return res.json();
};

export const apiAddToWatchlist = async (ticker: string): Promise<WatchlistMutationResponse> => {
  const res = await apiFetch(`${API_BASE}/api/watchlist/add`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ticker: ticker.toUpperCase() }),
  });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || 'Failed to add to watchlist');
  }
  return res.json();
};

export const apiRemoveFromWatchlist = async (ticker: string): Promise<void> => {
  const res = await apiFetch(`${API_BASE}/api/watchlist/${ticker.toUpperCase()}`, {
    method: 'DELETE',
  });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || 'Failed to remove from watchlist');
  }
};

/** Fetch persisted news articles from PostgreSQL (GET /news) */
export interface NewsPaginatedResponse {
  articles: NewsArticle[];
  total: number;
  page: number;
  limit: number;
  has_more: boolean;
}

export const fetchDbNews = async (
  ticker?: string,
  limit: number = 50,
  offset: number = 0,
  startDate?: string | null,
  endDate?: string | null,
): Promise<NewsPaginatedResponse> => {
  const params = new URLSearchParams();
  params.set('limit', String(limit));
  params.set('offset', String(offset));
  if (ticker) params.set('ticker', ticker.toUpperCase());
  if (startDate) params.set('start_date', startDate);
  if (endDate) params.set('end_date', endDate);

  const res = await apiFetch(`${API_BASE}/news?${params.toString()}`);
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || 'Failed to fetch news from database');
  }
  return res.json();
};

export const apiUpdateWatchlistOrder = async (tickers: string[]): Promise<void> => {
  const res = await apiFetch(`${API_BASE}/api/watchlist/order`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ tickers }),
  });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || 'Failed to update watchlist order');
  }
};

export const getWatchlistConfig = async (): Promise<WatchlistConfig> => {
  const res = await apiFetch(`${API_BASE}/api/watchlist/config`);
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || 'Failed to fetch watchlist config');
  }
  return res.json();
};

/** Fetch all distinct tickers from the news database (GET /news/tickers) */
export const fetchNewsTickers = async (): Promise<string[]> => {
  const res = await apiFetch(`${API_BASE}/news/tickers`);
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || 'Failed to fetch news tickers');
  }
  const data = await res.json();
  return data.tickers || [];
};

// ==============================================================================
// Cached Intelligence Endpoints (event-driven pipeline outputs)
// ==============================================================================

/** Get the latest cached AI intelligence report for a company */
export const fetchCompanyReport = async (ticker: string): Promise<CachedCompanyReport> => {
  const res = await apiFetch(`${API_BASE}/api/analysis/reports/company/${ticker.toUpperCase()}`);
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || `Failed to fetch cached report for ${ticker}`);
  }
  return res.json();
};

/** Fetch cached reports for multiple tickers (for dashboard grid view) */
export const fetchCompanyReportsBatch = async (tickers: string[]): Promise<CachedCompanyReport[]> => {
  const results = await Promise.allSettled(
    tickers.map(ticker => fetchCompanyReport(ticker)),
  );

  return results.reduce<CachedCompanyReport[]>((acc, result, idx) => {
    if (result.status === 'fulfilled') {
      acc.push(result.value);
    } else {
      console.warn(`Failed to fetch report for ${tickers[idx]}:`, result.reason);
    }
    return acc;
  }, []);
};

/** Get the latest cached daily market-wide intelligence report */
export const fetchMarketReport = async (): Promise<CachedMarketReport> => {
  const res = await apiFetch(`${API_BASE}/api/analysis/reports/market/latest`);
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || 'Failed to fetch market report');
  }
  return res.json();
};

/** Manually trigger a company report regeneration */
export const triggerCompanyReportRegeneration = async (ticker: string, model?: string): Promise<{ status: string; ticker: string }> => {
  const body: Record<string, any> = {};
  if (model) body.model = model;
  const res = await apiFetch(`${API_BASE}/api/analysis/reports/company/${ticker.toUpperCase()}/regenerate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || `Failed to trigger regeneration for ${ticker}`);
  }
  return res.json();
};

/** Get Ollama configuration (available models, connection status) */
export interface OllamaModelInfo {
  name: string;
  size?: number;
  modified_at?: string;
}
export interface OllamaConfig {
  default_model: string;
  available_models: OllamaModelInfo[];
  connected: boolean;
}
export const fetchOllamaConfig = async (): Promise<OllamaConfig> => {
  const res = await apiFetch(`${API_BASE}/api/analysis/config`);
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || 'Failed to fetch Ollama config');
  }
  return res.json();
};

/** Get current AI job queue status */
export const fetchAIQueueStatus = async (): Promise<AIQueueStatus> => {
  const res = await apiFetch(`${API_BASE}/api/analysis/reports/queue/status`);
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || 'Failed to fetch queue status');
  }
  return res.json();
};

/** Manually trigger a sector report regeneration */
export const triggerSectorReportRegeneration = async (sector: string): Promise<{ status: string; sector: string }> => {
  const res = await apiFetch(`${API_BASE}/api/analysis/reports/sector/${encodeURIComponent(sector)}/regenerate`, {
    method: 'POST',
  });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || `Failed to trigger sector regeneration for ${sector}`);
  }
  return res.json();
};

/** Manually trigger a market report regeneration */
export const triggerMarketReportRegeneration = async (): Promise<{ status: string }> => {
  const res = await apiFetch(`${API_BASE}/api/analysis/reports/market/regenerate`, {
    method: 'POST',
  });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || 'Failed to trigger market regeneration');
  }
  return res.json();
};

/** Trigger all tickers for company report regeneration */
export const triggerAllCompanyReports = async (tickers: string[], model?: string): Promise<void> => {
  await Promise.allSettled(
    tickers.map(ticker => triggerCompanyReportRegeneration(ticker, model)),
  );
};

/** Get comprehensive pipeline status */
export const fetchPipelineStatus = async (): Promise<PipelineStatus> => {
  const res = await apiFetch(`${API_BASE}/api/analysis/reports/pipeline/status`);
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || 'Failed to fetch pipeline status');
  }
  return res.json();
};

/** Get AI report history for a ticker */
export interface ReportHistoryEntry {
  id: number;
  original_report_id: number;
  overall_sentiment: string;
  confidence_score: number;
  articles_count: number;
  model_used: string;
  prompt_version: string;
  price_snapshot: number | null;
  report_data: Record<string, any> | null;
  created_at: string | null;
}
export interface ReportHistoryResponse {
  ticker: string;
  total: number;
  page: number;
  limit: number;
  entries: ReportHistoryEntry[];
}
export const fetchCompanyReportHistory = async (ticker: string, page = 1, limit = 20): Promise<ReportHistoryResponse> => {
  const res = await apiFetch(`${API_BASE}/api/analysis/reports/company/${ticker.toUpperCase()}/history?page=${page}&limit=${limit}`);
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || `Failed to fetch report history for ${ticker}`);
  }
  return res.json();
};

// ==============================================================================
// Risk Dashboard — Market Tracker Endpoints
// ==============================================================================

/** Get all market trackers (GET /api/markets/) */
export const fetchMarketTrackers = async (): Promise<MarketTracker[]> => {
  const res = await apiFetch(`${API_BASE}/api/markets/`);
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || 'Failed to fetch market trackers');
  }
  return res.json();
};

/** Get single market tracker detail with risk signal (GET /api/markets/{ticker}) */
export const fetchMarketTrackerDetail = async (ticker: string): Promise<MarketTrackerDetail> => {
  const res = await apiFetch(`${API_BASE}/api/markets/${ticker.toUpperCase()}`);
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || `Failed to fetch detail for ${ticker}`);
  }
  return res.json();
};

/** Get overall market regime (GET /api/markets/regime) */
export const fetchMarketRegime = async (): Promise<MarketRegime> => {
  const res = await apiFetch(`${API_BASE}/api/markets/regime`);
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || 'Failed to fetch market regime');
  }
  return res.json();
};

/** Backend response shape for /api/markets/{ticker}/prices */
export interface MarketPricesResponse {
  ticker: string;
  dates: string[];
  prices: Array<{ open: number; high: number; low: number; close: number; volume: number }>;
  count: number;
}

/** Supported chart period filters */
export type ChartPeriod = '1D' | '5D' | '1M' | '3M' | '6M' | '1Y' | 'ALL';

/** Map period label to trading days requested from backend */
const periodToDays: Record<ChartPeriod, number> = {
  '1D': 1,
  '5D': 5,
  '1M': 30,
  '3M': 90,
  '6M': 180,
  '1Y': 365,
  'ALL': 730,
};

/** Get OHLCV price history (GET /api/markets/{ticker}/prices) */
export const fetchMarketPrices = async (
  ticker: string,
  period: ChartPeriod = '6M',
): Promise<OhlcvPoint[]> => {
  const days = periodToDays[period];
  const res = await apiFetch(`${API_BASE}/api/markets/${ticker.toUpperCase()}/prices?days=${days}`);
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || `Failed to fetch prices for ${ticker}`);
  }
  const data: MarketPricesResponse = await res.json();
  // Backend returns {dates: string[], prices: [{open,high,low,close,volume}]}
  // Flatten to OhlcvPoint[] for frontend consumption
  return data.dates.map((date, i) => ({
    date,
    open: data.prices[i].open,
    high: data.prices[i].high,
    low: data.prices[i].low,
    close: data.prices[i].close,
    volume: data.prices[i].volume,
  }));
};

/** Get price statistics (GET /api/markets/{ticker}/stats) */
export const fetchMarketPriceStats = async (ticker: string): Promise<Record<string, any>> => {
  const res = await apiFetch(`${API_BASE}/api/markets/${ticker.toUpperCase()}/stats`);
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || `Failed to fetch stats for ${ticker}`);
  }
  return res.json();
};

/** Compute risk signal on demand (POST /api/markets/{ticker}/risk-signal) */
export const computeRiskSignal = async (ticker: string): Promise<Record<string, any>> => {
  const res = await apiFetch(`${API_BASE}/api/markets/${ticker.toUpperCase()}/risk-signal`, { method: 'POST' });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || `Failed to compute risk signal for ${ticker}`);
  }
  return res.json();
};

/** Backfill historical price data (POST /api/markets/{ticker}/backfill) */
export const backfillMarketPrices = async (ticker: string): Promise<{ message: string; records_added: number }> => {
  const res = await apiFetch(`${API_BASE}/api/markets/${ticker.toUpperCase()}/backfill`, { method: 'POST' });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || `Failed to backfill prices for ${ticker}`);
  }
  return res.json();
};

/** Get full risk signal + advanced metrics (GET /api/markets/{ticker}/risk) */
export interface RiskSignalResponse {
  ticker: string;
  data_points: number;
  signal: Record<string, any>;
  advanced_metrics: AdvancedRiskMetrics;
}
export const fetchRiskSignal = async (ticker: string): Promise<RiskSignalResponse> => {
  const res = await apiFetch(`${API_BASE}/api/markets/${ticker.toUpperCase()}/risk`);
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || `Failed to fetch risk signal for ${ticker}`);
  }
  return res.json();
};

/** Refresh all market tracker price data (POST /api/markets/refresh) */
export const refreshMarketTrackers = async (): Promise<MarketRefreshResponse> => {
  const res = await apiFetch(`${API_BASE}/api/markets/refresh`, { method: 'POST' });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || 'Failed to refresh market trackers');
  }
  return res.json();
};

// ==============================================================================
// Unified Intelligence Browser (Part C)
// ==============================================================================

/** Re-export types used by consumers of the unified browser API */
export type { UnifiedReportEntry, UnifiedReportFilters } from '@/types/stock';

/** Response shape for GET /api/analysis/reports/unified */
export interface UnifiedReportListResponse {
  items: UnifiedReportEntry[];
  total: number;
  page: number;
  limit: number;
  has_more: boolean;
}

/** Fetch unified intelligence reports combining company, sector, and market types */
export const fetchUnifiedReports = async (
  ticker?: string,
  report_type?: "company" | "sector" | "market",
  sentiment?: string,
  date_from?: string,
  date_to?: string,
  page: number = 1,
  limit: number = 20,
): Promise<UnifiedReportListResponse> => {
  const params = new URLSearchParams();
  params.set('page', String(page));
  params.set('limit', String(limit));
  if (ticker) params.set('ticker', ticker);
  if (report_type) params.set('report_type', report_type);
  if (sentiment) params.set('sentiment', sentiment);
  if (date_from) params.set('from', date_from);
  if (date_to) params.set('to', date_to);

  const res = await apiFetch(`${API_BASE}/api/analysis/reports/unified?${params.toString()}`);
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || 'Failed to fetch unified intelligence reports');
  }
  return res.json();
};

// ==============================================================================
// Market Report History (Part B)
// ==============================================================================

export interface MarketReportHistoryResponse {
  items: Array<{
    id: number;
    report_date: string | null;
    overall_sentiment: string;
    risk_level: string;
    confidence_score: number | null;
    model_used: string;
    created_at: string | null;
  }>;
  total: number;
  page: number;
  limit: number;
  has_more: boolean;
}

/** Fetch paginated market report history */
export const fetchMarketReportHistory = async (
  page: number = 1,
  limit: number = 20,
): Promise<MarketReportHistoryResponse> => {
  const res = await apiFetch(`${API_BASE}/api/analysis/reports/market/history?page=${page}&limit=${limit}`);
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || 'Failed to fetch market report history');
  }
  return res.json();
};

/** Fetch a specific market report by ID */
export const fetchMarketReportById = async (reportId: number): Promise<CachedMarketReport> => {
  const res = await apiFetch(`${API_BASE}/api/analysis/reports/market/${reportId}`);
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || `Failed to fetch market report #${reportId}`);
  }
  return res.json();
};
