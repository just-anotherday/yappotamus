# YapVibes Monorepo

YapVibes contains three independently runnable applications:

- **Website** — a React/Vite site with an optional live chat companion.
- **Projects** — a React/Vite/TypeScript app backed directly by Supabase.
- **Stocks** — a Next.js dashboard backed by FastAPI and PostgreSQL.

## Which app do you want to run?

| App | Frontend | Backend to run | Database | AI/model |
| --- | --- | --- | --- | --- |
| [Website](#run-website) | React + Vite | Express (for live chat) | No application database configured | Hosted OpenAI; no local model runtime |
| [Projects](#run-projects) | React + Vite + TypeScript | None separately — Supabase is the backend | Supabase PostgreSQL | No local model runtime |
| [Stocks](#run-stocks) | Next.js | FastAPI | PostgreSQL + Alembic | Ollama by default, or OpenAI when selected |

### Website

You need Node.js/npm and an OpenAI API key to use live chat. Start two processes for live chat: the Express backend and Vite frontend. You do not need Python, PostgreSQL, or Ollama.

### Projects

You need Node.js/npm and a Supabase project with its public URL and anon key. Start one process: the Vite frontend. You do not start a separate Express, FastAPI, or local PostgreSQL process.

### Stocks

You need Node.js/npm, Python 3.10+, a reachable PostgreSQL database, and an access token. Start FastAPI and Next.js; run Ollama separately only when using the default local AI provider for AI analysis. Finnhub credentials are recommended for Finnhub-dependent market-data features.

## Common setup

Install Node.js/npm dependencies from the repository root once:

```powershell
npm install
```

The root npm workspaces are `apps/projects`, `apps/stocks/frontend`, `apps/website/frontend/app`, and `packages/*`. The Website Express backend is not a workspace; install it from its own directory when running Website.

## Run Website

**Processes to start:** 2 for live chat (Express + Vite); 1 for the Website without live chat.

**Backend to run:** Express in `apps/website/backend/ai-generator-backend`.

**Local AI model required:** No. The backend uses the hosted OpenAI Chat Completions API.

### What you need

- Node.js 20 or later (declared by the Express backend) and npm.
- An OpenAI API key to generate chat responses.

You do not need Python, PostgreSQL, or Ollama for the Website.

### Architecture

```text
Browser → React/Vite frontend → Express chat API → OpenAI
```

### 1. Configure environment

Create a local Vite environment file from `apps/website/frontend/app/.env.example`. Set `VITE_AI_API_BASE` to the full Express endpoint.

The Express server defaults to port 5000, so its matching frontend configuration is:

```text
VITE_AI_API_BASE=http://localhost:5000/api/openai
```

The committed frontend example uses port 3001. Use that value only after setting the Express backend's `PORT=3001`.

Create `apps/website/backend/ai-generator-backend/.env` from its `.env.example`. Set:

- Required for generation: `OPENAI_API_KEY`
- Optional: `OPENAI_MODEL`, `OPENAI_TIMEOUT_MS`, `PORT`, `HOST`, `HEALTH_SECRET`

Never commit real environment values.

### 2. Start the Express backend — Terminal 1

```powershell
cd apps/website/backend/ai-generator-backend
npm install
npm start
```

`npm start` runs `node server.js`. With defaults it listens on `0.0.0.0:5000` and provides `POST /api/openai` (plus the legacy `POST /ai`).

### 3. Start the Vite frontend — Terminal 2

From the repository root:

```powershell
npm run dev:website
```

Or from `apps/website/frontend/app`:

```powershell
npm run dev
```

No Vite port override is configured, so Vite uses its default development port, 5173, unless overridden at launch.

### 4. Verify

- Open the Vite URL shown in the terminal (normally `http://localhost:5173`).
- Send a message through the chat companion; it should use the Express API when configured and reachable.
- The backend health route is available at `GET /health?key=<HEALTH_SECRET>` only when `HEALTH_SECRET` is configured. Without it, the route returns 501.

The rest of the Website works when the Express service is unavailable; the chat UI uses its offline fallback.

Build with `npm run build:website` from the root, or `npm run build` from `apps/website/frontend/app`. Run the backend tests with `npm test` from `apps/website/backend/ai-generator-backend`.

## Run Projects

**Processes to start:** 1 (Vite frontend).

**Backend to run:** None separately — Projects communicates directly with Supabase.

**Local AI model required:** No.

### What you need

- Node.js and npm.
- A Supabase project.
- Its public Project URL and anon key.

You do not need to start a separate Express or FastAPI server, or a local PostgreSQL process, for the Projects frontend.

### Architecture — where is the backend?

```text
Browser → React/Vite frontend → Supabase
                              ├─ PostgreSQL
                              ├─ Auth and RLS
                              ├─ Realtime
                              └─ RPC/database functions
```

Projects has no separate application API server to start locally. Its backend behavior lives in the Supabase database/schema, RLS policies, SQL/RPC functions, triggers, Realtime, and the frontend's Supabase data-access hooks and services.

### 1. Configure environment

Create `apps/projects/.env.local` from `apps/projects/.env.example` and set:

- `VITE_SUPABASE_URL`
- `VITE_SUPABASE_ANON_KEY`

### 2. Apply database migrations

Versioned SQL migrations are in `apps/projects/migrations/`, with checks in `apps/projects/migrations/tests/`. Apply the required SQL to the intended Supabase database using that project's database workflow. This repository does not define a root Supabase CLI migration command, so do not infer one from this README.

### 3. Start Projects

From the repository root:

```powershell
npm run dev:projects
```

Or from `apps/projects`:

```powershell
npm run dev
```

No Vite port override is configured, so it uses the default development port, 5173, unless overridden at launch.

### 4. Verify

- Open the Vite URL shown in the terminal.
- Confirm the app can authenticate against the configured Supabase project.
- Confirm data loads for the available project areas: boards, shopping lists, and recipe collections.

Validate from `apps/projects` with `npm run lint` and `npm run build`, or build from the root with `npm run build:projects`.

## Run Stocks

**Processes to start:** 2 (FastAPI + Next.js), plus Ollama only when using the default local AI provider for AI analysis.

**Backend to run:** FastAPI in `apps/stocks/backend`.

**Local AI model required:** Optional and provider-dependent. Ollama is the default provider; OpenAI needs no local model process.

### What you need

- Node.js and npm for the Next.js frontend.
- Python 3.10 or later for FastAPI.
- A reachable PostgreSQL database.
- An access token configured as `APP_ACCESS_TOKEN` or `APP_ACCESS_TOKENS`.
- `FINNHUB_API_KEY` for Finnhub-dependent features (the backend starts without it, but those features degrade).
- Either Ollama for local AI analysis or OpenAI credentials when `AI_PROVIDER=openai`.

### Architecture

```text
Browser → Next.js frontend → HTTP/WebSocket → FastAPI
                                           ├─ PostgreSQL
                                           ├─ Finnhub and yfinance market data
                                           └─ Ollama or OpenAI AI provider
```

FastAPI also starts its news, market-data, and AI-worker tasks in-process; there is no separate worker command.

### 1. Install JavaScript dependencies

Install root workspace dependencies from the repository root:

```powershell
npm install
```

### 2. Set up the Python backend

From `apps/stocks`, create and activate a virtual environment, then install dependencies:

```powershell
cd apps/stocks
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

For Windows Command Prompt, activate with `.venv\Scripts\activate`. On macOS/Linux, use `source .venv/bin/activate`.

### 3. Configure environment

Create `apps/stocks/.env` from `apps/stocks/.env.example`.

Backend variables required at startup:

- `APP_ACCESS_TOKEN` or `APP_ACCESS_TOKENS`
- `DATABASE_URL`

AI provider variables:

- Default local provider: `AI_PROVIDER=ollama`, with optional `OLLAMA_BASE_URL` and `OLLAMA_MODEL`
- Hosted provider: `AI_PROVIDER=openai`, `OPENAI_API_KEY`, `OPENAI_MODEL`, and `OPENAI_ALLOWED_MODELS` (the selected model must be allow-listed)

Create `apps/stocks/frontend/.env.local` from `apps/stocks/frontend/.env.example`.

- `NEXT_PUBLIC_API_BASE` — local backend origin; the code defaults to `http://localhost:8000` outside production
- `NEXT_PUBLIC_WS_URL` — optional; otherwise derived from the API base as its `/ws` URL

### 4. Run database migrations

From `apps/stocks`, with the backend environment configured:

```powershell
python -m alembic upgrade head
```

This is required before starting FastAPI against a new or outdated database. Alembic configuration is `apps/stocks/alembic.ini`; revisions are in `apps/stocks/alembic/versions/`. Application startup verifies connectivity but does not create or upgrade the schema. SQLAlchemy models represent tables; they are not separate processes.

### 5. Configure AI

#### Using Ollama (default)

Ollama is optional for FastAPI startup but required for AI analysis when `AI_PROVIDER=ollama`. The code defaults to `OLLAMA_BASE_URL=http://localhost:11434` and `OLLAMA_MODEL=llama3.2`.

Start the runtime and pull the configured default model:

```powershell
ollama serve
ollama pull llama3.2
```

If `OLLAMA_MODEL` changes, pull that configured model instead.

#### Using OpenAI

Set `AI_PROVIDER=openai`, `OPENAI_API_KEY`, `OPENAI_MODEL`, and `OPENAI_ALLOWED_MODELS` as described above. No local model runtime is required.

### 6. Start FastAPI — Terminal 1

From `apps/stocks`, with the virtual environment active:

```powershell
python run.py
```

`run.py` loads `.env`, selects the Windows-compatible asyncpg event loop, and starts `backend.main:app` with reload outside production. It listens on `http://localhost:8000` by default, or the configured `PORT`.

### 7. Start Next.js — Terminal 2

From the repository root:

```powershell
npm run dev:stocks-frontend
```

Or from `apps/stocks/frontend`:

```powershell
npm run dev
```

No Next.js development port is configured in the repository; use the URL printed by Next.js.

### 8. Verify

```powershell
curl http://localhost:8000/health/live
curl http://localhost:8000/health
```

- `/health/live` checks the FastAPI process only.
- `/health` and `/health/ready` check database readiness and return 503 when the database is unavailable.
- Open the Next.js URL printed in Terminal 2, unlock the UI with the configured access token, then confirm the watchlist and market data load.
- Confirm the browser WebSocket connects for live data. Test an AI feature only after configuring its selected provider.

Run `npm run typecheck` and `npm run build` from `apps/stocks/frontend`; the root frontend build command is `npm run build:stocks-frontend`.

## Repository structure

```text
apps/website/       React/Vite frontend and Express/OpenAI backend
apps/projects/      React/Vite frontend and Supabase SQL migrations
apps/stocks/        FastAPI backend, Alembic migrations, and Next.js frontend
packages/           Workspace package manifests (@yapvibes/ui, types, shared, config)
docs/               Environment and deployment reference material
```

The `packages/*` workspaces currently contain package manifests but no source files, so they are not active shared code in this guide.

## Short troubleshooting reference

### Frontend cannot reach a backend

Confirm the backend is running and the frontend environment variable points to its correct host, port, and endpoint. In particular, Website's committed frontend example uses port 3001 while the Express code default is 5000.

### Projects cannot load data

Check `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`, authentication, and the migration state of the target Supabase database.

### Stocks AI is unavailable

Check `AI_PROVIDER`. For Ollama, confirm the runtime is reachable at `OLLAMA_BASE_URL` and has the configured model. For OpenAI, verify its key and model allow-list configuration.

## Author

just-anotherday
