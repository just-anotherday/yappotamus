// ==============================================================================
// APP ACCESS TOKEN - single-user auth (sessionStorage-backed fetch wrapper)
// ==============================================================================

const TOKEN_KEY = 'yapvibes_app_access_token';

/** Dispatched on window whenever a request comes back 401, so any mounted
 * AuthGate can clear its unlocked state and show the token prompt again. */
export const AUTH_INVALID_EVENT = 'yapvibes:auth-invalid';

export function getAppToken(): string | null {
  if (typeof window === 'undefined') return null;
  return sessionStorage.getItem(TOKEN_KEY);
}

export function setAppToken(token: string): void {
  sessionStorage.setItem(TOKEN_KEY, token);
}

export function clearAppToken(): void {
  sessionStorage.removeItem(TOKEN_KEY);
}

/** Build the browser WebSocket subprotocol list without exposing the access
 * token in the URL. The backend echoes only the non-secret `yapvibes` value. */
export function getAppWebSocketProtocols(): [string, string] | null {
  const token = getAppToken();
  if (!token) return null;

  let binaryToken = '';
  for (const byte of new TextEncoder().encode(token)) {
    binaryToken += String.fromCharCode(byte);
  }
  const encodedToken = btoa(binaryToken)
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '');

  return ['yapvibes', encodedToken];
}

/** Clear invalid credentials and ask the mounted AuthGate to relock. */
export function invalidateAppToken(): void {
  clearAppToken();
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new Event(AUTH_INVALID_EVENT));
  }
}

/** Drop-in replacement for `fetch` that attaches the app access token and
 * reacts to a 401 by clearing the token and notifying the auth gate. */
export async function apiFetch(input: string, init: RequestInit = {}): Promise<Response> {
  const token = getAppToken();
  const headers = new Headers(init.headers);
  if (token) headers.set('Authorization', `Bearer ${token}`);

  const res = await fetch(input, { ...init, headers });

  if (res.status === 401) {
    invalidateAppToken();
  }

  return res;
}
