import assert from 'node:assert/strict';
import test from 'node:test';

import {
  easternDayLabel,
  formatApiTimestamp,
  formatDate,
  parseApiTimestamp,
  timeAgo,
} from './formatters.ts';

test('timezone-less API timestamps are treated as UTC instants', () => {
  assert.equal(
    parseApiTimestamp('2026-08-14T18:00:00')?.toISOString(),
    '2026-08-14T18:00:00.000Z',
  );
  assert.equal(
    timeAgo('2026-08-14T18:00:00', Date.parse('2026-08-14T18:30:00Z')),
    '30m ago',
  );
});

test('explicit UTC and offset timestamps preserve their instants', () => {
  const expected = '2026-08-14T18:00:00.000Z';

  assert.equal(parseApiTimestamp('2026-08-14T18:00:00Z')?.toISOString(), expected);
  assert.equal(parseApiTimestamp('2026-08-14T18:00:00+00:00')?.toISOString(), expected);
  assert.equal(parseApiTimestamp('2026-08-14T14:00:00-04:00')?.toISOString(), expected);
});

test('absolute timestamps display in Eastern time with daylight saving', () => {
  assert.equal(
    formatDate('2026-08-14T18:00:00Z'),
    'August 14, 2026 at 02:00 PM EDT',
  );
  assert.equal(
    formatDate('2026-01-14T18:00:00Z'),
    'January 14, 2026 at 01:00 PM EST',
  );
});

test('API timestamp presets preserve Eastern date and time boundaries', () => {
  assert.equal(
    formatApiTimestamp(
      '2026-08-15T01:30:00',
      { year: 'numeric', month: 'short', day: 'numeric' },
    ),
    'Aug 14, 2026',
  );
  assert.equal(
    formatApiTimestamp(
      '2026-08-15T01:30:00Z',
      { hour: '2-digit', minute: '2-digit', hour12: true, timeZoneName: 'short' },
    ),
    '09:30 PM EDT',
  );
});

test('day labels compare Eastern calendar dates instead of elapsed hours', () => {
  const justAfterEasternMidnight = Date.parse('2026-08-15T04:30:00Z');

  assert.equal(
    easternDayLabel('2026-08-15T02:30:00Z', justAfterEasternMidnight),
    'Yesterday',
  );
  assert.equal(
    easternDayLabel('2026-08-15T04:15:00Z', justAfterEasternMidnight),
    'Today',
  );
});

test('future timestamps are clamped to a newly published age', () => {
  assert.equal(
    timeAgo('2026-08-14T18:31:00Z', Date.parse('2026-08-14T18:30:00Z')),
    'Just now',
  );
});

test('missing and invalid timestamp inputs use safe fallbacks', () => {
  assert.equal(parseApiTimestamp('not-a-date'), null);
  assert.equal(timeAgo('not-a-date'), '');
  assert.equal(timeAgo(null), '');
  assert.equal(formatDate('not-a-date'), 'not-a-date');
  assert.equal(formatDate(null), 'Unknown date');
  assert.equal(formatDate('   '), 'Unknown date');
  assert.equal(easternDayLabel(null), 'No Date');
});
