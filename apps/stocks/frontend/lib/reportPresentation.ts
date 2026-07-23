export const CURRENT_PROMPT_VERSION = '2.0';

// Intentionally empty until a historical prompt version can be proven from
// stored metadata. Never classify a version as legacy based on age or "1.0" alone.
const CONFIRMED_LEGACY_PROMPT_VERSIONS = new Set<string>();

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
  const date = new Date(isoTimestamp);
  if (Number.isNaN(date.getTime())) return isoTimestamp;

  return new Intl.DateTimeFormat(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  }).format(date);
}