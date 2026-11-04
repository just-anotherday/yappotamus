# Automatic report publishing

Local analysis reports (including the daily Windows task and interactive ticker
analysis) are queued in the same transaction as the saved report. A local backend
uploads pending reports every 30 seconds. The daily pipeline also attempts a final
flush before its temporary backend shuts down. Failed uploads retry with delays
from 30 seconds to one hour; queued work survives restarts. Retries require a
running local backend, a subsequent daily task, or the standalone command below.

The cloud saves reports in its existing `analysis_reports` table, so they appear
in the deployed analysis report library without frontend changes. Cloud report IDs
are independent of local IDs. The original UTC generation timestamp is preserved.

## Configure and activate

1. Deploy the updated Stocks backend to Render, with a separate production
   database. Apply `python -m alembic upgrade head` on both local and cloud
   databases before starting the updated processes. The new migration follows
   `2026_10_28_research_workspace`; deploy that migration and its app changes too.
2. Use the generated `REPORT_PUBLISH_TOKEN` in the local Stocks `.env`, or
   generate a random replacement using a password manager (at least 32 characters).
   Set `REPORT_PUBLISH_TOKEN` to the same value in the local Stocks `.env` and
   Render's backend environment. Do not paste secrets into chat or commit them.
3. On the local machine only, set:

   ```dotenv
   REPORT_PUBLISH_URL=https://yapvibes-stocks-api.onrender.com
   ```

   Leave `REPORT_PUBLISH_URL` empty on Render. Restart the local and cloud
   backends after setting environment variables. Keep the hosted frontend at
   `stocks.yapvibes.com` pointed at this hosted API.
4. Generate a report locally, or upload existing reports using the command below.
   Confirm the report appears after signing in to the hosted analysis report
   library. Never rerun report generation just to retry uploads.

From `apps/stocks`:

```powershell
# Retry due pending uploads only; no model calls or news collection.
.venv\Scripts\python.exe scripts\publish_reports.py

# Optionally publish existing saved analysis reports. Safe to repeat.
.venv\Scripts\python.exe scripts\publish_reports.py --backfill
```

Each command sends at most 500 due reports in a pass of roughly one minute
(plus the final bounded request). An HTTP failure stops that pass. Repeat for a larger backlog; failed
items respect backoff. Exit status 1 means reports remain pending. The owner-only
`GET /api/analysis/publishing/status` endpoint on the local API shows pending,
retrying, published, and last successful upload time. It contains no credentials.
Daily logs emit `report_publishing_completed` with counts; generation outcome and
publishing outcome are separate. A failed publishing attempt makes the daily
command exit nonzero even if generation succeeded. Status on the hosted API
describes that server's outbound queue, not your computer's queue.

## Security and behavior

- Only outbound HTTPS from the computer is needed. No local database port,
  router forwarding, or inbound tunnel is needed.
- `PUT /api/internal/report-publications/{uuid}` accepts only the dedicated
  publishing token. It cannot use that credential to list, read, or delete
  reports, or call generation endpoints. Existing owner authentication still
  protects web report viewing.
- Request bodies are limited to 2 MiB. Redirects are never followed. Receipts
  deduplicate deliveries atomically, including after a lost acknowledgement.
  A UUID reused with different content is rejected. Cloud deletion keeps the
  receipt, preventing a delayed retry from recreating a deleted report.
- New queue/receipt tables have RLS enabled and no browser-role grants. Use the
  trusted backend database role, consistent with the existing private tables.
- Changing the target origin does not silently redirect existing queued reports.
  Existing items fail until the original origin is restored; moving publication
  history to another deployment requires an explicit queue migration.
- This publishes immutable report snapshots only. It does not sync local news
  article rows, watchlists, research notes, report-run history, deletions, or the
  separate company/sector/market intelligence cache. Citation text and source
  URLs travel inside report JSON; local article IDs do not identify cloud rows.
  Do not configure local development to use the production database.
- Disable local publishing by clearing `REPORT_PUBLISH_URL`; pending rows stay
  intact. Rotate the publishing token on both sides if needed.
