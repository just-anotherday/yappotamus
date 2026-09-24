import { formatApiTimestamp } from './formatters.ts';
import type { NeedsMoreResearchItem, OutlookData, TechnicalAnalysisData } from '../types/stock';

export const CURRENT_PROMPT_VERSION = '2.0';

export function formatArticlesSupplied(count: number): string {
  return `Articles Supplied: ${count}`;
}

export function formatArticlesCited(count: number): string {
  return `Articles Cited: ${count}`;
}

// Hashed reports from both retained pipelines have an auditable prompt identity.
const SUPPORTED_HASHED_PROMPT_VERSIONS = new Set<string>(['2.0', '3.0']);

// Unhashed v2 records predate the current reproducible prompt contract.
const CONFIRMED_LEGACY_PROMPT_VERSIONS = new Set<string>(['2.0']);

export function getPromptBadge(
  promptVersion?: string | null,
  promptHash?: string | null,
): string {
  if (
    promptVersion
    && promptHash
    && SUPPORTED_HASHED_PROMPT_VERSIONS.has(promptVersion)
  ) {
    return `Prompt v${promptVersion}`;
  }
  if (promptVersion && CONFIRMED_LEGACY_PROMPT_VERSIONS.has(promptVersion)) {
    return 'Legacy prompt';
  }
  return 'Prompt version not recorded';
}

export function formatReportDateTime(isoTimestamp: string): string {
  return formatApiTimestamp(isoTimestamp, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
    timeZoneName: 'short',
  }, isoTimestamp);
}

const SOURCE_SECTION_LABELS: Record<string, string> = {
  'outlook.short_term': 'Short-Term Outlook',
  'outlook.medium_term': 'Medium-Term Outlook',
  'outlook.long_term': 'Long-Term Outlook',
  technical_analysis: 'Technical Analysis',
};

export function formatResearchSourceSection(sourceSection: string): string {
  const knownLabel = SOURCE_SECTION_LABELS[sourceSection];
  if (knownLabel) return knownLabel;

  return sourceSection
    .replace(/\[(\d+)\]/g, (_, index: string) => ` ${Number(index) + 1}`)
    .replace(/[._-]+/g, ' ')
    .trim()
    .split(/\s+/)
    .filter(Boolean)
    .map(word => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
}

export function hasTechnicalAnalysis(
  technicalAnalysis?: TechnicalAnalysisData | null,
): boolean {
  return Boolean(
    technicalAnalysis?.trend
    || technicalAnalysis?.support_levels?.length
    || technicalAnalysis?.resistance_levels?.length
    || technicalAnalysis?.breakout_level
    || technicalAnalysis?.breakdown_level,
  );
}

export function hasOutlook(outlook?: OutlookData | null): boolean {
  return Boolean(outlook?.short_term || outlook?.medium_term || outlook?.long_term);
}

export function hasNeedsMoreResearch(
  items?: readonly NeedsMoreResearchItem[] | null,
): boolean {
  return Boolean(items?.length);
}
