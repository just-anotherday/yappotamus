// ==============================================================================
// COMPONENT: TickerTooltip - Rich investor profile hover card
// ==============================================================================

import { useState, useRef, useEffect } from "react";
import type { WatchlistItem } from "@/types/stock";
import { formatCurrency, formatLargeNumber } from "@/lib/formatters";

interface Props {
  item: WatchlistItem;
}

export default function TickerTooltip({ item }: Props) {
  const [show, setShow] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (timerRef.current) {
        globalThis.clearTimeout(timerRef.current);
      }
    };
  }, []);

  const handleMouseEnter = () => {
    if (timerRef.current) {
      globalThis.clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    setShow(true);
  };

  const handleMouseLeave = () => {
    timerRef.current = setTimeout(() => {
      setShow(false);
    }, 500);
  };

  // Truncate summary to ~180 chars
  const summary = item.long_business_summary
    ? item.long_business_summary.length > 180
      ? item.long_business_summary.slice(0, 180) + "..."
      : item.long_business_summary
    : "No description available.";

  return (
    <div
      className="absolute z-30 left-full ml-3 top-0 pointer-events-none"
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
    >
      <div
        className={`w-[340px] bg-white shadow-2xl rounded-xl border border-gray-200 overflow-hidden transition-all duration-200 pointer-events-auto ${
          show ? "opacity-100 scale-100 visible" : "opacity-0 scale-95 invisible"
        }`}
      >
        {/* Header */}
        <div className="bg-gradient-to-r from-blue-600 to-indigo-600 px-4 py-3">
          <p className="text-white font-bold text-base">{item.ticker}</p>
          <p className="text-blue-100 text-sm truncate">{item.company_name || "Unknown Company"}</p>
        </div>

        {/* Body */}
        <div className="px-4 py-3 space-y-2 text-xs">
          {/* Sector & Industry */}
          {(item.sector || item.industry) && (
            <div className="flex gap-2 flex-wrap">
              {item.sector && (
                <span className="px-2 py-0.5 bg-blue-100 text-blue-700 rounded-full font-medium">
                  {item.sector}
                </span>
              )}
              {item.industry && (
                <span className="px-2 py-0.5 bg-indigo-100 text-indigo-700 rounded-full font-medium">
                  {item.industry}
                </span>
              )}
            </div>
          )}

          {/* Description */}
          <p className="text-gray-600 leading-relaxed">{summary}</p>

          {/* Metrics Grid */}
          <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 pt-1 border-t border-gray-100">
            <span className="text-gray-500 font-medium">Employees</span>
            <span className="text-gray-900 font-semibold text-right">
              {item.full_time_employees != null ? item.full_time_employees.toLocaleString() : "N/A"}
            </span>

            <span className="text-gray-500 font-medium">Market Cap</span>
            <span className="text-gray-900 font-semibold text-right">
              {formatLargeNumber(item.market_cap)}
            </span>

            {item.average_analyst_rating && (
              <>
                <span className="text-gray-500 font-medium">Analyst Rating</span>
                <span className="text-gray-900 font-semibold text-right">{item.average_analyst_rating}</span>
              </>
            )}

            {item.forward_pe != null && (
              <>
                <span className="text-gray-500 font-medium">Forward P/E</span>
                <span className="text-gray-900 font-semibold text-right">{item.forward_pe.toFixed(1)}</span>
              </>
            )}

            {(item.fifty_two_week_low != null && item.fifty_two_week_high != null) && (
              <>
                <span className="text-gray-500 font-medium">52W Range</span>
                <span className="text-gray-900 font-semibold text-right">
                  {formatCurrency(item.fifty_two_week_low)} – {formatCurrency(item.fifty_two_week_high)}
                </span>
              </>
            )}
          </div>

          {/* Website Link */}
          {item.website && (
            <div className="pt-1 border-t border-gray-100">
              <a
                href={item.website}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 text-blue-600 hover:text-blue-800 font-medium transition-colors"
              >
                <span>Website</span>
                <svg xmlns="http://www.w3.org/2000/svg" className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                </svg>
              </a>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
