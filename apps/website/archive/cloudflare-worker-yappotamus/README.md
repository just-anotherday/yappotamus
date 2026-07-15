# Archived Cloudflare Worker (yappotamus)

This directory contains the old Cloudflare Worker configuration and code from the pre-migration yappotamus project.

## What's Here

- `wrangler-root.jsonc` - Root-level Wrangler config (named "yappotamus", D1 database binding)
- `cloudflare/` - Worker source, D1 migrations, DB schema

## Why Archived

The YapVibes monorepo now uses Cloudflare Pages for deployment instead of Workers. These files are preserved in case the leaderboard/Worker functionality is reused for future games and applications.

## Original Structure

```
yappotamus/
├── wrangler.jsonc          → archived as wrangler-root.jsonc
├── cloudflare/
│   ├── worker.js           → API handler (leaderboard CRUD + static assets proxy)
│   ├── wrangler.jsonc      → Alternate Wrangler config
│   ├── migrations/         → D1 schema migrations
│   └── db/                 → Schema documentation
```

## D1 Database Note

The original Worker used a D1 database (`yappotamus-leaderboard`, ID: `e73a778b-bcc1-4388-8fa5-b5fa8a1eb174`). If reusing this code, ensure the database still exists in your Cloudflare account.
