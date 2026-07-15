'use client';

// ==============================================================================
// CONTEXT: WatchlistConfigContext - Global cached config from /api/watchlist/config
// ==============================================================================

import { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { getWatchlistConfig } from '@/lib/api';
import type { WatchlistConfig } from '@/types/stock';

interface WatchlistConfigContextValue {
  config: WatchlistConfig | null;
  loading: boolean;
  error: string | null;
}

const WatchlistConfigContext = createContext<WatchlistConfigContextValue>({
  config: null,
  loading: true,
  error: null,
});

export function WatchlistConfigProvider({ children }: { children: React.ReactNode }) {
  const [config, setConfig] = useState<WatchlistConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchConfig = useCallback(async () => {
    try {
      const data = await getWatchlistConfig();
      setConfig(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load watchlist config');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchConfig();
  }, [fetchConfig]);

  return (
    <WatchlistConfigContext.Provider value={{ config, loading, error }}>
      {children}
    </WatchlistConfigContext.Provider>
  );
}

export function useWatchlistConfig() {
  const context = useContext(WatchlistConfigContext);
  if (!context) {
    throw new Error('useWatchlistConfig must be used within a WatchlistConfigProvider');
  }
  return context;
}
