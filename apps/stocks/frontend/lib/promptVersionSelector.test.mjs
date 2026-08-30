import assert from 'node:assert/strict';
import test from 'node:test';

import {
  PROMPT_VERSION_OPTIONS,
  isPromptVersionSelectorEnabled,
  promptVersionRequestFields,
} from './promptVersionSelector.ts';

test('selector is hidden by default and only enabled explicitly', () => {
  assert.equal(isPromptVersionSelectorEnabled(undefined), false);
  assert.equal(isPromptVersionSelectorEnabled('false'), false);
  assert.equal(isPromptVersionSelectorEnabled('TRUE'), false);
  assert.equal(isPromptVersionSelectorEnabled('true'), true);
});

test('selector options default to stable v2 and label v3 experimental', () => {
  assert.deepEqual(PROMPT_VERSION_OPTIONS, [
    { value: '2.0', label: 'v2.0 — Stable' },
    { value: '3.0', label: 'v3.0 — Experimental' },
  ]);
  assert.equal(PROMPT_VERSION_OPTIONS[0].value, '2.0');
});

test('visible selector includes the exact selected version in requests', () => {
  assert.deepEqual(promptVersionRequestFields(true, '2.0'), {
    prompt_version: '2.0',
  });
  assert.deepEqual(promptVersionRequestFields(true, '3.0'), {
    prompt_version: '3.0',
  });
});

test('production request shape is unchanged when selector is hidden', () => {
  assert.deepEqual(promptVersionRequestFields(false, '2.0'), {});
  assert.deepEqual(promptVersionRequestFields(false, '3.0'), {});
});
