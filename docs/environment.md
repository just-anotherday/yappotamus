# YapVibes Environment Configuration Reference

Complete reference for all environment variables across every service in this monorepo.

---

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Stocks Backend](#stocks-backend)
- [Stocks Frontend](#stocks-frontend)
- [Projects App (Website)](#projects-app-website)
- [AI Generator Backend](#ai-generator-backend)
- [Environment File Strategy](#environment-file-strategy)
- [Deployment Configuration](#deployment-configuration)
- [Validation](#validation)

---

## Architecture Overview

```
Cloudflare Pages (Frontend)
  ↓ HTTPS API calls
Railway (FastAPI Backend)
  ↓ PostgreSQL
Supabase (Database)
  ↓ REST API
Finnhub (Market Data)
  ↓ HTTP API
Ollama / OpenAI (AI)
```

---

## Stocks Backend

All backend variables are managed through `apps/stocks/backend/config/settings.py`.

### Required Variables

| Variable | Description | Required | Default | Local Value | Production Value |
|----------|-------------|----------|---------|-------------|------------------|
| `DATABASE_URL` | PostgreSQL connection string | ✅ Yes | — | `postgresql://user:pass@localhost:5432/db` | Supabase connection string |
| `AI_PROVIDER` | AI backend selection | No | `ollama` | `ollama` | `openai` or `ollama` |

### Conditional Variables

| Variable | Description | Required When | Default | Local Value | Production Value |
|----------|-------------|---------------|---------|-------------|------------------|
| `OPENAI_API_KEY` | OpenAI API key | `AI_PROVIDER=openai` | — | — | Set in Railway |

### Optional Variables (Recommended)

| Variable | Description | Default | Local Value | Production Value |
|----------|-------------|---------|-------------|------------------|
| `SUPABASE_URL` | Supabase project URL for image proxy | — | Local Supabase URL | Production Supabase URL |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase service role key for server-side operations | — | Local service key | Production service key (Railway) |
| `FINNHUB_API_KEY` | Finnhub API key for market data + news | — | Your Finnhub key | Set in Railway |

### AI Provider Configuration

#### Ollama

| Variable | Description | Default |
|----------|-------------|---------|
| `OLLAMA_BASE_URL` | Ollama server URL | `http://localhost:11434` |
| `OLLAMA_MODEL` | Model name | `llama3.2` |
| `OLLAMA_TIMEOUT_SMALL_S` | Timeout for small models (seconds) | `900` |
| `OLLAMA_TIMEOUT_LARGE_S` | Timeout for large models (seconds) | `1200` |
| `OLLAMA_MAX_RETRIES` | Max retry attempts | `3` |
| `MODEL_SIZE_THRESHOLD_GB` | GB threshold to determine small vs large model | `8` |

#### OpenAI

| Variable | Description | Default |
|----------|-------------|---------|
| `OPENAI_MODEL` | OpenAI model name | `gpt-4o-mini` |

### Market Data Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `LIVE_PRICE_POLL_S` | Price polling interval (seconds) | `30` |
| `YF_PER_TICKER_DELAY_S` | Delay between Yahoo Finance requests | `0.6` |
| `QUOTE_CACHE_MAX_SIZE` | Max cache entries for quotes | `256` |

### CORS Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `CORS_ORIGINS` | Comma-separated list of allowed origins | `http://localhost:3000,http://localhost:5173` (local) or production domains |

Production defaults include:
- `https://yapvibes.com`
- `https://stocks.yapvibes.com`
- `https://projects.yapvibes.com`
- `https://yapvibes-stocks.pages.dev`

### Rate Limiting

| Variable | Description | Default |
|----------|-------------|---------|
| `RATE_LIMIT_WINDOW_S` | Rate limit window (seconds) | `60` |
| `RATE_LIMIT_MAX_REQUESTS` | Max requests per window | `20` |

### AI Worker

| Variable | Description | Default |
|----------|-------------|---------|
| `AI_WORKER_POLL_INTERVAL_S` | How often to poll for jobs (seconds) | `5-10` |
| `AI_WORKER_MAX_CONCURRENT` | Max concurrent AI jobs | `2` |
| `AI_WORKER_QUEUE_TIMEOUT_S` | Job timeout (seconds) | `1800` |

### WebSocket Market Data

| Variable | Description | Default |
|----------|-------------|---------|
| `WS_INITIAL_DELAY_S` | Initial delay before first poll | `2.0` |
| `WS_PING_INTERVAL_S` | WebSocket ping interval | `30.0` |
| `WS_PING_TIMEOUT_S` | WebSocket ping timeout | `10.0` |

---

## Stocks Frontend

Managed through Next.js `.env` files in `apps/stocks/frontend/`.

### Required Variables

| Variable | Description | Required | Local Value | Production Value |
|----------|-------------|----------|-------------|------------------|
| `NEXT_PUBLIC_API_URL` | Backend API base URL | ✅ Yes | `http://localhost:8000` | Railway API URL |
| `NEXT_PUBLIC_WS_URL` | WebSocket connection URL | ✅ Yes | `ws://localhost:8000` | Railway WebSocket URL |

### Optional Variables

| Variable | Description | Default | Notes |
|----------|-------------|---------|-------|
| `NEXT_PUBLIC_APP_URL` | Frontend public URL | — | Used for redirects, OG images |
| `NEXT_PUBLIC_SENTRY_DSN` | Sentry error tracking DSN | — | Optional monitoring |

### Environment Files

| File | Purpose | Committed? |
|------|---------|-----------|
| `.env.example` | Template with all variables | ✅ Yes |
| `.env.local` | Local development values | ❌ No (gitignored) |
| `.env.production` | Production values for Cloudflare Pages build | ✅ Yes |

---

## Projects App (Website)

### Frontend (`apps/website/frontend/app/`)

| Variable | Description | Required | Local Value | Production Value |
|----------|-------------|----------|-------------|------------------|
| `NEXT_PUBLIC_API_URL` | Backend API URL | ✅ Yes | `http://localhost:3001` | Cloudflare Pages hostname |
| `NEXT_PUBLIC_APP_URL` | Public app URL | No | — | Production URL |

### HTML/JS Static Pages (`apps/website/frontend/projects/`)

These pages use hardcoded relative paths or are configured through build-time environment injection. No runtime `.env` needed.

---

## AI Generator Backend

Managed through `apps/website/backend/ai-generator-backend/.env`.

| Variable | Description | Required | Default | Notes |
|----------|-------------|----------|---------|-------|
| `PORT` | Server port | No | `3001` | Local dev port |
| `OPENAI_API_KEY` | OpenAI API key | ✅ Yes | — | Required for generation |
| `OPENAI_MODEL` | Model to use | No | `gpt-4o-mini` | — |
| `ANTHROPIC_API_KEY` | Anthropic API key (alternative) | No | — | Optional fallback |
| `CORS_ORIGINS` | Allowed CORS origins | No | `*` | Restrict in production |

---

## Environment File Strategy

### Directory Structure

```
apps/stocks/
  .env.example          # ✅ Committed - template
  .env                  # ❌ Local dev (gitignored)
  .env.production       # ✅ Production values for Railway

apps/stocks/frontend/
  .env.example          # ✅ Committed - template
  .env.local            # ❌ Local dev (gitignored)
  .env.production       # ✅ Production values for Cloudflare Pages

apps/website/backend/ai-generator-backend/
  .env.example          # ✅ Committed - template
  .env                  # ❌ Local dev (gitignored)

apps/projects/
  .env.production       # ✅ Production values
```

### Loading Order

#### Next.js (Frontend)

Next.js loads environment files in priority order (highest first):

1. `.env.local` (always loaded, gitignored)
2. `.env.[mode]` (e.g., `.env.production` for `next build`)
3. `.env` (loaded in development only)

Only `NEXT_PUBLIC_` prefixed variables are exposed to the browser.

#### FastAPI (Backend)

The backend uses `python-dotenv` via `run.py`:

```python
from dotenv import load_dotenv
load_dotenv()  # Loads .env from apps/stocks/ directory
```

Then all values are accessed through `backend.config.settings`:

```python
from backend.config.settings import settings
db_url = settings.DATABASE_URL
```

#### Railway Deployment

Railway reads environment variables directly from the dashboard. No `.env` file is mounted. All variables configured in Railway's environment settings take precedence.

#### Cloudflare Pages (Frontend)

Cloudflare Pages reads environment variables from the Pages project settings. Only `NEXT_PUBLIC_` variables are available at build time.

---

## Deployment Configuration

### Railway (Backend)

Configure these variables in Railway's project settings:

```
DATABASE_URL=postgresql://...
SUPABASE_URL=https://...
SUPABASE_SERVICE_ROLE_KEY=...
FINNHUB_API_KEY=...
AI_PROVIDER=openai
OPENAI_API_KEY=...
CORS_ORIGINS=https://stocks.yapvibes.com,https://yapvibes-stocks.pages.dev
```

### Cloudflare Pages (Frontend)

Configure these in Cloudflare Pages environment settings:

```
NEXT_PUBLIC_API_URL=https://api.yapvibes.com
NEXT_PUBLIC_WS_URL=wss://api.yapvibes.com
```

### Docker

If using Docker, create `apps/stocks/.env.docker` and pass via:

```bash
docker-compose --env-file .env.docker up
```

---

## Validation

The application validates required environment variables at startup through `settings.validate()`:

```
✅ DATABASE_URL must be set
✅ OPENAI_API_KEY must be set when AI_PROVIDER=openai
⚠️  FINNHUB_API_KEY recommended (warning logged if missing)
```

If validation fails, the application raises an `EnvironmentError` immediately with a clear message listing all missing variables.

---

## Hardcoded Values Replaced

The following hardcoded values were replaced with environment variables:

| Original | Replacement Variable | Location |
|----------|---------------------|----------|
| `http://localhost:8000` in frontend | `NEXT_PUBLIC_API_URL` | Frontend API calls |
| `ws://localhost:8000` in frontend | `NEXT_PUBLIC_WS_URL` | WebSocket connections |
| Inline CORS list in `main.py` | `CORS_ORIGINS` env var | Backend CORS middleware |

---

## Security Notes

1. **Never commit `.env` files** containing secrets to git
2. **Use Railway dashboard** for production secret management
3. **Use Cloudflare Pages settings** for frontend production variables
4. **`.env.example`** files serve as templates and should include all variable names with placeholder values
5. **Supabase service role key** is a high-privilege key — only use server-side, never expose to the browser

---

## Quick Start

### Local Development

1. Copy template: `cp apps/stocks/.env.example apps/stocks/.env`
2. Copy frontend template: `cp apps/stocks/frontend/.env.example apps/stocks/frontend/.env.local`
3. Fill in your API keys
4. Run backend: `cd apps/stocks && python run.py`
5. Run frontend: `cd apps/stocks/frontend && npm run dev`

### Production Deployment

1. Set Railway environment variables in dashboard
2. Set Cloudflare Pages environment variables in project settings
3. Deploy via GitHub Actions or manual trigger
