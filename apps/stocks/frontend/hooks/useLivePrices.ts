// ==============================================================================
// HOOK: useLivePrices - WebSocket connection + price flash effect + auto-reconnect
// ==============================================================================

import { useEffect, useState, useRef, useCallback } from 'react';
import { WS_URL } from '@/types/stock';
import type { LiveQuote } from '@/types/stock';

export function useLivePrices() {
  const [livePrices, setLivePrices] = useState<Record<string, LiveQuote>>({});
  const [priceFlash, setPriceFlash] = useState<Record<string, 'up' | 'down'>>({});
  const [connected, setConnected] = useState<boolean>(false);
  const prevPricesRef = useRef<Record<string, number>>({});
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectAttemptsRef = useRef<number>(0);

  const connect = useCallback(() => {
    // Clear any pending reconnect attempt
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }

    // Close existing connection before creating a new one
    if (wsRef.current && wsRef.current.readyState !== WebSocket.CLOSED) {
      wsRef.current.close();
    }

    const ws = new WebSocket(WS_URL);
    wsRef.current = ws;

    ws.onopen = () => {
      console.log('[WS] Connected');
      setConnected(true);
      reconnectAttemptsRef.current = 0;
    };

    ws.onmessage = (event) => {
      try {
        const quote = JSON.parse(event.data) as LiveQuote;
        setLivePrices((prev) => ({
          ...prev,
          [quote.ticker]: quote,
        }));

        // Detect price direction for flash effect
        const tickerKey = quote.ticker;
        const newPrice = quote.price;
        if (newPrice !== null) {
          const oldPrice = prevPricesRef.current[tickerKey];
          if (oldPrice !== undefined) {
            if (newPrice > oldPrice) {
              setPriceFlash((prev) => ({ ...prev, [tickerKey]: 'up' }));
            } else if (newPrice < oldPrice) {
              setPriceFlash((prev) => ({ ...prev, [tickerKey]: 'down' }));
            }
            setTimeout(() => {
              setPriceFlash((prev) => {
                const next = { ...prev };
                delete next[tickerKey];
                return next;
              });
            }, 1000);
          }
          prevPricesRef.current[tickerKey] = newPrice;
        }
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
      if (event.code !== 1000) {
        const attempts = reconnectAttemptsRef.current;
        // Exponential backoff: 1s, 2s, 4s, 8s, max 30s
        const delay = Math.min(1000 * Math.pow(2, attempts), 30000);
        console.log(`[WS] Reconnecting in ${delay}ms (attempt ${attempts + 1})`);
        reconnectAttemptsRef.current = attempts + 1;
        reconnectTimeoutRef.current = setTimeout(connect, delay);
      }
    };
  }, []);

  useEffect(() => {
    connect();

    return () => {
      // Cleanup on unmount
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (wsRef.current) {
        wsRef.current.close(1000, 'Component unmounted');
      }
    };
  }, [connect]);

  return { livePrices, priceFlash, connected };
}
