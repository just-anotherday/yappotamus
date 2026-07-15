// ==============================================================================
// PAGE: /news - All news articles feed from PostgreSQL (Light + Dark Theme)
// ==============================================================================

'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { useNews } from '@/hooks/useNews';
import { fetchNewsTickers } from '@/lib/api';
import { NewsCard } from '@/components/news/NewsCard';

export default function AllNewsPage() {
  const [tickerFilter, setTickerFilter] = useState<string>('');
  const [startDate, setStartDate] = useState<string>('');
  const [endDate, setEndDate] = useState<string>('');
  const [allTickers, setAllTickers] = useState<string[]>([]);

  useEffect(() => {
    let cancelled = false;
    fetchNewsTickers()
      .then(tickers => { if (!cancelled) setAllTickers(tickers); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, []);

  const {
    articles,
    loading,
    error,
    refetch,
    setPage,
    goToNextPage,
    goToPrevPage,
    resetToFirstPage,
    goToFirstPage,
    goToLastPage,
    total,
    totalPages,
    page,
    offset,
  } = useNews(
    tickerFilter || undefined,
    50,
    startDate || null,
    endDate || null,
  );

  const handleTickerChange = (value: string) => {
    setTickerFilter(value);
    resetToFirstPage();
  };

  const handleDateChange = () => {
    resetToFirstPage();
  };

  return (
    <div className="max-w-6xl mx-auto px-4 py-12">
      {/* Breadcrumb */}
      <nav className="flex items-center gap-2 text-sm text-gray-500 dark:text-slate-400 mb-4">
        <Link href="/" className="hover:text-blue-600 dark:hover:text-indigo-400 transition-colors">
          Dashboard
        </Link>
        <span>›</span>
        <span className="font-medium text-gray-900 dark:text-gray-100">All News</span>
      </nav>

      {/* Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900 dark:text-white">All News</h1>
        {total > 0 && (
          <p className="text-sm text-gray-500 dark:text-slate-400 mt-1">
            Showing {offset + 1}-{Math.min(offset + articles.length, total)} of {total} article{total !== 1 ? 's' : ''}
          </p>
        )}
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3 mb-8">
        <label htmlFor="ticker-filter" className="text-sm font-medium text-gray-700 dark:text-slate-300">
          Ticker:
        </label>
        <select
          id="ticker-filter"
          value={tickerFilter}
          onChange={(e) => handleTickerChange(e.target.value)}
          className="px-3 py-2 rounded-lg border border-gray-300 bg-white text-gray-900 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-400 dark:border-slate-600 dark:bg-slate-800 dark:text-gray-100 dark:focus:ring-indigo-500"
        >
          <option value="">All Tickers</option>
          {allTickers.map(t => (
            <option key={t} value={t}>{t}</option>
          ))}
        </select>

        <label htmlFor="start-date" className="text-sm font-medium text-gray-700 dark:text-slate-300">
          From:
        </label>
        <input
          id="start-date"
          type="date"
          value={startDate}
          onChange={(e) => { setStartDate(e.target.value); handleDateChange(); }}
          className="px-3 py-2 rounded-lg border border-gray-300 bg-white text-gray-900 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-400 dark:border-slate-600 dark:bg-slate-800 dark:text-gray-100 dark:focus:ring-indigo-500"
        />

        <label htmlFor="end-date" className="text-sm font-medium text-gray-700 dark:text-slate-300">
          To:
        </label>
        <input
          id="end-date"
          type="date"
          value={endDate}
          onChange={(e) => { setEndDate(e.target.value); handleDateChange(); }}
          className="px-3 py-2 rounded-lg border border-gray-300 bg-white text-gray-900 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-400 dark:border-slate-600 dark:bg-slate-800 dark:text-gray-100 dark:focus:ring-indigo-500"
        />

        {tickerFilter && (
          <Link
            href={`/news/${tickerFilter}`}
            className="px-3 py-2 rounded-lg border border-gray-300 text-sm font-medium text-blue-600 hover:bg-gray-100 transition-colors dark:border-slate-600 dark:text-indigo-400 dark:hover:bg-slate-700"
          >
            View {tickerFilter} Detail →
          </Link>
        )}
      </div>

      {/* Loading State */}
      {loading && (
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
            <svg className="w-8 h-8 text-gray-400 dark:text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M19 20H5a2 2 0 01-2-2V6a2 2 0 012-2h10a2 2 0 012 2v1m2 11a2 2 0 01-2-2V7m2 10a2 2 0 002-2V9a2 2 0 00-2-2h-4" />
            </svg>
          </div>
          <p className="text-gray-500 dark:text-slate-400 text-sm">No news articles found.</p>
          <p className="text-xs text-gray-400 dark:text-slate-500 mt-1">News auto-refreshes every 15 minutes during market hours (8 AM – 6 PM EST).</p>
        </div>
      )}

      {/* News Grid */}
      {!loading && articles.length > 0 && (
        <>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
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
                onClick={goToFirstPage}
                disabled={page <= 1}
                className={`px-3 py-2 rounded-lg text-sm font-medium border transition-colors ${
                  page <= 1
                    ? 'bg-gray-100 text-gray-400 cursor-not-allowed dark:bg-slate-700 dark:text-slate-500 dark:border-slate-600'
                    : 'bg-white text-gray-700 hover:bg-blue-50 hover:border-blue-300 border-gray-300 dark:bg-slate-800 dark:text-gray-100 dark:hover:bg-indigo-900 dark:hover:border-indigo-500 dark:border-slate-600'
                }`}
              >
                &laquo; First
              </button>
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
              <button
                onClick={goToLastPage}
                disabled={page >= totalPages}
                className={`px-3 py-2 rounded-lg text-sm font-medium border transition-colors ${
                  page >= totalPages
                    ? 'bg-gray-100 text-gray-400 cursor-not-allowed dark:bg-slate-700 dark:text-slate-500 dark:border-slate-600'
                    : 'bg-white text-gray-700 hover:bg-blue-50 hover:border-blue-300 border-gray-300 dark:bg-slate-800 dark:text-gray-100 dark:hover:bg-indigo-900 dark:hover:border-indigo-500 dark:border-slate-600'
                }`}
              >
                Last &raquo;
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
