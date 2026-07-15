'use client';

import Link from 'next/link';
import { timeAgo } from '@/lib/formatters';
import type { NewsArticle } from '@/types/stock';

interface ArticleCardProps {
  article: NewsArticle;
}

/** Validate news source URL - ensures Yahoo articles link to Yahoo domain */
function validateNewsSource(article: NewsArticle): boolean {
  if (!article.article_url) return false;

  try {
    const url = new URL(article.article_url);
    const hostname = url.hostname.toLowerCase();

    // If source is yfinance/Yahoo, prefer Yahoo canonical URLs
    if (article.data_source === 'yfinance' || article.provider_name?.toLowerCase().includes('yahoo')) {
      // Allow Yahoo domains
      if (hostname.includes('finance.yahoo.com') || hostname.includes('yahoo.com')) {
        return true;
      }
      // Block third-party syndicated links when Yahoo source exists
      // (syndicated articles redirect to non-Yahoo sites)
      return false;
    }

    // For Finnhub sources, allow common financial news domains
    const allowedDomains = [
      'finnhub.io', 'reuters.com', 'benzinga.com', 'marketwatch.com',
      'cnbc.com', 'bloomberg.com', 'businessinsider.com', 'forbes.com',
      'investopedia.com', 'seekingalpha.com', 'yahoo.com',
    ];

    return allowedDomains.some(domain => hostname.includes(domain));
  } catch {
    // Invalid URL
    return false;
  }
}

/** Resolve the effective author with proper fallback order */
function resolveAuthor(article: NewsArticle): string {
  // Fallback order: article.author -> metadata.author -> publisher name -> "Unknown Author"
  if (article.author && article.author !== 'Unknown Author' && article.author.trim() !== '') {
    return article.author;
  }
  if (article.provider_name && article.provider_name.trim() !== '') {
    return article.provider_name;
  }
  return ''; // Return empty to hide the author line entirely
}

export default function ArticleCard({ article }: ArticleCardProps) {
  const isValid = validateNewsSource(article);
  const author = resolveAuthor(article);

  const clickUrl = (article.article_url && isValid)
    ? { type: 'external' as const, url: article.article_url }
    : { type: 'internal' as const, url: `/news/${article.ticker || 'ALL'}` };

  return (
    <div className="bg-white dark:bg-slate-800 rounded-xl shadow-sm border border-gray-200 dark:border-slate-700 overflow-hidden hover:shadow-md hover:border-blue-300 dark:hover:border-indigo-500 transition-all duration-200 flex flex-col group">
      {clickUrl.type === 'external' ? (
        <a
          href={clickUrl.url}
          target="_blank"
          rel="noopener noreferrer"
          className="block hover:opacity-90 transition-opacity"
        >
          <img
            src={article.thumbnail_url || '/news_image.png'}
            alt={article.title || 'News'}
            className="w-full h-36 object-cover"
            onError={(e) => { (e.target as HTMLImageElement).src = '/news_image.png'; }}
          />
        </a>
      ) : (
        <Link href={clickUrl.url}>
          <img
            src={article.thumbnail_url || '/news_image.png'}
            alt={article.title || 'News'}
            className="w-full h-36 object-cover"
            onError={(e) => { (e.target as HTMLImageElement).src = '/news_image.png'; }}
          />
        </Link>
      )}

      <div className="p-4 flex flex-col flex-1">
        {article.ticker && (
          <Link
            href={`/news/${article.ticker}`}
            onClick={(e) => e.stopPropagation()}
            className="self-start px-2 py-0.5 rounded-full bg-blue-100 dark:bg-indigo-900/50 text-blue-700 dark:text-indigo-300 text-xs font-semibold mb-2 hover:bg-blue-200 dark:hover:bg-indigo-800 transition-colors"
          >
            {article.ticker}
          </Link>
        )}
        {clickUrl.type === 'external' ? (
          <a
            href={clickUrl.url}
            target="_blank"
            rel="noopener noreferrer"
            className="hover:text-blue-600 dark:hover:text-indigo-300 transition-colors"
          >
            <h3 className="text-sm font-bold text-gray-900 dark:text-gray-100 leading-snug line-clamp-2">
              {article.title || 'Untitled'}
            </h3>
          </a>
        ) : (
          <Link href={clickUrl.url} className="hover:text-blue-600 dark:hover:text-indigo-300 transition-colors">
            <h3 className="text-sm font-bold text-gray-900 dark:text-gray-100 leading-snug line-clamp-2">
              {article.title || 'Untitled'}
            </h3>
          </Link>
        )}

        {/* Author Attribution */}
        {author && (
          <div className="mt-2 flex items-center gap-1.5 text-xs text-gray-600 dark:text-slate-400">
            <svg xmlns="http://www.w3.org/2000/svg" className="h-3 w-3 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
            </svg>
            <span className="truncate">{author}</span>
          </div>
        )}

        {/* Source + Time Footer */}
        <div className="flex items-center justify-between text-xs text-gray-500 dark:text-slate-400 mt-3 pt-3 border-t border-gray-200 dark:border-slate-700">
          <span className="truncate max-w-[50%]">{article.provider_name || ''}</span>
          <span>{timeAgo(article.pub_date)}</span>
        </div>
      </div>
    </div>
  );
}
