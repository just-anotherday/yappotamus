'use client';

import { memo, useEffect, useState, type SetStateAction } from 'react';
import Link from 'next/link';
import { useNews } from '@/hooks/useNews';
import { getOffset, computeTotalPages, pageSizeForPage } from '@/lib/pagination';
import ArticleCard from '@/components/news/ArticleCard';
import type { NewsArticle } from '@/types/stock';
import AppIcon from '@/components/ui/AppIcon';
import NewsSync from '@/components/NewsSync';
import { NEWS_SYNC_COMPLETED_EVENT } from '@/lib/newsSync';

const NEWS_FETCH_LIMIT = 50;
const FIRST_PAGE_SIZE = 5;
const SUBSEQUENT_PAGE_SIZE = 9;

export default memo(function HomeNews() {
  const [page, setPage] = useState(1);
  const [fetchLimit, setFetchLimit] = useState(FIRST_PAGE_SIZE);
  useEffect(() => {
    const resetPage = () => setPage(1);
    window.addEventListener(NEWS_SYNC_COMPLETED_EVENT, resetPage);
    return () => window.removeEventListener(NEWS_SYNC_COMPLETED_EVENT, resetPage);
  }, []);
  const { articles, total, loading: newsLoading, error: newsError, refetch } = useNews(undefined, fetchLimit);
  const articleCount = Math.min(total, NEWS_FETCH_LIMIT);
  const totalPages = computeTotalPages(articleCount, FIRST_PAGE_SIZE, SUBSEQUENT_PAGE_SIZE);
  const startIdx = getOffset(page, FIRST_PAGE_SIZE, SUBSEQUENT_PAGE_SIZE);
  const pageSize = pageSizeForPage(page, FIRST_PAGE_SIZE, SUBSEQUENT_PAGE_SIZE);
  const pageArticles = articles.slice(startIdx, startIdx + pageSize);
  const changePage = (next: SetStateAction<number>) => {
    const target = typeof next === 'function' ? next(page) : next;
    if (target > 1) setFetchLimit(NEWS_FETCH_LIMIT);
    setPage(target);
  };
  return (
      <section className="surface news-section" aria-labelledby="latest-news-heading">
        <div className="news-section-header">
          <div>
            <h2 id="latest-news-heading">Latest market news</h2>
            <p>Stories from across your market.</p>
          </div>
          <div className="news-section-actions"><Link href="/news" className="text-link">All news <AppIcon name="arrow" width={15} height={15} /></Link><NewsSync /></div>
        </div>

        {newsLoading ? (
          <div className="flex items-center gap-3 text-muted dark:text-slate-400">
            <div className="w-6 h-6 border-2 border-info-border dark:border-info-border border-t-blue-600 dark:border-t-indigo-600 rounded-full animate-spin"></div>
            <span className="text-sm">Loading latest news...</span>
          </div>
        ) : newsError ? (
          <div className="rounded-xl border border-negative-border bg-negative-soft dark:border-negative-border/70 dark:bg-negative-soft/30 p-5 text-center">
            <p className="text-sm font-medium text-negative dark:text-negative">Unable to load market news.</p>
            <p className="mt-1 text-xs text-negative dark:text-negative">{newsError}</p>
            <button
              onClick={refetch}
              className="mt-3 px-4 py-2 text-sm font-medium rounded-lg border border-negative-border bg-card text-negative hover:bg-negative-soft dark:border-negative-border dark:bg-slate-800 dark:text-negative dark:hover:bg-slate-700 transition-colors"
            >
              Try Again
            </button>
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
              <div className="news-pagination">
                <button
                  onClick={() => changePage(1)}
                  disabled={page === 1}
                  className="px-3 py-1.5 text-sm rounded-lg border border-divider dark:border-slate-600 bg-card dark:bg-slate-800 text-secondary dark:text-gray-200 hover:bg-surface-muted dark:hover:bg-slate-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                >
                  &laquo; First
                </button>
                <button
                  onClick={() => changePage(p => Math.max(1, p - 1))}
                  disabled={page === 1}
                  className="px-3 py-1.5 text-sm rounded-lg border border-divider dark:border-slate-600 bg-card dark:bg-slate-800 text-secondary dark:text-gray-200 hover:bg-surface-muted dark:hover:bg-slate-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                >
                  &lsaquo; Prev
                </button>
                {Array.from({ length: totalPages }, (_, i) => i + 1).map((p) => (
                  <button
                    key={p}
                    onClick={() => changePage(p)}
                    className={`px-3 py-1.5 text-sm rounded-lg border transition-colors ${
                      p === page
                        ? 'bg-action dark:bg-action text-white border-info-border dark:border-info-border'
                        : 'border-divider dark:border-slate-600 bg-card dark:bg-slate-800 text-secondary dark:text-gray-200 hover:bg-surface-muted dark:hover:bg-slate-700'
                    }`}
                  >
                    {p}
                  </button>
                ))}
                <button
                  onClick={() => changePage(p => Math.min(totalPages, p + 1))}
                  disabled={page === totalPages}
                  className="px-3 py-1.5 text-sm rounded-lg border border-divider dark:border-slate-600 bg-card dark:bg-slate-800 text-secondary dark:text-gray-200 hover:bg-surface-muted dark:hover:bg-slate-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                >
                  Next &rsaquo;
                </button>
                <button
                  onClick={() => changePage(totalPages)}
                  disabled={page === totalPages}
                  className="px-3 py-1.5 text-sm rounded-lg border border-divider dark:border-slate-600 bg-card dark:bg-slate-800 text-secondary dark:text-gray-200 hover:bg-surface-muted dark:hover:bg-slate-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                >
                  Last &raquo;
                </button>

                {/* Article count + View all articles link */}
                <span className="ml-4 text-xs text-muted dark:text-slate-400">
                  {startIdx + 1}-{Math.min(startIdx + pageSize, articleCount)} of {articleCount} articles
                </span>
                <Link
                  href="/news"
                  className="text-accent dark:text-accent hover:text-info dark:hover:text-accent font-semibold text-sm flex items-center gap-1 hover:underline transition-colors"
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
          <div className="text-center py-8 text-muted dark:text-slate-400">
            <p className="text-sm">No news articles yet. News updates every 15 minutes from 4 AM to 8 PM ET on weekdays, with hourly off-hours coverage.</p>
            <button
              onClick={refetch}
              className="mt-3 px-4 py-2 text-sm font-medium rounded-lg border bg-card dark:bg-slate-800 hover:bg-surface-muted dark:hover:bg-slate-700 transition-colors"
            >
              Refresh
            </button>
          </div>
        )}
      </section>

  );
});
