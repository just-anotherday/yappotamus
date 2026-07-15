# Scripts Directory

Ad-hoc management and diagnostic scripts for the Stock Data Dashboard project.

## ⚠️ Important Notes

- **None of these scripts are part of the application runtime.** They are run manually from the command line.
- Most scripts require environment variables from `.env` to be set (database connection, API keys).
- **Destructive scripts** are marked with a 🗑️ icon. Always review before running in production.
- Run scripts from the project root: `python scripts/<script_name>.py`

---

## Script Index

### Thumbnail Management

| Script | Purpose | Safety | Notes |
|--------|---------|--------|-------|
| `backfill_thumbnails.py` | Primary backfill script — fetches thumbnails for all NULL `thumbnail_url` entries in `news_articles` | ✅ Safe (idempotent, uses retries) | **Use this one** — most robust implementation with retry logic |
| `fill_missing_thumbnails.py` | Alternative approach — uses yfinance title matching to find thumbnails | ✅ Safe | Unique strategy; useful when primary script fails |
| `backfill_all_thumbnails.py` | Earlier version of backfill (superseded) | ✅ Safe | Superseded by `backfill_thumbnails.py` |
| `backfill_missing_thumbnails.py` | Earlier version of backfill (superseded) | ✅ Safe | Superseded by `backfill_thumbnails.py` |
| `backfill_og_thumbnails.py` | Attempts to fetch OpenGraph images from article URLs | ✅ Safe | Experimental; lower success rate |
| `refresh_news_thumbnails.py` | Re-fetches thumbnails for existing articles (overwrite mode) | ✅ Safe | Useful when thumbnail URLs become stale |

### Diagnostics & Inspection

| Script | Purpose | Safety | Notes |
|--------|---------|--------|-------|
| `check_thumbnails.py` | Count articles with/without thumbnails | ✅ Read-only | Quick stats |
| `check_thumbnail_urls.py` | Validate thumbnail URL formats | ✅ Read-only | |
| `check_thumbnail_domains.py` | Analyze distribution of thumbnail domains | ✅ Read-only | |
| `check_thumbnail_stats.py` | Detailed thumbnail statistics (NULL count, by source, etc.) | ✅ Read-only | Most comprehensive |
| `check_other_thumbnails.py` | Check thumbnails from non-Finnhub sources | ✅ Read-only | |
| `check_current_stats.py` | General database statistics | ✅ Read-only | |
| `check_all_keys.py` | Inspect all keys in raw JSON payloads | ✅ Read-only | Debug helper |
| `diag_null_thumbs.py` | Diagnose why thumbnails are NULL (network errors, missing fields) | ✅ Read-only | Most detailed diagnostic |

### Data Inspection & Debugging

| Script | Purpose | Safety | Notes |
|--------|---------|--------|-------|
| `check_raw_json.py` | Dump raw JSON from news articles for inspection | ✅ Read-only | |
| `check_author_provider.py` | Inspect author and provider fields in news data | ✅ Read-only | |
| `check_yf_voo.py` | Test yfinance data for VOO specifically | ✅ Read-only | Debug helper |
| `test_yf_fallback.py` | Test yfinance fallback functionality | ✅ Read-only | |

### Data Modification

| Script | Purpose | Safety | Notes |
|--------|---------|--------|-------|
| `clear_yahoo_placeholders.py` | 🗑️ Clear Yahoo placeholder values from thumbnails | ⚠️ Destructive | Sets thumbnail_url to NULL for Yahoo-sourced placeholders |
| `migrate_news_table.py` | 🗑️ Database migration helper for news_articles schema changes | ⚠️ Destructive | Use only when schema changes are needed |
| `add_data_source_columns.py` | 🗑️ Add data_source and author columns to news table | ⚠️ Destructive | One-time migration script |

---

## Common Usage Examples

### Check thumbnail coverage
```bash
python scripts/check_thumbnail_stats.py
```

### Fill missing thumbnails
```bash
python scripts/backfill_thumbnails.py
```

### Diagnose why thumbnails are missing
```bash
python scripts/diag_null_thumbs.py
```

### Inspect raw API responses
```bash
python scripts/check_raw_json.py
```

---

## Required Environment Variables

Most scripts require:

- `DATABASE_URL` — PostgreSQL connection string
- `FINNHUB_API_KEY` — Finnhub API key (for thumbnail fetching scripts)

Ensure your `.env` file is configured before running.

---

## Maintenance Notes

- Scripts prefixed with `check_` are generally safe read-only operations.
- Scripts prefixed with `backfill_` write to the database but are idempotent (safe to re-run).
- Scripts prefixed with `clear_` or `migrate_` make destructive changes — review code first.
- Consider consolidating the 7 diagnostic scripts into a single `diagnostics.py` with CLI subcommands (deferred to future refactoring).
