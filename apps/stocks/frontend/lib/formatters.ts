// Currency formatting
export const formatCurrency = (val: number) => {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(val);
};

// Large number formatting (market cap, shares)
export const formatLargeNumber = (val: number) => {
  if (val == null || val === 0) return 'N/A';
  if (val >= 1e12) return `$${(val / 1e12).toFixed(2)}T`;
  if (val >= 1e9) return `$${(val / 1e9).toFixed(2)}B`;
  if (val >= 1e6) return `$${(val / 1e6).toFixed(2)}M`;
  return val.toLocaleString();
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

// Time-ago formatting
export function timeAgo(dateStr: string | null | undefined): string {
  if (!dateStr) return '';
  try {
    const now = new Date();
    const date = new Date(dateStr);
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    const diffHrs = Math.floor(diffMins / 60);
    if (diffHrs < 24) return `${diffHrs}h ago`;
    const diffDays = Math.floor(diffHrs / 24);
    return `${diffDays}d ago`;
  } catch {
    return '';
  }
}

// Full date formatting for tooltips/display
export function formatDate(dateStr: string | null | undefined): string {
  if (!dateStr) return 'Unknown date';
  try {
    const date = new Date(dateStr);
    return date.toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return dateStr;
  }
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
