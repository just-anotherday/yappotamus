import { formatApiTimestamp } from './formatters';

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
