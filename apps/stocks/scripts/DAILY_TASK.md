# Windows daily task lifecycle

Saved analysis reports can now publish automatically to the hosted backend.
See [report publishing setup](../docs/REPORT_PUBLISHING.md) for the dedicated
credential, deployment migration, retries, status endpoint, and history backfill.

The existing `YapVibes Stocks Daily News and Reports` task calls
`run_daily_news_and_reports_task.ps1` at 20:30 Eastern. The older Codex
automation must remain paused. Ollama is managed independently.

The older Codex run's silent hang was reproduced in restricted execution:
Windows asyncio blocked in `socket._fallback_socketpair` while constructing its
event loop, before the pipeline coroutine could emit a stage event. The same
database preflight passed outside the sandbox. Use the existing Windows task
for scheduled runs; a manual diagnostic needs local socket and database access.
The Python entry point now emits `runtime_startup_started` and exits with a
stack diagnostic if event-loop startup exceeds 30 seconds. This watchdog is
cancelled as soon as the coroutine starts and does not limit report runtime.

The pipeline reads report targets from the current database watchlist on every
run, using the same ordered list and 100-ticker ceiling as the application.
News is collected daily; reports run on weekdays in America/New_York using
`qwen3.8:27b`, prompt v3, and up to 50 articles per ticker. Each ticker receives
an outcome in the final JSON log summary. Missing quotes or a failed report
do not stop attempts for the remaining tickers; any failure makes the run exit
nonzero. A scheduled run therefore confirms complete coverage only when its
summary reports zero failures. An empty or unreadable watchlist fails the run.

## Research workspace run tracking

Apply Alembic migration `2026_10_28_research_workspace` before using these
features. The daily pipeline now persists a `report_runs` record, stage, current
ticker, ingestion counts, and each completed/failed outcome. Existing logs are
not imported as successful runs. The research page polls this record every
15 seconds and refreshes the library when an active run finishes.

The authenticated `POST /api/research/runs/{id}/retry` endpoint reserves a new
run and retries only failed or unfinished tickers still in the current watchlist.
It skips news ingestion and never repeats successful outcomes from that run.
The database permits only one queued/running daily or retry run at a time.
Retries execute in the backend process; keep it running until they finish.
If that process is forcibly stopped, six hours without progress marks the run
interrupted and makes its unfinished tickers eligible for another retry.
Ordinary interactive single-report generation is separate from this run history.

Notes and saved/read article state use owner-scoped backend endpoints. Supabase
mode uses the remotely verified allowed user ID; legacy token mode has one shared
owner. New tables have RLS enabled and no browser-role table grants. Notes use
optimistic versions to reject conflicting edits. Browser-only notes require an
explicit import and remain intact locally until the user removes them.

The development entry point remains `.venv\Scripts\python.exe run.py`.
It enables reload outside production. For the scheduled task,
`run_task_backend.py` uses the same `backend.main:app` and
`run:new_selector_event_loop` factory without a reloader. It binds loopback
port 8000 by default. The registered Windows task passes `-BackendPort 8010`
to isolate automation from development/test servers on port 8000. Its readiness
endpoint is `http://127.0.0.1:8010/health/ready`. It loads the existing environment
through `run.py`, without changing that file or `.env`.

The helper sets `STOCKS_TASK_MANAGED_BACKEND=1` only in its own process.
This disables the backend's news scheduler, queue worker, market-report
scheduler, and post-market scheduler. The daily Python pipeline remains
responsible for ingestion and reports, with its existing gates and retries.
Ordinary backend starts keep their existing behavior.

The launcher reuses a server only when `/health/ready` returns HTTP 200 with
`status=ready` and `database=reachable`. An occupied but unhealthy port is a
startup failure, not permission to terminate its owner. A newly started
server must own the listening port and be the launched process or its
direct child (the Windows venv executable can be a redirector).

Readiness is polled at 500 ms intervals with three-second request timeouts
for up to `-BackendStartupTimeoutSeconds` (default 90). The deadline may
overrun by one bounded probe. Cleanup writes a unique per-run stop file;
the helper asks Uvicorn to exit gracefully and execute application shutdown.
After `-BackendShutdownTimeoutSeconds` (default 20), the launcher may force
only its captured process tree to exit. Captured process handles are checked
for exit. A preexisting backend is never shut down.

Exit statuses:

| Status | Meaning |
| --- | --- |
| Pipeline status | Preserved when startup and cleanup succeed |
| 70 | Launcher/dependency failure |
| 71 | Backend startup/readiness failure; pipeline not executed |
| 72 | Cleanup failed after an otherwise successful pipeline |
| 75 | Overlap rejected |

A nonzero pipeline/startup result is preserved if cleanup also fails. Both
statuses are recorded separately. Cleanup guarantees apply to handled
errors; forcibly killing the launcher or Windows shutdown can bypass finally.
The pipeline has no same-day report guard: do not rerun the normal task to
test it after reports have completed.

Safe end-to-end lifecycle validation from the repository root:

```powershell
powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File apps\stocks\scripts\run_daily_news_and_reports_task.ps1 -BackendPort 8010 -DailyArguments --preflight-only
```

Logs reside in `apps/stocks/logs/daily-task/`, named with timestamp and PID:
`runner.log`, pipeline `stdout.log`/`stderr.log`, and backend
`backend.stdout.log`/`backend.stderr.log`. Per-run `backend.pid` and
`backend.stop` files are audit artifacts, not active locks. The shared
`daily-task.lock` prevents overlap through an exclusive open handle.
Runner logs contain startup/readiness, owned PIDs, pipeline exit, cleanup,
and final launcher status. Task Scheduler records the final process exit.

Windows host regression tests use isolated stub backends and pipelines:

```powershell
apps\stocks\.venv\Scripts\python.exe -m pytest apps\stocks\tests\test_daily_task_launcher.py -q -p no:cacheprovider
```
