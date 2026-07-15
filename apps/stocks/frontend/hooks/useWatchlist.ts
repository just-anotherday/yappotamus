// ==============================================================================
// HOOK: useWatchlist - Watchlist state + mutations
// ==============================================================================

import { useState, useEffect, useCallback } from 'react';
import { useWatchlistConfig } from '@/lib/WatchlistConfigContext';
import { fetchWatchlistData, apiAddToWatchlist, apiRemoveFromWatchlist, apiUpdateWatchlistOrder } from '@/lib/api';
import type { WatchlistItem } from '@/types/stock';

export function useWatchlist() {
  const [watchlist, setWatchlist] = useState<WatchlistItem[]>([]);
  const [watchlistLoading, setWatchlistLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [watchlistOrder, setWatchlistOrder] = useState<string[]>([]);

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

  const loadWatchlist = useCallback(async (tickers?: string) => {
    setWatchlistLoading(true);
    try {
      const data = await fetchWatchlistData(tickers);
      setWatchlist(data);
    } catch (err) {
      showToast(err instanceof Error ? err.message : 'Failed to load watchlist', true);
    } finally {
      setWatchlistLoading(false);
    }
  }, [showToast]);

  // Auto-load watchlist from DB on mount (no hardcoded defaults)
  useEffect(() => {
    loadWatchlist();
  }, [loadWatchlist]);

  const addTicker = useCallback(async (tickerToAdd: string) => {
    const normalized = tickerToAdd.trim().toUpperCase();
    if (watchlist.length >= maxWatchlistSize) {
      showToast(`Watchlist is full (max ${maxWatchlistSize}).`);
      return;
    }
    if (watchlist.some(item => item.ticker === normalized)) {
      showToast(`${normalized} is already in your watchlist.`);
      return;
    }
    try {
      await apiAddToWatchlist(normalized);
      showToast(`${normalized} added to watchlist.`);
      loadWatchlist();
    } catch (err) {
      showToast(err instanceof Error ? err.message : 'Failed to add ticker', true);
    }
  }, [watchlist, showToast, loadWatchlist, maxWatchlistSize]);

  const removeTicker = useCallback(async (tickerToRemove: string) => {
    try {
      await apiRemoveFromWatchlist(tickerToRemove);
      showToast(`${tickerToRemove} removed from watchlist.`);
      loadWatchlist();
    } catch (err) {
      showToast(err instanceof Error ? err.message : 'Failed to remove ticker', true);
    }
  }, [showToast, loadWatchlist]);

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
    try {
      await apiUpdateWatchlistOrder(newOrder);
      setWatchlistOrder(newOrder);
    } catch (err) {
      showToast(err instanceof Error ? err.message : 'Failed to save order', true);
    }
  }, [showToast]);

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
  };
}
