'use client';

import { useEffect, useState } from 'react';
import ReportPdfButton from '@/components/ReportPdfButton';
import { useParams, useRouter } from 'next/navigation';
import NeedsMoreResearchSection from '@/components/intelligence/NeedsMoreResearchSection';
import { API_BASE } from '@/lib/serviceUrls';
import { apiFetch } from '@/lib/apiFetch';
import { requireOk } from '@/lib/apiError';
import SourceArticles from '@/components/intelligence/SourceArticles';
import TickerResearchNotes from '@/components/TickerResearchNotes';
import type { ReportDetail, KeyRisk, FinancialAnalysisReport } from '@/types/stock';
import {
  formatArticlesCited,
  formatArticlesSupplied,
  formatReportDateTime,
  getPromptBadge,
  hasOutlook,
  hasTechnicalAnalysis,
} from '@/lib/reportPresentation';

export default function ReportDetailPage() {
  const { id } = useParams();
  const router = useRouter();
  const [report, setReport] = useState<ReportDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiFetch(`${API_BASE}/api/analysis/reports/${id}`)
      .then(async res => {
        await requireOk(res, 'Failed to load report');
        return res.json();
      })
      .then(data => setReport(data))
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, [id]);

  const handleDelete = async () => {
    if (!confirm('Are you sure you want to delete this report?')) return;
    try {
      const res = await apiFetch(`${API_BASE}/api/analysis/reports/${id}`, { method: 'DELETE' });
      await requireOk(res, 'Failed to delete report');
      router.push('/analysis/reports');
    } catch (e) {
      console.error(e);
      alert('Could not delete report');
    }
  };

  const renderReportContent = (data: FinancialAnalysisReport) => {
    const getSentimentColor = (s: string) => {
      switch (s) {
        case 'Very Bullish': return '#166b52';
        case 'Bullish': return '#287b61';
        case 'Neutral': return '#805d17';
        case 'Bearish': return '#b1364e';
        case 'Very Bearish': return '#b1364e';
        default: return 'var(--text-muted)';
      }
    };

    const getSeverityColor = (severity: string) => {
      switch (severity) {
        case 'High': return '#b1364e';
        case 'Medium': return '#805d17';
        case 'Low': return '#166b52';
        default: return 'var(--text-muted)';
      }
    };

    const getInvestmentRatingColor = (rating: string) => {
      switch (rating) {
        case 'Strong Buy': return '#166b52';
        case 'Buy': return '#287b61';
        case 'Hold': return '#805d17';
        case 'Sell': return '#b1364e';
        case 'Strong Sell': return '#b1364e';
        default: return 'var(--text-muted)';
      }
    };

    return (
      <>
        {/* Current Price Banner (TOP) */}
        <div style={{
          padding: '1.25rem 1.5rem', borderRadius: '12px',
          background: 'var(--info-soft)', border: '1px solid var(--info-border)',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        }}
        className="dark:bg-info-soft/30 dark:border-info-border">
          <div>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', fontWeight: 600 }}
              className="dark:text-slate-400">
              Price at Analysis Time
            </span>
            <div style={{ fontSize: '2rem', fontWeight: 800, color: 'var(--info)', marginTop: '0.25rem' }}
              className="dark:text-accent">
              ${(() => {
                // Use report_data price first, fall back to top-level DB column
                const price = data.current_price_at_analysis ?? (report as ReportDetail)?.current_price_at_analysis ?? null;
                return price != null ? Number(price).toFixed(2) : 'N/A';
              })()}
            </div>
          </div>
          <div style={{ textAlign: 'right' }}>
            <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }} className="dark:text-slate-400">
              Asset
            </div>
            <div style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--info)' }} className="dark:text-accent">
              {data.asset}
            </div>
          </div>
        </div>

        {/* Executive Summary & Sentiment Header */}
        <div style={{ padding: '1.5rem', borderRadius: '12px', background: 'var(--section-bg)', border: '1px solid var(--card-border)' }}
          className="dark:bg-slate-800 dark:border-slate-700">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem', flexWrap: 'wrap', gap: '0.5rem' }}>
            <h2 style={{ margin: 0, color: 'var(--text-primary)' }} className="dark:text-white">{data.asset}</h2>
            <div style={{ display: 'flex', gap: '0.5rem' }}>
              {data.investment_rating && (
                <span style={{
                  padding: '0.375rem 1rem', borderRadius: '999px',
                  background: getInvestmentRatingColor(data.investment_rating),
                  color: 'white', fontWeight: 600, fontSize: '0.875rem',
                }}>
                  {data.investment_rating}
                </span>
              )}
              <span style={{
                padding: '0.375rem 1rem', borderRadius: '999px',
                background: getSentimentColor(data.overall_sentiment),
                color: 'white', fontWeight: 600, fontSize: '0.875rem',
              }}>
                {data.overall_sentiment}
              </span>
            </div>
          </div>
          <div style={{ marginBottom: '1rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
              <span style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }} className="dark:text-slate-400">Confidence Score</span>
              <span style={{ fontWeight: 600, color: 'var(--text-secondary)' }} className="dark:text-gray-200">{data.confidence_score}/100</span>
            </div>
            <div style={{ height: 6, borderRadius: 3, background: 'var(--card-border)', overflow: 'hidden' }}
              className="dark:bg-slate-600">
              <div style={{
                width: `${data.confidence_score}%`, height: '100%', borderRadius: 3,
                background: data.confidence_score > 70 ? '#166b52' : data.confidence_score > 40 ? '#805d17' : '#b1364e',
              }} />
            </div>
          </div>
          {data.executive_summary && (
            <p style={{ lineHeight: 1.6, color: 'var(--text-secondary)' }} className="dark:text-gray-300">{data.executive_summary}</p>
          )}
        </div>

        {/* News Summary */}
        {data.news_summary?.length > 0 && (
          <div style={{ padding: '1.5rem', borderRadius: '12px', background: 'var(--card-bg)', border: '1px solid var(--card-border)' }}
            className="dark:bg-slate-800 dark:border-slate-700">
            <h3 style={{ marginTop: 0, fontSize: '1.25rem', fontWeight: 700, letterSpacing: '0.025em', color: 'var(--text-primary)', paddingBottom: '0.5rem', borderBottom: '2px solid var(--card-border)' }} className="dark:text-white dark:border-slate-600">Key News Developments</h3>
            <ul style={{ paddingLeft: '1.25rem' }}>
              {data.news_summary.map((item, i) => (
                <li key={i} style={{ marginBottom: '0.5rem', lineHeight: 1.6, color: 'var(--text-secondary)' }} className="dark:text-gray-300">{item}</li>
              ))}
            </ul>
          </div>
        )}

        {/* Catalysts */}
        {data.key_catalysts?.length > 0 && (
          <div style={{ padding: '1.5rem', borderRadius: '12px', background: 'var(--positive-soft)', border: '1px solid var(--positive-border)' }}
            className="dark:bg-positive-soft/30 dark:border-positive-border">
            <h3 style={{ marginTop: 0, fontSize: '1.25rem', fontWeight: 700, letterSpacing: '0.025em', color: 'var(--positive)', paddingBottom: '0.5rem', borderBottom: '2px solid var(--positive-border)' }} className="dark:text-positive dark:border-positive-border">Key Catalysts</h3>
            <ul style={{ paddingLeft: '1.25rem' }}>
              {data.key_catalysts.map((item, i) => (
                <li key={i} style={{ marginBottom: '0.5rem', lineHeight: 1.6, color: 'var(--positive)' }} className="dark:text-positive">{item}</li>
              ))}
            </ul>
          </div>
        )}

        {/* Risks */}
        {data.key_risks?.length > 0 && (
          <div style={{ padding: '1.5rem', borderRadius: '12px', background: 'var(--negative-soft)', border: '1px solid var(--negative-border)' }}
            className="dark:bg-negative-soft/30 dark:border-negative-border">
            <h3 style={{ marginTop: 0, fontSize: '1.25rem', fontWeight: 700, letterSpacing: '0.025em', color: 'var(--negative)', paddingBottom: '0.5rem', borderBottom: '2px solid var(--negative-border)' }} className="dark:text-negative dark:border-negative-border">Key Risks</h3>
            <ul style={{ paddingLeft: '1.25rem' }}>
              {data.key_risks.map((risk: KeyRisk, i) => (
                <li key={i} style={{ marginBottom: '0.5rem', lineHeight: 1.6, color: 'var(--negative)' }} className="dark:text-negative">
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

        {/* Bull Case / Bear Case */}
        {((data.bull_case && data.bull_case.length > 0) || (data.bear_case && data.bear_case.length > 0)) && (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: '1.5rem' }}>
            {data.bull_case && data.bull_case.length > 0 && (
              <div style={{ padding: '1.5rem', borderRadius: '12px', background: 'var(--positive-soft)', border: '1px solid var(--positive-border)' }}
                className="dark:bg-positive-soft/30 dark:border-positive-border">
                <h3 style={{ marginTop: 0, fontSize: '1.25rem', fontWeight: 700, letterSpacing: '0.025em', color: 'var(--positive)', paddingBottom: '0.5rem', borderBottom: '2px solid var(--positive-border)' }} className="dark:text-positive dark:border-positive-border">Bull Case</h3>
                <ul style={{ paddingLeft: '1.25rem' }}>
                  {data.bull_case.map((item, i) => (
                    <li key={i} style={{ marginBottom: '0.5rem', lineHeight: 1.6, color: 'var(--positive)' }} className="dark:text-positive">{item}</li>
                  ))}
                </ul>
              </div>
            )}
            {data.bear_case && data.bear_case.length > 0 && (
              <div style={{ padding: '1.5rem', borderRadius: '12px', background: 'var(--negative-soft)', border: '1px solid var(--negative-border)' }}
                className="dark:bg-negative-soft/30 dark:border-negative-border">
                <h3 style={{ marginTop: 0, fontSize: '1.25rem', fontWeight: 700, letterSpacing: '0.025em', color: 'var(--negative)', paddingBottom: '0.5rem', borderBottom: '2px solid var(--negative-border)' }} className="dark:text-negative dark:border-negative-border">Bear Case</h3>
                <ul style={{ paddingLeft: '1.25rem' }}>
                  {data.bear_case.map((item, i) => (
                    <li key={i} style={{ marginBottom: '0.5rem', lineHeight: 1.6, color: 'var(--negative)' }} className="dark:text-negative">{item}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}

        {/* Market Reaction */}
        {data.market_reaction_analysis && (
          <div style={{ padding: '1.5rem', borderRadius: '12px', background: 'var(--card-bg)', border: '1px solid var(--card-border)' }}
            className="dark:bg-slate-800 dark:border-slate-700">
            <h3 style={{ marginTop: 0, fontSize: '1.25rem', fontWeight: 700, letterSpacing: '0.025em', color: 'var(--text-primary)', paddingBottom: '0.5rem', borderBottom: '2px solid var(--card-border)' }} className="dark:text-white dark:border-slate-600">Market Reaction Analysis</h3>
            <p style={{ lineHeight: 1.6, color: 'var(--text-secondary)' }} className="dark:text-gray-300">{data.market_reaction_analysis}</p>
          </div>
        )}

        {/* Technical Analysis */}
        {hasTechnicalAnalysis(data.technical_analysis) && data.technical_analysis && (
          <div style={{ padding: '1.5rem', borderRadius: '12px', background: 'var(--card-bg)', border: '1px solid var(--card-border)' }}
            className="dark:bg-slate-800 dark:border-slate-700">
            <h3 style={{ marginTop: 0, fontSize: '1.25rem', fontWeight: 700, letterSpacing: '0.025em', color: 'var(--text-primary)', paddingBottom: '0.5rem', borderBottom: '2px solid var(--card-border)' }} className="dark:text-white dark:border-slate-600">Technical Context</h3>
          {data.technical_analysis.trend && (
            <p style={{ color: 'var(--text-secondary)' }} className="dark:text-gray-300"><strong>Trend:</strong> {data.technical_analysis.trend}</p>
          )}
          {data.technical_analysis.support_levels?.length > 0 && (
            <p style={{ color: 'var(--text-secondary)' }} className="dark:text-gray-300"><strong>Support Levels:</strong> {data.technical_analysis.support_levels.join(', ')}</p>
          )}
          {data.technical_analysis.resistance_levels?.length > 0 && (
            <p style={{ color: 'var(--text-secondary)' }} className="dark:text-gray-300"><strong>Resistance Levels:</strong> {data.technical_analysis.resistance_levels.join(', ')}</p>
          )}
          {data.technical_analysis.breakout_level && (
            <p style={{ color: 'var(--text-secondary)' }} className="dark:text-gray-300"><strong>Breakout Level:</strong> {data.technical_analysis.breakout_level}</p>
          )}
          {data.technical_analysis.breakdown_level && (
            <p style={{ color: 'var(--text-secondary)' }} className="dark:text-gray-300"><strong>Breakdown Level:</strong> {data.technical_analysis.breakdown_level}</p>
          )}
          </div>
        )}

        {/* Outlook */}
        {hasOutlook(data.outlook) && data.outlook && (
          <div style={{ padding: '1.5rem', borderRadius: '12px', background: 'var(--warning-soft)', border: '1px solid var(--warning-border)' }}
          className="dark:bg-warning-soft/30 dark:border-warning-border">
          <h3 style={{ marginTop: 0, fontSize: '1.25rem', fontWeight: 700, letterSpacing: '0.025em', color: 'var(--warning)', paddingBottom: '0.5rem', borderBottom: '2px solid var(--warning-border)' }} className="dark:text-warning dark:border-warning-border">Investment Outlook</h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            {data.outlook.short_term && <div>
              <strong style={{ color: 'var(--warning)' }} className="dark:text-warning">Short-Term (1-7 days):</strong>
              <p style={{ margin: '0.25rem 0 0', color: 'var(--text-secondary)' }} className="dark:text-gray-300">{data.outlook.short_term}</p>
            </div>}
            {data.outlook.medium_term && <div>
              <strong style={{ color: 'var(--warning)' }} className="dark:text-warning">Medium-Term (1-3 months):</strong>
              <p style={{ margin: '0.25rem 0 0', color: 'var(--text-secondary)' }} className="dark:text-gray-300">{data.outlook.medium_term}</p>
            </div>}
            {data.outlook.long_term && <div>
              <strong style={{ color: 'var(--warning)' }} className="dark:text-warning">Long-Term (6-12 months):</strong>
              <p style={{ margin: '0.25rem 0 0', color: 'var(--text-secondary)' }} className="dark:text-gray-300">{data.outlook.long_term}</p>
            </div>}
          </div>
          </div>
        )}

        {/* Actionable Insights */}
        {data.actionable_insights?.length > 0 && (
          <div style={{ padding: '1.5rem', borderRadius: '12px', background: 'var(--info-soft)', border: '1px solid var(--info-border)' }}
            className="dark:bg-info-soft/30 dark:border-info-border">
            <h3 style={{ marginTop: 0, fontSize: '1.25rem', fontWeight: 700, letterSpacing: '0.025em', color: 'var(--info)', paddingBottom: '0.5rem', borderBottom: '2px solid var(--info-border)' }} className="dark:text-accent dark:border-info-border">Actionable Insights</h3>
            <ul style={{ paddingLeft: '1.25rem' }}>
              {data.actionable_insights.map((item, i) => (
                <li key={i} style={{ marginBottom: '0.5rem', lineHeight: 1.6, color: 'var(--info)' }} className="dark:text-accent">{item}</li>
              ))}
            </ul>
          </div>
        )}

        <NeedsMoreResearchSection items={data.needs_more_research} />

        {/* Portfolio Fit */}
        {data.portfolio_fit && (
          <div style={{ padding: '1.5rem', borderRadius: '12px', background: 'var(--section-bg)', border: '1px solid var(--card-border)' }}
            className="dark:bg-slate-800 dark:border-slate-700">
            <h3 style={{ marginTop: 0, fontSize: '1.25rem', fontWeight: 700, letterSpacing: '0.025em', color: 'var(--text-primary)', paddingBottom: '0.5rem', borderBottom: '2px solid #cbd5e1' }} className="dark:text-white dark:border-slate-600">Portfolio Consideration</h3>
            <p style={{ lineHeight: 1.6, color: 'var(--text-secondary)' }} className="dark:text-gray-300">{data.portfolio_fit}</p>
          </div>
        )}

        <SourceArticles articles={data.articles_used} />

        {/* Disclaimer */}
        <div style={{ padding: '1rem', borderRadius: '8px', background: 'var(--section-bg)', fontSize: '0.75rem', color: 'var(--text-muted)', textAlign: 'center' }}
          className="dark:bg-slate-800 dark:text-slate-500">
          This analysis is generated by an AI model and should not be considered financial advice. Always conduct your own research before making investment decisions.
        </div>
      </>
    );
  };

  if (loading) {
    return (
      <div className="workspace-page report-detail-workspace">
        Loading report...
      </div>
    );
  }

  if (error || !report) {
    return (
      <div className="workspace-page report-detail-workspace">
        <button onClick={() => router.back()} style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: '1rem', marginBottom: '1rem', color: 'var(--accent)' }}
          className="dark:text-accent">
          ← Back
        </button>
        <div style={{ padding: '1rem', borderRadius: '8px', background: 'var(--negative-soft)', border: '1px solid var(--negative-border)', color: 'var(--negative)' }}
          className="dark:bg-negative-soft/30 dark:border-negative-border dark:text-negative">
          {error || 'Report not found'}
        </div>
      </div>
    );
  }

  return (
    <div className="workspace-page report-detail-workspace">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
        <button onClick={() => router.back()} style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: '1rem', color: 'var(--accent)' }}
          className="dark:text-accent">
          ← Back
        </button>
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
        <ReportPdfButton report={report} />
        <button onClick={handleDelete} style={{
          background: 'none', border: '1px solid #b1364e', color: 'var(--negative)',
          padding: '0.375rem 0.75rem', borderRadius: '6px', cursor: 'pointer', fontSize: '0.875rem',
        }}
        className="dark:border-negative-border dark:text-negative">
          Delete Report
        </button>
        </div>
      </div>

      <div style={{ marginBottom: '1rem' }}>
        <h1 style={{ margin: 0, fontSize: '1.75rem', color: 'var(--text-primary)' }} className="dark:text-white">
          {report.ticker} Analysis
        </h1>
        <div style={{ marginTop: 4, color: 'var(--text-muted)', fontSize: '0.875rem' }} className="dark:text-slate-400">
          {formatReportDateTime(report.created_at)}
        </div>
      </div>

      {/* Report metadata */}
      <div style={{ display: 'flex', gap: '1rem', marginBottom: '1.5rem', fontSize: '0.875rem', color: 'var(--text-muted)', flexWrap: 'wrap' }}
        className="dark:text-slate-400">
        <span style={{ fontSize: '0.75rem' }}><strong>Record ID:</strong> {report.id}</span>
        <span>{formatArticlesSupplied(report.articles_count)}</span>
        <span>{formatArticlesCited(report.report_data.articles_used?.length ?? 0)}</span>
        <span><strong>Model:</strong> {report.model_used}</span>
        <span><strong>Prompt:</strong> {getPromptBadge(report.prompt_version, report.prompt_hash)}</span>
      </div>

      <div className="mb-5">
        <a href="#report-sources" className="text-sm font-medium text-accent underline underline-offset-4 dark:text-accent">View supporting articles ({report.report_data.articles_used?.length ?? 0}) ↓</a>
      </div>
      <TickerResearchNotes ticker={report.ticker} />

      {/* Report content */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '1.75rem' }}>
        {renderReportContent(report.report_data)}
      </div>
    </div>
  );
}
