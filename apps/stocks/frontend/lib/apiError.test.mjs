import assert from 'node:assert/strict';
import test from 'node:test';

import {
  ApiError,
  apiErrorFromResponse,
  networkApiError,
  normalizeFetchError,
  requireOk,
} from './apiError.ts';

function response(body, status = 400, contentType = 'application/json') {
  return new Response(body, {
    status,
    headers: contentType ? { 'content-type': contentType } : {},
  });
}

test('extracts the backend error envelope and preserves status', async () => {
  const error = await apiErrorFromResponse(
    response(JSON.stringify({ error: 'Ticker is invalid', status_code: 422 }), 422),
  );
  assert.equal(error.message, 'Ticker is invalid');
  assert.equal(error.status, 422);
});

test('extracts a string detail envelope', async () => {
  const error = await apiErrorFromResponse(
    response(JSON.stringify({ detail: 'Not found' }), 404),
  );
  assert.equal(error.message, 'Not found');
  assert.equal(error.status, 404);
});

test('formats FastAPI validation arrays', async () => {
  const error = await apiErrorFromResponse(
    response(
      JSON.stringify({
        detail: [
          { loc: ['body', 'ticker'], msg: 'Field required', type: 'missing' },
          { loc: ['query', 'limit'], msg: 'Must be positive', type: 'value_error' },
        ],
      }),
      422,
    ),
  );
  assert.equal(
    error.message,
    'body.ticker: Field required; query.limit: Must be positive',
  );
});

test('formats validation arrays from the backend details envelope', async () => {
  const error = await apiErrorFromResponse(
    response(
      JSON.stringify({
        error: 'Request validation failed',
        details: [{ loc: ['body', 'ticker'], msg: 'Field required' }],
        status_code: 422,
      }),
      422,
    ),
  );
  assert.equal(error.message, 'body.ticker: Field required');
});
test('uses safe plain-text errors', async () => {
  const error = await apiErrorFromResponse(
    response('Service temporarily unavailable', 503, 'text/plain'),
  );
  assert.equal(error.message, 'Service temporarily unavailable');
});

test('does not expose HTML error pages', async () => {
  const error = await apiErrorFromResponse(
    response('<html><body>proxy internals</body></html>', 502, 'text/html'),
    'The service is unavailable',
  );
  assert.equal(error.message, 'The service is unavailable');
  assert.doesNotMatch(error.message, /proxy internals/);
});

test('empty and unknown non-JSON responses use the caller fallback', async () => {
  assert.equal(
    (await apiErrorFromResponse(response('', 500), 'Request failed')).message,
    'Request failed',
  );
  assert.equal(
    (
      await apiErrorFromResponse(
        response('binary-ish', 500, 'application/octet-stream'),
        'Request failed',
      )
    ).message,
    'Request failed',
  );
});

test('requireOk throws ApiError with the HTTP status', async () => {
  await assert.rejects(
    requireOk(response(JSON.stringify({ detail: 'Forbidden' }), 403)),
    (error) =>
      error instanceof ApiError &&
      error.status === 403 &&
      error.message === 'Forbidden',
  );
});

test('network failures are normalized without an HTTP status', () => {
  const error = networkApiError(new TypeError('fetch failed'));
  assert.equal(error.status, null);
  assert.match(error.message, /Unable to reach the server/);
  assert.doesNotMatch(error.message, /fetch failed/);
});

test('intentional AbortError cancellation is preserved', () => {
  const abort = new DOMException('signal is aborted', 'AbortError');
  assert.equal(normalizeFetchError(abort), abort);
  assert.equal(normalizeFetchError(abort).name, 'AbortError');
});
