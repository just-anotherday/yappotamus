const DEFAULT_ERROR_MESSAGE = 'The request could not be completed. Please try again.';

export class ApiError extends Error {
  readonly status: number | null;

  constructor(message: string, status: number | null, options?: ErrorOptions) {
    super(message, options);
    this.name = 'ApiError';
    this.status = status;
  }
}

function isHtml(value: string): boolean {
  return /<!doctype\s+html|<html[\s>]|<body[\s>]/i.test(value);
}

function validationMessage(value: unknown): string | null {
  if (!Array.isArray(value)) return null;

  const messages = value.flatMap((item) => {
    if (!item || typeof item !== 'object') return [];
    const entry = item as { loc?: unknown; msg?: unknown };
    if (typeof entry.msg !== 'string' || !entry.msg.trim()) return [];
    const location = Array.isArray(entry.loc)
      ? entry.loc
          .filter((part) => typeof part === 'string' || typeof part === 'number')
          .join('.')
      : '';
    return [location ? `${location}: ${entry.msg.trim()}` : entry.msg.trim()];
  });

  return messages.length ? messages.join('; ') : null;
}

function jsonMessage(payload: unknown): string | null {
  if (typeof payload === 'string') {
    const value = payload.trim();
    return value && !isHtml(value) ? value : null;
  }
  if (!payload || typeof payload !== 'object') return null;

  const envelope = payload as {
    error?: unknown;
    detail?: unknown;
    details?: unknown;
    message?: unknown;
  };

  const backendValidation = validationMessage(envelope.details);
  if (backendValidation) return backendValidation;

  for (const value of [envelope.error, envelope.detail, envelope.message]) {
    if (typeof value === 'string' && value.trim() && !isHtml(value)) {
      return value.trim();
    }
    const validation = validationMessage(value);
    if (validation) return validation;
  }
  return null;
}

export async function apiErrorFromResponse(
  response: Response,
  fallback = DEFAULT_ERROR_MESSAGE,
): Promise<ApiError> {
  let body = '';
  try {
    body = await response.text();
  } catch {
    return new ApiError(fallback, response.status);
  }

  let message: string | null = null;
  if (body.trim()) {
    try {
      message = jsonMessage(JSON.parse(body));
    } catch {
      const contentType = response.headers.get('content-type')?.toLowerCase() || '';
      if (!isHtml(body) && (contentType.includes('text/plain') || !contentType)) {
        message = body.trim();
      }
    }
  }

  return new ApiError(message || fallback, response.status);
}

export async function requireOk(
  response: Response,
  fallback?: string,
): Promise<Response> {
  if (!response.ok) {
    throw await apiErrorFromResponse(response, fallback);
  }
  return response;
}

export function networkApiError(cause: unknown): ApiError {
  if (cause instanceof ApiError) return cause;
  return new ApiError(
    'Unable to reach the server. Check your connection and try again.',
    null,
    cause instanceof Error ? { cause } : undefined,
  );
}

export function normalizeFetchError(cause: unknown): Error {
  // AbortController cancellation is normal during navigation, dependency
  // changes, and React Strict Mode's development cleanup. Callers already
  // recognize AbortError and must not display it as a network outage.
  if (cause instanceof Error && cause.name === 'AbortError') {
    return cause;
  }
  return networkApiError(cause);
}
