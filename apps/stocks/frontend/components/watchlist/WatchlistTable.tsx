'use client';

// ==============================================================================
// COMPONENT: WatchlistTable - Compact watchlist table with expandable details
// ==============================================================================

import React, { useState, useCallback, useMemo, useRef, Fragment } from 'react';
import Link from 'next/link';
import { DndContext, KeyboardSensor, PointerSensor, useSensor, useSensors, DragEndEvent } from '@dnd-kit/core';
import { SortableContext, verticalListSortingStrategy, useSortable, arrayMove, sortableKeyboardCoordinates } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { EASTERN_TIME_ZONE, formatShares, riskBadgeClass, recommendationBadgeClass, safePercent, formatExpenseRatio, formatAUM } from '@/lib/formatters';
import type { WatchlistItem, LiveQuote } from '@/types/stock';
import TickerTooltip from './TickerTooltip';
import TickerResearchNotes from '@/components/TickerResearchNotes';
import { useExtendedHours } from '@/hooks/useExtendedHours';
import type { WatchlistRefreshResult } from '@/hooks/useWatchlist';
import {
  canReorderWatchlist,
  formatWatchlistCurrency,
  formatWatchlistNumber,
  formatWatchlistRecommendation,
  formatMarketSize,
  getMarketSizeLabel,
  getCompanySize,
  formatWatchlistPercent,
  formatWatchlistRange,
  formatEmployeeCount,
  getWatchlistDataWarning,
  hasWatchlistRecommendation,
  getWatchlistDisplayPrice,
  getWatchlistChange,
  presentWatchlist,
  watchlistColumnCount,
} from '@/lib/watchlistPresentation';
import type { WatchlistDirectionFilter, WatchlistSort } from '@/lib/watchlistPresentation';

interface WatchlistTableProps {
  watchlist: WatchlistItem[];
  livePrices: Record<string, LiveQuote>;
  priceFlash: Record<string, 'up' | 'down'>;
  postMarketFlash: Record<string, 'up' | 'down'>;
  loading: boolean;
  onRemove: (ticker: string) => void;
  watchlistOrder: string[];
  onReorder: (newOrder: string[]) => void;
  onRefresh: () => Promise<WatchlistRefreshResult>;
  lastRefreshedAt: Date | null;
  isReordering: boolean;
}

const SortableRow = React.memo(function SortableRow({ ticker, disabled, children }: { ticker: string; disabled: boolean; children: React.ReactNode }) {
  const { attributes, listeners, setNodeRef, transform, transition } = useSortable({ id: ticker, disabled });
  return (
    <tr ref={setNodeRef} style={{ transform: CSS.Transform.toString(transform), transition }}>
      <td {...attributes} {...listeners} className={`px-3 py-2.5 text-muted select-none text-center ${disabled ? 'cursor-not-allowed opacity-40' : 'cursor-grab'}`} aria-label={`Reorder ${ticker}`}>
        <span aria-hidden="true">⋮⋮</span>
      </td>
      {children}
    </tr>
  );
});

export default function WatchlistTable({ watchlist, livePrices, priceFlash, postMarketFlash, loading, onRemove, watchlistOrder, onReorder, onRefresh, lastRefreshedAt, isReordering }: WatchlistTableProps) {
  const [expandedTickers, setExpandedTickers] = useState<Set<string>>(new Set());
  const [deletingTicker, setDeletingTicker] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [sort, setSort] = useState<WatchlistSort>('custom');
  const [direction, setDirection] = useState<WatchlistDirectionFilter>('all');
  const [refreshing, setRefreshing] = useState(false);
  const [refreshFeedback, setRefreshFeedback] = useState<{ error: boolean; message: string } | null>(null);
  const refreshInFlight = useRef(false);
  const { isExtendedHours: showAfterHours } = useExtendedHours();

  const handleRefresh = async () => {
    if (refreshInFlight.current || loading) return;
    refreshInFlight.current = true;
    setRefreshing(true);
    setRefreshFeedback(null);
    try {
      const result = await onRefresh();
      if (result.status === 'completed') {
        setRefreshFeedback({ error: false, message: `Refresh complete — ${result.count} ticker${result.count === 1 ? '' : 's'} checked. ${result.partial ? 'Some data is still cached or unavailable.' : 'Values may be unchanged.'}` });
      } else if (result.status === 'failed') {
        setRefreshFeedback({ error: true, message: `Refresh failed: ${result.message}. Try again; last-known values are still shown.` });
      } else {
        setRefreshFeedback({ error: false, message: 'The watchlist changed during refresh. Refresh again to check the latest list.' });
      }
    } catch {
      setRefreshFeedback({ error: true, message: 'Refresh failed. Try again; last-known values are still shown.' });
    } finally {
      refreshInFlight.current = false;
      setRefreshing(false);
    }
  };

  const allExpanded = watchlist.length > 0 && watchlist.every(item => expandedTickers.has(item.ticker));
  const reorderEnabled = canReorderWatchlist(sort, search, direction) && !isReordering;

  const toggleExpand = (ticker: string) => {
    setExpandedTickers(prev => {
      const next = new Set([...prev].filter(value => watchlist.some(item => item.ticker === value)));
      if (next.has(ticker)) {
        next.delete(ticker);
      } else {
        next.add(ticker);
      }
      return next;
    });
  };

  const toggleExpandAll = () => {
    if (allExpanded) {
      setExpandedTickers(new Set());
    } else {
      setExpandedTickers(new Set(watchlist.map(item => item.ticker)));
    }
  };

  // Ref to track if a drag is in progress — prevents double-click needed to expand
  const draggedRef = useRef(false);

  const safeToggleExpand = (ticker: string) => {
    if (draggedRef.current) return;
    toggleExpand(ticker);
  };

  const handleDelete = (ticker: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setDeletingTicker(ticker);
    setTimeout(() => {
      onRemove(ticker);
      setDeletingTicker(null);
    }, 400);
  };

  // ----------------------------------------------------------------
  // DnD sensors + handlers
  // ----------------------------------------------------------------
  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: { distance: 5 },
    }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  const handleDragEnd = useCallback(
    (event: DragEndEvent) => {
      const { active, over } = event;
      if (!reorderEnabled || !over || active.id === over.id) return;

      const oldIndex = watchlistOrder.indexOf(String(active.id));
      const newIndex = watchlistOrder.indexOf(String(over.id));
      if (oldIndex < 0 || newIndex < 0) return;

      const reordered = arrayMove(watchlistOrder, oldIndex, newIndex);
      onReorder(reordered);
    },
    [watchlistOrder, onReorder, reorderEnabled]
  );

  // Build ordered list from watchlistOrder + watchlist data
  const orderedWatchlist = useMemo(
    () => presentWatchlist(watchlist, watchlistOrder, livePrices, search, sort, direction),
    [watchlist, watchlistOrder, livePrices, search, sort, direction],
  );

  return (
    <div className="w-full watchlist-section">
      {/* Section Header */}
      <div className="watchlist-section-header">
          <div>
            <h2>Your watchlist</h2>
            <p>Your companies, at a glance. Expand a row for a closer look.</p>
          </div>
        {watchlist.length > 0 && (
          <button
            onClick={toggleExpandAll}
            className="button-secondary group"
          >
            {allExpanded ? (
              <>
                <svg className="w-4 h-4 group-hover:scale-110 transition-transform" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M5 15l7-7 7 7" />
                </svg>
                Collapse All
              </>
            ) : (
              <>
                <svg className="w-4 h-4 group-hover:scale-110 transition-transform" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
                </svg>
                Expand All
              </>
            )}
          </button>
        )}
      </div>

      <div className="watchlist-toolbar surface mb-3 flex flex-wrap items-center gap-2 p-3">
        <input aria-label="Search watchlist" value={search} onChange={event => setSearch(event.target.value)} placeholder="Search ticker or company" className="min-w-48 flex-1 rounded-md border px-3 py-2 text-sm dark:bg-slate-800" />
        <select aria-label="Sort watchlist" value={sort} onChange={event => setSort(event.target.value as WatchlistSort)} className="rounded-md border px-3 py-2 text-sm dark:bg-slate-800">
          <option value="custom">Custom order</option><option value="ticker">Ticker</option><option value="change">Price change</option><option value="market-cap">Market size</option>
        </select>
        <select aria-label="Filter watchlist movers" value={direction} onChange={event => setDirection(event.target.value as WatchlistDirectionFilter)} className="rounded-md border px-3 py-2 text-sm dark:bg-slate-800">
          <option value="all">All</option><option value="gainers">Gainers</option><option value="losers">Losers</option>
        </select>
        <span className="text-xs text-muted">{orderedWatchlist.length} of {watchlist.length}</span>
        <button type="button" onClick={handleRefresh} disabled={loading || refreshing} aria-busy={loading || refreshing} aria-controls="watchlist-refresh-status" className="inline-flex items-center gap-2 rounded-md border px-3 py-2 text-xs font-semibold disabled:cursor-wait disabled:opacity-60">
          {(loading || refreshing) && <span aria-hidden="true" className="h-3 w-3 animate-spin rounded-full border-2 border-current border-t-transparent motion-reduce:animate-none" />}
          {loading || refreshing ? 'Refreshing…' : 'Refresh'}
        </button>
        <span className="text-xs text-muted">{lastRefreshedAt ? `Last checked ${lastRefreshedAt.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit', timeZone: EASTERN_TIME_ZONE, timeZoneName: 'short' })}` : 'Not refreshed'}</span>
        <p id="watchlist-refresh-status" role={refreshFeedback?.error ? 'alert' : 'status'} className={`w-full text-xs ${refreshFeedback?.error ? 'text-negative dark:text-negative' : 'text-positive dark:text-positive'}`}>
          {refreshing ? 'Checking watchlist data… Last-known values remain visible.' : refreshFeedback?.message}
        </p>
        {!reorderEnabled && <span className="w-full text-xs text-warning">Clear filters and select Custom order to drag.</span>}
      </div>

      {loading && watchlist.length > 0 && <p role="status" className="mb-3 text-xs text-warning dark:text-warning">Showing the last loaded watchlist while refreshing.</p>}
      {loading && watchlist.length === 0 ? (
        /* Skeleton loader: renders a table-shaped skeleton with 4 pulsing rows */
        <div className="bg-card rounded-xl shadow-sm border overflow-hidden">
          <table className="w-full text-sm whitespace-nowrap">
            <thead className="bg-surface-muted border-b">
              <tr>
                <th className="px-2 py-2.5 text-center font-semibold text-secondary w-8"></th>
                <th className="px-2 py-2.5 text-left font-semibold text-secondary min-w-0">Ticker / Company</th>
                <th className="px-2 py-2.5 text-right font-semibold text-secondary tabular-nums">Current Price</th>
                <th className="px-2 py-2.5 text-right font-semibold text-secondary tabular-nums">Change %</th>
                <th className="px-2 py-2.5 text-right font-semibold text-secondary tabular-nums">Market Size</th>
              </tr>
            </thead>
            <tbody>
              {[...Array(4)].map((_, i) => (
                <tr key={i} className="border-b last:border-0">
                  <td className="px-3 py-2.5"><div className="h-4 w-4 bg-gray-200 rounded animate-pulse" /></td>
                  <td className="px-3 py-2.5">
                    <div className="flex flex-col gap-1">
                      <div className="h-4 w-16 bg-gray-200 rounded animate-pulse" />
                      <div className="h-3 w-32 bg-surface-muted rounded animate-pulse" style={{ animationDelay: '100ms' }} />
                    </div>
                  </td>
                  <td className="px-3 py-2.5 text-right"><div className="h-4 w-20 bg-gray-200 rounded animate-pulse ml-auto" /></td>
                  <td className="px-3 py-2.5 text-right"><div className="h-4 w-16 bg-gray-200 rounded animate-pulse ml-auto" /></td>
                  <td className="px-3 py-2.5 text-right"><div className="h-4 w-20 bg-gray-200 rounded animate-pulse ml-auto" /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="watchlist-table-shell w-full overflow-x-auto">
          <DndContext
            sensors={sensors}
            onDragStart={() => { draggedRef.current = true; }}
            onDragCancel={() => { draggedRef.current = false; }}
            onDragEnd={(event) => {
              handleDragEnd(event);
              draggedRef.current = false;
            }}
          >
            <SortableContext items={reorderEnabled ? watchlistOrder : []} strategy={verticalListSortingStrategy} disabled={!reorderEnabled}>
              <table className="w-full text-sm whitespace-nowrap">
                <thead className="bg-surface-muted border-b">
                  <tr>
                    <th className="px-3 py-2.5 text-center font-semibold text-secondary w-8" title="Drag to reorder"></th>
                    <th className="px-3 py-2.5 text-left font-semibold text-secondary">Ticker / Company</th>
                    <th className="px-3 py-2.5 text-right font-semibold text-secondary tabular-nums">Current Price</th>
                     <th className="px-3 py-2.5 text-right font-semibold text-secondary tabular-nums">Change %</th>
                     {showAfterHours && (
                       <th className="px-3 py-2.5 text-right font-semibold text-secondary tabular-nums" title="Extended-hours price (pre-market and after-hours ET)">After Hours</th>
                     )}
                     <th className="px-3 py-2.5 text-right font-semibold text-secondary tabular-nums">Market Size</th>
                   </tr>
                 </thead>
                 <tbody>
                   {orderedWatchlist.map((item) => {
                const live = livePrices[item.ticker];
                const isExpanded = expandedTickers.has(item.ticker);
                const liveOpen = live?.open_price ?? item.open_price;
                const livePreviousClose = live?.previous_close ?? item.previous_close;
                const liveDayLow = live?.day_low ?? item.day_low;
                const liveDayHigh = live?.day_high ?? item.day_high;

                // Use live price if available, fall back to static fundamental data
                const displayPrice = getWatchlistDisplayPrice(item, live);

                const displayChangePct = getWatchlistChange(item, live) ?? undefined;
                const dataWarning = getWatchlistDataWarning(item);

                return (
                  <Fragment key={item.ticker}>
                    {/* Main row - wrapped in SortableRow for drag-and-drop */}
                    <SortableRow ticker={item.ticker} disabled={!reorderEnabled}>
                      <td className="px-3 py-2.5 relative group cursor-pointer hover:bg-surface-muted transition-colors" onClick={() => safeToggleExpand(item.ticker)} onKeyDown={event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); safeToggleExpand(item.ticker); } }} tabIndex={0} role="button" aria-expanded={isExpanded} aria-controls={`${item.ticker}-details`}>
                        <div className="flex flex-col">
                          <span className="font-bold text-primary text-sm">{item.ticker}</span>
                          <span className="text-muted text-xs truncate max-w-[120px]">
                            {item.company_name || "Unknown Company"}
                          </span>
                          {dataWarning && (
                            <span role="status" className="mt-1 max-w-[150px] whitespace-normal text-[10px] font-medium text-warning" title={dataWarning}>
                              {dataWarning}
                            </span>
                          )}
                        </div>
                        <TickerTooltip item={item} />
                      </td>
                      <td className={`px-3 py-2.5 text-right transition-colors duration-1000 ${
                        displayChangePct != null && displayChangePct > 0 ? 'text-positive'
                          : displayChangePct != null && displayChangePct < 0 ? 'text-negative'
                          : 'text-primary'
                      } ${
                        priceFlash[item.ticker] === 'up'
                          ? 'bg-positive-soft'
                          : priceFlash[item.ticker] === 'down'
                          ? 'bg-negative-soft'
                          : ''
                      }`} onClick={() => safeToggleExpand(item.ticker)}>
                        {formatWatchlistCurrency(displayPrice)}
                      </td>
                      <td className={`px-3 py-2.5 text-right font-medium ${
                        displayChangePct != null && displayChangePct > 0 ? 'text-positive'
                          : displayChangePct != null && displayChangePct < 0 ? 'text-negative'
                          : 'text-muted'
                      }`} onClick={() => safeToggleExpand(item.ticker)}>
                        {displayChangePct != null ? (displayChangePct > 0 ? '+' : '') + displayChangePct.toFixed(2) + '%' : '—'}
                      </td>
                      {/* Extended-hours column — renders during weekday pre/post-market */}
                      {showAfterHours && (
                        <td className={`px-3 py-2.5 text-right tabular-nums transition-colors duration-1000 ${
                          item.post_market_price != null && item.post_market_price > 0
                            ? postMarketFlash[item.ticker] === 'up'
                              ? 'text-positive font-medium bg-positive-soft'
                              : postMarketFlash[item.ticker] === 'down'
                                ? 'text-negative font-medium bg-negative-soft'
                                : 'text-accent font-medium'
                            : 'text-muted'
                        }`} onClick={() => safeToggleExpand(item.ticker)}>
                          {item.post_market_price != null && item.post_market_price > 0 
                            ? formatWatchlistCurrency(item.post_market_price)
                            : '\u2014'}
                        </td>
                      )}
                      <td className="px-3 py-2.5 text-right text-info dark:text-accent" onClick={() => safeToggleExpand(item.ticker)}>
                        <div className="flex flex-col items-end">
                          <span>{formatMarketSize(item)}</span>
                          <span className="text-[10px] font-medium text-muted dark:text-slate-400">{getMarketSizeLabel(item)}</span>
                        </div>
                      </td>
                    </SortableRow>

                    {/* Expanded detail row */}
                    {isExpanded && (
                      <tr id={`${item.ticker}-details`} key={`${item.ticker}-detail`} className="border-b hover:bg-surface-muted transition-colors">
                        <td colSpan={watchlistColumnCount(showAfterHours)} className="whitespace-normal bg-surface-muted px-6 py-5">
                          <TickerResearchNotes ticker={item.ticker} />
                          {/* Max-width container keeps expanded content within table structure */}
                          <div className="w-full">
                            {/* Header Card with description + action bar */}
                            <div className="mb-4 bg-gradient-to-r from-blue-50 to-indigo-50 rounded-lg px-5 py-4 border border-info-border flex items-start justify-between gap-4 min-w-0">
                              <div className="flex-1 min-w-0 space-y-3 overflow-hidden">
                          {/* Sector & Industry */}
                          {(item.sector || item.industry) && (
                            <div className="flex gap-2 flex-wrap">
                              {item.sector && (
                                <span className="px-3 py-1 bg-info-soft text-info rounded-full text-xs font-semibold">
                                  {item.sector}
                                </span>
                              )}
                              {item.industry && (
                                <span className="px-3 py-1 bg-info-soft text-info rounded-full text-xs font-semibold">
                                  {item.industry}
                                </span>
                              )}
                            </div>
                          )}
                          {/* CEO / Exchange / Employees Row */}
                          {(item.ceo_name || item.exchange || item.full_time_employees) && (
                            <div className="flex items-center gap-3 text-xs text-secondary flex-wrap">
                              {item.ceo_name && (
                                <span className="flex items-center gap-1.5">
                                  <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 text-muted shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                    <path strokeLinecap="round" strokeLinejoin="round" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                                  </svg>
                                  <span className="font-medium">CEO:</span>
                                  <span>{item.ceo_name}</span>
                                </span>
                              )}
                              {item.exchange && (
                                <span className="flex items-center gap-1.5">
                                  <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 text-muted shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                    <path strokeLinecap="round" strokeLinejoin="round" d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m8-14l4 4-4 4m0-4h8" />
                                  </svg>
                                  <span className="font-medium">Exchange:</span>
                                  <span>{item.exchange}</span>
                                </span>
                              )}
                              {item.full_time_employees != null && (
                                <span className="flex items-center gap-1.5">
                                  <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 text-muted shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                    <path strokeLinecap="round" strokeLinejoin="round" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" />
                                  </svg>
                                  <span className="font-medium">Employees:</span>
                                  <span>{formatEmployeeCount(item.full_time_employees)}</span>
                                </span>
                              )}
                            </div>
                          )}
                              {/* Full Description */}
                              {item.long_business_summary && (
                                <p className="text-secondary text-sm leading-relaxed whitespace-pre-line">
                                  {item.long_business_summary}
                                </p>
                              )}
                               {/* Badges: Market Cap Size, Analyst Rec */}
                               <div className="flex gap-2 items-center flex-wrap">
                                 {(() => {
                                   const capInfo = getCompanySize(item);
                                   return (
                                     <>
                                       <span className={`px-2.5 py-1 rounded-full text-xs font-medium ${capInfo.color}`}>
                                         {capInfo.label}
                                       </span>
                                        {hasWatchlistRecommendation(item.recommendation_key) && (
                                          <span className={`px-2.5 py-1 rounded-full text-xs font-medium ${recommendationBadgeClass(item.recommendation_key)}`}>
                                            {formatWatchlistRecommendation(item.recommendation_key)}
                                          </span>
                                        )}
                                      </>
                                    );
                                  })()}
                                </div>
                            </div>
                              {/* Right side buttons */}
                              <div className="flex gap-2 shrink-0 flex-col sm:flex-row">
                               <Link
                                 href={`/news/${item.ticker}`}
                                 onClick={(e) => e.stopPropagation()}
                                 className="inline-flex items-center gap-1.5 px-2.5 py-1.5 bg-action text-white rounded-md text-xs font-medium hover:bg-action-hover transition-colors shadow-sm"
                                 title={`View latest news for ${item.ticker}`}
                               >
                                 <svg xmlns="http://www.w3.org/2000/svg" className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                   <path strokeLinecap="round" strokeLinejoin="round" d="M19 20H5a2 2 0 01-2-2V6a2 2 0 012-2h10a2 2 0 012 2v1m2 13a2 2 0 01-2-2V7m2 13a2 2 0 002-2V9a2 2 0 00-2-2h-2" />
                                 </svg>
                                 <span className="hidden sm:inline">News</span>
                               </Link>
                               <button
                                 onClick={(e) => handleDelete(item.ticker, e)}
                                 className={`inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs font-semibold transition-all duration-300 ${
                                   deletingTicker === item.ticker
                                     ? 'bg-negative-solid text-white scale-95 opacity-0'
                                     : 'bg-negative-soft text-negative hover:bg-negative-soft hover:text-negative border border-negative-border hover:border-negative-border'
                                 }`}
                                 title={`Remove ${item.ticker} from watchlist`}
                               >
                                 <svg xmlns="http://www.w3.org/2000/svg" className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                   <path strokeLinecap="round" strokeLinejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                                 </svg>
                                 <span className="hidden sm:inline">Remove</span>
                               </button>
                             </div>
                          </div>

                          {/* ---- Organized Metrics Sections ---- */}
                          <div className="space-y-4 mt-4">
                            {/* Price & Volume Section */}
                            <div>
                              <h4 className="text-xs font-bold text-secondary uppercase tracking-wider mb-2 flex items-center gap-2">
                                <svg xmlns="http://www.w3.org/2000/svg" className="h-3.5 w-3.5 text-accent" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                  <path strokeLinecap="round" strokeLinejoin="round" d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
                                </svg>
                                Price & Ranges
                              </h4>
                              <div className="grid grid-cols-2 md:grid-cols-5 gap-3 text-xs">
                                <div className="flex flex-col bg-card rounded-lg px-3 py-2.5 border border-divider shadow-sm">
                                  <span className="text-muted font-medium" style={{ fontSize: '10px' }}>Open</span>
                                  <span className="font-semibold text-primary">{formatWatchlistCurrency(liveOpen)}</span>
                                </div>
                                <div className="flex flex-col bg-card rounded-lg px-3 py-2.5 border border-divider shadow-sm">
                                  <span className="text-muted font-medium" style={{ fontSize: '10px' }}>Prev Close</span>
                                  <span className="font-semibold text-primary">{formatWatchlistCurrency(livePreviousClose)}</span>
                                </div>
                                <div className="flex flex-col bg-card rounded-lg px-3 py-2.5 border border-divider shadow-sm">
                                  <span className="text-muted font-medium" style={{ fontSize: '10px' }}>Day Low</span>
                                  <span className="font-semibold text-primary">{formatWatchlistCurrency(liveDayLow)}</span>
                                </div>
                                <div className="flex flex-col bg-card rounded-lg px-3 py-2.5 border border-divider shadow-sm">
                                  <span className="text-muted font-medium" style={{ fontSize: '10px' }}>Day High</span>
                                  <span className="font-semibold text-primary">{formatWatchlistCurrency(liveDayHigh)}</span>
                                </div>
                                <div className="flex flex-col bg-card rounded-lg px-3 py-2.5 border border-divider shadow-sm">
                                  <span className="text-muted font-medium" style={{ fontSize: '10px' }}>52W Range</span>
                                  <span className="font-semibold text-primary">{formatWatchlistRange(item.fifty_two_week_low, item.fifty_two_week_high)}</span>
                                </div>
                              </div>
                            </div>

                            {/* Analyst Targets Section - only for STOCKs with valid targets */}
                            {(item.security_type === 'STOCK' || item.security_type === 'ADR' || !item.security_type) && (item.target_mean_price != null || item.target_median_price != null || item.target_high_price != null || item.target_low_price != null) ? (
                            <div>
                              <h4 className="text-xs font-bold text-secondary uppercase tracking-wider mb-2 flex items-center gap-2">
                                <svg xmlns="http://www.w3.org/2000/svg" className="h-3.5 w-3.5 text-positive" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                  <path strokeLinecap="round" strokeLinejoin="round" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                                </svg>
                                Analyst Price Targets
                                {item.number_of_analysts != null && item.number_of_analysts > 0 && (
                                  <span className="text-muted font-normal normal-case ml-1">({item.number_of_analysts} analysts)</span>
                                )}
                              </h4>
                              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
                                <div className="flex flex-col bg-card rounded-lg px-3 py-2.5 border border-positive-border shadow-sm">
                                  <span className="text-positive font-medium" style={{ fontSize: '10px' }}>▲ High Target</span>
                                  <span className={`font-semibold ${item.target_high_price != null ? 'text-positive' : 'text-muted'}`}>
                                    {formatWatchlistCurrency(item.target_high_price)}
                                  </span>
                                </div>
                                <div className="flex flex-col bg-card rounded-lg px-3 py-2.5 border border-info-border shadow-sm">
                                  <span className="text-accent font-medium" style={{ fontSize: '10px' }}>◆ Mean Target</span>
                                  <span className={`font-semibold ${
                                    item.target_mean_price != null && displayPrice != null && displayPrice > 0
                                      ? (item.target_mean_price > displayPrice ? 'text-positive' : item.target_mean_price < displayPrice ? 'text-negative' : 'text-muted')
                                      : 'text-muted'
                                  }`}>
                                    {formatWatchlistCurrency(item.target_mean_price)}
                                  </span>
                                </div>
                                <div className="flex flex-col bg-card rounded-lg px-3 py-2.5 border border-info-border shadow-sm">
                                  <span className="text-accent font-medium" style={{ fontSize: '10px' }}>◆ Median Target</span>
                                  <span className={`font-semibold ${
                                    item.target_median_price != null && displayPrice != null && displayPrice > 0
                                      ? (item.target_median_price > displayPrice ? 'text-positive' : item.target_median_price < displayPrice ? 'text-negative' : 'text-muted')
                                      : 'text-muted'
                                  }`}>
                                    {formatWatchlistCurrency(item.target_median_price)}
                                  </span>
                                </div>
                                <div className="flex flex-col bg-card rounded-lg px-3 py-2.5 border border-negative-border shadow-sm">
                                  <span className="text-negative font-medium" style={{ fontSize: '10px' }}>▼ Low Target</span>
                                  <span className={`font-semibold ${item.target_low_price != null ? 'text-negative' : 'text-muted'}`}>
                                    {formatWatchlistCurrency(item.target_low_price)}
                                  </span>
                                </div>
                              </div>
                            </div>
                            ) : null}

                            {/* Share Structure Section - only for STOCKs with meaningful data */}
                            {(item.security_type === 'STOCK' || item.security_type === 'ADR' || !item.security_type) && (
                            <div>
                              <h4 className="text-xs font-bold text-secondary uppercase tracking-wider mb-2 flex items-center gap-2">
                                <svg xmlns="http://www.w3.org/2000/svg" className="h-3.5 w-3.5 text-accent" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                  <path strokeLinecap="round" strokeLinejoin="round" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z" />
                                </svg>
                                Share Structure & Ownership
                              </h4>
                              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
                                <div className="flex flex-col bg-card rounded-lg px-3 py-2.5 border border-divider shadow-sm">
                                  <span className="text-muted font-medium" style={{ fontSize: '10px' }}>Shares Outstanding</span>
                                  <span className="font-semibold text-primary">{formatShares(item.shares_outstanding)}</span>
                                </div>
                                <div className="flex flex-col bg-card rounded-lg px-3 py-2.5 border border-divider shadow-sm">
                                  <span className="text-muted font-medium" style={{ fontSize: '10px' }}>Float Shares</span>
                                  <span className="font-semibold text-primary">{formatShares(item.float_shares)}</span>
                                </div>
                                <div className="flex flex-col bg-card rounded-lg px-3 py-2.5 border border-divider shadow-sm">
                                  <span className="text-muted font-medium" style={{ fontSize: '10px' }}>Insider Ownership</span>
                                  <span className="font-semibold text-primary">{formatWatchlistPercent(item.insider_percent)}</span>
                                </div>
                                <div className="flex flex-col bg-card rounded-lg px-3 py-2.5 border border-divider shadow-sm">
                                  <span className="text-muted font-medium" style={{ fontSize: '10px' }}>Institution Ownership</span>
                                  <span className="font-semibold text-primary">{formatWatchlistPercent(item.institution_percent)}</span>
                                </div>
                              </div>
                            </div>
                            )}

                            {/* ETF-Specific Data Section - only for ETFs */}
                            {item.security_type === 'ETF' && item.etf_data && (
                            <div>
                              <h4 className="text-xs font-bold text-secondary uppercase tracking-wider mb-2 flex items-center gap-2">
                                <svg xmlns="http://www.w3.org/2000/svg" className="h-3.5 w-3.5 text-cyan-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                  <path strokeLinecap="round" strokeLinejoin="round" d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m8-14l4 4-4 4m0-4h8" />
                                </svg>
                                ETF Fund Details
                              </h4>
                              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
                                {item.etf_data.fund_family && (
                                  <div className="flex flex-col bg-card rounded-lg px-3 py-2.5 border border-cyan-200 shadow-sm">
                                    <span className="text-muted font-medium" style={{ fontSize: '10px' }}>Fund Family</span>
                                    <span className="font-semibold text-primary truncate">{item.etf_data.fund_family}</span>
                                  </div>
                                )}
                                {item.etf_data.expense_ratio != null && (
                                  <div className="flex flex-col bg-card rounded-lg px-3 py-2.5 border border-cyan-200 shadow-sm">
                                    <span className="text-muted font-medium" style={{ fontSize: '10px' }}>Expense Ratio</span>
                                    <span className="font-semibold text-primary">{formatExpenseRatio(item.etf_data.expense_ratio)}</span>
                                  </div>
                                )}
                                {item.etf_data.net_assets != null && (
                                  <div className="flex flex-col bg-card rounded-lg px-3 py-2.5 border border-cyan-200 shadow-sm">
                                    <span className="text-muted font-medium" style={{ fontSize: '10px' }}>Net Assets (AUM)</span>
                                    <span className="font-semibold text-primary">{formatAUM(item.etf_data.net_assets)}</span>
                                  </div>
                                )}
                                {item.etf_data.inception_date && (
                                  <div className="flex flex-col bg-card rounded-lg px-3 py-2.5 border border-cyan-200 shadow-sm">
                                    <span className="text-muted font-medium" style={{ fontSize: '10px' }}>Inception Date</span>
                                    <span className="font-semibold text-primary">{item.etf_data.inception_date}</span>
                                  </div>
                                )}
                                {item.etf_data.dividend_yield != null && (
                                  <div className="flex flex-col bg-card rounded-lg px-3 py-2.5 border border-cyan-200 shadow-sm">
                                    <span className="text-muted font-medium" style={{ fontSize: '10px' }}>Dividend Yield</span>
                                    <span className="font-semibold text-primary">{safePercent(item.etf_data.dividend_yield)}</span>
                                  </div>
                                )}
                                {item.etf_data.distribution_frequency && (
                                  <div className="flex flex-col bg-card rounded-lg px-3 py-2.5 border border-cyan-200 shadow-sm">
                                    <span className="text-muted font-medium" style={{ fontSize: '10px' }}>Distribution Freq</span>
                                    <span className="font-semibold text-primary">{item.etf_data.distribution_frequency}</span>
                                  </div>
                                )}
                                {item.etf_data.index_tracked && (
                                  <div className="flex flex-col bg-card rounded-lg px-3 py-2.5 border border-cyan-200 shadow-sm">
                                    <span className="text-muted font-medium" style={{ fontSize: '10px' }}>Index Tracked</span>
                                    <span className="font-semibold text-primary truncate">{item.etf_data.index_tracked}</span>
                                  </div>
                                )}
                                {item.etf_data.category && (
                                  <div className="flex flex-col bg-card rounded-lg px-3 py-2.5 border border-cyan-200 shadow-sm">
                                    <span className="text-muted font-medium" style={{ fontSize: '10px' }}>Fund Category</span>
                                    <span className="font-semibold text-primary">{item.etf_data.category}</span>
                                  </div>
                                )}
                                {item.etf_data.holdings_count != null && (
                                  <div className="flex flex-col bg-card rounded-lg px-3 py-2.5 border border-cyan-200 shadow-sm">
                                    <span className="text-muted font-medium" style={{ fontSize: '10px' }}>Holdings Count</span>
                                    <span className="font-semibold text-primary">{item.etf_data.holdings_count}</span>
                                  </div>
                                )}
                              </div>

                              {/* Top Holdings sub-section */}
                              {item.etf_data.top_holdings && item.etf_data.top_holdings.length > 0 && (
                                <div className="mt-3">
                                  <h5 className="text-xs font-bold text-secondary uppercase tracking-wider mb-2">Top Holdings</h5>
                                  <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-xs">
                                    {item.etf_data.top_holdings.map((h, idx) => (
                                      <div key={idx} className="flex items-center justify-between bg-card rounded-lg px-3 py-2 border border-divider shadow-sm">
                                        <span className="text-primary font-medium truncate">{h.name || h.ticker || `#${idx + 1}`}</span>
                                        <span className="text-muted ml-2 shrink-0">{safePercent(h.weight)}</span>
                                      </div>
                                    ))}
                                  </div>
                                </div>
                              )}

                              {/* Sector Allocation sub-section */}
                              {item.etf_data.sector_allocation && item.etf_data.sector_allocation.length > 0 && (
                                <div className="mt-3">
                                  <h5 className="text-xs font-bold text-secondary uppercase tracking-wider mb-2">Sector Allocation</h5>
                                  <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-xs">
                                    {item.etf_data.sector_allocation.map((s, idx) => (
                                      <div key={idx} className="flex items-center justify-between bg-card rounded-lg px-3 py-2 border border-divider shadow-sm">
                                        <span className="text-primary font-medium">{s.sector}</span>
                                        <span className="text-muted ml-2 shrink-0">{safePercent(s.weight)}</span>
                                      </div>
                                    ))}
                                  </div>
                                </div>
                              )}
                            </div>
                            )}

                            {/* Risk Profile Section - show for all types */}
                            <div>
                              <h4 className="text-xs font-bold text-secondary uppercase tracking-wider mb-2 flex items-center gap-2">
                                <svg xmlns="http://www.w3.org/2000/svg" className="h-3.5 w-3.5 text-warning" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                                </svg>
                                Risk Profile
                              </h4>
                              <div className="grid grid-cols-2 md:grid-cols-3 gap-3 text-xs">
                                <div className="flex flex-col bg-card rounded-lg px-3 py-2.5 border border-divider shadow-sm">
                                  <span className="text-muted font-medium" style={{ fontSize: '10px' }}>Beta</span>
                                  <span className="font-semibold text-primary">{formatWatchlistNumber(item.beta)}</span>
                                </div>
                                <div className="flex flex-col bg-card rounded-lg px-3 py-2.5 border border-divider shadow-sm">
                                  <span className="text-muted font-medium" style={{ fontSize: '10px' }}>Short % of Float</span>
                                  <span className="font-semibold text-primary">{formatWatchlistPercent(item.short_percent_of_float, item.security_type === 'ETF')}</span>
                                </div>
                                <div className="flex flex-col bg-card rounded-lg px-3 py-2.5 border border-divider shadow-sm">
                                  <span className="text-muted font-medium" style={{ fontSize: '10px' }}>Overall Risk</span>
                                  <span className={`font-semibold ${item.overall_risk != null ? riskBadgeClass(item.overall_risk).split(' ').pop() : 'text-muted'}`}>
                                    {item.overall_risk != null ? `${formatWatchlistNumber(item.overall_risk, 1)} / 10` : '—'}
                                  </span>
                                </div>
                              </div>
                            </div>
                          </div>

                          {/* Risk Formula Note */}
                          <div className="mt-3 p-3 bg-warning-soft border border-warning-border rounded-lg">
                            <p className="text-xs text-warning font-medium flex items-start gap-1.5">
                              <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 shrink-0 mt-0.5 text-warning" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                <path strokeLinecap="round" strokeLinejoin="round" d="M13 16h-1v-4h-1m1-4h.01M12 2a10 10 0 100 20 10 10 0 000-20z" />
                              </svg>
                              <span>Risk score formula: 10 × (0.25·β<sub>n</sub> + 0.25·ShortFloat<sub>n</sub> + 0.25·DebtEq<sub>n</sub> + 0.25·Volatility<sub>n</sub>). Each component normalized to [0,1] and capped. This is a heuristic composite score — not a predictive or investment-grade risk model.</span>
                            </p>
                          </div>
                          </div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
                </tbody>
              </table>
            </SortableContext>
          </DndContext>
        </div>
      )}

    </div>
  );
}
