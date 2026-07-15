// ==============================================================================
// COMPONENT: StockCard - Stock detail card + metrics grid
// ==============================================================================

import { formatCurrency, formatLargeNumber } from '@/lib/formatters';
import type { StockData } from '@/types/stock';

interface StockCardProps {
  data: StockData;
  onAddToWatchlist: (ticker: string) => void;
  isInWatchlist: boolean;
  isWatchlistFull: boolean;
}

export default function StockCard({ data, onAddToWatchlist, isInWatchlist, isWatchlistFull }: StockCardProps) {
  return (
    <div className="max-w-7xl mx-auto px-4 w-full mt-8">
       <div className="bg-white dark:bg-slate-800 rounded-xl shadow-sm border border-gray-200 dark:border-slate-700 p-6 mb-4">
         <div className="flex items-center justify-between">
           <div>
             <h2 className="text-3xl font-bold text-gray-900 dark:text-white">{data.ticker}</h2>
             <p className="text-gray-500 dark:text-slate-400 text-lg">{data.company_name}</p>
           </div>
           <div className="text-right">
             <p className="text-3xl font-bold text-gray-900 dark:text-white">
               {formatCurrency(data.current_price)}
             </p>
            <p
              className={`text-lg font-medium ${data.change > 0 ? 'text-green-600' : data.change < 0 ? 'text-red-600' : 'text-gray-500'}`}
            >
              {data.change > 0 ? '+' : ''}{data.change} ({data.change_percent}%)
            </p>
            <div className="flex gap-2 justify-end">
              <button
                onClick={() => onAddToWatchlist(data.ticker)}
                disabled={isWatchlistFull || isInWatchlist}
                className="mt-2 px-4 py-2 bg-green-600 text-white text-sm font-medium rounded-lg hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {isInWatchlist ? 'In Watchlist' : isWatchlistFull ? 'Watchlist Full' : 'Add to Watchlist'}
              </button>
            </div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
        <div className="bg-white dark:bg-slate-800 rounded-xl shadow-sm border border-gray-200 dark:border-slate-700 p-5">
          <p className="text-gray-500 dark:text-slate-400 text-sm">Previous Close</p>
          <p className="text-xl font-semibold mt-1 text-gray-900 dark:text-white">{formatCurrency(data.previous_close)}</p>
        </div>
        <div className="bg-white dark:bg-slate-800 rounded-xl shadow-sm border border-gray-200 dark:border-slate-700 p-5">
          <p className="text-gray-500 dark:text-slate-400 text-sm">Volume</p>
          <p className="text-xl font-semibold mt-1 text-gray-900 dark:text-white">{data.volume.toLocaleString()}</p>
        </div>
        <div className="bg-white dark:bg-slate-800 rounded-xl shadow-sm border border-gray-200 dark:border-slate-700 p-5">
          <p className="text-gray-500 dark:text-slate-400 text-sm">Market Cap</p>
          <p className="text-xl font-semibold mt-1 text-gray-900 dark:text-white">{formatLargeNumber(data.market_cap)}</p>
        </div>
        <div className="bg-white dark:bg-slate-800 rounded-xl shadow-sm border border-gray-200 dark:border-slate-700 p-5">
          <p className="text-gray-500 dark:text-slate-400 text-sm">52 Week High</p>
          <p className="text-xl font-semibold mt-1 text-gray-900 dark:text-white">{formatCurrency(data.fifty_two_week_high)}</p>
        </div>
        <div className="bg-white dark:bg-slate-800 rounded-xl shadow-sm border border-gray-200 dark:border-slate-700 p-5">
          <p className="text-gray-500 dark:text-slate-400 text-sm">52 Week Low</p>
          <p className="text-xl font-semibold mt-1 text-gray-900 dark:text-white">{formatCurrency(data.fifty_two_week_low)}</p>
        </div>
        <div className="bg-white dark:bg-slate-800 rounded-xl shadow-sm border border-gray-200 dark:border-slate-700 p-5">
          <p className="text-gray-500 dark:text-slate-400 text-sm">P/E Ratio</p>
          <p className="text-xl font-semibold mt-1 text-gray-900 dark:text-white">{data.pe_ratio?.toFixed(2) || 'N/A'}</p>
        </div>
      </div>
    </div>
  );
}
