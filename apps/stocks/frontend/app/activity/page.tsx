'use client';

import { useEffect, useState, useCallback } from 'react';
import Link from 'next/link';
import { fetchPipelineStatus } from '@/lib/api';
import type { PipelineStatus } from '@/types/stock';

export default function PipelineMonitor() {
  const [status, setStatus] = useState<PipelineStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastRefresh, setLastRefresh] = useState<Date>(new Date());

  const loadStatus = useCallback(async () => {
    setError(null);
    try {
      const data = await fetchPipelineStatus();
      setStatus(data);
      setLastRefresh(new Date());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch pipeline status');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadStatus();
    const interval = setInterval(loadStatus, 10000);
    return () => clearInterval(interval);
  }, [loadStatus]);

  const formatTime = (d: Date) => d.toLocaleTimeString();
  const formatRel = (iso: string | null) => {
    if (!iso) return '';
    const diff = Date.now() - new Date(iso).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return 'just now';
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.floor(mins / 60);
    return `${hrs}h ago`;
  };

  // Shared style tokens
  const cardStyle: React.CSSProperties = {
    padding: 20,
    background: 'var(--card-bg)',
    borderRadius: 12,
    border: '1px solid var(--card-border)',
  };

  const sectionStyle: React.CSSProperties = { marginBottom: 24 };

  const sectionTitleStyle: React.CSSProperties = {
    fontSize: 18, fontWeight: 700, marginBottom: 12,
    display: 'flex', alignItems: 'center', gap: 8,
    color: 'var(--text-primary)',
  };

  const statLabelStyle: React.CSSProperties = {
    fontSize: 13, color: 'var(--text-secondary)', marginBottom: 4,
  };

  const statValueStyle: React.CSSProperties = {
    fontSize: 32, fontWeight: 800, color: 'var(--text-primary)',
  };

  const subLabelStyle: React.CSSProperties = { fontSize: 12, color: 'var(--text-muted)' };

  return (
    <div style={{ maxWidth: 1200, margin: '0 auto', padding: '40px 20px' }}>
      {/* Header */}
      <div style={{ marginBottom: 32 }}>
        <h1 style={{ fontSize: 28, fontWeight: 800, margin: '0 0 8px', color: 'var(--text-primary)' }}>
          ⚡ Activity Monitor
        </h1>
        <p style={{ color: 'var(--text-secondary)', margin: 0, fontSize: 14 }}>
          Real-time visibility into data ingestion and processing.
          Auto-refreshes every 10s. Last update: {formatTime(lastRefresh)}
        </p>
      </div>

      {/* Refresh Button */}
      <div style={{ display: 'flex', gap: 12, marginBottom: 24 }}>
        <button
          onClick={loadStatus}
          disabled={loading}
          style={{
            padding: '10px 20px', background: '#2196f3',
            color: '#fff', border: 'none', borderRadius: 8,
            fontSize: 14, fontWeight: 700,
            cursor: loading ? 'not-allowed' : 'pointer',
          }}
        >
          ↻ Refresh Now
        </button>
      </div>

      {/* Error State */}
      {error && (
        <div style={{ padding: 16, background: '#ffebee', borderRadius: 8, marginBottom: 24, border: '1px solid #ffcdd2' }}>
          <p style={{ margin: 0, color: '#c62828' }}>{error}</p>
        </div>
      )}

      {/* Loading State */}
      {loading && !status && (
        <div style={{ textAlign: 'center', padding: 80, color: 'var(--text-muted)' }}>
          <div style={{ fontSize: 48, marginBottom: 16 }}>🔄</div>
          <p>Loading pipeline status...</p>
        </div>
      )}

      {/* Stats Grid */}
      {status && (
        <>
          {/* Data Ingestion */}
          <div style={sectionStyle}>
            <h2 style={sectionTitleStyle}>Data Ingestion</h2>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 16, marginBottom: 16 }}>
              <div style={cardStyle}>
                <div style={statLabelStyle}>Total Articles</div>
                <div style={statValueStyle}>{(status.news?.total_articles ?? 0).toLocaleString()}</div>
                <Link href="/news" style={{ fontSize: 12, color: '#2196f3' }}>View Articles →</Link>
              </div>
              <div style={cardStyle}>
                <div style={statLabelStyle}>Articles Today</div>
                <div style={{ ...statValueStyle, color: '#2e7d32' }}>{(status.news?.articles_today ?? 0).toLocaleString()}</div>
                <div style={subLabelStyle}>Fresh ingestion</div>
              </div>
            </div>

            {/* Recent Articles List */}
            {status.news?.recent_articles && status.news.recent_articles.length > 0 && (
              <div style={cardStyle}>
                <div style={{ ...statLabelStyle, fontWeight: 700, marginBottom: 8 }}>
                  📰 Headlines Ingested Today
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {status.news.recent_articles.map((a) => (
                    <div key={a.id} style={{ fontSize: 13, display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '4px 8px', borderRadius: 6, background: 'var(--bg-secondary)' }}>
                      <span style={{ fontWeight: 500, flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        <strong style={{ color: '#1565c0', marginRight: 8 }}>{a.ticker}</strong>
                        {a.article_url ? (
                          <a href={a.article_url} target="_blank" rel="noopener noreferrer" style={{ color: 'var(--text-primary)', textDecoration: 'none' }}>
                            {a.title}
                          </a>
                        ) : (
                          <span style={{ color: 'var(--text-primary)' }}>{a.title}</span>
                        )}
                      </span>
                      <span style={{ fontSize: 11, color: 'var(--text-muted)', marginLeft: 12, whiteSpace: 'nowrap' }}>
                        {formatRel(a.pub_date)}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Watchlist with News */}
          <div style={sectionStyle}>
            <h2 style={sectionTitleStyle}>Watchlist with News</h2>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 16 }}>
              <div style={cardStyle}>
                <div style={statLabelStyle}>Tickers w/ News</div>
                <div style={statValueStyle}>{status.news?.tickers_with_news ?? 0}</div>
                <div style={subLabelStyle}>
                  {(status.watchlist?.tickers ?? 0) > 0
                    ? `${status.watchlist?.tickers ?? 0} tickers tracked`
                    : 'No watchlist — add tickers to track'}
                </div>
              </div>
            </div>
          </div>

        </>
      )}
    </div>
  );
}
