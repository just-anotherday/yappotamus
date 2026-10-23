# Stocks launch review — October 23, 2026

Status: **Local code and deployment-build checks passed. Deploy and verify the production owner workflows before release.**

## Production finding — remediated

A read-only check of the saved production Supabase connection found row-level
security disabled on `analysis_reports`, `news_articles`, `watchlist`, and
`assets`, with SELECT grants to both `anon` and `authenticated`. These grants
could allow the Supabase Data API to bypass the backend owner allowlist. The Data
API currently returns PGRST002/schema-cache errors; that does not establish
that the data is protected. No exposure or exploitation is asserted by this check.

Prepared migration: `alembic/versions/2026_10_23_private_app_tables.py`.
It enables row-level security and removes PUBLIC/anon/authenticated privileges
on 21 explicitly named Stocks tables. It does not change unrelated tables or
Supabase Auth. The saved production database role is `postgres` with BYPASSRLS;
its backend access is preserved. No public-readable views were found.

The migration passed a local PostgreSQL transaction test that seeded public
SELECT grants, verified their removal, verified owner access, and required an
actual permission-denied error under the anon role. All test changes rolled
back. It was then applied successfully to the local database. Following explicit
user approval, it was applied to production at revision
`2026_10_23_private_app_tables`. All 21 app tables were verified with RLS enabled
and public-role SELECT privileges removed. Backend reads and the deployed
readiness probe passed afterward. An automatic downgrade deliberately refuses
to reopen access. The normal release migration gate will recognize this revision.

## Other launch requirements

- Supabase public Auth settings now verify `disable_signup=true`; anonymous
  sign-in is also disabled. The user disabled signup in the dashboard.
- Cloudflare/OpenNext build now passes. Two ignored legacy lockfiles were
  making the adapter detect the frontend as a standalone repository. Removed
  them and set Next.js outputFileTracingRoot to the repository root, allowing
  OpenNext to patch hoisted Next.js dependencies and omit native Sharp.
- Frontend lint now passes with **zero errors and zero warnings**. Added concrete
  response types, cancelled obsolete report requests, removed redundant effects,
  fixed the price-flash ref, and subscribed theme state to browser storage.
  Unified report pagination now fetches each requested page and keeps applied
  filters separate from unsubmitted edits. News thumbnails use unoptimized Image
  components, preserving external publisher image delivery.
- Local generated Worker smoke checks passed: /api/health, /healthz, the logo
  asset, and /_next/image each returned HTTP 200. The Worker preview was stopped
  and its generated output removed after verification; build:cf regenerates it.
- Local test/development artifacts under .wrangler are excluded from source
  control and lint; application source remains checked normally.
- Confirm the production frontend and backend use matching Supabase Auth
  configuration from `supabase-login.md`, then verify owner login, restoration,
  sign-out, report generation, and news sync on the deployed build. This sweep
  did not use an owner production session or create paid AI reports.
- Verify the normal production migration gate, database backups/restore
  arrangements, and the next external news-ingestion run before release.

## Fixes completed locally

- Updated Next.js and its ESLint configuration to 16.4.3; patched source-map and
  compatible build-tool dependencies. npm now reports zero known vulnerabilities
  across production and development dependencies.
- Updated python-dotenv, soupsieve, pytest, and pytest-asyncio to patched versions.
  The installed Python audit reports zero known vulnerabilities and pip check
  reports no broken requirements.
- Eager-load assets in asynchronous ticker lookups to eliminate startup
  MissingGreenlet errors. A read-only local lookup and restarted-server logs
  confirmed the fix.
- Reject non-ASCII/control-character authentication tokens before contacting
  Supabase; compare machine credentials without Unicode comparison exceptions.
- Validate external article/company links and match publisher domains by domain
  boundary, preventing lookalike hostnames from passing publisher checks.
- Mark private API/internal responses no-store and nosniff. Added frontend
  restrictions on framing, embedded objects, base URL changes, and unused
  camera/microphone/geolocation permissions. The CSP is deliberately limited;
  it is not a complete script-src policy.
- Fixed outdated correction-retry test expectations without changing the
  pipeline's validation/persistence boundary, and removed live Finnhub calls
  from two provider-outage tests.

## Verification evidence

- Backend full suite: **1,384 passed, 14 skipped**. The skipped tests require
  separately configured disposable PostgreSQL concurrency/migration fixtures.
- Additional live PostgreSQL permission-migration regression: **1 passed**.
- Frontend unit tests: **84 passed**.
- Next.js 16.4.3 production build and Cloudflare/OpenNext build: **passed**, including TypeScript.
- Frontend lint: **0 errors, 0 warnings**.
- Frontend/backend endpoint-contract tests: **19 passed**.
- npm audit (all dependencies): **0 known vulnerabilities**, rechecked after the final changes.
- pip-audit (installed environment): **0 known vulnerabilities**; pip check passed.
- Local frontend and backend readiness: HTTP 200 after restart. Private auth
  request returned 401 with no-store and nosniff; startup asset errors were absent.
- Deployed backend readiness: HTTP 200. Unauthenticated `/news`,
  `/api/auth/verify`, and `/api/operations/status` requests returned 401.
- A bounded tracked-file scan found no matching OpenAI secret, Supabase secret
  key, or private-key signatures in the Stocks source. Database-URL pattern
  matches were examples and test fixtures; this is not a full history audit.

The approved production permission migration was applied without an app
deployment. No credential rotation was performed. The local app continues
to use the user's local `news` database.

## Housekeeping

Removed approximately 121 MiB of stale test fixtures, review logs, obsolete
dependency staging files, and generated Cloudflare output. Removed the
temporary isolated Python audit tool. Original source assets, env configuration,
source changes, migrations and tests were retained. Active server logs and the
running development build were retained. The obsolete `.open-next` files had
been tracked despite being generated; their deletion prevents stale output
from being retained in source control. A successful build will regenerate them.

The user manually deleted the three Windows-protected test folders below.
Their removal was verified; no blocked cleanup folders remain:

- `C:/Users/jason/Development/YapVibes/.pytest_tmp_stocks`
- `C:/Users/jason/Development/YapVibes/apps/stocks/.pytest_tmp_merge_launcher`
- `C:/Users/jason/Development/YapVibes/apps/stocks/.pytest_tmp_unsupported_convergence`

## References

- [Next.js image optimization advisory](https://github.com/advisories/GHSA-2464-fhr4-w9xw)
- [source-map-js advisory](https://github.com/advisories/GHSA-68fv-2mgg-jv7q)
- [Supabase signup configuration](https://supabase.com/docs/guides/auth/general-configuration)


## Final local follow-through

No app deployment was performed. The successful Worker build used the production
API URL through a process environment override; the user's .env.local file was
not changed. Production hosting must provide the public Supabase Auth variables
listed in DEPLOYMENT.md. The local frontend and backend are left running for testing.
