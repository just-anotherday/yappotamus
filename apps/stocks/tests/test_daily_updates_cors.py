"""Exercise the real app's cross-origin browser request boundary."""
def test_daily_update_switch_preflight_allows_patch_from_live_site(monkeypatch):
    monkeypatch.setenv("FINNHUB_API_KEY", "test-finnhub-key")
    monkeypatch.setenv("CORS_ORIGINS", "https://stocks.yapvibes.com")
    from fastapi.testclient import TestClient
    from backend import main
    monkeypatch.setattr(main, "allow_origins_list", ["https://stocks.yapvibes.com"])
    # No context manager: this preflight does not run backend startup workers.
    client = TestClient(main.create_app())
    response = client.options("/api/daily-updates/tickers/SPY", headers={
        "Origin": "https://stocks.yapvibes.com",
        "Access-Control-Request-Method": "PATCH",
        "Access-Control-Request-Headers": "authorization,content-type",
    })
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://stocks.yapvibes.com"
    assert "PATCH" in response.headers["access-control-allow-methods"]
    rejected = client.options("/api/daily-updates/tickers/SPY", headers={
        "Origin": "https://untrusted.example",
        "Access-Control-Request-Method": "PATCH",
    })
    assert rejected.status_code == 400
    assert "access-control-allow-origin" not in rejected.headers
