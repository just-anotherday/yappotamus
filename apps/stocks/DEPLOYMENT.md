# YapVibes Stocks - Deployment Guide

## Architecture

```
Frontend (Next.js 16)          Backend (FastAPI/Python 3.12)
├── Cloudflare Worker   ──▶   Railway / Self-hosted Docker
└── Vercel (optional)         Supabase PostgreSQL (DB)
                              OpenAI API (production AI)
```

---

## Backend Deployment (Railway)

### Prerequisites
- Railway account + project created
- Supabase PostgreSQL instance running
- OpenAI API key for production AI analysis

### Environment Variables (set in Railway dashboard)

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | **Yes** | Supabase PostgreSQL connection string |
| `APP_ACCESS_TOKEN` | **Yes** | Private token used by the frontend for authenticated API/WebSocket access |
| `FINNHUB_API_KEY` | **Yes** | Market data API key |
| `OPENAI_API_KEY` | **Yes** (prod) | OpenAI API key for AI analysis |
| `AI_PROVIDER` | No | Set to `openai` (default: `ollama`) |
| `OPENAI_MODEL` | No | Model name (default: `gpt-4o-mini`) |
| `OPENAI_ALLOWED_MODELS` | **Yes** when OpenAI is used | Must include `OPENAI_MODEL` (for example `gpt-4o-mini`) |
| `CORS_ORIGINS` | **Yes** | Include `https://stocks.yapvibes.com` and the Worker preview domain |
| `PORT` | No | Override default port 8000 |

### Deployment Steps

1. Connect Railway to the GitHub repository and set the service root directory to `apps/stocks`
2. Set environment variables in Railway dashboard
3. Keep the service at one replica because the news scheduler runs inside FastAPI
4. Deploy → Railway builds the Dockerfile and runs `python -m alembic upgrade head` before starting Uvicorn

### Manual Deployment (Docker Compose)

```bash
# From repository root
docker compose -f apps/stocks/docker-compose.yml up -d
```

---

## Frontend Deployment (Cloudflare Workers)

### Prerequisites
- Cloudflare account with Workers enabled
- Repository dependencies installed locally or by CI (`npm ci` from the repository root)

### Build Configuration

**Cloudflare Workers Builds settings:**
- Root directory: `/` (repository root)
- Build command: `npm ci && npm run build:cf --workspace=apps/stocks/frontend`
- Deploy command: `npx opennextjs-cloudflare deploy --cwd apps/stocks/frontend`
- Wrangler config: `apps/stocks/frontend/wrangler.toml`

Do not publish `.next`, `.open-next`, or `.open-next/optimised` as a Pages static directory.
OpenNext generates a Worker entry point and an assets binding; deploying only a directory
causes the custom domain to return a 404 instead of invoking Next.js.

### Environment Variables (set in Cloudflare Workers Builds dashboard)

| Variable | Required | Description |
|----------|----------|-------------|
| `NEXT_PUBLIC_API_BASE` | **Yes** | Backend origin without a trailing slash (e.g., `https://stocks-api.up.railway.app`) |
| `NEXT_PUBLIC_WS_URL` | **Yes** | Complete WebSocket endpoint (e.g., `wss://stocks-api.up.railway.app/ws`) |

### Manual Deployment

```bash
cd apps/stocks/frontend
npm run deploy:cf
```

The two `NEXT_PUBLIC_*` values are compiled into the browser bundle, so set them
as **build variables before building**. They are not secrets.

### Custom Domain and 404 Recovery

1. Deploy the Worker and verify its generated `*.workers.dev` URL returns HTTP 200.
2. In **Workers & Pages → stocks-frontend → Settings → Domains & Routes**, add
   `stocks.yapvibes.com` as a custom domain.
3. Remove `stocks.yapvibes.com` from any old Pages project or legacy Worker route.
   Only one Cloudflare resource should own the hostname.
4. Keep the DNS record proxied. Cloudflare creates/updates the DNS target when the
   custom domain is attached to the Worker.

### Start and Verify Article Collection

The collector runs in the FastAPI lifespan and starts its first cycle immediately,
then repeats every 15 minutes. After the Railway deployment:

```bash
# Process and dependency checks
curl https://YOUR-BACKEND/health/live
curl https://YOUR-BACKEND/health

# Trigger an immediate authenticated collection cycle (default watchlist)
curl -X POST -H "Authorization: Bearer YOUR_APP_ACCESS_TOKEN" \
  https://YOUR-BACKEND/api/news/ingest
```

Confirm Railway logs contain `NewsScheduler Started` and `Cycle complete`, and
confirm `news_articles` rows appear in PostgreSQL. The production watchlist must
contain tickers; startup seeds defaults when its migration tables are available.

---

## AI Provider Configuration

The backend supports two AI providers, switched via the `AI_PROVIDER` environment variable:

### Ollama (Local Development)
```env
AI_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2
```

### OpenAI (Production)
```env
AI_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
```

No code changes needed to switch providers.

---

## Health Checks

| Endpoint | Description |
|----------|-------------|
| `GET /health/live` | Process-only liveness probe |
| `GET /health` | Database, worker, AI provider, and dependency readiness diagnostics |
| `GET /api/ollama/config` | AI provider status and available models |
| `GET /api/analysis/status` | AI worker queue status |

---

## CORS Configuration

Production CORS origins are configured by default:
- `https://yapvibes.com`
- `https://stocks.yapvibes.com`
- `https://projects.yapvibes.com`
- `https://yapvibes-stocks.pages.dev`

Override with the `CORS_ORIGINS` environment variable.

---

## Troubleshooting

### Frontend Build Fails on Cloudflare
1. Use Node.js 20 or 22 LTS in Cloudflare Builds (not an untested current release)
2. Verify `@opennextjs/cloudflare` is installed by the root workspace lockfile
3. Run `npm run build:cf --workspace=apps/stocks/frontend` and confirm `.open-next/worker.js` and `.open-next/assets` exist

### Backend Connection Issues
1. Verify Supabase connection string includes the `+asyncpg` driver prefix
2. Check Railway firewall allows outbound connections to Supabase
3. Test with `curl https://your-railway-url/health`

### AI Provider Errors
1. Confirm `AI_PROVIDER` matches available credentials
2. For OpenAI: verify API key has Chat Completions access
3. For Ollama: ensure the model is pulled and running locally
