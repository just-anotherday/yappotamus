import { articleLink } from '@/lib/articleEvidence';
import { formatApiTimestamp } from '@/lib/formatters';
import type { ArticleReference } from '@/types/stock';

export default function SourceArticles({ articles = [] }: { articles?: ArticleReference[] }) {
  return (
    <section id="report-sources" aria-labelledby="report-sources-heading" tabIndex={-1}
      className="mb-8 scroll-mt-6 rounded-xl border border-divider bg-card p-5 dark:border-slate-700 dark:bg-slate-800">
      <h2 id="report-sources-heading" className="text-lg font-bold text-primary dark:text-white">Supporting articles ({articles.length})</h2>
      <p className="mt-1 text-sm text-muted dark:text-slate-400">Sources cited by this report. Open an article to read the original reporting and review its context.</p>
      {articles.length === 0 ? <p className="mt-4 text-sm text-muted dark:text-slate-400">No supporting articles were recorded for this report.</p> : (
        <ol className="mt-4 space-y-3">
          {articles.map((article, index) => {
            const link = articleLink(article.url);
            return (
              <li key={`${index}-${article.url ?? article.title}`} className="rounded-lg border border-divider p-4 dark:border-slate-700">
                <p className="text-xs text-muted dark:text-slate-400">
                  Source {index + 1}{link && ` · ${link.publisher}`}
                  {article.published_at && ` · ${formatApiTimestamp(article.published_at, { month: 'short', day: 'numeric', year: 'numeric' })}`}
                </p>
                {link ? <a href={link.href} target="_blank" rel="noopener noreferrer" aria-label={`${article.title || 'Untitled article'} (new tab)`}
                  className="mt-1 block break-words text-sm font-medium text-accent underline underline-offset-4 dark:text-accent">{article.title || 'Untitled article'}</a>
                  : <>
                    <p className="mt-1 break-words text-sm font-medium text-primary dark:text-white">{article.title || 'Untitled article'}</p>
                    <p className="mt-1 text-xs text-muted dark:text-slate-400">Link unavailable</p>
                  </>}
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}
