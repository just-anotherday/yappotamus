# Stock Data Dashboard

A full-stack real-time stock market dashboard built with **FastAPI** + **PostgreSQL** backend and **Next.js** frontend. Features real-time price streaming via WebSockets, persistent watchlists, and automated news ingestion from Yahoo Finance.

## Tech Stack

| Layer | Technologies |
|-------|-------------|
| **Backend** | FastAPI, Python 3.10+, SQLAlchemy 2.x (async), asyncpg |
| **Database** | PostgreSQL (news articles + watchlist persistence) |
| **Frontend** | Next.js 15, TypeScript, React 19, Tailwind CSS |
| **Real-time** | WebSockets (yfinance live price streaming) |
| **External APIs** | yfinance (stock data, company info, news) |

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

- **Python 3.10+**
- **Node.js 20+** and **npm**
- **PostgreSQL 14+** running locally (or accessible via connection string)

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

Create a `.env` file in the project root:

```env
# Database
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/stock_dashboard

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
inside the FastAPI lifespan; there is no separate worker process command.

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
| `GET` | `/api/news` | Query news articles (supports filter, sort, pagination) |
| `POST` | `/api/news/ingest` | Trigger manual news ingestion for default tickers |
| `POST` | `/api/news/ingest/{ticker}` | Ingest news for a specific ticker |

### Real-time Prices
| Protocol | Path | Description |
|----------|------|-------------|
| WebSocket | `/ws/prices` | Subscribe to live price updates for watchlist tickers |

## Architecture Notes

- **Database schema** is managed by Alembic (`python -m alembic upgrade head`); startup performs a connectivity check only.
- **News ingestion** runs automatically every 15 minutes during market hours (8 AM – 6 PM EST) as a background scheduler.
- **WebSocket price streaming** uses a background thread to listen to Yahoo Finance WebSockets, then bridges events back to the FastAPI event loop.
- **Error handling** is centralized via FastAPI exception handlers (`backend/exceptions.py`).
- **All mutable endpoints currently lack authentication** — intended for local/personal use only (see `docs/TECHNICAL_DEBT_REPORT.md` for details).

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Backend won't start / DB error | Verify `DATABASE_URL` points to a running PostgreSQL instance |
| Frontend shows "Failed to fetch" | Ensure backend is running on port 8000 |
| No live price updates | Check WebSocket connection in browser dev tools; verify yfinance connectivity |
| News not populating | Manual trigger: `curl -X POST http://localhost:8000/api/news/ingest` |

## Known Limitations

- No authentication or authorization (local use only)
- No rate limiting on backend endpoints
- No unit test suite yet
- Singleton pattern used for `MarketDataService` (DI refactor pending)

See **[Technical Debt Report](docs/TECHNICAL_DEBT_REPORT.md)** for a complete audit and remediation roadmap.
