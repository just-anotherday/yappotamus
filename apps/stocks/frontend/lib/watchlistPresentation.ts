import type { LiveQuote, WatchlistItem } from '@/types/stock';

export type WatchlistSort = 'custom' | 'ticker' | 'change' | 'market-cap';
export type WatchlistDirectionFilter = 'all' | 'gainers' | 'losers';

export function getWatchlistChange(item: WatchlistItem, live?: LiveQuote): number | null {
  const price = live?.price ?? item.current_price;
  return item.previous_close > 0 ? ((price - item.previous_close) / item.previous_close) * 100 : null;
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
    if (sort === 'market-cap') return b.market_cap - a.market_cap;
    return (getWatchlistChange(b, livePrices[b.ticker]) ?? -Infinity) - (getWatchlistChange(a, livePrices[a.ticker]) ?? -Infinity);
  });
}

export function canReorderWatchlist(sort: WatchlistSort, search: string, direction: WatchlistDirectionFilter): boolean {
  return sort === 'custom' && search.trim() === '' && direction === 'all';
}

export function watchlistColumnCount(showAfterHours: boolean): number {
  return showAfterHours ? 6 : 5;
}