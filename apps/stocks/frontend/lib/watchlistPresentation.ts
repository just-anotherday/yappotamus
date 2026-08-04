import type { LiveQuote, WatchlistItem } from '@/types/stock';

export type WatchlistSort = 'custom' | 'ticker' | 'change' | 'market-cap';
export type WatchlistDirectionFilter = 'all' | 'gainers' | 'losers';

export function isFiniteWatchlistNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value);
}

export function formatWatchlistCurrency(value: unknown): string {
  if (!isFiniteWatchlistNumber(value)) return '—';
  return new Intl.NumberFormat('en-US', {
    style: 'currency', currency: 'USD',
  }).format(value);
}

export function getMarketSizeLabel(item: WatchlistItem): string {
  return item.market_size_type === 'fund_assets' ? 'Fund Assets' : 'Market Cap';
}

export function getMarketSizeValue(item: WatchlistItem): number | null {
  if (isFiniteWatchlistNumber(item.market_size_value) && item.market_size_value > 0) {
    return item.market_size_value;
  }
  if (
    item.security_type !== 'ETF'
    && item.market_size_type !== 'fund_assets'
    && isFiniteWatchlistNumber(item.market_cap)
    && item.market_cap > 0
  ) {
    return item.market_cap;
  }
  return null;
}

export function formatMarketSize(item: WatchlistItem): string {
  if (item.market_size_status === 'provider_failed') return 'Unavailable';
  const value = getMarketSizeValue(item);
  if (value === null) return item.security_type === 'ETF' ? 'Unavailable' : 'N/A';
  const currency = typeof item.market_size_currency === 'string'
    ? item.market_size_currency.trim().toUpperCase()
    : '';
  const prefix = currency === 'USD' ? '$' : currency ? `${currency} ` : 'Unknown currency ';
  if (value >= 1e12) return `${prefix}${(value / 1e12).toFixed(2)}T`;
  if (value >= 1e9) return `${prefix}${(value / 1e9).toFixed(2)}B`;
  if (value >= 1e6) return `${prefix}${(value / 1e6).toFixed(2)}M`;
  return `${prefix}${value.toLocaleString()}`;
}

export function getCompanySize(item: WatchlistItem): { label: string; color: string } {
  if (item.security_type === 'ETF' || item.market_size_type === 'fund_assets') {
    return { label: 'Not applicable', color: 'bg-gray-100 text-gray-700' };
  }
  const marketCap = getMarketSizeValue(item);
  if (marketCap === null) return { label: 'Unavailable', color: 'bg-gray-100 text-gray-700' };
  if (marketCap >= 200_000_000_000) return { label: 'Mega Cap', color: 'bg-purple-100 text-purple-700' };
  if (marketCap >= 10_000_000_000) return { label: 'Large Cap', color: 'bg-emerald-100 text-emerald-700' };
  if (marketCap >= 2_000_000_000) return { label: 'Mid Cap', color: 'bg-cyan-100 text-cyan-700' };
  if (marketCap >= 300_000_000) return { label: 'Small Cap', color: 'bg-orange-100 text-orange-700' };
  if (marketCap >= 50_000_000) return { label: 'Micro Cap', color: 'bg-yellow-100 text-yellow-700' };
  return { label: 'Nano Cap', color: 'bg-red-100 text-red-700' };
}
export function formatWatchlistNumber(value: unknown, decimals = 2): string {
  return isFiniteWatchlistNumber(value) ? value.toFixed(decimals) : '—';
}

export function formatWatchlistPercent(value: unknown, notApplicable = false): string {
  if (notApplicable) return 'Not applicable';
  return isFiniteWatchlistNumber(value) ? `${(value * 100).toFixed(2)}%` : '—';
}

export function formatWatchlistRange(low: unknown, high: unknown): string {
  if (!isFiniteWatchlistNumber(low) || !isFiniteWatchlistNumber(high)) return '—';
  return `${formatWatchlistCurrency(low)} - ${formatWatchlistCurrency(high)}`;
}

export function formatEmployeeCount(value: unknown): string {
  return isFiniteWatchlistNumber(value) && value >= 0
    ? new Intl.NumberFormat('en-US').format(value)
    : '—';
}

export function hasWatchlistRecommendation(value: unknown): value is string {
  return typeof value === 'string' && value.trim() !== '' && value.trim().toUpperCase() !== 'N/A';
}

export function getWatchlistDataWarning(item: WatchlistItem): string | null {
  if (item.data_status === 'stale') {
    const hasFreshQuoteProvider = item.provider_status?.finnhub === 'healthy'
      || item.provider_status?.yfinance === 'healthy';
    return hasFreshQuoteProvider
      ? 'Stale fundamentals — showing last-known fundamentals with current prices.'
      : 'Stale data — showing last-known values.';
  }
  if (item.data_status === 'partial') return 'Partial data — some fundamentals are temporarily unavailable.';
  if (item.data_status === 'unavailable') return 'Fundamentals temporarily unavailable.';
  return null;
}

export function formatWatchlistRecommendation(value: unknown): string {
  return typeof value === 'string' && value.trim()
    ? value.replace('_', ' ').toUpperCase()
    : 'N/A';
}

function sortableMarketCap(value: unknown): number {
  return isFiniteWatchlistNumber(value) ? value : Number.NEGATIVE_INFINITY;
}

const PRESERVE_WHEN_MISSING: readonly (keyof WatchlistItem)[] = [
  'symbol',
  'company_name',
  'sector',
  'industry',
  'long_business_summary',
  'website',
  'full_time_employees',
  'average_analyst_rating',
  'forward_pe',
  'ceo_name',
  'exchange',
  'security_type',
  'fund_assets',
  'market_size_value',
  'market_size_type',
  'market_size_currency',
  'market_size_fallback_used',
  'market_size_status',
  'shares_outstanding',
  'float_shares',
  'insider_percent',
  'institution_percent',
  'short_percent_of_float',
  'shares_short',
  'target_mean_price',
  'target_median_price',
  'target_high_price',
  'target_low_price',
  'recommendation_key',
  'number_of_analysts',
  'fifty_two_week_high',
  'fifty_two_week_low',
  'beta',
  'overall_risk',
];

const PRESERVE_WHEN_ZERO: readonly (keyof WatchlistItem)[] = [
  'current_price',
  'open_price',
  'previous_close',
  'day_low',
  'day_high',
  'fifty_two_week_high',
  'fifty_two_week_low',
  'market_cap',
  'volume',
  'full_time_employees',
  'shares_outstanding',
  'float_shares',
  'shares_short',
  'target_mean_price',
  'target_median_price',
  'target_high_price',
  'target_low_price',
  'number_of_analysts',
];

function isMissingRefreshValue(value: unknown): boolean {
  return value == null || (typeof value === 'string' && value.trim() === '');
}

function preserveField<K extends keyof WatchlistItem>(
  result: WatchlistItem,
  previous: WatchlistItem,
  field: K,
): void {
  result[field] = previous[field];
}

function preserveObjectField<T, K extends keyof T>(
  result: T,
  previous: T,
  field: K,
): void {
  result[field] = previous[field];
}
function mergeEtfData(
  previous: NonNullable<WatchlistItem['etf_data']>,
  incoming: NonNullable<WatchlistItem['etf_data']>,
): NonNullable<WatchlistItem['etf_data']> {
  const merged = { ...previous, ...incoming };
  for (const field of Object.keys(previous) as (keyof typeof previous)[]) {
    if (isMissingRefreshValue(incoming[field])) preserveObjectField(merged, previous, field);
  }
  return merged;
}

/**
 * Keep last-known fundamentals when a full REST refresh returns a sparse or
 * per-symbol error shell. Incoming quotes still replace valid quote fields.
 * The incoming list remains authoritative for membership and ordering.
 */
export function mergeWatchlistRefresh(
  previousItems: WatchlistItem[],
  incomingItems: WatchlistItem[],
): WatchlistItem[] {
  const previousByTicker = new Map(previousItems.map(item => [item.ticker, item]));

  return incomingItems.map(incoming => {
    const previous = previousByTicker.get(incoming.ticker);
    if (!previous) return incoming;

    const providerFailed = incoming.data_status === 'unavailable'
      || ['provider_failed', 'rate_limited', 'unauthorized'].includes(incoming.market_size_status ?? '');
    if (providerFailed) {
      return {
        ...previous,
        data_status: 'stale',
        market_size_status: previous.market_size_value != null ? 'stale_cache' : incoming.market_size_status,
        post_market_price: incoming.post_market_price ?? previous.post_market_price,
        post_market_change: incoming.post_market_change ?? previous.post_market_change,
        post_market_change_percent: incoming.post_market_change_percent ?? previous.post_market_change_percent,
      };
    }

    const merged: WatchlistItem = { ...previous, ...incoming };
    for (const field of PRESERVE_WHEN_MISSING) {
      if (isMissingRefreshValue(incoming[field])) preserveField(merged, previous, field);
    }
    for (const field of PRESERVE_WHEN_ZERO) {
      const prior = previous[field];
      if (incoming[field] === 0 && typeof prior === 'number' && prior > 0) {
        preserveField(merged, previous, field);
      }
    }

    const incomingCompany = incoming.company_name?.trim().toUpperCase();
    const incomingTicker = incoming.ticker.trim().toUpperCase();
    if (incomingCompany === incomingTicker && previous.company_name.trim().toUpperCase() !== incomingTicker) {
      merged.company_name = previous.company_name;
    }
    if (incoming.security_type === 'UNKNOWN' && previous.security_type && previous.security_type !== 'UNKNOWN') {
      merged.security_type = previous.security_type;
    }
    if (incoming.recommendation_key === 'N/A' && previous.recommendation_key !== 'N/A') {
      merged.recommendation_key = previous.recommendation_key;
    }

    merged.etf_data = incoming.etf_data == null
      ? previous.etf_data
      : previous.etf_data == null
        ? incoming.etf_data
        : mergeEtfData(previous.etf_data, incoming.etf_data);
    if (incoming.data_status === 'partial' && previous.data_status === 'complete') {
      merged.data_status = 'stale';
      if (merged.market_size_value != null) merged.market_size_status = 'stale_cache';
    }

    return merged;
  });
}

export function getWatchlistDisplayPrice(item: WatchlistItem, live?: LiveQuote): number | null {
  const value = live?.price ?? item.current_price;
  return isFiniteWatchlistNumber(value) && value > 0 ? value : null;
}

export function getWatchlistChange(item: WatchlistItem, live?: LiveQuote): number | null {
  if (live?.change_percent != null && Number.isFinite(live.change_percent)) return live.change_percent;
  const price = live?.price ?? item.current_price;
  const previousClose = live?.previous_close ?? item.previous_close;
  if (!isFiniteWatchlistNumber(price) || !isFiniteWatchlistNumber(previousClose) || previousClose <= 0) {
    return null;
  }
  return ((price - previousClose) / previousClose) * 100;
}

export function presentWatchlist(
  items: WatchlistItem[],
  order: string[],
  livePrices: Record<string, LiveQuote>,
  search: string,
  sort: WatchlistSort,
  direction: WatchlistDirectionFilter,
): WatchlistItem[] {
  const byTicker = new Map(items.map(item => [item.ticker, item]));
  const custom = [...order.map(ticker => byTicker.get(ticker)).filter((item): item is WatchlistItem => Boolean(item))];
  items.forEach(item => { if (!order.includes(item.ticker)) custom.push(item); });
  const query = search.trim().toLowerCase();
  const filtered = custom.filter(item => {
    if (query && !item.ticker.toLowerCase().includes(query) && !item.company_name?.toLowerCase().includes(query)) return false;
    const change = getWatchlistChange(item, livePrices[item.ticker]);
    return direction === 'all' || (direction === 'gainers' ? change != null && change > 0 : change != null && change < 0);
  });
  if (sort === 'custom') return filtered;
  return [...filtered].sort((a, b) => {
    if (sort === 'ticker') return a.ticker.localeCompare(b.ticker);
    if (sort === 'market-cap') return sortableMarketCap(getMarketSizeValue(b)) - sortableMarketCap(getMarketSizeValue(a));
    return (getWatchlistChange(b, livePrices[b.ticker]) ?? -Infinity) - (getWatchlistChange(a, livePrices[a.ticker]) ?? -Infinity);
  });
}

export function canReorderWatchlist(sort: WatchlistSort, search: string, direction: WatchlistDirectionFilter): boolean {
  return sort === 'custom' && search.trim() === '' && direction === 'all';
}

export function watchlistColumnCount(showAfterHours: boolean): number {
  return showAfterHours ? 6 : 5;
}
