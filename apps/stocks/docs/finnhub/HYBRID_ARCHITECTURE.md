# Finnhub + yfinance Hybrid Architecture Reference

## Table of Contents
1. [Architecture Overview](#architecture-overview)
2. [Data Flow](#data-flow)
3. [Rate Limits & Performance](#rate-limits--performance)
4. [API Endpoints](#api-endpoints)
5. [Free Tier Limitations](#free-tier-limitations)
6. [Enrichment Strategy](#enrichment-strategy)
7. [Configuration](#configuration)
8. [Troubleshooting](#troubleshooting)

---

## Architecture Overview

The Stock Data Dashboard uses a **hybrid data architecture** that combines Finnhub (primary) with yfinance (enrichment + fallback):

```
                        ┌─────────────────────┐
                        │   Frontend (Next.js) │
                        └──────────┬──────────┘
                                   │
                    ┌──────────────▼──────────────┐
                    │  FastAPI Backend (Port 8000)  │
                    └──────────┬──────────────────┘
                               │
              ┌────────────────┼────────────────┐
              │                │                │
    ┌─────────▼─────────┐ ┌───▼───────┐ ┌──────▼───────┐
    │ hybrid_data_      │ │ news_     │ │ market_data_  │
    │ service.py        │ │ ingestion │ │ service.py    │
    │ (Primary + YF)    │ │ _service  │ │ (WebSocket)   │
    └─────────┬─────────┘ └───┬───────┘ └──────┬───────┘
              │               │                │
       ┌──────▼──────┐  ┌────▼─────┐     ┌────▼─────┐
       │ finnhub_    │  │ finnhub  │     │ Finnhub  │
       │ service.py  │  │ API key  │     │ WebSocket│
       │ (REST)      │  │ .env     │     │ Stream   │
       └──────┬──────┘  └──────────┘     └──────────┘
              │
       ┌──────▼──────┐
       │ yfinance_   │
       │ fallback.py │
       │ (enrichment)│
       └─────────────┘
```

### Component Responsibilities

| Component | Purpose |
|-----------|---------|
| `hybrid_data_service.py` | Orchestrates Finnhub primary + yfinance enrichment |
| `finnhub_service.py` | Finnhub REST API client (quotes, profiles, news) |
| `yfinance_fallback.py` | yfinance fallback for ETFs/indices + fundamental enrichment |
| `news_ingestion_service.py` | Fetches and persists Finnhub news articles to PostgreSQL |
| `market_data_service.py` | WebSocket manager for real-time price streaming |

---

## Data Flow

### Single Ticker Request (`GET /api/stock/{ticker}`)

1. Frontend calls `/api/stock/AAPL`
2. Router → `hybrid_data_service.get_hybrid_stock_price("AAPL")`
3. **Step 1:** Try Finnhub `/quote` + `/company-profile2` endpoints
4. **Step 2:** If Finnhub returns valid data:
   - Check for fundamental gaps (PE, 52w range, short interest, etc.)
   - If gaps exist → fetch yfinance data in background thread pool
   - Merge yfinance values into result; track enriched fields in `yf_enriched_fields[]`
   - Return with `data_source: "fh"`
5. **Step 3:** If Finnhub fails or symbol is ETF/index → full yfinance fallback
   - Return with `data_source: "yf"`

### Batch Watchlist Request (`GET /api/watchlist`)

1. Frontend calls `/api/watchlist` (no params) or `/api/watchlist?tickers=AAPL,MSFT,...`
2. Router → `hybrid_data_service.get_hybrid_batch_prices(tickers)`
3. Split tickers into two groups:
   - **Finnhub candidates:** Regular US equities (batched in groups of 6, staggered)
   - **yfinance-only:** Known ETFs/indices (SPY, QQQ, VOO, etc.)
4. Both groups run concurrently via `asyncio.gather()`
5. Finnhub group respects rate limits (0.5s interval between calls)
6. yfinance group runs in thread pool executor (non-blocking)

---

## Rate Limits & Performance

### Finnhub Free Tier

| Metric | Limit |
|--------|-------|
| REST API calls | 60 per minute |
| WebSocket messages | 30 per second |
| Safe average (with batches) | ~1 call/second |

### Performance Optimizations

- **Batch concurrency:** 6 tickers processed concurrently per batch
- **Stagger delay:** 300ms between Finnhub batches to avoid bursting
- **Rate limiter:** Async lock with 0.5s minimum interval between API calls
- **Thread pool executor:** yfinance enrichment runs in 6-worker thread pool (non-blocking)
- **In-memory cache:** Per-request-cycle cache avoids redundant fetches
- **Parallel execution:** Finnhub + yfinance groups run concurrently

### Typical Response Times

| Scenario | Time |
|----------|------|
| Single ticker (Finnhub hit, no enrichment needed) | ~1-2s |
| Single ticker (Finnhub + yfinance enrichment) | ~3-5s |
| 30-ticker watchlist (mixed sources) | ~15-30s |
| Full yfinance fallback (ETF only) | ~2-4s |

---

## API Endpoints

### Stock Data

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/stock/{ticker}` | Fetch stock data for a single ticker |
| GET | `/api/watchlist` | Fetch watchlist with full analyst-grade data |
| POST | `/api/watchlist/add` | Add ticker to persistent watchlist |
| DELETE | `/api/watchlist/{ticker}` | Remove ticker from watchlist |

### News

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/news` | Fetch persisted news articles |
| GET | `/api/news/{ticker}` | Fetch news for specific ticker |

---

## Free Tier Limitations

### Fields NOT Available from Finnhub Free Tier

The following fields always return `0`/`None`/`"N/A"` from Finnhub free tier. These are automatically enriched by yfinance:

| Field | Finnhub Value | yfinance Value |
|-------|---------------|----------------|
| `forward_pe` | `0` | Actual PE ratio |
| `fifty_two_week_high` | Day high (inaccurate) | Real 52-week high |
| `fifty_two_week_low` | Day low (inaccurate) | Real 52-week low |
| `short_percent_of_float` | `0.0` | Actual short % |
| `shares_short` | `0` | Actual short shares |
| `heldPercentInsiders` | `0.0` | Insider ownership % |
| `heldPercentInstitutions` | `0.0` | Institution ownership % |
| `target_mean_price` | `None` | Analyst mean target |
| `target_median_price` | `None` | Analyst median target |
| `target_high_price` | `None` | Analyst high target |
| `target_low_price` | `None` | Analyst low target |
| `recommendationKey` | `"N/A"` | Buy/Hold/Sell rating |
| `numberOfAnalystOpinions` | `0` | Analyst count |
| `averageAnalystRating` | `None` | Rating string |
| `longBusinessSummary` | Empty/missing | Business description |
| `ceo_name` | `None` | CEO name |
| `full_time_employees` | `None` | Employee count |

### Fields Available from Finnhub Free Tier

| Field | Source | Notes |
|-------|--------|-------|
| `current_price` | `/quote` endpoint | Real-time price |
| `previous_close` | `/quote` endpoint | Previous close price |
| `change/change_percent` | Computed from quote | Price change |
| `company_name` | `/company-profile2` | Company name |
| `sector/industry` | `/company-profile2` | Sector and industry |
| `market_cap` | `/company-profile2` | Market capitalization |
| `beta` | `/company-profile2` | Beta value |
| News articles | `/company-news` | Up to 30/ticker |

---

## Enrichment Strategy

### How It Works

When Finnhub returns data but with fundamental gaps, the hybrid service:

1. **Detects gaps:** Checks each field in `FUNDAMENTAL_GAP_FIELDS` for gap values
2. **Fetches yfinance:** Runs `get_stock_price_yf()` in a thread pool (non-blocking)
3. **Merges selectively:** Only replaces Finnhub values where:
   - Finnhub value is a gap (0, None, "N/A", etc.)
   - yfinance has valid data
4. **Tracks enrichment:** Records which fields were enriched in `yf_enriched_fields[]`
5. **Preserves source tag:** `data_source` remains `"fh"` since primary source is Finnhub

### Gap Detection Logic

```python
# Simplified example
def _is_gap_value(value, field):
    if value is None: return True
    if isinstance(value, str) and value in ("N/A", ""): return True
    if field == "forward_pe" and value == 0: return True
    if field == "fifty_two_week_high" and value == 0: return True
    # ... (sees full logic in hybrid_data_service.py)
```

### Response Example

```json
{
  "ticker": "AAPL",
  "current_price": 198.50,
  "data_source": "fh",
  "yf_enriched_fields": [
    "forward_pe",
    "fifty_two_week_high",
    "fifty_two_week_low",
    "short_percent_of_float",
    "target_mean_price",
    "recommendation_key"
  ],
  "forward_pe": 32.5,
  "fifty_two_week_high": 205.0,
  ...
}
```

---

## Configuration

### Environment Variables (`.env`)

```ini
# Finnhub API Key (Required)
FINNHUB_API_KEY=your_api_key_here

# Database URL (Required)
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/news

# Rate Limiting (Optional)
FINNHUB_RATE_LIMIT_PER_MIN=60
FINNHUB_WS_RATE_LIMIT_PER_SEC=30
```

### Getting a Finnhub API Key

1. Visit https://finnhub.io/dashboard
2. Sign up for a free account
3. Copy your API key from the dashboard
4. Paste into `.env` at `FINNHUB_API_KEY`

---

## Troubleshooting

### Common Issues

| Problem | Cause | Solution |
|---------|-------|----------|
| All tickers return yfinance data | Missing/invalid API key | Check `FINNHUB_API_KEY` in `.env` |
| 429 Too Many Requests | Rate limit exceeded | Reduce batch size or increase interval |
| News ingestion fails | Wrong table schema | Run `python scripts/migrate_news_table.py` |
| 504 Timeout on large watchlists | Too many tickers | Increase `BATCH_TIMEOUT` in watchlist router |
| Empty profile for valid ticker | Symbol not recognized by Finnhub | Check with `/api/stock/search?q=TICKER` |

### Debug Logging

Enable debug logging to trace data flow:

```bash
python -c "import logging; logging.basicConfig(level=logging.DEBUG)" 
```

Key log prefixes:
- `[Finnhub]` - Finnhub REST API calls
- `[Hybrid]` - Hybrid orchestration (routing, enrichment)
- `[NewsScheduler]` - Background news ingestion
- `[Watchlist]` - Watchlist operations

### Migration Script

To fix the news_articles table schema:

```bash
.venv\Scripts\python scripts/migrate_news_table.py
```

This will:
1. Check if old `headline` column exists
2. Drop the old table if needed
3. Recreate with Finnhub-aligned schema (title, summary, provider_name, article_url, thumbnail_url)
