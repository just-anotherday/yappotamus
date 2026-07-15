# YapVibes Deployment Guide

## Table of Contents
1. [Architecture Overview](#architecture-overview)
2. [Domain Routing Plan](#domain-routing-plan)
3. [Application Build Verification](#application-build-verification)
4. [Local Development Commands](#local-development-commands)
5. [Production Build Commands](#production-build-commands)
6. [Environment Variables](#environment-variables)
7. [Cloudflare Deployment Configuration](#cloudflare-deployment-configuration)
8. [Backend Deployment Strategy](#backend-deployment-strategy)
9. [Node Version Requirements](#node-version-requirements)

---

## Architecture Overview

```
YapVibes Monorepo
├── apps/
│   ├── projects/              # React + Vite + TypeScript + Supabase (SPA)
│   ├── stocks/
│   │   ├── frontend/          # Next.js 16 (App Router, Static + Dynamic pages)
│   │   └── backend/           # FastAPI (Python 3.11+) [standalone in root]
│   └── website/
│       ├── frontend/app/      # React + Vite + TypeScript (SPA Landing Page)
│       └── backend/           # Node.js AI Generator Backend (Express-like JS server)
├── packages/                  # Shared packages (future migration)
└── docs/                      # Documentation
```

---

## Domain Routing Plan

| Domain | Application | Type | Hosting Target |
|--------|-------------|------|----------------|
| `yapvibes.com` | Website frontend | Static SPA | Cloudflare Pages |
| `projects.yapvibes.com` | Projects app | Static SPA | Cloudflare Pages |
| `stocks.yapvibes.com` | Stocks frontend | Next.js (SSR/SSG hybrid) | Cloudflare Pages or Vercel |
| `api.yapvibes.com` | FastAPI backend | Python API | Render / Railway / Fly.io |

### DNS Configuration

```
yapvibes.com           → CNAME → Cloudflare Pages (website)
projects.yapvibes.com  → CNAME → Cloudflare Pages (projects)
stocks.yapvibes.com    → CNAME → Cloudflare Pages/Vercel (stocks frontend)
api.yapvibes.com       → CNAME → Backend provider (Render/Railway/Fly.io)
```

---

## Application Build Verification

### Status: All builds verified ✓

| App | Build Command | Output Dir | Build Time | Status |
|-----|--------------|------------|------------|--------|
| projects | `tsc -b && vite build` | `dist/` | ~338ms | ✓ |
| stocks/frontend | `next build` | `.next/` | ~4s | ✓ |
| website/frontend/app | `vite build` | `dist/` | ~320ms | ✓ |

---

## Local Development Commands

### Prerequisites
- Node.js 18+ (recommended 20 LTS)
- npm 9+ (workspace-aware)
- Python 3.11+ (for stocks backend)
- PostgreSQL 15+ (for stocks backend)

### From Repository Root

```bash
# Install all workspace dependencies
cd C:\Users\jason\Development\YapVibes
npm install

# --- Projects App ---
cd apps/projects
npm run dev           # Vite dev server (default port 5173)

# --- Stocks Frontend ---
cd apps/stocks/frontend
npm run dev           # Next.js dev server (default port 3000)

# --- Stocks Backend ---
cd apps/stocks
pip install -r requirements.txt
python run.py         # Uvicorn dev server (default port 8000)

# --- Website Frontend ---
cd apps/website/frontend/app
npm run dev           # Vite dev server (default port 5173)

# --- Website Backend (AI Generator) ---
cd apps/website/backend/ai-generator-backend
npm install
node server.js        # Dev server (check package.json for port)
```

---

## Production Build Commands

### From Repository Root

```bash
# Install all dependencies
npm install

# --- Projects App ---
cd apps/projects
npm run build         # → dist/

# --- Stocks Frontend ---
cd apps/stocks/frontend
npm run build         # → .next/

# --- Website Frontend ---
cd apps/website/frontend/app
npm run build         # → dist/
```

### Backend Build (Python)

```bash
cd apps/stocks
pip install -r requirements.txt   # No compilation needed for FastAPI
```

---

## Environment Variables

### Projects App (`apps/projects/.env`)

| Variable | Required | Description |
|----------|----------|-------------|
| `VITE_SUPABASE_URL` | Yes | Supabase project URL |
| `VITE_SUPABASE_ANON_KEY` | Yes | Supabase anonymous/public key |

### Stocks Frontend (`apps/stocks/frontend/.env.local`)

| Variable | Required | Description |
|----------|----------|-------------|
| (inferred from backend CORS) | No | Next.js frontend calls backend via API routes or direct CORS |

> **Note:** The stocks frontend currently has no `.env` file. If it needs to call the backend directly, configure `NEXT_PUBLIC_API_URL`.

### Stocks Backend (`apps/stocks/.env`)

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | Yes | PostgreSQL async connection string |
| `FINNHUB_API_KEY` | Yes | Finnhub market data API key |
| `CORS_ORIGINS` | Yes | Allowed frontend origins (comma-separated) |
| `OLLAMA_BASE_URL` | Optional | Local LLM endpoint |
| `OLLAMA_MODEL` | Optional | Model name for analysis |
| `WS_RECONNECT_BACKOFF_S` | No | WebSocket reconnect delay (default: 1) |
| `WS_RECONNECT_MAX_BACKOFF_S` | No | Max WebSocket backoff (default: 30) |

### Website Backend (`apps/website/backend/ai-generator-backend/`)

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | Yes | OpenAI API key for AI generation |
| (check server.js) | Check | Any additional env vars needed by the Node server |

---

## Cloudflare Deployment Configuration

### Recommended Service per Application

#### 1. Website Frontend → **Cloudflare Pages**

- **Type:** Static SPA (Vite output)
- **Build command:** `npm run build` (run from `apps/website/frontend/app`)
- **Build output directory:** `dist`
- **Framework preset:** Vite
- **Root directory:** `apps/website/frontend/app`
- **SPA routing:** Enable "Redirect all URLs to root" (404 pages → index.html)

#### 2. Projects App → **Cloudflare Pages**

- **Type:** Static SPA (Vite output)
- **Build command:** `npm run build` (run from `apps/projects`)
- **Build output directory:** `dist`
- **Framework preset:** Vite
- **Root directory:** `apps/projects`
- **SPA routing:** Enable "Redirect all URLs to root"
- **Environment variables:** Configure `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY` in Cloudflare Pages settings

#### 3. Stocks Frontend → **Cloudflare Pages** (or Vercel for simpler Next.js support)

**Option A: Cloudflare Pages (recommended for consistency)**
- **Type:** Next.js hybrid (static + dynamic pages)
- **Build command:** `npm run build` (run from `apps/stocks/frontend`)
- **Build output directory:** `.next`
- **Framework preset:** Next.js
- **Root directory:** `apps/stocks/frontend`
- **Compatibility:** Requires Cloudflare Pages Node.js compatibility mode for serverless functions

**Option B: Vercel (simpler Next.js integration)**
- Native Next.js support with zero config
- Automatic ISR, API routes, and edge functions
- Recommended if you encounter limitations with Cloudflare's Next.js adapter

### Cloudflare Pages CI/CD Configuration

For each site in the Cloudflare Dashboard:

```
Production Branch: main
Build Command:     npm run build   (context depends on root directory setting)
Output Directory:  dist or .next  (depends on app)
Root Directory:    apps/{app-name} (relative to repo root)
```

### Cloudflare DNS Records

```
Type     Name                    Value                          TTL
CNAME    @                       {username}.pages.dev           Auto
CNAME    projects                {username}-projects.pages.dev  Auto
CNAME    stocks                  {username}-stocks.pages.dev    Auto
CNAME    api                     {backend-provider-url}         Auto
```

---

## Backend Deployment Strategy

### FastAPI Backend (`apps/stocks/`)

**Cloudflare does NOT natively support FastAPI.** Cloudflare Workers use JavaScript/Wasm/V8 isolates. For a Python FastAPI application, the recommended platforms are:

#### Recommended: **Render.com**

| Criteria | Score |
|----------|-------|
| Python 3.11+ support | ✓ |
| PostgreSQL managed DB | ✓ (built-in) |
| Free tier available | ✓ |
| Simple deployment | ✓ (Git push → auto-deploy) |
| Custom domain support | ✓ |

**Deployment Steps:**
1. Create a new Web Service on Render
2. Connect your GitHub repository
3. Set build command: `pip install -r apps/stocks/requirements.txt`
4. Set start command: `uvicorn run:app --host 0.0.0.0 --port $PORT` (adjust module path)
5. Configure environment variables in the dashboard
6. Add managed PostgreSQL database

#### Alternatives

| Platform | Pros | Cons |
|----------|------|------|
| **Railway** | Easy setup, good Python support | No free tier |
| **Fly.io** | Global edge deployment | More complex config |
| **Google Cloud Run** | Serverless containers | Requires Dockerfile |
| **AWS ECS/Lambda** | Enterprise-grade | Higher complexity |

### Website Backend (AI Generator - Node.js)

This is a **Node.js** application, which CAN be deployed on:

- **Cloudflare Workers** (if rewritten to Worker-compatible format)
- **Render.com** (same instance as FastAPI, simpler)
- **Railway** (separate service)

**Recommendation:** Deploy alongside the FastAPI backend on Render as a separate web service for simplicity.

---

## Node Version Requirements

| Application | Engine | Min Node Version | Recommended |
|-------------|--------|-----------------|-------------|
| projects | Vite 8, React 19 | Node 18 | Node 20 LTS |
| stocks/frontend | Next.js 16, React 19 | Node 18 | Node 20 LTS |
| website/frontend/app | Vite 8, React 19 | Node 18 | Node 20 LTS |

### Engine Configuration (Recommended)

Add to each app's `package.json`:
```json
{
  "engines": {
    "node": ">=20.0.0",
    "npm": ">=9.0.0"
  }
}
```

---

## Deployment Checklist

### Pre-Deployment
- [ ] All apps build successfully locally
- [ ] Environment variables documented and prepared
- [ ] `.env` files added to `.gitignore` in each app
- [ ] DNS records ready for subdomains
- [ ] SSL/TLS certificates (Cloudflare handles this automatically)

### Cloudflare Pages Setup
- [ ] Create Pages project for website
- [ ] Create Pages project for projects
- [ ] Create Pages project for stocks frontend
- [ ] Configure build settings for each
- [ ] Add environment variables to each Pages project

### Backend Setup (Render/Railway)
- [ ] Deploy FastAPI backend
- [ ] Deploy AI Generator backend
- [ ] Configure PostgreSQL database
- [ ] Set CORS origins to include all subdomains
- [ ] Test API connectivity from frontend subdomains

### Post-Deployment Verification
- [ ] `yapvibes.com` loads website frontend
- [ ] `projects.yapvibes.com` loads projects app with Supabase auth
- [ ] `stocks.yapvibes.com` loads stocks dashboard
- [ ] `api.yapvibes.com` responds to API requests
- [ ] CORS is configured correctly between all origins
- [ ] HTTPS works on all subdomains

---

## Notes & Known Issues

1. **Lockfile warnings:** Next.js detected multiple `package-lock.json` files in the workspace. The apps/stocks directory has its own lockfile from before migration. Consider removing redundant lockfiles once the monorepo is stable.

2. **SPA routing on Cloudflare Pages:** Both Vite apps (projects, website) need SPA fallback rules configured. In Cloudflare Pages, enable "Redirect all URLs to root" in settings.

3. **CORS configuration:** The FastAPI backend currently has `CORS_ORIGINS=http://localhost:3000`. Update this to include production domains before deploying:
   ```
   CORS_ORIGINS=http://localhost:3000,https://stocks.yapvibes.com
   ```

4. **Supabase URL:** The projects app's `.env` contains local/development Supabase credentials. Ensure production environment variables are set in Cloudflare Pages settings.

---

*Last updated: July 14, 2026*