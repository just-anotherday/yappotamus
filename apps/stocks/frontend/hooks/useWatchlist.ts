// ==============================================================================
// HOOK: useWatchlist - Watchlist state + mutations
// ==============================================================================

import { useState, useEffect, useCallback, useRef } from 'react';
import { useWatchlistConfig } from '@/lib/WatchlistConfigContext';
import { fetchWatchlistData, fetchPostMarketPrices, apiAddToWatchlist, apiRemoveFromWatchlist, apiUpdateWatchlistOrder } from '@/lib/api';
import type { WatchlistItem } from '@/types/stock';
import { useExtendedHours } from '@/hooks/useExtendedHours';
import { getWatchlistDataWarning, mergeWatchlistRefresh } from '@/lib/watchlistPresentation';
import { getAppToken } from '@/lib/apiFetch';

const EXTENDED_HOURS_REFRESH_MS = 15_000;
const PRICE_FLASH_MS = 1_000;
const SNAPSHOT_MAX_AGE_MS = 5 * 60_000;
export type WatchlistRefreshResult =
  | { status: 'completed'; count: number; partial: boolean }
  | { status: 'failed'; message: string }
  | { status: 'superseded' };
let watchlistSnapshot: { token: string; items: WatchlistItem[]; order: string[]; refreshedAt: Date } | null = null;

function currentSnapshot() {
  const token = getAppToken();
  if (!token || watchlistSnapshot?.token !== token
    || Date.now() - watchlistSnapshot.refreshedAt.getTime() > SNAPSHOT_MAX_AGE_MS) {
    watchlistSnapshot = null;
  }
  return watchlistSnapshot;
}

export function useWatchlist() {
  const [snapshot] = useState(currentSnapshot);
  const [watchlist, setWatchlist] = useState<WatchlistItem[]>(snapshot?.items ?? []);
  const [watchlistLoading, setWatchlistLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [watchlistOrder, setWatchlistOrder] = useState<string[]>(snapshot?.order ?? []);
  const [pendingTickers, setPendingTickers] = useState<Set<string>>(new Set());
  const [isReordering, setIsReordering] = useState(false);
  const [lastRefreshedAt, setLastRefreshedAt] = useState<Date | null>(snapshot?.refreshedAt ?? null);
  const [postMarketFlash, setPostMarketFlash] = useState<Record<string, 'up' | 'down'>>({});
  const postMarketPricesRef = useRef<Record<string, number>>({});
  const flashTimeoutsRef = useRef<Record<string, ReturnType<typeof setTimeout>>>({});
  const loadGenerationRef = useRef(0);
  const mutationGenerationRef = useRef(0);
  const pendingTickersRef = useRef<Set<string>>(new Set());
  const isReorderingRef = useRef(false);
  const { shouldPoll } = useExtendedHours();

  // Consume cached config from global context (fetched once at app startup)
  const { config } = useWatchlistConfig();
  const maxWatchlistSize = config?.max_watchlist_size ?? 50;

  // Memory-only, session-scoped snapshot for navigation back to Home. Always revalidate.
  useEffect(() => {
    const token = getAppToken();
    if (token && lastRefreshedAt && !watchlistLoading && pendingTickers.size === 0 && !isReordering) {
      watchlistSnapshot = { token, items: watchlist, order: watchlistOrder, refreshedAt: lastRefreshedAt };
    }
  }, [watchlist, watchlistOrder, lastRefreshedAt, watchlistLoading, pendingTickers, isReordering]);

  const showToast = useCallback((msg: string, isError = false) => {
    if (isError) setError(msg);
    else setSuccessMessage(msg);
    setTimeout(() => {
      if (isError) setError(null);
      else setSuccessMessage(null);
    }, 3000);
  }, []);

  const loadWatchlist = useCallback(async (tickers?: string, quiet = false): Promise<WatchlistRefreshResult> => {
    const generation = ++loadGenerationRef.current;
    if (!quiet) setWatchlistLoading(true);
    try {
      const data = await fetchWatchlistData(tickers);
      if (generation !== loadGenerationRef.current || mutationGenerationRef.current > generation) return { status: 'superseded' };
      const nextPrices: Record<string, number> = {};

      data.forEach(item => {
        const newPrice = item.post_market_price;
        if (newPrice == null || newPrice <= 0) return;

        nextPrices[item.ticker] = newPrice;
        const oldPrice = postMarketPricesRef.current[item.ticker];
        if (oldPrice === undefined || oldPrice === newPrice) return;

        setPostMarketFlash(prev => ({
          ...prev,
          [item.ticker]: newPrice > oldPrice ? 'up' : 'down',
        }));

        if (flashTimeoutsRef.current[item.ticker]) {
          clearTimeout(flashTimeoutsRef.current[item.ticker]);
        }
        flashTimeoutsRef.current[item.ticker] = setTimeout(() => {
          setPostMarketFlash(prev => {
            const next = { ...prev };
            delete next[item.ticker];
            return next;
          });
          delete flashTimeoutsRef.current[item.ticker];
        }, PRICE_FLASH_MS);
      });

      postMarketPricesRef.current = nextPrices;
      setWatchlist(previous => mergeWatchlistRefresh(previous, data));
      setWatchlistOrder(previous => {
        const tickers = data.map(item => item.ticker);
        const existing = previous.filter(ticker => tickers.includes(ticker));
        return [...existing, ...tickers.filter(ticker => !existing.includes(ticker))];
      });
      setLastRefreshedAt(new Date());
      return { status: 'completed', count: data.length, partial: data.some(item => getWatchlistDataWarning(item) != null) };
    } catch (err) {
      if (generation !== loadGenerationRef.current) return { status: 'superseded' };
      const message = err instanceof Error ? err.message : 'Failed to load watchlist';
      if (!quiet) showToast(message, true);
      return { status: 'failed', message };
    } finally {
      if (!quiet && generation === loadGenerationRef.current) setWatchlistLoading(false);
    }
  }, [showToast]);

  // Auto-load watchlist from DB on mount (no hardcoded defaults)
  useEffect(() => {
    // Cancel the discarded Strict Mode mount before it starts a second quote batch.
    const timer = setTimeout(() => { void loadWatchlist(); }, 0);
    return () => clearTimeout(timer);
  }, [loadWatchlist]);

  useEffect(() => {
    if (!shouldPoll) return;

    const refreshPostMarketPrices = async () => {
      try {
        const prices = await fetchPostMarketPrices();
        const nextPrices: Record<string, number> = {};

        Object.entries(prices).forEach(([ticker, quote]) => {
          const newPrice = quote.post_market_price;
          if (newPrice == null || newPrice <= 0) return;

          nextPrices[ticker] = newPrice;
          const oldPrice = postMarketPricesRef.current[ticker];
          if (oldPrice === undefined || oldPrice === newPrice) return;

          setPostMarketFlash(prev => ({
            ...prev,
            [ticker]: newPrice > oldPrice ? 'up' : 'down',
          }));
          if (flashTimeoutsRef.current[ticker]) clearTimeout(flashTimeoutsRef.current[ticker]);
          flashTimeoutsRef.current[ticker] = setTimeout(() => {
            setPostMarketFlash(prev => {
              const next = { ...prev };
              delete next[ticker];
              return next;
            });
            delete flashTimeoutsRef.current[ticker];
          }, PRICE_FLASH_MS);
        });

        postMarketPricesRef.current = nextPrices;
        setWatchlist(prev => prev.map(item => {
          const quote = prices[item.ticker];
          return quote
            ? { ...item, ...quote }
            : {
                ...item,
                post_market_price: null,
                post_market_change: null,
                post_market_change_percent: null,
              };
        }));
      } catch {
        // Keep the last known quote during transient background refresh failures.
      }
    };

    void refreshPostMarketPrices();
    const id = setInterval(refreshPostMarketPrices, EXTENDED_HOURS_REFRESH_MS);
    return () => clearInterval(id);
  }, [shouldPoll]);

  useEffect(() => () => {
    Object.values(flashTimeoutsRef.current).forEach(clearTimeout);
  }, []);

  const addTicker = useCallback(async (tickerToAdd: string) => {
    const normalized = tickerToAdd.trim().toUpperCase();
    if (!normalized || pendingTickersRef.current.has(normalized)) return;
    if (watchlist.length >= maxWatchlistSize) {
      showToast(`Watchlist is full (max ${maxWatchlistSize}).`);
      return;
    }
    if (watchlist.some(item => item.ticker === normalized)) {
      showToast(`${normalized} is already in your watchlist.`);
      return;
    }
    pendingTickersRef.current.add(normalized);
    setPendingTickers(new Set(pendingTickersRef.current));
    try {
      const response = await apiAddToWatchlist(normalized);
      if (!response.data) throw new Error(`No watchlist data returned for ${normalized}`);
      mutationGenerationRef.current = ++loadGenerationRef.current;
      setWatchlistLoading(false);
      setWatchlist(prev => [...prev, response.data!]);
      setWatchlistOrder(prev => [...prev, normalized]);
      showToast(`${normalized} added to watchlist.`);
    } catch (err) {
      showToast(err instanceof Error ? err.message : 'Failed to add ticker', true);
    } finally {
      pendingTickersRef.current.delete(normalized);
      setPendingTickers(new Set(pendingTickersRef.current));
    }
  }, [watchlist, showToast, maxWatchlistSize]);

  const removeTicker = useCallback(async (tickerToRemove: string) => {
    const normalized = tickerToRemove.toUpperCase();
    if (pendingTickersRef.current.has(normalized)) return;
    const removedItem = watchlist.find(item => item.ticker === normalized);
    if (!removedItem) return;
    const previousWatchlist = watchlist;
    const previousOrder = watchlistOrder;
    mutationGenerationRef.current = ++loadGenerationRef.current;
    setWatchlistLoading(false);
    pendingTickersRef.current.add(normalized);
    setPendingTickers(new Set(pendingTickersRef.current));
    setWatchlist(prev => prev.filter(item => item.ticker !== normalized));
    setWatchlistOrder(prev => prev.filter(ticker => ticker !== normalized));
    try {
      await apiRemoveFromWatchlist(normalized);
      showToast(`${normalized} removed from watchlist.`);
    } catch (err) {
      setWatchlist(previousWatchlist);
      setWatchlistOrder(previousOrder);
      showToast(err instanceof Error ? err.message : 'Failed to remove ticker', true);
    } finally {
      pendingTickersRef.current.delete(normalized);
      setPendingTickers(new Set(pendingTickersRef.current));
    }
  }, [watchlist, watchlistOrder, showToast]);

  const reorderWatchlist = useCallback(async (newOrder: string[]) => {
    if (isReorderingRef.current) return;
    const previousOrder = watchlistOrder;
    mutationGenerationRef.current = ++loadGenerationRef.current;
    setWatchlistLoading(false);
    setWatchlistOrder(newOrder);
    isReorderingRef.current = true;
    setIsReordering(true);
    try {
      await apiUpdateWatchlistOrder(newOrder);
    } catch (err) {
      setWatchlistOrder(previousOrder);
      showToast(err instanceof Error ? err.message : 'Failed to save order', true);
    } finally {
      isReorderingRef.current = false;
      setIsReordering(false);
    }
  }, [watchlistOrder, showToast]);

  return {
    watchlist,
    watchlistLoading,
    error,
    successMessage,
    addTicker,
    removeTicker,
    loadWatchlist,
    watchlistOrder,
    reorderWatchlist,
    maxWatchlistSize,
    postMarketFlash,
    pendingTickers,
    isReordering,
    lastRefreshedAt,
  };
}
