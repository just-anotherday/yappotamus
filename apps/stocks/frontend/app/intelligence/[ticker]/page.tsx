'use client';

import { useEffect, useState, useCallback } from 'react';
import { useParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import ReportPdfButton from '@/components/ReportPdfButton';
import type { CachedCompanyReport, KeyRisk } from '@/types/stock';
import NeedsMoreResearchSection from '@/components/intelligence/NeedsMoreResearchSection';
import { fetchCompanyReport, triggerCompanyReportRegeneration } from '@/lib/api';
import SourceArticles from '@/components/intelligence/SourceArticles';
import TickerResearchNotes from '@/components/TickerResearchNotes';
import { formatReportDateTime, hasOutlook, hasTechnicalAnalysis } from '@/lib/reportPresentation';

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

export default function IntelligenceDetail() {
  const params = useParams();
  const router = useRouter();
  const ticker = typeof params.ticker === 'string' ? params.ticker.toUpperCase() : '';

  const [report, setReport] = useState<CachedCompanyReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [regenerating, setRegenerating] = useState(false);

  const loadReport = useCallback(async (signal?: AbortSignal) => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchCompanyReport(ticker, signal);
      if (!signal?.aborted) setReport(data);
    } catch (err) {
      if (!signal?.aborted) setError(err instanceof Error ? err.message : 'Failed to load report');
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, [ticker]);

  useEffect(() => {
    if (!ticker) return;
    const controller = new AbortController();
    const timer = setTimeout(() => { void loadReport(controller.signal); }, 0);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [ticker, loadReport]);

  const handleRegenerate = async () => {
    setRegenerating(true);
    try {
      await triggerCompanyReportRegeneration(ticker);
      setTimeout(loadReport, 2000);
    } catch (err) {
      console.error('Failed to regenerate:', err);
    } finally {
      setRegenerating(false);
    }
  };

  // Shared style tokens
  const cardStyle: React.CSSProperties = {
    padding: 24,
    background: 'var(--card-bg)',
    borderRadius: 12,
    border: '1px solid var(--card-border)',
  };

  if (!ticker) {
    return <div style={{ padding: 40, color: 'var(--text-primary)' }}>Invalid ticker.</div>;
  }

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: 80, color: 'var(--text-muted)' }}>
        <div style={{ fontSize: 48, marginBottom: 16 }}>🔄</div>
        <p>Loading intelligence for {ticker}...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ maxWidth: 800, margin: '0 auto', padding: '40px 20px' }}>
        <button onClick={() => router.back()} style={{ marginBottom: 16, background: 'none', border: 'none', color: 'var(--accent)', cursor: 'pointer' }}>
          ← Back
        </button>
        <TickerResearchNotes ticker={ticker} />
        <div style={{ padding: 24, background: 'var(--negative-soft)', borderRadius: 12, border: '1px solid var(--negative-border)' }}>
          <h2 style={{ color: 'var(--negative)', margin: '0 0 8px' }}>⚠️ Report Not Available</h2>
          <p style={{ margin: '0 0 16px' }}>{error}</p>
          <button
            onClick={handleRegenerate}
            disabled={regenerating}
            style={{
              padding: '10px 20px',
              background: regenerating ? 'var(--card-border)' : 'var(--positive)',
              color: '#fff',
              border: 'none',
              borderRadius: 8,
              cursor: regenerating ? 'not-allowed' : 'pointer',
              fontWeight: 600,
            }}
          >
            {regenerating ? '⏳ Queuing...' : `🔄 Generate Report for ${ticker}`}
          </button>
        </div>
      </div>
    );
  }

  if (!report) return null;

  const rd = report.report_data;
  const color = sentimentColor(report.overall_sentiment);
  const updated = report.last_updated ? formatReportDateTime(report.last_updated) : 'N/A';

  return (
    <div style={{ maxWidth: 900, margin: '0 auto', padding: '40px 20px' }}>
      {/* Back + Header */}
      <Link href="/analysis/reports" style={{ textDecoration: 'none', color: 'var(--accent)', display: 'inline-block', marginBottom: 24 }}>
        ← Back to Analysis Reports
      </Link>

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 32, flexWrap: 'wrap', gap: 16 }}>
        <div>
          <h1 style={{ fontSize: 32, fontWeight: 800, margin: '0 0 4px', color: 'var(--text-primary)' }}>{ticker}</h1>
          <p style={{ color: 'var(--text-muted)', margin: 0, fontSize: 13 }}>Last updated: {updated} · Model: {report.model_used} · {report.articles_count} articles analyzed</p>
        </div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <ReportPdfButton report={report} />
          <Link href={`/intelligence/${ticker}/history`} style={{
            padding: '10px 20px',
            background: '#7c4dff',
            color: '#fff',
            border: 'none',
            borderRadius: 8,
            textDecoration: 'none',
            fontWeight: 600,
            display: 'inline-flex',
            alignItems: 'center',
          }}>
            📦 History
          </Link>
          <button
            onClick={handleRegenerate}
            disabled={regenerating}
            style={{
              padding: '10px 20px',
              background: regenerating ? 'var(--card-border)' : 'var(--warning)',
              color: '#fff',
              border: 'none',
              borderRadius: 8,
              cursor: regenerating ? 'not-allowed' : 'pointer',
              fontWeight: 600,
            }}
          >
            {regenerating ? '⏳ Queued...' : '🔄 Regenerate'}
          </button>
        </div>
      </div>

      <div className="mb-5">
        <a href="#report-sources" className="text-sm font-medium text-accent underline underline-offset-4 dark:text-accent">View supporting articles ({rd.articles_used?.length ?? 0}) ↓</a>
      </div>
      <TickerResearchNotes ticker={ticker} />

      {/* Sentiment + Confidence */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, marginBottom: 32 }}>
        <div style={{ padding: 24, background: `color-mix(in srgb, ${color} 7%, transparent)`, border: `1px solid color-mix(in srgb, ${color} 20%, transparent)`, borderRadius: 12 }}>
          <p style={{ margin: '0 0 4px', fontSize: 13, color: 'var(--text-muted)' }}>Overall Sentiment</p>
          <h2 style={{ margin: 0, color, fontSize: 28, fontWeight: 800 }}>{report.overall_sentiment}</h2>
        </div>
        <div style={{ ...cardStyle }}>
          <p style={{ margin: '0 0 4px', fontSize: 13, color: 'var(--text-muted)' }}>Confidence Score</p>
          <h2 style={{ margin: 0, color: 'var(--text-primary)', fontSize: 28, fontWeight: 800 }}>
            {report.confidence_score}/100
            <span style={{ fontSize: 14, fontWeight: 400, color: 'var(--text-muted)' }}>
              {' '}({report.confidence_score >= 70 ? 'High' : report.confidence_score >= 40 ? 'Medium' : 'Low'})
            </span>
          </h2>
        </div>
      </div>

      {/* Executive Summary */}
      {rd.executive_summary && (
        <section style={{ marginBottom: 32 }}>
          <h2 style={{ fontSize: 18, fontWeight: 700, marginBottom: 12, color: 'var(--text-primary)' }}>📋 Executive Summary</h2>
          <div style={{ ...cardStyle, lineHeight: 1.7, fontSize: 15, color: 'var(--text-secondary)' }}>
            {rd.executive_summary}
          </div>
        </section>
      )}

      {/* Key Catalysts */}
      {rd.key_catalysts?.length > 0 && (
        <section style={{ marginBottom: 32 }}>
          <h2 style={{ fontSize: 18, fontWeight: 700, marginBottom: 12, color: 'var(--text-primary)' }}>🚀 Key Catalysts</h2>
          <div style={cardStyle}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {rd.key_catalysts.map((c, i) => (
                <div key={i} style={{ padding: '10px 16px', background: 'var(--section-bg)', borderRadius: 8, borderLeft: '4px solid var(--positive)', fontSize: 14, color: 'var(--text-primary)' }}>
                  {c}
                </div>
              ))}
            </div>
          </div>
        </section>
      )}

      {/* Key Risks */}
      {rd.key_risks?.length > 0 && (
        <section style={{ marginBottom: 32 }}>
          <h2 style={{ fontSize: 18, fontWeight: 700, marginBottom: 12, color: 'var(--text-primary)' }}>⚠️ Key Risks</h2>
          <div style={cardStyle}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {rd.key_risks.map((r: KeyRisk, i: number) => (
                <div key={i} style={{ padding: '10px 16px', background: 'var(--section-bg)', borderRadius: 8, borderLeft: `4px solid ${severityColor(r.severity)}`, fontSize: 14, color: 'var(--text-primary)' }}>
                  <strong>{r.risk}</strong>
                  <span style={{ marginLeft: 8, fontSize: 12, color: severityColor(r.severity), fontWeight: 600 }}>[{r.severity}]</span>
                </div>
              ))}
            </div>
          </div>
        </section>
      )}

      {/* Technical Analysis */}
      {hasTechnicalAnalysis(rd.technical_analysis) && (
        <section style={{ marginBottom: 32 }}>
          <h2 style={{ fontSize: 18, fontWeight: 700, marginBottom: 12, color: 'var(--text-primary)' }}>📈 Technical Analysis</h2>
          <div style={cardStyle}>
            {rd.technical_analysis && (
              <>
              {rd.technical_analysis.trend && (
              <p style={{ margin: '0 0 8px', color: 'var(--text-secondary)' }}><strong>Trend:</strong> {rd.technical_analysis.trend}</p>
              )}
              {rd.technical_analysis.support_levels?.length > 0 && (
                <p style={{ margin: '0 0 8px', color: 'var(--text-secondary)' }}><strong>Support:</strong> {rd.technical_analysis.support_levels.join(', ')}</p>
              )}
              {rd.technical_analysis.resistance_levels?.length > 0 && (
                <p style={{ margin: '0 0 8px', color: 'var(--text-secondary)' }}><strong>Resistance:</strong> {rd.technical_analysis.resistance_levels.join(', ')}</p>
              )}
              {rd.technical_analysis.breakout_level && (
                <p style={{ margin: '0 0 8px', color: 'var(--positive)' }}><strong>Breakout Level:</strong> {rd.technical_analysis.breakout_level}</p>
              )}
              {rd.technical_analysis.breakdown_level && (
                <p style={{ margin: 0, color: 'var(--negative)' }}><strong>Breakdown Level:</strong> {rd.technical_analysis.breakdown_level}</p>
              )}
              </>
            )}
          </div>
        </section>
      )}

      {/* Outlook */}
      {hasOutlook(rd.outlook) && (
        <section style={{ marginBottom: 32 }}>
          <h2 style={{ fontSize: 18, fontWeight: 700, marginBottom: 12, color: 'var(--text-primary)' }}>🔭 Outlook</h2>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 16 }}>
          {rd.outlook?.short_term && (
            <div style={{ padding: 16, background: 'var(--info-soft)', borderRadius: 8 }}>
              <p style={{ margin: '0 0 4px', fontSize: 12, fontWeight: 700, color: 'var(--info)' }}>Short Term (1-7 days)</p>
              <p style={{ margin: 0, fontSize: 13, lineHeight: 1.5, color: 'var(--text-secondary)' }}>{rd.outlook.short_term}</p>
            </div>
          )}
          {rd.outlook?.medium_term && (
            <div style={{ padding: 16, background: 'var(--warning-soft)', borderRadius: 8 }}>
              <p style={{ margin: '0 0 4px', fontSize: 12, fontWeight: 700, color: '#e65100' }}>Medium Term (1-3 months)</p>
              <p style={{ margin: 0, fontSize: 13, lineHeight: 1.5, color: 'var(--text-secondary)' }}>{rd.outlook.medium_term}</p>
            </div>
          )}
          {rd.outlook?.long_term && (
            <div style={{ padding: 16, background: 'var(--positive-soft)', borderRadius: 8 }}>
              <p style={{ margin: '0 0 4px', fontSize: 12, fontWeight: 700, color: 'var(--positive)' }}>Long Term (6-12 months)</p>
              <p style={{ margin: 0, fontSize: 13, lineHeight: 1.5, color: 'var(--text-secondary)' }}>{rd.outlook.long_term}</p>
            </div>
          )}
          </div>
        </section>
      )}

      {/* Actionable Insights */}
      {rd.actionable_insights?.length > 0 && (
        <section style={{ marginBottom: 32 }}>
          <h2 style={{ fontSize: 18, fontWeight: 700, marginBottom: 12, color: 'var(--text-primary)' }}>💡 Actionable Insights</h2>
          <div style={cardStyle}>
            <ol style={{ paddingLeft: 24, margin: 0, color: 'var(--text-secondary)' }}>
              {rd.actionable_insights.map((insight, i) => (
                <li key={i} style={{ padding: '6px 0', fontSize: 14, lineHeight: 1.6 }}>{insight}</li>
              ))}
          </ol>
          </div>
        </section>
      )}

      {/* Market Reaction */}
      {rd.market_reaction_analysis && (
        <section style={{ marginBottom: 32 }}>
          <h2 style={{ fontSize: 18, fontWeight: 700, marginBottom: 12, color: 'var(--text-primary)' }}>📊 Market Reaction</h2>
          <div style={{ ...cardStyle, lineHeight: 1.7, fontSize: 15, color: 'var(--text-secondary)' }}>
            {rd.market_reaction_analysis}
          </div>
        </section>
      )}

      <NeedsMoreResearchSection items={rd.needs_more_research} />

      {/* News Summary */}
      {rd.news_summary?.length > 0 && (
        <section style={{ marginBottom: 32 }}>
          <h2 style={{ fontSize: 18, fontWeight: 700, marginBottom: 12, color: 'var(--text-primary)' }}>📰 News Summary</h2>
          <div style={cardStyle}>
            <ul style={{ paddingLeft: 24, margin: 0, color: 'var(--text-secondary)' }}>
              {rd.news_summary.map((item, i) => (
                <li key={i} style={{ padding: '4px 0', fontSize: 13, lineHeight: 1.5 }}>{item}</li>
              ))}
            </ul>
          </div>
        </section>
      )}

      <SourceArticles articles={rd.articles_used} />
    </div>
  );
}
