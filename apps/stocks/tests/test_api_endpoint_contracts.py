"""Security contracts for financial-analysis API persistence boundaries."""

import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import Depends, FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from backend.auth import verify_app_access_token
from backend.config.database import get_async_session
from backend.main import app
from backend.models.analysis import ArticleReference, FinancialAnalysisResponse
from backend.routers import analysis as analysis_router
from backend.routers import analysis_reports as analysis_reports_router
from backend.services import report_service
from backend.services.ollama_service import CURRENT_PROMPT_VERSION


REMOVED_SAVE_PATH = "/api/analysis/reports/save"
ROUTERS_ROOT = Path(__file__).resolve().parents[1] / "backend" / "routers"


def _registered_route_methods(application: FastAPI) -> set[tuple[str, str]]:
    return {
        (method, route.path)
        for route in application.routes
        if isinstance(route, APIRoute)
        for method in route.methods
    }


def test_untrusted_report_save_route_and_request_model_are_absent():
    assert ("POST", REMOVED_SAVE_PATH) not in _registered_route_methods(app)
    assert not hasattr(analysis_reports_router, "SaveReportRequest")


def test_untrusted_report_save_post_is_absent_from_openapi():
    path_item = app.openapi()["paths"].get(REMOVED_SAVE_PATH, {})
    assert "post" not in path_item


def test_trusted_analysis_and_existing_report_routes_remain_registered():
    registered = _registered_route_methods(app)
    expected = {
        ("POST", "/api/analysis/analyze_ticker"),
        ("GET", "/api/analysis/reports/"),
        ("GET", "/api/analysis/reports/latest/{ticker}"),
        ("GET", "/api/analysis/reports/{report_id}"),
        ("DELETE", "/api/analysis/reports/{report_id}"),
        ("GET", "/api/analysis/reports/company/{ticker}"),
        ("POST", "/api/analysis/reports/company/{ticker}/regenerate"),
        ("GET", "/api/analysis/reports/company/{ticker}/history"),
        ("GET", "/api/analysis/reports/market/latest"),
        ("GET", "/api/analysis/reports/market/history"),
        ("GET", "/api/analysis/reports/market/{report_id}"),
        ("POST", "/api/analysis/reports/market/regenerate"),
        ("GET", "/api/analysis/reports/sector/all"),
        ("GET", "/api/analysis/reports/sector/{sector}"),
        ("POST", "/api/analysis/reports/sector/{sector}/regenerate"),
        ("GET", "/api/analysis/reports/queue/status"),
        ("GET", "/api/analysis/reports/pipeline/status"),
        ("GET", "/api/analysis/reports/unified"),
    }
    assert expected <= registered

    openapi_paths = app.openapi()["paths"]
    assert "post" in openapi_paths["/api/analysis/analyze_ticker"]
    assert "get" in openapi_paths["/api/analysis/reports/"]
    assert "delete" in openapi_paths["/api/analysis/reports/{report_id}"]


def _legacy_save_payload(**overrides):
    payload = {
        "ticker": "AMD",
        "report_data": {"asset": "AMD", "overall_sentiment": "Neutral"},
        "articles_count": 0,
        "model_used": "fake-model",
        "prompt_version": "99.0",
        "current_price_at_analysis": 999_999.0,
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def removed_save_client(monkeypatch):
    persistence = AsyncMock(side_effect=AssertionError("removed save path persisted"))
    session = SimpleNamespace(commit=AsyncMock())

    async def test_session():
        yield session

    monkeypatch.setattr(analysis_router, "create_report", persistence)
    monkeypatch.setattr(report_service, "create_report", persistence)
    monkeypatch.setattr(
        analysis_reports_router, "create_report", persistence, raising=False
    )
    app.dependency_overrides[get_async_session] = test_session
    try:
        yield TestClient(app), persistence, session
    finally:
        app.dependency_overrides.pop(get_async_session, None)


@pytest.mark.parametrize(
    "headers",
    [
        pytest.param({}, id="no-auth"),
        pytest.param(
            {"Authorization": "Bearer test-app-token"}, id="normal-app-auth"
        ),
    ],
)
def test_removed_save_requests_never_dispatch_persistence(removed_save_client, headers):
    client, persistence, session = removed_save_client

    response = client.post(
        REMOVED_SAVE_PATH,
        headers=headers,
        json=_legacy_save_payload(),
    )

    assert not 200 <= response.status_code < 300
    persistence.assert_not_awaited()
    session.commit.assert_not_awaited()


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param(
            _legacy_save_payload(
                report_data={
                    "asset": "AMD",
                    "articles_used": [
                        {
                            "title": "Fabricated article",
                            "url": "https://attacker.invalid/fabricated",
                            "published_at": "1900-01-01T00:00:00Z",
                        }
                    ],
                }
            ),
            id="fabricated-citation",
        ),
        pytest.param(
            _legacy_save_payload(
                report_data={
                    "articles_used": [
                        {"title": f"Fabricated {index}"} for index in range(1_000)
                    ]
                },
                articles_count=1_000,
            ),
            id="fabricated-counts",
        ),
        pytest.param(
            _legacy_save_payload(model_used="definitely-not-a-provider-model"),
            id="fake-model",
        ),
        pytest.param(
            _legacy_save_payload(prompt_version="99.0"),
            id="fake-prompt-version",
        ),
        pytest.param(
            _legacy_save_payload(
                ticker="AMD", report_data={"asset": "NVDA", "confidence_score": 100}
            ),
            id="ticker-asset-mismatch",
        ),
        pytest.param(
            _legacy_save_payload(
                current_price_at_analysis=999_999.0,
                report_data={"asset": "AMD", "current_price_at_analysis": -1.0},
            ),
            id="fake-price",
        ),
        pytest.param(
            _legacy_save_payload(
                report_data={"asset": "AMD", "investment_rating": "Moonshot"}
            ),
            id="unsupported-rating",
        ),
        pytest.param(
            _legacy_save_payload(
                report_data={
                    "asset": "AMD",
                    "investment_rating": "Strong Buy",
                    "executive_summary": "Unreviewed recommendation.",
                }
            ),
            id="unreviewed-analysis",
        ),
        pytest.param(
            _legacy_save_payload(
                report_data={
                    "asset": "AMD",
                    "unexpected": {"nested": ["arbitrary", {"json": True}]},
                }
            ),
            id="unexpected-nested-json",
        ),
        pytest.param(
            _legacy_save_payload(report_data={"arbitrary": "json"}),
            id="minimal-arbitrary-json",
        ),
    ],
)
def test_malicious_legacy_save_payloads_are_non_dispatching(
    removed_save_client, payload
):
    client, persistence, session = removed_save_client

    response = client.post(
        REMOVED_SAVE_PATH,
        headers={"Authorization": "Bearer test-app-token"},
        json=payload,
    )

    assert not 200 <= response.status_code < 300
    persistence.assert_not_awaited()
    session.commit.assert_not_awaited()


class _CreateReportCallVisitor(ast.NodeVisitor):
    def __init__(self, direct_names: set[str], module_names: set[str]):
        self.direct_names = direct_names
        self.module_names = module_names
        self.function_stack: list[str] = []
        self.calls: list[tuple[str, int]] = []

    def visit_FunctionDef(self, node: ast.FunctionDef):
        self.function_stack.append(node.name)
        self.generic_visit(node)
        self.function_stack.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Call(self, node: ast.Call):
        is_direct = isinstance(node.func, ast.Name) and node.func.id in self.direct_names
        is_module_call = (
            isinstance(node.func, ast.Attribute)
            and node.func.attr == "create_report"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id in self.module_names
        )
        if is_direct or is_module_call:
            owner = self.function_stack[-1] if self.function_stack else "<module>"
            self.calls.append((owner, node.lineno))
        self.generic_visit(node)


def _router_create_report_calls() -> list[tuple[str, str]]:
    calls = []
    for path in sorted(ROUTERS_ROOT.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        direct_names = {
            alias.asname or alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            and node.module == "backend.services.report_service"
            for alias in node.names
            if alias.name == "create_report"
        }
        module_names = {
            alias.asname or alias.name.rsplit(".", 1)[-1]
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
            if alias.name == "backend.services.report_service"
        }
        module_names.update(
            alias.asname or alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            and node.module == "backend.services"
            for alias in node.names
            if alias.name == "report_service"
        )
        visitor = _CreateReportCallVisitor(direct_names, module_names)
        visitor.visit(tree)
        calls.extend((path.name, owner) for owner, _line in visitor.calls)
    return calls


def test_analyze_ticker_is_the_only_normal_router_report_persistence_callsite():
    # Internal services remain free to persist through explicit trusted workflows;
    # this contract limits the browser-facing API router surface only.
    assert _router_create_report_calls() == [
        ("analysis.py", "analysis_analyze_ticker")
    ]


def test_analyze_ticker_auth_and_backend_owned_persistence_are_preserved(monkeypatch):
    article = SimpleNamespace(
        id=1,
        title="Trusted database article",
        summary="Trusted database summary.",
        provider_name="Trusted Wire",
        article_url="https://trusted.example/amd",
        pub_date=None,
    )

    async def execute(_statement):
        return SimpleNamespace(
            scalars=lambda: SimpleNamespace(all=lambda: [article])
        )

    session = SimpleNamespace(execute=execute, commit=AsyncMock())

    async def test_session():
        yield session

    accepted = FinancialAnalysisResponse(
        asset="AMD",
        overall_sentiment="Neutral",
        confidence_score=60,
        investment_rating="Hold",
        articles_used=[
            ArticleReference(
                title=article.title,
                url=article.article_url,
                published_at=None,
            )
        ],
        executive_summary="Accepted deterministic fixture.",
    )
    generate = AsyncMock(return_value=accepted)
    persist = AsyncMock(return_value=77)
    monkeypatch.setattr(analysis_router, "generate_analysis", generate)
    monkeypatch.setattr(analysis_router, "create_report", persist)
    monkeypatch.setattr(
        analysis_router,
        "get_hybrid_stock_price",
        AsyncMock(
            return_value={
                "current_price": 123.45,
                "previous_close": 120.0,
                "fifty_two_week_high": 150.0,
                "fifty_two_week_low": 80.0,
                "volume": 1_000_000,
                "company_name": "Advanced Micro Devices",
            }
        ),
    )
    monkeypatch.setattr(
        analysis_router,
        "resolve_provider_model",
        lambda *_args: ("ollama", "fixture-model"),
    )
    monkeypatch.setattr(analysis_router, "_get_timeout_for_model", lambda *_: 30)

    test_app = FastAPI()
    test_app.include_router(
        analysis_router.router,
        dependencies=[Depends(verify_app_access_token)],
    )
    test_app.dependency_overrides[get_async_session] = test_session
    client = TestClient(test_app)
    payload = {
        "ticker": "amd",
        "max_articles": 1,
        "days_back": 3,
        "provider": "ollama",
        "model": "fixture-model",
        "article_ids": [1],
    }

    unauthorized = client.post("/api/analysis/analyze_ticker", json=payload)
    assert unauthorized.status_code == 401
    generate.assert_not_awaited()
    persist.assert_not_awaited()
    session.commit.assert_not_awaited()

    response = client.post(
        "/api/analysis/analyze_ticker",
        headers={"Authorization": "Bearer test-app-token"},
        json=payload,
    )

    assert response.status_code == 200
    assert response.json()["report_id"] == 77
    generate.assert_awaited_once()
    persist.assert_awaited_once()
    session.commit.assert_awaited_once()

    generated_request = generate.await_args.args[0]
    assert generated_request.ticker == "AMD"
    assert generated_request.price_data.current_price == 123.45
    assert generated_request.news_articles[0].title == article.title
    assert generated_request.news_articles[0].url == article.article_url

    persisted = persist.await_args.kwargs
    assert persisted["ticker"] == "AMD"
    assert persisted["report_data"]["asset"] == "AMD"
    assert persisted["report_data"]["articles_used"] == [
        {
            "title": article.title,
            "url": article.article_url,
            "published_at": None,
        }
    ]
    assert persisted["articles_count"] == 1
    assert len(persisted["report_data"]["articles_used"]) == 1
    assert persisted["model_used"] == "fixture-model"
    assert persisted["prompt_version"] == CURRENT_PROMPT_VERSION
    assert len(persisted["prompt_hash"]) == 64
    assert persisted["current_price_at_analysis"] == 123.45
