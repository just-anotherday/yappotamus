# Stock Data Dashboard

A full-stack stock market dashboard built with a **FastAPI** + **PostgreSQL** backend and **Next.js** frontend. It provides live price updates, persistent personal watchlists, Finnhub news ingestion, and optional AI analysis through Ollama or OpenAI.

## Tech Stack

| Layer | Technologies |
|-------|-------------|
| **Backend** | FastAPI, Python 3.12+, SQLAlchemy 2.x (async), asyncpg |
| **Database** | PostgreSQL (news articles + watchlist persistence) |
| **Frontend** | Next.js 16, TypeScript, React 19, Tailwind CSS |
| **Real-time** | WebSockets (yfinance live price streaming) |
| **External APIs** | Finnhub and yfinance (quotes, company data, and news) |

## Features

- **Stock Search** — Lookup any ticker for real-time quote + company fundamentals
- **Watchlist** — Persistent watchlist with real-time WebSocket price updates
- **Live Prices** — Sub-second price streaming via Yahoo Finance WebSockets
- **Market News** — Automated news ingestion (every 15 min during market hours) with full-text browsing per ticker
- **Dark/Light Theme** — Toggle between light and dark mode

## Project Structure

```
Stock Data Dashboard/
├── backend/                          # FastAPI backend
│   ├── main.py                       # App entry, lifespan, routes
│   ├── exceptions.py                 # Centralized exception handlers + logging
│   ├── config/                       # Database + watchlist configuration
│   │   ├── database.py               # SQLAlchemy async engine/session setup
│   │   └── watchlist.py              # Watchlist constants (max size, defaults)
│   ├── lib/                          # Shared utilities
│   │   └── tickers.py                # Ticker normalization + validation
│   ├── models/                       # SQLAlchemy ORM models
│   │   └── news.py                   # NewsArticle model + indexes
│   ├── routers/                      # API route modules
│   │   ├── watchlist.py              # Watchlist CRUD endpoints
│   │   ├── news.py                   # News query + ingestion endpoints
│   │   └── websocket.py              # WebSocket real-time price endpoint
│   └── services/                     # Business logic
│       ├── market_data_service.py    # Yahoo WebSocket listener (threaded)
│       ├── connection_manager.py     # WebSocket client connections
│       ├── news_ingestion_service.py # News upsert + scheduled ingestion
│       ├── news_query_service.py     # News query building with filters/sorting
│       ├── yfinance_service.py       # yfinance REST helper (ticker info, prices)
│       └── watchlist_service.py      # Watchlist CRUD via SQLAlchemy
├── frontend/                         # Next.js frontend
│   ├── app/                          # App Router pages + layout
│   │   ├── page.tsx                  # Home page entry
│   │   ├── components/HomeClient.tsx # Client-side home component
│   │   ├── news/page.tsx             # News listing page
│   │   └── news/[ticker]/page.tsx    # Per-ticker news detail
│   ├── components/                   # Shared React components
│   │   ├── ErrorBoundary.tsx         # Global error boundary
│   │   ├── watchlist/                # Watchlist table + tooltip
│   │   ├── stock/                    # Stock detail card
│   │   ├── news/                     # NewsCard, filters, pagination
│   │   └── ui/                       # Banners, headers, footer
│   ├── hooks/                        # Custom React hooks
│   │   ├── useWatchlist.ts           # Watchlist state + API calls
│   │   ├── useLivePrices.ts          # WebSocket price subscription
│   │   └── useNews.ts                # News fetching hook
│   ├── lib/                          # Frontend utilities
│   │   ├── api.ts                    # Centralized API client
│   │   └── formatters.ts             # Date + currency formatting
│   ├── types/                        # TypeScript interfaces
│   │   └── stock.ts                  # StockData, WatchlistItem, NewsArticle
│   └── public/                       # Static assets
├── docs/                             # Documentation
│   └── TECHNICAL_DEBT_REPORT.md      # Architecture audit + remediation log
├── requirements.txt                  # Python dependencies
└── README.md                         # This file
```

## Prerequisites

- **Python 3.12+** (matches the production Docker image)
- **Node.js 20+** and **npm**
- **PostgreSQL 14+** running locally (or accessible via connection string)
- A private app access token that you choose
- A Finnhub API key for Finnhub-backed quotes and news
- Ollama only if you want to use the default local AI provider

## Setup Instructions

### 1. Database

Create a PostgreSQL database:
```sql
CREATE DATABASE stock_dashboard;
```

### 2. Backend Setup

```bash
# Activate virtual environment
python -m venv .venv
.venv\Scripts\activate          # Windows CMD
.venv\Scripts\Activate.ps1      # Windows PowerShell
source .venv/bin/activate       # macOS/Linux

# Install dependencies
pip install -r requirements.txt
```

### 3. Environment Configuration

Copy the tracked example and edit the resulting `.env` file:

```powershell
Copy-Item .env.example .env
```

```env
# Private password chosen by you; this is not a Finnhub or OpenAI key
APP_ACCESS_TOKEN=generate_a_long_random_value

# Database
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/stock_dashboard

# Your Finnhub account API key
FINNHUB_API_KEY=replace_with_your_key

# Optional: fetch news every 15 minutes while this backend remains running
NEWS_SCHEDULER_ENABLED=true

# CORS (comma-separated origins)
CORS_ORIGINS=http://localhost:3000

# WebSocket reconnect backoff (seconds)
WS_RECONNECT_BACKOFF_S=1
WS_RECONNECT_MAX_BACKOFF_S=30

# Quote cache max entries
QUOTE_CACHE_MAX_SIZE=256
```

> **Security**: Never commit `.env` with real credentials. It is listed in `.gitignore`.

### 4. Start the Application

Run commands below from `apps/stocks`.

**Database migrations (required before backend deployment):**
```bash
python -m alembic upgrade head
```

Review generated migrations before applying them. Application startup verifies
connectivity but never creates, drops, or alters tables.

**Terminal 1 — Backend (includes the in-process AI worker):**
```bash
python run.py
```

**Terminal 2 — Frontend:**
```bash
cd frontend
npm install          # first time only
npm run dev
```

**Verification commands:**
```bash
python -m pip install -r requirements-test.txt
python -m pytest tests -q
cd frontend
npm run typecheck
npm run build
```

Open **http://localhost:3000** in your browser. The AI worker currently starts
inside the FastAPI lifespan; there is no separate worker process command. Enter
the same `APP_ACCESS_TOKEN` when the frontend asks you to unlock the app.

Search for a ticker and add it to the watchlist to use the app with your own
stocks. The watchlist is stored in PostgreSQL, subscribes the ticker to live
updates, and starts an initial background news fetch for that symbol.

## API Endpoints

### Stock Data
| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/stock/{symbol}` | Real-time quote + company info for a ticker |

### Watchlist (persistent in PostgreSQL)
| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/watchlist` | List all watchlist items |
| `POST` | `/api/watchlist/add` | Add a ticker to the watchlist |
| `DELETE` | `/api/watchlist/{ticker}` | Remove a ticker from the watchlist |
| `PUT` | `/api/watchlist/order` | Reorder watchlist items |

### News
| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/news` | Query news articles (supports filter, sort, pagination) |
| `GET` | `/news/tickers` | List tickers represented in stored news |
| `POST` | `/api/news/ingest` | Trigger manual news ingestion for default tickers |
| `POST` | `/api/news/ingest/{ticker}` | Ingest news for a specific ticker |

### Real-time Prices
| Protocol | Path | Description |
|----------|------|-------------|
| WebSocket | `/ws/prices` | Subscribe to live price updates for watchlist tickers |

## Architecture Notes

- **Database schema** is managed by Alembic (`python -m alembic upgrade head`); startup performs a connectivity check only.
- **News ingestion** is externally triggered every 15 minutes from 4 AM to 8 PM ET on weekdays, with hourly overnight/weekend coverage; the in-process scheduler remains a local-development option.
- Local automatic ingestion is disabled in `.env.example` to avoid unexpected Finnhub usage. Set `NEWS_SCHEDULER_ENABLED=true` and `FINNHUB_API_KEY` in `apps/stocks/.env`, then keep `python run.py` running. The scheduler runs in the FastAPI process every 15 minutes.
- For a one-time local run, keep FastAPI running and call `curl.exe -X POST -H "Authorization: Bearer YOUR_APP_ACCESS_TOKEN" http://localhost:8000/api/news/ingest`. Verify it through the response summary, backend `[NewsIngestion]` logs, and the `news_ingestion` object returned by `GET /health`.
- **WebSocket price streaming** uses a background thread to listen to Yahoo Finance WebSockets, then bridges events back to the FastAPI event loop.
- **Error handling** is centralized via FastAPI exception handlers (`backend/exceptions.py`).
- **API access is token protected** — use the `APP_ACCESS_TOKEN` value as a Bearer token for direct API calls.

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Backend won't start / DB error | Verify `DATABASE_URL` points to a running PostgreSQL instance |
| Frontend shows "Failed to fetch" | Ensure backend is running on port 8000 |
| No live price updates | Check WebSocket connection in browser dev tools; verify yfinance connectivity |
| News not populating | Set `FINNHUB_API_KEY`; then use the authenticated manual ingestion command in Architecture Notes and inspect `/health` |

## Known Limitations

- Local automatic news ingestion runs only while FastAPI is running and only when `NEWS_SCHEDULER_ENABLED=true`.
- Ollama analysis requires a separately running Ollama service with the configured model already downloaded.
- This is a personal/single-user deployment model protected by a shared app token, not a multi-tenant authorization system.
- `MarketDataService` remains a process singleton.

See **[Technical Debt Report](docs/TECHNICAL_DEBT_REPORT.md)** for a complete audit and remediation roadmap.
