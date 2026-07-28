"""Static contract checks between frontend API calls and FastAPI routes."""

import re
from pathlib import Path

from backend.main import app


FRONTEND_ROOT = Path(__file__).resolve().parents[1] / "frontend"
API_CALL = re.compile(
    r"apiFetch\(\s*`\$\{API_BASE\}(?P<path>[^`]+)`",
    re.MULTILINE,
)
DYNAMIC_PART = re.compile(r"\$\{[^}]+\}")
ROUTE_PARAMETER = re.compile(r"\{[^}]+\}")


def _normalized_route(path: str) -> str:
    path = path.split("?", 1)[0]
    path = DYNAMIC_PART.sub("{parameter}", path)
    path = ROUTE_PARAMETER.sub("{parameter}", path)
    return path.rstrip("/") or "/"


def test_frontend_api_paths_exist_in_backend_openapi():
    backend_paths = {
        _normalized_route(path)
        for path in app.openapi()["paths"]
    }
    frontend_paths: dict[str, list[str]] = {}

    for source_path in FRONTEND_ROOT.rglob("*"):
        if source_path.suffix not in {".ts", ".tsx"}:
            continue
        if any(part in {"node_modules", ".next", ".open-next"} for part in source_path.parts):
            continue
        source = source_path.read_text(encoding="utf-8")
        for match in API_CALL.finditer(source):
            route = _normalized_route(match.group("path"))
            frontend_paths.setdefault(route, []).append(
                str(source_path.relative_to(FRONTEND_ROOT))
            )

    missing = {
        route: callers
        for route, callers in frontend_paths.items()
        if route not in backend_paths
    }
    assert not missing, f"Frontend API routes missing from backend OpenAPI: {missing}"


def test_removed_nonexistent_market_routes_do_not_return():
    active_source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (FRONTEND_ROOT / "lib").glob("*.ts")
    )
    for nonexistent_path in ("/stats", "/risk-signal", "/backfill"):
        assert nonexistent_path not in active_source
