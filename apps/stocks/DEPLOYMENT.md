# YapVibes Stocks - Deployment Guide

## Architecture

```
Frontend (Next.js 16)          Backend (FastAPI/Python 3.12)
├── Cloudflare Worker   ──▶   Render / Self-hosted Docker
└── Vercel (optional)         Supabase PostgreSQL (DB)
                              OpenAI API (production AI)
```

---

## Backend Deployment (Render)

### Prerequisites
- Render account + web service created
- Supabase PostgreSQL instance running
- OpenAI API key for production AI analysis

### Environment Variables (set in Render dashboard)

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | **Yes** | Supabase PostgreSQL connection string |
| `ENVIRONMENT` | **Yes** | Set to `production`; disables development reload behavior and the in-process news scheduler. |
| `APP_ACCESS_TOKEN` | **Yes** | Private token used by the frontend for authenticated API/WebSocket access |
| `FINNHUB_API_KEY` | **Yes** | Market data API key |
| `FINNHUB_REQUESTS_PER_MINUTE` | No | Defaults to and is capped at `45`, reserving 25% below Finnhub Free's 60/minute ceiling. |
| `INTERNAL_JOB_TOKEN` | **Yes** for scheduled ingestion | Dedicated bearer token accepted only by `POST /internal/jobs/news-ingest`. |
| `NEWS_SCHEDULER_ENABLED` | **Yes** in production | Set `false`; the GitHub workflow is the production scheduler. |
| `NEWS_OVERLAP_MINUTES` | No | Defaults to `30`; combined with the 15-minute cadence this normally replays 45 minutes. |
| `NEWS_MAX_BACKFILL_HOURS` | No | Defaults to `72`; bounds recovery after an outage. |
| `NEWS_ENQUEUE_COMPANY_REPORTS` | No | Defaults to `false` so news collection cannot trigger unrelated quote/profile refreshes. |
| `YFINANCE_CACHE_DIR` | No | Writable yfinance SQLite cache path. Defaults to OS temp; it is an optimization and can remain ephemeral on Render. |
| `OPENAI_API_KEY` | **Yes** (prod) | OpenAI API key for AI analysis |
| `AI_PROVIDER` | No | Set to `openai` (default: `ollama`) |
| `OPENAI_MODEL` | No | Model name (default: `gpt-4o-mini`) |
| `OPENAI_ALLOWED_MODELS` | **Yes** when OpenAI is used | Must include `OPENAI_MODEL` (for example `gpt-4o-mini`) |
| `CORS_ORIGINS` | **Yes** | Include `https://stocks.yapvibes.com` and the Worker preview domain |
| `AI_STALE_JOB_RECOVERY_ENABLED` | No | Keep `false` until protected queue timestamps are verified |
| `PORT` | No | Override default port 8000 |

### Deployment Steps

Render Free does not execute pre-deploy commands. Production therefore uses the
dedicated `.github/workflows/stocks-production-release.yml` check as the schema
gate. The required ordering is:

```text
GitHub migration job succeeds
        -> Render deploys the same main-branch commit
        -> Render verifies /health/ready
        -> operator verifies production
```

Configure the release path as follows:

1. Connect Render to the GitHub repository, branch `main`, with service root
   directory `apps/stocks`, runtime `Docker`, and Dockerfile `Dockerfile`.
2. Store the production Supabase session-pooler connection string as the
   `STOCKS_DATABASE_URL` secret in the GitHub `stocks-production` environment.
   Restrict that environment to the `main` branch. Do not put the value in the
   workflow, repository, logs, or documentation.
3. Configure matching Render included-path filters for the backend image inputs:
   `apps/stocks/backend/**`, `apps/stocks/alembic/**`,
   `apps/stocks/alembic.ini`, `apps/stocks/Dockerfile`,
   `apps/stocks/requirements.txt`, and `apps/stocks/run.py`.
4. In Render, set **Auto-Deploy** to **After CI Checks Pass**. Do not use
   **On Commit**: the migration check is the release gate.
5. Set the Render workspace's **Overlapping Deploy Policy** to **Wait**. Render
   may skip an intermediate deploy when several commits arrive, but it must not
   cancel an in-progress deploy.
6. Keep the Render Docker Command empty so the image uses the Dockerfile
   `CMD`. Do not add migrations to application startup.
7. Keep the Render pre-deploy command empty on the Free plan; it is not an
   enforceable migration mechanism on that tier.
8. Set the Render health-check path to `/health/ready`, which verifies database
   connectivity. `/health/live` remains the process-only liveness endpoint.
9. Set `ENVIRONMENT=production` and `NEWS_SCHEDULER_ENABLED=false`; production
   article collection is initiated externally.

The workflow and Render build filters cover the same backend image inputs, so
frontend, documentation, and test-only commits do not run a production
migration or redeploy the backend. The additional workflow-file trigger
self-validates release-gate changes without triggering Render. The workflow can
also be invoked manually on `main`. It serializes production schema work with the
`production-stocks-release` concurrency group and does not cancel an in-flight
migration. It applies `python -m alembic upgrade head`, then requires
`python -m alembic current --check-heads` to pass. A missing secret, connection
failure, migration failure, or revision mismatch fails the check. Render must
then leave the previous healthy deployment running.

Migrations must be backward-compatible with the version already serving
traffic. Use expand-first changes; perform destructive contract changes only
in a later release after all running application versions no longer depend on
the old schema. Never automatically downgrade production after a failed
application deployment.

### Production Release Verification

For each release:

1. Confirm the `Stocks production release gate / Migrate production database`
   check passed for the exact commit being released.
2. Confirm Render deployed that same commit and reports it as **Live**.
3. Require HTTP 200 from both `/health/live` and `/health/ready`.
4. Confirm the successful workflow log includes
   `python -m alembic current --check-heads`; do not copy the production
   database URL to an operator shell for routine verification.
5. Check the authenticated `/api/operations/status` response and sanitized
   Render logs for database, startup, authentication, and feature errors.

If the migration workflow fails, stop. Diagnose or safely roll forward the
migration and rerun the gate. Do not manually deploy the new application,
stamp the database, edit an applied migration, or auto-downgrade the schema.

### Emergency Manual Release Gate

Manual Render deployments bypass CI and build filters, so use this procedure
only when GitHub Actions is unavailable:

1. Set Render Auto-Deploy to **Off** and positively identify the production
   Supabase project and database.
2. From the exact commit to release, inject `DATABASE_URL` from a secure secret
   store and run `python -m alembic upgrade head` from `apps/stocks`.
3. Run `python -m alembic current --check-heads`. Stop if either command fails.
4. Manually deploy that exact commit in Render.
5. Verify `/health/live`, `/health/ready`, the deployed commit, authenticated
   operations status, and relevant sanitized logs.
6. Restore **After CI Checks Pass** before resuming normal releases.

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
| `NEXT_PUBLIC_API_BASE` | **Yes** | `https://yapvibes-stocks-api.onrender.com` |
| `NEXT_PUBLIC_WS_URL` | No | Optional override; normally derived as `wss://yapvibes-stocks-api.onrender.com/ws` |

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

### Scheduled Article Collection

The production collector is a one-shot, authenticated internal operation. GitHub
Actions supplies an hourly baseline plus weekday quarter-hour triggers spanning
both EDT and EST, and can be run manually with `workflow_dispatch`; it wakes
Render if necessary. The workflow labels baseline versus quarter-hour triggers,
and the service applies the authoritative runtime schedule guard
in `America/New_York`: on weekdays from 4:00 AM until 8:00 PM it runs every 15
minutes, while overnight and on weekends it runs only once per hour.
Manual `workflow_dispatch` runs append `force=true` to bypass that cadence guard
and collect immediately.
Keep the production in-process scheduler disabled with
`NEWS_SCHEDULER_ENABLED=false`. Configure these repository secrets (names only):
`STOCKS_API_URL` and `STOCKS_INTERNAL_JOB_TOKEN`.

After the Render deployment, require HTTP 200 from `/health/live` and
`/health/ready`, then inspect the latest scheduled GitHub Actions run and the
authenticated `/api/operations/status` response. Confirm the checkpoint
advanced, consecutive failures are zero, and no lease is stuck. Only use one
manual `workflow_dispatch` if no scheduled run has occurred since the release;
do not repeatedly dispatch ingestion. The production watchlist must contain
tickers; startup seeds defaults when its migration tables are available.

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
| `GET /health` and `GET /health/ready` | Database-connectivity readiness probe |
| `GET /api/operations/status` | Authenticated database, provider, worker, and ingestion diagnostics |
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
2. Check Render firewall allows outbound connections to Supabase
3. Test with `curl https://YOUR-RENDER-BACKEND/health/ready`

### AI Provider Errors
1. Confirm `AI_PROVIDER` matches available credentials
2. For OpenAI: verify API key has Chat Completions access
3. For Ollama: ensure the model is pulled and running locally
