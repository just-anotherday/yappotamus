// Currency formatting
export const formatCurrency = (val: number) => {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(val);
};

// Large number formatting (market cap, shares)
export const formatLargeNumber = (val: number | null | undefined, currency = 'USD') => {
  if (val == null || val === 0) return 'N/A';
  const prefix = currency === 'USD' ? '$' : `${currency} `;
  if (val >= 1e12) return `${prefix}${(val / 1e12).toFixed(2)}T`;
  if (val >= 1e9) return `${prefix}${(val / 1e9).toFixed(2)}B`;
  if (val >= 1e6) return `${prefix}${(val / 1e6).toFixed(2)}M`;
  return `${prefix}${val.toLocaleString()}`;
};

// Share count formatting
export const formatShares = (val: number | undefined | null) => {
  if (val == null || val === 0) return 'N/A';
  if (val >= 1e9) return `${(val / 1e9).toFixed(2)}B`;
  if (val >= 1e6) return `${(val / 1e6).toFixed(2)}M`;
  if (val >= 1e3) return `${(val / 1e3).toFixed(2)}K`;
  return val.toLocaleString();
};

// Decimal to percentage string
export const formatPercent = (val: number | undefined | null) => {
  if (val == null) return 'N/A';
  return `${(val * 100).toFixed(2)}%`;
};

// Risk score badge class
export const riskBadgeClass = (risk: number) => {
  if (risk <= 3) return 'bg-green-100 text-green-800';
  if (risk <= 5) return 'bg-yellow-100 text-yellow-800';
  return 'bg-red-100 text-red-800';
};

// Analyst recommendation badge class
export const recommendationBadgeClass = (key: string) => {
  if (key.includes('strong_buy')) return 'bg-green-100 text-green-800';
  if (key.includes('buy')) return 'bg-blue-100 text-blue-800';
  if (key.includes('hold')) return 'bg-yellow-100 text-yellow-800';
  if (key.includes('sell')) return 'bg-red-100 text-red-800';
  return 'bg-gray-100 text-gray-800';
};

export const EASTERN_TIME_ZONE = 'America/New_York';
const OFFSETLESS_ISO_DATETIME = /^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d{1,9})?)?$/;

/**
 * Parse an instant returned by the API.
 *
 * Several timestamps are stored as UTC-naive database values, so legacy API
 * responses omit the trailing `Z`. Browsers otherwise interpret those values
 * in the viewer's local time zone and can display them hours in the future.
 */
export function parseApiTimestamp(dateStr: string | null | undefined): Date | null {
  if (!dateStr) return null;

  const trimmed = dateStr.trim();
  if (!trimmed) return null;

  const normalized = OFFSETLESS_ISO_DATETIME.test(trimmed)
    ? `${trimmed.replace(' ', 'T')}Z`
    : trimmed;
  const date = new Date(normalized);

  return Number.isNaN(date.getTime()) ? null : date;
}

/** Format an API instant deterministically in the application's Eastern zone. */
export function formatApiTimestamp(
  dateStr: string | null | undefined,
  options: Intl.DateTimeFormatOptions,
  fallback = '',
): string {
  const date = parseApiTimestamp(dateStr);
  if (!date) return dateStr?.trim() ? dateStr : fallback;

  return new Intl.DateTimeFormat('en-US', {
    ...options,
    timeZone: EASTERN_TIME_ZONE,
  }).format(date);
}

function easternDateKey(date: Date): string {
  const parts = new Intl.DateTimeFormat('en-US', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    timeZone: EASTERN_TIME_ZONE,
  }).formatToParts(date);
  const values = Object.fromEntries(parts.map(({ type, value }) => [type, value]));
  return `${values.year}-${values.month}-${values.day}`;
}

/** Group an API instant by Eastern calendar day, including DST boundaries. */
export function easternDayLabel(
  dateStr: string | null | undefined,
  nowMs: number = Date.now(),
): string {
  const date = parseApiTimestamp(dateStr);
  if (!date) return 'No Date';

  const articleKey = easternDateKey(date);
  const todayKey = easternDateKey(new Date(nowMs));
  if (articleKey === todayKey) return 'Today';

  const [year, month, day] = todayKey.split('-').map(Number);
  const yesterday = new Date(Date.UTC(year, month - 1, day - 1));
  const yesterdayKey = yesterday.toISOString().slice(0, 10);
  if (articleKey === yesterdayKey) return 'Yesterday';

  return formatApiTimestamp(dateStr, { month: 'short', day: 'numeric' }, 'No Date');
}

// Time-ago formatting
export function timeAgo(
  dateStr: string | null | undefined,
  nowMs: number = Date.now(),
): string {
  const date = parseApiTimestamp(dateStr);
  if (!date) return '';

  // Clock skew or a provider's future timestamp should never render a
  // negative age. Treat it as newly published instead.
  const diffMs = Math.max(0, nowMs - date.getTime());
  const diffMins = Math.floor(diffMs / 60000);
  if (diffMins < 1) return 'Just now';
  if (diffMins < 60) return `${diffMins}m ago`;
  const diffHrs = Math.floor(diffMins / 60);
  if (diffHrs < 24) return `${diffHrs}h ago`;
  const diffDays = Math.floor(diffHrs / 24);
  return `${diffDays}d ago`;
}

// Full date formatting for tooltips/display
export function formatDate(dateStr: string | null | undefined): string {
  return formatApiTimestamp(dateStr, {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: true,
    timeZoneName: 'short',
  }, 'Unknown date');
}

// ==============================================================================
// Data Quality Validation Helpers
// ==============================================================================

/** Check if a value is a placeholder/null/undefined/NaN/zero that should be hidden */
export function isValidValue(val: any, allowZero: boolean = false): boolean {
  if (val == null) return false;
  if (typeof val === 'string' && (val === '' || val === 'N/A' || val === 'null' || val === 'undefined')) return false;
  if (typeof val === 'number' && (isNaN(val) || (!allowZero && val === 0))) return false;
  return true;
}

/** Safely format a percentage, returning 'N/A' for invalid values */
export function safePercent(val: number | null | undefined): string {
  if (val == null || isNaN(val)) return 'N/A';
  return `${(val * 100).toFixed(2)}%`;
}

/** Safely format a number with decimals, returning 'N/A' for invalid values */
export function safeNumber(val: number | null | undefined, decimals: number = 2): string {
  if (val == null || isNaN(val)) return 'N/A';
  return val.toFixed(decimals);
}

/** Safely format currency, hiding invalid values */
export function safeCurrency(val: number | null | undefined): string {
  if (val == null || isNaN(val)) return 'N/A';
  return formatCurrency(val);
}

/** Check if a percentage value is meaningful (not 0.00% placeholder) */
export function isMeaningfulPercent(val: number | null | undefined): boolean {
  if (val == null || isNaN(val)) return false;
  // 0.0 is often a placeholder for missing data in financial APIs
  if (val === 0) return false;
  return true;
}

/** Format expense ratio as percentage */
export function formatExpenseRatio(val: number | null | undefined): string {
  if (val == null || isNaN(val)) return 'N/A';
  return `${(val * 100).toFixed(2)}%`;
}

/** Format AUM (net assets) similar to market cap */
export function formatAUM(val: number | null | undefined): string {
  if (val == null || isNaN(val)) return 'N/A';
  return formatLargeNumber(val);
}
