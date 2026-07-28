import assert from 'node:assert/strict';
import test from 'node:test';

import { ReconnectingWebSocket } from './reconnectingWebSocket.ts';

class FakeSocket {
  onopen = null;
  onmessage = null;
  onclose = null;
  closeCalls = 0;

  close() {
    this.closeCalls += 1;
  }

  open() {
    this.onopen?.();
  }

  disconnect(code = 1006) {
    this.onclose?.({ code });
  }
}

function harness(options = {}) {
  const sockets = [];
  const timers = [];
  const delays = [];
  const messages = [];
  let unauthorized = 0;

  const connection = new ReconnectingWebSocket({
    createSocket: () => {
      const socket = new FakeSocket();
      sockets.push(socket);
      return socket;
    },
    onMessage: (event) => messages.push(event.data),
    onUnauthorized: () => {
      unauthorized += 1;
    },
    random: () => 0.5,
    setTimer: (callback, delay) => {
      timers.push(callback);
      delays.push(delay);
      return callback;
    },
    clearTimer: (timer) => {
      const index = timers.indexOf(timer);
      if (index >= 0) timers.splice(index, 1);
    },
    ...options,
  });

  return {
    connection,
    sockets,
    timers,
    delays,
    messages,
    unauthorized: () => unauthorized,
    runNextTimer() {
      const callback = timers.shift();
      assert.ok(callback, 'expected a reconnect timer');
      callback();
    },
  };
}

test('start creates one initial connection and is idempotent', () => {
  const h = harness();
  h.connection.start();
  h.connection.start();
  assert.equal(h.sockets.length, 1);
});

test('an unexpected close creates a new socket after backoff', () => {
  const h = harness();
  h.connection.start();
  h.sockets[0].disconnect();
  assert.deepEqual(h.delays, [1000]);
  h.runNextTimer();
  assert.equal(h.sockets.length, 2);
});

test('repeated failures back off exponentially within the bound', () => {
  const h = harness({ baseDelayMs: 1000, maxDelayMs: 2500 });
  h.connection.start();
  h.sockets[0].disconnect();
  h.runNextTimer();
  h.sockets[1].disconnect();
  h.runNextTimer();
  h.sockets[2].disconnect();
  assert.deepEqual(h.delays, [1000, 2000, 2500]);
});

test('a successful connection resets the retry delay', () => {
  const h = harness();
  h.connection.start();
  h.sockets[0].disconnect();
  h.runNextTimer();
  h.sockets[1].disconnect();
  h.runNextTimer();
  h.sockets[2].open();
  h.sockets[2].disconnect();
  assert.deepEqual(h.delays, [1000, 2000, 1000]);
});

test('stop cancels reconnect and closes the active socket', () => {
  const h = harness();
  h.connection.start();
  h.sockets[0].disconnect();
  h.connection.stop();
  assert.equal(h.timers.length, 0);
  assert.equal(h.sockets.length, 1);

  const active = harness();
  active.connection.start();
  active.connection.stop();
  assert.equal(active.sockets[0].closeCalls, 1);
  active.sockets[0].disconnect();
  assert.equal(active.timers.length, 0);
});

test('there are no duplicate reconnect timers or sockets', () => {
  const h = harness();
  h.connection.start();
  h.sockets[0].disconnect();
  h.sockets[0].disconnect();
  assert.equal(h.timers.length, 1);
  h.runNextTimer();
  assert.equal(h.sockets.length, 2);
});

test('unauthorized closure invalidates auth without reconnecting', () => {
  const h = harness();
  h.connection.start();
  h.sockets[0].disconnect(4401);
  assert.equal(h.unauthorized(), 1);
  assert.equal(h.timers.length, 0);
});
