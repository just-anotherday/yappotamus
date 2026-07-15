// ==============================================================================
// COMPONENT: TickerHeader - Full stock detail card with live price flash
// Matches the watchlist StockCard style for /news/[ticker] page
// ==============================================================================

import { useEffect, useState } from 'react';
import { fetchStock } from '@/lib/api';
import { useLivePrices } from '@/hooks/useLivePrices';
import { formatCurrency, formatLargeNumber } from '@/lib/formatters';
import type { StockData, LiveQuote } from '@/types/stock';

interface TickerHeaderProps {
  ticker: string;
}

export default function TickerHeader({ ticker }: TickerHeaderProps) {
  const [stockData, setStockData] = useState<StockData | null>(null);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const { livePrices } = useLivePrices();
  const liveQuote = livePrices[ticker];

  // Fetch fundamental data on mount
  useEffect(() => {
    let cancelled = false;
    fetchStock(ticker)
      .then(data => { if (!cancelled) setStockData(data); })
      .catch(err => { if (!cancelled) setFetchError(err.message); });
    return () => { cancelled = true; };
  }, [ticker]);

  // Determine which price to display: live WS price or initial fetch
  const displayPrice = liveQuote?.price ?? stockData?.current_price ?? null;
  const displayChange = liveQuote?.change ?? stockData?.change ?? 0;
  const displayChangePercent = liveQuote?.change_percent ?? stockData?.change_percent ?? 0;
  const company = stockData?.company_name || ticker;

  // Flash class based on price direction (use a ref-style state to avoid flickering)
  const [flash, setFlash] = useState<'up' | 'down' | ''>('');
  const prevPriceRef: { current: number | null } = { current: displayPrice };

  useEffect(() => {
    if (displayPrice === null || displayPrice === undefined) return;
    if (prevPriceRef.current !== null && displayPrice !== prevPriceRef.current) {
      if (displayPrice > prevPriceRef.current) {
        setFlash('up');
      } else {
        setFlash('down');
      }
      setTimeout(() => setFlash(''), 1000);
    }
    prevPriceRef.current = displayPrice;
  }, [displayPrice]);

  const flashClass = flash === 'up' ? 'bg-green-200 dark:bg-green-900/40 animate-pulse' : flash === 'down' ? 'bg-red-200 dark:bg-red-900/40 animate-pulse' : '';
  const changeColor = displayChange > 0 ? 'text-green-600 dark:text-green-400' : displayChange < 0 ? 'text-red-600 dark:text-red-400' : 'text-gray-500 dark:text-slate-400';

  return (
    <div className="max-w-7xl mx-auto w-full">
      {/* Main header card - mirrors StockCard layout */}
      <div className="bg-white dark:bg-slate-800 rounded-xl shadow-sm border border-gray-200 dark:border-slate-600 p-6 mb-4">
        <div className="flex items-center justify-between">
          {/* Left: Company + Ticker */}
          <div>
            <h2 className="text-3xl font-bold text-gray-900 dark:text-white">{company}</h2>
            <p className="text-blue-600 dark:text-blue-400 text-lg font-semibold">{ticker}</p>
          </div>
          {/* Right: Live Price + Change */}
          <div className={`text-right px-6 py-4 rounded-xl transition-all duration-300 ${flashClass}`}>
            {displayPrice !== null ? (
              <>
                <p className="text-3xl font-bold text-gray-900 dark:text-white">
                  {formatCurrency(displayPrice)}
                </p>
                <p className={`text-lg font-medium mt-1 ${changeColor}`}>
                  {displayChange > 0 ? '+' : ''}{displayChange.toFixed(2)} ({typeof displayChangePercent === 'number' && !isNaN(displayChangePercent) ? displayChangePercent.toFixed(2) : '0.00'}%)
                </p>
              </>
            ) : (
              <p className="text-gray-400 dark:text-slate-500 text-lg">Loading price...</p>
            )}
          </div>
        </div>
      </div>

      {/* Metrics grid - mirrors StockCard metrics */}
      {stockData && (
        <div className="grid grid-cols-2 md:grid-cols-3 gap-4 mb-4">
          <div className="bg-white dark:bg-slate-800 rounded-xl shadow-sm border border-gray-200 dark:border-slate-600 p-5">
            <p className="text-gray-500 dark:text-slate-400 text-sm">Previous Close</p>
            <p className="text-xl font-semibold mt-1 text-gray-900 dark:text-white">{formatCurrency(stockData.previous_close)}</p>
          </div>
          <div className="bg-white dark:bg-slate-800 rounded-xl shadow-sm border border-gray-200 dark:border-slate-600 p-5">
            <p className="text-gray-500 dark:text-slate-400 text-sm">Volume</p>
            <p className="text-xl font-semibold mt-1 text-gray-900 dark:text-white">{stockData.volume.toLocaleString()}</p>
          </div>
          <div className="bg-white dark:bg-slate-800 rounded-xl shadow-sm border border-gray-200 dark:border-slate-600 p-5">
            <p className="text-gray-500 dark:text-slate-400 text-sm">Market Cap</p>
            <p className="text-xl font-semibold mt-1 text-gray-900 dark:text-white">{formatLargeNumber(stockData.market_cap)}</p>
          </div>
          <div className="bg-white dark:bg-slate-800 rounded-xl shadow-sm border border-gray-200 dark:border-slate-600 p-5">
            <p className="text-gray-500 dark:text-slate-400 text-sm">52 Week High</p>
            <p className="text-xl font-semibold mt-1 text-gray-900 dark:text-white">{formatCurrency(stockData.fifty_two_week_high)}</p>
          </div>
          <div className="bg-white dark:bg-slate-800 rounded-xl shadow-sm border border-gray-200 dark:border-slate-600 p-5">
            <p className="text-gray-500 dark:text-slate-400 text-sm">52 Week Low</p>
            <p className="text-xl font-semibold mt-1 text-gray-900 dark:text-white">{formatCurrency(stockData.fifty_two_week_low)}</p>
          </div>
          <div className="bg-white dark:bg-slate-800 rounded-xl shadow-sm border border-gray-200 dark:border-slate-600 p-5">
            <p className="text-gray-500 dark:text-slate-400 text-sm">P/E Ratio</p>
            <p className="text-xl font-semibold mt-1 text-gray-900 dark:text-white">{stockData.pe_ratio?.toFixed(2) || 'N/A'}</p>
          </div>
        </div>
      )}

      {fetchError && (
        <p className="mt-3 text-xs text-red-500 dark:text-red-400">Failed to load fundamentals: {fetchError}</p>
      )}
    </div>
  );
}
