# Finnhub Integration Architecture Guide

## Overview

This document describes the Finnhub-first, yfinance-fallback hybrid architecture powering the Stock Data Dashboard.

### Why Hybrid?

Finnhub's free tier covers US equities well but has gaps:
- No company profiles for ETFs, indices, or non-US symbols
- Limited analyst target data on free tier
- 60 REST calls/min rate limit

yfinance fills these gaps as a fallback, ensuring coverage for all symbol types.

---

## Architecture Diagram

```
Frontend (Next.js)
     │
     ▼
FastAPI Routers (/api/stock, /api/watchlist)
     │
     ▼
yfinance_service.py (shim layer)
     │
     ├──► hybrid_data_service.py (orchestrator)
     │        │
     │        ├──► finnhub_service.py  (primary, tags data_source: "fh")
     │        │
     │        └──► yfinance_fallback.py (fallback, tags data_source: "yf")
```

---

## Service Layer Breakdown

### 1. `finnhub_service.py` — Primary Data Source
- Uses `finnhub-python` SDK
- Endpoints: `/quote`, `/stock-profile2`, `/symbol-search`
- Async with rate limiting (0.5s interval between calls)
- Batch concurrency of 6 with staggered starts
- Retry logic via tenacity (3 attempts, exponential backoff)

### 2. `yfinance_fallback.py` — Fallback Data Source
- Pure yfinance implementation
- Used for: ETFs (SPY, QQQ, etc.), non-US symbols, Finnhub failures
- Adds 1s delay per call to match Finnhub rate-limit pace
- Produces identical output shape as finnhub_service

### 3. `hybrid_data_service.py` — Orchestrator
- Tries Finnhub first for US equities
- Routes known ETFs/indices directly to yfinance
- Falls back to yfinance if Finnhub returns no data or errors
- Tags every result with `data_source: "fh"` or `data_source: "yf"`

### 4. `yfinance_service.py` — Backward-Compatible Shim
- Re-exports from hybrid_data_service
- Existing imports continue to work without changes
- Transparent routing through hybrid layer

---

## Data Source Tagging

Every stock data response includes a `data_source` field:

| Value | Source       | Frontend Badge |
|-------|--------------|----------------|
| `fh`  | Finnhub      | Blue "FH"      |
| `yf`  | yfinance     | Purple "YF"    |

This allows the frontend to display which data source served each ticker.

---

## Rate Limits & Performance

### Free Tier Limits (https://finnhub.io/docs/api/rate-limit)
- **REST API**: 60 calls/min
- **WebSocket**: 30 messages/sec
- **Some endpoints**: 1 request/sec

### Our Strategy
- Rate limiter enforces 0.5s minimum interval between API calls
- Batch concurrency of 6 (quote + profile = ~12 calls per batch)
- Stagger delay of 0.3s between batches
- Estimated throughput: ~30 tickers in 12-15 seconds

### Performance Benchmarks
| Operation          | yfinance (old) | Finnhub+fallback (new) |
|--------------------|---------------|------------------------|
| Single ticker      | ~2-3s         | ~1-2s                  |
| 10-ticker batch    | ~15-20s       | ~8-12s                 |
| 30-ticker batch    | ~45-60s       | ~25-35s                |
| ETF fallback       | N/A           | ~2-3s                  |

---

## Free Tier Limitations & Workarounds

### What's Missing on Free Tier
1. **Analyst targets** (mean/median/high/low price targets) — set to `None`
2. **Forward PE ratio** — set to `None`
3. **52-week high/low** — approximated with day high/low from quote
4. **Short interest data** — defaults to 0
5. **Institutional/insider ownership** — defaults to 0
6. **CEO name** — set to `None`
7. **Full-time employees** — set to `None`

### Workarounds
- Composite risk score is computed from available data (beta, 52-week range)
- yfinance fallback provides richer fundamentals when Finnhub fails
- News ingestion uses Finnhub `/company-news2` which IS available on free tier

---

## Configuration

### Environment Variables
```env
FINNHUB_API_KEY=your_key_here          # Required (get from finnhub.io/dashboard)
DATABASE_URL=postgresql://...          # Required
CORS_ORIGINS=http://localhost:3000     # Required for frontend
WS_RECONNECT_BACKOFF_S=1              # Optional
WS_RECONNECT_MAX_BACKOFF_S=30         # Optional
QUOTE_CACHE_MAX_SIZE=256              # Optional
```

### Known ETF/Index Symbols
The following symbols always route to yfinance (skip Finnhub):
`SPY`, `QQQ`, `VOO`, `IWM`, `DIA`, `VWO`, `VEA`, `VGT`, `XLK`, `XLF`, `SPCX`

---

## Testing Endpoints

### Single Ticker (US Equity — Finnhub)
```bash
curl http://localhost:8000/api/stock/AAPL
```

### Single Ticker (ETF — yfinance fallback)
```bash
curl http://localhost:8000/api/stock/SPY
```

### Watchlist Batch
```bash
curl http://localhost:8000/api/watchlist
```

### Add Ticker
```bash
curl -X POST http://localhost:8000/api/watchlist/add \
  -H "Content-Type: application/json" \
  -d '{"ticker": "TSLA"}'
```

---

## Files Modified/Created

| File                              | Status       | Purpose                          |
|-----------------------------------|-------------|----------------------------------|
| `backend/services/finnhub_service.py`     | Created     | Primary Finnhub API service      |
| `backend/services/yfinance_fallback.py`   | Created     | yfinance fallback service        |
| `backend/services/hybrid_data_service.py` | Created     | Hybrid orchestrator              |
| `backend/services/yfinance_service.py`    | Rewritten   | Backward-compatible shim         |
| `backend/models/stock.py`               | Modified    | Added `data_source` field        |
| `backend/routers/stock.py`              | Modified    | Use hybrid service               |
| `backend/routers/watchlist.py`          | Modified    | Use hybrid service               |
| `frontend/types/stock.ts`               | Modified    | Added `DataSource` type          |
| `requirements.txt`                          | Modified    | Added yfinance fallback dep      |
| `.env.example`                            | Modified    | API key placeholder              |

---

## Troubleshooting

### Finnhub Returns Empty Quote
- Symbol may not be a US-traded equity
- Check that FINNHUB_API_KEY is valid and not expired
- Verify the symbol exists on finnhub.io/dashboard

### Rate Limit Exceeded (HTTP 429)
- Reduce batch concurrency in `finnhub_service.py`
- Increase `_min_interval` from 0.5s to 1.0s
- Check if background tasks are making duplicate calls

### yfinance Fallback Slow
- yfinance has no official rate limit but can be throttled
- 1s delay is built-in; remove only if Finnhub coverage improves
