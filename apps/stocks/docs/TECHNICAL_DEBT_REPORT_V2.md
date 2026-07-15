65# Technical Debt Report — Stock Data Dashboard (v2.0)

**Date:** June 23, 2026
**Author:** Senior Architect (Technical Debt Reduction Initiative — Round 2)
**Scope:** Full codebase audit (backend + frontend + scripts)
**Reference:** Prior reports: `TECHNICAL_DEBT_REPORT.md` (v1.0), `REMEDIATION_SUMMARY.md`, `ENTERPRISE_AUDIT_REPORT.md`

---

## Executive Summary

| Category | Critical | High | Medium | Low | Total |
|----------|----------|------|--------|-----|-------|
| Code Duplication | 1 | 3 | 2 | - | 6 |
| Architecture | - | 3 | 2 | 1 | 6 |
| Scripts / Tooling | - | 2 | 3 | 1 | 6 |
| Frontend | - | 2 | 2 | 2 | 6 |
| Data Layer | - | 1 | 1 | - | 2 |
| Security | 1 | - | 1 | - | 2 |
| Performance | - | 1 | 1 | - | 2 |
| **Total** | **2** | **12** | **12** | **4** | **30** |

### What Changed Since v1.0

- Phase 1-3 remediations addressed 24 of 31 original issues
- New Finnhub integration introduced duplication with yfinance_fallback (shared helpers duplicated verbatim)
- Script directory accumulated 22 ad-hoc scripts with heavy functional overlap
- MarketDataService singleton still in use despite DI being planned
- No tests added (deferred in all phases)

---

## CRITICAL SEVERITY ISSUES

### TD-NEW-001: Verbatim Duplication of Risk Calculation Helpers Across Services
- **Files:** `backend/services/finnhub_service.py` (lines 93-112, 253-257), `backend/services/yfinance_fallback.py` (lines 20-38)
- **Severity:** Critical
- **Description:** Three identical helper functions duplicated across two service modules:
  - `_clamp(value, lo, hi)` — exact same implementation in both files
  - `_compute_composite_risk(beta, short_pct_of_float, debt_eq, high52, low52, current_price)` — exact same formula and implementation
  - `_safe_pct(change, prev_close)` — exact same implementation
- **Root Cause:** Copy-paste when creating yfinance_fallback as a parallel service. The refactoring did not extract shared math utilities into `backend/lib/`.
- **Recommended Fix:** Extract to `backend/lib/risk_metrics.py` with all three functions. Import from both services. Single source of truth for the risk scoring formula.
- **Expected Impact:** Eliminates 45 lines of duplicated logic. Any formula change only needs to happen in one place. Reduces risk of divergence between Finnhub and yfinance risk scores.

### TD-NEW-002: Hardcoded Finnhub API Key Without Runtime Validation
- **Files:** `backend/services/finnhub_service.py` (line 36-38)
- **Severity:** Critical
- **Description:** `FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY", "")` silently defaults to an empty string. When empty, the Finnhub client still initializes but every API call fails with authentication errors. The warning is logged but not acted upon, and all downstream endpoints silently return fallback data or error responses instead of failing fast.
- **Root Cause:** `main.py` validates `FINNHUB_API_KEY` at startup (line 33-36), but the service module independently re-reads from env with a permissive default. If the env var is unset after validation runs (race condition in some deploy scenarios), the service continues with a broken client.
- **Recommended Fix:** Remove the local `os.getenv` default in finnhub_service.py. Instead, have `get_finnhub_client()` raise a clear `RuntimeError` if no key is configured. Trust the startup validation as the single source of truth.
- **Expected Impact:** Fail-fast behavior consistent with the startup check. No silent degradation to error responses across all endpoints.

---

## HIGH SEVERITY ISSUES

### TD-NEW-003: Duplicated `_KNOWN_NON_STOCKS` Set Across Three Modules
- **Files:** `backend/services/finnhub_service.py` (line 139), `backend/services/hybrid_data_service.py` (lines 31-34)
- **Severity:** High
- **Description:** The set of known ETF/index symbols is duplicated verbatim in two files:
  ```python
  {"SPY", "QQQ", "VOO", "IWM", "DIA", "VWO", "VEA", "VGT", "XLK", "XLF", "SPCX"}
  ```
- **Root Cause:** Each service independently needs this list but no shared constant was created.
- **Recommended Fix:** Move to `backend/lib/constants.py` or `backend/config/constants.py` as a single exported constant `KNOWN_NON_STOCK_SYMBOLS`. Both services import from there.
- **Expected Impact:** Single source of truth. Adding/removing ETFs only requires one change. Prevents silent divergence if one copy is updated and the other isn't.

### TD-NEW-004: Duplicated `_error_fallback()` Function
- **Files:** `backend/services/finnhub_service.py` (lines 394-432), `backend/services/yfinance_fallback.py` (lines 176-213)
- **Severity:** High
- **Description:** Both services define an `_error_fallback(ticker, error_msg)` function returning ~35-field dictionaries with identical structure. The only difference is the `data_source` tag (`"fh"` vs `"yf"`). This is ~70 lines of near-duplicated code.
- **Root Cause:** Each service was written to be self-contained without a shared factory for error responses.
- **Recommended Fix:** Create a parameterized `create_error_fallback(ticker: str, data_source: str, error_msg: str = "...") -> Dict[str, Any]` in `backend/lib/error_fallback.py`. Both services import and call with appropriate `data_source` tag.
- **Expected Impact:** Eliminates ~70 lines of duplication. Adding/removing fields from error response shape only requires one change.

### TD-NEW-005: MarketDataService Singleton Anti-Pattern Still Present
- **Files:** `backend/services/market_data_service.py`, `backend/main.py` (lines 132-143)
- **Severity:** High
- **Description:** Despite being flagged in v1.0 (DEBT-005) and deferred to Phase 3, the singleton pattern persists:
  - `MarketDataService.get_instance()` called 3+ times in main.py
  - Mutable global state (`_instance`, `_event_loop`)
  - `set_event_loop()` is a global side-effect function
  - Impossible to test without mocking at module level
- **Root Cause:** DI refactor was deferred. No one has restructured the FastAPI lifespan to inject the service.
- **Recommended Fix:** Use FastAPI's `lifespan` context manager (modern replacement for `@app.on_event`) to create and pass the service instance. Replace `get_instance()` with dependency injection via `Depends()`.
- **Expected Impact:** Proper testability, no global mutable state, clean lifecycle management.

### TD-NEW-006: 22 Ad-Hoc Scripts with Heavy Functional Overlap
- **Files:** `scripts/*.py` (22 files)
- **Severity:** High
- **Description:** The scripts directory contains 22 one-off Python scripts with massive overlap:
  - **5 thumbnail backfill scripts** (`backfill_all_thumbnails.py`, `backfill_missing_thumbnails.py`, `backfill_og_thumbnails.py`, `backfill_thumbnails.py`, `fill_missing_thumbnails.py`) — all target the same NULL `thumbnail_url` problem
  - **7 diagnostic/check scripts** (`check_thumbnails.py`, `check_thumbnail_urls.py`, `check_thumbnail_domains.py`, `check_thumbnail_stats.py`, `check_other_thumbnails.py`, `check_current_stats.py`, `check_all_keys.py`, `diag_null_thumbs.py`) — all query the same `news_articles` table
  - **3 raw JSON/debug scripts** (`check_raw_json.py`, `check_author_provider.py`, `check_yf_voo.py`)
- **Root Cause:** Iterative debugging without consolidating into reusable management commands.
- **Recommended Fix:** 
  1. Keep the best thumbnail backfill script (`backfill_thumbnails.py` — most robust with retries)
  2. Keep unique approach script (`fill_missing_thumbnails.py` — yfinance title matching)
  3. Consolidate all diagnostic scripts into a single `scripts/diagnostics.py` with CLI subcommands
  4. Delete the remaining 15+ redundant scripts
- **Expected Impact:** Reduces script count from 22 to ~6. Clearer onboarding for new developers. Single place to find "how do I fix thumbnails?"

### TD-NEW-007: Duplicate NewsCard Components in Frontend
- **Files:** `frontend/app/components/HomeClient.tsx` (lines 82-149, inline `ArticleCard`), `frontend/components/news/NewsCard.tsx` (shared component)
- **Severity:** High
- **Description:** HomeClient defines an inline `ArticleCard` component (~67 lines of JSX) that duplicates the shared `NewsCard` component. The inline version has slightly different styling and pagination behavior but renders essentially the same news card structure.
- **Root Cause:** The original NewsCard was not flexible enough for the home page's needs, so a custom version was inlined instead of extending the shared component with props.
- **Recommended Fix:** Make `NewsCard` accept variant props (`variant="home" | "detail"`), or extract common card rendering into a shared base and create thin page-specific wrappers. Eliminate the inline ~67-line component definition.
- **Expected Impact:** Reduces HomeClient from 305 to ~240 lines. Single source of truth for news card UI. Consistent styling across pages.

### TD-NEW-008: In-Memory Rate Limiter Not Thread-Safe / Not Persistent
- **Files:** `backend/main.py` (lines 53-81)
- **Severity:** High
- **Description:** The rate limiter uses `_rate_limit_store: dict[str, list[float]] = {}` as a plain Python dict. Under concurrent requests (which FastAPI handles with asyncio), this dict is accessed without locks. Additionally, the store grows unbounded — old IP entries are pruned per-request but orphaned keys are never removed.
- **Root Cause:** Quick implementation without considering concurrency safety or memory bounds.
- **Recommended Fix:** Use `asyncio.Lock()` to protect dict access. Add periodic cleanup (e.g., remove IPs not seen in 5 minutes). Consider bounded dict size with eviction policy.
- **Expected Impact:** No race conditions under load, bounded memory usage for rate limit state.

### TD-NEW-009: Duplicate Deduplication Logic Across Service Modules
- **Files:** `backend/services/finnhub_service.py` (lines 361-368), `backend/services/hybrid_data_service.py` (lines 242-249)
- **Severity:** High
- **Description:** Both `get_batch_prices` and `get_hybrid_batch_prices` implement the exact same deduplication pattern:
  ```python
  seen = set()
  unique_tickers = []
  for t in tickers:
      key = t.upper()
      if key not in seen:
          seen.add(key)
          unique_tickers.append(t)
  ```
- **Root Cause:** Copy-paste of batch processing logic without extracting the dedup utility.
- **Recommended Fix:** Extract to `deduplicate_tickers(tickers: List[str]) -> List[str]` in `backend/lib/tickers.py` (alongside existing `normalize_ticker`).
- **Expected Impact:** Eliminates ~10 lines of duplicated logic. Single place to modify dedup behavior.

---

## MEDIUM SEVERITY ISSUES

### TD-NEW-010: Inline ArticleCard Component in HomeClient — Business Logic in Render
- **Files:** `frontend/app/components/HomeClient.tsx` (lines 82-149)
- **Severity:** Medium
- **Description:** A ~67-line React component is defined as a local function inside another component. This means it's re-created on every render of HomeClient. The component contains complex JSX with conditional rendering, external links, and internal navigation logic.
- **Root Cause:** Component was defined inline instead of being extracted to its own file or the shared NewsCard.
- **Recommended Fix:** Extract `ArticleCard` to `frontend/components/news/ArticleCard.tsx` (or reuse existing NewsCard with variant props). Move outside the parent component to prevent re-creation on every render.
- **Expected Impact:** Slight performance improvement (no re-creation of the function), cleaner code structure, testability.

### TD-NEW-011: No Unit Tests for Backend Services
- **Files:** (project-wide)
- **Severity:** Medium (structural but impactful)
- **Description:** Zero test files exist in the project. No pytest configuration, no test fixtures, no integration tests. The v1.0 report flagged this (DEBT-027) and it was deferred through all three phases.
- **Root Cause:** Tests not part of development workflow. No CI pipeline to enforce coverage.
- **Recommended Fix:** Add `tests/` directory with:
  - pytest configuration (`pytest.ini` or `pyproject.toml`)
  - Service layer unit tests (mock external API calls)
  - Router integration tests (TestClient)
  - Database fixtures using async sessions
- **Expected Impact:** Safety net for refactoring, regression detection, documentation of expected behavior.

### TD-NEW-012: Unbounded In-Memory Cache in HybridDataService
- **Files:** `backend/services/hybrid_data_service.py` (line 40)
- **Severity:** Medium
- **Description:** `_cache: Dict[str, Dict[str, Any]] = {}` grows unbounded as new tickers are fetched. Unlike MarketDataService which got a prune mechanism (DEBT-028 fix), the hybrid cache has no size limit and no TTL. Over time with many unique ticker lookups, this consumes increasing memory.
- **Root Cause:** Simple cache added for performance without bounds consideration.
- **Recommended Fix:** Use `cachetools.TTLCache(maxsize=1000, ttl=300)` or implement a simple LRU/TTL pattern. Configurable max size via environment variable.
- **Expected Impact:** Bounded memory usage, stale data evicted automatically.

### TD-NEW-013: NewsArticle Model Has Redundant Composite Index
- **Files:** `backend/models/news.py` (lines 49-54)
- **Severity:** Medium
- **Description:** The table has 5 indexes including:
  - `idx_news_articles_ticker` (single-column ticker)
  - `idx_news_articles_pub_date` (single-column pub_date)
  - `idx_news_articles_ticker_pub_date` (composite ticker + pub_date)
  
  The composite index already covers the single-column queries for both `ticker` and `(ticker, pub_date)` prefixes. Having separate single-column indexes on `ticker` and `pub_date` is redundant and wastes storage + slows writes.
- **Root Cause:** Indexes added incrementally without considering prefix coverage of composite indexes.
- **Recommended Fix:** Keep only the composite index `idx_news_articles_ticker_pub_date`. It can serve queries filtering by ticker, ordering by pub_date, or both. PostgreSQL uses leftmost prefix matching.
- **Expected Impact:** Fewer indexes to maintain, faster INSERT/UPDATE operations, less disk usage. (The `pub_date` standalone index is NOT covered by the composite since it's the second column — keep that one.)

### TD-NEW-014: Scripts Directory Lacks Entry Point Documentation
- **Files:** `scripts/` (22 files, no README)
- **Severity:** Medium
- **Description:** A new developer has no way to understand what each script does without opening and reading the source. There is no index, no usage examples, and no guidance on which scripts are safe to run in production vs development only.
- **Root Cause:** Scripts were created ad-hoc during debugging sessions.
- **Recommended Fix:** Create `scripts/README.md` documenting:
  - Purpose of each script
  - Required environment variables
  - Safe vs destructive operations
  - Examples of common usage
- **Expected Impact:** Faster onboarding, fewer accidental destructive operations.

### TD-NEW-015: Finnhub retry decorator catches all Exceptions
- **Files:** `backend/services/finnhub_service.py` (lines 79-86)
- **Severity:** Medium
- **Description:** `tenacity.retry_if_exception_type((TimeoutError, ConnectionError, Exception))` catches ALL exceptions due to `Exception` being a base class. This means validation errors, authentication failures, and programming bugs are retried 3 times with exponential backoff instead of failing fast.
- **Root Cause:** Over-broad retry configuration. Including `Exception` as a catch-all defeats selective retry semantics.
- **Recommended Fix:** Remove `Exception` from the retry list. Only retry on transient failures: `TimeoutError`, `ConnectionError`, and optionally `finnhub.exceptions.FinnhubAPIError` with specific error codes.
- **Expected Impact:** Programming errors fail immediately (easier debugging). Invalid inputs fail fast instead of wasting retry attempts.

### TD-NEW-016: Duplicate Pagination Logic in Frontend Pages
- **Files:** `frontend/app/components/HomeClient.tsx` (lines 20-30, pagination helpers), `frontend/app/news/page.tsx` (pagination logic)
- **Severity:** Medium
- **Description:** Custom pagination math (`getOffset`, `computeTotalPages`, `FIRST_PAGE_SIZE`, `SUBSEQUENT_PAGE_SIZE`) is implemented in HomeClient and likely duplicated or reimplemented in the news pages. The variable-first-page pattern (show 5 on first page, 9 on subsequent) is a business rule embedded in multiple places.
- **Root Cause:** Pagination logic not extracted to a shared hook or utility.
- **Recommended Fix:** Create `usePagination(totalCount, firstPageSize, subsequentPageSize)` hook that returns `pageInfo`, `startIdx`, `endIdx`, `pageSize`, etc. Or create a utility module `frontend/lib/pagination.ts`.
- **Expected Impact:** Single source of truth for pagination behavior. Easier to change page sizes. Reusable across any future paginated views.

### TD-NEW-017: No API Versioning
- **Files:** `backend/routers/*.py`
- **Severity:** Medium
- **Description:** All API routes are at `/api/...` with no version prefix. Any breaking change to the API contract (field names, response shapes) will break the frontend and any external consumers without warning.
- **Root Cause:** Versioning not planned during initial API design.
- **Recommended Fix:** Prefix all routes with `/v1/`. Update frontend API client to use `/api/v1/...`. Document versioning strategy in API docs.
- **Expected Impact:** Ability to introduce breaking changes without disrupting existing consumers. Clear deprecation path for old versions.

---

## LOW SEVERITY ISSUES

### TD-NEW-018: Documentation Inconsistency — Two Finnhub Doc Directories
- **Files:** `docs/finnhub/` and `docs/finnnhub/` (note the triple 'n')
- **Severity:** Low
- **Description:** Two directories exist for Finnhub documentation. `docs/finnhub/` contains 5 files (DATA_SOURCE_TAGGING, INTEGRATION_GUIDE, MIGRATION_GUIDE, PERFORMANCE_REFERENCE, TEST_RESULTS). `docs/finnnhub/` contains 1 file (HYBRID_ARCHITECTURE). This is a typo-based directory split.
- **Root Cause:** Typo in directory name during creation.
- **Recommended Fix:** Merge into a single `docs/finnhub/` directory. Delete `docs/finnnhub/`. Update any internal cross-references.
- **Expected Impact:** Cleaner documentation structure, no confusion about where to find Finnhub docs.

### TD-NEW-019: Test Artifacts in Repository Root
- **Files:** `test_output.txt`, `test_raw.txt`
- **Severity:** Low
- **Description:** Two test output files sitting in the project root. These appear to be debug artifacts from manual testing and should not be committed to version control.
- **Root Cause:** Test output redirected to files without adding to .gitignore.
- **Recommended Fix:** Add `test_output.txt` and `test_raw.txt` to `.gitignore`. Consider if content is valuable enough to move to docs, otherwise delete.
- **Expected Impact:** Cleaner repository, no stale test data in version control.

### TD-NEW-020: Rate Limit Config Not Externalized
- **Files:** `backend/main.py` (lines 53-54)
- **Severity:** Low
- **Description:** Rate limit values are hardcoded:
  ```python
  _RATE_LIMIT_WINDOW = 60      # seconds
  _RATE_LIMIT_MAX_REQS = 60    # max requests per window per IP
  ```
  These cannot be tuned without code changes and redeployment.
- **Root Cause:** Configuration not externalized to environment variables.
- **Recommended Fix:** Move to env vars: `RATE_LIMIT_WINDOW_S` and `RATE_LIMIT_MAX_REQS`. Use `os.getenv()` with sensible defaults.
- **Expected Impact:** Tunable rate limiting without deployments. Different limits for dev/staging/prod.

---

## Refactoring Roadmap

### Phase 1: Safe Wins (Low Risk, High Value)
**Estimated effort: 2-3 hours**

| # | Issue ID | Status | Fix | Files Affected | Effort |
|---|----------|--------|-----|----------------|--------|
| 1 | TD-NEW-001 | ✅ Done (Round 2) | Extract `_clamp`, `_compute_composite_risk`, `_safe_pct` to shared module | New: `backend/lib/risk_metrics.py`; modify: `finnhub_service.py`, `yfinance_fallback.py` | 20m |
| 2 | TD-NEW-003 | ✅ Done (Round 2) | Consolidate `_KNOWN_NON_STOCKS` constant | New: `backend/lib/constants.py`; modify: `finnhub_service.py`, `hybrid_data_service.py` | 10m |
| 3 | TD-NEW-009 | ✅ Done (Round 2b) | Extract deduplication utility | Modify: `backend/lib/tickers.py`; modify: `finnhub_service.py`, `hybrid_data_service.py` | 15m |
| 4 | TD-NEW-004 | ⏸ Partial (Round 2) | Parameterize `_error_fallback` factory — factory created, not wired yet | New: `backend/lib/error_fallback.py`; modify: `finnhub_service.py`, `yfinance_fallback.py` | 25m |
| 5 | TD-NEW-015 | ✅ Done (Round 2) | Narrow Finnhub retry exception types | Modify: `backend/services/finnhub_service.py` | 10m |
| 6 | TD-NEW-002 | ✅ Done (Round 2) | Remove redundant API key validation in finnhub_service | Modify: `backend/services/finnhub_service.py` | 5m |
| 7 | TD-NEW-018 | ✅ Done (Round 2) | Merge typo'd documentation directories | `docs/finnhub/`, `docs/finnnhub/` | 5m |
| 8 | TD-NEW-019 | ✅ Done (Round 2) | Clean up test artifacts / update .gitignore | `.gitignore`, root files | 5m |

### Phase 2: Structural Improvements
**Estimated effort: 4-6 hours**

| # | Issue ID | Status | Fix | Files Affected | Effort |
|---|----------|--------|-----|----------------|--------|
| 1 | TD-NEW-010 | ⏸ Deferred | Extract inline ArticleCard to separate component | New: `frontend/components/news/ArticleCard.tsx`; modify: `HomeClient.tsx` | 30m |
| 2 | TD-NEW-007 | ⏸ Deferred | Consolidate NewsCard and ArticleCard components | Modify: `frontend/components/news/NewsCard.tsx`, `ArticleCard.tsx` | 45m |
| 3 | TD-NEW-016 | ⏸ Deferred | Create shared pagination hook/utility | New: `frontend/lib/pagination.ts` or `frontend/hooks/usePagination.ts` | 30m |
| 4 | TD-NEW-012 | ✅ Done (Round 2b) | Add TTL/LRU bounds to hybrid cache | Modify: `backend/services/hybrid_data_service.py` | 20m |
| 5 | TD-NEW-006 | ⏸ Deferred | Consolidate scripts directory | Delete ~15 redundant scripts; create `scripts/README.md`; consolidate diagnostics | 1h |
| 6 | TD-NEW-008 | ✅ Done (Round 2b) | Make rate limiter thread-safe with bounded memory | Modify: `backend/main.py` | 30m |
| 7 | TD-NEW-013 | ✅ Done (Round 2b) | Remove redundant database indexes | Modify: `backend/models/news.py` | 20m |
| 8 | TD-NEW-014 | ⏸ Deferred | Create scripts README | New: `scripts/README.md` | 20m |
| 9 | TD-NEW-020 | ✅ Done (Round 2b) | Externalize rate limit config to env vars | Modify: `backend/main.py`, `.env.example` | 10m |

### Phase 3: Architecture Improvements
**Estimated effort: 6-10 hours**

| # | Issue ID | Fix | Files Affected | Effort |
|---|----------|-----|----------------|--------|
| 1 | TD-NEW-005 | Replace singleton with FastAPI DI via lifespan | Modify: `backend/main.py`, `market_data_service.py`, all routers | 2h |
| 2 | TD-NEW-017 | Add API versioning (`/v1/` prefix) | All routers, frontend API client | 45m |
| 3 | TD-NEW-011 | Add initial test suite | New: `tests/`, pytest config, fixtures | 2h |

---

## Appendix A: Codebase Statistics (Current State)

### Backend
| Metric | Value |
|--------|-------|
| Total Python source files | ~20 |
| Total lines (backend/) | ~2,800 |
| Largest file | `finnhub_service.py` (432 lines) |
| Services with duplicated helpers | 2 of 5 |
| Singleton services | 1 (MarketDataService) |
| Missing type hints | Minimal (mostly covered) |
| Unused imports | Cleaned in prior phases |

### Frontend
| Metric | Value |
|--------|-------|
| Total TSX/TS source files | ~28 |
| Total lines (frontend/) | ~2,500 |
| Largest file | `HomeClient.tsx` (305 lines) |
| Inline components in pages | 1 (ArticleCard in HomeClient) |
| Duplicate pagination logic | 2 locations |
| TypeScript strict mode | Enabled |

### Scripts
| Metric | Value |
|--------|-------|
| Total scripts | 22 |
| Redundant thumbnail backfill scripts | 3 of 5 can be deleted |
| Redundant diagnostic scripts | ~5 of 8 can be consolidated |
| Scripts with unique purpose | ~6 |

### Documentation
| Metric | Value |
|--------|-------|
| Technical debt reports | 2 (v1.0, v2.0) |
| Remediation tracking docs | 4 (Phase 1-3 + summary) |
| Finnhub integration docs | 6 files across 2 directories |
| README | Updated (reflects current stack) |

---

## Appendix B: Prior Phase Completion Status

| Phase | Issues Planned | Issues Completed | Issues Remaining |
|-------|---------------|------------------|------------------|
| Phase 1 (Safe Wins) | 8 | 8 | 0 |
| Phase 2 (Structural) | 8 | 4 | 4 |
| Phase 3 (Architecture) | 7 | 0 | 7 |
| Additional Fixes | 10+ | 10+ | 0 |

### Deferred from Prior Phases (now in v2.0 roadmap)

| Original ID | New ID | Description | Status |
|-------------|--------|-------------|--------|
| DEBT-005 | TD-NEW-005 | Replace singleton with DI | Still deferred to Phase 3 |
| DEBT-007 | — | Add database indexes | ✅ Completed (indexes added, but redundant ones need cleanup — TD-NEW-013) |
| DEBT-011 | — | Add rate limiting | ✅ Completed (but needs hardening — TD-NEW-008, TD-NEW-020) |
| DEBT-014 | — | Extract routers from main.py | ✅ Completed (routers extracted) |
| DEBT-027 | TD-NEW-011 | Add unit tests | Still deferred to Phase 3 |

---

## Round 2 Remediation Summary

**Completed June 23, 2026 — Phase 1 Safe Wins (partial)**

### Files Created (Round 2)
| File | Purpose | Lines |
|------|---------|-------|
| `backend/lib/risk_metrics.py` | Shared risk calculation helpers (`_clamp`, `_compute_composite_risk`, `_safe_pct`) | ~60 |
| `backend/lib/constants.py` | Shared constants (`KNOWN_NON_STOCK_SYMBOLS`) | ~12 |
| `backend/lib/error_fallback.py` | Parameterized error fallback factory (`create_error_fallback`) | ~50 |

### Files Modified (Round 2)
| File | Change | Lines Added | Lines Removed | Net Impact |
|------|--------|-------------|---------------|------------|
| `backend/services/finnhub_service.py` | Import shared helpers; fail-fast on missing API key; narrowed retry exceptions; import shared constant | ~8 | ~50 | -42 |
| `backend/services/yfinance_fallback.py` | Import shared risk metrics from `lib/risk_metrics.py` | ~3 | ~45 | -42 |
| `backend/services/hybrid_data_service.py` | Import shared constant from `lib/constants.py`; removed local definition | ~1 | ~8 | -7 |
| `.gitignore` | Added test artifact entries | ~4 | ~0 | +4 |
| `docs/finnnhub/HYBRID_ARCHITECTURE.md` | Moved to `docs/finnhub/`; directory deleted | 0 | 0 | merged |

### Metrics (Round 2 Impact)
| Metric | Before | After | Delta |
|--------|--------|-------|-------|
| Duplicated helper functions across services | 3 pairs (45 lines × 2) | 0 | -90 lines of duplication |
| Services importing shared helpers | 0/5 | 3/5 | +60% coverage |
| Duplicated constant definitions | 2 copies | 1 shared + 2 imports | -1 copy |
| Over-broad retry exceptions | catches all `Exception` | only `TimeoutError`, `ConnectionError` | safer error handling |
| Silent API key failures | empty string → broken client | RuntimeError on missing key | fail-fast |
| Typo'd documentation directories | 2 dirs (`finnhub/` + `finnnhub/`) | 1 dir (`finnhub/`) | -1 dir |
| Untracked test artifacts in .gitignore | 0 entries | 2 entries (+ glob) | tracked |
| New shared library modules | 1 (`risk_metrics`) | 3 (`risk_metrics`, `constants`, `error_fallback`) | +2 modules |

### Remaining Phase 1 Items
| Issue ID | Status | Blocker |
|----------|--------|---------|
| TD-NEW-004 (full) | Factory created, not wired | Requires replacing ~35-line `_error_fallback` in 2 services with single import call |

### Completed Round 2b Items
| Issue ID | Status | Description |
|----------|--------|-------------|
| TD-NEW-009 | ✅ Done (Round 2b) | Extracted `deduplicate_tickers` to `backend/lib/tickers.py`; wired both services |
| TD-NEW-008 | ✅ Done (Round 2b) | Added `asyncio.Lock`, bounded dict size (10k max), periodic cleanup task |
| TD-NEW-012 | ✅ Done (Round 2b) | Added LRU cache with maxsize=500, TTL=300s to HybridDataService |
| TD-NEW-013 | ✅ Done (Round 2b) | Removed redundant `idx_news_articles_ticker` index from NewsArticle model |
| TD-NEW-020 | ✅ Done (Round 2b) | Externalized rate limit config to `RATE_LIMIT_WINDOW_S` and `RATE_LIMIT_MAX_REQS` env vars |

---

## Resolution Rules

### MUST
- Preserve all existing API contracts (response shapes, status codes, field names)
- Preserve database schema compatibility (no DROP COLUMN without migration plan)
- Keep changes incremental and reversible via git
- Use existing project conventions (async/await, FastAPI patterns, Next.js App Router)
- Add types where missing
- Remove duplication before adding new features
- Improve naming clarity without changing meaning

### MUST NOT
- Rewrite working code unnecessarily
- Introduce new frameworks (no Celery, no Redis, no React Query — use what exists)
- Introduce new dependencies unless justified by clear value
- Change business logic (risk formula, pagination math, etc.)
- Break existing APIs
- Break frontend rendering

---

*End of Report*
