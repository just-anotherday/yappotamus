import test from 'node:test';
import assert from 'node:assert/strict';
import { dailySyncStatus } from './dailyUpdatesPresentation.ts';

const now = Date.parse('2026-11-06T12:00:00Z');
const state = { revision: 'new', applied_revision: 'new', last_seen_at: '2026-11-06T11:59:30Z' };
test('a live acknowledgement is required before showing matching settings', () => {
  assert.equal(dailySyncStatus(state, now).label, 'Received by local automation');
  assert.equal(dailySyncStatus({ ...state, applied_revision: 'old' }, now).label, 'Syncing your changes');
});
test('distinguishes offline-but-received settings from edits waiting for the computer', () => {
  const offline = { ...state, last_seen_at: '2026-11-06T11:00:00Z' };
  assert.equal(dailySyncStatus(offline, now).label, 'Received · local automation offline');
  assert.equal(dailySyncStatus({ ...offline, applied_revision: 'old' }, now).label, 'Changes waiting for local automation');
  assert.equal(dailySyncStatus({ ...state, last_seen_at: null }, now).label, 'Waiting for local automation');
});
