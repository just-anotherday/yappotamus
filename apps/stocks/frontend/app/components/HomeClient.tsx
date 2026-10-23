'use client';

import { useState } from 'react';
import dynamic from 'next/dynamic';
import Link from 'next/link';
import HomeNews from './HomeNews';
import WatchlistTable from '@/components/watchlist/WatchlistTable';
import ErrorBanner from '@/components/ui/ErrorBanner';
import SuccessBanner from '@/components/ui/SuccessBanner';
import { useLivePrices } from '@/hooks/useLivePrices';
import { useWatchlist } from '@/hooks/useWatchlist';
import { fetchStock } from '@/lib/api';
import type { StockData } from '@/types/stock';
import { getWatchlistChange } from '@/lib/watchlistPresentation';
import AppIcon from '@/components/ui/AppIcon';


const StockCard = dynamic(() => import('@/components/stock/StockCard'), {
  loading: () => <p role="status" className="py-4 text-sm">Loading stock details…</p>,
});

export default function HomeClient() {
  const [ticker, setTicker] = useState('');
  const [stockData, setStockData] = useState<StockData | null>(null);
  const [loading, setLoading] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);

  const { livePrices, priceFlash } = useLivePrices();
  const {
    watchlist,
    watchlistLoading,
    error,
    successMessage,
    addTicker,
    removeTicker,
    watchlistOrder,
    reorderWatchlist,
    maxWatchlistSize,
    postMarketFlash,
    isReordering,
    lastRefreshedAt,
    loadWatchlist,
  } = useWatchlist();

  const handleChangeTicker = (value: string) => {
    setTicker(value);
    if (!value.trim() && stockData) {
      setStockData(null);
    }
  };

  const handleSearch = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!ticker.trim()) return;
    setLoading(true);
    setStockData(null);
    try {
      const data = await fetchStock(ticker);
      setStockData(data);
      setSearchError(null);
    } catch (err) {
      setSearchError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  };

  const changes = watchlist.map(item => getWatchlistChange(item, livePrices[item.ticker]));
  const rising = changes.filter(change => change != null && change > 0).length;
  const falling = changes.filter(change => change != null && change < 0).length;

  return (
    <div className="workspace-page">

      <section aria-labelledby="watchlist-briefing" className="page-heading overview-heading">
          <div>
            <p className="eyebrow"><span className="accent-line" /> The overview</p>
            <h1 id="watchlist-briefing">Your research desk.</h1>
            <p>Follow your companies. Find the stories. See the bigger picture.</p>
          </div>
          <Link href="/analysis/reports" className="button-secondary">Explore your research <AppIcon name="arrow" width={15} height={15} /></Link>
      </section>

      <div className="surface overview-summary" aria-live="polite" aria-busy={watchlistLoading}>
        <div className="overview-stat"><div><p className="overview-stat-label">Companies tracked</p><p className="overview-stat-value">{watchlistLoading ? '—' : watchlist.length}</p></div><span className="stat-icon"><AppIcon name="dashboard" /></span></div>
        <div className="overview-stat"><div><p className="overview-stat-label">Moving up</p><p className="overview-stat-value">{watchlistLoading ? '—' : rising}</p></div><span className="stat-icon positive"><AppIcon name="chart" /></span></div>
        <div className="overview-stat"><div><p className="overview-stat-label">Moving down</p><p className="overview-stat-value">{watchlistLoading ? '—' : falling}</p></div><span className="stat-icon negative"><AppIcon name="chart" style={{ transform: 'scaleY(-1)' }} /></span></div>
      </div>
      <p className="overview-caption">Based on available price changes in your watchlist. Companies without change data are excluded.</p>

      <form onSubmit={handleSearch} className="ticker-search">
        <div><AppIcon name="search" width={17} height={17} />
        <input
          type="text"
          aria-label="Look up a ticker"
          value={ticker}
          onChange={(e) => handleChangeTicker(e.target.value)}
          placeholder="Look up a company ticker…"
        />
        </div>
        <button
          type="submit"
          disabled={loading || !ticker.trim()}
          className="button-primary disabled:opacity-50"
        >
          {loading ? 'Searching…' : 'Look up'}
        </button>
        <span className="ticker-search-hint">A closer look starts with a ticker.</span>
      </form>

      {/* Search error message */}
      {searchError && <ErrorBanner message={searchError} />}

      {/* Watchlist error message */}
      {error && <ErrorBanner message={error} />}

      {/* Stock Detail Card */}
      {stockData && (
        <StockCard
          data={stockData}
          onAddToWatchlist={addTicker}
          isInWatchlist={watchlist.some(item => item.ticker === stockData.ticker)}
          isWatchlistFull={watchlist.length >= maxWatchlistSize}
        />
      )}

      {/* Success message */}
      {successMessage && <SuccessBanner message={successMessage} />}

      <div className="mb-10 w-full overflow-visible">
        <WatchlistTable
          watchlist={watchlist}
          livePrices={livePrices}
          priceFlash={priceFlash}
          postMarketFlash={postMarketFlash}
          loading={watchlistLoading}
          onRemove={removeTicker}
          watchlistOrder={watchlistOrder}
          onReorder={reorderWatchlist}
          onRefresh={() => loadWatchlist()}
          lastRefreshedAt={lastRefreshedAt}
          isReordering={isReordering}
        />
      </div>
      <HomeNews />
    </div>
  );
}
