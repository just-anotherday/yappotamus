import test from 'node:test';
import assert from 'node:assert/strict';
import { dailySyncStatus, filterDailyTickers } from './dailyUpdatesPresentation.ts';

const now = Date.parse('2026-11-06T12:00:00Z');
const state = { revision: 'new', applied_revision: 'new', last_seen_at: '2026-11-06T11:59:30Z' };
test('a live acknowledgement is required before showing matching settings', () => {
  assert.equal(dailySyncStatus(state, now).label, 'Received by local automation');
  assert.equal(dailySyncStatus({ ...state, applied_revision: 'old' }, now).label, 'Syncing your changes');
});
test('distinguishes offline-but-received settings from edits waiting for the computer', () => {
  const offline = { ...state, last_seen_at: '2026-11-06T11:00:00Z' };
  assert.equal(dailySyncStatus(offline, now).label, 'Received · local automation offline');
  assert.equal(dailySyncStatus({ ...offline, applied_revision: 'old' }, now).label, 'Changes waiting for local automation');
  assert.equal(dailySyncStatus({ ...state, last_seen_at: null }, now).label, 'Waiting for local automation');
});

const tickers = [
  { ticker: 'SPY', news_enabled: true, reports_enabled: true },
  { ticker: 'MSFT', news_enabled: true, reports_enabled: false },
  { ticker: 'META', news_enabled: false, reports_enabled: true },
  { ticker: 'AMD', news_enabled: false, reports_enabled: false },
];
test('ticker search ignores case and surrounding whitespace without changing the list', () => {
  assert.deepEqual(filterDailyTickers(tickers, ' ms ', 'all').map(item => item.ticker), ['MSFT']);
  assert.equal(tickers.length, 4);
  assert.deepEqual(filterDailyTickers(tickers, '', 'all'), tickers);
});
test('news and report filters reflect independent switches', () => {
  assert.deepEqual(filterDailyTickers(tickers, '', 'news').map(item => item.ticker), ['SPY', 'MSFT']);
  assert.deepEqual(filterDailyTickers(tickers, '', 'reports').map(item => item.ticker), ['SPY', 'META']);
});
test('paused means both activities are off and combines with ticker search', () => {
  assert.deepEqual(filterDailyTickers(tickers, 'a', 'paused').map(item => item.ticker), ['AMD']);
  assert.deepEqual(filterDailyTickers(tickers, 'MSFT', 'paused'), []);
  assert.deepEqual(filterDailyTickers([], '', 'all'), []);
});
