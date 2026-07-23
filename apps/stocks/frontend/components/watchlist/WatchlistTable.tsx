'use client';

// ==============================================================================
// COMPONENT: WatchlistTable - Compact watchlist table with expandable details
// ==============================================================================

import React, { useState, useCallback, useMemo, useRef, Fragment, useEffect } from 'react';
import Link from 'next/link';
import { DndContext, KeyboardSensor, PointerSensor, useSensor, useSensors, DragEndEvent } from '@dnd-kit/core';
import { SortableContext, verticalListSortingStrategy, useSortable, arrayMove, sortableKeyboardCoordinates } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { formatCurrency, formatLargeNumber, formatShares, formatPercent, riskBadgeClass, recommendationBadgeClass, safePercent, formatExpenseRatio, formatAUM } from '@/lib/formatters';
import type { WatchlistItem, LiveQuote } from '@/types/stock';
import TickerTooltip from './TickerTooltip';
import { useExtendedHours } from '@/hooks/useExtendedHours';
import { canReorderWatchlist, getWatchlistChange, presentWatchlist, watchlistColumnCount } from '@/lib/watchlistPresentation';
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
  onRefresh: () => void;
  lastRefreshedAt: Date | null;
  isReordering: boolean;
}

const SortableRow = React.memo(function SortableRow({ ticker, disabled, children }: { ticker: string; disabled: boolean; children: React.ReactNode }) {
  const { attributes, listeners, setNodeRef, transform, transition } = useSortable({ id: ticker, disabled });
  return (
    <tr ref={setNodeRef} style={{ transform: CSS.Transform.toString(transform), transition }}>
      <td {...attributes} {...listeners} className={`px-3 py-2.5 text-gray-400 select-none text-center ${disabled ? 'cursor-not-allowed opacity-40' : 'cursor-grab'}`} aria-label={`Reorder ${ticker}`}>
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
  const { isExtendedHours: showAfterHours } = useExtendedHours();

  const allExpanded = watchlist.length > 0 && expandedTickers.size === watchlist.length;
  const reorderEnabled = canReorderWatchlist(sort, search, direction) && !isReordering;

  useEffect(() => {
    const tickers = new Set(watchlist.map(item => item.ticker));
    setExpandedTickers(prev => new Set([...prev].filter(ticker => tickers.has(ticker))));
  }, [watchlist]);

  const toggleExpand = (ticker: string) => {
    setExpandedTickers(prev => {
      const next = new Set(prev);
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

  // Market cap classification per financial standards
  function marketCapLabel(mc: number): { label: string; color: string } {
    if (mc >= 200_000_000_000) return { label: 'Mega Cap', color: 'bg-purple-100 text-purple-700' };
    if (mc >= 10_000_000_000) return { label: 'Large Cap', color: 'bg-emerald-100 text-emerald-700' };
    if (mc >= 2_000_000_000) return { label: 'Mid Cap', color: 'bg-cyan-100 text-cyan-700' };
    if (mc >= 300_000_000) return { label: 'Small Cap', color: 'bg-orange-100 text-orange-700' };
    if (mc >= 50_000_000) return { label: 'Micro Cap', color: 'bg-yellow-100 text-yellow-700' };
    return { label: 'Nano Cap', color: 'bg-red-100 text-red-700' };
  }

  return (
    <div className="w-full px-6 mt-12">
      {/* Section Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className="flex items-center justify-center w-10 h-10 rounded-xl bg-gradient-to-br from-green-500 to-emerald-600 shadow-md">
            <svg className="w-6 h-6 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
            </svg>
          </div>
          <div>
            <h2 className="text-2xl font-extrabold text-gray-900 dark:text-white">Tickers</h2>
            <span className="text-xs text-gray-500 dark:text-slate-400">Watchlist: {watchlist.length} stock{watchlist.length !== 1 ? 's' : ''}</span>
          </div>
        </div>
        {watchlist.length > 0 && (
          <button
            onClick={toggleExpandAll}
            className="group inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-gradient-to-r from-orange-500 to-orange-600 text-white text-xs font-bold shadow-md hover:from-orange-600 hover:to-orange-700 hover:shadow-lg transition-all duration-300"
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

      <div className="mb-3 flex flex-wrap items-center gap-2 rounded-xl border bg-white p-3 shadow-sm dark:bg-slate-900">
        <input aria-label="Search watchlist" value={search} onChange={event => setSearch(event.target.value)} placeholder="Search ticker or company" className="min-w-48 flex-1 rounded-md border px-3 py-2 text-sm dark:bg-slate-800" />
        <select aria-label="Sort watchlist" value={sort} onChange={event => setSort(event.target.value as WatchlistSort)} className="rounded-md border px-3 py-2 text-sm dark:bg-slate-800">
          <option value="custom">Custom order</option><option value="ticker">Ticker</option><option value="change">Price change</option><option value="market-cap">Market cap</option>
        </select>
        <select aria-label="Filter watchlist movers" value={direction} onChange={event => setDirection(event.target.value as WatchlistDirectionFilter)} className="rounded-md border px-3 py-2 text-sm dark:bg-slate-800">
          <option value="all">All</option><option value="gainers">Gainers</option><option value="losers">Losers</option>
        </select>
        <span className="text-xs text-gray-500">{orderedWatchlist.length} of {watchlist.length}</span>
        <button type="button" onClick={onRefresh} disabled={loading} className="rounded-md border px-3 py-2 text-xs font-semibold disabled:opacity-50">{loading ? 'Refreshing…' : 'Refresh'}</button>
        <span className="text-xs text-gray-400">{lastRefreshedAt ? `Updated ${lastRefreshedAt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}` : 'Not refreshed'}</span>
        {!reorderEnabled && <span className="w-full text-xs text-amber-600">Clear filters and select Custom order to drag.</span>}
      </div>

      {loading ? (
        /* Skeleton loader: renders a table-shaped skeleton with 4 pulsing rows */
        <div className="bg-white rounded-xl shadow-sm border overflow-hidden">
          <table className="w-full text-sm whitespace-nowrap">
            <thead className="bg-gray-100 border-b">
              <tr>
                <th className="px-2 py-2.5 text-center font-semibold text-gray-700 w-8"></th>
                <th className="px-2 py-2.5 text-left font-semibold text-gray-700 min-w-0">Ticker / Company</th>
                <th className="px-2 py-2.5 text-right font-semibold text-gray-700 tabular-nums">Current Price</th>
                <th className="px-2 py-2.5 text-right font-semibold text-gray-700 tabular-nums">Change %</th>
                <th className="px-2 py-2.5 text-right font-semibold text-gray-700 tabular-nums">Market Cap</th>
              </tr>
            </thead>
            <tbody>
              {[...Array(4)].map((_, i) => (
                <tr key={i} className="border-b last:border-0">
                  <td className="px-3 py-2.5"><div className="h-4 w-4 bg-gray-200 rounded animate-pulse" /></td>
                  <td className="px-3 py-2.5">
                    <div className="flex flex-col gap-1">
                      <div className="h-4 w-16 bg-gray-200 rounded animate-pulse" />
                      <div className="h-3 w-32 bg-gray-100 rounded animate-pulse" style={{ animationDelay: '100ms' }} />
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
        <div className="w-full overflow-x-auto bg-white rounded-xl shadow-sm border">
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
                <thead className="bg-gray-100 border-b">
                  <tr>
                    <th className="px-3 py-2.5 text-center font-semibold text-gray-700 w-8" title="Drag to reorder"></th>
                    <th className="px-3 py-2.5 text-left font-semibold text-gray-700">Ticker / Company</th>
                    <th className="px-3 py-2.5 text-right font-semibold text-gray-700 tabular-nums">Current Price</th>
                     <th className="px-3 py-2.5 text-right font-semibold text-gray-700 tabular-nums">Change %</th>
                     {showAfterHours && (
                       <th className="px-3 py-2.5 text-right font-semibold text-gray-700 tabular-nums" title="Extended-hours price (pre-market and after-hours ET)">After Hours</th>
                     )}
                     <th className="px-3 py-2.5 text-right font-semibold text-gray-700 tabular-nums">Market Cap</th>
                   </tr>
                 </thead>
                 <tbody>
                   {orderedWatchlist.map((item) => {
                const live = livePrices[item.ticker];
                const isExpanded = expandedTickers.has(item.ticker);

                // Use live price if available, fall back to static fundamental data
                const displayPrice = live?.price ?? item.current_price;

                const displayChangePct = getWatchlistChange(item, live) ?? undefined;

                return (
                  <Fragment key={item.ticker}>
                    {/* Main row - wrapped in SortableRow for drag-and-drop */}
                    <SortableRow ticker={item.ticker} disabled={!reorderEnabled}>
                      <td className="px-3 py-2.5 relative group cursor-pointer hover:bg-gray-50 transition-colors" onClick={() => safeToggleExpand(item.ticker)} onKeyDown={event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); safeToggleExpand(item.ticker); } }} tabIndex={0} role="button" aria-expanded={isExpanded} aria-controls={`${item.ticker}-details`}>
                        <div className="flex flex-col">
                          <span className="font-bold text-gray-900 text-sm">{item.ticker}</span>
                          <span className="text-gray-500 text-xs truncate max-w-[120px]">
                            {item.company_name || "Unknown Company"}
                          </span>
                        </div>
                        <TickerTooltip item={item} />
                      </td>
                      <td className={`px-3 py-2.5 text-right transition-colors duration-1000 ${
                        displayChangePct != null && displayChangePct > 0 ? 'text-green-600'
                          : displayChangePct != null && displayChangePct < 0 ? 'text-red-600'
                          : 'text-gray-900'
                      } ${
                        priceFlash[item.ticker] === 'up'
                          ? 'bg-green-200'
                          : priceFlash[item.ticker] === 'down'
                          ? 'bg-red-200'
                          : ''
                      }`} onClick={() => safeToggleExpand(item.ticker)}>
                        {formatCurrency(displayPrice)}
                      </td>
                      <td className={`px-3 py-2.5 text-right font-medium ${
                        displayChangePct != null && displayChangePct > 0 ? 'text-green-600'
                          : displayChangePct != null && displayChangePct < 0 ? 'text-red-600'
                          : 'text-gray-500'
                      }`} onClick={() => safeToggleExpand(item.ticker)}>
                        {displayChangePct != null ? (displayChangePct > 0 ? '+' : '') + displayChangePct.toFixed(2) + '%' : 'N/A'}
                      </td>
                      {/* Extended-hours column — renders during weekday pre/post-market */}
                      {showAfterHours && (
                        <td className={`px-3 py-2.5 text-right tabular-nums transition-colors duration-1000 ${
                          item.post_market_price != null && item.post_market_price > 0
                            ? postMarketFlash[item.ticker] === 'up'
                              ? 'text-green-600 font-medium bg-green-200'
                              : postMarketFlash[item.ticker] === 'down'
                                ? 'text-red-600 font-medium bg-red-200'
                                : 'text-blue-600 font-medium'
                            : 'text-gray-400'
                        }`} onClick={() => safeToggleExpand(item.ticker)}>
                          {item.post_market_price != null && item.post_market_price > 0 
                            ? formatCurrency(item.post_market_price)
                            : '\u2014'}
                        </td>
                      )}
                      <td className="px-3 py-2.5 text-right text-blue-800 dark:text-blue-300" onClick={() => safeToggleExpand(item.ticker)}>{formatLargeNumber(item.market_cap)}</td>
                    </SortableRow>

                    {/* Expanded detail row */}
                    {isExpanded && (
                      <tr id={`${item.ticker}-details`} key={`${item.ticker}-detail`} className="border-b hover:bg-gray-50 transition-colors">
                        <td colSpan={watchlistColumnCount(showAfterHours)} className="bg-gray-50 px-6 py-5">
                          {/* Max-width container keeps expanded content within table structure */}
                          <div className="w-full">
                            {/* Header Card with description + action bar */}
                            <div className="mb-4 bg-gradient-to-r from-blue-50 to-indigo-50 rounded-lg px-5 py-4 border border-blue-200 flex items-start justify-between gap-4 min-w-0">
                              <div className="flex-1 min-w-0 space-y-3 overflow-hidden">
                          {/* Sector & Industry */}
                          {(item.sector || item.industry) && (
                            <div className="flex gap-2 flex-wrap">
                              {item.sector && (
                                <span className="px-3 py-1 bg-blue-100 text-blue-700 rounded-full text-xs font-semibold">
                                  {item.sector}
                                </span>
                              )}
                              {item.industry && (
                                <span className="px-3 py-1 bg-indigo-100 text-indigo-700 rounded-full text-xs font-semibold">
                                  {item.industry}
                                </span>
                              )}
                            </div>
                          )}
                          {/* CEO / Exchange / Employees Row */}
                          {(item.ceo_name || item.exchange || item.full_time_employees) && (
                            <div className="flex items-center gap-3 text-xs text-gray-600 flex-wrap">
                              {item.ceo_name && (
                                <span className="flex items-center gap-1.5">
                                  <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 text-gray-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                    <path strokeLinecap="round" strokeLinejoin="round" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                                  </svg>
                                  <span className="font-medium">CEO:</span>
                                  <span>{item.ceo_name}</span>
                                </span>
                              )}
                              {item.exchange && (
                                <span className="flex items-center gap-1.5">
                                  <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 text-gray-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                    <path strokeLinecap="round" strokeLinejoin="round" d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m8-14l4 4-4 4m0-4h8" />
                                  </svg>
                                  <span className="font-medium">Exchange:</span>
                                  <span>{item.exchange}</span>
                                </span>
                              )}
                              {item.full_time_employees != null && (
                                <span className="flex items-center gap-1.5">
                                  <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 text-gray-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                    <path strokeLinecap="round" strokeLinejoin="round" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" />
                                  </svg>
                                  <span className="font-medium">Employees:</span>
                                  <span>{formatLargeNumber(item.full_time_employees)}</span>
                                </span>
                              )}
                            </div>
                          )}
                              {/* Full Description */}
                              {item.long_business_summary && (
                                <p className="text-gray-600 text-sm leading-relaxed whitespace-pre-line">
                                  {item.long_business_summary}
                                </p>
                              )}
                               {/* Badges: Market Cap Size, Analyst Rec */}
                               <div className="flex gap-2 items-center flex-wrap">
                                 {(() => {
                                   const capInfo = marketCapLabel(item.market_cap);
                                   return (
                                     <>
                                       <span className={`px-2.5 py-1 rounded-full text-xs font-medium ${capInfo.color}`}>
                                         {capInfo.label}
                                       </span>
                                        <span className={`px-2.5 py-1 rounded-full text-xs font-medium ${recommendationBadgeClass(item.recommendation_key)}`}>
                                          {item.recommendation_key.replace('_', ' ').toUpperCase()}
                                        </span>
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
                                 className="inline-flex items-center gap-1.5 px-2.5 py-1.5 bg-blue-600 text-white rounded-md text-xs font-medium hover:bg-blue-700 transition-colors shadow-sm"
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
                                     ? 'bg-red-600 text-white scale-95 opacity-0'
                                     : 'bg-red-50 text-red-600 hover:bg-red-100 hover:text-red-700 border border-red-200 hover:border-red-300'
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
                              <h4 className="text-xs font-bold text-gray-700 uppercase tracking-wider mb-2 flex items-center gap-2">
                                <svg xmlns="http://www.w3.org/2000/svg" className="h-3.5 w-3.5 text-blue-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                  <path strokeLinecap="round" strokeLinejoin="round" d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
                                </svg>
                                Price & Ranges
                              </h4>
                              <div className="grid grid-cols-2 md:grid-cols-5 gap-3 text-xs">
                                <div className="flex flex-col bg-white rounded-lg px-3 py-2.5 border border-gray-200 shadow-sm">
                                  <span className="text-gray-500 font-medium" style={{ fontSize: '10px' }}>Open</span>
                                  <span className="font-semibold text-gray-900">{formatCurrency(item.open_price)}</span>
                                </div>
                                <div className="flex flex-col bg-white rounded-lg px-3 py-2.5 border border-gray-200 shadow-sm">
                                  <span className="text-gray-500 font-medium" style={{ fontSize: '10px' }}>Prev Close</span>
                                  <span className="font-semibold text-gray-900">{formatCurrency(item.previous_close)}</span>
                                </div>
                                <div className="flex flex-col bg-white rounded-lg px-3 py-2.5 border border-gray-200 shadow-sm">
                                  <span className="text-gray-500 font-medium" style={{ fontSize: '10px' }}>Day Low</span>
                                  <span className="font-semibold text-gray-900">{formatCurrency(item.day_low)}</span>
                                </div>
                                <div className="flex flex-col bg-white rounded-lg px-3 py-2.5 border border-gray-200 shadow-sm">
                                  <span className="text-gray-500 font-medium" style={{ fontSize: '10px' }}>Day High</span>
                                  <span className="font-semibold text-gray-900">{formatCurrency(item.day_high)}</span>
                                </div>
                                <div className="flex flex-col bg-white rounded-lg px-3 py-2.5 border border-gray-200 shadow-sm">
                                  <span className="text-gray-500 font-medium" style={{ fontSize: '10px' }}>52W Range</span>
                                  <span className="font-semibold text-gray-900">{formatCurrency(item.fifty_two_week_low)} - {formatCurrency(item.fifty_two_week_high)}</span>
                                </div>
                              </div>
                            </div>

                            {/* Analyst Targets Section - only for STOCKs with valid targets */}
                            {(item.security_type === 'STOCK' || item.security_type === 'ADR' || !item.security_type) && (item.target_mean_price != null || item.target_median_price != null || item.target_high_price != null || item.target_low_price != null) ? (
                            <div>
                              <h4 className="text-xs font-bold text-gray-700 uppercase tracking-wider mb-2 flex items-center gap-2">
                                <svg xmlns="http://www.w3.org/2000/svg" className="h-3.5 w-3.5 text-emerald-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                  <path strokeLinecap="round" strokeLinejoin="round" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                                </svg>
                                Analyst Price Targets
                                {item.number_of_analysts != null && item.number_of_analysts > 0 && (
                                  <span className="text-gray-400 font-normal normal-case ml-1">({item.number_of_analysts} analysts)</span>
                                )}
                              </h4>
                              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
                                <div className="flex flex-col bg-white rounded-lg px-3 py-2.5 border border-green-200 shadow-sm">
                                  <span className="text-green-600 font-medium" style={{ fontSize: '10px' }}>▲ High Target</span>
                                  <span className={`font-semibold ${item.target_high_price != null ? 'text-green-700' : 'text-gray-400'}`}>
                                    {item.target_high_price ? formatCurrency(item.target_high_price) : 'N/A'}
                                  </span>
                                </div>
                                <div className="flex flex-col bg-white rounded-lg px-3 py-2.5 border border-blue-200 shadow-sm">
                                  <span className="text-blue-600 font-medium" style={{ fontSize: '10px' }}>◆ Mean Target</span>
                                  <span className={`font-semibold ${
                                    item.target_mean_price != null && displayPrice > 0
                                      ? (item.target_mean_price > displayPrice ? 'text-green-600' : item.target_mean_price < displayPrice ? 'text-red-600' : 'text-gray-500')
                                      : 'text-gray-400'
                                  }`}>
                                    {item.target_mean_price ? formatCurrency(item.target_mean_price) : 'N/A'}
                                  </span>
                                </div>
                                <div className="flex flex-col bg-white rounded-lg px-3 py-2.5 border border-blue-200 shadow-sm">
                                  <span className="text-blue-600 font-medium" style={{ fontSize: '10px' }}>◆ Median Target</span>
                                  <span className={`font-semibold ${
                                    item.target_median_price != null && displayPrice > 0
                                      ? (item.target_median_price > displayPrice ? 'text-green-600' : item.target_median_price < displayPrice ? 'text-red-600' : 'text-gray-500')
                                      : 'text-gray-400'
                                  }`}>
                                    {item.target_median_price ? formatCurrency(item.target_median_price) : 'N/A'}
                                  </span>
                                </div>
                                <div className="flex flex-col bg-white rounded-lg px-3 py-2.5 border border-red-200 shadow-sm">
                                  <span className="text-red-600 font-medium" style={{ fontSize: '10px' }}>▼ Low Target</span>
                                  <span className={`font-semibold ${item.target_low_price != null ? 'text-red-700' : 'text-gray-400'}`}>
                                    {item.target_low_price ? formatCurrency(item.target_low_price) : 'N/A'}
                                  </span>
                                </div>
                              </div>
                            </div>
                            ) : null}

                            {/* Share Structure Section - only for STOCKs with meaningful data */}
                            {(item.security_type === 'STOCK' || item.security_type === 'ADR' || !item.security_type) && (
                            <div>
                              <h4 className="text-xs font-bold text-gray-700 uppercase tracking-wider mb-2 flex items-center gap-2">
                                <svg xmlns="http://www.w3.org/2000/svg" className="h-3.5 w-3.5 text-purple-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                  <path strokeLinecap="round" strokeLinejoin="round" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z" />
                                </svg>
                                Share Structure & Ownership
                              </h4>
                              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
                                <div className="flex flex-col bg-white rounded-lg px-3 py-2.5 border border-gray-200 shadow-sm">
                                  <span className="text-gray-500 font-medium" style={{ fontSize: '10px' }}>Shares Outstanding</span>
                                  <span className="font-semibold text-gray-900">{formatShares(item.shares_outstanding)}</span>
                                </div>
                                <div className="flex flex-col bg-white rounded-lg px-3 py-2.5 border border-gray-200 shadow-sm">
                                  <span className="text-gray-500 font-medium" style={{ fontSize: '10px' }}>Float Shares</span>
                                  <span className="font-semibold text-gray-900">{formatShares(item.float_shares)}</span>
                                </div>
                                <div className="flex flex-col bg-white rounded-lg px-3 py-2.5 border border-gray-200 shadow-sm">
                                  <span className="text-gray-500 font-medium" style={{ fontSize: '10px' }}>Insider Ownership</span>
                                  <span className="font-semibold text-gray-900">{formatPercent(item.insider_percent)}</span>
                                </div>
                                <div className="flex flex-col bg-white rounded-lg px-3 py-2.5 border border-gray-200 shadow-sm">
                                  <span className="text-gray-500 font-medium" style={{ fontSize: '10px' }}>Institution Ownership</span>
                                  <span className="font-semibold text-gray-900">{formatPercent(item.institution_percent)}</span>
                                </div>
                              </div>
                            </div>
                            )}

                            {/* ETF-Specific Data Section - only for ETFs */}
                            {item.security_type === 'ETF' && item.etf_data && (
                            <div>
                              <h4 className="text-xs font-bold text-gray-700 uppercase tracking-wider mb-2 flex items-center gap-2">
                                <svg xmlns="http://www.w3.org/2000/svg" className="h-3.5 w-3.5 text-cyan-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                  <path strokeLinecap="round" strokeLinejoin="round" d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m8-14l4 4-4 4m0-4h8" />
                                </svg>
                                ETF Fund Details
                              </h4>
                              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
                                {item.etf_data.fund_family && (
                                  <div className="flex flex-col bg-white rounded-lg px-3 py-2.5 border border-cyan-200 shadow-sm">
                                    <span className="text-gray-500 font-medium" style={{ fontSize: '10px' }}>Fund Family</span>
                                    <span className="font-semibold text-gray-900 truncate">{item.etf_data.fund_family}</span>
                                  </div>
                                )}
                                {item.etf_data.expense_ratio != null && (
                                  <div className="flex flex-col bg-white rounded-lg px-3 py-2.5 border border-cyan-200 shadow-sm">
                                    <span className="text-gray-500 font-medium" style={{ fontSize: '10px' }}>Expense Ratio</span>
                                    <span className="font-semibold text-gray-900">{formatExpenseRatio(item.etf_data.expense_ratio)}</span>
                                  </div>
                                )}
                                {item.etf_data.net_assets != null && (
                                  <div className="flex flex-col bg-white rounded-lg px-3 py-2.5 border border-cyan-200 shadow-sm">
                                    <span className="text-gray-500 font-medium" style={{ fontSize: '10px' }}>Net Assets (AUM)</span>
                                    <span className="font-semibold text-gray-900">{formatAUM(item.etf_data.net_assets)}</span>
                                  </div>
                                )}
                                {item.etf_data.inception_date && (
                                  <div className="flex flex-col bg-white rounded-lg px-3 py-2.5 border border-cyan-200 shadow-sm">
                                    <span className="text-gray-500 font-medium" style={{ fontSize: '10px' }}>Inception Date</span>
                                    <span className="font-semibold text-gray-900">{item.etf_data.inception_date}</span>
                                  </div>
                                )}
                                {item.etf_data.dividend_yield != null && (
                                  <div className="flex flex-col bg-white rounded-lg px-3 py-2.5 border border-cyan-200 shadow-sm">
                                    <span className="text-gray-500 font-medium" style={{ fontSize: '10px' }}>Dividend Yield</span>
                                    <span className="font-semibold text-gray-900">{safePercent(item.etf_data.dividend_yield)}</span>
                                  </div>
                                )}
                                {item.etf_data.distribution_frequency && (
                                  <div className="flex flex-col bg-white rounded-lg px-3 py-2.5 border border-cyan-200 shadow-sm">
                                    <span className="text-gray-500 font-medium" style={{ fontSize: '10px' }}>Distribution Freq</span>
                                    <span className="font-semibold text-gray-900">{item.etf_data.distribution_frequency}</span>
                                  </div>
                                )}
                                {item.etf_data.index_tracked && (
                                  <div className="flex flex-col bg-white rounded-lg px-3 py-2.5 border border-cyan-200 shadow-sm">
                                    <span className="text-gray-500 font-medium" style={{ fontSize: '10px' }}>Index Tracked</span>
                                    <span className="font-semibold text-gray-900 truncate">{item.etf_data.index_tracked}</span>
                                  </div>
                                )}
                                {item.etf_data.category && (
                                  <div className="flex flex-col bg-white rounded-lg px-3 py-2.5 border border-cyan-200 shadow-sm">
                                    <span className="text-gray-500 font-medium" style={{ fontSize: '10px' }}>Fund Category</span>
                                    <span className="font-semibold text-gray-900">{item.etf_data.category}</span>
                                  </div>
                                )}
                                {item.etf_data.holdings_count != null && (
                                  <div className="flex flex-col bg-white rounded-lg px-3 py-2.5 border border-cyan-200 shadow-sm">
                                    <span className="text-gray-500 font-medium" style={{ fontSize: '10px' }}>Holdings Count</span>
                                    <span className="font-semibold text-gray-900">{item.etf_data.holdings_count}</span>
                                  </div>
                                )}
                              </div>

                              {/* Top Holdings sub-section */}
                              {item.etf_data.top_holdings && item.etf_data.top_holdings.length > 0 && (
                                <div className="mt-3">
                                  <h5 className="text-xs font-bold text-gray-600 uppercase tracking-wider mb-2">Top Holdings</h5>
                                  <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-xs">
                                    {item.etf_data.top_holdings.map((h, idx) => (
                                      <div key={idx} className="flex items-center justify-between bg-white rounded-lg px-3 py-2 border border-gray-200 shadow-sm">
                                        <span className="text-gray-800 font-medium truncate">{h.name || h.ticker || `#${idx + 1}`}</span>
                                        <span className="text-gray-500 ml-2 shrink-0">{safePercent(h.weight)}</span>
                                      </div>
                                    ))}
                                  </div>
                                </div>
                              )}

                              {/* Sector Allocation sub-section */}
                              {item.etf_data.sector_allocation && item.etf_data.sector_allocation.length > 0 && (
                                <div className="mt-3">
                                  <h5 className="text-xs font-bold text-gray-600 uppercase tracking-wider mb-2">Sector Allocation</h5>
                                  <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-xs">
                                    {item.etf_data.sector_allocation.map((s, idx) => (
                                      <div key={idx} className="flex items-center justify-between bg-white rounded-lg px-3 py-2 border border-gray-200 shadow-sm">
                                        <span className="text-gray-800 font-medium">{s.sector}</span>
                                        <span className="text-gray-500 ml-2 shrink-0">{safePercent(s.weight)}</span>
                                      </div>
                                    ))}
                                  </div>
                                </div>
                              )}
                            </div>
                            )}

                            {/* Risk Profile Section - show for all types */}
                            <div>
                              <h4 className="text-xs font-bold text-gray-700 uppercase tracking-wider mb-2 flex items-center gap-2">
                                <svg xmlns="http://www.w3.org/2000/svg" className="h-3.5 w-3.5 text-amber-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                                </svg>
                                Risk Profile
                              </h4>
                              <div className="grid grid-cols-2 md:grid-cols-3 gap-3 text-xs">
                                <div className="flex flex-col bg-white rounded-lg px-3 py-2.5 border border-gray-200 shadow-sm">
                                  <span className="text-gray-500 font-medium" style={{ fontSize: '10px' }}>Beta</span>
                                  <span className="font-semibold text-gray-900">{item.beta.toFixed(2)}</span>
                                </div>
                                <div className="flex flex-col bg-white rounded-lg px-3 py-2.5 border border-gray-200 shadow-sm">
                                  <span className="text-gray-500 font-medium" style={{ fontSize: '10px' }}>Short % of Float</span>
                                  <span className="font-semibold text-gray-900">{formatPercent(item.short_percent_of_float)}</span>
                                </div>
                                <div className="flex flex-col bg-white rounded-lg px-3 py-2.5 border border-gray-200 shadow-sm">
                                  <span className="text-gray-500 font-medium" style={{ fontSize: '10px' }}>Overall Risk</span>
                                  <span className={`font-semibold ${riskBadgeClass(item.overall_risk).replace('bg-*', '').split(' ').pop() || ''}`}>
                                    {item.overall_risk} / 10
                                  </span>
                                </div>
                              </div>
                            </div>
                          </div>

                          {/* Risk Formula Note */}
                          <div className="mt-3 p-3 bg-amber-50 border border-amber-200 rounded-lg">
                            <p className="text-xs text-amber-800 font-medium flex items-start gap-1.5">
                              <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 shrink-0 mt-0.5 text-amber-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
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
