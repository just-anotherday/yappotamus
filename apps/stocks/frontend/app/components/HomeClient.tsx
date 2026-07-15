'use client';

import { useState } from 'react';
import Link from 'next/link';
import StockCard from '@/components/stock/StockCard';
import WatchlistTable from '@/components/watchlist/WatchlistTable';
import ErrorBanner from '@/components/ui/ErrorBanner';
import SuccessBanner from '@/components/ui/SuccessBanner';
import { useLivePrices } from '@/hooks/useLivePrices';
import { useWatchlist } from '@/hooks/useWatchlist';
import { useNews } from '@/hooks/useNews';
import { fetchStock } from '@/lib/api';
import { getOffset, computeTotalPages, pageSizeForPage } from '@/lib/pagination';
import ArticleCard from '@/components/news/ArticleCard';
import type { StockData, NewsArticle } from '@/types/stock';

const NEWS_FETCH_LIMIT = 50;
const FIRST_PAGE_SIZE = 5;
const SUBSEQUENT_PAGE_SIZE = 9;

export default function HomeClient() {
  const [ticker, setTicker] = useState('');
  const [stockData, setStockData] = useState<StockData | null>(null);
  const [loading, setLoading] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [page, setPage] = useState(1);

  const { livePrices, priceFlash } = useLivePrices();
  const {
    watchlist,
    watchlistLoading,
    error,
    successMessage,
    addTicker,
    removeTicker,
    watchlistOrder,
    reorderWatchlist,
    maxWatchlistSize,
  } = useWatchlist();

  const { articles, loading: newsLoading, refetch } = useNews(undefined, NEWS_FETCH_LIMIT);

  const totalPages = computeTotalPages(articles.length, FIRST_PAGE_SIZE, SUBSEQUENT_PAGE_SIZE);
  const startIdx = getOffset(page, FIRST_PAGE_SIZE, SUBSEQUENT_PAGE_SIZE);
  const pageSize = pageSizeForPage(page, FIRST_PAGE_SIZE, SUBSEQUENT_PAGE_SIZE);
  const pageArticles = articles.slice(startIdx, startIdx + pageSize);

  const handleChangeTicker = (value: string) => {
    setTicker(value);
    if (!value.trim() && stockData) {
      setStockData(null);
    }
  };

  const handleSearch = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!ticker.trim()) return;
    setLoading(true);
    setStockData(null);
    try {
      const data = await fetchStock(ticker);
      setStockData(data);
      setSearchError(null);
    } catch (err) {
      setSearchError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-7xl mx-auto px-4 w-full mt-8">

      {/* ============================================================ */}
      {/* 1. LATEST MARKET NEWS (first section)                        */}
      {/* ============================================================ */}
      <div className="mb-10 bg-gradient-to-br from-orange-50 to-amber-50 dark:from-slate-800 dark:to-slate-900 rounded-2xl p-6 border-l-4 border-orange-500 shadow-sm">
        <div className="flex items-center gap-3 mb-5">
          <div className="flex items-center justify-center w-10 h-10 rounded-xl bg-gradient-to-br from-orange-500 to-amber-500 shadow-md">
            <svg className="w-6 h-6 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M19 20H5a2 2 0 01-2-2V6a2 2 0 012-2h10a2 2 0 012 2v1m2 13a2 2 0 01-2-2V7m-6 14l4-4m0 0l4 4m-4-4v12" />
            </svg>
          </div>
          <h2 className="text-2xl font-extrabold text-gray-900 dark:text-white">
            Latest Market News
          </h2>
        </div>

        {newsLoading ? (
          <div className="flex items-center gap-3 text-gray-500 dark:text-slate-400">
            <div className="w-6 h-6 border-2 border-blue-400 dark:border-indigo-400 border-t-blue-600 dark:border-t-indigo-600 rounded-full animate-spin"></div>
            <span className="text-sm">Loading latest news...</span>
          </div>
        ) : pageArticles.length > 0 ? (
          <>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5 mb-6">
              {pageArticles.map((article: NewsArticle) => (
                <ArticleCard key={article.id} article={article} />
              ))}
            </div>

            {/* Pagination with First/Last buttons */}
            {totalPages > 1 && (
              <div className="flex items-center justify-center gap-2">
                <button
                  onClick={() => setPage(1)}
                  disabled={page === 1}
                  className="px-3 py-1.5 text-sm rounded-lg border border-gray-300 dark:border-slate-600 bg-white dark:bg-slate-800 text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-slate-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                >
                  &laquo; First
                </button>
                <button
                  onClick={() => setPage(p => Math.max(1, p - 1))}
                  disabled={page === 1}
                  className="px-3 py-1.5 text-sm rounded-lg border border-gray-300 dark:border-slate-600 bg-white dark:bg-slate-800 text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-slate-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                >
                  &lsaquo; Prev
                </button>
                {Array.from({ length: totalPages }, (_, i) => i + 1).map((p) => (
                  <button
                    key={p}
                    onClick={() => setPage(p)}
                    className={`px-3 py-1.5 text-sm rounded-lg border transition-colors ${
                      p === page
                        ? 'bg-blue-600 dark:bg-indigo-600 text-white border-blue-600 dark:border-indigo-600'
                        : 'border-gray-300 dark:border-slate-600 bg-white dark:bg-slate-800 text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-slate-700'
                    }`}
                  >
                    {p}
                  </button>
                ))}
                <button
                  onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                  disabled={page === totalPages}
                  className="px-3 py-1.5 text-sm rounded-lg border border-gray-300 dark:border-slate-600 bg-white dark:bg-slate-800 text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-slate-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                >
                  Next &rsaquo;
                </button>
                <button
                  onClick={() => setPage(totalPages)}
                  disabled={page === totalPages}
                  className="px-3 py-1.5 text-sm rounded-lg border border-gray-300 dark:border-slate-600 bg-white dark:bg-slate-800 text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-slate-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                >
                  Last &raquo;
                </button>

                {/* Article count + View all articles link */}
                <span className="ml-4 text-xs text-gray-500 dark:text-slate-400">
                  {startIdx + 1}-{Math.min(startIdx + pageSize, articles.length)} of {articles.length} articles
                </span>
                <Link
                  href="/news"
                  className="text-blue-600 dark:text-indigo-400 hover:text-blue-700 dark:hover:text-indigo-300 font-semibold text-sm flex items-center gap-1 hover:underline transition-colors"
                >
                  View all articles
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
                  </svg>
                </Link>
              </div>
            )}
          </>
        ) : (
          <div className="text-center py-8 text-gray-500 dark:text-slate-400">
            <p className="text-sm">No news articles yet. Auto-ingestion runs every 15 minutes during market hours (8 AM – 6 PM EST).</p>
            <button
              onClick={refetch}
              className="mt-3 px-4 py-2 text-sm font-medium rounded-lg border bg-white dark:bg-slate-800 hover:bg-gray-50 dark:hover:bg-slate-700 transition-colors"
            >
              Refresh
            </button>
          </div>
        )}
      </div>

      {/* ============================================================ */}
      {/* 2. TICKER SEARCH (second section)                            */}
      {/* ============================================================ */}
      <form onSubmit={handleSearch} className="flex gap-2 mb-5">
        <input
          type="text"
          value={ticker}
          onChange={(e) => handleChangeTicker(e.target.value)}
          placeholder="TICKER"
          className="w-[10ch] px-2 py-1.5 border border-gray-300 dark:border-slate-600 bg-white dark:bg-slate-800 text-gray-900 dark:text-white rounded-md text-sm font-mono placeholder-gray-400 dark:placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-indigo-500 focus:border-transparent shadow-sm"
        />
        <button
          type="submit"
          disabled={loading}
          className="px-4 py-1.5 bg-blue-600 dark:bg-indigo-600 text-white text-sm font-medium rounded-md hover:bg-blue-700 dark:hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors shadow-sm"
        >
          {loading ? '...' : 'Search'}
        </button>
      </form>

      {/* Search error message */}
      {searchError && <ErrorBanner message={searchError} />}

      {/* Watchlist error message */}
      {error && <ErrorBanner message={error} />}

      {/* Stock Detail Card */}
      {stockData && (
        <StockCard
          data={stockData}
          onAddToWatchlist={addTicker}
          isInWatchlist={watchlist.some(item => item.ticker === stockData.ticker)}
          isWatchlistFull={watchlist.length >= maxWatchlistSize}
        />
      )}

      {/* Success message */}
      {successMessage && <SuccessBanner message={successMessage} />}

      {/* ============================================================ */}
      {/* 3. WATCHLIST TABLE (last section)                            */}
      {/* ============================================================ */}
      <div className="w-full overflow-visible pb-16">
        <WatchlistTable
          watchlist={watchlist}
          livePrices={livePrices}
          priceFlash={priceFlash}
          loading={watchlistLoading}
          onRemove={removeTicker}
          watchlistOrder={watchlistOrder}
          onReorder={reorderWatchlist}
        />
      </div>
    </div>
  );
}
