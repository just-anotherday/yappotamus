'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { apiFetch } from '@/lib/apiFetch';
import { requireOk } from '@/lib/apiError';
import { API_BASE } from '@/lib/serviceUrls';
import { dailySyncStatus, type DailyUpdateSync } from '@/lib/dailyUpdatesPresentation';

interface TickerPreference {
  ticker: string;
  news_enabled: boolean;
  reports_enabled: boolean;
  news_status: string;
  news_checked_at: string | null;
}
interface Settings extends DailyUpdateSync {
  tickers: TickerPreference[];
  applied_at: string | null;
  max_tickers: number;
  shared_settings_ready: boolean;
  sync_pending?: boolean;
  local_status: Record<string, { status: string; checked_at: string | null }>;
}

async function requestSettings(path = '', init?: RequestInit): Promise<Settings> {
  const response = await apiFetch(`${API_BASE}/api/daily-updates${path}`, { cache: 'no-store', ...init });
  await requireOk(response, 'Daily update settings could not be loaded');
  return response.json();
}

function timestamp(value: string | null) {
  return value ? new Date(value).toLocaleString(undefined, { timeZone: 'America/New_York', timeZoneName: 'short' }) : 'Not yet received';
}
function newsLabel(value: string) {
  return ({ pending: 'Queued', fetching: 'Fetching news…', completed: 'Initial fetch complete', retrying: 'Retry queued', paused: 'Paused', not_requested: 'Scheduled collection' } as Record<string, string>)[value] || 'Waiting';
}

export default function DailyUpdatesPage() {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [ticker, setTicker] = useState('');
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState('');
  const busyRef = useRef(false);
  const generation = useRef(0);

  const load = useCallback(async () => {
    if (busyRef.current) return;
    const version = ++generation.current;
    try {
      const next = await requestSettings();
      if (version === generation.current) { setSettings(next); setError(''); }
    } catch (err) {
      if (version === generation.current) setError(err instanceof Error ? err.message : 'Could not load settings');
    }
  }, []);
  useEffect(() => {
    void load();
    const interval = setInterval(() => void load(), 15_000);
    return () => { clearInterval(interval); generation.current++; };
  }, [load]);

  async function change(key: string, path: string, method: string, body?: object) {
    if (busyRef.current) return;
    busyRef.current = true;
    const version = ++generation.current;
    setBusy(key); setError(''); setMessage('');
    try {
      const next = await requestSettings(path, { method, headers: { 'Content-Type': 'application/json' }, ...(body ? { body: JSON.stringify(body) } : {}) });
      if (version !== generation.current) return;
      setSettings(next);
      setMessage(next.sync_pending ? 'Saved on the live site. Local synchronization is pending.' : 'Settings saved. The local automation will acknowledge the change below.');
      if (key === 'add') setTicker('');
    } catch (err) {
      if (version === generation.current) setError(err instanceof Error ? err.message : 'Could not save settings');
    } finally {
      busyRef.current = false;
      if (version === generation.current) setBusy('');
    }
  }

  const sync = settings ? dailySyncStatus(settings) : null;
  return <div className="mx-auto w-full max-w-5xl px-4 py-8">
    <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
      <div><p className="text-sm opacity-60">Your collection preferences</p><h1 className="mt-1 text-3xl font-semibold">Daily updates</h1>
        <p className="mt-3 max-w-2xl text-sm opacity-75">One ticker list for the live site and your local automation. Choose which companies receive news, daily reports, or both.</p></div>
      <button type="button" className="button-secondary" disabled={!!busy} onClick={() => void load()}>Refresh status</button>
    </div>
    {error && <p role="alert" className="mb-4 rounded-lg border border-red-500/40 p-3 text-sm">{error}</p>}
    {message && <p role="status" className="mb-4 rounded-lg border border-emerald-500/40 p-3 text-sm">{message}</p>}
    {!settings ? <p role="status">{error ? 'Settings unavailable. Refresh to try again.' : 'Loading daily update settings…'}</p> : <>
      {!settings.shared_settings_ready && <p role="status" className="mb-4 rounded-xl border p-4 text-sm">Shared controls are waiting for the live deployment and local synchronization to be enabled. The list below currently reflects this computer; editing will be available once connected.</p>}
      <section aria-label="Local synchronization" className="surface mb-6 rounded-xl border p-5">
        <h2 className="font-semibold">{sync?.label}</h2><p className="mt-2 text-sm opacity-75">{sync?.detail}</p>
        <p className="mt-3 text-xs opacity-60">Last local check-in: {timestamp(settings.last_seen_at)} · Settings received: {timestamp(settings.applied_at)}</p>
      </section>
      <form className="surface mb-5 flex flex-wrap items-end gap-3 rounded-xl border p-4" onSubmit={event => {
        event.preventDefault();
        void change('add', '/tickers', 'POST', { ticker: ticker.trim().toUpperCase(), news_enabled: true, reports_enabled: true });
      }}>
        <label className="min-w-40 flex-1 text-sm">Add a ticker<input className="mt-2 block w-full rounded-md border bg-transparent px-3 py-2" aria-label="Ticker to add" value={ticker} onChange={event => setTicker(event.target.value.toUpperCase())} placeholder="e.g. MSFT" maxLength={10} pattern="[A-Za-z0-9]+" required disabled={!!busy} /></label>
        <button className="button-primary" type="submit" disabled={!!busy || !settings.shared_settings_ready || !ticker.trim() || settings.tickers.length >= settings.max_tickers}>{busy === 'add' ? 'Adding…' : 'Add ticker'}</button>
        <p className="w-full text-xs opacity-60">New tickers start with news and reports enabled. News is queued immediately; reports join the next weekday run.</p>
      </form>
      <div className="surface overflow-x-auto rounded-xl border">
        <table className="w-full text-left text-sm"><caption className="p-4 text-left font-semibold">{settings.tickers.length} of {settings.max_tickers} tickers</caption>
          <thead><tr className="border-y"><th className="p-4">Ticker</th><th className="p-4">Collect news</th><th className="p-4">Daily report</th><th className="p-4">Initial news fetch</th><th className="p-4"><span className="sr-only">Actions</span></th></tr></thead>
          <tbody>{settings.tickers.map(item => <tr key={item.ticker} className="border-b last:border-0">
            <th scope="row" className="p-4 font-semibold">{item.ticker}</th>
            {(['news_enabled', 'reports_enabled'] as const).map(field => <td className="p-4" key={field}><button type="button" role="switch" aria-checked={item[field]} aria-label={`${field === 'news_enabled' ? 'Collect news' : 'Daily report'} for ${item.ticker}`} disabled={!!busy || !settings.shared_settings_ready} className={`rounded-full border px-4 py-1.5 text-xs font-medium ${item[field] ? 'border-emerald-500/50 bg-emerald-500/10' : 'opacity-60'}`} onClick={() => void change(item.ticker, `/tickers/${item.ticker}`, 'PATCH', { news_enabled: item.news_enabled, reports_enabled: item.reports_enabled, [field]: !item[field] })}>{item[field] ? 'On' : 'Off'}</button></td>)}
            <td className="p-4 text-xs"><span>{newsLabel(item.news_status)}</span>{settings.local_status[item.ticker] && <span className="mt-1 block opacity-60">Local: {newsLabel(settings.local_status[item.ticker].status)}</span>}</td>
            <td className="p-4 text-right"><button type="button" className="text-xs underline underline-offset-4 disabled:opacity-50" disabled={!!busy || !settings.shared_settings_ready} onClick={() => {
              if (window.confirm(`Remove ${item.ticker} from the watchlist and future daily updates? Existing articles and reports will remain.`)) void change(item.ticker, `/tickers/${item.ticker}`, 'DELETE');
            }}>Remove<span className="sr-only"> {item.ticker}</span></button></td>
          </tr>)}</tbody>
        </table>
        {!settings.tickers.length && <p className="p-5 text-sm opacity-70">No tickers selected. Add one above to start collecting news and include it in daily updates.</p>}
      </div>
      {busy && <p role="status" className="mt-3 text-sm">{busy === 'add' ? 'Adding ticker and queuing news…' : `Saving ${busy}…`}</p>}
      <p className="mt-5 text-sm opacity-70">News follows its collection schedule every day; daily reports run on weekdays. Reports can use previously collected articles when news is paused. Changes apply after the local automation receives them. An article fetch or report already in progress may finish.</p>
      <p className="mt-3 text-sm opacity-70">Removing a ticker also removes it from the overview watchlist. Your existing research stays available in <Link className="underline" href="/analysis/reports">Reports</Link> and <Link className="underline" href="/news">Market news</Link>.</p>
    </>}
  </div>;
}
