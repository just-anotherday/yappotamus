# YapVibes Production Deployment Checklist

## Status: Ready for Deployment (pending manual configuration)

---

## 1. Cloudflare Pages Configuration

### Website Frontend (`yapvibes.com`)

| Setting | Value |
|---------|-------|
| **Branch** | `main` |
| **Root Directory** | `apps/website/frontend/app` |
| **Build Command** | `npm run build` |
| **Build Output** | `dist` |
| **Framework** | Vite |
| **SPA Routing** | Enable "Redirect all URLs to root" (404 → index.html) |
| **Environment Variables** | None required |

### Projects App (`projects.yapvibes.com`)

| Setting | Value |
|---------|-------|
| **Branch** | `main` |
| **Root Directory** | `apps/projects` |
| **Build Command** | `npm run build` |
| **Build Output** | `dist` |
| **Framework** | Vite |
| **SPA Routing** | Enable "Redirect all URLs to root" (404 → index.html) |
| **Environment Variables** | `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY` |

### Stocks Frontend (`stocks.yapvibes.com`)

| Setting | Value |
|---------|-------|
| **Branch** | `main` |
| **Root Directory** | `apps/stocks/frontend` |
| **Build Command** | `npm run build:cf` |
| **Build Output** | `.open-next` |
| **Framework** | Next.js (via OpenNext Cloudflare adapter) |
| **Environment Variables** | `NEXT_PUBLIC_API_BASE`, `NEXT_PUBLIC_WS_URL` |

---

## 2. Render Configuration (Backend)

### FastAPI Service (`api.yapvibes.com`)

| Setting | Value |
|---------|-------|
| **Service Type** | Web Service |
| **Root Directory** | `apps/stocks` |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `uvicorn backend.main:app --host 0.0.0.0 --port $PORT` |
| **Environment Variables** | See section 4 below |
| **Database** | Managed PostgreSQL on Render (or external Supabase) |

---

## 3. DNS Records

| Type | Name | Value | TTL |
|------|------|-------|-----|
| CNAME | `@` | `{username}.pages.dev` (website) | Auto |
| CNAME | `projects` | `{username}-projects.pages.dev` | Auto |
| CNAME | `stocks` | `{username}-stocks.pages.dev` | Auto |
| CNAME | `api` | `{service-id}.onrender.com` | Auto |

---

## 4. Required Environment Variables by Service

### Projects (Cloudflare Pages)

| Variable | Source | Description |
|----------|--------|-------------|
| `VITE_SUPABASE_URL` | Supabase dashboard | Project URL |
| `VITE_SUPABASE_ANON_KEY` | Supabase dashboard | Public anon key |

### Stocks Backend (Render)

| Variable | Source | Description |
|----------|--------|-------------|
| `DATABASE_URL` | Render PostgreSQL / Supabase | Async connection string |
| `CORS_ORIGINS` | Manual | `https://stocks.yapvibes.com,http://localhost:3000` |
| `FINNHUB_API_KEY` | Finnhub account | Market data API key |
| `OLLAMA_BASE_URL` | Optional | Local LLM endpoint (omit in prod if not using) |
| `OLLAMA_MODEL` | Optional | Model name |

### Stocks Frontend (Cloudflare Pages)

| Variable | Source | Description |
|----------|--------|-------------|
| `NEXT_PUBLIC_API_BASE` | Manual | `https://api.yapvibes.com` |
| `NEXT_PUBLIC_WS_URL` | Manual | `wss://api.yapvibes.com/ws` |

---

## 5. Supabase Checklist

- [ ] Create production Supabase project (or reuse existing)
- [ ] Copy migration SQL files from `apps/projects/migrations/` to production database
- [ ] Enable Row-Level Security (RLS) on all tables
- [ ] Configure anon key policies for public read access
- [ ] Set service role key in backend if needed
- [ ] Record `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY`

---

## 6. Pre-Deployment Verification

- [ ] All three frontends build from clean clone (`npm install && npm run build:<app>`)
- [ ] `.env` files are in `.gitignore` (not committed)
- [ ] `.env.example` files exist for all apps
- [ ] No hardcoded `localhost` URLs remain in production code paths
- [ ] CORS origins configured for production domain in backend `.env`

---

## 7. Post-Deployment Testing

- [ ] `https://yapvibes.com` loads website frontend
- [ ] `https://projects.yapvibes.com` loads projects app + Supabase auth works
- [ ] `https://stocks.yapvibes.com` loads stocks dashboard
- [ ] API calls from stocks frontend reach `api.yapvibes.com`
- [ ] WebSocket connections work for live data
- [ ] HTTPS certificates active on all subdomains

---

## 8. Current Blockers Before First Production Deployment

1. **No production Supabase project configured** — Need to create or migrate to production instance
2. **No Render account/services created** — Backend needs deployment target
3. **DNS records not configured** — Subdomains need to point to Cloudflare Pages / Render
4. **Finnhub API key** — Ensure it's added to Render environment variables
5. **Supabase RLS policies** — Verify row-level security is enabled on production database
6. **SSL certificates** — Cloudflare handles automatically, but verify after DNS propagation

---

*Last updated: July 15, 2026*
