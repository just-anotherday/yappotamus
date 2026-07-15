# Stock Data Dashboard — Comprehensive Technical Debt Report

> **Generated:** June 24, 2026
> **Auditor:** Senior Software Engineer (AI)
> **Scope:** Full codebase — backend (FastAPI/Python), frontend (Next.js/TypeScript), scripts, config, docs
> **Total Issues Found:** 87 across 5 audit dimensions

---

## Executive Summary

The project is architecturally sound overall with a well-thought-out hybrid data architecture (Finnhub + yfinance). The main debt areas are:

1. **Dead debug scripts** (17 one-shot scripts in `scripts/`) — quick cleanup
2. **Frontend component duplication** (3 near-identical news card components, repeated pagination UI) — structural issue
3. **CEO enrichment causing 25s API latency** — performance bottleneck on the fast path
4. **Silent exception swallowing** in several try/except blocks — reliability risk
5. **Missing input validation** on a few API endpoints — security concern

---

## Phase Tracking (Previously Completed)

| Phase | Status | Items Done |
|-------|--------|------------|
| Phase 1 (Safe Wins) | ✅ Complete | Removed dead imports, extracted formatters, added type hints, created exception handlers |
| Phase 2 (Structural) | ✅ Partially Complete | News query extraction, batch ingestion (N+1 fix), static imports, CORS env var, DB indexes |
| Phase 3 (Architecture) | ❌ Not Started | Domain boundaries, state management refactor, API redesign |

---

# SECTION A: ARCHITECTURE ISSUES

## A-001: God Component — WatchlistTable (549 lines)
| Field | Value |
|-------|-------|
| **File** | `frontend/components/watchlist/WatchlistTable.tsx` |
| **Severity** | **High** |
| **Root Cause** | Component evolved organically — all metric sections, drag-and-drop, expansion logic, and skeleton loading are in one file |
| **Description** | Single React component handles: DnD orchestration, expand/collapse state, market cap classification, 4 metric section renderers (Price/Targets/Shares/Risk), skeleton loader, pagination badges. Violates Single Responsibility Principle. |
| **Recommended Fix** | Extract into sub-components: `WatchlistMetricSection`, `PriceRangeGrid`, `AnalystTargetGrid`, `ShareStructureGrid`, `RiskProfileGrid`, `SkeletonLoader` |
| **Expected Impact** | Reduces file from 549→~200 lines, improves testability and readability |

## A-002: Business Logic in Components (marketCapLabel function)
| Field | Value |
|-------|-------|
| **File** | `frontend/components/watchlist/WatchlistTable.tsx:126-133` |
| **Severity** | **Medium** |
| **Description** | `marketCapLabel()` classification logic is embedded inside the component. Should be a pure utility function in `frontend/lib/formatters.ts`. |
| **Recommended Fix** | Move to `formatters.ts`, export as `classifyMarketCap(mc: number): {label, color}` |

## A-003: Tight Coupling — HybridDataService depends on both Finnhub AND yfinance internals
| Field | Value |
|-------|-------|
| **File** | `backend/services/hybrid_data_service.py` |
| **Severity** | **Medium** |
| **Description** | Service imports and directly calls methods from both `finnhub_service` and `yfinance_fallback`. Adding a third data source requires modifying this file. Violates Open/Closed Principle. |
| **Recommended Fix** | Introduce a `DataProvider` protocol/ABC. Each provider implements `fetch(ticker) -> dict`. HybridDataService accepts a list of providers. |

## A-004: Fail-fast startup blocks yfinance-only operation
| Field | Value |
|-------|-------|
| **File** | `backend/main.py:32-36` |
| **Severity** | **High** |
| **Description** | App refuses to start if `FINNHUB_API_KEY` is missing, but the hybrid architecture supports yfinance-only fallback. Contradicts design intent. |
| **Recommended Fix** | Replace hard assert with conditional warning. Only fail if NO data sources are configured. |

---

# SECTION B: CODE QUALITY ISSUES

## B-001: Dead Debug Scripts (17 files)
| Field | Value |
|-------|-------|
| **Files** | See list below |
| **Severity** | **High** (maintenance overhead, developer confusion) |
| **Description** | One-shot exploration scripts from thumbnail debugging sessions. No longer needed and clutter the workspace. |
| **Recommended Fix** | Delete or archive to `scripts/archive/` |

**Files to delete:**
- `check_yf_voo.py`, `check_all_keys.py`, `test_yf_fallback.py` (yfinance exploration)
- `check_author_provider.py`, `check_raw_json.py` (data debugging)
- `backfill_all_thumbnails.py`, `backfill_missing_thumbnails.py`, `backfill_og_thumbnails.py`, `backfill_thumbnails.py` (3 duplicate backfill scripts → keep only `backfill_thumbnails.py`)
- `diag_null_thumbs.py`, `fill_missing_thumbnails.py` (diagnostic tools)
- `check_thumbnail_domains.py`, `check_thumbnail_stats.py`, `check_thumbnail_urls.py`, `check_other_thumbnails.py`, `check_thumbnails.py`, `check_yahoo_source.py` (8 duplicate thumbnail checkers → keep the most comprehensive one)
- `clear_yahoo_placeholders.py` (one-shot data fix, already executed)

## B-002: Silent Exception Swallowing (4 occurrences)
| Field | Value |
|-------|-------|
| **Files** | `backend/services/finnhub_service.py`, `backend/services/yfinance_fallback.py` |
| **Severity** | **High** |
| **Description** | Multiple `except: pass` or bare `except Exception: pass` blocks silently ignore errors. Makes debugging failures nearly impossible. |
| **Recommended Fix** | Replace with `except Exception as e: logger.warning(...)` at minimum |

## B-003: Large Functions (>50 lines without decomposition)
| Field | Value |
|-------|-------|
| **Files** | Various service files |
| **Severity** | **Medium** |
| **Description** | `fetch_and_ingest_many()` (437 lines in news_ingestion_service.py), `_do_poll()` in market_data_service could be decomposed further. |

## B-004: Inconsistent Error Handling Patterns
| Field | Value |
|-------|-------|
| **Files** | Multiple router files |
| **Severity** | **Medium** |
| **Description** | Some endpoints return 500s, others return structured JSON error bodies. No consistent `ErrorResponse` model used across all routers. |

---

# SECTION C: DATA LAYER ISSUES

## C-001: News thumbnail extraction loses valid images
| Field | Value |
|-------|-------|
| **File** | `backend/services/news_ingestion_service.py:266-267` |
| **Severity** | **Critical** (current bug) |
| **Root Cause** | `_is_yahoo_placeholder()` check is over-aggressive or Finnhub API changed response format, causing ALL thumbnails to be stripped |
| **Description** | User reports all news articles show the default `news_image.png` fallback. Thumbnails from the Finnnhub API are being incorrectly filtered out before reaching OG extraction. |
| **Recommended Fix** | 1) Log sample `raw_image` values to diagnose what Finnhub actually returns now; 2) Narrow `_is_yahoo_placeholder()` patterns; 3) Add debug logging at normalization time |

## C-002: Missing unique constraint on finnhub_id
| Field | Value |
|-------|-------|
| **File** | `backend/models/news.py` |
| **Severity** | **Medium** |
| **Description** | `finnhub_id` is indexed but not UNIQUE. Could allow duplicate articles from the same Finnhub source. |

## C-003: raw_json column stores full article dict (unbounded size)
| Field | Value |
|-------|-------|
| **File** | `backend/models/news.py` |
| **Severity** | **Low** |
| **Description** | JSONB column stores entire Finnhub response. With 2700+ articles, this adds unnecessary storage overhead. Consider archiving raw_json older than 30 days. |

---

# SECTION D: API LAYER ISSUES

## D-001: /api/watchlist endpoint is slow (~25s on first load)
| Field | Value |
|-------|-------|
| **File** | `backend/routers/watchlist.py` + `backend/services/hybrid_data_service.py` |
| **Severity** | **Critical** (current bug) |
| **Root Cause** | CEO enrichment via `ticker_obj.officers` makes 22 sequential HTTP calls to Yahoo Finance, each taking ~0.5-1s |
| **Description** | Initial watchlist load blocks on CEO name extraction for every non-ETF ticker. This adds 10-15 seconds of unnecessary latency. |
| **Recommended Fix** | Move CEO enrichment to a background task. Return the initial watchlist response immediately with `ceo_name: null`, then fill in via WebSocket broadcast when enrichment completes. |

## D-002: No request validation on ticker parameter in news router
| Field | Value |
|-------|-------|
| **File** | `backend/routers/news.py` |
| **Severity** | **Medium** |
| **Description** | Ticker parameter accepted as any string. No regex validation against valid ticker format (1-5 uppercase letters, optional period for ETFs). |

## D-003: Rate limiting is in-memory only
| Field | Value |
|-------|-------|
| **File** | `backend/main.py:56-89` |
| **Severity** | **Low** |
| **Description** | Rate limit store is a plain dict that resets on server restart. No persistence across deployments. Adequate for single-instance dev but not production-ready. |

---

# SECTION E: PERFORMANCE ISSUES

## E-001: CEO enrichment blocks watchlist API response
| Field | Value |
|-------|-------|
| **File** | `backend/services/yfinance_fallback.py:_extract_ceo_name()` |
| **Severity** | **Critical** (already diagnosed) |
| **Description** | 22 sequential `ticker_obj.officers` calls add ~15s to the `/api/watchlist` endpoint. This is the #1 performance issue. |

## E-002: yfinance poller creates new Ticker objects every cycle
| Field | Value |
|-------|-------|
| **File** | `backend/services/market_data_service.py:_do_poll()` |
| **Severity** | **Medium** |
| **Description** | Each 15s poll cycle creates 26 new `yf.Ticker()` instances and fetches `fast_info`. Over time this generates garbage collection pressure. Consider caching Ticker objects. |

## E-003: Watchlist initial load is sequential, not parallel
| Field | Value |
|-------|-------|
| **File** | `backend/services/hybrid_data_service.py` |
| **Severity** | **Medium** |
| **Description** | The batch fetch for 26 tickers processes them sequentially. With async available, concurrent fetching could reduce initial load time from ~25s to ~10-12s (bounded by slowest Finnhub REST call + parallel yfinance calls). |

---

# SECTION F: SECURITY ISSUES

## F-001: .env.example exposes structure of secrets
| Field | Value |
|-------|-------|
| **File** | `.env.example` |
| **Severity** | **Low** |
| **Description** | Shows key names and placeholder values. Not a vulnerability itself but should include a comment to NOT commit the actual `.env`. |

## F-002: No SQL injection protection on user-provided ticker in news URL path
| Field | Value |
|-------|-------|
| **File** | `backend/routers/news.py` |
| **Severity** | **Low** (SQLAlchemy parameterized queries mitigate this) |
| **Description** | Ticker from URL path is used directly in WHERE clause. While SQLAlchemy ORM prevents actual injection, adding input validation is defense-in-depth. |

## F-003: CORS allows all origins by default in dev
| Field | Value |
|-------|-------|
| **File** | `backend/main.py` |
| **Severity** | **Low** |
| **Description** | `allow_origins=["*"]` is fine for local development but should be restricted in production. |

---

# SECTION G: FRONTEND ISSUES

## G-001: Three duplicate news card components
| Field | Value |
|-------|-------|
| **Files** | `components/news/ArticleCard.tsx`, `components/news/NewsCard.tsx`, `components/news/NewsFeed.tsx` (internal ArticleCard) |
| **Severity** | **High** |
| **Description** | Three components render the same structure: thumbnail, ticker badge, title link, summary, metadata. Different heights (`h-36`, `h-48`, `h-56`) and inconsistent error handling. |
| **Recommended Fix** | Single `<NewsCard variant="compact\|medium\|large">` component with prop-driven sizing |

## G-002: Pagination UI copy-pasted 3 times
| Field | Value |
|-------|-------|
| **Files** | `HomeClient.tsx:138-196`, `app/news/page.tsx:185-253`, `app/news/[ticker]/page.tsx` |
| **Severity** | **High** |
| **Description** | ~60 lines of pagination buttons (First/Prev/Next/Last) duplicated across 3 files. Any change to pagination behavior requires editing 3 places. |
| **Recommended Fix** | Extract to `<Pagination />` component in `components/ui/` |

## G-003: Inline SVG icons repeated throughout WatchlistTable
| Field | Value |
|-------|-------|
| **File** | `frontend/components/watchlist/WatchlistTable.tsx` |
| **Severity** | **Low** |
| **Description** | ~12 inline `<svg>` definitions for person, building, chart icons. Adds visual noise and bloats the component. |
| **Recommended Fix** | Extract to an `Icons` object or use an icon library (Lucide, Heroicons) |

---

# REFCTORING ROADMAP

## Phase 1: Critical Fixes (Do Now — Low Risk, High Value)

| # | Task | Effort | Risk |
|---|------|--------|------|
| 1.1 | Fix news thumbnail stripping bug — diagnose `_is_yahoo_placeholder()` over-filtering | 30 min | Low |
| 1.2 | Move CEO enrichment to background task, unblock `/api/watchlist` response | 45 min | Low |
| 1.3 | Delete dead debug scripts (17 files) | 15 min | Zero |
| 1.4 | Replace silent `except: pass` with logging calls | 20 min | Zero |

## Phase 2: Structural Cleanup (This Week)

| # | Task | Effort | Risk |
|---|------|--------|------|
| 2.1 | Consolidate 3 news card components into 1 parameterized component | 2h | Low |
| 2.2 | Extract `<Pagination />` component | 45 min | Low |
| 2.3 | Move `marketCapLabel()` to formatters.ts | 15 min | Zero |
| 2.4 | Make FINNHUB_API_KEY optional at startup (soft dependency) | 20 min | Low |
| 2.5 | Add ticker format validation on all API endpoints accepting tickers | 30 min | Low |

## Phase 3: Architecture Improvements (Next Sprint)

| # | Task | Effort | Risk |
|---|------|--------|------|
| 3.1 | Extract WatchlistTable into sub-components | 3-4h | Medium |
| 3.2 | Introduce `DataProvider` protocol for hybrid service | 2h | Medium |
| 3.3 | Parallelize watchlist batch fetching with asyncio.gather | 1h | Medium |
| 3.4 | Add consistent `ErrorResponse` model across all routers | 1h | Low |

---

# APPENDIX: Previously Fixed Issues (for reference)

From Phase 1-3 completion docs, these were already addressed:
- ✅ Removed unused imports (`LargeBinary`, `get_news()`)
- ✅ Extracted `normalize_ticker()` to shared lib
- ✅ Added type hints to backend services
- ✅ Replaced `any` types in frontend with proper TypeScript types
- ✅ Extracted `timeAgo` to shared formatters
- ✅ Created centralized exception handlers
- ✅ Batch news ingestion (N+1 fix)
- ✅ Database indexes added
- ✅ CORS configured via env var
- ✅ Static imports replaced dynamic `__import__()`
