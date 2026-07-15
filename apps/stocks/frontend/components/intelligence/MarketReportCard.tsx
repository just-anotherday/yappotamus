'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { fetchMarketReport } from '@/lib/api';
import type { CachedMarketReport } from '@/types/stock';

interface MarketReportCardProps {
  onHover?: (hovering: boolean) => void;
}

function sentimentColor(sentiment: string): string {
  const s = sentiment.toLowerCase();
  if (s.includes('bullish')) return '#4caf50';
  if (s.includes('bearish')) return '#f44336';
  return '#9e9e9e';
}

function sentimentEmoji(sentiment: string): string {
  const s = sentiment.toLowerCase();
  if (s.includes('very bullish')) return '🚀';
  if (s.includes('bullish')) return '📈';
  if (s.includes('bearish')) return '📉';
  if (s.includes('very bearish')) return '💥';
  return '➡️';
}

export default function MarketReportCard({ onHover }: MarketReportCardProps) {
  const [report, setReport] = useState<CachedMarketReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchMarketReport()
      .then(r => {
        setReport(r);
        setError(null);
      })
      .catch(err => {
        setError(err.message || 'Failed to load market report');
      })
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div style={{
        padding: 24,
        background: 'var(--card-bg)',
        borderRadius: 12,
        border: '1px solid var(--card-border)',
        marginBottom: 24,
        textAlign: 'center',
        color: 'var(--text-muted)',
      }}>
        Loading market summary...
      </div>
    );
  }

  if (error || !report) {
    return (
      <div style={{
        padding: 24,
        background: '#fff3e0',
        borderRadius: 12,
        border: '1px solid #ffcc80',
        marginBottom: 24,
        textAlign: 'center',
        color: '#e65100',
      }}>
        <p style={{ margin: 0, fontWeight: 600 }}>No market report available yet.</p>
        <p style={{ margin: '8px 0 0', fontSize: 13, opacity: 0.8 }}>Reports are generated daily at market close.</p>
      </div>
    );
  }

  const rd = report.report_data || {};
  const summaryText = typeof rd === 'string' ? rd : (rd.summary_text || JSON.stringify(rd).slice(0, 300));
  const generatedAt = report.last_generated
    ? new Date(report.last_generated).toLocaleString()
    : 'Unknown';

  return (
    <div
      onMouseEnter={() => onHover?.(true)}
      onMouseLeave={() => onHover?.(false)}
      style={{
        padding: 24,
        background: 'var(--card-bg)',
        borderRadius: 12,
        border: `1px solid ${report.overall_sentiment ? sentimentColor(report.overall_sentiment) : 'var(--card-border)'}`,
        marginBottom: 24,
        boxShadow: '0 2px 8px rgba(0,0,0,0.06)',
      }}
    >
      {/* Header row */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <span style={{ fontSize: 32 }}>{sentimentEmoji(report.overall_sentiment)}</span>
          <div>
            <h2 style={{ margin: 0, fontSize: 18, fontWeight: 700, color: 'var(--text-primary)' }}>
              Daily Market Summary
            </h2>
            <p style={{ margin: '4px 0 0', fontSize: 12, color: 'var(--text-muted)' }}>
              AI-generated market-wide analysis • {generatedAt}
            </p>
          </div>
        </div>

        {/* Sentiment badge */}
        <div style={{
          padding: '6px 14px',
          borderRadius: 20,
          background: sentimentColor(report.overall_sentiment) + '22',
          color: sentimentColor(report.overall_sentiment),
          fontSize: 13,
          fontWeight: 700,
        }}>
          {report.overall_sentiment || 'Neutral'}
        </div>
      </div>

      {/* Risk level + confidence */}
      <div style={{ display: 'flex', gap: 24, marginBottom: 16, fontSize: 13, color: 'var(--text-secondary)' }}>
        {report.risk_level && (
          <span>
            ⚠️ Risk Level: <strong>{report.risk_level}</strong>
          </span>
        )}
        {report.confidence_score !== null && report.confidence_score !== undefined && (
          <span>
            🎯 Confidence: <strong>{Math.round(report.confidence_score * 100)}%</strong>
          </span>
        )}
        {report.model_used && (
          <span>
            🤖 Model: <strong>{report.model_used}</strong>
          </span>
        )}
      </div>

      {/* Summary excerpt */}
      <div style={{
        padding: 16,
        background: 'var(--section-bg)',
        borderRadius: 8,
        fontSize: 14,
        lineHeight: 1.6,
        color: 'var(--text-secondary)',
        marginBottom: 16,
      }}>
        {summaryText}
      </div>

      {/* Footer actions */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Link href="/analysis/market-history" style={{ fontSize: 13, color: '#ff9800', fontWeight: 600 }}>
          View full report & history →
        </Link>
        <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>
          Report #{report.id} • {report.report_date || 'N/A'}
        </span>
      </div>
    </div>
  );
}
