# YapVibes Stocks - Deployment Guide

## Architecture

```
Frontend (Next.js 16)          Backend (FastAPI/Python 3.12)
├── Cloudflare Pages    ──▶   Railway / Self-hosted Docker
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
| `FINNHUB_API_KEY` | **Yes** | Market data API key |
| `OPENAI_API_KEY` | **Yes** (prod) | OpenAI API key for AI analysis |
| `AI_PROVIDER` | No | Set to `openai` (default: `ollama`) |
| `OPENAI_MODEL` | No | Model name (default: `gpt-4o-mini`) |
| `CORS_ORIGINS` | No | Comma-separated allowed origins |
| `PORT` | No | Override default port 8000 |

### Deployment Steps

1. Connect Railway to your GitHub repository (`apps/stocks` branch)
2. Set environment variables in Railway dashboard
3. Deploy → Railway auto-detects Dockerfile and builds

### Manual Deployment (Docker Compose)

```bash
# From repository root
docker compose -f apps/stocks/docker-compose.yml up -d
```

---

## Frontend Deployment (Cloudflare Pages)

### Prerequisites
- Cloudflare account with Pages enabled
- Wrangler CLI installed (`npm i -g wrangler`)

### Build Configuration

**Cloudflare Pages Settings:**
- Framework preset: **None** (custom build)
- Build command: `cd apps/stocks/frontend && npm ci && npm run build`
- Build output directory: `.open-next/optimised`
- Root directory: `/` (repository root)

### Environment Variables (set in Cloudflare Pages dashboard)

| Variable | Required | Description |
|----------|----------|-------------|
| `NEXT_PUBLIC_API_BASE_URL` | **Yes** | Backend API URL (e.g., `https://stocks-api.up.railway.app`) |
| `NEXT_PUBLIC_WS_URL` | **Yes** | WebSocket URL (e.g., `wss://stocks-api.up.railway.app`) |

### Manual Deployment

```bash
cd apps/stocks/frontend
npm ci
npm run build          # Runs open-next build internally
npx wrangler pages deploy .open-next/optimised
```

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
| `GET /health` | Backend liveness probe (returns `{"status": "ok"}`) |
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
1. Ensure Node.js 20+ is selected in Cloudflare Pages build settings
2. Verify `open-next` and `@opennextjs/cloudflare` are in `package.json`
3. Check that `.open-next/optimised` directory is created after build

### Backend Connection Issues
1. Verify Supabase connection string includes the `+asyncpg` driver prefix
2. Check Railway firewall allows outbound connections to Supabase
3. Test with `curl https://your-railway-url/health`

### AI Provider Errors
1. Confirm `AI_PROVIDER` matches available credentials
2. For OpenAI: verify API key has Chat Completions access
3. For Ollama: ensure the model is pulled and running locally
