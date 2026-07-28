export interface ServiceUrlEnvironment {
  apiOrigin?: string;
  websocketUrl?: string;
  nodeEnv?: string;
}

export interface ServiceUrls {
  apiOrigin: string;
  websocketUrl: string;
}

export type WebSocketChannel = 'prices' | 'news';

const LOCAL_API_ORIGIN = 'http://localhost:8000';

function parseOrigin(value: string, label: string): URL {
  let parsed: URL;
  try {
    parsed = new URL(value);
  } catch {
    throw new Error(`${label} must be a valid absolute URL`);
  }

  if (!['http:', 'https:'].includes(parsed.protocol)) {
    throw new Error(`${label} must use http or https`);
  }
  if (parsed.username || parsed.password || parsed.search || parsed.hash) {
    throw new Error(`${label} must not contain credentials, a query, or a fragment`);
  }

  return parsed;
}

function normalizeApiOrigin(value: string): string {
  const parsed = parseOrigin(value, 'NEXT_PUBLIC_API_BASE');
  parsed.pathname = parsed.pathname.replace(/\/+$/, '');
  return parsed.toString().replace(/\/$/, '');
}

export function deriveWebSocketUrl(apiOrigin: string): string {
  const parsed = parseOrigin(apiOrigin, 'API origin');
  parsed.protocol = parsed.protocol === 'https:' ? 'wss:' : 'ws:';
  parsed.pathname = `${parsed.pathname.replace(/\/+$/, '')}/ws`;
  return parsed.toString();
}

export function websocketUrlForChannel(
  websocketUrl: string,
  channel: WebSocketChannel,
): string {
  const parsed = new URL(websocketUrl);
  parsed.searchParams.set('channel', channel);
  return parsed.toString();
}

function normalizeWebSocketUrl(value: string): string {
  let parsed: URL;
  try {
    parsed = new URL(value);
  } catch {
    throw new Error('NEXT_PUBLIC_WS_URL must be a valid absolute URL');
  }

  if (!['ws:', 'wss:'].includes(parsed.protocol)) {
    throw new Error('NEXT_PUBLIC_WS_URL must use ws or wss');
  }
  if (parsed.username || parsed.password || parsed.search || parsed.hash) {
    throw new Error(
      'NEXT_PUBLIC_WS_URL must not contain credentials, a query, or a fragment',
    );
  }

  return parsed.toString();
}

export function resolveServiceUrls(environment: ServiceUrlEnvironment): ServiceUrls {
  const production = environment.nodeEnv === 'production';
  const configuredApi = environment.apiOrigin?.trim();

  if (production && !configuredApi) {
    throw new Error('NEXT_PUBLIC_API_BASE is required for production builds');
  }

  const apiOrigin = normalizeApiOrigin(configuredApi || LOCAL_API_ORIGIN);
  const configuredWebSocket = environment.websocketUrl?.trim();
  const websocketUrl = configuredWebSocket
    ? normalizeWebSocketUrl(configuredWebSocket)
    : deriveWebSocketUrl(apiOrigin);

  return { apiOrigin, websocketUrl };
}

const serviceUrls = resolveServiceUrls({
  apiOrigin: process.env.NEXT_PUBLIC_API_BASE,
  websocketUrl: process.env.NEXT_PUBLIC_WS_URL,
  nodeEnv: process.env.NODE_ENV,
});

export const API_BASE = serviceUrls.apiOrigin;
export const WS_URL = serviceUrls.websocketUrl;
export const LIVE_PRICES_WS_URL = websocketUrlForChannel(WS_URL, 'prices');
export const NEWS_WS_URL = websocketUrlForChannel(WS_URL, 'news');
