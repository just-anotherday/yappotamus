'use client';

import { useEffect, useState, useCallback } from 'react';
import { useParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import type { CachedCompanyReport, KeyRisk, TechnicalAnalysisData, OutlookData } from '@/types/stock';
import { fetchCompanyReport, triggerCompanyReportRegeneration } from '@/lib/api';

function sentimentColor(sentiment: string): string {
  const s = sentiment.toLowerCase();
  if (s.includes('very bullish')) return '#00c853';
  if (s.includes('bullish')) return '#4caf50';
  if (s.includes('neutral')) return '#ff9800';
  if (s.includes('bearish')) return '#f44336';
  if (s.includes('very bearish')) return '#b71c1c';
  return '#9e9e9e';
}

function severityColor(severity: string): string {
  const s = severity.toLowerCase();
  if (s === 'high') return '#f44336';
  if (s === 'medium') return '#ff9800';
  return '#4caf50';
}

export default function IntelligenceDetail() {
  const params = useParams();
  const router = useRouter();
  const ticker = typeof params.ticker === 'string' ? params.ticker.toUpperCase() : '';

  const [report, setReport] = useState<CachedCompanyReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [regenerating, setRegenerating] = useState(false);

  const loadReport = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchCompanyReport(ticker);
      setReport(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load report');
    } finally {
      setLoading(false);
    }
  }, [ticker]);

  useEffect(() => {
    if (ticker) loadReport();
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
        <button onClick={() => router.back()} style={{ marginBottom: 16, background: 'none', border: 'none', color: '#2196f3', cursor: 'pointer' }}>
          ← Back
        </button>
        <div style={{ padding: 24, background: '#ffebee', borderRadius: 12, border: '1px solid #ffcdd2' }}>
          <h2 style={{ color: '#c62828', margin: '0 0 8px' }}>⚠️ Report Not Available</h2>
          <p style={{ margin: '0 0 16px' }}>{error}</p>
          <button
            onClick={handleRegenerate}
            disabled={regenerating}
            style={{
              padding: '10px 20px',
              background: regenerating ? '#e0e0e0' : '#4caf50',
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
  const updated = report.last_updated ? new Date(report.last_updated).toLocaleString() : 'N/A';

  return (
    <div style={{ maxWidth: 900, margin: '0 auto', padding: '40px 20px' }}>
      {/* Back + Header */}
      <Link href="/intelligence" style={{ textDecoration: 'none', color: '#2196f3', display: 'inline-block', marginBottom: 24 }}>
        ← Back to Dashboard
      </Link>

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 32, flexWrap: 'wrap', gap: 16 }}>
        <div>
          <h1 style={{ fontSize: 32, fontWeight: 800, margin: '0 0 4px', color: 'var(--text-primary)' }}>{ticker}</h1>
          <p style={{ color: 'var(--text-muted)', margin: 0, fontSize: 13 }}>Last updated: {updated} · Model: {report.model_used} · {report.articles_count} articles analyzed</p>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
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
              background: regenerating ? '#e0e0e0' : '#ff9800',
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

      {/* Sentiment + Confidence */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, marginBottom: 32 }}>
        <div style={{ padding: 24, background: color + '11', border: `1px solid ${color}33`, borderRadius: 12 }}>
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
      <section style={{ marginBottom: 32 }}>
        <h2 style={{ fontSize: 18, fontWeight: 700, marginBottom: 12, color: 'var(--text-primary)' }}>📋 Executive Summary</h2>
        <div style={{ ...cardStyle, lineHeight: 1.7, fontSize: 15, color: 'var(--text-secondary)' }}>
          {rd.executive_summary}
        </div>
      </section>

      {/* Key Catalysts */}
      <section style={{ marginBottom: 32 }}>
        <h2 style={{ fontSize: 18, fontWeight: 700, marginBottom: 12, color: 'var(--text-primary)' }}>🚀 Key Catalysts</h2>
        <div style={cardStyle}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {rd.key_catalysts?.map((c, i) => (
              <div key={i} style={{ padding: '10px 16px', background: 'var(--section-bg)', borderRadius: 8, borderLeft: '4px solid #4caf50', fontSize: 14, color: 'var(--text-primary)' }}>
                {c}
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Key Risks */}
      <section style={{ marginBottom: 32 }}>
        <h2 style={{ fontSize: 18, fontWeight: 700, marginBottom: 12, color: 'var(--text-primary)' }}>⚠️ Key Risks</h2>
        <div style={cardStyle}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {rd.key_risks?.map((r: KeyRisk, i: number) => (
              <div key={i} style={{ padding: '10px 16px', background: 'var(--section-bg)', borderRadius: 8, borderLeft: `4px solid ${severityColor(r.severity)}`, fontSize: 14, color: 'var(--text-primary)' }}>
                <strong>{r.risk}</strong>
                <span style={{ marginLeft: 8, fontSize: 12, color: severityColor(r.severity), fontWeight: 600 }}>[{r.severity}]</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Technical Analysis */}
      <section style={{ marginBottom: 32 }}>
        <h2 style={{ fontSize: 18, fontWeight: 700, marginBottom: 12, color: 'var(--text-primary)' }}>📈 Technical Analysis</h2>
        <div style={cardStyle}>
          {(rd.technical_analysis as TechnicalAnalysisData)?.trend && (
            <>
              <p style={{ margin: '0 0 8px', color: 'var(--text-secondary)' }}><strong>Trend:</strong> {rd.technical_analysis.trend}</p>
              {rd.technical_analysis.support_levels?.length > 0 && (
                <p style={{ margin: '0 0 8px', color: 'var(--text-secondary)' }}><strong>Support:</strong> {rd.technical_analysis.support_levels.join(', ')}</p>
              )}
              {rd.technical_analysis.resistance_levels?.length > 0 && (
                <p style={{ margin: '0 0 8px', color: 'var(--text-secondary)' }}><strong>Resistance:</strong> {rd.technical_analysis.resistance_levels.join(', ')}</p>
              )}
              {rd.technical_analysis.breakout_level && (
                <p style={{ margin: '0 0 8px', color: '#4caf50' }}><strong>Breakout Level:</strong> {rd.technical_analysis.breakout_level}</p>
              )}
              {rd.technical_analysis.breakdown_level && (
                <p style={{ margin: 0, color: '#f44336' }}><strong>Breakdown Level:</strong> {rd.technical_analysis.breakdown_level}</p>
              )}
            </>
          )}
        </div>
      </section>

      {/* Outlook */}
      <section style={{ marginBottom: 32 }}>
        <h2 style={{ fontSize: 18, fontWeight: 700, marginBottom: 12, color: 'var(--text-primary)' }}>🔭 Outlook</h2>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 16 }}>
          {(rd.outlook as OutlookData)?.short_term && (
            <div style={{ padding: 16, background: '#e3f2fd', borderRadius: 8 }}>
              <p style={{ margin: '0 0 4px', fontSize: 12, fontWeight: 700, color: '#1565c0' }}>Short Term (1-7 days)</p>
              <p style={{ margin: 0, fontSize: 13, lineHeight: 1.5, color: 'var(--text-secondary)' }}>{rd.outlook.short_term}</p>
            </div>
          )}
          {(rd.outlook as OutlookData)?.medium_term && (
            <div style={{ padding: 16, background: '#fff3e0', borderRadius: 8 }}>
              <p style={{ margin: '0 0 4px', fontSize: 12, fontWeight: 700, color: '#e65100' }}>Medium Term (1-3 months)</p>
              <p style={{ margin: 0, fontSize: 13, lineHeight: 1.5, color: 'var(--text-secondary)' }}>{rd.outlook.medium_term}</p>
            </div>
          )}
          {(rd.outlook as OutlookData)?.long_term && (
            <div style={{ padding: 16, background: '#e8f5e9', borderRadius: 8 }}>
              <p style={{ margin: '0 0 4px', fontSize: 12, fontWeight: 700, color: '#2e7d32' }}>Long Term (6-12 months)</p>
              <p style={{ margin: 0, fontSize: 13, lineHeight: 1.5, color: 'var(--text-secondary)' }}>{rd.outlook.long_term}</p>
            </div>
          )}
        </div>
      </section>

      {/* Actionable Insights */}
      <section style={{ marginBottom: 32 }}>
        <h2 style={{ fontSize: 18, fontWeight: 700, marginBottom: 12, color: 'var(--text-primary)' }}>💡 Actionable Insights</h2>
        <div style={cardStyle}>
          <ol style={{ paddingLeft: 24, margin: 0, color: 'var(--text-secondary)' }}>
            {rd.actionable_insights?.map((insight, i) => (
              <li key={i} style={{ padding: '6px 0', fontSize: 14, lineHeight: 1.6 }}>{insight}</li>
            ))}
          </ol>
        </div>
      </section>

      {/* Market Reaction */}
      {rd.market_reaction_analysis && (
        <section style={{ marginBottom: 32 }}>
          <h2 style={{ fontSize: 18, fontWeight: 700, marginBottom: 12, color: 'var(--text-primary)' }}>📊 Market Reaction</h2>
          <div style={{ ...cardStyle, lineHeight: 1.7, fontSize: 15, color: 'var(--text-secondary)' }}>
            {rd.market_reaction_analysis}
          </div>
        </section>
      )}

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

      {/* Source Articles */}
      {rd.articles_used?.length > 0 && (
        <section style={{ marginBottom: 32 }}>
          <h2 style={{ fontSize: 18, fontWeight: 700, marginBottom: 12, color: 'var(--text-primary)' }}>📚 Source Articles ({rd.articles_used.length})</h2>
          <div style={cardStyle}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {rd.articles_used.map((a, i) => (
                <a key={i} href={a.url || '#'} target="_blank" rel="noopener noreferrer"
                  style={{ textDecoration: 'none', fontSize: 13, color: '#2196f3', padding: '4px 0' }}>
                  {a.title}
                  {a.published_at && <span style={{ color: 'var(--text-muted)', marginLeft: 8 }}>{new Date(a.published_at).toLocaleDateString()}</span>}
                </a>
              ))}
            </div>
          </div>
        </section>
      )}
    </div>
  );
}
