// ==============================================================================
// HOOK: useWatchlist - Watchlist state + mutations
// ==============================================================================

import { useState, useEffect, useCallback, useRef } from 'react';
import { useWatchlistConfig } from '@/lib/WatchlistConfigContext';
import { fetchWatchlistData, fetchPostMarketPrices, apiAddToWatchlist, apiRemoveFromWatchlist, apiUpdateWatchlistOrder } from '@/lib/api';
import type { WatchlistItem } from '@/types/stock';
import { useExtendedHours } from '@/hooks/useExtendedHours';

const EXTENDED_HOURS_REFRESH_MS = 15_000;
const PRICE_FLASH_MS = 1_000;

export function useWatchlist() {
  const [watchlist, setWatchlist] = useState<WatchlistItem[]>([]);
  const [watchlistLoading, setWatchlistLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [watchlistOrder, setWatchlistOrder] = useState<string[]>([]);
  const [pendingTickers, setPendingTickers] = useState<Set<string>>(new Set());
  const [isReordering, setIsReordering] = useState(false);
  const [lastRefreshedAt, setLastRefreshedAt] = useState<Date | null>(null);
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

  const showToast = useCallback((msg: string, isError = false) => {
    if (isError) setError(msg);
    else setSuccessMessage(msg);
    setTimeout(() => {
      if (isError) setError(null);
      else setSuccessMessage(null);
    }, 3000);
  }, []);

  const loadWatchlist = useCallback(async (tickers?: string, quiet = false) => {
    const generation = ++loadGenerationRef.current;
    if (!quiet) setWatchlistLoading(true);
    try {
      const data = await fetchWatchlistData(tickers);
      if (generation !== loadGenerationRef.current || mutationGenerationRef.current > generation) return;
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
      setWatchlist(data);
      setLastRefreshedAt(new Date());
    } catch (err) {
      if (!quiet) showToast(err instanceof Error ? err.message : 'Failed to load watchlist', true);
    } finally {
      if (!quiet && generation === loadGenerationRef.current) setWatchlistLoading(false);
    }
  }, [showToast]);

  // Auto-load watchlist from DB on mount (no hardcoded defaults)
  useEffect(() => {
    loadWatchlist();
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
  }, [watchlist, pendingTickers, showToast, maxWatchlistSize]);

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
  }, [pendingTickers, watchlist, watchlistOrder, showToast]);

  // Sync watchlistOrder when watchlist changes (handles add/remove)
  useEffect(() => {
    const tickers = watchlist.map(w => w.ticker);
    setWatchlistOrder(prev => {
      const existing = prev.filter(t => tickers.includes(t));
      const newTickers = tickers.filter(t => !existing.includes(t));
      return [...existing, ...newTickers];
    });
  }, [watchlist]);

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
  }, [isReordering, watchlistOrder, showToast]);

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
