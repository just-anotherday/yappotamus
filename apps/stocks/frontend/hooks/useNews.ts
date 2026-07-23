// ==============================================================================
// HOOK: useNews - Fetch paginated news articles from PostgreSQL via GET /news
//             Listens for "news_refresh" WebSocket events instead of polling
// ==============================================================================

import { useState, useEffect, useCallback, useRef } from 'react';
import { fetchDbNews } from '@/lib/api';
import { getAppWebSocketProtocols, invalidateAppToken } from '@/lib/apiFetch';
import { WS_URL } from '@/types/stock';
import type { NewsArticle } from '@/types/stock';

interface UseNewsReturn {
  articles: NewsArticle[];
  total: number;
  page: number;
  offset: number;
  totalPages: number;
  limit: number;
  hasMore: boolean;
  loading: boolean;
  error: string | null;
  setPage: (page: number) => Promise<void>;
  goToNextPage: () => Promise<void>;
  goToPrevPage: () => Promise<void>;
  resetToFirstPage: () => Promise<void>;
  goToFirstPage: () => Promise<void>;
  goToLastPage: () => Promise<void>;
  refetch: () => Promise<void>;
}

export function useNews(
  ticker?: string,
  limit: number = 50,
  startDate?: string | null,
  endDate?: string | null,
): UseNewsReturn {
  const [articles, setArticles] = useState<NewsArticle[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [total, setTotal] = useState(0);
  const [page, setPageState] = useState(1);

  const totalPages = Math.max(1, Math.ceil(total / limit));
  const offset = (page - 1) * limit;
  const hasMore = page < totalPages;

  const loadData = useCallback(
    async (targetPage: number) => {
      setLoading(true);
      setError(null);
      try {
        const off = (targetPage - 1) * limit;
        const data = await fetchDbNews(ticker, limit, off, startDate, endDate);
        setArticles(data.articles);
        setTotal(data.total);
        setPageState(targetPage);
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : 'Failed to fetch news articles';
        setError(message);
      } finally {
        setLoading(false);
      }
    },
    [ticker, limit, startDate, endDate],
  );

  // Initial load when dependencies change
  useEffect(() => {
    loadData(1);
  }, [loadData]);

  // WebSocket: listen for "news_refresh" events from backend after ingestion cycles
  const wsRef = useRef<WebSocket | null>(null);
  const refetchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    const protocols = getAppWebSocketProtocols();
    if (!protocols) return;

    const ws = new WebSocket(WS_URL, protocols);
    wsRef.current = ws;

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.type === 'news_refresh') {
          // Backend just finished an ingestion cycle.
          // Wait a short delay so the DB commit settles, then refetch.
          if (refetchTimerRef.current) clearTimeout(refetchTimerRef.current);
          refetchTimerRef.current = setTimeout(() => {
            loadData(page);
          }, 3000); // 3s delay after ingestion completes
        }
      } catch (err) {
        // Ignore parse errors for price-update messages (they're handled by useLivePrices)
      }
    };

    ws.onclose = (event) => {
      if (event.code === 4401) {
        invalidateAppToken();
        return;
      }

      // Attempt reconnect after 5s if not intentionally closed
      setTimeout(() => {
        if (wsRef.current && wsRef.current.readyState === WebSocket.CLOSED) {
          wsRef.current = null;
          // Effect will re-run on next render, but we can also trigger a gentle reload
        }
      }, 5000);
    };

    return () => {
      if (wsRef.current) wsRef.current.close();
      if (refetchTimerRef.current) clearTimeout(refetchTimerRef.current);
    };
  }, [page, loadData]);

  const setPage = useCallback(
    async (targetPage: number) => {
      const clamped = Math.max(1, Math.min(targetPage, totalPages));
      await loadData(clamped);
    },
    [loadData, totalPages],
  );

  const goToNextPage = useCallback(() => {
    return setPage(page + 1);
  }, [page, setPage]);

  const goToPrevPage = useCallback(() => {
    return setPage(page - 1);
  }, [page, setPage]);

  const resetToFirstPage = useCallback(() => {
    return loadData(1);
  }, [loadData]);

  const goToFirstPage = useCallback(() => {
    return setPage(1);
  }, [setPage]);

  const goToLastPage = useCallback(() => {
    return setPage(totalPages);
  }, [setPage, totalPages]);

  const refetch = useCallback(() => {
    return loadData(page);
  }, [loadData, page]);

  return {
    articles,
    total,
    page,
    offset,
    totalPages,
    limit,
    hasMore,
    loading,
    error,
    setPage,
    goToNextPage,
    goToPrevPage,
    resetToFirstPage,
    goToFirstPage,
    goToLastPage,
    refetch,
  };
}
