// ==============================================================================
// COMPONENT: NewsFeed - Displays news articles from PostgreSQL with loading/error states
// ==============================================================================

'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import { useNews } from '@/hooks/useNews';
import type { NewsArticle } from '@/types/stock';

function formatDate(dateStr: string | null): string {
  if (!dateStr) return '';
  try {
    const date = new Date(dateStr);
    return date.toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return dateStr;
  }
}

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
  { bg: 'bg-emerald-100', text: 'text-emerald-700' },
  { bg: 'bg-rose-100', text: 'text-rose-700' },
  { bg: 'bg-amber-100', text: 'text-amber-800' },
  { bg: 'bg-indigo-100', text: 'text-indigo-700' },
  { bg: 'bg-teal-100', text: 'text-teal-700' },
  { bg: 'bg-fuchsia-100', text: 'text-fuchsia-700' },
  { bg: 'bg-orange-100', text: 'text-orange-700' },
  { bg: 'bg-cyan-100', text: 'text-cyan-700' },
  { bg: 'bg-lime-100', text: 'text-lime-800' },
  { bg: 'bg-pink-100', text: 'text-pink-700' },
];

function getProviderBadgeColor(provider: string | null): string {
  if (!provider) return 'bg-gray-100 text-gray-600';
  const idx = _hashString(provider.toLowerCase()) % PROVIDER_COLORS.length;
  return `${PROVIDER_COLORS[idx].bg} ${PROVIDER_COLORS[idx].text}`;
}

function getDataSourceBadge(source: string | null | undefined): React.ReactNode {
  if (source === 'finnhub') {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium rounded bg-orange-100 text-orange-700">
        <span className="inline-block w-2 h-2 rounded-full bg-orange-500" />
        Finnhub
      </span>
    );
  }
  if (source === 'yfinance') {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium rounded bg-blue-100 text-blue-700">
        <span className="inline-block w-2 h-2 rounded-full bg-blue-500" />
        YFinance
      </span>
    );
  }
  return null;
}

function ArticleCard({ article }: { article: NewsArticle }) {
  const [imgError, setImgError] = useState(false);
  const defaultSrc = article.thumbnail_url || FALLBACK_IMAGE;
  const imageSrc = imgError ? FALLBACK_IMAGE : defaultSrc;
  const providerColor = getProviderBadgeColor(article.provider_name);

  return (
    <div className="bg-white rounded-xl shadow-sm border overflow-hidden hover:shadow-md transition-shadow">
      {/* Thumbnail — always shown, with onError fallback */}
      <a
        href={article.article_url || '#'}
        target="_blank"
        rel="noopener noreferrer"
        className="block hover:opacity-90 transition-opacity"
      >
        <img
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
            <span className="inline-block px-2 py-0.5 text-xs font-semibold rounded bg-blue-100 text-blue-700">
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
        {article.article_url ? (
          <a href={article.article_url} target="_blank" rel="noopener noreferrer">
            <h2 className="text-lg font-semibold text-gray-900 mb-3 leading-snug hover:text-blue-600 transition-colors">
              {article.title || 'Untitled'}
            </h2>
          </a>
        ) : (
          <h2 className="text-lg font-semibold text-gray-900 mb-3 leading-snug">
            {article.title || 'Untitled'}
          </h2>
        )}

        {/* Summary */}
        {article.summary && (
          <p className="text-sm text-gray-600 mb-4 line-clamp-4">{article.summary}</p>
        )}

        {/* Meta — date only since provider is now in badge */}
        <div className="flex items-center justify-end text-xs text-gray-500">
          <span>{formatDate(article.pub_date)}</span>
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
          <h2 className="text-2xl font-bold text-gray-900">
            {ticker ? `${ticker} News` : 'Latest News'}
          </h2>
          {!loading && !error && (
            <p className="text-sm text-gray-500 mt-1">
              {articles.length} article{articles.length !== 1 ? 's' : ''} from database
            </p>
          )}
        </div>

        <button
          onClick={refetch}
          disabled={loading}
          className="px-4 py-2 text-sm font-medium rounded-lg border bg-white hover:bg-gray-50 disabled:opacity-50 transition-colors"
        >
          Refresh
        </button>
      </div>

      {/* Loading state */}
      {loading && (
        <div className="flex items-center justify-center py-16">
          <div className="animate-spin h-8 w-8 border-4 border-blue-600 border-t-transparent rounded-full" />
          <span className="ml-3 text-gray-500">Loading news articles...</span>
        </div>
      )}

      {/* Error state */}
      {!loading && error && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-6 text-center">
          <p className="text-red-700 font-medium">Failed to load news</p>
          <p className="text-sm text-red-500 mt-1">{error}</p>
          <button
            onClick={refetch}
            className="mt-4 px-4 py-2 text-sm font-medium rounded-lg bg-red-600 text-white hover:bg-red-700 transition-colors"
          >
            Try Again
          </button>
        </div>
      )}

      {/* Articles grid */}
      {!loading && !error && articles.length === 0 && (
        <div className="text-center py-16 bg-white rounded-xl border">
          <p className="text-gray-500">No news articles found.</p>
          <p className="text-xs text-gray-400 mt-2">News auto-refreshes every 15 minutes during market hours (8 AM – 6 PM EST).</p>
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