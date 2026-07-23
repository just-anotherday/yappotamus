import assert from 'node:assert/strict';
import { after, before, test } from 'node:test';
import { spawn } from 'node:child_process';

const port = 5199;
const baseUrl = `http://127.0.0.1:${port}`;
let server;

before(async () => {
  server = spawn(process.execPath, ['server.js'], {
    cwd: new URL('..', import.meta.url),
    env: {
      ...process.env,
      HOST: '127.0.0.1',
      PORT: String(port),
      OPENAI_API_KEY: 'test-only-not-sent'
    },
    stdio: ['ignore', 'pipe', 'pipe']
  });

  await new Promise((resolve, reject) => {
    const timeout = setTimeout(() => reject(new Error('Server startup timed out')), 5000);
    server.once('error', reject);
    server.stdout.on('data', (chunk) => {
      if (chunk.toString().includes(`127.0.0.1:${port}`)) {
        clearTimeout(timeout);
        resolve();
      }
    });
  });
});

after(() => {
  server?.kill();
});

test('GET / returns the health response', async () => {
  const response = await fetch(`${baseUrl}/`);
  assert.equal(response.status, 200);
  assert.deepEqual(await response.json(), { status: 'ok' });
});

for (const origin of ['https://yapvibes.com', 'https://www.yapvibes.com']) {
  test(`CORS preflight allows ${origin}`, async () => {
    const response = await fetch(`${baseUrl}/api/openai`, {
      method: 'OPTIONS',
      headers: {
        Origin: origin,
        'Access-Control-Request-Method': 'POST',
        'Access-Control-Request-Headers': 'content-type'
      }
    });

    assert.equal(response.status, 204);
    assert.equal(response.headers.get('access-control-allow-origin'), origin);
    assert.match(response.headers.get('access-control-allow-methods') || '', /POST/);
  });
}

test('POST /api/openai rejects an invalid prompt before calling OpenAI', async () => {
  const response = await fetch(`${baseUrl}/api/openai`, {
    method: 'POST',
    headers: {
      Origin: 'https://yapvibes.com',
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ message: 'x', context: [] })
  });

  assert.equal(response.status, 400);
  assert.deepEqual(await response.json(), {
    error: 'Prompt must be at least 3 characters long.'
  });
});

test('POST /api/openai rejects malformed context before calling OpenAI', async () => {
  const response = await fetch(`${baseUrl}/api/openai`, {
    method: 'POST',
    headers: {
      Origin: 'https://www.yapvibes.com',
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      message: 'valid prompt',
      context: [{ role: 'system', content: 'not allowed' }]
    })
  });

  assert.equal(response.status, 400);
  assert.deepEqual(await response.json(), {
    error: 'Context contains an invalid message.'
  });
});