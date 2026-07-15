import asyncio, sys, selectors, urllib.request, urllib.error, json
sys.path.insert(0, '.')

BASE = "http://localhost:8000"

endpoints = [
    ("GET", "/api/analysis/reports/company/NVDA"),
    ("GET", "/api/analysis/reports/sector/all"),
    ("GET", "/api/analysis/reports/market/latest"),
    ("GET", "/api/analysis/reports/queue/status"),
    ("GET", "/api/analysis/reports/"),
]

post_endpoints = [
    ("/api/analysis/reports/company/NVDA/regenerate", {"ticker": "NVDA"}),
    ("/api/analysis/reports/sector/Technology/regenerate", None),
    ("/api/analysis/reports/market/regenerate", None),
]

def test_get(path):
    try:
        req = urllib.request.Request(f"{BASE}{path}")
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read())
        print(f"  200 OK  GET {path}")
        return True
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else ""
        print(f"  {e.code} ERR  GET {path} -> {body[:200]}")
        return False
    except Exception as e:
        print(f"  FAIL     GET {path} -> {e}")
        return False

def test_post(path, body):
    try:
        payload = json.dumps(body).encode() if body else b'{}'
        req = urllib.request.Request(f"{BASE}{path}", data=payload, headers={"Content-Type": "application/json"}, method="POST")
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read())
        print(f"  200 OK  POST {path}")
        return True
    except urllib.error.HTTPError as e:
        body_text = e.read().decode() if e.fp else ""
        print(f"  {e.code} ERR  POST {path} -> {body_text[:200]}")
        return False
    except Exception as e:
        print(f"  FAIL     POST {path} -> {e}")
        return False

print("\n=== Testing GET endpoints ===")
ok = sum(1 for e in endpoints if test_get(e[1]))
print(f"\n=== Testing POST endpoints ===")
ok += sum(1 for path, body in post_endpoints if test_post(path, body))
total = len(endpoints) + len(post_endpoints)
print(f"\nResult: {ok}/{total} passed")
