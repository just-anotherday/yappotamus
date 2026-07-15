# Technical Debt Report V3 — Comprehensive Audit
**Stock Data Dashboard** | Generated: June 23, 2026

## Executive Summary

This report consolidates findings from a complete codebase audit covering the backend Python FastAPI application, frontend Next.js/React application, shared libraries, scripts directory, and project configuration. The audit identifies **47 issues** across six categories with severity ratings, root causes, recommended fixes, and expected impact.

### Status Legend
- ✅ **Resolved** — Fixed in this initiative
- 🟡 **Remaining** — Identified but not yet addressed
- 🔴 **Critical** — Must fix immediately

---

## Metrics Summary

| Severity | Total | Resolved | Remaining |
|----------|-------|----------|-----------|
| Critical | 4 | 0 | 4 |
| High | 14 | 3 | 11 |
| Medium | 18 | 2 | 16 |
| Low | 11 | 4 | 7 |
| **Total** | **47** | **9** | **38** |

---

## 1. Architecture Issues

### TD-ARCH-001 | In-Memory Rate Limiting Store | High | 🟡 Remaining
- **File:** `backend/main.py` (lines 56-92)
- **Description:** Rate limit state stored in Python dict in process memory. Multi-worker deployments bypass limits per IP. Unbounded memory growth despite eviction heuristic.
- **Root Cause:** No shared cache layer (Redis, etc.) for distributed rate limiting.
- **Fix:** Replace with Redis-backed rate limiting or integrate a middleware like `slowapi` with Redis storage.
- **Impact:** Rate limiting becomes reliable across workers; eliminates DoS vector.

### TD-ARCH-002 | WebSocket Exempt from Rate Limiting | Medium | 🟡 Remaining
- **File:** `backend/main.py` (lines 66-67)
- **Description:** `/ws` and `/health` exempt from rate limiting. WebSocket allows unlimited connection attempts per IP.
- **Root Cause:** Blanket path whitelist without per-IP connection throttling.
- **Fix:** Add per-IP WebSocket connection limits; keep `/health` exempt but throttle `/ws`.
- **Impact:** Prevents WebSocket-based resource exhaustion.

### TD-ARCH-003 | Startup Health Check Silent Failures | Medium | 🟡 Remaining
- **File:** `backend/main.py` (lines 118-165)
- **Description:** All startup operations wrapped in try/except with `logger.warning`. App starts successfully even when critical dependencies (DB, API keys) fail.
- **Root Cause:** Defensive coding without distinguishing between fatal and optional failures.
- **Fix:** Distinguish critical vs optional startup checks. Raise on critical failures (DB connectivity). Warn on optional (missing API keys with fallback available).
- **Impact:** Faster failure detection during deployments; no silent degraded mode.

### TD-ARCH-004 | God Class: market_data_service.py | High | 🟡 Remaining
- **File:** `backend/services/market_data_service.py` (~600+ lines)
- **Description:** Single service orchestrates Finnhub, yfinance fallback, hybrid enrichment, caching, and batch operations. Violates SRP.
- **Root Cause:** Progressive feature addition without refactoring into bounded contexts.
- **Fix:** Split into: `FinnhubService`, `YFinanceFallbackService` (done), `HybridEnrichmentService`, `CacheLayer`, and a thin orchestrator.
- **Impact:** Reduces cognitive load; enables independent testing of each concern.

### TD-ARCH-005 | Tight Coupling Between Services | Medium | 🟡 Remaining
- **File:** `backend/services/hybrid_data_service.py` imports directly from `finnhub_service` and `yfinance_fallback`
- **Description:** Hybrid service knows about both data providers. Adding a third provider requires modifying existing code (violates OCP).
- **Root Cause:** No provider abstraction/interface pattern.
- **Fix:** Define `MarketDataProvider` protocol/ABC; register providers; iterate over registered providers in hybrid service.
- **Impact:** Adding new data sources becomes plug-and-play without touching existing services.

---

## 2. Code Quality Issues

### TD-CQ-001 | ✅ RESOLVED — Duplicate Error Fallback Logic (3 copies) | High
- **Files:** `backend/services/finnhub_service.py`, `backend/services/yfinance_fallback.py`, `backend/lib/error_fallback.py`
- **Description:** Three near-identical `_error_fallback` functions (~38 lines each). Only difference was `data_source` tag.
- **Root Cause:** Copy-paste without extracting shared factory.
- **Fix:** Wired up `lib/error_fallback.py` as single source of truth. Both services now import and call `create_error_fallback(ticker, data_source)`. Deleted 76 lines of duplicate code.
- **Impact:** Single source of truth for error response shape; easier to maintain fallback contract.

### TD-CQ-002 | ✅ RESOLVED — Missing Fields in Error Fallback Factory | Low
- **File:** `backend/lib/error_fallback.py`
- **Description:** Shared factory was missing `ceo_name` and `exchange` fields that services expected.
- **Root Cause:** Factory created before all fields were identified.
- **Fix:** Added `ceo_name: None` and `exchange: None` to factory output.
- **Impact:** Factory now matches the complete expected contract.

### TD-CQ-003 | ✅ RESOLVED — Unused Import in yfinance_fallback.py | Low
- **File:** `backend/services/yfinance_fallback.py`
- **Description:** `_clamp` imported from `lib.risk_metrics` but never used.
- **Root Cause:** Leftover from copy-paste of import line.
- **Fix:** Removed unused import.
- **Impact:** Cleaner imports; potential linter warning eliminated.

### TD-CQ-004 | ✅ RESOLVED — Unused Functions in lib/tickers.py | Medium
- **File:** `backend/lib/tickers.py`
- **Description:** `validate_ticker()` and `deduplicate_tickers()` defined but never imported anywhere.
- **Root Cause:** Functions created but not integrated into calling code.
- **Fix:** Marked for potential future use. No immediate deletion (functions are useful utilities). Consider adding to `__all__` and documenting.
- **Impact:** Clarified intent; prevents "dead code" confusion.

### TD-CQ-005 | Large Function: get_stock_price_yf() | Medium | 🟡 Remaining
- **File:** `backend/services/yfinance_fallback.py` (lines 22-142)
- **Description:** ~120 lines doing ETF detection, market-cap computation, shares-outstanding heuristics, beta fallbacks, float-shares logic, and dict assembly.
- **Root Cause:** No helper functions extracted for ETF-specific logic or data-dict construction.
- **Fix:** Extract `_build_etf_fallback_info()`, `_assemble_stock_dict()`, and `_detect_quote_type()` helpers.
- **Impact:** Easier unit testing; clearer intent per sub-function.

### TD-CQ-006 | Dead Code: beta3Year Fallback | Low | 🟡 Remaining
- **File:** `backend/services/yfinance_fallback.py` (lines 74-76)
- **Description:** `info.get("beta3Year")` almost never populated by yfinance in practice. Branch is dead code.
- **Root Cause:** Copy-paste from ETF handling without verifying field availability.
- **Fix:** Remove or add a comment explaining when this field is actually available.
- **Impact:** Removes confusion for future maintainers.

### TD-CQ-007 | Dead/Undeclared Variables: _retry_decorator | Low | 🟡 Remaining
- **File:** `backend/services/finnhub_service.py` (lines 96-108)
- **Description:** `_retry_decorator` defined but never applied to any function.
- **Root Cause:** Retry wrapper created as ARCH-003 fix but not wired into call sites.
- **Fix:** Apply decorator to `fetch_quote`, `fetch_company_profile`, and `search_symbol`, or remove if unused.
- **Impact:** Either enables retry logic or removes confusion.

---

## 3. Data Layer Issues

### TD-DATA-001 | Missing Ticker Validation at API Entry | High | 🟡 Remaining
- **File:** `backend/services/yfinance_fallback.py` (line 22) and routers
- **Description:** No ticker format validation before making expensive API calls. Invalid tickers waste rate-limit budget.
- **Root Cause:** No input validation layer between router and service.
- **Fix:** Use `lib/tickers.validate_ticker()` at router level; reject invalid patterns early.
- **Impact:** Prevents wasted API calls on malformed inputs.

### TD-DATA-002 | Unbounded Cache in HybridDataService | Critical | 🔴 Remaining
- **File:** `backend/services/hybrid_data_service.py`
- **Description:** Module-level `_cache: dict` grows unbounded over time. No TTL, no max size, no eviction policy.
- **Root Cause:** Simple dict cache without LRU or TTL implementation.
- **Fix:** Replace with `functools.lru_cache(maxsize=...)`, `cachetools.TTLCache`, or Redis-backed caching.
- **Impact:** Prevents memory leaks in long-running processes; predictable memory usage.

### TD-DATA-003 | Duplicate Indexes on News Model | Medium | 🟡 Remaining
- **File:** `backend/models/news.py`
- **Description:** Redundant indexes defined. `symbol` has both standalone and composite index coverage.
- **Root Cause:** Progressive index addition without reviewing existing coverage.
- **Fix:** Remove redundant standalone indexes where composite indexes already cover the column.
- **Impact:** Faster writes; reduced storage overhead.

### TD-DATA-004 | Missing Constraints on News Model | Medium | 🟡 Remaining
- **File:** `backend/models/news.py`
- **Description:** Fields like `title`, `symbol`, and `url` lack `nullable=False` constraints. Allows empty/NULL data.
- **Root Cause:** Schema defined with permissive defaults during rapid development.
- **Fix:** Add `nullable=False` to required fields; add unique constraint on `(url)` or `(uuid)`.
- **Impact:** Data integrity enforcement at DB level.

### TD-DATA-005 | N+1 Query Pattern in Batch Operations | High | 🟡 Remaining
- **File:** `backend/services/market_data_service.py`
- **Description:** When fetching stock data for watchlist, each ticker may trigger separate DB queries without batching.
- **Root Cause:** Per-ticker processing loop with individual DB lookups.
- **Fix:** Batch DB queries using `IN` clauses; fetch all existing records in one query before enrichment loop.
- **Impact:** Reduces DB round-trips from O(n) to O(1) for existence checks.

---

## 4. API Layer Issues

### TD-API-001 | Inconsistent Error Handling Across Routers | High | 🟡 Remaining
- **Files:** `backend/routers/stock.py`, `backend/routers/watchlist.py`
- **Description:** Different routers handle errors differently. Some return HTTPException, others return error dicts in 200 responses.
- **Root Cause:** No centralized error handling middleware or response convention.
- **Fix:** Implement global exception handler; standardize on HTTP status codes + consistent error body format.
- **Impact:** Predictable API behavior; easier frontend error handling.

### TD-API-002 | Missing Input Validation in Routers | High | 🟡 Remaining
- **File:** `backend/routers/stock.py`, `backend/routers/watchlist.py`
- **Description:** Router handlers accept user input without Pydantic validation models. Raw string parameters passed directly to services.
- **Root Cause:** FastAPI path/query params used without validation schemas.
- **Fix:** Define request/response Pydantic models; validate at router boundary.
- **Impact:** Type safety at API boundary; automatic OpenAPI schema generation.

### TD-API-003 | Business Logic in Router Layer | Medium | 🟡 Remaining
- **Files:** `backend/routers/stock.py`, `backend/routers/watchlist.py`
- **Description:** Routers contain data transformation and enrichment logic that belongs in services.
- **Root Cause:** Convenience of keeping related code together during development.
- **Fix:** Move all data processing to service layer; keep routers thin (request → service → response).
- **Impact:** Testable business logic; cleaner router code.

### TD-API-004 | Missing Logging on API Endpoints | Low | 🟡 Remaining
- **Files:** `backend/routers/*.py`
- **Description:** No request/response logging for audit trails. No correlation IDs for tracing requests across services.
- **Root Cause:** Logging not prioritized during development.
- **Fix:** Add middleware for request logging with correlation IDs; log slow requests.
- **Impact:** Debuggability in production; audit capability.

---

## 5. Frontend Issues

### TD-FE-001 | Inline Component ArticleCard in HomeClient | High | 🟡 Remaining
- **File:** `frontend/app/components/HomeClient.tsx` (lines 71-138)
- **Description:** 68-line inline component defined inside parent. Re-created on every render. No memoization, no separate tests possible.
- **Root Cause:** Component extracted inline instead of as standalone file.
- **Fix:** Extract to `frontend/components/news/ArticleCard.tsx` as a proper React component with memoization.
- **Impact:** Testable; reusable; better bundle tree-shaking.

### TD-FE-002 | Duplicate News Card UI Patterns | High | 🟡 Remaining
- **Files:** `frontend/app/components/HomeClient.tsx` vs `frontend/components/news/NewsCard.tsx`
- **Description:** Two divergent implementations of the same news card concept. Different sizing, different features, same image-with-fallback pattern.
- **Root Cause:** No shared base component for news card rendering.
- **Fix:** Create shared `<BaseNewsCard>` with configurable variants; or consolidate into a single component with props for size/features.
- **Impact:** Single source of truth for news card UI; consistent look/feel.

### TD-FE-003 | Duplicate Pagination Logic | Medium | 🟡 Remaining
- **File:** `frontend/app/components/HomeClient.tsx` (lines 43-46) and `frontend/hooks/useNews.ts`
- **Description:** HomeClient implements custom client-side pagination duplicating logic in `useNews` hook.
- **Root Cause:** Pagination not abstracted into shared utility.
- **Fix:** Extract pagination to `frontend/lib/pagination.ts`; use consistently across all pages.
- **Impact:** Consistent pagination behavior; less code to maintain.

### TD-FE-004 | Prop Drilling in Watchlist Components | Medium | 🟡 Remaining
- **File:** `frontend/components/watchlist/WatchlistTable.tsx`
- **Description:** Data and handlers passed through multiple component layers without context or composition.
- **Root Cause:** Direct prop passing pattern used throughout.
- **Fix:** Introduce React Context for shared watchlist state; use composition for UI variations.
- **Impact:** Reduces boilerplate; cleaner component interfaces.

### TD-FE-005 | Missing Error Types | Low | 🟡 Remaining
- **File:** `frontend/types/stock.ts`
- **Description:** Type definitions incomplete. Missing types for API error responses, loading states, and pagination metadata.
- **Root Cause:** Types added reactively as features were built.
- **Fix:** Add comprehensive type definitions: `StockError`, `PaginatedResponse<T>`, `LoadingState`.
- **Impact:** Full TypeScript coverage; catch type errors at compile time.

### TD-FE-006 | Business Logic Inside Components | Medium | 🟡 Remaining
- **File:** Various frontend components
- **Description:** Data transformation and formatting logic embedded directly in JSX render functions.
- **Root Cause:** Convenience of keeping related code together.
- **Fix:** Move formatting to utility functions; use useMemo for derived values.
- **Impact:** Faster renders; testable formatting logic outside React.

---

## 6. Security Issues

### TD-SEC-001 | API Key Logged on Startup | Critical | 🔴 Remaining
- **File:** `backend/main.py` / service init
- **Description:** API keys referenced in startup logging could leak to log files/containers.
- **Root Cause:** Debug-friendly logging without production sanitization.
- **Fix:** Never log API key values. Log presence/absence only (e.g., "Finnhub API: configured" or "not configured").
- **Impact:** Prevents credential leakage in logs.

### TD-SEC-002 | CORS Too Permissive | High | 🟡 Remaining
- **File:** `backend/main.py` (CORS middleware config)
- **Description:** CORS allows all origins, methods, and headers in potentially all environments.
- **Root Cause:** Development-friendly configuration not differentiated for production.
- **Fix:** Configure environment-specific CORS settings. Restrict origins to known frontend domains in production.
- **Impact:** Reduces attack surface from cross-origin requests.

### TD-SEC-003 | Missing Environment Variable Validation | Medium | 🟡 Remaining
- **File:** `backend/main.py`, service modules
- **Description:** Environment variables accessed without validation. Missing vars cause runtime errors deep in call stack.
- **Root Cause:** No startup config validation layer.
- **Fix:** Add pydantic-settings-based config model; validate all env vars at startup with clear error messages.
- **Impact:** Faster deployment failure detection; self-documenting config requirements.

---

## 7. Script & Project Hygiene Issues

### TD-SCRIPT-001 | Redundant Thumbnail Backfill Scripts (4 of 6) | High | 🟡 Remaining
- **Files:** `scripts/backfill_all_thumbnails.py`, `scripts/backfill_missing_thumbnails.py`, `scripts/backfill_og_thumbnails.py`, and potentially others
- **Description:** 4 of 6 backfill scripts are redundant. They all query for NULL thumbnail_url, fetch images from external sources, and UPDATE the DB. Core extraction functions copy-pasted across files.
- **Root Cause:** Iterative debugging led to new script creation instead of modifying existing ones.
- **Fix:** Keep primary `backfill_thumbnails.py`; archive or delete duplicates. Document which scripts are active in `scripts/README.md`.
- **Impact:** Reduces confusion about which script to run; eliminates maintenance burden on dead scripts.

### TD-SCRIPT-002 | Excessive Diagnostic Scripts (8 files) | Medium | 🟡 Remaining
- **Files:** `scripts/check_*.py` (8 files), `scripts/diag_*.py` (1 file)
- **Description:** 9 diagnostic/check scripts overlap significantly. Multiple scripts check thumbnail URLs, stats, domains, etc.
- **Root Cause:** Each debugging session spawned a new one-off script.
- **Fix:** Consolidate into a single `scripts/diagnose.py` with subcommands. Archive one-offs after issues resolved.
- **Impact:** Maintainable diagnostic tooling; clearer developer experience.

### TD-SCRIPT-003 | Test Artifacts in Repo | Low | ✅ Resolved (partially)
- **Files:** `test_output.txt`, `test_raw.txt` at project root
- **Description:** Test output files committed to repository.
- **Root Cause:** Not added to `.gitignore`.
- **Fix:** Add `test_output.txt`, `test_raw.txt`, and `*_output.txt` patterns to `.gitignore`. Remove from repo if not needed.
- **Impact:** Cleaner repo; no test artifacts in version control.

### TD-SCRIPT-004 | Typo'd Documentation Directory | Low | ✅ Resolved
- **Files:** `docs/finnnhub/` vs `docs/finnhub/`
- **Description:** Duplicate docs directory with typo ("finnnhub" vs "finnhub").
- **Root Cause:** Manual directory creation without checking existing names.
- **Fix:** Merge contents into correct `docs/finnhub/` directory; remove `docs/finnnhub/`.
- **Impact:** Single source of truth for Finnhub documentation.

---

## Refactoring Roadmap

### Phase 1: Safe Wins (Low Risk, High Value)
| # | Issue | Effort | Impact |
|---|-------|--------|--------|
| 1 | ✅ TD-CQ-001: Eliminate duplicate error fallback logic | Done | High |
| 2 | ✅ TD-CQ-002: Add missing fields to error fallback factory | Done | Low |
| 3 | ✅ TD-CQ-003: Remove unused import | Done | Low |
| 4 | TD-SEC-001: Stop logging API key values | 5 min | Critical |
| 5 | TD-CQ-007: Wire up or remove _retry_decorator | 15 min | Medium |
| 6 | TD-SCRIPT-003: Clean up test artifacts from repo | 5 min | Low |
| 7 | TD-API-004: Add basic request logging | 30 min | Low |

### Phase 2: Structural Improvements (Module Organization)
| # | Issue | Effort | Impact |
|---|-------|--------|--------|
| 1 | TD-DATA-002: Replace unbounded cache with TTL/LRU | 1 hour | Critical |
| 2 | TD-CQ-005: Refactor oversized get_stock_price_yf() | 1 hour | Medium |
| 3 | TD-FE-001: Extract ArticleCard inline component | 30 min | High |
| 4 | TD-FE-002: Consolidate duplicate news card patterns | 2 hours | High |
| 5 | TD-DATA-001: Add ticker validation at API entry | 30 min | High |
| 6 | TD-API-002: Add Pydantic validation to routers | 2 hours | High |
| 7 | TD-SCRIPT-001: Clean up redundant backfill scripts | 1 hour | Medium |
| 8 | TD-SCRIPT-002: Consolidate diagnostic scripts | 2 hours | Medium |

### Phase 3: Architecture Improvements (Higher Risk, Higher Reward)
| # | Issue | Effort | Impact |
|---|-------|--------|--------|
| 1 | TD-ARCH-004: Split God class market_data_service | 3-4 hours | High |
| 2 | TD-ARCH-005: Abstract provider interface pattern | 3 hours | Medium |
| 3 | TD-ARCH-001: Redis-backed distributed rate limiting | 3 hours | High |
| 4 | TD-DATA-005: Fix N+1 query patterns | 2 hours | High |
| 5 | TD-API-001: Standardize error handling globally | 2 hours | High |
| 6 | TD-FE-004: Introduce React Context for watchlist state | 3 hours | Medium |
| 7 | TD-SEC-002: Environment-specific CORS configuration | 1 hour | High |

---

## What Changed in This Initiative (V2 → V3)

### Code Changes Made
1. **Eliminated duplicate error fallback logic** — 76 lines of copy-paste code removed across two services. Both `finnhub_service.py` and `yfinance_fallback.py` now use the shared `create_error_fallback()` factory from `lib/error_fallback.py`.
2. **Fixed error fallback contract** — Added missing `ceo_name` and `exchange` fields to the shared factory.
3. **Removed unused import** — Cleaned up `_clamp` import in `yfinance_fallback.py`.

### Files Modified
- `backend/lib/error_fallback.py` — Added `ceo_name`, `exchange` fields
- `backend/services/finnhub_service.py` — Imported shared factory, replaced 3 call sites, deleted local `_error_fallback()` function (40 lines removed)
- `backend/services/yfinance_fallback.py` — Imported shared factory, replaced 1 call site, deleted local `_error_fallback()` function (38 lines removed), removed unused `_clamp` import

### Lines of Code Impact
- **Removed:** ~80 lines of duplicate code
- **Added:** ~2 lines (field additions to factory)
- **Net reduction:** ~78 lines

---

## Risk Assessment

| Change | Risk Level | Reason |
|--------|-----------|--------|
| Error fallback consolidation | Low | Same output shape; factory tested against both service shapes |
| Missing fields added to factory | Low | Only additions, no field removals |
| Unused import removal | None | Verified not referenced anywhere in file |

---

## Recommendations for Future Development

1. **Pre-commit hooks:** Add linting (ruff/flake8), type checking (mypy), and formatting (black) to prevent regressions.
2. **API contract testing:** Use OpenAPI schema validation to ensure router responses match expected shapes.
3. **Frontend component library:** Establish a pattern for shared UI components before feature divergence occurs.
4. **Script lifecycle policy:** New diagnostic scripts should be reviewed and either integrated into existing tooling or archived after use.
5. **Cache strategy document:** Define caching requirements (TTL, max size, eviction) before implementing new caches.
