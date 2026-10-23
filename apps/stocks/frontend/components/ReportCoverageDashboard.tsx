'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { apiFetch } from '@/lib/apiFetch';
import { requireOk } from '@/lib/apiError';
import { API_BASE } from '@/lib/serviceUrls';
import { formatReportDateTime } from '@/lib/reportPresentation';
import { EASTERN_TIME_ZONE } from '@/lib/formatters';

type Status = 'current' | 'outdated' | 'missing';
interface CoverageItem {
  ticker: string;
  company_name: string;
  status: Status;
  report_id: number | null;
  created_at: string | null;
  overall_sentiment: string | null;
  confidence_score: number | null;
}
interface Coverage {
  as_of: string;
  expected_date: string;
  total: number;
  counts: Record<Status, number>;
  items: CoverageItem[];
  fresh_reports: CoverageItem[];
  important_news: { id: number; ticker: string; title: string; provider_name: string | null; pub_date: string; reason: string; article_url: string | null }[];
}
const labels: Record<Status, string> = { current: 'Current', outdated: 'Needs update', missing: 'No report' };
const colors: Record<Status, string> = {
  current: 'bg-positive-soft text-positive dark:bg-positive-soft dark:text-positive',
  outdated: 'bg-warning-soft text-warning dark:bg-warning-soft dark:text-warning',
  missing: 'bg-slate-100 text-slate-700 dark:bg-slate-700 dark:text-slate-200',
};
const card = 'surface p-5';

export default function ReportCoverageDashboard({ onSelectTicker, revision = 0 }: {
  onSelectTicker: (ticker: string) => void;
  revision?: number;
}) {
  const [data, setData] = useState<Coverage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<'all' | Status>('all');
  const [search, setSearch] = useState('');
  const [refresh, setRefresh] = useState(0);
  const [refreshMessage, setRefreshMessage] = useState('');
  const [lastCheckedAt, setLastCheckedAt] = useState<Date | null>(null);
  const reload = useCallback(() => {
    setLoading(true);
    setError(null);
    setRefreshMessage('');
    setRefresh(value => value + 1);
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    const timer = setTimeout(() => {
      setLoading(true);
      setError(null);
      void (async () => {
        try {
          const response = await apiFetch(`${API_BASE}/api/analysis/reports/coverage`, { signal: controller.signal, cache: 'no-store' });
          await requireOk(response, 'Unable to load report coverage');
          const result: Coverage = await response.json();
          if (!controller.signal.aborted) {
            setData(result);
            setLastCheckedAt(new Date());
            setRefreshMessage(refresh > 0 ? `Refresh complete — ${result.total} compan${result.total === 1 ? 'y' : 'ies'} checked. Reports and headlines may be unchanged.` : '');
          }
        } catch (failure) {
          if (!controller.signal.aborted) setError(failure instanceof Error ? failure.message : 'Unable to load coverage');
        } finally {
          if (!controller.signal.aborted) setLoading(false);
        }
      })();
    }, 0);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [refresh, revision]);

  const query = search.trim().toLowerCase();
  const items = data?.items.filter(item => (filter === 'all' || item.status === filter)
    && `${item.ticker} ${item.company_name}`.toLowerCase().includes(query)) ?? [];

  return (
    <section aria-labelledby="coverage-heading" aria-busy={loading} className="mb-8 space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 id="coverage-heading" className="text-lg font-semibold tracking-tight">Report coverage</h2>
          <p className="mt-1 text-sm text-muted dark:text-slate-400">Fresh research and news worth a closer look.</p>
        </div>
        <div className="flex flex-col items-end gap-2">
          <button type="button" onClick={reload} disabled={loading} aria-busy={loading} aria-controls="coverage-refresh-status" className="inline-flex items-center gap-2 rounded-lg border border-divider px-4 py-2 text-sm disabled:cursor-wait disabled:opacity-60 dark:border-slate-600">
            {loading && <span aria-hidden="true" className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent motion-reduce:animate-none" />}
            {loading ? 'Refreshing…' : 'Refresh'}
          </button>
          {lastCheckedAt && <span className="text-xs text-muted dark:text-slate-400">Last checked {lastCheckedAt.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit', timeZone: EASTERN_TIME_ZONE, timeZoneName: 'short' })}</span>}
        </div>
      </div>
      <p id="coverage-refresh-status" role="status" className="text-sm text-positive dark:text-positive">
        {loading ? 'Checking report coverage and headlines…' : !error && refreshMessage}
      </p>
      {error && <p role="alert" className="rounded-lg bg-negative-soft p-3 text-sm text-negative dark:bg-negative-soft dark:text-negative">Refresh failed: {error} {data && 'Showing the last loaded snapshot.'} <button onClick={reload} disabled={loading} className="underline">Retry</button></p>}
      {!data && loading && <div role="status" className="grid grid-cols-2 gap-3 sm:grid-cols-4">{['Watchlist', 'Current', 'Needs update', 'No report'].map(label => <div key={label} className={card}><p className="text-sm">{label}</p><div className="mt-3 h-8 animate-pulse rounded bg-surface-muted dark:bg-slate-700" /></div>)}</div>}
      {data && <>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {(['all', 'current', 'outdated', 'missing'] as const).map(status => <button key={status} type="button" aria-pressed={filter === status} onClick={() => setFilter(status)} className={`${card} text-left ${filter === status ? 'ring-2 ring-accent' : ''}`}>
            <p className="text-sm text-muted dark:text-slate-400">{status === 'all' ? 'Watchlist' : labels[status]}</p>
            <p className="mt-1 text-3xl font-bold">{status === 'all' ? data.total : data.counts[status]}</p>
          </button>)}
        </div>
        <p className="text-xs text-muted dark:text-slate-400">Current = a report dated {data.expected_date} or later in Eastern time. Based on the weekday 8:30 PM schedule; a due run may still be processing. Updated {formatReportDateTime(data.as_of)}.</p>
        <div className={card}>
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <h2 className="font-semibold">Company coverage</h2>
            <input type="search" aria-label="Search company coverage" placeholder="Find a ticker or company…" value={search} onChange={event => setSearch(event.target.value)} className="w-full rounded-lg border border-divider bg-transparent px-3 py-2 text-sm sm:w-64 dark:border-slate-600" />
          </div>
          <div className="max-h-96 overflow-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-xs text-muted dark:text-slate-400"><tr><th className="pb-3 pr-4">Company</th><th className="pb-3 pr-4">Coverage</th><th className="pb-3 pr-4">Latest report</th><th className="pb-3">Browse</th></tr></thead>
              <tbody>{items.map(item => <tr key={item.ticker} className="border-t border-divider dark:border-slate-700">
                <td className="py-3 pr-4"><strong>{item.ticker}</strong>{item.company_name !== item.ticker && <p className="max-w-48 truncate text-xs text-muted">{item.company_name}</p>}</td>
                <td className="py-3 pr-4"><span className={`whitespace-nowrap rounded-full px-2 py-1 text-xs ${colors[item.status]}`}>{labels[item.status]}</span></td>
                <td className="py-3 pr-4">{item.report_id && item.created_at ? <Link prefetch={false} href={`/analysis/reports/${item.report_id}`} className="text-accent underline dark:text-accent">{formatReportDateTime(item.created_at)}</Link> : 'Not generated yet'}</td>
                <td className="py-3"><button onClick={() => onSelectTicker(item.ticker)} className="text-accent underline dark:text-accent" aria-label={`Browse ${item.ticker} reports`}>Reports</button></td>
              </tr>)}</tbody>
            </table>
            {items.length === 0 && <p className="py-6 text-center text-sm text-muted">{data.total ? 'No companies match these filters.' : 'Add companies to your watchlist to track coverage.'}</p>}
          </div>
        </div>
        <div className="grid gap-5 md:grid-cols-2">
          <div className={card}>
            <h2 className="font-semibold">Fresh reports</h2>
            <p className="mt-1 text-xs text-muted dark:text-slate-400">Latest current report per company.</p>
            <ul className="mt-3 divide-y divide-gray-100 dark:divide-slate-700">{data.fresh_reports.map(item => <li key={item.ticker} className="py-3"><Link prefetch={false} href={`/analysis/reports/${item.report_id}`} className="block hover:text-accent"><span className="font-semibold">{item.ticker}</span> <span className="text-sm">· {item.overall_sentiment}</span><p className="mt-1 text-xs text-muted dark:text-slate-400">{formatReportDateTime(item.created_at!)} · {item.confidence_score}% confidence</p></Link></li>)}</ul>
            {!data.fresh_reports.length && <p className="mt-4 text-sm text-muted">No reports are current for the latest scheduled day.</p>}
          </div>
          <div className={card}>
            <h2 className="font-semibold">Important news</h2>
            <p className="mt-1 text-xs text-muted dark:text-slate-400">Recent watchlist headlines flagged by event keywords, including earnings, deals and regulatory news. Past 72 hours.</p>
            <ul className="mt-3 divide-y divide-gray-100 dark:divide-slate-700">{data.important_news.map(article => <li key={article.id} className="py-3"><span className="text-xs font-semibold text-accent dark:text-accent">{article.ticker} · {article.reason}</span><a href={article.article_url && /^https?:\/\//i.test(article.article_url) ? article.article_url : `/news/${encodeURIComponent(article.ticker)}`} target="_blank" rel="noopener noreferrer" className="mt-1 block text-sm font-medium hover:underline">{article.title}</a><p className="mt-1 text-xs text-muted dark:text-slate-400">{article.provider_name || 'News'} · {formatReportDateTime(article.pub_date)}</p></li>)}</ul>
            {!data.important_news.length && <p className="mt-4 text-sm text-muted">No recent headlines matched the event filters.</p>}
          </div>
        </div>
      </>}
    </section>
  );
}
