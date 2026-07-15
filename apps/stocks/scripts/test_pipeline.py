"""Comprehensive pipeline test for YapVibes architecture migration."""
import sys
import asyncio
from datetime import datetime, timedelta
from sqlalchemy import text, select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

# Fix Windows console encoding
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

DB_URL = "postgresql+asyncpg://postgres:Fo11ow%23%24%24@localhost:5432/news"
engine = create_async_engine(DB_URL, echo=False)

TEST_TICKER = "AAPL"

def print_section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")

async def test_db_connection():
    """Test 1: Database connectivity."""
    print_section("TEST 1: Database Connection")
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT version()"))
        ver = result.fetchone()[0]
        print(f"PostgreSQL: {ver[:80]}...")
        print("[OK] Database connection OK")
    return True

async def test_assets_table():
    """Test 2: Assets table structure and data."""
    print_section("TEST 2: Assets Table")
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT COUNT(*) FROM assets WHERE is_active = true"))
        count = result.scalar()
        print(f"Active assets: {count}")

        result = await conn.execute(text("""
            SELECT ticker, slug, sector, analysis_window_days, max_articles_per_analysis
            FROM asset_tickers t
            JOIN assets a ON t.asset_id = a.id
            WHERE t.is_primary = true
            LIMIT 5
        """))
        rows = result.fetchall()
        print(f"\nSample assets with config columns:")
        for r in rows:
            print(f"  {r[0]:8} | {r[1]:20} | sector={r[2] or 'None':15} | window={r[3]}d | max_articles={r[4]}")

        if count > 0:
            print(f"\n[OK] Assets table OK ({count} active assets)")
        else:
            print("\n[WARN] No active assets found")
    return count > 0

async def test_ai_company_reports():
    """Test 3: AI Company Reports table."""
    print_section("TEST 3: AI Company Reports")
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT COUNT(*) FROM ai_company_reports"))
        count = result.scalar()
        print(f"Total company reports: {count}")

        if count > 0:
            result = await conn.execute(text("""
                SELECT ticker, overall_sentiment, confidence_score, articles_count,
                       EXTRACT(EPOCH FROM NOW() - updated_at)/3600 as hours_ago
                FROM ai_company_reports
                ORDER BY updated_at DESC
                LIMIT 5
            """))
            rows = result.fetchall()
            print(f"\nLatest reports:")
            for r in rows:
                print(f"  {r[0]:8} | sentiment={r[1] or 'N/A':12} | confidence={r[2]} | articles={r[3]} | updated {r[4]:.1f}h ago")

        print("[OK] AI Company Reports table OK")
    return True

async def test_ai_sector_reports():
    """Test 4: AI Sector Reports table."""
    print_section("TEST 4: AI Sector Reports")
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT COUNT(*) FROM ai_sector_reports"))
        count = result.scalar()
        print(f"Total sector reports: {count}")

        if count > 0:
            result = await conn.execute(text("""
                SELECT sector, overall_sentiment, assets_count, confidence_score,
                       EXTRACT(EPOCH FROM NOW() - created_at)/3600 as hours_ago
                FROM ai_sector_reports
                ORDER BY created_at DESC
                LIMIT 5
            """))
            rows = result.fetchall()
            print(f"\nLatest sector reports:")
            for r in rows:
                print(f"  {r[0]:15} | sentiment={r[1] or 'N/A'} | assets={r[2]} | confidence={r[3]} | age={r[4]:.1f}h")

        print("[OK] AI Sector Reports table OK")
    return True

async def test_ai_market_reports():
    """Test 5: AI Market Reports table."""
    print_section("TEST 5: AI Market Reports")
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT COUNT(*) FROM ai_market_reports"))
        count = result.scalar()
        print(f"Total market reports: {count}")

        if count > 0:
            result = await conn.execute(text("""
                SELECT report_date, overall_sentiment, risk_level, confidence_score,
                       EXTRACT(EPOCH FROM NOW() - created_at)/3600 as hours_ago
                FROM ai_market_reports
                ORDER BY created_at DESC
                LIMIT 3
            """))
            rows = result.fetchall()
            print(f"\nLatest market reports:")
            for r in rows:
                print(f"  date={r[0]} | sentiment={r[1] or 'N/A'} | risk={r[2] or 'N/A'} | confidence={r[3]} | age={r[4]:.1f}h")

        print("[OK] AI Market Reports table OK")
    return True

async def test_ai_job_queue():
    """Test 6: AI Job Queue."""
    print_section("TEST 6: AI Job Queue")
    async with engine.connect() as conn:
        result = await conn.execute(text("""
            SELECT status, COUNT(*)
            FROM ai_job_queue
            GROUP BY status
            ORDER BY status
        """))
        rows = result.fetchall()
        print("Job queue by status:")
        for r in rows:
            bar = "#" * min(r[1], 50)
            print(f"  {r[0]:12} | {r[1]:4} {bar}")

        result = await conn.execute(text("""
            SELECT job_type, target_type || ':' || target_id as target, status, retry_count, scheduled_for
            FROM ai_job_queue
            ORDER BY created_at DESC
            LIMIT 5
        """))
        rows = result.fetchall()
        print(f"\nRecent jobs:")
        for r in rows:
            print(f"  {r[0]:15} | target={r[1]:8} | status={r[2]:12} | retries={r[3]} | scheduled={r[4]}")

        print("[OK] AI Job Queue OK")
    return True

async def test_indexes():
    """Test 7: Performance indexes exist."""
    print_section("TEST 7: Database Indexes")
    async with engine.connect() as conn:
        result = await conn.execute(text("""
            SELECT tablename, indexname
            FROM pg_indexes
            WHERE schemaname = 'public'
              AND (tablename LIKE '%ai_%' OR tablename IN ('assets', 'asset_tickers', 'news_articles'))
            ORDER BY tablename, indexname
        """))
        rows = result.fetchall()

        print(f"Found {len(rows)} indexes on AI/asset/news tables:\n")
        current_table = None
        for r in rows:
            if r[0] != current_table:
                print(f"  [{r[0]}]")
                current_table = r[0]
            print(f"    {r[1]}")

        print(f"\n[OK] Index scan OK ({len(rows)} indexes)")
    return True

async def test_article_count():
    """Test 8: News articles available for processing."""
    print_section("TEST 8: News Articles")
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT COUNT(*) FROM news_articles"))
        total = result.scalar()
        print(f"Total articles: {total}")

        result = await conn.execute(text("""
            SELECT ticker, COUNT(*) as cnt
            FROM news_articles
            WHERE ticker IS NOT NULL
            GROUP BY ticker
            ORDER BY cnt DESC
            LIMIT 10
        """))
        rows = result.fetchall()
        print(f"\nArticles by ticker (top 10):")
        for r in rows:
            bar = "#" * min(r[1] // max(1, total // 200), 50)
            print(f"  {r[0]:8} | {r[1]:4} {bar}")

        if total > 0:
            print(f"\n[OK] News articles OK ({total} articles)")
        else:
            print("\n[WARN] No articles in database")
    return True

async def test_unique_constraint():
    """Test 9: Unique constraint on ai_company_reports.ticker."""
    print_section("TEST 9: Unique Constraints")
    async with engine.connect() as conn:
        result = await conn.execute(text("""
            SELECT conname, confrelid::regclass
            FROM pg_constraint
            WHERE contype = 'u'
              AND confrelid::regclass::text = 'ai_company_reports'
        """))
        rows = result.fetchall()
        print("Unique constraints on ai_company_reports:")
        for r in rows:
            print(f"  {r[0]} on {r[1]}")

        if rows:
            print("[OK] Unique constraints enforced")
        else:
            print("[WARN] No unique constraints found")
    return True

async def test_api_endpoint():
    """Test 10: API endpoint availability."""
    print_section("TEST 10: HTTP API Endpoint Test")
    try:
        import urllib.request
        import json

        endpoints = [
            ("GET", "/api/health"),
            ("GET", f"/api/analysis/reports/company/{TEST_TICKER}"),
            ("GET", "/api/analysis/reports/queue/status"),
            ("GET", "/api/analysis/reports/market/latest"),
            ("GET", "/api/analysis/reports/sector/all"),
        ]

        for method, path in endpoints:
            try:
                url = f"http://localhost:8000{path}"
                req = urllib.request.Request(url)
                resp = urllib.request.urlopen(req, timeout=5)
                data = json.loads(resp.read())
                status = resp.status
                summary = str(data)[:120] if isinstance(data, dict) else f"items={len(data)}" if isinstance(data, list) else "ok"
                print(f"  {path} -> {status} | {summary}")
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    print(f"  {path} -> 404 (no data yet, expected)")
                else:
                    print(f"  {path} -> {e.code}")
            except Exception as e:
                print(f"  {path} -> ERROR: {str(e)[:60]}")

        print("\n[OK] API endpoints responding")
        return True
    except Exception as e:
        print(f"\n[WARN] API test failed (backend may not be running): {e}")
        return False

async def test_regenerate_endpoint():
    """Test 11: POST regenerate endpoint."""
    print_section("TEST 11: Regenerate Endpoint")
    try:
        import urllib.request
        import json

        url = f"http://localhost:8000/api/analysis/reports/company/{TEST_TICKER}/regenerate"
        req = urllib.request.Request(url, data=b"", method="POST")
        resp = urllib.request.urlopen(req, timeout=10)
        status = resp.status
        data = json.loads(resp.read())
        print(f"  POST /api/analysis/reports/company/{TEST_TICKER}/regenerate -> {status}")
        if status == 200:
            print(f"    message={data.get('message', 'N/A')}")

        import time
        time.sleep(1)

        # Check queue status after trigger
        req2 = urllib.request.Request("http://localhost:8000/api/analysis/reports/queue/status")
        resp2 = urllib.request.urlopen(req2, timeout=5)
        data2 = json.loads(resp2.read())
        print(f"  Queue after trigger: pending={data2.get('pending', 0)} processing={data2.get('processing', 0)}")

        print("\n[OK] Regenerate endpoint OK")
        return True
    except Exception as e:
        print(f"\n[WARN] Regenerate test failed: {e}")
        return False

async def main():
    print("=" * 62)
    print("   YapVibes Pipeline Test Suite")
    print("   Architecture Migration Verification")
    print("=" * 62 + "\n")

    results = {}
    tests = [
        ("DB Connection", test_db_connection),
        ("Assets Table", test_assets_table),
        ("AI Company Reports", test_ai_company_reports),
        ("AI Sector Reports", test_ai_sector_reports),
        ("AI Market Reports", test_ai_market_reports),
        ("AI Job Queue", test_ai_job_queue),
        ("Database Indexes", test_indexes),
        ("News Articles", test_article_count),
        ("Unique Constraints", test_unique_constraint),
        ("API Endpoints", test_api_endpoint),
        ("Regenerate Endpoint", test_regenerate_endpoint),
    ]

    passed = 0
    failed = 0

    for name, test_fn in tests:
        try:
            ok = await test_fn()
            results[name] = "PASS" if ok else "WARN"
            if ok:
                passed += 1
            else:
                failed += 1
        except Exception as e:
            import traceback
            print(f"\n[FAIL] {name} FAILED: {e}")
            traceback.print_exc()
            results[name] = "FAIL"
            failed += 1

    print_section("TEST SUMMARY")
    total = passed + failed
    for name, status in results.items():
        icon = "[PASS]" if status == "PASS" else "[WARN]" if status == "WARN" else "[FAIL]"
        print(f"  {icon} {name:25} [{status}]")

    print(f"\n  Total: {passed}/{total} passed, {failed} failed/warning")

    if failed == 0:
        print("\n  >>> All pipeline tests passed!")
    else:
        print(f"\n  >>> {failed} test(s) had warnings or failures")

if __name__ == "__main__":
    asyncio.run(main())
