import assert from 'node:assert/strict';
import test from 'node:test';

import {
  deriveWebSocketUrl,
  resolveServiceUrls,
  websocketUrlForChannel,
} from './serviceUrls.ts';

test('production REST origin derives a secure WebSocket URL', () => {
  assert.deepEqual(
    resolveServiceUrls({
      apiOrigin: 'https://yapvibes-stocks-api.onrender.com/',
      nodeEnv: 'production',
    }),
    {
      apiOrigin: 'https://yapvibes-stocks-api.onrender.com',
      websocketUrl: 'wss://yapvibes-stocks-api.onrender.com/ws',
    },
  );
});

test('development defaults remain localhost', () => {
  assert.deepEqual(resolveServiceUrls({ nodeEnv: 'development' }), {
    apiOrigin: 'http://localhost:8000',
    websocketUrl: 'ws://localhost:8000/ws',
  });
});

test('a valid dedicated WebSocket URL is supported', () => {
  assert.equal(
    resolveServiceUrls({
      apiOrigin: 'http://localhost:8000',
      websocketUrl: 'ws://localhost:9000/events',
      nodeEnv: 'development',
    }).websocketUrl,
    'ws://localhost:9000/events',
  );
});

test('production configuration fails clearly without an API origin', () => {
  assert.throws(
    () => resolveServiceUrls({ nodeEnv: 'production' }),
    /NEXT_PUBLIC_API_BASE is required/,
  );
});

test('invalid REST and WebSocket protocols are rejected', () => {
  assert.throws(
    () => resolveServiceUrls({ apiOrigin: 'file:///tmp/api', nodeEnv: 'test' }),
    /http or https/,
  );
  assert.throws(
    () =>
      resolveServiceUrls({
        apiOrigin: 'http://localhost:8000',
        websocketUrl: 'https://localhost/ws',
        nodeEnv: 'test',
      }),
    /ws or wss/,
  );
});

test('derivation preserves an API path prefix', () => {
  assert.equal(
    deriveWebSocketUrl('https://example.test/backend/'),
    'wss://example.test/backend/ws',
  );
});

test('WebSocket channel labels identify the browser connection purpose', () => {
  assert.equal(
    websocketUrlForChannel('wss://example.test/ws', 'prices'),
    'wss://example.test/ws?channel=prices',
  );
  assert.equal(
    websocketUrlForChannel('wss://example.test/ws', 'news'),
    'wss://example.test/ws?channel=news',
  );
});