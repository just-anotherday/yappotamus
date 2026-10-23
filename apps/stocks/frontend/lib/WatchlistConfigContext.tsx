'use client';

// ==============================================================================
// CONTEXT: WatchlistConfigContext - Global cached config from /api/watchlist/config
// ==============================================================================

import { createContext, useContext, useState, useEffect } from 'react';
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

  useEffect(() => {
    let active = true;
    void getWatchlistConfig().then(data => {
      if (active) { setConfig(data); setError(null); }
    }).catch(err => {
      if (active) setError(err instanceof Error ? err.message : 'Failed to load watchlist config');
    }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

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
