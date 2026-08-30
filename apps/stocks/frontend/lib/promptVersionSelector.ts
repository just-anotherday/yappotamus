export type PromptVersion = '2.0' | '3.0';

export const PROMPT_VERSION_OPTIONS: ReadonlyArray<{
  value: PromptVersion;
  label: string;
}> = [
  { value: '2.0', label: 'v2.0 — Stable' },
  { value: '3.0', label: 'v3.0 — Experimental' },
];

export function isPromptVersionSelectorEnabled(value: string | undefined): boolean {
  return value === 'true';
}

export const PROMPT_VERSION_SELECTOR_ENABLED = isPromptVersionSelectorEnabled(
  process.env.NEXT_PUBLIC_ENABLE_PROMPT_VERSION_SELECTOR,
);

export function promptVersionRequestFields(
  selectorEnabled: boolean,
  selectedVersion: PromptVersion,
): { prompt_version?: PromptVersion } {
  return selectorEnabled ? { prompt_version: selectedVersion } : {};
}
