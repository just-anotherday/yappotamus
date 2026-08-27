import { formatApiTimestamp } from './formatters';

export const CURRENT_PROMPT_VERSION = '3.0';

export function formatArticlesSupplied(count: number): string {
  return `Articles Supplied: ${count}`;
}

export function formatArticlesCited(count: number): string {
  return `Articles Cited: ${count}`;
}

// Prompt v2 is now a known historical version. Never classify other versions
// as legacy based on age or a guessed default alone.
const CONFIRMED_LEGACY_PROMPT_VERSIONS = new Set<string>(['2.0']);

export function getPromptBadge(
  promptVersion?: string | null,
  promptHash?: string | null,
): string {
  if (promptVersion === CURRENT_PROMPT_VERSION && promptHash) {
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
