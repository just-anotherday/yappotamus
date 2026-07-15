'use client';

import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { API_BASE } from '@/types/stock';
import type { ReportDetail, KeyRisk, FinancialAnalysisReport, ArticleReference } from '@/types/stock';

export default function ReportDetailPage() {
  const { id } = useParams();
  const router = useRouter();
  const [report, setReport] = useState<ReportDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${API_BASE}/api/analysis/reports/${id}`)
      .then(async res => {
        if (!res.ok) {
          const err = await res.json();
          throw new Error(err.detail || 'Failed to load report');
        }
        return res.json();
      })
      .then(data => setReport(data))
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, [id]);

  const handleDelete = async () => {
    if (!confirm('Are you sure you want to delete this report?')) return;
    try {
      const res = await fetch(`${API_BASE}/api/analysis/reports/${id}`, { method: 'DELETE' });
      if (!res.ok) throw new Error('Failed to delete');
      router.push('/analysis/reports');
    } catch (e) {
      console.error(e);
      alert('Could not delete report');
    }
  };

  const renderReportContent = (data: FinancialAnalysisReport) => {
    const getSentimentColor = (s: string) => {
      switch (s) {
        case 'Very Bullish': return '#10b981';
        case 'Bullish': return '#34d399';
        case 'Neutral': return '#f59e0b';
        case 'Bearish': return '#f87171';
        case 'Very Bearish': return '#ef4444';
        default: return '#6b7280';
      }
    };

    const getSeverityColor = (severity: string) => {
      switch (severity) {
        case 'High': return '#ef4444';
        case 'Medium': return '#f59e0b';
        case 'Low': return '#10b981';
        default: return '#6b7280';
      }
    };

    return (
      <>
        {/* Current Price Banner (TOP) */}
        <div style={{
          padding: '1.25rem 1.5rem', borderRadius: '12px',
          background: '#eff6ff', border: '1px solid #bfdbfe',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        }}
        className="dark:bg-blue-900/30 dark:border-blue-800">
          <div>
            <span style={{ fontSize: '0.75rem', color: '#6b7280', textTransform: 'uppercase', letterSpacing: '0.05em', fontWeight: 600 }}
              className="dark:text-slate-400">
              Price at Analysis Time
            </span>
            <div style={{ fontSize: '2rem', fontWeight: 800, color: '#1e40af', marginTop: '0.25rem' }}
              className="dark:text-blue-400">
              ${(() => {
                // Use report_data price first, fall back to top-level DB column
                const price = data.current_price_at_analysis ?? (report as ReportDetail)?.current_price_at_analysis ?? null;
                return price != null ? Number(price).toFixed(2) : 'N/A';
              })()}
            </div>
          </div>
          <div style={{ textAlign: 'right' }}>
            <div style={{ fontSize: '0.75rem', color: '#6b7280' }} className="dark:text-slate-400">
              Asset
            </div>
            <div style={{ fontSize: '1.25rem', fontWeight: 700, color: '#1e40af' }} className="dark:text-blue-400">
              {data.asset}
            </div>
          </div>
        </div>

        {/* Executive Summary & Sentiment Header */}
        <div style={{ padding: '1.5rem', borderRadius: '12px', background: '#f9fafb', border: '1px solid #e5e7eb' }}
          className="dark:bg-slate-800 dark:border-slate-700">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
            <h2 style={{ margin: 0, color: '#111827' }} className="dark:text-white">{data.asset}</h2>
            <span style={{
              padding: '0.375rem 1rem', borderRadius: '999px',
              background: getSentimentColor(data.overall_sentiment),
              color: 'white', fontWeight: 600, fontSize: '0.875rem',
            }}>
              {data.overall_sentiment}
            </span>
          </div>
          <div style={{ marginBottom: '1rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
              <span style={{ fontSize: '0.875rem', color: '#6b7280' }} className="dark:text-slate-400">Confidence Score</span>
              <span style={{ fontWeight: 600, color: '#374151' }} className="dark:text-gray-200">{data.confidence_score}/100</span>
            </div>
            <div style={{ height: 6, borderRadius: 3, background: '#e5e7eb', overflow: 'hidden' }}
              className="dark:bg-slate-600">
              <div style={{
                width: `${data.confidence_score}%`, height: '100%', borderRadius: 3,
                background: data.confidence_score > 70 ? '#10b981' : data.confidence_score > 40 ? '#f59e0b' : '#ef4444',
              }} />
            </div>
          </div>
          <p style={{ lineHeight: 1.6, color: '#374151' }} className="dark:text-gray-300">{data.executive_summary}</p>
        </div>

        {/* News Summary */}
        {data.news_summary.length > 0 && (
          <div style={{ padding: '1.5rem', borderRadius: '12px', background: 'white', border: '1px solid #e5e7eb' }}
            className="dark:bg-slate-800 dark:border-slate-700">
            <h3 style={{ marginTop: 0, fontSize: '1.25rem', fontWeight: 700, letterSpacing: '0.025em', color: '#111827', paddingBottom: '0.5rem', borderBottom: '2px solid #e5e7eb' }} className="dark:text-white dark:border-slate-600">Key News Developments</h3>
            <ul style={{ paddingLeft: '1.25rem' }}>
              {data.news_summary.map((item, i) => (
                <li key={i} style={{ marginBottom: '0.5rem', lineHeight: 1.6, color: '#374151' }} className="dark:text-gray-300">{item}</li>
              ))}
            </ul>
          </div>
        )}

        {/* Catalysts */}
        {data.key_catalysts.length > 0 && (
          <div style={{ padding: '1.5rem', borderRadius: '12px', background: '#f0fdf4', border: '1px solid #bbf7d0' }}
            className="dark:bg-green-900/30 dark:border-green-800">
            <h3 style={{ marginTop: 0, fontSize: '1.25rem', fontWeight: 700, letterSpacing: '0.025em', color: '#166534', paddingBottom: '0.5rem', borderBottom: '2px solid #bbf7d0' }} className="dark:text-green-400 dark:border-green-800">Key Catalysts</h3>
            <ul style={{ paddingLeft: '1.25rem' }}>
              {data.key_catalysts.map((item, i) => (
                <li key={i} style={{ marginBottom: '0.5rem', lineHeight: 1.6, color: '#166534' }} className="dark:text-green-300">{item}</li>
              ))}
            </ul>
          </div>
        )}

        {/* Risks */}
        {data.key_risks.length > 0 && (
          <div style={{ padding: '1.5rem', borderRadius: '12px', background: '#fef2f2', border: '1px solid #fecaca' }}
            className="dark:bg-red-900/30 dark:border-red-800">
            <h3 style={{ marginTop: 0, fontSize: '1.25rem', fontWeight: 700, letterSpacing: '0.025em', color: '#991b1b', paddingBottom: '0.5rem', borderBottom: '2px solid #fecaca' }} className="dark:text-red-400 dark:border-red-800">Key Risks</h3>
            <ul style={{ paddingLeft: '1.25rem' }}>
              {data.key_risks.map((risk: KeyRisk, i) => (
                <li key={i} style={{ marginBottom: '0.5rem', lineHeight: 1.6, color: '#991b1b' }} className="dark:text-red-300">
                  {risk.risk}{' '}
                  <span style={{
                    fontSize: '0.75rem', padding: '0.125rem 0.5rem', borderRadius: '999px',
                    background: getSeverityColor(risk.severity), color: 'white',
                  }}>
                    {risk.severity}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Market Reaction */}
        <div style={{ padding: '1.5rem', borderRadius: '12px', background: 'white', border: '1px solid #e5e7eb' }}
          className="dark:bg-slate-800 dark:border-slate-700">
          <h3 style={{ marginTop: 0, fontSize: '1.25rem', fontWeight: 700, letterSpacing: '0.025em', color: '#111827', paddingBottom: '0.5rem', borderBottom: '2px solid #e5e7eb' }} className="dark:text-white dark:border-slate-600">Market Reaction Analysis</h3>
          <p style={{ lineHeight: 1.6, color: '#374151' }} className="dark:text-gray-300">{data.market_reaction_analysis}</p>
        </div>

        {/* Technical Analysis */}
        <div style={{ padding: '1.5rem', borderRadius: '12px', background: 'white', border: '1px solid #e5e7eb' }}
          className="dark:bg-slate-800 dark:border-slate-700">
          <h3 style={{ marginTop: 0, fontSize: '1.25rem', fontWeight: 700, letterSpacing: '0.025em', color: '#111827', paddingBottom: '0.5rem', borderBottom: '2px solid #e5e7eb' }} className="dark:text-white dark:border-slate-600">Technical Context</h3>
          <p style={{ color: '#374151' }} className="dark:text-gray-300"><strong>Trend:</strong> {data.technical_analysis.trend}</p>
          {data.technical_analysis.support_levels.length > 0 && (
            <p style={{ color: '#374151' }} className="dark:text-gray-300"><strong>Support Levels:</strong> {data.technical_analysis.support_levels.join(', ')}</p>
          )}
          {data.technical_analysis.resistance_levels.length > 0 && (
            <p style={{ color: '#374151' }} className="dark:text-gray-300"><strong>Resistance Levels:</strong> {data.technical_analysis.resistance_levels.join(', ')}</p>
          )}
          {data.technical_analysis.breakout_level && (
            <p style={{ color: '#374151' }} className="dark:text-gray-300"><strong>Breakout Level:</strong> {data.technical_analysis.breakout_level}</p>
          )}
          {data.technical_analysis.breakdown_level && (
            <p style={{ color: '#374151' }} className="dark:text-gray-300"><strong>Breakdown Level:</strong> {data.technical_analysis.breakdown_level}</p>
          )}
        </div>

        {/* Outlook */}
        <div style={{ padding: '1.5rem', borderRadius: '12px', background: '#fffbeb', border: '1px solid #fde68a' }}
          className="dark:bg-yellow-900/30 dark:border-yellow-800">
          <h3 style={{ marginTop: 0, fontSize: '1.25rem', fontWeight: 700, letterSpacing: '0.025em', color: '#92400e', paddingBottom: '0.5rem', borderBottom: '2px solid #fde68a' }} className="dark:text-yellow-400 dark:border-yellow-800">Investment Outlook</h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            <div>
              <strong style={{ color: '#92400e' }} className="dark:text-yellow-400">Short-Term (1-7 days):</strong>
              <p style={{ margin: '0.25rem 0 0', color: '#374151' }} className="dark:text-gray-300">{data.outlook.short_term}</p>
            </div>
            <div>
              <strong style={{ color: '#92400e' }} className="dark:text-yellow-400">Medium-Term (1-3 months):</strong>
              <p style={{ margin: '0.25rem 0 0', color: '#374151' }} className="dark:text-gray-300">{data.outlook.medium_term}</p>
            </div>
            <div>
              <strong style={{ color: '#92400e' }} className="dark:text-yellow-400">Long-Term (6-12 months):</strong>
              <p style={{ margin: '0.25rem 0 0', color: '#374151' }} className="dark:text-gray-300">{data.outlook.long_term}</p>
            </div>
          </div>
        </div>

        {/* Actionable Insights */}
        {data.actionable_insights.length > 0 && (
          <div style={{ padding: '1.5rem', borderRadius: '12px', background: '#eff6ff', border: '1px solid #bfdbfe' }}
            className="dark:bg-blue-900/30 dark:border-blue-800">
            <h3 style={{ marginTop: 0, fontSize: '1.25rem', fontWeight: 700, letterSpacing: '0.025em', color: '#1e40af', paddingBottom: '0.5rem', borderBottom: '2px solid #bfdbfe' }} className="dark:text-blue-400 dark:border-blue-800">Actionable Insights</h3>
            <ul style={{ paddingLeft: '1.25rem' }}>
              {data.actionable_insights.map((item, i) => (
                <li key={i} style={{ marginBottom: '0.5rem', lineHeight: 1.6, color: '#1e40af' }} className="dark:text-blue-300">{item}</li>
              ))}
            </ul>
          </div>
        )}

        {/* Articles Used in Analysis (BOTTOM) */}
        {data.articles_used && data.articles_used.length > 0 && (
          <div style={{ padding: '1.5rem', borderRadius: '12px', background: '#f8fafc', border: '1px solid #e2e8f0' }}
            className="dark:bg-slate-800 dark:border-slate-700">
            <h3 style={{ marginTop: 0, fontSize: '1.25rem', fontWeight: 700, letterSpacing: '0.025em', color: '#1e293b', paddingBottom: '0.5rem', borderBottom: '2px solid #cbd5e1' }} className="dark:text-white dark:border-slate-600">Articles Used in Analysis ({data.articles_used.length})</h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              {(data.articles_used as ArticleReference[]).map((article, index) => {
                const dateStr = article.published_at
                  ? new Date(article.published_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
                  : '';
                return (
                  <div key={index} style={{ paddingLeft: '0.5rem' }}>
                    {article.url ? (
                      <a
                        href={article.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        style={{ fontSize: '0.925rem', lineHeight: 1.5, color: '#3b82f6', textDecoration: 'none' }}
                        className="dark:text-blue-400 hover:underline dark:hover:text-blue-300"
                      >
                        {article.title}
                      </a>
                    ) : (
                      <span style={{ fontSize: '0.925rem', lineHeight: 1.5, color: '#475569' }} className="dark:text-slate-300">
                        {article.title}
                      </span>
                    )}
                    {dateStr && (
                      <span style={{ fontSize: '0.8rem', color: '#94a3b8', marginLeft: '0.5rem' }} className="dark:text-slate-500">
                        ({dateStr})
                      </span>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Disclaimer */}
        <div style={{ padding: '1rem', borderRadius: '8px', background: '#f3f4f6', fontSize: '0.75rem', color: '#6b7280', textAlign: 'center' }}
          className="dark:bg-slate-800 dark:text-slate-500">
          This analysis is generated by an AI model and should not be considered financial advice. Always conduct your own research before making investment decisions.
        </div>
      </>
    );
  };

  if (loading) {
    return (
      <div style={{ maxWidth: 900, margin: '0 auto', padding: '2rem' }}>
        Loading report...
      </div>
    );
  }

  if (error || !report) {
    return (
      <div style={{ maxWidth: 900, margin: '0 auto', padding: '2rem' }}>
        <button onClick={() => router.back()} style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: '1rem', marginBottom: '1rem', color: '#3b82f6' }}
          className="dark:text-blue-400">
          ← Back
        </button>
        <div style={{ padding: '1rem', borderRadius: '8px', background: '#fef2f2', border: '1px solid #fecaca', color: '#dc2626' }}
          className="dark:bg-red-900/30 dark:border-red-800 dark:text-red-400">
          {error || 'Report not found'}
        </div>
      </div>
    );
  }

  return (
    <div style={{ maxWidth: 900, margin: '0 auto', padding: '2rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
        <button onClick={() => router.back()} style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: '1rem', color: '#3b82f6' }}
          className="dark:text-blue-400">
          ← Back
        </button>
        <button onClick={handleDelete} style={{
          background: 'none', border: '1px solid #ef4444', color: '#ef4444',
          padding: '0.375rem 0.75rem', borderRadius: '6px', cursor: 'pointer', fontSize: '0.875rem',
        }}
        className="dark:border-red-800 dark:text-red-500">
          Delete Report
        </button>
      </div>

      {/* Report metadata */}
      <div style={{ display: 'flex', gap: '1rem', marginBottom: '1.5rem', fontSize: '0.875rem', color: '#6b7280', flexWrap: 'wrap' }}
        className="dark:text-slate-400">
        <span><strong>Report ID:</strong> #{report.id}</span>
        <span><strong>Articles:</strong> {report.articles_count}</span>
        <span><strong>Days back:</strong> {report.days_back}</span>
        <span><strong>Model:</strong> {report.model_used}</span>
        <span><strong>Generated:</strong> {new Date(report.created_at).toLocaleString()}</span>
      </div>

      {/* Report content */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '1.75rem' }}>
        {renderReportContent(report.report_data)}
      </div>
    </div>
  );
}
