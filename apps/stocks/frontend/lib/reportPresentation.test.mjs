import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

import {
  CURRENT_PROMPT_VERSION,
  getPromptBadge,
} from './reportPresentation.ts';

test('current prompt requires both the current version and a deterministic hash', () => {
  assert.equal(
    getPromptBadge(CURRENT_PROMPT_VERSION, 'a'.repeat(64)),
    `Prompt v${CURRENT_PROMPT_VERSION}`,
  );
  assert.equal(getPromptBadge(CURRENT_PROMPT_VERSION, null), 'Prompt version not recorded');
});

test('ambiguous historical versions are not guessed to be legacy', () => {
  assert.equal(getPromptBadge('1.0', null), 'Prompt version not recorded');
  assert.equal(getPromptBadge(null, null), 'Prompt version not recorded');
});

test('report cards do not render database IDs or unstable report numbers', async () => {
  const source = await readFile(
    new URL('../app/analysis/reports/page.tsx', import.meta.url),
    'utf8',
  );
  assert.doesNotMatch(source, /report\.report_number/);
  assert.doesNotMatch(source, /Record ID/);
  assert.match(source, /\{report\.ticker\} Analysis/);
  assert.match(source, /formatReportDateTime\(report\.created_at\)/);
});