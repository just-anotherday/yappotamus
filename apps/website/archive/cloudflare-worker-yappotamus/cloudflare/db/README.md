# D1 Leaderboard Schema Guide

This folder documents the **expected leaderboard schema** and migration workflow.

## Source of truth

- Migration files: `cloudflare/migrations/`
- Wrangler config: `wrangler.jsonc` (`d1_databases[].migrations_dir` points to `cloudflare/migrations`)
- Expected final structure: `cloudflare/db/schema-current.sql`

## Migration order

1. `0001_leaderboard.sql` (base table)
2. `0002_leaderboard_aggregates.sql` (adds rounds + aggregate columns)

## Apply migrations (remote)

```bash
npx wrangler d1 migrations apply yappotamus-leaderboard --remote
```

## Quick API verification

```bash
curl "https://www.yapvibes.com/api/leaderboard"
```

Entries should include:

- `score`
- `rounds`
- `avgWpm`
- `avgAccuracy`
