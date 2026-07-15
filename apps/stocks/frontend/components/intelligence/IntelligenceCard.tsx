'use client';

import Link from 'next/link';
import type { CachedCompanyReport } from '@/types/stock';

interface IntelligenceCardProps {
  report: CachedCompanyReport;
  onRegenerate?: () => void;
  isProcessing?: boolean;
  queueStatusText?: string;
}

function sentimentColor(sentiment: string): string {
  const s = sentiment.toLowerCase();
  if (s.includes('very bullish')) return '#00c853';
  if (s.includes('bullish')) return '#4caf50';
  if (s.includes('neutral')) return '#ff9800';
  if (s.includes('bearish')) return '#f44336';
  if (s.includes('very bearish')) return '#b71c1c';
  return '#9e9e9e';
}

function confidenceRing(score: number): string {
  const hue = Math.round((score / 100) * 120);
  return `hsl(${hue}, 70%, 50%)`;
}

export default function IntelligenceCard({ report, onRegenerate, isProcessing, queueStatusText }: IntelligenceCardProps) {
  const rd = report.report_data;
  const color = sentimentColor(report.overall_sentiment);
  const confColor = confidenceRing(report.confidence_score);
  const updated = report.last_updated
    ? new Date(report.last_updated).toLocaleString()
    : 'N/A';

  return (
    <div
      style={{
        border: '1px solid var(--card-border)',
        borderRadius: 12,
        padding: 20,
        background: 'var(--card-bg)',
        boxShadow: '0 2px 8px rgba(0,0,0,0.06)',
        transition: 'transform 0.15s, box-shadow 0.15s',
      }}
      onMouseEnter={(e) => {
        (e.currentTarget as HTMLElement).style.transform = 'translateY(-3px)';
        (e.currentTarget as HTMLElement).style.boxShadow = '0 6px 20px rgba(0,0,0,0.12)';
      }}
      onMouseLeave={(e) => {
        (e.currentTarget as HTMLElement).style.transform = '';
        (e.currentTarget as HTMLElement).style.boxShadow = '';
      }}
    >
      {/* Clickable card content */}
      <Link href={`/intelligence/${report.ticker}`} style={{ textDecoration: 'none', cursor: 'pointer' }}>
        {/* Ticker + Sentiment */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
          <h3 style={{ margin: 0, fontSize: 20, fontWeight: 700, color: 'var(--text-primary)' }}>{report.ticker}</h3>
          <span
            style={{
              background: color + '22',
              color,
              border: `1px solid ${color}44`,
              borderRadius: 6,
              padding: '4px 10px',
              fontSize: 12,
              fontWeight: 700,
              textTransform: 'uppercase',
            }}
          >
            {report.overall_sentiment}
          </span>
        </div>

        {/* Confidence */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
          <div
            style={{
              width: 24,
              height: 24,
              borderRadius: '50%',
              border: `3px solid ${confColor}`,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: 10,
              fontWeight: 700,
              color: confColor,
            }}
          >
            {report.confidence_score}
          </div>
          <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>Confidence</span>
        </div>

        {/* Executive summary (truncated) */}
        <p
          style={{
            margin: '0 0 10px',
            fontSize: 13,
            color: 'var(--text-secondary)',
            lineHeight: 1.5,
            display: '-webkit-box',
            WebkitLineClamp: 3,
            WebkitBoxOrient: 'vertical',
            overflow: 'hidden',
          }}
        >
          {rd.executive_summary || 'No summary available yet.'}
        </p>

        {/* Metadata */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: 11, color: 'var(--text-muted)' }}>
          <span>{report.articles_count} articles</span>
          {report.model_used && (
            <span style={{ 
              background: 'var(--section-bg)', 
              border: '1px solid var(--card-border)', 
              borderRadius: 4, 
              padding: '1px 6px', 
              fontSize: 10,
              fontFamily: 'monospace',
            }}>
              🤖 {report.model_used}
            </span>
          )}
          <span>{updated}</span>
        </div>
      </Link>

      {/* Action buttons row */}
      <div style={{ marginTop: 8, display: 'flex', gap: 6 }}>
        {onRegenerate && (
          <button
            onClick={(e) => {
              e.preventDefault();
              e.stopPropagation();
              onRegenerate();
            }}
            disabled={!!isProcessing}
            style={{
              flex: 1,
              padding: '6px 0',
              background: isProcessing ? '#e3f2fd' : 'var(--card-bg)',
              border: isProcessing ? '1px solid #90caf9' : '1px solid var(--card-border)',
              borderRadius: 6,
              fontSize: 12,
              cursor: isProcessing ? 'not-allowed' : 'pointer',
              color: isProcessing ? '#1565c0' : 'var(--text-secondary)',
            }}
          >
            {isProcessing
              ? (queueStatusText || '⏳ Processing...')
              : '🔄 Regenerate'}
          </button>
        )}
        <Link href={`/intelligence/${report.ticker}/history`}
          style={{
            flex: 0,
            padding: '6px 10px',
            background: 'var(--card-bg)',
            border: '1px solid var(--card-border)',
            borderRadius: 6,
            fontSize: 12,
            textDecoration: 'none',
            color: 'var(--text-muted)',
            display: 'flex',
            alignItems: 'center',
          }}
        >
          📦 Archive
        </Link>
      </div>
    </div>
  );
}
