'use client';

import { useEffect, useState, useCallback } from 'react';
import Link from 'next/link';
import ReportPdfButton from '@/components/ReportPdfButton';
import { fetchMarketReportHistory, fetchMarketReportById, triggerMarketReportRegeneration } from '@/lib/api';
import { formatApiTimestamp } from '@/lib/formatters';
import type { MarketReportHistoryResponse } from '@/lib/api';
import type { CachedMarketReport } from '@/types/stock';

export default function MarketReportHistoryPage() {
  const [reports, setReports] = useState<MarketReportHistoryResponse['items']>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [regenerating, setRegenerating] = useState(false);
  const [selectedReport, setSelectedReport] = useState<CachedMarketReport | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const LIMIT = 20;

  const loadReports = useCallback(async (pageNum: number, signal?: AbortSignal) => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetchMarketReportHistory(pageNum, LIMIT, signal);
      if (!signal?.aborted) { setReports(res.items); setTotal(res.total); }
    } catch (err) {
      if (!signal?.aborted) setError(err instanceof Error ? err.message : 'Failed to load market report history');
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    const timer = setTimeout(() => { void loadReports(page, controller.signal); }, 0);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [page, loadReports]);

  const handleViewReport = async (id: number) => {
    setDetailLoading(true);
    setError(null);
    try {
      const report = await fetchMarketReportById(id);
      setSelectedReport(report);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load report details');
    } finally {
      setDetailLoading(false);
    }
  };

  const handleRegenerate = async () => {
    setRegenerating(true);
    try {
      await triggerMarketReportRegeneration();
      setTimeout(() => loadReports(1), 5000);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to trigger regeneration');
    } finally {
      setRegenerating(false);
    }
  };

  const sentimentColor = (sentiment: string) => {
    const s = sentiment.toLowerCase();
    if (s.includes('very bullish')) return '#166b52';
    if (s.includes('bullish')) return '#8bc34a';
    if (s.includes('neutral')) return '#805d17';
    if (s.includes('bearish')) return '#ff5722';
    if (s.includes('very bearish')) return '#b1364e';
    return 'var(--text-muted)';
  };

  const totalPages = Math.ceil(total / LIMIT);

  return (
    <div className="workspace-page">
      {/* Header */}
      <div style={{ marginBottom: 32 }}>
        <h1 style={{ fontSize: 28, fontWeight: 800, margin: '0 0 8px', color: 'var(--text-primary)' }}>
          📊 Daily Market Report History
        </h1>
        <p style={{ color: 'var(--text-muted)', margin: 0, fontSize: 14 }}>
          Archive of AI-generated daily market summaries. Generated at 9:00 AM ET each trading day.
        </p>
      </div>

      {/* Actions */}
      <div style={{ display: 'flex', gap: 12, marginBottom: 24, alignItems: 'center' }}>
        <button
          onClick={handleRegenerate}
          disabled={regenerating || loading}
          style={{
            padding: '10px 20px',
            background: regenerating ? 'var(--text-muted)' : '#805d17',
            color: '#fff',
            border: 'none',
            borderRadius: 8,
            fontSize: 14,
            fontWeight: 700,
            cursor: regenerating || loading ? 'not-allowed' : 'pointer',
          }}
        >
          {regenerating ? '⏳ Generating...' : '🔄 Generate New Report'}
        </button>
        <Link href="/intelligence" style={{ marginLeft: 'auto', fontSize: 13, color: 'var(--accent)', textDecoration: 'none' }}>
          ← Back to Intelligence Dashboard
        </Link>
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

      {/* Selected Report Detail Modal */}
      {selectedReport && (
        <div style={{
          marginBottom: 24, padding: 24, background: 'var(--card-bg)', borderRadius: 12,
          border: '1px solid var(--card-border)', boxShadow: '0 2px 8px rgba(0,0,0,0.08)',
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 16 }}>
            <div>
              <h2 style={{ margin: '0 0 4px', fontSize: 18, fontWeight: 700 }}>
                Market Report #{selectedReport.id}
              </h2>
              <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                {selectedReport.report_date ? formatApiTimestamp(selectedReport.report_date, { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' }) : 'Date unknown'}
                {' • '}Model: {selectedReport.model_used || 'N/A'}
              </span>
            </div>
            <button
              onClick={() => setSelectedReport(null)}
              style={{ background: 'none', border: 'none', fontSize: 20, cursor: 'pointer', color: 'var(--text-muted)' }}
            >
              ✕
            </button>
          </div>
          <div style={{ display: 'flex', gap: 12, marginBottom: 16 }}>
            <span style={{
              padding: '4px 12px', borderRadius: 16, fontSize: 12, fontWeight: 700,
              background: sentimentColor(selectedReport.overall_sentiment),
              color: '#fff',
            }}>
              {selectedReport.overall_sentiment}
            </span>
            <span style={{ padding: '4px 12px', borderRadius: 16, fontSize: 12, fontWeight: 700, background: 'var(--info-soft)', color: 'var(--info)' }}>
              Risk: {selectedReport.risk_level}
            </span>
            {selectedReport.confidence_score != null && (
              <span style={{ padding: '4px 12px', borderRadius: 16, fontSize: 12, fontWeight: 700, background: '#f3e5f5', color: '#7b1fa2' }}>
                Confidence: {(selectedReport.confidence_score * 100).toFixed(0)}%
              </span>
            )}
          </div>
          <ReportPdfButton report={selectedReport} />
          {selectedReport.report_data && (
            <pre style={{
              background: 'var(--section-bg)', padding: 16, borderRadius: 8, fontSize: 12,
              overflow: 'auto', maxHeight: 400, whiteSpace: 'pre-wrap',
            }}>
              {JSON.stringify(selectedReport.report_data, null, 2)}
            </pre>
          )}
        </div>
      )}

      {/* Loading */}
      {loading && reports.length === 0 && (
        <div style={{ textAlign: 'center', padding: 80, color: 'var(--text-muted)' }}>
          <div style={{ fontSize: 48, marginBottom: 16 }}>🔄</div>
          <p>Loading report history...</p>
        </div>
      )}

      {/* Empty State */}
      {!loading && reports.length === 0 && !error && (
        <div style={{ textAlign: 'center', padding: 80, color: 'var(--text-muted)' }}>
          <div style={{ fontSize: 48, marginBottom: 16 }}>📭</div>
          <p>No market reports found. Generate one to get started.</p>
        </div>
      )}

      {/* Report Table */}
      {reports.length > 0 && (
        <div style={{ background: 'var(--card-bg)', borderRadius: 12, border: '1px solid var(--card-border)', overflow: 'hidden' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
            <thead>
              <tr style={{ background: 'var(--section-bg)' }}>
                <th style={{ padding: '12px 16px', textAlign: 'left', fontWeight: 700, color: 'var(--text-secondary)' }}>ID</th>
                <th style={{ padding: '12px 16px', textAlign: 'left', fontWeight: 700, color: 'var(--text-secondary)' }}>Date</th>
                <th style={{ padding: '12px 16px', textAlign: 'left', fontWeight: 700, color: 'var(--text-secondary)' }}>Sentiment</th>
                <th style={{ padding: '12px 16px', textAlign: 'left', fontWeight: 700, color: 'var(--text-secondary)' }}>Risk</th>
                <th style={{ padding: '12px 16px', textAlign: 'center', fontWeight: 700, color: 'var(--text-secondary)' }}>Confidence</th>
                <th style={{ padding: '12px 16px', textAlign: 'left', fontWeight: 700, color: 'var(--text-secondary)' }}>Model</th>
                <th style={{ padding: '12px 16px', textAlign: 'center', fontWeight: 700, color: 'var(--text-secondary)' }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {reports.map((r) => (
                <tr key={r.id} style={{ borderTop: '1px solid #f0f0f0' }}>
                  <td style={{ padding: '12px 16px', color: 'var(--text-muted)' }}>#{r.id}</td>
                  <td style={{ padding: '12px 16px', color: 'var(--text-secondary)' }}>
                    {r.report_date ? formatApiTimestamp(r.report_date, { month: 'short', day: 'numeric', year: 'numeric' }) : 'N/A'}
                  </td>
                  <td style={{ padding: '12px 16px' }}>
                    <span style={{
                      display: 'inline-block', padding: '3px 10px', borderRadius: 12,
                      fontSize: 11, fontWeight: 700, color: '#fff',
                      background: sentimentColor(r.overall_sentiment),
                    }}>
                      {r.overall_sentiment}
                    </span>
                  </td>
                  <td style={{ padding: '12px 16px', color: 'var(--text-secondary)' }}>{r.risk_level}</td>
                  <td style={{ padding: '12px 16px', textAlign: 'center', color: 'var(--text-secondary)' }}>
                    {r.confidence_score != null ? `${(r.confidence_score * 100).toFixed(0)}%` : 'N/A'}
                  </td>
                  <td style={{ padding: '12px 16px', color: 'var(--text-muted)', fontSize: 12 }}>{r.model_used || 'N/A'}</td>
                  <td style={{ padding: '12px 16px', textAlign: 'center' }}>
                    <button
                      onClick={() => handleViewReport(r.id)}
                      disabled={detailLoading}
                      style={{
                        padding: '5px 12px', background: 'var(--info-soft)', color: 'var(--info)',
                        border: 'none', borderRadius: 6, fontSize: 12, fontWeight: 600,
                        cursor: detailLoading ? 'not-allowed' : 'pointer',
                      }}
                    >
                      View
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div style={{ display: 'flex', justifyContent: 'center', gap: 8, marginTop: 24 }}>
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
            Page {page} of {totalPages} ({total} reports)
          </span>
          <button
            onClick={() => setPage(Math.min(totalPages, page + 1))}
            disabled={page >= totalPages}
            style={{
              padding: '8px 16px', borderRadius: 8, border: '1px solid var(--card-border)',
              background: page >= totalPages ? 'var(--section-bg)' : '#fff',
              color: page >= totalPages ? 'var(--text-muted)' : 'var(--text-secondary)',
              cursor: page >= totalPages ? 'not-allowed' : 'pointer',
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
