// ==============================================================================
// PAGE: /news/[ticker] - Stock news detail page with live ticker header (Light + Dark Theme)
// ==============================================================================

'use client';

import { useState, useEffect } from 'react';
import { useParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import { useNews } from '@/hooks/useNews';
import { fetchNewsTickers } from '@/lib/api';
import TickerHeader from '@/components/stock/TickerHeader';
import { NewsCard } from '@/components/news/NewsCard';

export default function TickerNewsPage() {
  const params = useParams();
  const router = useRouter();
  const ticker = (params.ticker as string).toUpperCase();

  const [allTickers, setAllTickers] = useState<string[]>([]);

  // Fetch all distinct tickers from the database on mount
  useEffect(() => {
    let cancelled = false;
    fetchNewsTickers()
      .then(tickers => { if (!cancelled) setAllTickers(tickers); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, []);

  // Fetch persisted articles for this ticker from PostgreSQL
  const {
    articles,
    loading,
    error,
    refetch,
    setPage,
    goToNextPage,
    goToPrevPage,
    total,
    totalPages,
    page,
    offset,
  } = useNews(ticker, 50);

  // Handle ticker dropdown change - navigate to that ticker's news page
  const handleTickerSelect = (selectedTicker: string) => {
    if (selectedTicker === ticker) return; // already viewing this ticker
    router.push(`/news/${selectedTicker}`);
  };

  return (
    <div className="min-h-screen bg-sky-100 dark:bg-gradient-to-br dark:from-slate-800 dark:via-gray-900 dark:to-slate-700">
      <div className="max-w-6xl mx-auto px-4 py-12">

        {/* Breadcrumb */}
        <nav className="flex items-center gap-2 text-sm text-gray-600 mb-4">
          <Link href="/" className="hover:text-blue-600 transition-colors">
            Dashboard
          </Link>
          <span>›</span>
          <Link href="/news" className="hover:text-blue-600 transition-colors">
            All News
          </Link>
          <span>›</span>
          <span className="font-semibold text-gray-900">{ticker}</span>
        </nav>

        {/* ============================ */}
        {/* Ticker Info + Live Price     */}
        {/* ============================ */}
        <TickerHeader ticker={ticker} />

        {/* ============================ */}
        {/* Large Navigation Buttons     */}
        {/* ============================ */}
        <div className="flex flex-wrap gap-4 mb-6">
          <Link
            href="/news"
            className="flex-1 min-w-[200px] px-6 py-4 rounded-xl border-2 border-blue-300 bg-blue-50 text-lg font-semibold text-blue-700 shadow-sm hover:bg-blue-100 hover:border-blue-400 transition-all duration-200 flex items-center justify-center gap-2 dark:border-indigo-600 dark:bg-indigo-900/30 dark:text-indigo-300 dark:hover:bg-indigo-800"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M19 20H5a2 2 0 01-2-2V6a2 2 0 012-2h10a2 2 0 012 2v1m2 11a2 2 0 01-2-2V7m2 10a2 2 0 002-2V9a2 2 0 00-2-2h-4" />
            </svg>
            Back to All News
          </Link>
          <Link
            href="/"
            className="flex-1 min-w-[200px] px-6 py-4 rounded-xl border-2 border-green-300 bg-green-50 text-lg font-semibold text-green-700 shadow-sm hover:bg-green-100 hover:border-green-400 transition-all duration-200 flex items-center justify-center gap-2 dark:border-emerald-600 dark:bg-emerald-900/30 dark:text-emerald-300 dark:hover:bg-emerald-800"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
            </svg>
            Back to Watchlist
          </Link>
        </div>

        {/* ============================ */}
        {/* News Controls                */}
        {/* ============================ */}
        <div className="flex items-center justify-between mb-6">
          <div>
            {total > 0 && (
              <p className="text-sm text-gray-500 dark:text-slate-400">
                Showing {offset + 1}-{Math.min(offset + articles.length, total)} of {total} article{total !== 1 ? 's' : ''}
              </p>
            )}
          </div>

          <div className="flex items-center gap-3">
            {/* Ticker selector dropdown */}
            <select
              value={ticker}
              onChange={(e) => handleTickerSelect(e.target.value)}
              className="px-3 py-2 rounded-lg border border-gray-300 bg-white text-sm font-medium shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-400 dark:border-slate-600 dark:bg-slate-800 dark:text-gray-100 dark:focus:ring-indigo-500"
            >
              {allTickers.map(t => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
          </div>
        </div>

        {/* Loading State */}
        {loading && !articles.length && (
          <div className="flex flex-col items-center justify-center py-20">
            <div className="w-10 h-10 border-4 border-blue-200 border-t-blue-600 rounded-full animate-spin mb-4 dark:border-indigo-400 dark:border-t-indigo-600"></div>
            <p className="text-gray-500 dark:text-slate-400 text-sm">Loading articles...</p>
          </div>
        )}

        {/* Error State */}
        {!loading && error && (
          <div className="flex flex-col items-center justify-center py-20">
            <div className="w-16 h-16 rounded-full bg-red-100 dark:bg-red-900/30 flex items-center justify-center mb-4">
              <svg className="w-8 h-8 text-red-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
            <p className="text-red-600 dark:text-red-400 text-sm mb-3">{error}</p>
            <button
              onClick={() => refetch()}
              className="px-4 py-2 rounded-lg bg-blue-600 text-white text-sm hover:bg-blue-700 dark:bg-indigo-600 dark:hover:bg-indigo-700 transition-colors"
            >
              Retry
            </button>
          </div>
        )}

        {/* Empty State */}
        {!loading && !error && articles.length === 0 && (
          <div className="flex flex-col items-center justify-center py-20">
            <div className="w-16 h-16 rounded-full bg-gray-100 dark:bg-slate-700 flex items-center justify-center mb-4">
              <svg className="w-8 h-8 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M19 20H5a2 2 0 01-2-2V6a2 2 0 012-2h10a2 2 0 012 2v1m2 11a2 2 0 01-2-2V7m2 10a2 2 0 002-2V9a2 2 0 00-2-2h-4" />
              </svg>
            </div>
            <p className="text-gray-500 dark:text-slate-400 text-sm mb-3">No news articles for {ticker}.</p>
            <p className="text-xs text-gray-400 dark:text-slate-500">News auto-refreshes every 15 minutes during market hours (8 AM – 6 PM EST).</p>
          </div>
        )}

        {/* News Grid */}
        {!loading && articles.length > 0 && (
          <>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {articles.map((article, index) => {
                const globalIndex = offset + index + 1;
                return (
                  <NewsCard
                    key={article.id}
                    article={article}
                    articleNumber={globalIndex}
                    totalArticles={total}
                  />
                );
              })}
            </div>

            {/* Pagination */}
            {totalPages > 1 && (
              <div className="flex flex-wrap items-center justify-center gap-2 mt-8">
                <button
                  onClick={goToPrevPage}
                  disabled={page <= 1}
                  className={`px-3 py-2 rounded-lg text-sm font-medium border transition-colors ${
                    page <= 1
                      ? 'bg-gray-100 text-gray-400 cursor-not-allowed dark:bg-slate-700 dark:text-slate-500 dark:border-slate-600'
                      : 'bg-white text-gray-700 hover:bg-blue-50 hover:border-blue-300 border-gray-300 dark:bg-slate-800 dark:text-gray-100 dark:hover:bg-indigo-900 dark:hover:border-indigo-500 dark:border-slate-600'
                  }`}
                >
                  ← Prev
                </button>

                {(() => {
                  const pages: number[] = [];
                  const start = Math.max(1, page - 5);
                  const end = Math.min(totalPages, page + 5);
                  for (let i = start; i <= end; i++) pages.push(i);
                  return pages.map((p) => (
                    <button
                      key={p}
                      onClick={() => setPage(p)}
                      className={`w-10 h-10 rounded-lg text-sm font-medium transition-colors ${
                        p === page
                          ? 'bg-blue-600 text-white dark:bg-indigo-600'
                          : 'bg-white border border-gray-300 text-gray-700 hover:bg-blue-50 dark:bg-slate-800 dark:border-slate-600 dark:text-gray-100 dark:hover:bg-indigo-900'
                      }`}
                    >
                      {p}
                    </button>
                  ));
                })()}

                <button
                  onClick={goToNextPage}
                  disabled={page >= totalPages}
                  className={`px-3 py-2 rounded-lg text-sm font-medium border transition-colors ${
                    page >= totalPages
                      ? 'bg-gray-100 text-gray-400 cursor-not-allowed dark:bg-slate-700 dark:text-slate-500 dark:border-slate-600'
                      : 'bg-white text-gray-700 hover:bg-blue-50 hover:border-blue-300 border-gray-300 dark:bg-slate-800 dark:text-gray-100 dark:hover:bg-indigo-900 dark:hover:border-indigo-500 dark:border-slate-600'
                  }`}
                >
                  Next →
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
