from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from backend.exceptions import register_exception_handlers


def test_controlled_500_keeps_cors_headers_for_frontend_origin(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "https://stocks.yapvibes.com")
    app = FastAPI()
    register_exception_handlers(app)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["https://stocks.yapvibes.com"],
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @app.get("/boom")
    async def boom():
        raise RuntimeError("database unavailable")

    response = TestClient(app, raise_server_exceptions=False).get(
        "/boom", headers={"Origin": "https://stocks.yapvibes.com"}
    )
    assert response.status_code == 500
    assert response.headers["access-control-allow-origin"] == "https://stocks.yapvibes.com"
    assert response.json()["error"] == "Internal server error"


def test_preflight_accepts_authorization_for_configured_origin(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "https://stocks.yapvibes.com")
    app = FastAPI()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["https://stocks.yapvibes.com"],
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"],
    )
    response = TestClient(app).options(
        "/news",
        headers={
            "Origin": "https://stocks.yapvibes.com",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://stocks.yapvibes.com"
    assert "authorization" in response.headers["access-control-allow-headers"].lower()
