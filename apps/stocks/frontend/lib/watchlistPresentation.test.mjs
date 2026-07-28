import test from 'node:test';
import assert from 'node:assert/strict';
import { canReorderWatchlist, getWatchlistChange, presentWatchlist, watchlistColumnCount } from './watchlistPresentation.ts';
import { formatWatchlistCurrency, formatWatchlistNumber, formatWatchlistRecommendation, getWatchlistDisplayPrice, mergeWatchlistRefresh } from './watchlistPresentation.ts';

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

test('prefers the live change percentage and falls back to the live previous close', () => {
  const base = item('AAA', 'Alpha', 110, 100, 10);
  assert.equal(getWatchlistChange(base, { ticker: 'AAA', price: 120, change: 1, change_percent: 1.25, volume: 1 }), 1.25);
  assert.equal(getWatchlistChange({ ...base, previous_close: 0 }, { ticker: 'AAA', price: 102, change: 2, change_percent: null, volume: 1, previous_close: 100 }), 2);
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
test('optional watchlist values render safely and zero remains distinct from missing', () => {
  assert.equal(formatWatchlistCurrency(undefined), 'N/A');
  assert.equal(formatWatchlistCurrency(null), 'N/A');
  assert.equal(formatWatchlistCurrency(Number.NaN), 'N/A');
  assert.equal(formatWatchlistCurrency(0), '$0.00');
  assert.equal(formatWatchlistNumber(undefined), 'N/A');
  assert.equal(formatWatchlistNumber(0), '0.00');
  assert.equal(formatWatchlistRecommendation(undefined), 'N/A');
  assert.equal(formatWatchlistRecommendation('strong_buy'), 'STRONG BUY');
});

test('missing runtime price fields do not create NaN change percentages', () => {
  const sparse = { ticker: 'SPY', company_name: 'Sparse ETF', current_price: undefined, previous_close: 100, market_cap: undefined };
  assert.equal(getWatchlistChange(sparse), null);
  assert.equal(getWatchlistDisplayPrice(sparse), null);
  assert.equal(getWatchlistDisplayPrice({ ...sparse, current_price: 0 }), null);
  assert.deepEqual(presentWatchlist([sparse], [], {}, '', 'market-cap', 'all'), [sparse]);
});

const completeSpy = () => ({
  ticker: 'SPY',
  symbol: 'SPY',
  company_name: 'SPDR S&P 500 ETF Trust',
  sector: 'Broad Market',
  industry: 'Exchange Traded Fund',
  long_business_summary: 'Tracks the S&P 500.',
  website: 'https://example.test/spy',
  full_time_employees: null,
  average_analyst_rating: null,
  forward_pe: 22,
  ceo_name: null,
  exchange: 'PCX',
  security_type: 'ETF',
  current_price: 500,
  open_price: 498,
  previous_close: 499,
  day_low: 497,
  day_high: 502,
  fifty_two_week_high: 510,
  fifty_two_week_low: 400,
  change: 1,
  change_percent: 0.2,
  market_cap: 500_000_000_000,
  volume: 10_000,
  shares_outstanding: null,
  float_shares: null,
  insider_percent: 0.03,
  institution_percent: null,
  beta: 1,
  short_percent_of_float: null,
  shares_short: null,
  overall_risk: 3,
  target_mean_price: null,
  target_median_price: null,
  target_high_price: null,
  target_low_price: null,
  recommendation_key: 'buy',
  number_of_analysts: null,
  etf_data: {
    fund_family: 'Example Funds',
    expense_ratio: 0.0009,
    net_assets: 500_000_000_000,
    holdings_count: 503,
  },
  data_source: 'yf',
  yf_enriched_fields: [],
});

test('partial full-refresh quote does not erase existing ETF fundamentals', () => {
  const previous = completeSpy();
  const partial = {
    ticker: 'SPY',
    symbol: 'SPY',
    company_name: 'SPY',
    sector: null,
    current_price: 501,
    open_price: 0,
    previous_close: 0,
    day_low: 0,
    day_high: 0,
    fifty_two_week_high: 0,
    fifty_two_week_low: 0,
    change: 2,
    change_percent: 0.4,
    market_cap: 0,
    volume: 0,
    insider_percent: 0,
    beta: 1,
    overall_risk: 5,
    security_type: 'UNKNOWN',
    recommendation_key: 'N/A',
    etf_data: { fund_family: null, expense_ratio: 0 },
    data_source: 'yf',
  };

  const [merged] = mergeWatchlistRefresh([previous], [partial]);

  assert.equal(merged.current_price, 501);
  assert.equal(merged.change_percent, 0.4);
  assert.equal(merged.company_name, previous.company_name);
  assert.equal(merged.market_cap, previous.market_cap);
  assert.equal(merged.previous_close, previous.previous_close);
  assert.equal(merged.sector, previous.sector);
  assert.equal(merged.industry, previous.industry);
  assert.equal(merged.security_type, 'ETF');
  assert.equal(merged.recommendation_key, 'buy');
  assert.equal(merged.etf_data.fund_family, 'Example Funds');
  assert.equal(merged.etf_data.expense_ratio, 0);
  assert.equal(merged.insider_percent, 0);
});

test('unsupported-symbol error shell cannot replace complete custom SPCX data', () => {
  const previous = { ...completeSpy(), ticker: 'SPCX', symbol: 'SPCX', company_name: 'Space Exploration Technologies', security_type: 'STOCK', market_cap: 1_500_000_000_000 };
  const errorShell = { ...previous, company_name: 'Error', current_price: 0, market_cap: 0, recommendation_key: 'error', post_market_price: null };

  const [merged] = mergeWatchlistRefresh([previous], [errorShell]);

  assert.equal(merged.company_name, 'Space Exploration Technologies');
  assert.equal(merged.current_price, previous.current_price);
  assert.equal(merged.market_cap, previous.market_cap);
});

test('late WebSocket quote changes price and change only, preserving metadata', () => {
  const previous = Object.freeze(completeSpy());
  const before = JSON.stringify(previous);
  const live = { ticker: 'SPY', price: 505, change: 6, change_percent: 1.2, volume: 20_000, previous_close: 499 };

  assert.equal(getWatchlistDisplayPrice(previous, live), 505);
  assert.equal(getWatchlistChange(previous, live), 1.2);
  assert.equal(previous.company_name, 'SPDR S&P 500 ETF Trust');
  assert.equal(previous.market_cap, 500_000_000_000);
  assert.equal(JSON.stringify(previous), before);
});
