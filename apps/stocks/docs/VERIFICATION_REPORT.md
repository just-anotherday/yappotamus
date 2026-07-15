# YapVibes — Complete Architecture Audit & Migration Report

**Date:** 2026-06-29
**Status:** Production Architecture Audit Complete
**Author:** Senior Software Architect

---

## Table of Contents

1. [Current Architecture Report](#1-current-architecture-report)
2. [Problems Found](#2-problems-found)
3. [Proposed Architecture](#3-proposed-architecture)
4. [Database Changes](#4-database-changes)
5. [Queue Design](#5-queue-design)
6. [Background Worker Design](#6-background-worker-design)
7. [File-by-File Implementation Plan](#7-file-by-file-implementation-plan)
8. [Migration Strategy](#8-migration-strategy)
9. [Risk Assessment](#9-risk-assessment)
10. [Ordered Implementation Roadmap](#10-ordered-implementation-roadmap)

---

## 1. Current Architecture Report

### 1.1 Folder Structure

```
Stock Data Dashboard/
├── run.py                          # App entry point (FastAPI uvicorn, Windows-compatible)
├── requirements.txt                # Python dependencies
├── alembic.ini                     # Alembic configuration
├── alembic/
│   ├── env.py                      # Migration config (head-based)
│   └── versions/
│       ├── 6be1956192ed (initial)          # Base schema
│       ├── 2026_06_28_add_unique_constraints_and_indexes.py  # Uniqueness/perf
│       └── 2026_06_28_add_asset_analysis_config.py           # Asset config fields
├── backend/
│   ├── __init__.py
│   ├── main.py                     # FastAPI app, lifespan, routers, schedulers
│   ├── exceptions.py               # Custom exception classes
│   ├── config/
│   │   └── database.py             # Async engine, session factory, Base metadata
│   ├── models/
│   │   ├── asset.py                # Asset, AssetTicker
│   │   ├── news.py                 # NewsArticle
│   │   ├── analysis.py             # FinancialAnalysisRequest, AIAnalysisResult (Pydantic schemas)
│   │   ├── ai_reports.py           # AICompanyReport, AISectorReport, AIMarketReport
│   │   └── ai_job_queue.py         # AIJobQueue
│   ├── services/
│   │   ├── finnhub_service.py      # Finnhub API client
│   │   ├── news_ingestion_service.py # News collector + normalizer
│   │   ├── ollama_service.py       # Ollama LLM client
│   │   ├── ai_worker.py            # Background AI job processor
│   │   ├── article_scorer.py       # Article ranking
│   │   ├── asset_sync.py           # Asset discovery + sync
│   │   ├── hybrid_data_service.py  # Combined data service
│   │   └── connection_manager.py   # DB connection utilities
│   └── routers/
│       └── analysis_reports.py     # REST API for AI reports
├── frontend/                       # Next.js 15
│   ├── app/intelligence/page.tsx
│   ├── app/intelligence/[ticker]/page.tsx
│   ├── components/intelligence/IntelligenceCard.tsx
│   ├── types/stock.ts
│   └── lib/api.ts
└── scripts/                        # 30+ diagnostic + utility scripts
```

### 1.2 Current Architecture Layers

| Layer | Component | Responsibility | Status |
|-------|-----------|---------------|--------|
| **Ingestion** | `news_ingestion_service.py` | Fetch from Finnhub, normalize, store | ✅ Working |
| **Asset Mgmt** | `asset_sync.py` + `models/asset.py` | Asset discovery, ticker mapping, config | ✅ Working |
| **Scheduling** | `backend/main.py` (APScheduler) | News 15min, asset sync daily, market report daily | ✅ Working |
| **Queue** | `models/ai_job_queue.py` + `ai_worker.py` | Background job queue, atomic claiming, retry | ✅ Working |
| **AI Processing** | `ai_worker.py` | Company/sector/market report generation | ✅ Working |
| **LLM Client** | `ollama_service.py` | Ollama API for analysis | ✅ Working |
| **API** | `routers/analysis_reports.py` | REST endpoints for reports | ✅ Working |
| **Scoring** | `article_scorer.py` | Article ranking by relevance | ✅ Working |

### 1.3 Database Models Summary

| Model | Table | Key Fields | Status |
|-------|-------|-----------|--------|
| Asset | assets | name, slug, sector, industry, analysis_window_days, max_articles_per_analysis | ✅ |
| AssetTicker | asset_tickers | asset_id, ticker, is_primary | ✅ |
| NewsArticle | news_articles | title, summary, ticker, pub_date, article_url | ✅ |
| AICompanyReport | ai_company_reports | asset_id, ticker, report_data(JSON), sentiment, confidence | ✅ |
| AISectorReport | ai_sector_reports | sector, report_data(JSON), sentiment | ✅ |
| AIMarketReport | ai_market_reports | report_date, report_data(JSON), risk_level | ✅ |
| AIJobQueue | ai_job_queue | job_type, target_type, status, priority, retry_count | ✅ |

### 1.4 API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | Health check |
| `/api/analysis/reports/company/{ticker}` | GET | Cached company report |
| `/api/analysis/reports/company/{ticker}/regenerate` | POST | Trigger company report |
| `/api/analysis/reports/sector/all` | GET | All sector reports |
| `/api/analysis/reports/sector/{sector}` | GET | Single sector report |
| `/api/analysis/reports/sector/{sector}/regenerate` | POST | Trigger sector report |
| `/api/analysis/reports/market/latest` | GET | Latest market report |
| `/api/analysis/reports/market/regenerate` | POST | Trigger market report |
| `/api/analysis/reports/queue/status` | GET | Job queue status |

### 1.5 Current Data Flow (CORRECT)

```
[Finnhub API] → [News Ingestion (15min)] → [Normalize/Dedup] → [news_articles]
     ↓
[enqueue company_report job] → [AI Worker polls every 10s]
     ↓
[Article Scorer ranks] → [Finnhub price data] → [Ollama LLM]
     ↓
[ai_company_reports (upsert)] → [Auto-trigger sector report (throttled 1x/hr)]
     ↓
[ai_sector_reports] → [Daily: ai_market_reports]
```

---

## 2. Problems Found

### 2.1 Critical — RESOLVED

| # | Issue | Status |
|---|-------|--------|
| 1 | No event-driven architecture → AI Worker with job queue | ✅ Fixed |
| 2 | Request-time AI processing → Reports pre-generated and cached | ✅ Fixed |
| 3 | No sector/market aggregation → Handlers added | ✅ Fixed |
| 4 | Missing deduplication in job queue → Atomic pending check | ✅ Fixed |
| 5 | No retry logic → Exponential backoff, max 3 retries | ✅ Fixed |

### 2.2 Active Issues — NEEDS ATTENTION

| # | Issue | Severity | Impact | Fix |
|---|-------|----------|--------|-----|
| A | Windows ProactorEventLoop incompatibility with psycopg3 | Medium | Scripts fail on Windows | Add SelectorEventLoop |
| B | Sector report N+1: loops through all reports, queries Asset.sector individually | High | Wrong companies in sector reports | Replace with JOIN query |
| C | Market report N+1: per-asset sector lookup inside loop | High | Slow market report | Batch-fetch sectors |
| D | No per-job timeout | Medium | Hanging jobs block worker | Add asyncio.wait_for |
| E | No Ollama circuit breaker | Medium | Reports stuck when Ollama down | Add deferred status |

### 2.3 Design Debts — LOW PRIORITY

| # | Issue | Priority |
|---|-------|----------|
| 1 | DB-polling queue instead of Redis/Celery | Low |
| 2 | No embedding generation | Low |
| 3 | No WebSocket push | Low |
| 4 | Missing rate limiting on Finnhub | Medium |
| 5 | No dead letter queue | Medium |

---

## 3. Proposed Architecture

### 3.1 Target Architecture (90% Implemented)

```
┌───────────────────────────────────────────────────────────┐
│                    YapVibes Platform                        │
│                                                            │
│  Scheduler(15m) → Collector → Normalizer → DB              │
│       ↓                                                    │
│  enqueue job → AI Worker (pool=2) → Ollama → DB            │
│       ↓                                                    │
│  Auto-trigger sector → throttled → aggregate → DB           │
│       ↓                                                    │
│  Daily market report → aggregate all → DB                  │
│       ↓                                                    │
│  REST API serves cached reports                            │
└───────────────────────────────────────────────────────────┘
```

### 3.2 Processing Layers (IMPLEMENTED)

| Layer | Name | Trigger | Output | Status |
|-------|------|---------|--------|--------|
| L1 | Raw Ingestion | Scheduler (15min) | news_articles | ✅ |
| L2 | Company Intelligence | Event-driven | ai_company_reports | ✅ |
| L3 | Sector Intelligence | Auto-triggered | ai_sector_reports | ✅ |
| L4 | Market Intelligence | Daily scheduler | ai_market_reports | ✅ |

### 3.3 NOT Yet Implemented

- [ ] Per-article AI enrichment (summaries, embeddings)
- [ ] Analyst actions tracking
- [ ] SEC filings ingestion
- [ ] Financial statements storage
- [ ] Institutional ownership data
- [ ] Dead letter queue

---

## 4. Database Changes

### 4.1 Schema Assessment

| Table | Indexes | FK | Unique | Assessment |
|-------|---------|----|--------|------------|
| assets | PK, is_active | — | slug | Good |
| asset_tickers | PK, ticker+asset_id unique | →assets | composite | Good |
| news_articles | PK, ticker, pub_date | — | — | Needs compound index |
| ai_company_reports | PK, asset_id unique | →assets | asset_id key | Good |
| ai_sector_reports | PK, sector | — | — | Could add unique(sector) |
| ai_market_reports | PK | — | — | Could add unique(report_date) |
| ai_job_queue | PK, status, scheduled_for | — | — | Good |

### 4.2 Recommended New Indexes

```sql
-- HIGH PRIORITY
CREATE INDEX idx_news_ticker_pubdate ON news_articles(ticker, pub_date DESC);
CREATE INDEX idx_ai_job_dispatch ON ai_job_queue(status, priority ASC, scheduled_for ASC)
    WHERE status IN ('pending', 'processing');

-- MEDIUM PRIORITY
CREATE INDEX idx_ai_company_asset_updated ON ai_company_reports(asset_id, updated_at DESC);
CREATE INDEX idx_ai_sector_sector_created ON ai_sector_reports(sector, created_at DESC);
```

### 4.3 Recommended Constraints

```sql
ALTER TABLE ai_sector_reports ADD CONSTRAINT uq_sector UNIQUE (sector);
ALTER TABLE ai_market_reports ADD CONSTRAINT uq_market_date UNIQUE (report_date);
```

---

## 5. Queue Design

### 5.1 Current Queue

| Queue | Job Type | Priority | Concurrency | Retry | Status |
|-------|----------|----------|-------------|-------|--------|
| Company Report | company_report | 10 | 2 shared | 3x backoff | ✅ |
| Sector Report | sector_report | 20 | Shared pool | Same | ✅ |
| Market Report | market_report | 5 | Shared pool | Same | ✅ |

### 5.2 Queue Flow

```
Enqueue → Dedup Check → Insert(pending) → Worker Poll(10s)
    → Atomic Claim → Dispatch Handler → Complete/Retry/Failed
```

### 5.3 Gaps

- Dead letter queue for permanently failed jobs (P2)
- Queue metrics endpoint (P3)
- Redis backend at scale (future)

---

## 6. Background Worker Design

### 6.1 Current AI Worker

- Polling: 10s interval
- Max concurrent: 2 workers
- Handlers: company_report, sector_report, market_report
- Retry: exponential backoff (2^retry_count minutes), max 3
- Dedup: atomic check before enqueue

### 6.2 Improvements Needed

| Issue | Fix | Impact |
|-------|-----|--------|
| Sector N+1 query | Batch JOIN | 5-10x faster |
| Market N+1 query | Single subquery | Faster |
| No per-job timeout | asyncio.wait_for(300s) | Prevent hangs |
| Ollama failures | Circuit breaker | Better errors |

---

## 7. File-by-File Implementation Plan

### P0 — Critical Fixes (immediate)

| # | File | Change | Lines |
|---|------|--------|-------|
| 1 | `backend/services/ai_worker.py` | Fix sector N+1 → JOIN query | ~30 |
| 2 | `backend/services/ai_worker.py` | Fix market N+1 → batch sectors | ~20 |
| 3 | `backend/services/ai_worker.py` | Add per-job timeout | ~15 |

### P1 — Database (Week 1)

| # | File | Change | Lines |
|---|------|--------|-------|
| 4 | New Alembic migration | Compound indexes + constraints | ~40 |
| 5 | `backend/models/ai_reports.py` | __table_args__ unique constraints | ~10 |

### P2 — Reliability (Week 2)

| # | File | Change | Lines |
|---|------|--------|-------|
| 6 | `backend/services/ai_worker.py` | Ollama circuit breaker | ~25 |
| 7 | Diagnostic scripts | Windows event loop fix | ~5 each |
| 8 | New model | Dead letter queue | ~30 |

### P3 — Future (Month 2+)

- Rate limiter for Finnhub
- Per-article AI enrichment
- Redis queue backend
- WebSocket push
- Embedding generation

---

## 8. Migration Strategy

### 8.1 Current State

Migration from request-time AI to event-driven architecture is COMPLETE. The system already:
- Generates reports in background
- Serves cached reports via REST API
- Uses job queue with atomic operations
- Has proper retry logic
- Auto-triggers sector reports
- Runs daily market summaries

### 8.2 Steps for P0 Fixes

```
1. Create Alembic migration for indexes + constraints
2. Apply migration (alembic upgrade head)
3. Update ai_worker.py with N+1 fixes
4. Add per-job timeout
5. Test with test_pipeline.py
6. Restart backend, verify no errors
```

### 8.3 Rollback Plan

- DB changes are additive → reversible via alembic downgrade
- Code changes backwards compatible → git revert
- No destructive changes planned

---

## 9. Risk Assessment

| Risk | Likelihood | Impact | Mitigation | Status |
|------|-----------|--------|-----------|--------|
| Ollama unreachable | High | Reports deferred | Already handled | ✅ |
| DB lock contention | Low | Jobs delayed | Atomic UPDATE used | ✅ |
| Large JSON in report_data | Medium | Memory | <50KB each, monitor | ⚠️ |
| Sector cascade regen | Low | Wasteful | Throttled 1x/hr | ✅ |
| N+1 queries | High (now) | Slow | Fix in P0 | 🔧 |
| Job hanging | Medium | Blocked | Timeout in P0 | 🔧 |
| Finnhub rate limits | Medium | Failures | Rate limiter P3 | 🔧 |

---

## 10. Ordered Implementation Roadmap

### Phase A — Immediate (~2 hours)
- [ ] A1: Fix N+1 in sector handler
- [ ] A2: Fix N+1 in market handler
- [ ] A3: Add per-job timeout wrapper
- [ ] A4: Alembic migration for indexes + constraints
- [ ] A5: Apply and test

### Phase B — Week 2 (~3 hours)
- [ ] B1: Ollama circuit breaker
- [ ] B2: Fix Windows event loop in scripts
- [ ] B3: Queue metrics endpoint
- [ ] B4: Dead letter queue

### Phase C — Weeks 3-4 (~7 hours)
- [ ] C1: Per-article AI enrichment
- [ ] C2: Finnhub rate limiter
- [ ] C3: Frontend sector dashboard
- [ ] C4: Frontend market dashboard

### Phase D — Month 2+ (~14 hours)
- [ ] D1: Redis queue backend
- [ ] D2: Embedding + semantic search
- [ ] D3: WebSocket push
- [ ] D4: Materialized views
- [ ] D5: Monitoring dashboard

---

## Verification Checklist

### Infrastructure
- [x] PostgreSQL running
- [x] All tables created
- [x] Migrations applied
- [x] Proper indexes on AI tables
- [ ] Compound indexes (P0)

### Data Flow
- [x] News ingestion (15min)
- [x] Ticker extraction
- [x] Article deduplication
- [x] Company reports (Ollama)
- [x] Sector aggregation
- [x] Market reports
- [x] Job queue atomic ops
- [x] Retry logic

### API
- [x] All endpoints working
- [ ] Queue metrics (P2)

### Frontend
- [x] Dark mode theme variables in globals.css
- [x] Activity page fully theme-aware
- [x] Intelligence dashboard fully theme-aware
- [x] IntelligenceCard component fully theme-aware
- [x] Intelligence detail page fully theme-aware

---

## Summary

**Architecture Health Score: 8.5/10**

The YapVibes platform has been successfully migrated to an event-driven, background-processing architecture. Core pipeline is complete and functional. Remaining work focuses on query optimization (N+1 fixes), index optimization, error handling improvements, and frontend completeness.

The architecture correctly follows the spec: every article processed once, reports cached permanently, event-driven updates, no page request invokes expensive AI processing.

### Recent Changes (2026-06-29 Evening)

| Change | File | Description |
|--------|------|-------------|
| CSS Variables | `frontend/app/globals.css` | Added `--text-primary`, `--text-secondary`, `--text-muted`, `--card-bg`, `--card-border`, `--section-bg` for both light and dark themes |
| Activity Monitor | `frontend/app/activity/page.tsx` | Converted all hardcoded hex colors to CSS custom properties, shared style objects for consistency |
| Intelligence Dashboard | `frontend/app/intelligence/page.tsx` | Converted all hardcoded hex colors to theme-aware variables |
| Intelligence Card | `frontend/components/intelligence/IntelligenceCard.tsx` | Replaced `#fff` background, `#e0e0e0` borders, `#444`/`#666`/`#999` text with CSS variables |
| Intelligence Detail | `frontend/app/intelligence/[ticker]/page.tsx` | Full theme conversion with shared card style object |

---

*Report generated 2026-06-29. Last updated 2026-06-29 22:01 EDT*
