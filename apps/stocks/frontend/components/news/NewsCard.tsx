"use client";

import Image from 'next/image';
import Link from "next/link";
import { articleLink } from '@/lib/articleEvidence';
import { timeAgo, formatDate } from "@/lib/formatters";
import type { NewsArticle } from "@/types/stock";

// Fallback thumbnail image
const FALLBACK_THUMBNAIL = "/news_image.png";

interface NewsCardProps {
  article: NewsArticle;
  articleNumber: number;
  totalArticles: number;
  selected?: boolean;
  onToggle?: (id: number) => void;
}

export function NewsCard({ article, articleNumber, totalArticles, selected, onToggle }: NewsCardProps) {
  const articleUrl = articleLink(article.article_url)?.href;
  const displayDate = article.pub_date || article.imported_at;

  return (
    <article className="bg-card dark:bg-slate-800 rounded-xl shadow-sm border border-divider dark:border-slate-600 overflow-hidden hover:shadow-md hover:border-info-border dark:hover:border-info-border transition-all duration-200 flex flex-col">
      {/* Thumbnail area with date overlay */}
      <div className="bg-gray-200 dark:bg-slate-700 w-full h-48 relative overflow-hidden">
        <a
          href={articleUrl || "#"}
          target="_blank"
          rel="noopener noreferrer"
          className="block h-full hover:opacity-90 transition-opacity"
        >
          <Image unoptimized width={640} height={360}
            src={article.thumbnail_url || FALLBACK_THUMBNAIL}
            alt={article.title || "News thumbnail"}
            className="w-full h-full object-cover"
            onError={(e) => { (e.target as HTMLImageElement).src = FALLBACK_THUMBNAIL; }}
          />
        </a>
        {/* Date overlay badge on bottom-left */}
        {displayDate && (
          <span className="absolute bottom-2 left-2 bg-black/65 text-white text-xs px-2 py-1 rounded-md font-medium">
            {formatDate(displayDate)}
          </span>
        )}
      </div>

      <div className="p-5 flex flex-col flex-1">
        {/* Selection checkbox row */}
        {onToggle && (
          <div className="flex items-center gap-2 mb-3">
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={selected || false}
                onChange={() => onToggle(article.id)}
                className="w-4 h-4 rounded border-divider text-accent focus:ring-accent cursor-pointer"
              />
              <span className="text-xs font-medium text-muted dark:text-slate-400">
                {selected ? 'Selected for analysis' : 'Select for analysis'}
              </span>
            </label>
          </div>
        )}
        {/* Ticker badge + article counter row */}
        <div className="flex items-center justify-between mb-3">
          {article.ticker ? (
            <Link
              href={`/news/${article.ticker}`}
              className="px-2.5 py-1 rounded-full bg-info-soft dark:bg-info-soft/40 text-info dark:text-accent text-xs font-semibold hover:bg-info-soft dark:hover:bg-action-hover transition-colors"
            >
              {article.ticker}
            </Link>
          ) : (
            <span />
          )}
          <span className="text-xs text-muted dark:text-slate-500 font-medium">
            {articleNumber} of {totalArticles}
          </span>
        </div>

        {/* Article title */}
        {articleUrl ? (
          <a
            href={articleUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="text-base font-semibold text-primary dark:text-gray-100 mb-2 leading-snug line-clamp-3 hover:text-accent dark:hover:text-accent transition-colors inline-block"
          >
            {article.title || "Untitled"}
          </a>
        ) : (
          <h3 className="text-base font-semibold text-primary dark:text-gray-100 mb-2 leading-snug line-clamp-3">
            {article.title || "Untitled"}
          </h3>
        )}

        {/* Article summary */}
        <p className="text-sm text-secondary dark:text-slate-400 mb-4 line-clamp-4 flex-1">
          {article.summary || "No summary available."}
        </p>

        {/* Publisher + Timestamp metadata row */}
        <div className="space-y-2 mb-3 pt-3 border-t border-divider dark:border-slate-600">
          {/* Timestamp + Publisher line */}
          <div className="flex items-center justify-between text-xs">
            <span title={formatDate(displayDate)} className="text-muted dark:text-slate-500 flex items-center gap-1.5">
              <svg xmlns="http://www.w3.org/2000/svg" className="h-3.5 w-3.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              {timeAgo(displayDate)}
              {!article.pub_date && article.imported_at && (
                <span className="text-gray-300 dark:text-slate-600 ml-1">(ingested)</span>
              )}
            </span>
            {/* Publisher badge — always show provider_name on the right */}
            {article.provider_name && article.provider_name.trim() !== '' && (
              <span className="text-muted dark:text-slate-500 truncate max-w-[35%] text-right font-medium">
                {article.provider_name}
              </span>
            )}
          </div>
        </div>

        {/* Read Article link */}
        {articleUrl && (
          <a
            href={articleUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="text-accent dark:text-accent text-sm font-medium hover:text-info dark:hover:text-accent inline-flex items-center gap-1 mt-auto transition-colors"
          >
            Read Article
            <svg xmlns="http://www.w3.org/2000/svg" className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M14 5l7 7m0 0l-7 7m7-7H3" />
            </svg>
          </a>
        )}
      </div>
    </article>
  );
}
