// ==============================================================================
// HOOK: useLivePrices - WebSocket connection + price flash effect + auto-reconnect
// ==============================================================================

import { useEffect, useState, useRef, useCallback } from 'react';
import { WS_URL } from '@/types/stock';
import type { LiveQuote } from '@/types/stock';
import { getAppWebSocketProtocols, invalidateAppToken } from '@/lib/apiFetch';

export function useLivePrices() {
  const [livePrices, setLivePrices] = useState<Record<string, LiveQuote>>({});
  const [priceFlash, setPriceFlash] = useState<Record<string, 'up' | 'down'>>({});
  const [connected, setConnected] = useState<boolean>(false);
  const prevPricesRef = useRef<Record<string, number>>({});
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectAttemptsRef = useRef<number>(0);
  const stoppedRef = useRef(false);
  const pendingQuotesRef = useRef<Record<string, LiveQuote>>({});
  const frameRef = useRef<number | null>(null);
  const flashTimeoutsRef = useRef<Record<string, ReturnType<typeof setTimeout>>>({});

  const flushQuotes = useCallback(() => {
    frameRef.current = null;
    const quotes = pendingQuotesRef.current;
    pendingQuotesRef.current = {};
    if (Object.keys(quotes).length === 0) return;

    setLivePrices(prev => ({ ...prev, ...quotes }));
    const flashes: Record<string, 'up' | 'down'> = {};
    Object.values(quotes).forEach(quote => {
      if (quote.price === null) return;
      const oldPrice = prevPricesRef.current[quote.ticker];
      if (oldPrice !== undefined && quote.price !== oldPrice) {
        flashes[quote.ticker] = quote.price > oldPrice ? 'up' : 'down';
        if (flashTimeoutsRef.current[quote.ticker]) clearTimeout(flashTimeoutsRef.current[quote.ticker]);
        flashTimeoutsRef.current[quote.ticker] = setTimeout(() => {
          setPriceFlash(prev => {
            const next = { ...prev };
            delete next[quote.ticker];
            return next;
          });
          delete flashTimeoutsRef.current[quote.ticker];
        }, 1000);
      }
      prevPricesRef.current[quote.ticker] = quote.price;
    });
    if (Object.keys(flashes).length > 0) setPriceFlash(prev => ({ ...prev, ...flashes }));
  }, []);

  const connect = useCallback(() => {
    const protocols = getAppWebSocketProtocols();
    if (!protocols || stoppedRef.current) return;
    // Clear any pending reconnect attempt
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }

    // Close existing connection before creating a new one
    if (wsRef.current && wsRef.current.readyState !== WebSocket.CLOSED) {
      wsRef.current.close();
    }

    const ws = new WebSocket(WS_URL, protocols);
    wsRef.current = ws;

    ws.onopen = () => {
      console.log('[WS] Connected');
      setConnected(true);
      reconnectAttemptsRef.current = 0;
    };

    ws.onmessage = (event) => {
      try {
        const quote = JSON.parse(event.data) as LiveQuote;
        pendingQuotesRef.current[quote.ticker] = quote;
        if (frameRef.current === null) frameRef.current = requestAnimationFrame(flushQuotes);
      } catch (err) {
        console.error('[WS] Failed to parse message:', err);
      }
    };

    ws.onerror = (err) => {
      console.error('[WS] Error', err);
    };

    ws.onclose = (event) => {
      console.log(`[WS] Closed (code: ${event.code}, reason: ${event.reason})`);
      setConnected(false);

      // Only reconnect if not an intentional close (code 1000)
      if (event.code === 4401) {
        stoppedRef.current = true;
        invalidateAppToken();
        return;
      }

      if (event.code !== 1000 && !stoppedRef.current && reconnectAttemptsRef.current < 10) {
        const attempts = reconnectAttemptsRef.current;
        // Exponential backoff: 1s, 2s, 4s, 8s, max 30s
        const delay = Math.min(1000 * Math.pow(2, attempts), 30000);
        console.log(`[WS] Reconnecting in ${delay}ms (attempt ${attempts + 1})`);
        reconnectAttemptsRef.current = attempts + 1;
        reconnectTimeoutRef.current = setTimeout(connect, delay);
      }
    };
  }, [flushQuotes]);

  useEffect(() => {
    stoppedRef.current = false;
    connect();

    return () => {
      // Cleanup on unmount
      stoppedRef.current = true;
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (frameRef.current !== null) cancelAnimationFrame(frameRef.current);
      Object.values(flashTimeoutsRef.current).forEach(clearTimeout);
      if (wsRef.current) {
        wsRef.current.close(1000, 'Component unmounted');
      }
    };
  }, [connect]);

  return { livePrices, priceFlash, connected };
}
