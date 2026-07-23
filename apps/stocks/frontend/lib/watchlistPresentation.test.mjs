import test from 'node:test';
import assert from 'node:assert/strict';
import { canReorderWatchlist, presentWatchlist, watchlistColumnCount } from './watchlistPresentation.ts';

const item = (ticker, company_name, current_price, previous_close, market_cap) => ({ ticker, company_name, current_price, previous_close, market_cap });
const items = [item('BBB', 'Beta', 90, 100, 20), item('AAA', 'Alpha', 110, 100, 10)];

test('custom order remains the default and filtering does not mutate it', () => {
  const order = ['AAA', 'BBB'];
  assert.deepEqual(presentWatchlist(items, order, {}, '', 'custom', 'all').map(x => x.ticker), order);
  assert.deepEqual(presentWatchlist(items, order, {}, 'beta', 'custom', 'all').map(x => x.ticker), ['BBB']);
  assert.deepEqual(order, ['AAA', 'BBB']);
});

test('sorts ticker, change, market cap and filters movers', () => {
  assert.deepEqual(presentWatchlist(items, [], {}, '', 'ticker', 'all').map(x => x.ticker), ['AAA', 'BBB']);
  assert.deepEqual(presentWatchlist(items, [], {}, '', 'change', 'all').map(x => x.ticker), ['AAA', 'BBB']);
  assert.deepEqual(presentWatchlist(items, [], {}, '', 'market-cap', 'all').map(x => x.ticker), ['BBB', 'AAA']);
  assert.deepEqual(presentWatchlist(items, [], {}, '', 'custom', 'gainers').map(x => x.ticker), ['AAA']);
  assert.deepEqual(presentWatchlist(items, [], {}, '', 'custom', 'losers').map(x => x.ticker), ['BBB']);
});

test('reordering is limited to the unfiltered custom view', () => {
  assert.equal(canReorderWatchlist('custom', '', 'all'), true);
  assert.equal(canReorderWatchlist('ticker', '', 'all'), false);
  assert.equal(canReorderWatchlist('custom', 'a', 'all'), false);
  assert.equal(canReorderWatchlist('custom', '', 'gainers'), false);
});

test('column count follows extended-hours visibility', () => {
  assert.equal(watchlistColumnCount(false), 5);
  assert.equal(watchlistColumnCount(true), 6);
});