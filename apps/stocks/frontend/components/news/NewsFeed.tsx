// ==============================================================================
// COMPONENT: NewsFeed - Displays news articles from PostgreSQL with loading/error states
// ==============================================================================

'use client';

import Image from 'next/image';
import React, { useState } from 'react';
import { articleLink } from '@/lib/articleEvidence';
import { useNews } from '@/hooks/useNews';
import { formatDate } from '@/lib/formatters';
import type { NewsArticle } from '@/types/stock';

const FALLBACK_IMAGE = '/news_image.png';

// Deterministic hash: maps any publisher string to a stable index into a color palette.
// No hardcoded publisher names required — new publishers get a color automatically.
function _hashString(s: string): number {
  let h = 0;
  for (let i = 0; i < s.length; i++) {
    h = ((h << 5) - h + s.charCodeAt(i)) | 0;
  }
  return Math.abs(h);
}

const PROVIDER_COLORS = [
  { bg: 'bg-sky-100', text: 'text-sky-700' },
  { bg: 'bg-violet-100', text: 'text-violet-700' },
  { bg: 'bg-positive-soft', text: 'text-positive' },
  { bg: 'bg-negative-soft', text: 'text-negative' },
  { bg: 'bg-warning-soft', text: 'text-warning' },
  { bg: 'bg-info-soft', text: 'text-info' },
  { bg: 'bg-teal-100', text: 'text-teal-700' },
  { bg: 'bg-fuchsia-100', text: 'text-fuchsia-700' },
  { bg: 'bg-accent-soft', text: 'text-accent' },
  { bg: 'bg-cyan-100', text: 'text-cyan-700' },
  { bg: 'bg-lime-100', text: 'text-lime-800' },
  { bg: 'bg-pink-100', text: 'text-pink-700' },
];

function getProviderBadgeColor(provider: string | null): string {
  if (!provider) return 'bg-surface-muted text-secondary';
  const idx = _hashString(provider.toLowerCase()) % PROVIDER_COLORS.length;
  return `${PROVIDER_COLORS[idx].bg} ${PROVIDER_COLORS[idx].text}`;
}

function getDataSourceBadge(source: string | null | undefined): React.ReactNode {
  if (source === 'finnhub') {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium rounded bg-accent-soft text-accent">
        <span className="inline-block w-2 h-2 rounded-full bg-action" />
        Finnhub
      </span>
    );
  }
  if (source === 'yfinance') {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium rounded bg-info-soft text-info">
        <span className="inline-block w-2 h-2 rounded-full bg-action" />
        YFinance
      </span>
    );
  }
  return null;
}

function ArticleCard({ article }: { article: NewsArticle }) {
  const articleUrl = articleLink(article.article_url)?.href;
  const [imgError, setImgError] = useState(false);
  const defaultSrc = article.thumbnail_url || FALLBACK_IMAGE;
  const imageSrc = imgError ? FALLBACK_IMAGE : defaultSrc;
  const providerColor = getProviderBadgeColor(article.provider_name);

  return (
    <div className="bg-card rounded-xl shadow-sm border overflow-hidden hover:shadow-md transition-shadow">
      {/* Thumbnail — always shown, with onError fallback */}
      <a
        href={articleUrl || '#'}
        target="_blank"
        rel="noopener noreferrer"
        className="block hover:opacity-90 transition-opacity"
      >
        <Image unoptimized width={640} height={360}
          src={imageSrc}
          alt={article.title || 'Article thumbnail'}
          className="w-full h-56 object-cover"
          loading="lazy"
          onError={() => setImgError(true)}
        />
      </a>

      <div className="p-5">
        {/* Ticker badge + Data source badge (first) + Author badge */}
        <div className="flex items-center gap-2 mb-3 flex-wrap">
          {article.ticker && (
            <span className="inline-block px-2 py-0.5 text-xs font-semibold rounded bg-info-soft text-info">
              {article.ticker}
            </span>
          )}
          {getDataSourceBadge(article.data_source)}
          {article.author && (
            <span className={`inline-block px-2 py-0.5 text-xs font-medium rounded ${providerColor}`}>
              {article.author}
            </span>
          )}
        </div>

        {/* Title */}
        {articleUrl ? (
          <a href={articleUrl} target="_blank" rel="noopener noreferrer">
            <h2 className="text-lg font-semibold text-primary mb-3 leading-snug hover:text-accent transition-colors">
              {article.title || 'Untitled'}
            </h2>
          </a>
        ) : (
          <h2 className="text-lg font-semibold text-primary mb-3 leading-snug">
            {article.title || 'Untitled'}
          </h2>
        )}

        {/* Summary */}
        {article.summary && (
          <p className="text-sm text-secondary mb-4 line-clamp-4">{article.summary}</p>
        )}

        {/* Meta — date only since provider is now in badge */}
        <div className="flex items-center justify-end text-xs text-muted">
          <span>{article.pub_date ? formatDate(article.pub_date) : ''}</span>
        </div>
      </div>
    </div>
  );
}

interface NewsFeedProps {
  ticker?: string;
  limit?: number;
}

export default function NewsFeed({ ticker, limit = 20 }: NewsFeedProps) {
  const { articles, loading, error, refetch } = useNews(ticker, limit);

  return (
    <div>
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-2xl font-bold text-primary">
            {ticker ? `${ticker} News` : 'Latest News'}
          </h2>
          {!loading && !error && (
            <p className="text-sm text-muted mt-1">
              {articles.length} article{articles.length !== 1 ? 's' : ''} from database
            </p>
          )}
        </div>

        <button
          onClick={refetch}
          disabled={loading}
          className="px-4 py-2 text-sm font-medium rounded-lg border bg-card hover:bg-surface-muted disabled:opacity-50 transition-colors"
        >
          Refresh
        </button>
      </div>

      {/* Loading state */}
      {loading && (
        <div className="flex items-center justify-center py-16">
          <div className="animate-spin h-8 w-8 border-4 border-info-border border-t-transparent rounded-full" />
          <span className="ml-3 text-muted">Loading news articles...</span>
        </div>
      )}

      {/* Error state */}
      {!loading && error && (
        <div className="bg-negative-soft border border-negative-border rounded-xl p-6 text-center">
          <p className="text-negative font-medium">Failed to load news</p>
          <p className="text-sm text-negative mt-1">{error}</p>
          <button
            onClick={refetch}
            className="mt-4 px-4 py-2 text-sm font-medium rounded-lg bg-negative-solid text-white hover:bg-negative-solid transition-colors"
          >
            Try Again
          </button>
        </div>
      )}

      {/* Articles grid */}
      {!loading && !error && articles.length === 0 && (
        <div className="text-center py-16 bg-card rounded-xl border">
          <p className="text-muted">No news articles found.</p>
          <p className="text-xs text-muted mt-2">News updates every 15 minutes from 4 AM to 8 PM ET on weekdays, with hourly off-hours coverage.</p>
        </div>
      )}

      {/* Article cards */}
      {!loading && !error && articles.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {articles.map((article) => (
            <ArticleCard key={article.id} article={article} />
          ))}
        </div>
      )}
    </div>
  );
}
