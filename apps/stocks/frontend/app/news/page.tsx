// ==============================================================================
// PAGE: /news - All news articles feed from PostgreSQL (Light + Dark Theme)
// ==============================================================================

'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { useNews } from '@/hooks/useNews';
import { fetchNewsTickers } from '@/lib/api';
import { NewsCard } from '@/components/news/NewsCard';
import NewsSync from '@/components/NewsSync';
import { NEWS_SYNC_COMPLETED_EVENT } from '@/lib/newsSync';

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
    const refreshTickers = () => {
      fetchNewsTickers().then(tickers => { if (!cancelled) setAllTickers(tickers); }).catch(() => {});
    };
    window.addEventListener(NEWS_SYNC_COMPLETED_EVENT, refreshTickers);
    return () => {
      cancelled = true;
      window.removeEventListener(NEWS_SYNC_COMPLETED_EVENT, refreshTickers);
    };
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
    <div className="workspace-page">
      {/* Breadcrumb */}
      <nav className="flex items-center gap-2 text-sm text-muted dark:text-slate-400 mb-4">
        <Link href="/" className="hover:text-accent dark:hover:text-accent transition-colors">
          Overview
        </Link>
        <span>›</span>
        <span className="font-medium text-primary dark:text-gray-100">All News</span>
      </nav>

      {/* Header */}
      <div className="page-heading">
        <p className="eyebrow"><span className="accent-line" /> Market news</p>
        <h1>The stories behind the numbers.</h1>
        <p>Explore the latest coverage, or focus on the companies you follow.</p>
        {total > 0 && (
          <p className="text-sm text-muted dark:text-slate-400 mt-1">
            Showing {offset + 1}-{Math.min(offset + articles.length, total)} of {total} article{total !== 1 ? 's' : ''}
          </p>
        )}
      </div>

      <div className="mb-6"><NewsSync /></div>

      {/* Filters */}
      <div className="surface news-filters">
        <div className="news-filter-field">
        <label htmlFor="ticker-filter" className="text-sm font-medium text-secondary dark:text-slate-300">
          Ticker:
        </label>
        <select
          id="ticker-filter"
          value={tickerFilter}
          onChange={(e) => handleTickerChange(e.target.value)}
          className="px-3 py-2 rounded-lg border border-divider bg-card text-primary text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-accent dark:border-slate-600 dark:bg-slate-800 dark:text-gray-100 dark:focus:ring-accent"
        >
          <option value="">All Tickers</option>
          {allTickers.map(t => (
            <option key={t} value={t}>{t}</option>
          ))}
        </select>
        </div>

        <div className="news-filter-field">
        <label htmlFor="start-date" className="text-sm font-medium text-secondary dark:text-slate-300">
          From:
        </label>
        <input
          id="start-date"
          type="date"
          value={startDate}
          onChange={(e) => { setStartDate(e.target.value); handleDateChange(); }}
          className="px-3 py-2 rounded-lg border border-divider bg-card text-primary text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-accent dark:border-slate-600 dark:bg-slate-800 dark:text-gray-100 dark:focus:ring-accent"
        />
        </div>

        <div className="news-filter-field">
        <label htmlFor="end-date" className="text-sm font-medium text-secondary dark:text-slate-300">
          To:
        </label>
        <input
          id="end-date"
          type="date"
          value={endDate}
          onChange={(e) => { setEndDate(e.target.value); handleDateChange(); }}
          className="px-3 py-2 rounded-lg border border-divider bg-card text-primary text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-accent dark:border-slate-600 dark:bg-slate-800 dark:text-gray-100 dark:focus:ring-accent"
        />
        </div>

        {tickerFilter && (
          <Link
            href={`/news/${tickerFilter}`}
            className="px-3 py-2 rounded-lg border border-divider text-sm font-medium text-accent hover:bg-surface-muted transition-colors dark:border-slate-600 dark:text-accent dark:hover:bg-slate-700"
          >
            View {tickerFilter} Detail →
          </Link>
        )}
      </div>

      {/* Loading State */}
      {loading && (
        <div className="flex flex-col items-center justify-center py-20">
          <div className="w-10 h-10 border-4 border-info-border border-t-blue-600 rounded-full animate-spin mb-4 dark:border-info-border dark:border-t-indigo-600"></div>
          <p className="text-muted dark:text-slate-400 text-sm">Loading articles...</p>
        </div>
      )}

      {/* Error State */}
      {!loading && error && (
        <div className="flex flex-col items-center justify-center py-20">
          <div className="w-16 h-16 rounded-full bg-negative-soft dark:bg-negative-soft/30 flex items-center justify-center mb-4">
            <svg className="w-8 h-8 text-negative" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
          <p className="text-negative dark:text-negative text-sm mb-3">{error}</p>
          <button
            onClick={() => refetch()}
            className="px-4 py-2 rounded-lg bg-action text-white text-sm hover:bg-action-hover dark:bg-action dark:hover:bg-action-hover transition-colors"
          >
            Retry
          </button>
        </div>
      )}

      {/* Empty State */}
      {!loading && !error && articles.length === 0 && (
        <div className="flex flex-col items-center justify-center py-20">
          <div className="w-16 h-16 rounded-full bg-surface-muted dark:bg-slate-700 flex items-center justify-center mb-4">
            <svg className="w-8 h-8 text-muted dark:text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M19 20H5a2 2 0 01-2-2V6a2 2 0 012-2h10a2 2 0 012 2v1m2 11a2 2 0 01-2-2V7m2 10a2 2 0 002-2V9a2 2 0 00-2-2h-4" />
            </svg>
          </div>
          <p className="text-muted dark:text-slate-400 text-sm">No news articles found.</p>
          <p className="text-xs text-muted dark:text-slate-500 mt-1">News updates every 15 minutes from 4 AM to 8 PM ET on weekdays, with hourly off-hours coverage.</p>
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
                    ? 'bg-surface-muted text-muted cursor-not-allowed dark:bg-slate-700 dark:text-slate-500 dark:border-slate-600'
                    : 'bg-card text-secondary hover:bg-info-soft hover:border-info-border border-divider dark:bg-slate-800 dark:text-gray-100 dark:hover:bg-info-soft dark:hover:border-info-border dark:border-slate-600'
                }`}
              >
                &laquo; First
              </button>
              <button
                onClick={goToPrevPage}
                disabled={page <= 1}
                className={`px-3 py-2 rounded-lg text-sm font-medium border transition-colors ${
                  page <= 1
                    ? 'bg-surface-muted text-muted cursor-not-allowed dark:bg-slate-700 dark:text-slate-500 dark:border-slate-600'
                    : 'bg-card text-secondary hover:bg-info-soft hover:border-info-border border-divider dark:bg-slate-800 dark:text-gray-100 dark:hover:bg-info-soft dark:hover:border-info-border dark:border-slate-600'
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
                        ? 'bg-action text-white dark:bg-action'
                        : 'bg-card border border-divider text-secondary hover:bg-info-soft dark:bg-slate-800 dark:border-slate-600 dark:text-gray-100 dark:hover:bg-info-soft'
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
                    ? 'bg-surface-muted text-muted cursor-not-allowed dark:bg-slate-700 dark:text-slate-500 dark:border-slate-600'
                    : 'bg-card text-secondary hover:bg-info-soft hover:border-info-border border-divider dark:bg-slate-800 dark:text-gray-100 dark:hover:bg-info-soft dark:hover:border-info-border dark:border-slate-600'
                }`}
              >
                Next →
              </button>
              <button
                onClick={goToLastPage}
                disabled={page >= totalPages}
                className={`px-3 py-2 rounded-lg text-sm font-medium border transition-colors ${
                  page >= totalPages
                    ? 'bg-surface-muted text-muted cursor-not-allowed dark:bg-slate-700 dark:text-slate-500 dark:border-slate-600'
                    : 'bg-card text-secondary hover:bg-info-soft hover:border-info-border border-divider dark:bg-slate-800 dark:text-gray-100 dark:hover:bg-info-soft dark:hover:border-info-border dark:border-slate-600'
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
