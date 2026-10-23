'use client';

import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from 'react';
import { apiFetch } from '@/lib/apiFetch';
import { requireOk } from '@/lib/apiError';
import { API_BASE } from '@/lib/serviceUrls';
import { describeNewsSync, NEWS_SYNC_COMPLETED_EVENT, type NewsSyncFeedback } from '@/lib/newsSync';
import AppIcon from '@/components/ui/AppIcon';

const NewsSyncContext = createContext<{
  syncing: boolean;
  feedback: NewsSyncFeedback | null;
  sync: () => Promise<void>;
} | null>(null);

/** Keep the active operation visible when navigating between news and overview. */
export function NewsSyncProvider({ children }: { children: ReactNode }) {
  const [syncing, setSyncing] = useState(false);
  const [feedback, setFeedback] = useState<NewsSyncFeedback | null>(null);
  const inFlight = useRef(false);
  const mounted = useRef(false);
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);

  async function sync() {
    if (inFlight.current) return;
    inFlight.current = true;
    setSyncing(true);
    setFeedback(null);
    try {
      // The backend checks the user's session and retains its shared ingestion
      // lease, provider limits, deduplication, and durable checkpoint.
      const response = await apiFetch(`${API_BASE}/api/news/ingest`, { method: 'POST' });
      await requireOk(response, 'The news sync request failed.');
      const result = describeNewsSync(await response.json());
      if (!mounted.current) return;
      setFeedback(result);
      if (result.refresh) window.dispatchEvent(new Event(NEWS_SYNC_COMPLETED_EVENT));
    } catch {
      if (mounted.current) setFeedback({
        kind: 'error', refresh: false,
        message: 'Unable to confirm the news sync finished. Refresh the news list before retrying; the server may still be working.',
      });
    } finally {
      inFlight.current = false;
      if (mounted.current) setSyncing(false);
    }
  }

  return <NewsSyncContext.Provider value={{ syncing, feedback, sync }}>{children}</NewsSyncContext.Provider>;
}

export default function NewsSync() {
  const state = useContext(NewsSyncContext);
  if (!state) throw new Error('NewsSync requires NewsSyncProvider');
  const { syncing, feedback, sync } = state;
  return <div className="news-sync-control">
    <button type="button" onClick={sync} disabled={syncing} className="button-secondary" aria-busy={syncing}>
      {syncing ? <span className="button-spinner" /> : <AppIcon name="news" width={16} height={16} />}
      {syncing ? 'Syncing news…' : 'Sync news now'}
    </button>
    {syncing && <p role="status" className="news-sync-feedback">Fetching news for your watchlist. This can take a minute.</p>}
    {!syncing && feedback && <p role={feedback.kind === 'error' || feedback.kind === 'warning' ? 'alert' : 'status'} className={`news-sync-feedback is-${feedback.kind}`}>{feedback.message}</p>}
  </div>;
}
