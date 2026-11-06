'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { apiFetch } from '@/lib/apiFetch';
import { requireOk } from '@/lib/apiError';
import { API_BASE } from '@/lib/serviceUrls';
import { dailySyncStatus, filterDailyTickers, type DailyTickerFilter, type DailyUpdateSync } from '@/lib/dailyUpdatesPresentation';

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
  const [actionError, setActionError] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState('');
  const [removingTicker, setRemovingTicker] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState<DailyTickerFilter>('all');
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
    setBusy(key); setError(''); setActionError(''); setMessage('');
    try {
      const next = await requestSettings(path, { method, headers: { 'Content-Type': 'application/json' }, ...(body ? { body: JSON.stringify(body) } : {}) });
      if (version !== generation.current) return;
      setSettings(next);
      setMessage(next.sync_pending ? 'Saved on the live site. Local synchronization is pending.' : 'Settings saved. The local automation will acknowledge the change below.');
      if (key === 'add') setTicker('');
    } catch (err) {
      if (version === generation.current) setActionError(err instanceof Error ? err.message : 'Could not save settings');
    } finally {
      busyRef.current = false;
      if (version === generation.current) setBusy('');
    }
  }

  const sync = settings ? dailySyncStatus(settings) : null;
  const visibleTickers = filterDailyTickers(settings?.tickers ?? [], search, filter);
  const disabled = !!busy || !settings?.shared_settings_ready;

  function renderSwitch(item: TickerPreference, field: 'news_enabled' | 'reports_enabled', showLabel = false) {
    const label = field === 'news_enabled' ? 'Collect news' : 'Daily report';
    return <button type="button" role="switch" aria-checked={item[field]} aria-label={`${label} for ${item.ticker}`} disabled={disabled}
      className={`daily-switch${showLabel ? '' : ' daily-switch-compact'}`} onClick={() => void change(item.ticker, `/tickers/${item.ticker}`, 'PATCH', {
        news_enabled: item.news_enabled, reports_enabled: item.reports_enabled, [field]: !item[field],
      })}>
      {showLabel && <span>{label}</span>}
      <span className="daily-switch-value" aria-hidden="true"><span className="daily-switch-track"><span /></span><span>{item[field] ? 'On' : 'Off'}</span></span>
    </button>;
  }

  function renderRemoval(item: TickerPreference) {
    return removingTicker === item.ticker ? <div className="daily-remove-confirm">
      <p>Remove {item.ticker} from the watchlist and daily updates?</p>
      <div><button type="button" disabled={!!busy} onClick={() => setRemovingTicker(null)}>Keep ticker</button>
        <button type="button" disabled={!!busy} aria-label={`Confirm removal of ${item.ticker}`} onClick={() => {
          setRemovingTicker(null); void change(item.ticker, `/tickers/${item.ticker}`, 'DELETE');
        }}>Remove</button></div>
    </div> : <button type="button" className="daily-remove-button" disabled={disabled} onClick={() => setRemovingTicker(item.ticker)}>Remove<span className="sr-only"> {item.ticker}</span></button>;
  }

  function renderNewsStatus(item: TickerPreference) {
    return <div className="daily-news-status"><span>{newsLabel(item.news_status)}</span>
      {settings?.local_status[item.ticker] && <span>Local: {newsLabel(settings.local_status[item.ticker].status)}</span>}
    </div>;
  }

  return <div className="daily-updates-page mx-auto w-full max-w-5xl px-4 py-6 md:py-8">
    <div className="daily-page-heading mb-5 flex items-start justify-between gap-3">
      <div><p className="text-sm opacity-60">Your collection preferences</p><h1 className="mt-1 text-3xl font-semibold">Daily updates</h1>
        <p className="mt-3 max-w-2xl text-sm opacity-75">One ticker list for the live site and your local automation. Choose which companies receive news, daily reports, or both.</p></div>
      <button type="button" className="button-secondary daily-refresh" disabled={!!busy} onClick={() => void load()}>Refresh<span className="daily-desktop-inline"> status</span></button>
    </div>
    {(actionError || error) && <p role="alert" className="mb-4 rounded-lg border border-red-500/40 p-3 text-sm">{actionError || error}</p>}
    {message && <p role="status" className="mb-4 rounded-lg border border-emerald-500/40 p-3 text-sm">{message}</p>}
    {!settings ? <p role="status">{error ? 'Settings unavailable. Refresh to try again.' : 'Loading daily update settings…'}</p> : <>
      {!settings.shared_settings_ready && <p role="status" className="mb-4 rounded-xl border p-4 text-sm">Shared controls are waiting for the live deployment and local synchronization to be enabled. The list below currently reflects this computer; editing will be available once connected.</p>}
      <section aria-label="Local synchronization" className="surface daily-sync-panel mb-4">
        <h2 className="font-semibold">{sync?.label}</h2>
        <div className="daily-desktop-only"><p className="mt-2 text-sm opacity-75">{sync?.detail}</p>
          <p className="mt-3 text-xs opacity-60">Last local check-in: {timestamp(settings.last_seen_at)} · Settings received: {timestamp(settings.applied_at)}</p></div>
        <details className="daily-mobile-only daily-sync-details"><summary>Sync details</summary>
          <p>{sync?.detail}</p><p>Last local check-in: {timestamp(settings.last_seen_at)}</p><p>Settings received: {timestamp(settings.applied_at)}</p>
        </details>
      </section>
      <form id="daily-add-ticker" className="surface daily-add-form mb-5" onSubmit={event => {
        event.preventDefault();
        if (disabled) return;
        void change('add', '/tickers', 'POST', { ticker: ticker.trim().toUpperCase(), news_enabled: true, reports_enabled: true });
      }}>
        <label>Add a ticker<input aria-label="Ticker to add" value={ticker} onChange={event => setTicker(event.target.value.toUpperCase())} placeholder="e.g. MSFT" maxLength={10} pattern="[A-Za-z0-9]+" autoCapitalize="characters" autoCorrect="off" spellCheck={false} required disabled={!!busy} /></label>
        <button className="button-primary" type="submit" disabled={!!busy || !settings.shared_settings_ready || !ticker.trim() || settings.tickers.length >= settings.max_tickers}>{busy === 'add' ? 'Adding…' : 'Add ticker'}</button>
        <p>News is queued immediately. Daily reports join the next weekday run.</p>
      </form>

      <div className="daily-filters">
        <label>Search tickers<input type="search" value={search} onChange={event => setSearch(event.target.value)} placeholder="Find ticker" aria-label="Search daily update tickers" autoCapitalize="characters" spellCheck={false} /></label>
        <label>Show<select value={filter} onChange={event => setFilter(event.target.value as DailyTickerFilter)} aria-label="Filter daily update tickers">
          <option value="all">All tickers</option><option value="news">News on</option><option value="reports">Reports on</option><option value="paused">Fully paused</option>
        </select></label>
      </div>
      <div className="daily-list-heading"><p role="status">Showing {visibleTickers.length} of {settings.tickers.length} tickers <span>· Maximum {settings.max_tickers}</span></p>
        {(search || filter !== 'all') && <button type="button" onClick={() => { setSearch(''); setFilter('all'); }}>Clear filters</button>}
        <a href="#daily-add-ticker" className="daily-add-shortcut daily-mobile-only">+ Add ticker</a>
      </div>

      <ul aria-label="Daily update tickers" className="daily-ticker-cards daily-mobile-only">
        {visibleTickers.map(item => <li key={item.ticker}><article className="surface daily-ticker-card" aria-labelledby={`daily-card-${item.ticker}`}>
          <div className="daily-card-heading"><div><h2 id={`daily-card-${item.ticker}`}>{item.ticker}</h2>{!item.news_enabled && !item.reports_enabled && <span className="daily-paused-badge">Fully paused</span>}</div>{renderRemoval(item)}</div>
          <div className="daily-card-controls">{renderSwitch(item, 'news_enabled', true)}{renderSwitch(item, 'reports_enabled', true)}</div>
          <div className="daily-card-footer">{renderNewsStatus(item)}{busy === item.ticker && <p role="status">Saving {item.ticker}…</p>}</div>
        </article></li>)}
      </ul>

      <div className="surface daily-desktop-only overflow-x-auto rounded-xl border">
        <table className="w-full text-left text-sm"><caption className="sr-only">Daily update preferences</caption>
          <thead><tr className="border-y"><th className="p-4">Ticker</th><th className="p-4">Collect news</th><th className="p-4">Daily report</th><th className="p-4">Initial news fetch</th><th className="p-4"><span className="sr-only">Actions</span></th></tr></thead>
          <tbody>{visibleTickers.map(item => <tr key={item.ticker} className="border-b last:border-0">
            <th scope="row" className="p-4 font-semibold">{item.ticker}</th>
            {(['news_enabled', 'reports_enabled'] as const).map(field => <td className="p-4" key={field}>{renderSwitch(item, field)}</td>)}
            <td className="p-4 text-xs">{renderNewsStatus(item)}</td>
            <td className="p-4 text-right">{renderRemoval(item)}</td>
          </tr>)}</tbody>
        </table>
      </div>
      {!visibleTickers.length && <p className="surface p-5 text-sm opacity-70">{settings.tickers.length ? 'No tickers match these filters. Clear the filters to see your full list.' : 'No tickers selected. Add one above to start collecting news and include it in daily updates.'}</p>}
      {busy && <p role="status" className="mt-3 text-sm">{busy === 'add' ? 'Adding ticker and queuing news…' : `Saving ${busy}…`}</p>}
      <p className="mt-5 text-sm opacity-70">News follows its collection schedule every day; daily reports run on weekdays. Reports can use previously collected articles when news is paused. Changes apply after the local automation receives them. An article fetch or report already in progress may finish.</p>
      <p className="mt-3 text-sm opacity-70">Removing a ticker also removes it from the overview watchlist. Your existing research stays available in <Link className="underline" href="/analysis/reports">Reports</Link> and <Link className="underline" href="/news">Market news</Link>.</p>
    </>}
  </div>;
}
