'use client';

import { useEffect, useState, useRef, useCallback, useMemo } from 'react';
import { useRouter } from 'next/navigation';
import { API_BASE } from '@/lib/serviceUrls';
import { apiFetch } from '@/lib/apiFetch';
import { requireOk } from '@/lib/apiError';
import type { ReportSummary, ReportPaginationResponse } from '@/types/stock';
import ReportCoverageDashboard from '@/components/ReportCoverageDashboard';
import {
  formatArticlesCited,
  formatArticlesSupplied,
  formatReportDateTime,
  getPromptBadge,
} from '@/lib/reportPresentation';
import dynamic from 'next/dynamic';

const ReportGenerator = dynamic(() => import('@/components/ReportGenerator'), {
  loading: () => <p role="status" className="py-4 text-sm">Loading report generator…</p>,
});

interface ReportCompanyOption {
  ticker: string;
  company_name: string;
  report_count: number;
}

export default function ReportsPage() {
  const router = useRouter();

  // ---- Saved reports state ----
  const [reports, setReports] = useState<ReportSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(false);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [limit] = useState(20);

  // ---- Filters ----
  const [tickerFilter, setTickerFilter] = useState('');
  const [debouncedFilter, setDebouncedFilter] = useState('');
  const debounceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const [sort, setSort] = useState<'newest' | 'oldest'>('newest');
  const [reportCompanies, setReportCompanies] = useState<ReportCompanyOption[]>([]);
  const [companyFilterError, setCompanyFilterError] = useState(false);
  const [watchlistCompanyNames, setWatchlistCompanyNames] = useState<Record<string, string>>({});
  const companyOptions = useMemo(() => reportCompanies.map(company => ({
    ...company,
    company_name: company.company_name === company.ticker
      ? watchlistCompanyNames[company.ticker] || company.ticker
      : company.company_name,
  })).sort((a, b) => a.company_name.localeCompare(b.company_name)), [reportCompanies, watchlistCompanyNames]);

  const fetchReportCompanies = useCallback(async (signal?: AbortSignal) => {
    try {
      const res = await apiFetch(`${API_BASE}/api/analysis/reports/companies`, { signal });
      await requireOk(res, 'Failed to fetch report companies');
      const companies: ReportCompanyOption[] = await res.json();
      if (signal?.aborted) return;
      setReportCompanies(companies);
      setCompanyFilterError(false);
    } catch {
      if (!signal?.aborted) setCompanyFilterError(true);
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    const timer = setTimeout(() => { void fetchReportCompanies(controller.signal); }, 0);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [fetchReportCompanies]);

  const [showGenerator, setShowGenerator] = useState(false);
  const [generatorLoaded, setGeneratorLoaded] = useState(false);
  const [coverageRevision, setCoverageRevision] = useState(0);

  // ---- Debounce cleanup on unmount ----
  useEffect(() => {
    return () => {
      if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);
      if (abortControllerRef.current) abortControllerRef.current.abort();
    };
  }, []);

  // ---- Fetch saved reports with abort support ----
  const doFetch = useCallback(async (pg: number, lim: number, st: string, tf: string) => {
    // Abort any in-flight request
    if (abortControllerRef.current) abortControllerRef.current.abort();
    const controller = new AbortController();
    abortControllerRef.current = controller;

    setLoading(true);
    setFetchError(null);
    try {
      const params = new URLSearchParams();
      params.set('page', String(pg));
      params.set('limit', String(lim));
      params.set('sort', st);
      if (tf) params.set('ticker', tf.toUpperCase());

      const res = await apiFetch(`${API_BASE}/api/analysis/reports/?${params}`, { signal: controller.signal });
      await requireOk(res, 'Failed to fetch reports');
      const data: ReportPaginationResponse = await res.json();
      if (controller.signal.aborted) return;
      setReports(data.items);
      setTotal(data.total);
      setHasMore(data.has_more);
    } catch (e) {
      if (!controller.signal.aborted) {
        console.error('[Reports] Fetch error:', e);
        setFetchError(e instanceof Error ? e.message : 'Failed to load reports');
      }
    } finally {
      if (!controller.signal.aborted) setLoading(false);
    }
  }, []);

  // ---- Debounce ticker filter: wait 400ms after last keystroke, then fetch ----
  useEffect(() => {
    if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);
    const normalized = tickerFilter.trim().toUpperCase();
    if (normalized === debouncedFilter) return;
    debounceTimerRef.current = setTimeout(() => {
      setDebouncedFilter(normalized);
      setPage(1);
    }, 400);
  }, [tickerFilter, debouncedFilter]);

  // ---- Fetch when debounced filter, page, or sort changes ----
  useEffect(() => {
    const timer = setTimeout(() => { void doFetch(page, limit, sort, debouncedFilter); }, 0);
    return () => { clearTimeout(timer); abortControllerRef.current?.abort(); };
  }, [page, limit, sort, debouncedFilter, doFetch]);

  // ---- Delete handler (re-fetches to trigger re-numbering) ----
  const handleDeleteReport = async (reportId: number) => {
    if (!confirm('Are you sure you want to delete this report?')) return;
    try {
      const res = await apiFetch(`${API_BASE}/api/analysis/reports/${reportId}`, { method: 'DELETE' });
      await requireOk(res, 'Failed to delete report');
      // Re-fetch reports to trigger numbering recalculation
      await doFetch(page, limit, sort, tickerFilter);
      fetchReportCompanies();
      setCoverageRevision(value => value + 1);
    } catch (e) {
      console.error(e);
      alert('Could not delete report');
    }
  };

  const applyCompanyFilter = (ticker: string) => {
    if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);
    setTickerFilter(ticker);
    setDebouncedFilter(ticker);
    setPage(1);
  };

  const resetFilters = () => {
    applyCompanyFilter('');
    setSort('newest');
    setPage(1);
  };

  const getSentimentColor = (sentiment: string) => {
    switch (sentiment) {
      case 'Very Bullish': return '#166b52';
      case 'Bullish': return '#287b61';
      case 'Neutral': return '#805d17';
      case 'Bearish': return '#b1364e';
      case 'Very Bearish': return '#b1364e';
      default: return 'var(--text-muted)';
    }
  };

  const hasActiveFilters = tickerFilter;

  return (
    <div className="workspace-page reports-workspace">
      <div className="page-heading overview-heading">
        <div>
          <p className="eyebrow"><span className="accent-line" /> Research library</p>
          <h1>Your research library.</h1>
          <p>Keep your research current. Bring company news and analysis together.</p>
        </div>
      </div>
      <ReportCoverageDashboard revision={coverageRevision} onSelectTicker={ticker => {
        applyCompanyFilter(ticker);
        document.getElementById('saved-reports')?.scrollIntoView({ behavior: 'smooth' });
      }} />

      {/* ============================================================ */}
      {/* SECTION: My Reports (Saved) - Container Wrapper              */}
      {/* ============================================================ */}
      <div id="saved-reports" style={{
        padding: '1.5rem', borderRadius: '12px', marginBottom: '2rem',
        background: 'var(--section-bg)', border: '1px solid var(--card-border)',
      }}
      className="dark:bg-slate-800 dark:border-slate-700">
        <h2 style={{ margin: '0 0 1rem', fontSize: '1.125rem', fontWeight: 600, color: 'var(--text-primary)' }}
          className="dark:text-white">
          Saved reports
        </h2>

        {/* Filters */}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.75rem', marginBottom: '1.5rem', alignItems: 'center' }}>
          <label htmlFor="report-company-filter" style={{ fontSize: '0.875rem', fontWeight: 600 }}>
            Company
          </label>
          <select
            id="report-company-filter"
            value={tickerFilter.trim().toUpperCase()}
            onChange={e => applyCompanyFilter(e.target.value)}
            style={{
              padding: '0.5rem 0.75rem', borderRadius: '6px', border: '1px solid var(--card-border)',
              fontSize: '0.875rem', background: 'var(--card-bg)', color: 'var(--text-secondary)',
              maxWidth: '100%', flex: '1 1 260px', minWidth: 0,
            }}
            className="dark:bg-slate-900 dark:border-slate-600 dark:text-gray-200"
          >
            <option value="">All companies</option>
            {tickerFilter.trim() && !companyOptions.some(company => company.ticker === tickerFilter.trim().toUpperCase()) && (
              <option value={tickerFilter.trim().toUpperCase()}>{tickerFilter.trim().toUpperCase()}</option>
            )}
            {companyOptions.map(company => (
              <option key={company.ticker} value={company.ticker}>
                {company.company_name === company.ticker ? company.ticker : `${company.company_name} (${company.ticker})`} · {company.report_count} report{company.report_count !== 1 ? 's' : ''}
              </option>
            ))}
          </select>
        <button type="button" aria-expanded={showGenerator} aria-controls="report-generator-panel" onClick={() => { setGeneratorLoaded(true); setShowGenerator(value => !value); }} className="button-primary">
          {showGenerator ? 'Close generator' : '+ New report'}
        </button>
          <input
            type="text"
            aria-label="Filter reports by ticker"
            placeholder="Or enter a ticker…"
            value={tickerFilter}
            onChange={e => setTickerFilter(e.target.value)}
            style={{
              padding: '0.5rem 0.75rem', borderRadius: '6px', border: '1px solid var(--card-border)',
              fontSize: '0.875rem', outline: 'none', minWidth: '120px',
              background: 'var(--card-bg)', color: 'var(--text-secondary)',
            }}
            className="dark:bg-slate-900 dark:border-slate-600 dark:text-gray-200"
          />

          <select
            value={sort}
            onChange={e => setSort(e.target.value as 'newest' | 'oldest')}
            style={{
              padding: '0.5rem 0.75rem', borderRadius: '6px', border: '1px solid var(--card-border)',
              fontSize: '0.875rem', outline: 'none', background: 'var(--card-bg)', color: 'var(--text-secondary)',
            }}
            className="dark:bg-slate-900 dark:border-slate-600 dark:text-gray-200"
          >
            <option value="newest">Newest First</option>
            <option value="oldest">Oldest First</option>
          </select>

          {hasActiveFilters && (
            <button onClick={resetFilters} style={{
              padding: '0.5rem 0.75rem', borderRadius: '6px', border: 'none',
              background: 'var(--card-border)', color: 'var(--text-secondary)', fontSize: '0.875rem', cursor: 'pointer', fontWeight: 600,
            }}
            className="dark:bg-slate-700 dark:text-gray-200">
              Clear
            </button>
          )}

          <span style={{ fontSize: '0.875rem', color: 'var(--text-muted)', marginLeft: 'auto' }}
            className="dark:text-slate-400">
            {total} report{total !== 1 ? 's' : ''} found
          </span>
        </div>

        <div id="report-generator-panel" hidden={!showGenerator}>
          {generatorLoaded && (
        <ReportGenerator onCompanyNames={setWatchlistCompanyNames} onGenerated={() => {
          setPage(1);
          doFetch(1, limit, sort, tickerFilter);
          fetchReportCompanies();
          setCoverageRevision(value => value + 1);
        }} />
          )}
        </div>

        {companyFilterError && (
          <p role="status" style={{ fontSize: '0.875rem', marginTop: '-0.75rem', marginBottom: '1rem' }}>
            Company choices are unavailable. You can still filter by ticker.{' '}
            <button type="button" onClick={() => fetchReportCompanies()} className="underline">Retry</button>
          </p>
        )}

        {/* Fetch Error Banner */}
        {fetchError && (
          <div style={{
            marginBottom: '1rem', padding: '0.75rem 1rem', borderRadius: '8px',
            background: 'var(--negative-soft)', border: '1px solid var(--negative-border)', color: 'var(--negative)', fontSize: '0.875rem',
          }}
          className="dark:bg-negative-soft/30 dark:border-negative-border dark:text-negative">
            <strong>Error:</strong> {fetchError}
          </div>
        )}

        {/* Report List */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
          {loading && reports.length === 0 ? (
            Array.from({ length: 4 }).map((_, i) => (
              <div key={i} style={{ padding: '1rem', borderRadius: '8px', background: 'var(--section-bg)', border: '1px solid var(--card-border)' }}
                className="dark:bg-slate-800 dark:border-slate-700">
                Loading...
              </div>
            ))
          ) : reports.length === 0 ? (
            <div style={{ padding: '2rem', borderRadius: '8px', background: 'var(--section-bg)', textAlign: 'center', color: 'var(--text-muted)' }}
              className="dark:bg-slate-800 dark:text-slate-400">
              {hasActiveFilters ? `No reports found for ${debouncedFilter || tickerFilter}. Try another company or clear the filter.` : 'No reports yet. Select “New report” above to create your first analysis.'}
            </div>
          ) : (
            reports.map((report) => (
              <div
                key={report.id}
                style={{
                  display: 'flex', alignItems: 'center', gap: '1rem',
                  padding: '1rem', borderRadius: '8px',
                  background: 'var(--card-bg)', border: '1px solid var(--card-border)', cursor: 'pointer',
                  transition: 'box-shadow 0.15s ease, background 0.15s ease',
                }}
                className="dark:bg-slate-800 dark:border-slate-700"
                onClick={() => router.push(`/analysis/reports/${report.id}`)}
                onMouseEnter={e => { e.currentTarget.style.boxShadow = '0 2px 8px rgba(0,0,0,0.1)'; }}
                onMouseLeave={e => { e.currentTarget.style.boxShadow = 'none'; }}
              >
                {/* Descriptive report label */}
                <div style={{ minWidth: '170px' }}>
                  <div style={{ fontWeight: 700, fontSize: '1.125rem', color: 'var(--text-primary)' }}
                    className="dark:text-white">
                    {report.ticker} Analysis
                  </div>
                  <div style={{ marginTop: 2, fontSize: '0.75rem', color: 'var(--text-muted)' }}
                    className="dark:text-slate-400">
                    {formatReportDateTime(report.created_at)}
                  </div>
                </div>

                {/* Sentiment badge */}
                <span style={{
                  padding: '0.25rem 0.75rem', borderRadius: '999px',
                  background: getSentimentColor(report.overall_sentiment),
                  color: 'white', fontSize: '0.75rem', fontWeight: 600, whiteSpace: 'nowrap',
                }}>
                  {report.overall_sentiment}
                </span>

                {/* Confidence bar */}
                <div style={{ flex: 1, maxWidth: '160px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: '2px' }}
                    className="dark:text-slate-400">
                    <span>Confidence</span>
                    <span style={{ fontWeight: 600 }}>{report.confidence_score}%</span>
                  </div>
                  <div style={{ height: 4, borderRadius: 2, background: 'var(--card-border)', overflow: 'hidden' }}
                    className="dark:bg-slate-600">
                    <div style={{
                      width: `${report.confidence_score}%`, height: '100%', borderRadius: 2,
                      background: report.confidence_score > 70 ? '#166b52' : report.confidence_score > 40 ? '#805d17' : '#b1364e',
                    }} />
                  </div>
                </div>

                {/* Price */}
                {report.current_price_at_analysis != null && (
                  <div style={{ fontSize: '0.875rem', color: 'var(--text-secondary)', fontWeight: 500 }}
                    className="dark:text-gray-300">
                    ${Number(report.current_price_at_analysis).toFixed(2)}
                  </div>
                )}

                {/* Articles count */}
                <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}
                  className="dark:text-slate-500">
                  <div>{formatArticlesSupplied(report.articles_count)}</div>
                  <div>{formatArticlesCited(report.articles_cited_count ?? 0)}</div>
                </div>

                {/* Prompt version & model */}
                <div style={{ textAlign: 'right', fontSize: '0.75rem', color: 'var(--text-muted)' }}
                  className="dark:text-slate-500">
                  <div style={{ fontWeight: 600, color: report.prompt_hash ? 'var(--info)' : 'var(--text-muted)' }}>
                    {getPromptBadge(report.prompt_version, report.prompt_hash)}
                  </div>
                  <div>{report.model_used}</div>
                </div>

                {/* Delete button */}
                <button
                  onClick={(e) => { e.stopPropagation(); handleDeleteReport(report.id); }}
                  style={{
                    padding: '0.25rem 0.5rem', borderRadius: '4px', border: '1px solid #fca5a5',
                    background: 'transparent', color: 'var(--negative)', fontSize: '0.75rem', cursor: 'pointer',
                    display: 'flex', alignItems: 'center',
                  }}
                  className="dark:border-negative-border dark:text-negative"
                  title="Delete report"
                >
                  <svg width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                  </svg>
                </button>

                {/* Arrow */}
                <svg width="16" height="16" style={{ color: 'var(--text-muted)', minWidth: '16px' }} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
                </svg>
              </div>
            ))
          )}
        </div>

        {/* Pagination */}
        {reports.length > 0 && (
          <div style={{ display: 'flex', justifyContent: 'center', gap: '0.5rem', marginTop: '1.5rem' }}>
            <button
              onClick={() => setPage(p => Math.max(1, p - 1))}
              disabled={page <= 1 || loading}
              style={{
                padding: '0.5rem 1rem', borderRadius: '6px', border: '1px solid var(--card-border)',
                background: page <= 1 ? 'var(--section-bg)' : 'white', cursor: page <= 1 ? 'not-allowed' : 'pointer',
                fontSize: '0.875rem', color: 'var(--text-secondary)',
              }}
              className="dark:bg-slate-800 dark:border-slate-600 dark:text-gray-200 dark:disabled:bg-slate-700"
            >
              ← Previous
            </button>

            <span style={{ padding: '0.5rem 1rem', fontSize: '0.875rem', color: 'var(--text-muted)' }}
              className="dark:text-slate-400">
              Page {page}
            </span>

            <button
              onClick={() => setPage(p => p + 1)}
              disabled={!hasMore || loading}
              style={{
                padding: '0.5rem 1rem', borderRadius: '6px', border: '1px solid var(--card-border)',
                background: !hasMore ? 'var(--section-bg)' : 'white', cursor: !hasMore ? 'not-allowed' : 'pointer',
                fontSize: '0.875rem', color: 'var(--text-secondary)',
              }}
              className="dark:bg-slate-800 dark:border-slate-600 dark:text-gray-200 dark:disabled:bg-slate-700"
            >
              Next →
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
