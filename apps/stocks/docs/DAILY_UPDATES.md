# Shared Daily Updates

The live website's `/daily-updates` page owns the watchlist and independent
`news_enabled` / `reports_enabled` preferences. The overview's add/remove/reorder
controls use the same list. Existing articles and saved reports are retained.
Empty lists remain empty across restarts; they do not reseed defaults.

Deploy migration `2026_11_06_daily_updates` through the production migration gate
before the backend release, then deploy the frontend. Existing tickers retain
both preferences enabled. Existing rows are not queued for another initial fetch.

After the live machine endpoint is available, set only on the local computer:

```dotenv
DAILY_UPDATES_SYNC_ENABLED=true
```

The existing local `REPORT_PUBLISH_URL` and matching `REPORT_PUBLISH_TOKEN` are
reused. No new secret is required. Keep `REPORT_PUBLISH_URL` empty on the hosted
backend. Restart the local backend after enabling synchronization. The opt-in
flag prevents scheduled runs from requiring an endpoint before it is deployed.

Every 30 seconds while the local backend runs, it pulls a validated, bounded
snapshot from `GET /api/internal/daily-updates`, applies it atomically to its
own database, and acknowledges its revision at
`POST /api/internal/daily-updates/ack`. This is outbound HTTPS; neither local
database access nor an inbound tunnel is required. The same publishing credential
now also permits reading ticker preferences and submitting a bounded worker
acknowledgement. It cannot edit preferences; those endpoints require owner login.
Local owner edits are forwarded with the owner's existing login to the live API.
Redirects are never followed and credentials are not included in logs.

The daily script pulls settings again before ingestion or report generation.
If live settings cannot be validated/received/acknowledged, that run stops before
generating reports from an outdated list. An intentionally empty or fully paused
report list is valid. Failed-only retries respect the reports-enabled list.

Adding a ticker or enabling its news switch creates a durable initial-fetch
request on each backend. Separate workers claim these requests, show their status,
and retain failures for retry after five minutes. Normal scheduled collection
reads only news-enabled tickers. Report generation reads only report-enabled
tickers; it may use existing articles when news is paused. Disabling/removing a
ticker stops subsequent cycles; work already in progress may finish.

The page distinguishes saved settings from the exact revision acknowledged by
the computer. A check-in older than two minutes is shown as offline; acknowledgement
does not mean a report was generated. Local and hosted news databases each collect
news using the shared preferences; this is not an article-row replication system.
Report snapshots continue to publish through the existing durable queue.

Production news cadence still uses the existing externally triggered workflow.
The in-process initial-fetch worker handles pending additions while awake and
resumes after restart; it is separate from the normal news scheduler.

Validation:

```powershell
$env:RUN_DAILY_UPDATES_DB_TESTS='1'
.venv\Scripts\python.exe -m pytest tests/test_daily_updates.py tests/test_daily_news_and_reports_preflight.py -q
```

Database integration tests create and remove only UUID-named disposable schemas.
