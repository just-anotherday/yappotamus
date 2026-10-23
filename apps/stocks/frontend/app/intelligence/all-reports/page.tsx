'use client';

import { useEffect, useState, useCallback } from 'react';
import Link from 'next/link';
import { fetchUnifiedReports } from '@/lib/api';
import { formatApiTimestamp } from '@/lib/formatters';
import type { UnifiedReportEntry } from '@/lib/api';

type ReportKind = 'company' | 'sector' | 'market';
interface AppliedFilters { ticker: string; type: ReportKind | ''; sentiment: string; from: string; to: string }
const EMPTY_FILTERS: AppliedFilters = { ticker: '', type: '', sentiment: '', from: '', to: '' };

export default function UnifiedIntelligenceBrowser() {
  const [reports, setReports] = useState<UnifiedReportEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [hasMore, setHasMore] = useState(false);

  // Filters
  const [tickerFilter, setTickerFilter] = useState<string>('');
  const [typeFilter, setTypeFilter] = useState<ReportKind | ''>('');
  const [sentimentFilter, setSentimentFilter] = useState<string>('');
  const [dateFrom, setDateFrom] = useState<string>('');
  const [dateTo, setDateTo] = useState<string>('');

  const [applied, setApplied] = useState<AppliedFilters>(EMPTY_FILTERS);
  const LIMIT = 20;

  const loadReports = useCallback(async (pageNum: number, signal?: AbortSignal) => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetchUnifiedReports(
        applied.ticker || undefined,
        applied.type || undefined,
        applied.sentiment || undefined,
        applied.from || undefined,
        applied.to || undefined,
        pageNum,
        LIMIT,
        signal,
      );
      if (signal?.aborted) return;
      setReports(res.items);
      setTotal(res.total);
      setHasMore(res.has_more);
    } catch (err) {
      if (!signal?.aborted) setError(err instanceof Error ? err.message : 'Failed to load unified reports');
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, [applied]);

  useEffect(() => {
    const controller = new AbortController();
    const timer = setTimeout(() => { void loadReports(page, controller.signal); }, 0);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [page, loadReports]);

  const handleApplyFilters = () => {
    setPage(1);
    setApplied({ ticker: tickerFilter, type: typeFilter, sentiment: sentimentFilter, from: dateFrom, to: dateTo });
  };

  const handleClearFilters = () => {
    setTickerFilter('');
    setTypeFilter('');
    setSentimentFilter('');
    setDateFrom('');
    setDateTo('');
    setPage(1);
    setApplied({ ...EMPTY_FILTERS });
  };

  const sentimentColor = (sentiment: string) => {
    const s = (sentiment || '').toLowerCase();
    if (s.includes('very bullish')) return '#166b52';
    if (s.includes('bullish')) return 'var(--positive-solid)';
    if (s.includes('neutral')) return '#805d17';
    if (s.includes('bearish')) return 'var(--negative-solid)';
    if (s.includes('very bearish')) return '#b1364e';
    return 'var(--text-muted)';
  };

  const typeIcon = (type: string) => {
    if (type === 'company') return '🏢';
    if (type === 'sector') return '📊';
    if (type === 'market') return '🌐';
    return '📄';
  };

  const typeLabel = (type: string) => {
    if (type === 'company') return 'Company';
    if (type === 'sector') return 'Sector';
    if (type === 'market') return 'Market';
    return type;
  };

  const totalPages = Math.ceil(total / LIMIT);

  // Navigate to the correct detail page based on report type
  const getDetailLink = (entry: UnifiedReportEntry) => {
    if (entry.report_type === 'market') {
      return `/analysis/market-history#${entry.id}`;
    }
    return `/intelligence/${entry.ticker}`;
  };

  return (
    <div style={{ maxWidth: 1100, margin: '0 auto', padding: '40px 20px' }}>
      {/* Header */}
      <div style={{ marginBottom: 32 }}>
        <h1 style={{ fontSize: 28, fontWeight: 800, margin: '0 0 8px', color: 'var(--text-primary)' }}>
          🔍 Unified Intelligence Browser
        </h1>
        <p style={{ color: 'var(--text-muted)', margin: 0, fontSize: 14 }}>
          Browse all AI-generated reports — company analysis, sector insights, and daily market summaries in one place.
        </p>
      </div>

      {/* Actions Bar */}
      <div style={{ display: 'flex', gap: 12, marginBottom: 24 }}>
        <Link href="/analysis/reports" style={{ fontSize: 13, color: 'var(--accent)', textDecoration: 'none', display: 'flex', alignItems: 'center' }}>
          ← Analysis Reports
        </Link>
        <Link href="/analysis/market-history" style={{ fontSize: 13, color: 'var(--accent)', textDecoration: 'none', display: 'flex', alignItems: 'center' }}>
          Market History →
        </Link>
      </div>

      {/* Filters */}
      <div style={{
        padding: 20, marginBottom: 24, background: 'var(--card-bg)', borderRadius: 12,
        border: '1px solid var(--card-border)', display: 'flex', flexWrap: 'wrap', gap: 16, alignItems: 'flex-end',
      }}>
        <div>
          <label style={{ display: 'block', fontSize: 11, fontWeight: 700, color: 'var(--text-muted)', marginBottom: 4, textTransform: 'uppercase' }}>
            Ticker
          </label>
          <input
            type="text"
            value={tickerFilter}
            onChange={e => setTickerFilter(e.target.value.toUpperCase())}
            placeholder="AAPL, SPY..."
            style={{
              padding: '8px 12px', borderRadius: 6, border: '1px solid var(--card-border)',
              fontSize: 13, width: 120, outline: 'none',
            }}
          />
        </div>

        <div>
          <label style={{ display: 'block', fontSize: 11, fontWeight: 700, color: 'var(--text-muted)', marginBottom: 4, textTransform: 'uppercase' }}>
            Report Type
          </label>
          <select
            value={typeFilter}
            onChange={e => setTypeFilter(e.target.value as ReportKind | '')}
            style={{
              padding: '8px 12px', borderRadius: 6, border: '1px solid var(--card-border)',
              fontSize: 13, outline: 'none', background: 'var(--card-bg)',
            }}
          >
            <option value="">All Types</option>
            <option value="company">🏢 Company</option>
            <option value="sector">📊 Sector</option>
            <option value="market">🌐 Market</option>
          </select>
        </div>

        <div>
          <label style={{ display: 'block', fontSize: 11, fontWeight: 700, color: 'var(--text-muted)', marginBottom: 4, textTransform: 'uppercase' }}>
            Sentiment
          </label>
          <select
            value={sentimentFilter}
            onChange={e => setSentimentFilter(e.target.value)}
            style={{
              padding: '8px 12px', borderRadius: 6, border: '1px solid var(--card-border)',
              fontSize: 13, outline: 'none', background: 'var(--card-bg)',
            }}
          >
            <option value="">All Sentiments</option>
            <option value="Very Bullish">Very Bullish</option>
            <option value="Bullish">Bullish</option>
            <option value="Neutral">Neutral</option>
            <option value="Bearish">Bearish</option>
            <option value="Very Bearish">Very Bearish</option>
          </select>
        </div>

        <div>
          <label style={{ display: 'block', fontSize: 11, fontWeight: 700, color: 'var(--text-muted)', marginBottom: 4, textTransform: 'uppercase' }}>
            From
          </label>
          <input
            type="date"
            value={dateFrom}
            onChange={e => setDateFrom(e.target.value)}
            style={{
              padding: '8px 12px', borderRadius: 6, border: '1px solid var(--card-border)',
              fontSize: 13, outline: 'none', width: 140,
            }}
          />
        </div>

        <div>
          <label style={{ display: 'block', fontSize: 11, fontWeight: 700, color: 'var(--text-muted)', marginBottom: 4, textTransform: 'uppercase' }}>
            To
          </label>
          <input
            type="date"
            value={dateTo}
            onChange={e => setDateTo(e.target.value)}
            style={{
              padding: '8px 12px', borderRadius: 6, border: '1px solid var(--card-border)',
              fontSize: 13, outline: 'none', width: 140,
            }}
          />
        </div>

        <button
          onClick={handleApplyFilters}
          style={{
            padding: '8px 20px', background: '#805d17', color: '#fff',
            border: 'none', borderRadius: 6, fontSize: 13, fontWeight: 700,
            cursor: 'pointer', height: 36,
          }}
        >
          Apply Filters
        </button>

        {(tickerFilter || typeFilter || sentimentFilter || dateFrom || dateTo) && (
          <button
            onClick={handleClearFilters}
            style={{
              padding: '8px 16px', background: 'var(--section-bg)', color: 'var(--text-muted)',
              border: '1px solid var(--card-border)', borderRadius: 6, fontSize: 13, fontWeight: 600,
              cursor: 'pointer', height: 36,
            }}
          >
            Clear All
          </button>
        )}
      </div>

      {/* Error */}
      {error && (
        <div style={{
          padding: 16, marginBottom: 20, background: 'var(--negative-soft)', borderRadius: 8,
          border: '1px solid #ef9a9a', color: 'var(--negative)', fontSize: 14,
        }}>
          {error}
        </div>
      )}

      {/* Results Count */}
      {!loading && (
        <div style={{ marginBottom: 16, fontSize: 13, color: 'var(--text-muted)' }}>
          Showing {reports.length} of {total} report{total !== 1 ? 's' : ''}
        </div>
      )}

      {/* Loading */}
      {loading && reports.length === 0 && (
        <div style={{ textAlign: 'center', padding: 80, color: 'var(--text-muted)' }}>
          <div style={{ fontSize: 48, marginBottom: 16 }}>🔄</div>
          <p>Loading intelligence reports...</p>
        </div>
      )}

      {/* Empty State */}
      {!loading && reports.length === 0 && !error && (
        <div style={{ textAlign: 'center', padding: 80, color: 'var(--text-muted)' }}>
          <div style={{ fontSize: 48, marginBottom: 16 }}>📭</div>
          <p>No reports found matching your filters.</p>
        </div>
      )}

      {/* Report List */}
      {reports.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {reports.map((entry) => (
            <Link
              key={`${entry.report_type}-${entry.id}`}
              href={getDetailLink(entry)}
              style={{
                padding: 20, background: 'var(--card-bg)', borderRadius: 12,
                border: '1px solid var(--card-border)', textDecoration: 'none',
                display: 'flex', gap: 16, alignItems: 'flex-start',
                boxShadow: '0 1px 4px rgba(0,0,0,0.04)',
                transition: 'box-shadow 0.2s, border-color 0.2s',
              }}
              onMouseEnter={e => {
                (e.currentTarget as HTMLAnchorElement).style.boxShadow = '0 2px 12px rgba(0,0,0,0.1)';
                (e.currentTarget as HTMLAnchorElement).style.borderColor = '#805d17';
              }}
              onMouseLeave={e => {
                (e.currentTarget as HTMLAnchorElement).style.boxShadow = '0 1px 4px rgba(0,0,0,0.04)';
                (e.currentTarget as HTMLAnchorElement).style.borderColor = 'var(--card-border)';
              }}
            >
              {/* Type Icon */}
              <div style={{
                width: 48, height: 48, borderRadius: 12,
                background: entry.report_type === 'market' ? 'var(--info-soft)' : entry.report_type === 'sector' ? 'var(--positive-soft)' : 'var(--warning-soft)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 24, flexShrink: 0,
              }}>
                {typeIcon(entry.report_type)}
              </div>

              {/* Main Content */}
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                  <span style={{ fontSize: 16, fontWeight: 700, color: 'var(--text-primary)' }}>
                    {entry.ticker || 'MARKET'}
                  </span>
                  {entry.company_name && (
                    <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>{entry.company_name}</span>
                  )}
                  <span style={{
                    padding: '2px 8px', borderRadius: 10, fontSize: 10, fontWeight: 700,
                    background: 'var(--section-bg)', color: 'var(--text-muted)', textTransform: 'uppercase',
                  }}>
                    {typeLabel(entry.report_type)}
                  </span>
                </div>

                <p style={{
                  margin: '0 0 8px', fontSize: 13, color: 'var(--text-muted)',
                  overflow: 'hidden', textOverflow: 'ellipsis', display: '-webkit-box',
                  WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', lineHeight: 1.5,
                }}>
                  {entry.summary_preview || 'No summary available'}
                </p>

                <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                  <span style={{
                    padding: '3px 10px', borderRadius: 12, fontSize: 11, fontWeight: 700,
                    color: '#fff', background: sentimentColor(entry.overall_sentiment),
                  }}>
                    {entry.overall_sentiment}
                  </span>

                  {entry.confidence_score != null && (
                    <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                      Confidence: {(entry.confidence_score * 100).toFixed(0)}%
                    </span>
                  )}

                  {entry.articles_count != null && (
                    <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                      {entry.articles_count} articles
                    </span>
                  )}

                  {entry.model_used && (
                    <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                      Model: {entry.model_used}
                    </span>
                  )}
                </div>
              </div>

              {/* Meta */}
              <div style={{ textAlign: 'right', flexShrink: 0 }}>
                <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                  {formatApiTimestamp(entry.created_at, { month: 'short', day: 'numeric' })}
                </div>
                <div style={{ fontSize: 10, color: 'var(--card-border)', marginTop: 4 }}>
                  {formatApiTimestamp(entry.created_at, { hour: '2-digit', minute: '2-digit', hour12: true, timeZoneName: 'short' })}
                </div>
              </div>
            </Link>
          ))}
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div style={{ display: 'flex', justifyContent: 'center', gap: 8, marginTop: 32 }}>
          <button
            onClick={() => setPage(Math.max(1, page - 1))}
            disabled={page === 1}
            style={{
              padding: '8px 16px', borderRadius: 8, border: '1px solid var(--card-border)',
              background: page === 1 ? 'var(--section-bg)' : '#fff',
              color: page === 1 ? 'var(--text-muted)' : 'var(--text-secondary)',
              cursor: page === 1 ? 'not-allowed' : 'pointer',
              fontWeight: 600, fontSize: 13,
            }}
          >
            ← Prev
          </button>
          <span style={{ padding: '8px 16px', fontSize: 13, color: 'var(--text-muted)', display: 'flex', alignItems: 'center' }}>
            Page {page} of {totalPages}
          </span>
          <button
            onClick={() => setPage(hasMore ? page + 1 : page)}
            disabled={!hasMore}
            style={{
              padding: '8px 16px', borderRadius: 8, border: '1px solid var(--card-border)',
              background: !hasMore ? 'var(--section-bg)' : '#fff',
              color: !hasMore ? 'var(--text-muted)' : 'var(--text-secondary)',
              cursor: !hasMore ? 'not-allowed' : 'pointer',
              fontWeight: 600, fontSize: 13,
            }}
          >
            Next →
          </button>
        </div>
      )}
    </div>
  );
}
