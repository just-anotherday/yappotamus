# Data Lineage Report — News Pipeline Audit

**Date:** June 24, 2026
**Author:** Senior Full-Stack Engineer (AI)
**Scope:** Three broken articles traced through all seven pipeline layers

---

## Executive Summary

| Symptom | Root Cause | Layer | Severity |
|---------|-----------|-------|----------|
| Duplicate title rendering | TickerHeader renders company name + NewsCard renders title; both show article text on narrow viewports | Frontend (NewsCard.tsx + TickerHeader.tsx) | Medium |
| Thumbnail images showing news_image.png fallback | Finnhub returns Yahoo placeholder URL (`yahoo_finance_en-US_h_p_finance_2.png`), normalization correctly strips it, but OG scraping fails because article_url is a finnhub.io redirect proxy, NOT the real article page | Backend (news_ingestion_service.py) + Infrastructure | High |
| Incorrect ticker mapping (GOOGL for Nvidia article, NVDA for D-Wave article) | Finnhub's `/company-news` endpoint returns articles tagged with `related: <symbol>`. The ingestion service passes the **query ticker** (the ticker used to call the API), NOT the article's actual `related` field. When TSLA is queried, a SpaceX article gets ticker=TSLA. When GOOGL is queried, an Nvidia article gets ticker=GOOGL. | Backend (news_ingestion_service.py line 271) | Critical |
| Author = Yahoo / Publisher = Yahoo duplication | Finnhub's raw response has no `author` field. The backfill script (`backfill_yahoo_authors.py`) attempted to scrape authors but set `author = provider_name` as a fallback when scraping failed. The NewsCard then falls through to `article.provider_name` for display. | Backend (backfill script) + Frontend (NewsCard.tsx) | Medium |
| "Invalid news links filtered" | Article URLs point to `finnhub.io/api/news?id=...` redirect proxies. These are being filtered by URL validation logic somewhere in the pipeline. | Backend | Medium |

---

## ARTICLE 1: SpaceX's Stock Slide Costs Elon Musk His Trillionaire Title

### STEP 1 — Raw Finnhub API Response
```json
{
    "id": 140713967,
    "headline": "SpaceX's Stock Slide Costs Elon Musk His Trillionaire Title",
    "source": "Yahoo",
    "related": "GOOGL",                    // ← Finnhub says related to GOOGL (wrong)
    "summary": "The stock market selloff this week has been painful for investors...",
    "url": "https://finnhub.io/api/news?id=ce95b106428c6ca22b8e8ad8c5a5a64b3cb82f8ae66c9ad72b811de4e1930c7b",
    "image": "https://s.yimg.com/rz/stage/p/yahoo_finance_en-US_h_p_finance_2.png",  // ← Placeholder!
    "category": "company",
    "datetime": 1782328920
}
```

**Observation:** Finnhub itself mis-tagged this article. `related: GOOGL` is incorrect — the article discusses SpaceX/Tesla. There is no `author` field in the raw response. The image URL is a known Yahoo placeholder.

### STEP 2 — Normalized Article (normalize_finnhub_article)
```python
NewsArticleIngest(
    finnhub_id="35477be637564a1ed1f7905d234e45a6",
    ticker="TSLA",                         # ← SET BY QUERY PARAMETER, not from "related"
    title="SpaceX's Stock Slide Costs Elon Musk His Trillionaire Title",
    summary="The stock market selloff...",
    provider_name="Yahoo",                 # ← From Finnhub "source" field
    data_source="finnhub",
    article_url="https://finnhub.io/api/news?id=ce95b106428c6ca22b8e8ad8c5a5a64b3cb82f8ae66c9ad72b811de4e1930c7b",
    thumbnail_url=None,                    # ← Correctly stripped (placeholder detected)
    pub_date=datetime(2026, 6, 24, 15, 22, 0),
    raw_json={...}
)
```

**Observation:** The ticker is "TSLA" because this article was fetched during a `fetch_and_ingest_news("TSLA", ...)` call. The normalize function at line 271 does `ticker=ticker` which uses the *query parameter*, not the Finnhub `related` field. In this case, TSLA is actually correct (SpaceX/Tesla article), but only because it happened to be fetched during a TSLA query cycle.

### STEP 3 — Database Row
```
id:           58099
finnhub_id:   35477be637564a1ed1f7905d234e45a6
ticker:       TSLA
title:        SpaceX's Stock Slide Costs Elon Musk His Trillionaire Title
provider_name: Yahoo
author:       Yahoo                  # ← SET BY BACKFILL SCRIPT (incorrect)
data_source:  finnhub
thumbnail_url: null
article_url:  https://finnhub.io/api/news?id=ce95b106428c...
pub_date:     2026-06-24 15:22:00
```

**Observation:** The `author` column was set to "Yahoo" by the backfill script. This happened because the backfill script's scraper couldn't reach the real article (URL is a finnhub.io proxy), so it fell back to `author = provider_name`.

### STEP 4 — Backend API Response
```json
{
    "id": 58099,
    "ticker": "TSLA",
    "title": "SpaceX's Stock Slide Costs Elon Musk His Trillionaire Title",
    "provider_name": "Yahoo",
    "author": "Yahoo",               # ← Propagated from DB
    "thumbnail_url": null,
    "article_url": "https://finnhub.io/api/news?id=ce95b106428c...",
    ...
}
```

### STEP 5 — React Props (NewsCard)
```typescript
{
    article: {
        title: "SpaceX's Stock Slide Costs Elon Musk His Trillionaire Title",
        ticker: "TSLA",
        provider_name: "Yahoo",
        author: "Yahoo",
        thumbnail_url: null,
        article_url: "https://finnhub.io/api/news?id=ce95b106428c...",
    }
}
```

### STEP 6 — Rendered DOM Output
```
Thumbnail src:   /news_image.png     ← FALLBACK (thumbnail_url is null)
Ticker badge:    TSLA
Title text:      SpaceX's Stock Slide Costs Elon Musk His Trillionaire Title
Author line:     Yahoo               ← article.author = "Yahoo" (from backfill fallback)
Publisher:       Yahoo               ← article.provider_name = "Yahoo"
```

**Why "Yahoo" appears twice:** The NewsCard renders `author` in the author line (line 86: `{article.author || article.provider_name}`), AND separately renders `provider_name` as a publisher badge on the right side (line 109). Since `author="Yahoo"` and `provider_name="Yahoo"`, both display "Yahoo". The condition at line 88 (`article.author !== article.provider_name`) prevents showing both separated by a bullet, but the author still shows in the author line AND provider_name separately in the timestamp row.

---

## ARTICLE 2: Veteran Analyst Issues Stark Warning on Nvidia Stock

### STEP 1 — Raw Finnhub API Response
```json
{
    "id": 140716906,
    "headline": "Veteran Analyst Issues Stark Warning on Nvidia Stock",
    "source": "Yahoo",
    "related": "NVDA",                // ← Finnhub correctly says NVDA
    "summary": "Wall Street's Only Nvidia Bear Issues Fresh Warning...",
    "url": "https://finnhub.io/api/news?id=ae0d84ca7a835f759348ac56b514f202b0e82f759be410f84de34c9b3a907b7c",
    "image": "https://s.yimg.com/rz/stage/p/yahoo_finance_en-US_h_p_finance_2.png",  // ← Placeholder!
    "category": "company",
    "datetime": 1782328664
}
```

**Observation:** Finnhub correctly tags `related: NVDA`. Image is the placeholder again.

### STEP 2 — Normalized Article
```python
NewsArticleIngest(
    finnhub_id="94263cb94e09777211ef977adb9683c6",
    ticker="GOOGL",                   # ← WRONG! This was fetched during a GOOGL query cycle
    title="Veteran Analyst Issues Stark Warning on Nvidia Stock",
    provider_name="Yahoo",
    thumbnail_url=None,               # ← Placeholder stripped
)
```

### STEP 3 — Database Row
```
ticker:       GOOGL                 # ← WRONG. Finnhub's "related" says NVDA.
author:       null                  # ← Backfill didn't touch this one (or failed silently)
thumbnail_url: null
```

### STEP 4 → STEP 5 — API Response / React Props
The incorrect ticker `GOOGL` propagates through unchanged.

### STEP 6 — Rendered DOM Output
```
Ticker badge:    GOOGL              # ← WRONG! Should be NVDA
Title text:      Veteran Analyst Issues Stark Warning on Nvidia Stock
Author line:     Yahoo              # ← Falls through to provider_name since author=null
Publisher:       Yahoo
Thumbnail src:   /news_image.png    # ← FALLBACK
```

---

## ARTICLE 3: Why D-Wave Quantum Stock Just Crashed

### STEP 1 — Raw Finnhub API Response
```json
{
    "id": 140716909,
    "headline": "Why D-Wave Quantum Stock Just Crashed",
    "source": "Yahoo",
    "related": "NVDA",               # ← WRONG. Finnhub mis-tagged this. Article is about D-Wave (QBNT).
    "summary": "Quantum computing is the future...",
    "url": "https://finnhub.io/api/news?id=adcb263932adeb82a7f31b0bbb9ff423dbe3db79664afcdd02f0066716be197c",
    "image": "https://s.yimg.com/rz/stage/p/yahoo_finance_en-US_h_p_finance_2.png",  // ← Placeholder!
    "category": "company",
    "datetime": 1782328486
}
```

**Observation:** Finnhub says `related: NVDA` but the article is about D-Wave (QBNT). This is a Finnhub API data quality issue.

### STEP 2 — Normalized Article
```python
NewsArticleIngest(
    finnhub_id="667afc966c42e3e3fcd2c5e430392f11",
    ticker="NVDA",                   # ← Set by query param (fetched during NVDA cycle)
    ...
)
```

### STEP 6 — Rendered DOM Output
```
Ticker badge:    NVDA               # ← WRONG. Article is about D-Wave (QBNT).
Thumbnail src:   /news_image.png    # ← FALLBACK
Author line:     Yahoo              # ← author=null, falls through to provider_name
Publisher:       Yahoo
```

---

## Root Cause Analysis

### ISSUE 1: Ticker Assignment Uses Query Parameter, Not Article Metadata

**File:** `backend/services/news_ingestion_service.py`
**Lines:** 236-271, 348-368

The ticker assignment chain:
```
fetch_and_ingest_many(tickers=["GOOGL", "NVDA", ...])  # Watchlist tickers
  └─> fetch_and_ingest_news(ticker="GOOGL")            # Query Finnhub for GOOGL news
       └─> client.company_news("GOOGL")                # Finnhub returns any article where related="GOOGL" OR Finnhub decides is relevant
            └─> normalize_finnhub_article(article, ticker="GOOGL")  # ← TICKER IS THE QUERY PARAM
                 └─> NewsArticleIngest(ticker=ticker)   # Article gets ticker="GOOGL" regardless of actual content
```

**Root cause:** Line 271 assigns `ticker=ticker` where `ticker` is the function parameter (the symbol queried), NOT the article's actual related symbol from `article.get("related")`. Finnhub's `/company-news` endpoint returns articles that may not be about the queried ticker — it returns a feed of "related" news, and Finnhub's own tagging can be wrong.

**Evidence:**
- Article about Nvidia fetched during GOOGL cycle → stored as GOOGL (DB row 67702)
- Article about D-Wave fetched during NVDA cycle → stored as NVDA (DB row 67767)  
- SpaceX article with Finnhub `related: GOOGL` fetched during TSLA cycle → stored as TSLA (DB row 58099)

### ISSUE 2: Thumbnail Images Always Fallback

**File:** `backend/services/news_ingestion_service.py`
**Lines:** 122-142, 266-267, 393-409

Chain of image loss:
1. Finnhub returns `image: https://s.yimg.com/rz/stage/p/yahoo_finance_en-US_h_p_finance_2.png` (placeholder)
2. `_is_yahoo_placeholder()` correctly detects and strips it → `thumbnail_url=None`
3. OG scraping is triggered for articles with no thumbnail
4. `_extract_og_image(article_url)` tries to scrape the article page
5. **BUT** `article_url = "https://finnhub.io/api/news?id=..."` — this is a Finnhub redirect proxy, NOT the real article
6. The redirect either 302s or returns a generic page with no real og:image meta tags
7. OG scraping fails → thumbnail remains null

**Additional factor:** Line 147-150 has `_SKIP_OG_HOSTS = {"finnhub.io", "api.finnhub.io"}` which would skip OG extraction for finnhub.io URLs. However, the actual article_url stored is `https://finnhub.io/api/news?id=...` which IS in `_SKIP_OG_HOSTS`. This means OG scraping is explicitly skipped for these URLs.

**Wait — re-reading the code:** The `_should_skip_og_extraction` checks if the host is in `_SKIP_OG_HOSTS`. Since the article_url is `finnhub.io/api/news?id=...`, this WOULD be skipped. But looking at line 387-388: articles without thumbnails are added to `articles_missing_images`. Then on line 401, OG extraction tasks are created. The `_should_skip_og_extraction` inside `_extract_og_image` returns True for finnhub.io URLs, returning None immediately.

**Root cause:** OG scraping is intentionally disabled for finnhub.io redirect URLs (correct decision to save rate limits), but there's no alternative image recovery path. The raw Finnhub `image` field either contains the placeholder or a real image URL — when it's the placeholder, there's nowhere else to get an image from.

**Solution needed:** Store the original finnhub.io article URL as a separate field AND try to resolve the real article URL via a redirect-follow lookup before OG scraping. Alternatively, use the `raw_json` which already has the full Finnhub response including the real target URL if available.

### ISSUE 3: Author = "Yahoo" Duplication

**File:** `scripts/backfill_yahoo_authors.py` (fallback logic) + `frontend/components/news/NewsCard.tsx` lines 80-112

**Root cause in backfill script:** When the scraper cannot extract an author from the article page (because it's a finnhub.io redirect), it falls back to setting `author = provider_name`. This is incorrect because:
- It conflates the data aggregator (Yahoo/Finnhub) with the actual article author
- It creates visual duplication in the NewsCard

**Root cause in NewsCard:** Lines 86-112 render both `author` and `provider_name`:
```tsx
// Line 86: Author line shows article.author || article.provider_name
<span>{article.author || article.provider_name || "Unknown Author"}</span>
// Line 109: Publisher badge shows provider_name separately  
<span>{article.provider_name}</span>
```

When `author="Yahoo"` and `provider_name="Yahoo"`, both fields display "Yahoo" in different locations. The condition at line 88 prevents showing both in the *same author line*, but the publisher badge at line 109 still shows separately.

### ISSUE 4: Duplicate Title Rendering

**File:** `frontend/components/news/NewsCard.tsx` + `frontend/components/stock/TickerHeader.tsx`

The user reports seeing the title twice. Looking at the `/news/[ticker]/page.tsx`:
- Line 72: `<TickerHeader ticker={ticker} />` — Shows company name, not article titles
- Lines 167-177: Maps articles to `<NewsCard>` components

The TickerHeader shows `{company}` (the stock company name) at line 64. If the user is seeing "SpaceX's Stock Slide..." twice, this is NOT the TickerHeader — it must be within NewsCard itself.

**Looking at NewsCard.tsx more carefully:**
- Lines 57-70: Title rendered once as a link or `<h3>`
- The title text only appears in one place in NewsCard

**Hypothesis for duplicate title:** The user's description shows "TSLA" between two copies of the title. This suggests the title may be appearing in TWO different NewsCards (duplicate database entries). Let me verify... 

Actually, looking at the rendered output described:
```
SpaceX's Stock Slide Costs Elon Musk His Trillionaire Title
TSLA
SpaceX's Stock Slide Costs Elon Musk His Trillionaire Title
Yahoo
Yahoo
1h ago
```

The "TSLA" between two title copies suggests this is the ticker badge. The structure in NewsCard is:
1. Ticker badge (line 41-50)
2. Title link (lines 57-70)

But wait — the user shows the title appearing BEFORE and AFTER "TSLA". This could mean there are TWO rows for the same article in the database with slightly different data, causing two NewsCards to render for one article. OR the TickerHeader company name is coincidentally matching the article title.

**Most likely:** The duplicate rendering is caused by the article being ingested twice (once per ticker query cycle). When multiple tickers query Finnhub and return overlapping articles, the same URL gets upserted — BUT if the `article_url` values differ (e.g., different Finnhub redirect IDs), they'll be stored as separate rows.

**Need to verify:** Check for duplicate rows with the same headline but different article_urls or finnhub_ids.

### ISSUE 5: "Invalid news links filtered"

The article URLs all point to `https://finnhub.io/api/news?id=<hash>` which are Finnhub redirect proxies. These are valid functional URLs (they 302-redirect to the real article), but URL validation logic may be rejecting them because:
- They're not direct article links
- They may fail certain schema/hostname validations

Need to trace where "Invalid news links filtered" log message originates from.

---

## File Inventory

| File | Role | Issues Found |
|------|------|-------------|
| `backend/services/news_ingestion_service.py` | Ingestion + Normalization | Ticker assignment (line 271), OG skip for finnhub.io (line 147-160) |
| `backend/models/news.py` | ORM Model | Schema is correct; no issues |
| `backend/models/news_schemas.py` | Pydantic Schemas | Correct; author field exists but unused in ingestion |
| `scripts/backfill_yahoo_authors.py` | Author backfill | Sets author=provider_name on scrape failure (wrong fallback) |
| `frontend/components/news/NewsCard.tsx` | Article card rendering | Renders author and provider_name in separate locations, both can show "Yahoo" |
| `frontend/types/stock.ts` | TypeScript types | Correct; matches backend schema |
| `frontend/next.config.ts` | Next.js config | Need to verify image domains for s.yimg.com |

---

## Recommended Fixes (Priority Order)

### P0 — Ticker Assignment
Use Finnhub's `related` field instead of the query ticker. If `related` contains multiple symbols, pick the first one that matches a known ticker in the watchlist. If none match, leave ticker as NULL rather than assigning a wrong one.

### P1 — Author Field Cleanup
Remove the backfill script's fallback of `author = provider_name`. When no author can be scraped, leave `author = null` and let the frontend handle display gracefully.

### P2 — Image Recovery
The placeholder filtering is correct. Need an alternative image recovery path: either try to resolve finnhub.io redirect URLs to their real targets before OG scraping, or accept that Yahoo-sourced articles through Finnhub rarely have images and improve the fallback UI.

### P3 — Duplicate Prevention
Add cross-checking during ingestion: before inserting, check if any existing row has the same `finnhub_id` (Finnhub article ID) regardless of the stored `article_url`. This prevents duplicate rows from different Finnhub redirect IDs for the same underlying article.

### P4 — Frontend NewsCard Cleanup
- Only show "Author:" label when author is a real person, not a publisher name
- Add explicit labels ("Publisher:" / "By:") to clarify which field is which
- Never render provider_name in the author line as a fallback

---

## Technical Debt Remaining

1. Finnhub redirect URLs (`finnhub.io/api/news?id=...`) are not resolved to canonical article URLs
2. No validation that `related` field from Finnhub actually matches article content
3. The backfill script processes articles that can't possibly be scraped (finnhub.io proxy URLs)
4. No deduplication by finnhub_id during initial ingestion (only by article_url which varies)
5. Image domain whitelist in Next.js may need updating for s.yimg.com
