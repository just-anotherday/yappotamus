# Finnhub API Performance & Integration Reference

**Date:** 2026-06-18
**Status:** Active

---

## 1. Rate Limits (Free Tier)

### REST API
| Metric | Limit | Notes |
|--------|-------|-------|
| Calls per minute | 60 | Global limit, all endpoints combined |
| Safe call rate | ~1/sec | Implemented via `_rate_limiter()` with 1.05s interval |
| Concurrent connections | 2-3 | Python SDK supports connection pooling |

### WebSocket
| Metric | Limit | Notes |
|--------|-------|-------|
| Messages per second | 30 | Subscribe/unsubscribe + incoming trades |
| Max subscriptions | Unlimited (server-side) | Free tier recommended: ≤50 symbols |
| Reconnect rate | Unrestricted | Exponential backoff prevents abuse |

---

## 2. Endpoint Latency (Observed)

| Endpoint | Typical Response Time | Timeout Setting |
|----------|----------------------|-----------------|
| `/quote` | 80-150ms | 15s |
| `/stock-profile2` | 100-200ms | 15s |
| `/symbol-search` | 60-120ms | 15s |
| `/company-news2` | 150-400ms | 15s |
| WebSocket connect | 300-800ms | N/A (handled by backoff) |

---

## 3. Batch Fetch Performance

When fetching a watchlist of **N tickers**, the total time is approximately:

```
Total = N × (endpoint_latency + rate_limit_delay)
       = N × (~200ms + 1050ms)
       = ~1250ms per ticker
```

**Examples:**
- 5 tickers: ~6.3 seconds
- 10 tickers: ~12.5 seconds
- 20 tickers: ~25 seconds

**Watchlist batch timeout:** Set to **45 seconds** — supports up to 30+ tickers before timing out.

---

## 4. Retry Behavior

All REST API calls use tenacity retry with these parameters:

```python
tenacity.retry(
    stop=tenacity.stop_after_attempt(3),        # Max 3 attempts
    wait=tenacity.wait_exponential(multiplier=0.5, max=5),  # 0.5s → 1s → 2s (cap 5s)
    retry=tenacity.retry_if_exception_type((TimeoutError, ConnectionError)),
    reraise=True,
)
```

**Worst case per ticker:** 3 attempts × 5s wait = 15s of retries before failure.

---

## 5. WebSocket Message Flow

### Connection Lifecycle
```
Client → wss://ws.finnhub.io?id={API_KEY}
  → On Open: Subscribe to all watchlist tickers (1 msg/ticker)
  → On Trade: Parse {"type":"trade","symbol":"AAPL","price":150.25,"volume":100}
  → On Error: Log error, continue listening
  → On Close: Trigger reconnect loop with exponential backoff
```

### Backoff Schedule
| Attempt | Wait Time | Cumulative |
|---------|-----------|------------|
| 1st reconnect | 1s | 1s |
| 2nd reconnect | 2s | 3s |
| 3rd reconnect | 4s | 7s |
| 4th reconnect | 8s | 15s |
| 5th+ reconnect | 30s (capped) | 45s+ |

---

## 6. Cache Strategy

### Quote Cache (`latest_quotes`)
- **Type:** In-memory dictionary, thread-safe via `threading.RLock()`
- **Max size:** 256 entries (configurable via `QUOTE_CACHE_MAX_SIZE`)
- **Eviction:** LRU-style — oldest entries removed when cap reached
- **Pruning:** Automatically removes quotes for unsubscribed tickers

### Rate Limiter State
- **Type:** Async lock with timestamp tracking
- **Scope:** Global singleton per process
- **Thread safety:** Uses `asyncio.Lock` for concurrency control

---

## 7. News Ingestion Scheduler

| Parameter | Value | Source |
|-----------|-------|--------|
| Interval | 900s (15 minutes) | `_scheduler_interval_seconds` |
| Active window | 8 AM - 6 PM EST | `ZoneInfo("US/Eastern")` |
| Articles per ticker | 25 | `limit=25` in scheduler call |
| Date range | Last 7 days | `start_ts = current_ts - 86400*7` |

**REST calls per cycle:** N tickers × 1 call each (plus rate limiter delays)
- 5 tickers: ~6.3s per cycle
- Total daily cycles: ~38 cycles/day (10 active hours ÷ 15 min)

---

## 8. Error Handling Matrix

| Error Type | Handler | User Impact |
|------------|---------|-------------|
| Missing API key | Startup failure with clear error | Service won't start |
| Rate limit exceeded (429) | Retry with exponential backoff | Delayed response |
| Timeout (>15s) | HTTPException 504 | User sees timeout error |
| Invalid ticker | HTTPException 404 | User informed ticker not found |
| WebSocket disconnect | Auto-reconnect with backoff | Brief data gap (1-30s) |
| Database unavailable | Warning logged, service continues | Watchlist/news features degraded |

---

## 9. Monitoring & Logging

### Key Log Prefixes
- `[Finnhub]` — REST API operations (quote/profile/search)
- `[MarketData]` — WebSocket lifecycle + trade processing
- `[NewsIngestion]` — News fetch + persist operations
- `[NewsScheduler]` — Background scheduler cycles
- `[RateLimit]` — Client-side rate limiting triggers
- `[Watchlist]` — CRUD operations

### Health Checks
```bash
# Service liveness
curl http://localhost:8000/health

# Expected response:
{"status": "ok", "service": "Stock Dashboard"}
```

---

## 10. Scaling Considerations

### Current Architecture Limits (Free Tier)
- **Max practical tickers:** ~20-30 (rate-limited REST + WebSocket subscriptions)
- **Simultaneous users:** Limited by rate limiting middleware (60 req/min/IP)
- **News ingestion frequency:** 15 minutes minimum (to avoid exhausting API quota)

### Upgrade Path (Paid Tier: $99/mo)
- Rate limit increases to 300 calls/min → Remove `_rate_limiter()` delay
- Access to `/stock-time-series` → 52-week range data
- Access to `/target-price` → Analyst ratings + price targets
- Access to `/insider-transactions` → Ownership tracking
- WebSocket: 60 msg/sec limit (2x capacity)
