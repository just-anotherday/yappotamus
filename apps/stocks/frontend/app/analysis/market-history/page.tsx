'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { fetchMarketReportHistory, fetchMarketReportById, triggerMarketReportRegeneration } from '@/lib/api';
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

  const loadReports = async (pageNum: number) => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetchMarketReportHistory(pageNum, LIMIT);
      setReports(res.items);
      setTotal(res.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load market report history');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadReports(page);
  }, [page]);

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
    if (s.includes('very bullish')) return '#4caf50';
    if (s.includes('bullish')) return '#8bc34a';
    if (s.includes('neutral')) return '#ff9800';
    if (s.includes('bearish')) return '#ff5722';
    if (s.includes('very bearish')) return '#f44336';
    return '#9e9e9e';
  };

  const totalPages = Math.ceil(total / LIMIT);

  return (
    <div style={{ maxWidth: 1000, margin: '0 auto', padding: '40px 20px' }}>
      {/* Header */}
      <div style={{ marginBottom: 32 }}>
        <h1 style={{ fontSize: 28, fontWeight: 800, margin: '0 0 8px', color: '#1a1a2e' }}>
          📊 Daily Market Report History
        </h1>
        <p style={{ color: '#6b7280', margin: 0, fontSize: 14 }}>
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
            background: regenerating ? '#9e9e9e' : '#ff9800',
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
        <Link href="/intelligence" style={{ marginLeft: 'auto', fontSize: 13, color: '#2196f3', textDecoration: 'none' }}>
          ← Back to Intelligence Dashboard
        </Link>
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

      {/* Selected Report Detail Modal */}
      {selectedReport && (
        <div style={{
          marginBottom: 24, padding: 24, background: '#fff', borderRadius: 12,
          border: '1px solid #e0e0e0', boxShadow: '0 2px 8px rgba(0,0,0,0.08)',
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 16 }}>
            <div>
              <h2 style={{ margin: '0 0 4px', fontSize: 18, fontWeight: 700 }}>
                Market Report #{selectedReport.id}
              </h2>
              <span style={{ fontSize: 12, color: '#9e9e9e' }}>
                {selectedReport.report_date ? new Date(selectedReport.report_date).toLocaleDateString('en-US', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' }) : 'Date unknown'}
                {' • '}Model: {selectedReport.model_used || 'N/A'}
              </span>
            </div>
            <button
              onClick={() => setSelectedReport(null)}
              style={{ background: 'none', border: 'none', fontSize: 20, cursor: 'pointer', color: '#9e9e9e' }}
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
            <span style={{ padding: '4px 12px', borderRadius: 16, fontSize: 12, fontWeight: 700, background: '#e3f2fd', color: '#1565c0' }}>
              Risk: {selectedReport.risk_level}
            </span>
            {selectedReport.confidence_score != null && (
              <span style={{ padding: '4px 12px', borderRadius: 16, fontSize: 12, fontWeight: 700, background: '#f3e5f5', color: '#7b1fa2' }}>
                Confidence: {(selectedReport.confidence_score * 100).toFixed(0)}%
              </span>
            )}
          </div>
          {selectedReport.report_data && (
            <pre style={{
              background: '#f5f5f5', padding: 16, borderRadius: 8, fontSize: 12,
              overflow: 'auto', maxHeight: 400, whiteSpace: 'pre-wrap',
            }}>
              {JSON.stringify(selectedReport.report_data, null, 2)}
            </pre>
          )}
        </div>
      )}

      {/* Loading */}
      {loading && reports.length === 0 && (
        <div style={{ textAlign: 'center', padding: 80, color: '#9e9e9e' }}>
          <div style={{ fontSize: 48, marginBottom: 16 }}>🔄</div>
          <p>Loading report history...</p>
        </div>
      )}

      {/* Empty State */}
      {!loading && reports.length === 0 && !error && (
        <div style={{ textAlign: 'center', padding: 80, color: '#9e9e9e' }}>
          <div style={{ fontSize: 48, marginBottom: 16 }}>📭</div>
          <p>No market reports found. Generate one to get started.</p>
        </div>
      )}

      {/* Report Table */}
      {reports.length > 0 && (
        <div style={{ background: '#fff', borderRadius: 12, border: '1px solid #e0e0e0', overflow: 'hidden' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
            <thead>
              <tr style={{ background: '#f5f5f5' }}>
                <th style={{ padding: '12px 16px', textAlign: 'left', fontWeight: 700, color: '#424242' }}>ID</th>
                <th style={{ padding: '12px 16px', textAlign: 'left', fontWeight: 700, color: '#424242' }}>Date</th>
                <th style={{ padding: '12px 16px', textAlign: 'left', fontWeight: 700, color: '#424242' }}>Sentiment</th>
                <th style={{ padding: '12px 16px', textAlign: 'left', fontWeight: 700, color: '#424242' }}>Risk</th>
                <th style={{ padding: '12px 16px', textAlign: 'center', fontWeight: 700, color: '#424242' }}>Confidence</th>
                <th style={{ padding: '12px 16px', textAlign: 'left', fontWeight: 700, color: '#424242' }}>Model</th>
                <th style={{ padding: '12px 16px', textAlign: 'center', fontWeight: 700, color: '#424242' }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {reports.map((r) => (
                <tr key={r.id} style={{ borderTop: '1px solid #f0f0f0' }}>
                  <td style={{ padding: '12px 16px', color: '#757575' }}>#{r.id}</td>
                  <td style={{ padding: '12px 16px', color: '#424242' }}>
                    {r.report_date ? new Date(r.report_date).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : 'N/A'}
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
                  <td style={{ padding: '12px 16px', color: '#424242' }}>{r.risk_level}</td>
                  <td style={{ padding: '12px 16px', textAlign: 'center', color: '#424242' }}>
                    {r.confidence_score != null ? `${(r.confidence_score * 100).toFixed(0)}%` : 'N/A'}
                  </td>
                  <td style={{ padding: '12px 16px', color: '#757575', fontSize: 12 }}>{r.model_used || 'N/A'}</td>
                  <td style={{ padding: '12px 16px', textAlign: 'center' }}>
                    <button
                      onClick={() => handleViewReport(r.id)}
                      disabled={detailLoading}
                      style={{
                        padding: '5px 12px', background: '#e3f2fd', color: '#1565c0',
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
            Page {page} of {totalPages} ({total} reports)
          </span>
          <button
            onClick={() => setPage(Math.min(totalPages, page + 1))}
            disabled={page >= totalPages}
            style={{
              padding: '8px 16px', borderRadius: 8, border: '1px solid #e0e0e0',
              background: page >= totalPages ? '#f5f5f5' : '#fff',
              color: page >= totalPages ? '#bdbdbd' : '#424242',
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
