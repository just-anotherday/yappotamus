'use client';

import { useEffect, useState, useCallback, useRef } from 'react';
import Link from 'next/link';
import { fetchPipelineStatus } from '@/lib/api';
import { timeAgo } from '@/lib/formatters';
import type { PipelineStatus } from '@/types/stock';

export default function PipelineMonitor() {
  const [status, setStatus] = useState<PipelineStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);
  const refreshInFlight = useRef(false);

  const loadStatus = useCallback(async () => {
    if (refreshInFlight.current) return;
    refreshInFlight.current = true;
    setLoading(true);
    setError(null);
    try {
      const data = await fetchPipelineStatus();
      setStatus(data);
      setLastRefresh(new Date());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch pipeline status');
    } finally {
      refreshInFlight.current = false;
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const initialLoad = setTimeout(() => { void loadStatus(); }, 0);
    const interval = setInterval(loadStatus, 10000);
    return () => {
      clearTimeout(initialLoad);
      clearInterval(interval);
    };
  }, [loadStatus]);

  const formatTime = (d: Date) => d.toLocaleTimeString('en-US', {
    timeZone: 'America/New_York',
    timeZoneName: 'short',
  });

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
    fontSize: 30, fontWeight: 550, letterSpacing: '-.04em', color: 'var(--text-primary)',
  };

  const subLabelStyle: React.CSSProperties = { fontSize: 12, color: 'var(--text-muted)' };

  return (
    <div className="workspace-page">
      {/* Header */}
      <div className="page-heading">
        <p className="eyebrow"><span className="accent-line" /> Behind the scenes</p>
        <h1>
          Workspace activity.
        </h1>
        <p>
          Data ingestion and processing at a glance.
          Auto-refreshes every 10s. Last update: {lastRefresh ? formatTime(lastRefresh) : 'Not yet updated'}
        </p>
      </div>

      {/* Refresh Button */}
      <div style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 12, marginBottom: 24 }}>
        <button
          onClick={loadStatus}
          disabled={loading}
          aria-busy={loading}
          aria-describedby="activity-refresh-status"
          className="button-secondary"
        >
          {loading ? <><span className="button-spinner" aria-hidden="true" /> Refreshing…</> : '↻ Refresh Now'}
        </button>
        <span id="activity-refresh-status" role="status" style={subLabelStyle}>
          {loading ? 'Checking for activity updates…' : error ? 'Refresh failed. Try again.' : lastRefresh ? `Activity updated at ${formatTime(lastRefresh)}` : ''}
        </span>
      </div>

      {/* Error State */}
      {error && (
        <div style={{ padding: 16, background: 'var(--negative-soft)', borderRadius: 8, marginBottom: 24, border: '1px solid var(--negative-border)' }}>
          <p style={{ margin: 0, color: 'var(--negative)' }}>{error}</p>
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
                <Link href="/news" style={{ fontSize: 12, color: 'var(--accent)' }}>View Articles →</Link>
              </div>
              <div style={cardStyle}>
                <div style={statLabelStyle}>Articles Today</div>
                <div style={{ ...statValueStyle, color: 'var(--positive)' }}>{(status.news?.articles_today ?? 0).toLocaleString()}</div>
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
                        <strong style={{ color: 'var(--info)', marginRight: 8 }}>{a.ticker}</strong>
                        {a.article_url ? (
                          <a href={a.article_url} target="_blank" rel="noopener noreferrer" style={{ color: 'var(--text-primary)', textDecoration: 'none' }}>
                            {a.title}
                          </a>
                        ) : (
                          <span style={{ color: 'var(--text-primary)' }}>{a.title}</span>
                        )}
                      </span>
                      <span style={{ fontSize: 11, color: 'var(--text-muted)', marginLeft: 12, whiteSpace: 'nowrap' }}>
                        {timeAgo(a.pub_date)}
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
