import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

import {
  CURRENT_PROMPT_VERSION,
  formatArticlesCited,
  formatArticlesSupplied,
  formatReportDateTime,
  getPromptBadge,
} from './reportPresentation.ts';

test('current financial-analysis prompt version is v2', () => {
  assert.equal(CURRENT_PROMPT_VERSION, '2.0');
});

test('article metadata distinguishes supplied inputs from trusted citations', () => {
  assert.equal(formatArticlesSupplied(35), 'Articles Supplied: 35');
  assert.equal(formatArticlesCited(10), 'Articles Cited: 10');
  assert.equal(formatArticlesCited(0), 'Articles Cited: 0');
});

test('current prompt is supported only when it has a deterministic hash', () => {
  assert.equal(
    getPromptBadge(CURRENT_PROMPT_VERSION, 'a'.repeat(64)),
    `Prompt v${CURRENT_PROMPT_VERSION}`,
  );
  assert.equal(getPromptBadge(CURRENT_PROMPT_VERSION, null), 'Legacy prompt');
});

test('retained hashed v3 reports remain explicitly identifiable', () => {
  assert.equal(getPromptBadge('3.0', 'b'.repeat(64)), 'Prompt v3.0');
});

test('unhashed historical v2 reports remain identifiable as legacy', () => {
  assert.equal(getPromptBadge('2.0', null), 'Legacy prompt');
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
  assert.match(source, /formatArticlesSupplied\(report\.articles_count\)/);
  assert.match(source, /formatArticlesCited\(report\.articles_cited_count \?\? 0\)/);
});

test('report detail labels supplied and cited counts independently', async () => {
  const source = await readFile(
    new URL('../app/analysis/reports/[id]/page.tsx', import.meta.url),
    'utf8',
  );
  assert.match(source, /formatArticlesSupplied\(report\.articles_count\)/);
  assert.match(source, /formatArticlesCited\(report\.report_data\.articles_used\?\.length \?\? 0\)/);
  assert.match(source, /Articles Cited in Analysis/);
  assert.doesNotMatch(source, /<strong>Articles:<\/strong>/);
  assert.doesNotMatch(source, /report\.days_back/);
  assert.match(source, /data\.news_summary\?\.length/);
  assert.match(source, /data\.technical_analysis &&/);
  assert.match(source, /data\.outlook &&/);
});

test('report timestamps render in Eastern time, including legacy UTC-naive values', () => {
  assert.equal(
    formatReportDateTime('2026-08-20T17:35:00Z'),
    'Aug 20, 2026, 1:35 PM EDT',
  );
  assert.equal(
    formatReportDateTime('2026-01-14T18:00:00Z'),
    'Jan 14, 2026, 1:00 PM EST',
  );
  assert.equal(
    formatReportDateTime('2026-08-20T13:35:00-04:00'),
    'Aug 20, 2026, 1:35 PM EDT',
  );
  assert.equal(
    formatReportDateTime('2026-08-20T17:35:00'),
    'Aug 20, 2026, 1:35 PM EDT',
  );
  assert.equal(formatReportDateTime('not-a-date'), 'not-a-date');
});
