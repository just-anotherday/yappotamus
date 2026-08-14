import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

import {
  CURRENT_PROMPT_VERSION,
  formatReportDateTime,
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

test('report timestamps render in Eastern time, including legacy UTC-naive values', () => {
  assert.equal(
    formatReportDateTime('2026-08-14T18:00:00'),
    'Aug 14, 2026, 2:00 PM EDT',
  );
  assert.equal(
    formatReportDateTime('2026-01-14T18:00:00Z'),
    'Jan 14, 2026, 1:00 PM EST',
  );
  assert.equal(formatReportDateTime('not-a-date'), 'not-a-date');
});
