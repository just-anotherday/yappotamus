'use client';

import { useEffect, useState, useCallback } from 'react';
import Link from 'next/link';
import { fetchUnifiedReports } from '@/lib/api';
import type { UnifiedReportListResponse, UnifiedReportEntry } from '@/lib/api';
import type { UnifiedReportFilters } from '@/types/stock';

export default function UnifiedIntelligenceBrowser() {
  const [reports, setReports] = useState<UnifiedReportEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [hasMore, setHasMore] = useState(false);

  // Filters
  const [tickerFilter, setTickerFilter] = useState<string>('');
  const [typeFilter, setTypeFilter] = useState<string>('');
  const [sentimentFilter, setSentimentFilter] = useState<string>('');
  const [dateFrom, setDateFrom] = useState<string>('');
  const [dateTo, setDateTo] = useState<string>('');

  const LIMIT = 20;

  const loadReports = useCallback(async (pageNum: number) => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetchUnifiedReports(
        tickerFilter || undefined,
        typeFilter as any,
        sentimentFilter || undefined,
        dateFrom || undefined,
        dateTo || undefined,
        pageNum,
        LIMIT,
      );
      setReports(res.items);
      setTotal(res.total);
      setHasMore(res.has_more);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load unified reports');
    } finally {
      setLoading(false);
    }
  }, [tickerFilter, typeFilter, sentimentFilter, dateFrom, dateTo]);

  useEffect(() => {
    loadReports(1);
  }, []);

  const handleApplyFilters = () => {
    setPage(1);
    loadReports(1);
  };

  const handleClearFilters = () => {
    setTickerFilter('');
    setTypeFilter('');
    setSentimentFilter('');
    setDateFrom('');
    setDateTo('');
    setPage(1);
  };

  // Reset filters then load
  useEffect(() => {
    if (!tickerFilter && !typeFilter && !sentimentFilter && !dateFrom && !dateTo) {
      loadReports(1);
    }
  }, [tickerFilter, typeFilter, sentimentFilter, dateFrom, dateTo]);

  const sentimentColor = (sentiment: string) => {
    const s = (sentiment || '').toLowerCase();
    if (s.includes('very bullish')) return '#4caf50';
    if (s.includes('bullish')) return '#8bc34a';
    if (s.includes('neutral')) return '#ff9800';
    if (s.includes('bearish')) return '#ff5722';
    if (s.includes('very bearish')) return '#f44336';
    return '#9e9e9e';
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
        <h1 style={{ fontSize: 28, fontWeight: 800, margin: '0 0 8px', color: '#1a1a2e' }}>
          🔍 Unified Intelligence Browser
        </h1>
        <p style={{ color: '#6b7280', margin: 0, fontSize: 14 }}>
          Browse all AI-generated reports — company analysis, sector insights, and daily market summaries in one place.
        </p>
      </div>

      {/* Actions Bar */}
      <div style={{ display: 'flex', gap: 12, marginBottom: 24 }}>
        <Link href="/intelligence" style={{ fontSize: 13, color: '#2196f3', textDecoration: 'none', display: 'flex', alignItems: 'center' }}>
          ← Intelligence Dashboard
        </Link>
        <Link href="/analysis/market-history" style={{ fontSize: 13, color: '#2196f3', textDecoration: 'none', display: 'flex', alignItems: 'center' }}>
          Market History →
        </Link>
      </div>

      {/* Filters */}
      <div style={{
        padding: 20, marginBottom: 24, background: '#fff', borderRadius: 12,
        border: '1px solid #e0e0e0', display: 'flex', flexWrap: 'wrap', gap: 16, alignItems: 'flex-end',
      }}>
        <div>
          <label style={{ display: 'block', fontSize: 11, fontWeight: 700, color: '#757575', marginBottom: 4, textTransform: 'uppercase' }}>
            Ticker
          </label>
          <input
            type="text"
            value={tickerFilter}
            onChange={e => setTickerFilter(e.target.value.toUpperCase())}
            placeholder="AAPL, SPY..."
            style={{
              padding: '8px 12px', borderRadius: 6, border: '1px solid #e0e0e0',
              fontSize: 13, width: 120, outline: 'none',
            }}
          />
        </div>

        <div>
          <label style={{ display: 'block', fontSize: 11, fontWeight: 700, color: '#757575', marginBottom: 4, textTransform: 'uppercase' }}>
            Report Type
          </label>
          <select
            value={typeFilter}
            onChange={e => setTypeFilter(e.target.value)}
            style={{
              padding: '8px 12px', borderRadius: 6, border: '1px solid #e0e0e0',
              fontSize: 13, outline: 'none', background: '#fff',
            }}
          >
            <option value="">All Types</option>
            <option value="company">🏢 Company</option>
            <option value="sector">📊 Sector</option>
            <option value="market">🌐 Market</option>
          </select>
        </div>

        <div>
          <label style={{ display: 'block', fontSize: 11, fontWeight: 700, color: '#757575', marginBottom: 4, textTransform: 'uppercase' }}>
            Sentiment
          </label>
          <select
            value={sentimentFilter}
            onChange={e => setSentimentFilter(e.target.value)}
            style={{
              padding: '8px 12px', borderRadius: 6, border: '1px solid #e0e0e0',
              fontSize: 13, outline: 'none', background: '#fff',
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
          <label style={{ display: 'block', fontSize: 11, fontWeight: 700, color: '#757575', marginBottom: 4, textTransform: 'uppercase' }}>
            From
          </label>
          <input
            type="date"
            value={dateFrom}
            onChange={e => setDateFrom(e.target.value)}
            style={{
              padding: '8px 12px', borderRadius: 6, border: '1px solid #e0e0e0',
              fontSize: 13, outline: 'none', width: 140,
            }}
          />
        </div>

        <div>
          <label style={{ display: 'block', fontSize: 11, fontWeight: 700, color: '#757575', marginBottom: 4, textTransform: 'uppercase' }}>
            To
          </label>
          <input
            type="date"
            value={dateTo}
            onChange={e => setDateTo(e.target.value)}
            style={{
              padding: '8px 12px', borderRadius: 6, border: '1px solid #e0e0e0',
              fontSize: 13, outline: 'none', width: 140,
            }}
          />
        </div>

        <button
          onClick={handleApplyFilters}
          style={{
            padding: '8px 20px', background: '#ff9800', color: '#fff',
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
              padding: '8px 16px', background: '#f5f5f5', color: '#757575',
              border: '1px solid #e0e0e0', borderRadius: 6, fontSize: 13, fontWeight: 600,
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
          padding: 16, marginBottom: 20, background: '#ffebee', borderRadius: 8,
          border: '1px solid #ef9a9a', color: '#c62828', fontSize: 14,
        }}>
          {error}
        </div>
      )}

      {/* Results Count */}
      {!loading && (
        <div style={{ marginBottom: 16, fontSize: 13, color: '#757575' }}>
          Showing {reports.length} of {total} report{total !== 1 ? 's' : ''}
        </div>
      )}

      {/* Loading */}
      {loading && reports.length === 0 && (
        <div style={{ textAlign: 'center', padding: 80, color: '#9e9e9e' }}>
          <div style={{ fontSize: 48, marginBottom: 16 }}>🔄</div>
          <p>Loading intelligence reports...</p>
        </div>
      )}

      {/* Empty State */}
      {!loading && reports.length === 0 && !error && (
        <div style={{ textAlign: 'center', padding: 80, color: '#9e9e9e' }}>
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
                padding: 20, background: '#fff', borderRadius: 12,
                border: '1px solid #e0e0e0', textDecoration: 'none',
                display: 'flex', gap: 16, alignItems: 'flex-start',
                boxShadow: '0 1px 4px rgba(0,0,0,0.04)',
                transition: 'box-shadow 0.2s, border-color 0.2s',
              }}
              onMouseEnter={e => {
                (e.currentTarget as HTMLAnchorElement).style.boxShadow = '0 2px 12px rgba(0,0,0,0.1)';
                (e.currentTarget as HTMLAnchorElement).style.borderColor = '#ff9800';
              }}
              onMouseLeave={e => {
                (e.currentTarget as HTMLAnchorElement).style.boxShadow = '0 1px 4px rgba(0,0,0,0.04)';
                (e.currentTarget as HTMLAnchorElement).style.borderColor = '#e0e0e0';
              }}
            >
              {/* Type Icon */}
              <div style={{
                width: 48, height: 48, borderRadius: 12,
                background: entry.report_type === 'market' ? '#e3f2fd' : entry.report_type === 'sector' ? '#e8f5e9' : '#fff3e0',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 24, flexShrink: 0,
              }}>
                {typeIcon(entry.report_type)}
              </div>

              {/* Main Content */}
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                  <span style={{ fontSize: 16, fontWeight: 700, color: '#1a1a2e' }}>
                    {entry.ticker || 'MARKET'}
                  </span>
                  {entry.company_name && (
                    <span style={{ fontSize: 13, color: '#9e9e9e' }}>{entry.company_name}</span>
                  )}
                  <span style={{
                    padding: '2px 8px', borderRadius: 10, fontSize: 10, fontWeight: 700,
                    background: '#f5f5f5', color: '#757575', textTransform: 'uppercase',
                  }}>
                    {typeLabel(entry.report_type)}
                  </span>
                </div>

                <p style={{
                  margin: '0 0 8px', fontSize: 13, color: '#6b7280',
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
                    <span style={{ fontSize: 11, color: '#9e9e9e' }}>
                      Confidence: {(entry.confidence_score * 100).toFixed(0)}%
                    </span>
                  )}

                  {entry.articles_count != null && (
                    <span style={{ fontSize: 11, color: '#9e9e9e' }}>
                      {entry.articles_count} articles
                    </span>
                  )}

                  {entry.model_used && (
                    <span style={{ fontSize: 11, color: '#bdbdbd' }}>
                      Model: {entry.model_used}
                    </span>
                  )}
                </div>
              </div>

              {/* Meta */}
              <div style={{ textAlign: 'right', flexShrink: 0 }}>
                <div style={{ fontSize: 11, color: '#bdbdbd' }}>
                  {new Date(entry.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                </div>
                <div style={{ fontSize: 10, color: '#e0e0e0', marginTop: 4 }}>
                  {new Date(entry.created_at).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' })}
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
              padding: '8px 16px', borderRadius: 8, border: '1px solid #e0e0e0',
              background: page === 1 ? '#f5f5f5' : '#fff',
              color: page === 1 ? '#bdbdbd' : '#424242',
              cursor: page === 1 ? 'not-allowed' : 'pointer',
              fontWeight: 600, fontSize: 13,
            }}
          >
            ← Prev
          </button>
          <span style={{ padding: '8px 16px', fontSize: 13, color: '#757575', display: 'flex', alignItems: 'center' }}>
            Page {page} of {totalPages}
          </span>
          <button
            onClick={() => setPage(hasMore ? page + 1 : page)}
            disabled={!hasMore}
            style={{
              padding: '8px 16px', borderRadius: 8, border: '1px solid #e0e0e0',
              background: !hasMore ? '#f5f5f5' : '#fff',
              color: !hasMore ? '#bdbdbd' : '#424242',
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
