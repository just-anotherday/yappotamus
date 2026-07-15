# Finnhub Migration Guide

**Date:** 2026-06-18  
**Author:** Stock Data Dashboard Team  
**Status:** Active  

---

## Overview

This document describes the complete migration from `yfinance` to the **Finnhub API** (free tier) for all market data, news ingestion, and real-time WebSocket functionality.

### Why Finnhub?

- **Reliable REST API** with documented endpoints
- **Real-time WebSocket** streaming for live price data
- **Free tier** sufficient for dashboard use: 60 calls/min REST, 30 msg/sec WebSocket
- **No blocking I/O** — all calls are async-compatible

---

## Architecture Overview

### Before (yfinance)

```
[Frontend] → [FastAPI Routers] → [yfinance_service.py] → yfinance (blocking, no rate control)
                             → [news_ingestion_service.py] → yfinance Ticker.news (blocking)
                             → [market_data_service.py] → yfinance WebSocket (unreliable)
```

### After (Finnhub)

```
[Frontend] → [FastAPI Routers] → [finnhub_service.py] → Finnhub REST API (async, rate-limited)
                             → [news_ingestion_service.py] → Finnhub company_news (async)
                             → [market_data_service.py] → Finnhub WebSocket (reliable)
```

---

## File Changes Summary

| File | Action | Description |
|------|--------|-------------|
| `.env.example` | Updated | Replaced `YFINANCE_ENABLED` with `FINNHUB_API_KEY=YAPPY PASTE API KEY HERE` |
| `.env` | Updated | Added Finnhub API key placeholder, removed yfinance config |
| `requirements.txt` | Updated | Removed `yfinance`, added `finnhub-python`, `httpx` |
| `backend/services/finnhub_service.py` | **NEW** | Core Finnhub REST API client with rate limiting + retry |
| `backend/services/yfinance_service.py` | Replaced | Backward-compatible shim re-exporting from `finnhub_service` |
| `backend/services/market_data_service.py` | Rewritten | Replaced yfinance WebSocket with Finnhub WebSocket |
| `backend/services/news_ingestion_service.py` | Rewritten | Replaced yfinance news fetcher with Finnhub `company_news` |
| `backend/routers/stock.py` | Updated | Converted from sync threadpool to native async Finnhub calls |
| `backend/routers/watchlist.py` | Updated | Updated imports + timeout handling for async batch fetches |
| `backend/main.py` | Updated | Added `FINNHUB_API_KEY` to required env vars validation |

---

## Finnhub Endpoints Used

| Endpoint | Purpose | Free Tier Limit |
|----------|---------|-----------------|
| `/quote` | Real-time price quote (OHLC + change) | 60 calls/min |
| `/stock-profile2` | Company profile + fundamentals | 60 calls/min |
| `/symbol-search` | Search valid ticker symbols | 60 calls/min |
| `/company-news2` | Market news for a specific ticker | 60 calls/min |
| WebSocket (`wss://ws.finnhub.io?id={KEY}`) | Real-time trade streaming | 30 msg/sec |

---

## Rate Limiting Strategy

### REST API (60 calls/min)

- Implemented via async `_rate_limiter()` in `finnhub_service.py`
- Minimum interval: **1.05 seconds** between calls (~57 calls/min, safely under limit)
- Uses `asyncio.Lock` for thread safety across concurrent requests

### WebSocket (30 msg/sec)

- Finnhub handles rate limiting server-side
- Client subscribes only to watchlist tickers (max ~20 typical)
- Reconnect backoff: 1s → 2s → 4s → ... → max 30s

### Retry Policy

All REST API calls wrapped with `tenacity.retry`:
- Max attempts: 3
- Wait: exponential backoff (0.5s, 1s, 2s, max 5s)
- Retries on: `TimeoutError`, `ConnectionError`, any unhandled exception

---

## Free Tier Limitations & Workarounds

| Feature | yfinance | Finnhub (Free) | Workaround |
|---------|----------|----------------|------------|
| 52-week high/low | ✅ | ❌ | Use day's high/low as proxy; historical API available on paid tier |
| Analyst ratings | ✅ | ❌ | Set to `None` / "N/A" |
| Short interest data | ✅ | ❌ | Defaults to 0 |
| Insider/institution ownership | ✅ | ❌ | Defaults to 0 |
| CEO name | ✅ | ❌ | Not available on free tier |
| Company summary text | ✅ | ❌ | Finnhub doesn't provide this field |
| Real-time quotes | ✅ (delayed) | ✅ (near real-time) | Better than yfinance |
| Company news | ✅ | ✅ | Same functionality |
| WebSocket streaming | Unreliable | Reliable | Improved stability |

---

## Configuration

### Environment Variables

```env
# Required
DATABASE_URL=postgresql://postgres:password@localhost:5432/news
FINNHUB_API_KEY=<your-api-key>

# Optional (defaults shown)
CORS_ORIGINS=http://localhost:3000
WS_RECONNECT_BACKOFF_S=1
WS_RECONNECT_MAX_BACKOFF_S=30
QUOTE_CACHE_MAX_SIZE=256
```

### Getting an API Key

1. Visit https://finnhub.io/register
2. Create a free account
3. Navigate to https://finnhub.io/dashboard
4. Copy your API key
5. Paste into `.env` replacing `YAPPY PASTE API KEY HERE`

---

## Testing Checklist

- [ ] Set `FINNHUB_API_KEY` in `.env`
- [ ] Run `pip install -r requirements.txt`
- [ ] Start PostgreSQL: `docker compose up -d postgres` (or equivalent)
- [ ] Start backend: `uvicorn backend.main:app --reload`
- [ ] Verify health endpoint: `curl http://localhost:8000/health`
- [ ] Test stock quote: `curl http://localhost:8000/api/stock/AAPL`
- [ ] Test watchlist: `curl http://localhost:8000/api/watchlist`
- [ ] Test adding ticker: `curl -X POST http://localhost:8000/api/watchlist/add -H "Content-Type: application/json" -d '{"ticker":"TSLA"}'`
- [ ] Verify WebSocket connects: Open frontend at `http://localhost:3000`
- [ ] Check logs for Finnhub subscription confirmations
- [ ] Wait 15+ minutes and verify news scheduler runs

---

## Database Notes

The database schema (`news_articles`, `watchlist`) remains **unchanged**. No migration needed. The Finnhub data maps to the same columns used by yfinance.

### Fields Populated Differently

| DB Column | yfinance Source | Finnhub Source |
|-----------|----------------|----------------|
| `title` | article content.title | article headline |
| `summary` | article content.summary | article summary |
| `provider_name` | article provider.displayName | article source |
| `article_url` | clickThroughUrl or canonicalUrl | article url |
| `thumbnail_url` | thumbnail.originalUrl | article image |
| `pub_date` | pubDate (ISO or timestamp) | datetime (Unix timestamp) |
| `raw_json` | Full yfinance article dict | Full Finnhub article dict |

---

## Troubleshooting

### "Missing required environment variable: FINNHUB_API_KEY"

- Ensure `.env` exists in project root with a valid key
- Check for leading/trailing whitespace

### WebSocket connection fails

- Verify API key is valid at https://finnhub.io/dashboard
- Check logs for `[MarketData] Finnhub WebSocket connected.` message
- Rate limit exceeded → wait 60 seconds for reset

### Stock data returns zeros

- Finnhub free tier doesn't support all symbols (US equities only)
- Test with major tickers: AAPL, MSFT, GOOGL, AMZN, TSLA
- Symbol validation: `curl "http://localhost:8000/api/stock/AAPL"`

### News not appearing

- Scheduler runs 8 AM - 6 PM EST only
- Check logs for `[NewsScheduler]` entries
- Manually trigger by adding a new ticker to watchlist

---

## Future Improvements (Paid Tier)

If upgrading to Finnhub paid tier:

1. Enable `/stock-time-series` for 52-week high/low data
2. Enable `/target-price` for analyst target prices
3. Enable `/insider-transactions` for insider ownership tracking
4. Increase rate limit allowance (remove `_rate_limiter` delay)
5. Add `/financial-statement` for fundamental analysis
