# News Data Source Tagging

## Overview

Each news article stored in `news_articles` is tagged with two tracking fields that distinguish **which API delivered the article** and **who originally authored/published it**.

| Column | Type | Example Values | Description |
|--------|------|----------------|-------------|
| `data_source` | `TEXT` | `"finnhub"`, `"yfinance"` | Which backend API fetched and delivered the article |
| `author` | `TEXT` | `"ChartMill"`, `"Benzinga"`, `"Yahoo Finance"` | The original publisher/author of the article content |

## Why Two Fields?

Finnhub aggregates news from many publishers. An article delivered via the Finnhub API might originally be written by Benzinga, ChartMill, Reuters, etc. Previously, `provider_name` stored the publisher but there was no way to tell which API (Finnhub vs yfinance) actually fetched it.

- **`data_source`** = the delivery pipeline (Finnhub REST API, yfinance fallback)
- **`author`** = the original content creator (extracted from Finnhub's `source` field)

## Database Schema

```sql
ALTER TABLE news_articles
    ADD COLUMN data_source TEXT DEFAULT 'finnhub',   -- API that delivered it
    ADD COLUMN author TEXT;                          -- Original publisher

CREATE INDEX idx_news_articles_data_source ON news_articles (data_source);
```

### Migration

Run the additive migration script (safe, does NOT drop data):

```bash
python scripts/add_data_source_columns.py
```

This will:
1. Add `data_source` column (default `'finnhub'`) if missing
2. Add `author` column if missing
3. Back-fill `author` from existing `provider_name` values for all 595+ rows
4. Create the `idx_news_articles_data_source` index

The script is idempotent — running it multiple times is safe (no-op if columns exist).

## Backend Flow

### Normalization (`news_ingestion_service.py`)

```python
def normalize_finnhub_article(article: Dict, ticker: str) -> NewsArticleIngest:
    return NewsArticleIngest(
        ...
        provider_name=article.get("source"),   # e.g. "ChartMill"
        data_source="finnhub",                  # Hard-coded: Finnhub delivered it
        author=article.get("source"),           # Same as provider_name for now
        ...
    )
```

### UPSERT Logic

Both `ingest_article()` and `batch_ingest_articles()` include `data_source` and `author` in their `ON CONFLICT DO UPDATE` clauses, ensuring existing rows stay in sync when re-ingested.

## Frontend Display

### Badge Rendering (`NewsFeed.tsx`)

Each article card shows up to 3 badges:

```
[AAPL]  [ChartMill]  [● Finnhub]
 ^         ^              ^
ticker   author      data_source badge
```

| `data_source` value | Color | Dot |
|---------------------|-------|-----|
| `"finnhub"` | Orange (`bg-orange-100 text-orange-700`) | 🟠 orange dot |
| `"yfinance"` | Blue (`bg-blue-100 text-blue-700`) | 🔵 blue dot |
| `null` / missing | Hidden | — |

### TypeScript Interface (`types/stock.ts`)

```typescript
export interface NewsArticle {
  id: number;
  finnhub_id?: string | null;
  ticker: string | null;
  title: string | null;
  summary: string | null;
  provider_name: string | null;
  data_source?: string | null;   // "finnhub" | "yfinance"
  author?: string | null;        // Original publisher
  pub_date: string | null;
  article_url: string | null;
  thumbnail_url: string | null;
  imported_at: string | null;
}
```

## Filtering (Future Enhancement)

The `data_source` index enables efficient filtering queries:

```sql
-- Only show Finnhub-delivered articles
SELECT * FROM news_articles WHERE data_source = 'finnhub' ORDER BY pub_date DESC;

-- Only show yfinance fallback articles
SELECT * FROM news_articles WHERE data_source = 'yfinance' ORDER BY pub_date DESC;

-- Count by source
SELECT data_source, COUNT(*) FROM news_articles GROUP BY data_source;
```

This could power a UI toggle: "Show only Finnhub" / "Show only yfinance" / "Show all".

## Migration History

| Date | Script | Action |
|------|--------|--------|
| 2026-06-18 | `migrate_news_table.py` | Initial news table creation (Finnhub-aligned schema) |
| 2026-06-19 | `add_data_source_columns.py` | Add `data_source` + `author` columns, back-fill, index |
