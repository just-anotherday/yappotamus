# YapVibes Architecture Migration — Implementation Status

## Overview

This document tracks the migration from a request-time AI processing model to an event-driven, cached intelligence pipeline.

---

## Completed Phases

### Phase 1: Database Schema — ✅ COMPLETE

**Models Created:**
- `AICompanyReport` — Per-company AI intelligence reports (sentiment, confidence, full JSON)
- `AISectorReport` — Aggregated sector intelligence from company reports
- `AIMarketReport` — Daily market-wide intelligence summary
- `AIJobQueue` — Background job queue with priority scheduling and retry logic

**File:** `backend/models/ai_reports.py`, `backend/models/ai_job_queue.py`

### Phase 2: Alembic Migrations — ✅ COMPLETE

**Migration:** `2026_06_28_add_unique_constraints_and_indexes.py`

- Added unique constraints on `assets(ticker)`
- Created all AI report tables
- Created AI job queue table
- Added proper indexes for query performance

### Phase 3: Asset Model — ✅ COMPLETE

- Normalized asset entity with ticker mapping
- Proper foreign keys and indexes
- Unique ticker constraint per asset

### Phase 4: AI Worker Service — ✅ COMPLETE

**File:** `backend/services/ai_worker.py`

**Capabilities:**
- Background polling loop (configurable interval + concurrency)
- Job claiming with atomic status transitions
- Three job handlers:
  - `_handle_company_report`: Fetches articles, calls Ollama, persists report, auto-triggers sector report
  - `_handle_sector_report`: Aggregates company reports into sector intelligence
  - `_handle_market_report`: Aggregates all data into daily market summary
- Exponential backoff retry logic (max 3 retries)
- Deduplication: prevents duplicate pending jobs for same target
- Semaphore-based concurrency control

### Phase 5: Event Pipeline — ✅ COMPLETE

**Data Flow:**
```
News arrives (every 15 min scheduler)
  ↓
Articles stored with ticker extracted
  ↓
Company report job enqueued (if not already pending)
  ↓
AI Worker processes company report (Ollama LLM)
  ↓
Report persisted to AICompanyReport
  ↓
Sector report auto-triggered (throttled: max once per hour per sector)
  ↓
Daily market report scheduler (runs once per day)
```

**Key Design Decisions:**
- Reports are NEVER regenerated unless new data arrives or manual trigger
- Sector reports throttled to prevent cascading regeneration
- Market reports run on a daily schedule, not triggered per-article

### Phase 6: API Endpoints — ✅ COMPLETE

**File:** `backend/routers/analysis_reports.py`

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/analysis/reports/company/{ticker}` | GET | Cached company intelligence report |
| `/api/analysis/reports/company/{ticker}/regenerate` | POST | Manually trigger company report |
| `/api/analysis/reports/sector/all` | GET | All sector reports |
| `/api/analysis/reports/sector/{sector}` | GET | Single sector report |
| `/api/analysis/reports/sector/{sector}/regenerate` | POST | Manually trigger sector report |
| `/api/analysis/reports/market/latest` | GET | Latest daily market report |
| `/api/analysis/reports/market/regenerate` | POST | Manually trigger market report |
| `/api/analysis/reports/queue/status` | GET | Job queue status |

### Phase 7: Application Lifecycle — ✅ COMPLETE

**File:** `backend/main.py`

- AI Worker starts as background task on startup
- Daily market report scheduler runs independently
- Proper shutdown sequence stops all workers
- All services wrapped in try/except for fault tolerance

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                        YapVibes Backend                         │
├─────────────┬──────────────┬───────────────┬───────────────────┤
│  Scheduler  │   Collector  │    AI Worker  │    API Router     │
│             │              │               │                   │
│ News (15m)  │ Finnhub API  │ Company(2)    │ GET /company      │
│ Market(daily│              │ Sector(2)     │ GET /sector       │
│ Asset sync  │ Ticker extract│ Market(2)    │ GET /market       │
│             │              │               │ POST /regenerate  │
└──────┬──────┴──────┬───────┴───────┬───────┴────────┬──────────┘
       │             │              │                 │
       ↓             ↓              ↓                 ↓
┌─────────────────────────────────────────────────────────────────┐
│                        PostgreSQL                               │
├─────────────────────────────────────────────────────────────────┤
│ assets ────── Asset entities with normalized info               │
│ asset_tickers ── Ticker mapping (primary + aliases)             │
│ news_articles ── Ingested articles with ticker                  │
│ ai_company_reports ── Cached company intelligence              │
│ ai_sector_reports  ── Aggregated sector intelligence            │
│ ai_market_reports  ── Daily market summary                      │
│ ai_job_queue ────── Background job queue                        │
└─────────────────────────────────────────────────────────────────┘
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `AI_WORKER_POLL_INTERVAL_S` | 10 | How often AI worker polls for jobs |
| `AI_WORKER_MAX_CONCURRENT` | 2 | Max parallel AI job executions |
| `OLLAMA_BASE_URL` | http://host.docker.internal:11434 | Ollama API endpoint |
| `OLLAMA_MODEL` | llama3 | Model name for analysis |

---

## Remaining Work (Future Enhancements)

### Frontend Integration (Partial)
- [ ] Sector reports display in frontend
- [ ] Market report dashboard view
- [ ] Queue status monitoring UI
- [ ] Real-time report freshness indicators

### Advanced Features
- [ ] Redis-based job queue (replace DB polling)
- [ ] Embedding generation for semantic search
- [ ] Materialized views for dashboard queries
- [ ] Connection pooling optimization
- [ ] WebSocket push for report completion notifications
- [ ] Rate limiting for Finnhub API calls

### Monitoring
- [ ] Job completion metrics endpoint
- [ ] AI processing latency tracking
- [ ] Error rate dashboards
- [ ] Report freshness SLA monitoring

---

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| Ollama unreachable | Reports not generated | Deferred status, retry with backoff |
| DB lock contention during claims | Jobs missed | Atomic UPDATE...RETURNING pattern |
| Large report payloads | Memory pressure | Consider compression for JSON columns |
| Cascade sector regeneration | Unnecessary work | Throttled to once/hour per sector |

---

## Migration Checklist

- [x] Create AI report models
- [x] Create AI job queue model
- [x] Run Alembic migrations
- [x] Implement AI Worker with all three handlers
- [x] Add sector auto-trigger after company reports
- [x] Add daily market report scheduler
- [x] Create all API endpoints
- [x] Wire up application lifecycle
- [ ] Frontend sector/market dashboard views
- [ ] Redis queue upgrade (optional)
- [ ] Monitoring and metrics
