export const NEWS_SYNC_COMPLETED_EVENT = 'yapvibes:news-synced';

export interface NewsSyncFeedback {
  kind: 'success' | 'warning' | 'info' | 'error';
  message: string;
  refresh: boolean;
}

/** A successful HTTP response can still describe an incomplete ingestion run. */
export function describeNewsSync(payload: unknown): NewsSyncFeedback {
  if (!payload || typeof payload !== 'object') throw new Error('Invalid news sync response');
  const result = payload as Record<string, unknown>;
  if (result.status === 'skipped_overlap') return {
    kind: 'info', refresh: false,
    message: 'A news sync is already running. Wait for it to finish, then refresh the news list.',
  };
  if (result.status !== 'completed' && result.status !== 'partial') {
    throw new Error('The server did not confirm a completed news sync');
  }
  const count = (key: string) => {
    const value = result[key];
    if (typeof value !== 'number' || !Number.isSafeInteger(value) || value < 0) {
      throw new Error('Invalid news sync counts');
    }
    return value;
  };
  const tickers = count('tickers');
  const added = count('articles_inserted');
  const duplicates = count('duplicates_ignored');
  const failed = count('symbols_failed');
  if (result.status === 'partial' || failed > 0) {
    const details = result.provider_failure_details;
    const rejectedKey = details && typeof details === 'object' && Object.values(details).some(
      failure => failure && typeof failure === 'object' && failure.status_code === 401,
    );
    if (rejectedKey) return {
      kind: added > 0 ? 'warning' : 'error', refresh: added > 0,
      message: `${added > 0 ? `${added} articles added, but ` : ''}Finnhub rejected the server’s API key (401). Update the Finnhub key and restart the backend before syncing again.`,
    };
    const allFailed = tickers > 0 && failed === tickers && added === 0;
    const reason = result.error_code === 'provider_rate_limited'
      ? 'The news provider rate limit was reached.'
      : result.error_code === 'provider_timeout' ? 'The news provider timed out.' : 'Check the news provider connection.';
    return { kind: allFailed ? 'error' : 'warning', refresh: !allFailed, message: `${allFailed ? 'Sync failed' : 'Sync incomplete'}: ${added} article${added === 1 ? '' : 's'} added; ${failed} of ${tickers} companies could not be checked. ${reason} Try again later.` };
  }
  if (tickers === 0) return { kind: 'info', refresh: true, message: 'Your watchlist is empty. Add a company, then sync its news.' };
  return {
    kind: 'success', refresh: true,
    message: `${added ? `Added ${added} new article${added === 1 ? '' : 's'}.` : 'Sync complete: no new articles.'} Checked ${tickers} compan${tickers === 1 ? 'y' : 'ies'}; ${duplicates} article${duplicates === 1 ? ' was' : 's were'} already saved.`,
  };
}
