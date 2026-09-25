import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

import {
  CURRENT_PROMPT_VERSION,
  formatArticlesCited,
  formatArticlesSupplied,
  formatResearchSourceSection,
  formatReportDateTime,
  getPromptBadge,
  hasNeedsMoreResearch,
  hasOutlook,
  hasTechnicalAnalysis,
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

test('research source sections are formatted for people without changing the data', () => {
  assert.equal(formatResearchSourceSection('bear_case'), 'Bear Case');
  assert.equal(formatResearchSourceSection('outlook.short_term'), 'Short-Term Outlook');
  assert.equal(formatResearchSourceSection('key_catalysts[0]'), 'Key Catalysts 1');
  assert.equal(formatResearchSourceSection('new_section.detail'), 'New Section Detail');
});

test('research visibility is backward compatible for absent and empty fields', () => {
  const item = {
    id: 'research-item-0001',
    source_section: 'bear_case',
    research_question: 'What evidence would establish the proposed downside scenario?',
    reason: 'The available sources do not establish it.',
    missing_evidence: 'A primary source and current market data.',
    grounding_rule: 'source_support',
    classification: 'research_candidate',
    article_indices: [],
    market_fields: [],
  };

  assert.equal(hasNeedsMoreResearch(undefined), false);
  assert.equal(hasNeedsMoreResearch([]), false);
  assert.equal(hasNeedsMoreResearch([item]), true);
  assert.equal(hasNeedsMoreResearch([item, { ...item, id: 'research-item-0002' }]), true);
});

test('partial report sections render only when validated public content remains', () => {
  assert.equal(hasTechnicalAnalysis(null), false);
  assert.equal(hasTechnicalAnalysis({
    trend: null,
    support_levels: [],
    resistance_levels: [],
    breakout_level: '',
    breakdown_level: '',
  }), false);
  assert.equal(hasTechnicalAnalysis({
    trend: null,
    support_levels: ['$100'],
    resistance_levels: [],
    breakout_level: '',
    breakdown_level: '',
  }), true);
  assert.equal(hasOutlook(null), false);
  assert.equal(hasOutlook({ short_term: null, medium_term: null, long_term: null }), false);
  assert.equal(hasOutlook({ short_term: null, medium_term: 'Neutral — evidence is mixed.', long_term: null }), true);
});

test('research section preserves the trust boundary on every report surface', async () => {
  const component = await readFile(
    new URL('../components/intelligence/NeedsMoreResearchSection.tsx', import.meta.url),
    'utf8',
  );
  const current = await readFile(
    new URL('../app/intelligence/[ticker]/page.tsx', import.meta.url),
    'utf8',
  );
  const history = await readFile(
    new URL('../app/intelligence/[ticker]/history/page.tsx', import.meta.url),
    'utf8',
  );
  const saved = await readFile(
    new URL('../app/analysis/reports/[id]/page.tsx', import.meta.url),
    'utf8',
  );

  assert.match(component, /if \(!hasNeedsMoreResearch\(items\)\) return null/);
  assert.match(component, /key=\{item\.id\}/);
  assert.match(component, /item\.research_question/);
  assert.match(component, /item\.missing_evidence/);
  assert.match(component, /formatResearchSourceSection\(item\.source_section\)/);
  assert.doesNotMatch(component, /grounding_rule|classification|article_indices|market_fields/);
  assert.doesNotMatch(component, /Bullish|Bearish|Strong Buy|recommendation|#4caf50|#f44336/i);

  for (const surface of [current, history, saved]) {
    assert.match(surface, /<NeedsMoreResearchSection items=\{/);
  }
  assert.doesNotMatch(history, /JSON\.stringify\(rd/);
});
