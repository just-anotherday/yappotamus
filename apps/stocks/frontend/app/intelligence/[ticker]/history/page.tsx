'use client';

import { useEffect, useState, useCallback } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { articleLink } from '@/lib/articleEvidence';
import ReportPdfButton from '@/components/ReportPdfButton';
import NeedsMoreResearchSection from '@/components/intelligence/NeedsMoreResearchSection';
import { fetchCompanyReportHistory } from '@/lib/api';
import { formatApiTimestamp } from '@/lib/formatters';
import { formatReportDateTime, hasOutlook, hasTechnicalAnalysis } from '@/lib/reportPresentation';
import type { ReportHistoryEntry, ReportHistoryResponse } from '@/lib/api';
import type { ArticleReference, FinancialAnalysisReport, KeyRisk } from '@/types/stock';

function sentimentColor(sentiment: string): string {
  const s = sentiment.toLowerCase();
  if (s.includes('very bullish')) return 'var(--positive)';
  if (s.includes('bullish')) return 'var(--positive)';
  if (s.includes('neutral')) return 'var(--warning)';
  if (s.includes('bearish')) return 'var(--negative)';
  if (s.includes('very bearish')) return 'var(--negative)';
  return 'var(--text-muted)';
}

function severityColor(severity: string): string {
  const s = severity.toLowerCase();
  if (s === 'high') return 'var(--negative)';
  if (s === 'medium') return 'var(--warning)';
  return 'var(--positive)';
}

function renderReportData(rd: FinancialAnalysisReport) {
  const cardStyle: React.CSSProperties = {
    padding: 24,
    background: 'var(--card-bg)',
    borderRadius: 12,
    border: '1px solid var(--card-border)',
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* Executive Summary */}
      {rd.executive_summary && (
        <section>
          <h3 style={{ fontSize: 15, fontWeight: 700, marginBottom: 8, color: 'var(--text-primary)' }}>📋 Executive Summary</h3>
          <div style={{ ...cardStyle, lineHeight: 1.7, fontSize: 14, color: 'var(--text-secondary)' }}>
            {rd.executive_summary}
          </div>
        </section>
      )}

      {/* Key Catalysts */}
      {rd.key_catalysts?.length > 0 && (
        <section>
          <h3 style={{ fontSize: 15, fontWeight: 700, marginBottom: 8, color: 'var(--text-primary)' }}>🚀 Key Catalysts</h3>
          <div style={cardStyle}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {rd.key_catalysts.map((c: string, i: number) => (
                <div key={i} style={{ padding: '8px 12px', background: 'var(--section-bg)', borderRadius: 6, borderLeft: '4px solid var(--positive)', fontSize: 13, color: 'var(--text-primary)' }}>
                  {c}
                </div>
              ))}
            </div>
          </div>
        </section>
      )}

      {/* Key Risks */}
      {rd.key_risks?.length > 0 && (
        <section>
          <h3 style={{ fontSize: 15, fontWeight: 700, marginBottom: 8, color: 'var(--text-primary)' }}>⚠️ Key Risks</h3>
          <div style={cardStyle}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {rd.key_risks.map((r: KeyRisk, i: number) => (
                <div key={i} style={{ padding: '8px 12px', background: 'var(--section-bg)', borderRadius: 6, borderLeft: `4px solid ${severityColor(r.severity)}`, fontSize: 13, color: 'var(--text-primary)' }}>
                  <strong>{r.risk}</strong>
                  <span style={{ marginLeft: 8, fontSize: 11, color: severityColor(r.severity), fontWeight: 600 }}>[{r.severity}]</span>
                </div>
              ))}
            </div>
          </div>
        </section>
      )}

      {/* Technical Analysis */}
      {hasTechnicalAnalysis(rd.technical_analysis) && rd.technical_analysis && (
        <section>
          <h3 style={{ fontSize: 15, fontWeight: 700, marginBottom: 8, color: 'var(--text-primary)' }}>📈 Technical Analysis</h3>
          <div style={cardStyle}>
            {rd.technical_analysis.trend && (
              <p style={{ margin: '0 0 6px', color: 'var(--text-secondary)', fontSize: 13 }}><strong>Trend:</strong> {rd.technical_analysis.trend}</p>
            )}
            {rd.technical_analysis.support_levels?.length > 0 && (
              <p style={{ margin: '0 0 6px', color: 'var(--text-secondary)', fontSize: 13 }}><strong>Support:</strong> {rd.technical_analysis.support_levels.join(', ')}</p>
            )}
            {rd.technical_analysis.resistance_levels?.length > 0 && (
              <p style={{ margin: '0 0 6px', color: 'var(--text-secondary)', fontSize: 13 }}><strong>Resistance:</strong> {rd.technical_analysis.resistance_levels.join(', ')}</p>
            )}
          </div>
        </section>
      )}

      {/* Outlook */}
      {hasOutlook(rd.outlook) && rd.outlook && (
        <section>
          <h3 style={{ fontSize: 15, fontWeight: 700, marginBottom: 8, color: 'var(--text-primary)' }}>🔭 Outlook</h3>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 12 }}>
            {rd.outlook.short_term && (
              <div style={{ padding: 12, background: 'var(--info-soft)', borderRadius: 8 }}>
                <p style={{ margin: '0 0 4px', fontSize: 11, fontWeight: 700, color: 'var(--info)' }}>Short Term</p>
                <p style={{ margin: 0, fontSize: 12, lineHeight: 1.5, color: 'var(--text-secondary)' }}>{rd.outlook.short_term}</p>
              </div>
            )}
            {rd.outlook.medium_term && (
              <div style={{ padding: 12, background: 'var(--warning-soft)', borderRadius: 8 }}>
                <p style={{ margin: '0 0 4px', fontSize: 11, fontWeight: 700, color: '#e65100' }}>Medium Term</p>
                <p style={{ margin: 0, fontSize: 12, lineHeight: 1.5, color: 'var(--text-secondary)' }}>{rd.outlook.medium_term}</p>
              </div>
            )}
            {rd.outlook.long_term && (
              <div style={{ padding: 12, background: 'var(--positive-soft)', borderRadius: 8 }}>
                <p style={{ margin: '0 0 4px', fontSize: 11, fontWeight: 700, color: 'var(--positive)' }}>Long Term</p>
                <p style={{ margin: 0, fontSize: 12, lineHeight: 1.5, color: 'var(--text-secondary)' }}>{rd.outlook.long_term}</p>
              </div>
            )}
          </div>
        </section>
      )}

      {/* Actionable Insights */}
      {rd.actionable_insights?.length > 0 && (
        <section>
          <h3 style={{ fontSize: 15, fontWeight: 700, marginBottom: 8, color: 'var(--text-primary)' }}>💡 Actionable Insights</h3>
          <div style={cardStyle}>
            <ol style={{ paddingLeft: 20, margin: 0, color: 'var(--text-secondary)', fontSize: 13 }}>
              {rd.actionable_insights.map((insight: string, i: number) => (
                <li key={i} style={{ padding: '4px 0', lineHeight: 1.5 }}>{insight}</li>
              ))}
            </ol>
          </div>
        </section>
      )}

      <NeedsMoreResearchSection items={rd.needs_more_research} compact />

      {/* News Summary */}
      {rd.news_summary?.length > 0 && (
        <section>
          <h3 style={{ fontSize: 15, fontWeight: 700, marginBottom: 8, color: 'var(--text-primary)' }}>📰 News Summary</h3>
          <div style={cardStyle}>
            <ul style={{ paddingLeft: 20, margin: 0, color: 'var(--text-secondary)', fontSize: 12 }}>
              {rd.news_summary.map((item: string, i: number) => (
                <li key={i} style={{ padding: '3px 0', lineHeight: 1.4 }}>{item}</li>
              ))}
            </ul>
          </div>
        </section>
      )}

      {/* Source Articles */}
      {rd.articles_used?.length > 0 && (
        <section>
          <h3 style={{ fontSize: 15, fontWeight: 700, marginBottom: 8, color: 'var(--text-primary)' }}>📚 Source Articles ({rd.articles_used.length})</h3>
          <div style={cardStyle}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              {rd.articles_used.map((a: ArticleReference, i: number) => (
                <a key={i} href={articleLink(a.url)?.href || '#'} target="_blank" rel="noopener noreferrer"
                  style={{ textDecoration: 'none', fontSize: 12, color: 'var(--accent)', padding: '2px 0' }}>
                  {a.title}
                  {a.published_at && <span style={{ color: 'var(--text-muted)', marginLeft: 8 }}>{formatApiTimestamp(a.published_at, { year: 'numeric', month: 'numeric', day: 'numeric' })}</span>}
                </a>
              ))}
            </div>
          </div>
        </section>
      )}

      {!(rd.executive_summary
        || rd.key_catalysts?.length
        || rd.key_risks?.length
        || hasTechnicalAnalysis(rd.technical_analysis)
        || hasOutlook(rd.outlook)
        || rd.actionable_insights?.length
        || rd.news_summary?.length
        || rd.articles_used?.length
        || rd.needs_more_research?.length) && (
        <div style={{ ...cardStyle, fontSize: 13, color: 'var(--text-muted)' }}>
          No validated analysis details are available for this report.
        </div>
      )}
    </div>
  );
}

export default function ReportHistoryPage() {
  const params = useParams();
  const ticker = typeof params.ticker === 'string' ? params.ticker.toUpperCase() : '';

  const [history, setHistory] = useState<ReportHistoryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [expandedId, setExpandedId] = useState<number | null>(null);

  const loadHistory = useCallback(async (signal?: AbortSignal) => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchCompanyReportHistory(ticker, page, 50, signal);
      if (!signal?.aborted) setHistory(data);
    } catch (err) {
      if (!signal?.aborted) setError(err instanceof Error ? err.message : 'Failed to load report history');
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, [ticker, page]);

  useEffect(() => {
    if (!ticker) return;
    const controller = new AbortController();
    const timer = setTimeout(() => { void loadHistory(controller.signal); }, 0);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [ticker, loadHistory]);

  if (!ticker) {
    return <div style={{ padding: 40, color: 'var(--text-primary)' }}>Invalid ticker.</div>;
  }

  return (
    <div style={{ maxWidth: 900, margin: '0 auto', padding: '40px 20px' }}>
      {/* Breadcrumb + Header */}
      <div style={{ marginBottom: 32 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, marginBottom: 12 }}>
          <Link href="/analysis/reports" style={{ textDecoration: 'none', color: 'var(--accent)' }}>Analysis Reports</Link>
          <span style={{ color: 'var(--text-muted)' }}>/</span>
          <Link href={`/intelligence/${ticker}`} style={{ textDecoration: 'none', color: 'var(--accent)' }}>{ticker} Report</Link>
          <span style={{ color: 'var(--text-muted)' }}>/</span>
          <span style={{ color: 'var(--text-muted)' }}>History</span>
        </div>
        <h1 style={{ fontSize: 28, fontWeight: 800, margin: '0 0 4px', color: 'var(--text-primary)' }}>
          📦 Archived Reports — {ticker}
        </h1>
        <p style={{ color: 'var(--text-muted)', margin: 0, fontSize: 13 }}>
          Past AI analysis snapshots showing how sentiment and confidence evolved over time.
        </p>
      </div>

      {/* Loading */}
      {loading && (
        <div style={{ textAlign: 'center', padding: 80, color: 'var(--text-muted)' }}>
          <div style={{ fontSize: 48, marginBottom: 16 }}>🔄</div>
          <p>Loading archived reports...</p>
        </div>
      )}

      {/* Error */}
      {error && (
        <div style={{ padding: 24, background: 'var(--negative-soft)', borderRadius: 12, border: '1px solid var(--negative-border)' }}>
          <h2 style={{ color: 'var(--negative)', margin: '0 0 8px' }}>⚠️ Error</h2>
          <p style={{ margin: 0 }}>{error}</p>
        </div>
      )}

      {/* History Table */}
      {!loading && !error && history && (
        <>
          <div style={{ marginBottom: 16, fontSize: 13, color: 'var(--text-muted)' }}>
            Total archived reports: <strong>{history.total}</strong>
          </div>

          {history.entries.length === 0 ? (
            <div style={{ padding: 40, textAlign: 'center', background: 'var(--card-bg)', borderRadius: 12, border: '1px solid var(--card-border)' }}>
              <p style={{ fontSize: 48, margin: '0 0 16px' }}>📭</p>
              <p style={{ color: 'var(--text-secondary)' }}>No archived reports found for {ticker}.</p>
              <p style={{ color: 'var(--text-muted)', fontSize: 12 }}>Archived snapshots are created automatically when new AI analyses run.</p>
            </div>
          ) : (
            <div style={{ background: 'var(--card-bg)', borderRadius: 12, border: '1px solid var(--card-border)', overflow: 'hidden' }}>
              {/* Table Header */}
              <div style={{
                display: 'grid',
                gridTemplateColumns: '140px 120px 80px 80px 1fr',
                gap: 12,
                padding: '12px 20px',
                background: 'var(--section-bg)',
                borderBottom: '1px solid var(--card-border)',
                fontSize: 11,
                fontWeight: 700,
                textTransform: 'uppercase',
                color: 'var(--text-muted)',
              }}>
                <span>Date</span>
                <span>Sentiment</span>
                <span>Confidence</span>
                <span>Articles</span>
                <span>Model</span>
              </div>

              {/* Rows */}
              {history.entries.map((entry: ReportHistoryEntry) => {
                const color = sentimentColor(entry.overall_sentiment);
                const dateStr = entry.created_at
                  ? formatReportDateTime(entry.created_at)
                  : 'Unknown';
                const isExpanded = expandedId === entry.id;
                return (
                  <div key={entry.id}>
                    <div
                      onClick={() => setExpandedId(isExpanded ? null : entry.id)}
                      style={{
                        display: 'grid',
                        gridTemplateColumns: '140px 120px 80px 80px 1fr',
                        gap: 12,
                        padding: '14px 20px',
                        borderBottom: '1px solid var(--card-border)',
                        fontSize: 13,
                        alignItems: 'center',
                        cursor: 'pointer',
                        background: isExpanded ? '#1a237e11' : 'transparent',
                      }}
                    >
                      <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>{dateStr}</span>
                      <span style={{
                        background: `color-mix(in srgb, ${color} 13%, transparent)`,
                        color,
                        borderRadius: 4,
                        padding: '3px 8px',
                        fontSize: 11,
                        fontWeight: 700,
                        textTransform: 'uppercase',
                        display: 'inline-block',
                      }}>
                        {entry.overall_sentiment}
                      </span>
                      <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{entry.confidence_score}</span>
                      <span style={{ color: 'var(--text-muted)' }}>{entry.articles_count}</span>
                      <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                        <span style={{
                          fontFamily: 'monospace',
                          fontSize: 11,
                          background: 'var(--section-bg)',
                          padding: '2px 6px',
                          borderRadius: 4,
                          color: 'var(--text-secondary)',
                        }}>
                          {entry.model_used || 'N/A'}
                        </span>
                        <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>{isExpanded ? '▲' : '▶'}</span>
                      </div>
                    </div>
                    {isExpanded && entry.report_data && (
                      <div style={{ padding: '0 20px 20px', borderBottom: '1px solid var(--card-border)' }}>
                        <ReportPdfButton report={{ ...entry, ticker }} />
                        {renderReportData(entry.report_data)}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}

          {/* Pagination */}
          {!loading && history && history.total > 0 && (
            <div style={{ display: 'flex', gap: 8, marginTop: 20, justifyContent: 'center' }}>
              <button
                onClick={() => setPage(p => Math.max(1, p - 1))}
                disabled={page <= 1}
                style={{
                  padding: '8px 16px',
                  background: page <= 1 ? 'var(--card-border)' : '#2b6178',
                  color: page <= 1 ? 'var(--text-muted)' : '#fff',
                  border: 'none',
                  borderRadius: 6,
                  cursor: page <= 1 ? 'not-allowed' : 'pointer',
                  fontWeight: 600,
                }}
              >
                ← Prev
              </button>
              <span style={{ padding: '8px 16px', color: 'var(--text-muted)', display: 'flex', alignItems: 'center' }}>
                Page {page}
              </span>
              <button
                onClick={() => setPage(p => p + 1)}
                disabled={(page * 50) >= history.total}
                style={{
                  padding: '8px 16px',
                  background: (page * 50) >= history.total ? 'var(--card-border)' : '#2b6178',
                  color: (page * 50) >= history.total ? 'var(--text-muted)' : '#fff',
                  border: 'none',
                  borderRadius: 6,
                  cursor: (page * 50) >= history.total ? 'not-allowed' : 'pointer',
                  fontWeight: 600,
                }}
              >
                Next →
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
