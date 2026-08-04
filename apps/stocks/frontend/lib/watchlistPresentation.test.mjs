import test from 'node:test';
import assert from 'node:assert/strict';
import { canReorderWatchlist, getWatchlistChange, presentWatchlist, watchlistColumnCount } from './watchlistPresentation.ts';
import { formatEmployeeCount, formatMarketSize, formatWatchlistCurrency, formatWatchlistNumber, formatWatchlistPercent, formatWatchlistRange, formatWatchlistRecommendation, getCompanySize, getMarketSizeLabel, getWatchlistDataWarning, getWatchlistDisplayPrice, hasWatchlistRecommendation, mergeLiveQuote, mergeWatchlistRefresh } from './watchlistPresentation.ts';

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
  assert.equal(formatWatchlistCurrency(undefined), '—');
  assert.equal(formatWatchlistCurrency(null), '—');
  assert.equal(formatWatchlistCurrency(Number.NaN), '—');
  assert.equal(formatWatchlistCurrency(0), '$0.00');
  assert.equal(formatWatchlistNumber(undefined), '—');
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
  const errorShell = { ...previous, company_name: 'SPCX', current_price: 0, market_cap: null, market_size_status: 'provider_failed', post_market_price: null };

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

test('renders fund assets and non-USD market sizes without a dollar prefix', () => {
  const fund = { security_type: 'ETF', market_size_type: 'fund_assets', market_size_value: 10_000_000_000, market_size_currency: 'USD' };
  const fallback = { security_type: 'ETF', market_size_type: 'etf_market_cap', market_size_value: 9_000_000_000, market_size_currency: 'USD' };
  assert.equal(formatMarketSize(fund), '$10.00B');
  assert.equal(getMarketSizeLabel(fund), 'Fund Size');
  assert.equal(formatMarketSize(fallback), '$9.00B');
  assert.equal(getMarketSizeLabel(fallback), 'Fund Market Value');
  assert.equal(formatMarketSize({ market_size_type: 'market_cap', market_size_value: 62_890_000_000_000, market_size_currency: 'TWD' }), 'TWD 62.89T');
  assert.equal(formatMarketSize({ market_size_status: 'provider_failed' }), 'Unavailable');
  assert.equal(getMarketSizeLabel({ security_type: 'ETF', market_size_status: 'provider_failed' }), 'Fundamentals temporarily unavailable.');
});

test('price-only WebSocket ticks retain the official close and never become daily change', () => {
  const first = mergeLiveQuote(undefined, { ticker: 'SPY', price: 505, change: null, change_percent: null, volume: 1, previous_close: 499, open_price: 500, day_low: 498, day_high: 506 });
  const second = mergeLiveQuote(first, { ticker: 'SPY', price: 506, change: null, change_percent: null, volume: 2, previous_close: null, open_price: null, day_low: null, day_high: null });
  assert.equal(second.previous_close, 499);
  assert.equal(second.open_price, 500);
  assert.equal(second.day_low, 498);
  assert.equal(second.day_high, 506);
  assert.equal(second.change, 7);
  assert.equal(second.change_percent, (7 / 499) * 100);
  const noClose = mergeLiveQuote(undefined, { ticker: 'SPY', price: 506, change: 1, change_percent: 0.2, volume: 2 });
  assert.equal(noClose.change, null);
  assert.equal(noClose.change_percent, null);
  const completed = mergeLiveQuote(noClose, { ticker: 'SPY', price: 507, change: null, change_percent: null, volume: 3, previous_close: 500, open_price: 501, day_low: 499, day_high: 508 });
  assert.equal(completed.previous_close, 500);
  assert.equal(completed.open_price, 501);
  assert.equal(completed.day_low, 499);
  assert.equal(completed.day_high, 508);
  assert.equal(completed.change, 7);
  assert.equal(completed.change_percent, (7 / 500) * 100);
});

test('maps legacy market_cap responses and distinguishes missing equity from ETFs', () => {
  const equity = { security_type: 'STOCK', market_cap: 10_523_970_132 };
  assert.equal(formatMarketSize(equity), 'Unknown currency 10.52B');
  assert.equal(getCompanySize(equity).label, 'Large Cap');
  assert.equal(formatMarketSize({ security_type: 'STOCK', market_cap: null }), 'N/A');
  assert.equal(getCompanySize({ security_type: 'STOCK', market_cap: null }).label, 'Unavailable');
  assert.equal(formatMarketSize({ security_type: 'ETF', market_cap: null }), 'Unavailable');
  assert.equal(getCompanySize({ security_type: 'ETF', market_cap: null }).label, 'Not applicable');
});

test('classifies company size at each market-cap boundary', () => {
  const size = market_cap => getCompanySize({ security_type: 'STOCK', market_cap }).label;
  assert.equal(size(200_000_000_000), 'Mega Cap');
  assert.equal(size(10_000_000_000), 'Large Cap');
  assert.equal(size(2_000_000_000), 'Mid Cap');
  assert.equal(size(300_000_000), 'Small Cap');
  assert.equal(size(50_000_000), 'Micro Cap');
  assert.equal(size(49_999_999), 'Nano Cap');
});

test('renders unavailable measurements truthfully while preserving provider zero', () => {
  assert.equal(formatWatchlistCurrency(null), '—');
  assert.equal(formatWatchlistRange(null, 100), '—');
  assert.equal(formatWatchlistPercent(null), '—');
  assert.equal(formatWatchlistPercent(0), '0.00%');
  assert.equal(formatWatchlistPercent(null, true), 'Not applicable');
  assert.equal(formatEmployeeCount(42_000), '42,000');
  assert.equal(formatEmployeeCount(null), '—');
});

test('exposes partial and stale warnings but leaves complete rows quiet', () => {
  assert.match(getWatchlistDataWarning({ data_status: 'partial' }), /Partial data/);
  assert.match(getWatchlistDataWarning({ data_status: 'stale' }), /Stale data/);
  assert.match(getWatchlistDataWarning({
    data_status: 'stale',
    provider_status: { finnhub: 'healthy', yfinance: 'degraded' },
  }), /Stale fundamentals/);
  assert.equal(getWatchlistDataWarning({ data_status: 'complete' }), null);
});

test('missing recommendations never qualify for an unlabeled badge', () => {
  assert.equal(hasWatchlistRecommendation('N/A'), false);
  assert.equal(hasWatchlistRecommendation(null), false);
  assert.equal(hasWatchlistRecommendation('buy'), true);
});

test('partial refresh retains complete static metadata and marks it stale', () => {
  const previous = { ticker: 'ORI', company_name: 'Old Republic', data_status: 'complete', current_price: 42, fifty_two_week_high: 47, market_cap: 10_000_000_000 };
  const incoming = { ticker: 'ORI', company_name: 'Old Republic', data_status: 'partial', current_price: 44, fifty_two_week_high: null, market_cap: 10_500_000_000 };
  const [merged] = mergeWatchlistRefresh([previous], [incoming]);
  assert.equal(merged.current_price, 44);
  assert.equal(merged.fifty_two_week_high, 47);
  assert.equal(merged.data_status, 'stale');
});
test('provider failure retains the complete prior market-size identity as stale cache', () => {
  const prior = { ticker: 'SPY', company_name: 'SPDR', market_cap: null, fund_assets: 100, market_size_value: 100, market_size_type: 'fund_assets', market_size_currency: 'USD', market_size_status: 'available' };
  const failed = { ticker: 'SPY', company_name: 'SPY', market_cap: null, market_size_status: 'provider_failed' };
  const [merged] = mergeWatchlistRefresh([prior], [failed]);
  assert.equal(merged.fund_assets, 100);
  assert.equal(merged.market_size_type, 'fund_assets');
  assert.equal(merged.market_size_currency, 'USD');
  assert.equal(merged.market_size_status, 'stale_cache');
});
test('ETF refresh keeps fund assets over a newer market-cap fallback and preserves null fallback data', () => {
  const priorFund = { ticker: 'SPY', company_name: 'SPDR', security_type: 'ETF', fund_assets: 100, etf_market_cap: null, market_size_value: 100, market_size_type: 'fund_assets', market_size_currency: 'USD', market_size_source: 'yfinance_info.totalAssets', market_size_status: 'available' };
  const capOnly = { ticker: 'SPY', company_name: 'SPDR', security_type: 'ETF', fund_assets: null, etf_market_cap: 120, market_size_value: 120, market_size_type: 'etf_market_cap', market_size_currency: 'USD', market_size_source: 'yfinance_info.marketCap', market_size_status: 'available' };
  const [fundPreserved] = mergeWatchlistRefresh([priorFund], [capOnly]);
  assert.equal(fundPreserved.market_size_value, 100);
  assert.equal(fundPreserved.market_size_type, 'fund_assets');
  assert.equal(fundPreserved.market_size_source, 'yfinance_info.totalAssets');

  const priorCap = { ...capOnly, etf_market_cap: 120 };
  const nullRefresh = { ...capOnly, etf_market_cap: null, market_size_value: null, market_size_type: null, market_size_source: null };
  const [capPreserved] = mergeWatchlistRefresh([priorCap], [nullRefresh]);
  assert.equal(capPreserved.etf_market_cap, 120);
  assert.equal(capPreserved.market_size_value, 120);
  assert.equal(capPreserved.market_size_type, 'etf_market_cap');
});
test('market-size sorting uses displayed ETF values without company classification', () => {
  const fund = { ticker: 'FUND', company_name: 'Fund', security_type: 'ETF', market_size_value: 90, market_size_type: 'fund_assets' };
  const fallback = { ticker: 'CAP', company_name: 'Cap ETF', security_type: 'ETF', market_size_value: 110, market_size_type: 'etf_market_cap' };
  const equity = { ticker: 'EQ', company_name: 'Equity', security_type: 'STOCK', market_size_value: 100, market_size_type: 'market_cap' };
  assert.deepEqual(presentWatchlist([fund, fallback, equity], [], {}, '', 'market-cap', 'all').map(row => row.ticker), ['CAP', 'EQ', 'FUND']);
  assert.equal(getCompanySize(fallback).label, 'Not applicable');
});
test('normalizes valid currencies and labels missing currency explicitly', () => {
  assert.equal(formatMarketSize({ market_size_value: 4_860_000_000_000, market_size_currency: 'usd' }), '$4.86T');
  assert.equal(formatMarketSize({ market_size_value: 62_890_000_000_000, market_size_currency: ' TWD ' }), 'TWD 62.89T');
  assert.equal(formatMarketSize({ market_size_value: 1_200_000_000, market_size_currency: 'EUR' }), 'EUR 1.20B');
  for (const currency of [null, undefined, '', '   ']) {
    assert.equal(formatMarketSize({ market_size_value: 4_860_000_000_000, market_size_currency: currency }), 'Unknown currency 4.86T');
  }
  assert.equal(formatMarketSize({ market_size_currency: 'USD' }), 'N/A');
  assert.equal(formatMarketSize({ market_size_status: 'provider_failed' }), 'Unavailable');
});
