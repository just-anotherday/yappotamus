import assert from 'node:assert/strict';
import test from 'node:test';
import { describeNewsSync } from './newsSync.ts';

const complete = { status: 'completed', tickers: 3, articles_inserted: 2, duplicates_ignored: 5, symbols_failed: 0 };

test('completed sync reports newly inserted articles separately from duplicates', () => {
  const result = describeNewsSync(complete);
  assert.equal(result.kind, 'success');
  assert.equal(result.refresh, true);
  assert.match(result.message, /Added 2 new articles/);
  assert.match(result.message, /5 articles were already saved/);
});

test('a successful run with only duplicates does not claim to have added news', () => {
  const result = describeNewsSync({ ...complete, articles_inserted: 0 });
  assert.equal(result.kind, 'success');
  assert.match(result.message, /no new articles/);
});

test('HTTP-success partial results warn while refreshing saved articles', () => {
  const result = describeNewsSync({ ...complete, status: 'partial', symbols_failed: 1, error_code: 'provider_rate_limited' });
  assert.equal(result.kind, 'warning');
  assert.equal(result.refresh, true);
  assert.match(result.message, /1 of 3 companies/);
  assert.match(result.message, /rate limit/);
});

test('an overlapping job does not claim this request completed or inserted articles', () => {
  const result = describeNewsSync({ status: 'skipped_overlap' });
  assert.equal(result.kind, 'info');
  assert.equal(result.refresh, false);
  assert.match(result.message, /already running/);
});

test('Finnhub 401 explains that credentials must be updated instead of suggesting blind retries', () => {
  const result = describeNewsSync({ ...complete, status: 'partial', articles_inserted: 0, symbols_failed: 3, provider_failure_details: { AAA: { status_code: 401, outcome: 'failure' } } });
  assert.equal(result.kind, 'error');
  assert.equal(result.refresh, false);
  assert.match(result.message, /Finnhub rejected.*API key \(401\)/);
  assert.match(result.message, /restart the backend/);
});

test('a credential failure after partial insertion still refreshes the saved articles', () => {
  const result = describeNewsSync({ ...complete, status: 'partial', symbols_failed: 1, provider_failure_details: { AAA: { status_code: 401 } } });
  assert.equal(result.kind, 'warning');
  assert.equal(result.refresh, true);
});

test('failure for every company is reported as a failed sync', () => {
  const result = describeNewsSync({ ...complete, status: 'partial', articles_inserted: 0, symbols_failed: 3 });
  assert.equal(result.kind, 'error');
  assert.match(result.message, /^Sync failed:/);
});

test('empty watchlist explains why nothing was fetched', () => {
  const result = describeNewsSync({ ...complete, tickers: 0, articles_inserted: 0, duplicates_ignored: 0 });
  assert.equal(result.kind, 'info');
  assert.match(result.message, /watchlist is empty/);
});

test('missing, malformed, negative and unknown results cannot be reported as success', () => {
  for (const value of [null, {}, { status: 'skipped_cadence' }, { ...complete, articles_inserted: -1 }, { ...complete, tickers: '3' }, { ...complete, symbols_failed: undefined }]) {
    assert.throws(() => describeNewsSync(value));
  }
});
