import assert from 'node:assert/strict';
import test from 'node:test';

import {
  PROMPT_VERSION_OPTIONS,
  promptVersionRequestFields,
} from './promptVersionSelector.ts';

test('selector options default to stable v2 and label v3 experimental', () => {
  assert.deepEqual(PROMPT_VERSION_OPTIONS, [
    { value: '2.0', label: 'v2.0 — Stable' },
    { value: '3.0', label: 'v3.0 — Experimental' },
  ]);
  assert.equal(PROMPT_VERSION_OPTIONS[0].value, '2.0');
});

test('visible selector includes the exact selected version in requests', () => {
  assert.deepEqual(promptVersionRequestFields('2.0'), {
    prompt_version: '2.0',
  });
  assert.deepEqual(promptVersionRequestFields('3.0'), {
    prompt_version: '3.0',
  });
});
