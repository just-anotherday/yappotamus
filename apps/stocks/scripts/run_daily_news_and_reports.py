"""Daily stock-news ingestion and weekday analysis-report generation.

This is the deterministic entry point used by the scheduled Codex task. It
runs the backend services directly, so it does not leave an HTTP server or a
development reload process running after completion.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yfinance as yf
from alembic.config import Config
from alembic.script import ScriptDirectory
from dotenv import load_dotenv
from sqlalchemy import text


STOCKS_ROOT = Path(__file__).resolve().parents[1]
os.chdir(STOCKS_ROOT)
sys.path.insert(0, str(STOCKS_ROOT))
load_dotenv(STOCKS_ROOT / ".env", override=False)

from backend.config.database import async_session_factory
from backend.routers import analysis as analysis_router
from backend.services.market_data_service import parse_download_quotes
from backend.services.news_ingestion_service import fetch_and_ingest_watchlist_once


EASTERN = ZoneInfo("America/New_York")
REPORT_TICKERS = ("SPCX", "AMD", "NVDA", "SPY")
REPORT_MODEL = "qwen3.8:27b"
REPORT_ARTICLE_LIMIT = 50
REPORT_DAYS_BACK = 14
REPORT_PROMPT_VERSION = "3.0"
REPORT_MAX_ATTEMPTS = 2
ALEMBIC_INI = STOCKS_ROOT / "alembic.ini"
ALEMBIC_UPGRADE_COMMAND = "python -m alembic upgrade head"


def _event(name: str, **fields: Any) -> None:
    print(
        json.dumps(
            {
                "event": name,
                "timestamp": datetime.now(EASTERN).isoformat(),
                **fields,
            },
            default=str,
            sort_keys=True,
        ),
        flush=True,
    )


def _repository_migration_state() -> tuple[ScriptDirectory, tuple[str, ...]]:
    config = Config(str(ALEMBIC_INI))
    script = ScriptDirectory.from_config(config)
    return script, tuple(sorted(script.get_heads()))


async def _database_migration_revisions() -> tuple[str, ...]:
    async with async_session_factory() as session:
        result = await session.execute(
            text("SELECT version_num FROM alembic_version ORDER BY version_num")
        )
        return tuple(row[0] for row in result.all())


def _revision_ancestors(
    script: ScriptDirectory, revisions: tuple[str, ...]
) -> set[str]:
    ancestors: set[str] = set()
    pending = list(revisions)
    while pending:
        revision_id = pending.pop()
        if revision_id in ancestors:
            continue
        revision = script.get_revision(revision_id)
        if revision is None:
            raise LookupError(revision_id)
        ancestors.add(revision_id)
        down_revisions = revision.down_revision
        if isinstance(down_revisions, str):
            pending.append(down_revisions)
        elif down_revisions:
            pending.extend(down_revisions)
    return ancestors


def _migration_mismatch_reason(
    script: ScriptDirectory,
    current: tuple[str, ...],
    expected: tuple[str, ...],
) -> str:
    if len(current) > 1:
        return "Database has multiple unexpected Alembic revisions."
    try:
        current_ancestors = _revision_ancestors(script, current)
        expected_ancestors = _revision_ancestors(script, expected)
    except (LookupError, KeyError):
        return "Database migration state is divergent from the repository history."
    if set(current).issubset(expected_ancestors):
        return "Database schema is behind the repository migration head."
    if set(expected).issubset(current_ancestors):
        return "Database schema is ahead of the repository migration head."
    return "Database migration state is divergent from the repository history."


def _format_revisions(revisions: tuple[str, ...]) -> str:
    return ", ".join(revisions) if revisions else "unavailable"


async def _run_schema_preflight() -> bool:
    expected: tuple[str, ...] = ()
    current: tuple[str, ...] = ()
    try:
        script, expected = _repository_migration_state()
        if not expected:
            raise RuntimeError("repository has no Alembic head")
        current = await _database_migration_revisions()
        if not current:
            raise RuntimeError("database has no Alembic revision")
        if set(current) == set(expected):
            _event(
                "database_schema_preflight_completed",
                current_revisions=list(current),
                expected_heads=list(expected),
            )
            return True
        reason = _migration_mismatch_reason(script, current, expected)
    except Exception:
        reason = "Database migration state could not be determined."

    print(
        "Daily workflow preflight failed:\n"
        f"{reason}\n"
        f"Current: {_format_revisions(current)}\n"
        f"Expected: {_format_revisions(expected)}\n"
        "Apply the pending Stocks Alembic migrations and rerun the workflow.\n"
        f"From apps/stocks with the same local configuration, run: {ALEMBIC_UPGRADE_COMMAND}",
        file=sys.stderr,
        flush=True,
    )
    _event(
        "database_schema_preflight_failed",
        reason=reason,
        current_revisions=list(current),
        expected_heads=list(expected),
        migration_command=ALEMBIC_UPGRADE_COMMAND,
    )
    return False


def _fetch_report_quotes() -> dict[str, dict[str, Any]]:
    frame = yf.download(
        tickers=list(REPORT_TICKERS),
        period="5d",
        interval="1m",
        group_by="column",
        auto_adjust=False,
        prepost=False,
        progress=False,
        threads=True,
        timeout=15,
    )
    quotes = parse_download_quotes(frame, list(REPORT_TICKERS))
    for ticker, quote in quotes.items():
        quote.update(
            ticker=ticker,
            symbol=ticker,
            company_name=(
                "SPDR S&P 500 ETF Trust" if ticker == "SPY" else ticker
            ),
            current_price=quote["price"],
        )
    return quotes


async def _generate_report(ticker: str, quote: dict[str, Any]) -> dict[str, Any]:
    async def quote_override(requested_ticker: str) -> dict[str, Any] | None:
        if requested_ticker.upper() != ticker:
            return None
        return dict(quote)

    analysis_router.get_hybrid_stock_price = quote_override
    last_error: Exception | None = None

    for attempt in range(1, REPORT_MAX_ATTEMPTS + 1):
        _event(
            "report_started",
            ticker=ticker,
            attempt=attempt,
            model=REPORT_MODEL,
            max_articles=REPORT_ARTICLE_LIMIT,
        )
        try:
            async with async_session_factory() as session:
                result = await analysis_router.analysis_analyze_ticker(
                    ticker=ticker,
                    max_articles=REPORT_ARTICLE_LIMIT,
                    days_back=REPORT_DAYS_BACK,
                    model=REPORT_MODEL,
                    provider="ollama",
                    prompt_version=REPORT_PROMPT_VERSION,
                    article_ids=None,
                    session=session,
                )
            outcome = {
                "ticker": ticker,
                "status": "completed",
                "report_id": result.report_id,
                "sentiment": result.overall_sentiment,
                "confidence": result.confidence_score,
                "attempt": attempt,
            }
            _event("report_completed", **outcome)
            return outcome
        except Exception as exc:
            last_error = exc
            _event(
                "report_attempt_failed",
                ticker=ticker,
                attempt=attempt,
                exception_type=type(exc).__name__,
                error=str(exc),
            )

    assert last_error is not None
    return {
        "ticker": ticker,
        "status": "failed",
        "exception_type": type(last_error).__name__,
        "error": str(last_error),
        "attempts": REPORT_MAX_ATTEMPTS,
    }


async def run(*, dry_run: bool = False, preflight_only: bool = False) -> int:
    now_eastern = datetime.now(EASTERN)
    is_weekday = now_eastern.weekday() < 5
    _event(
        "daily_pipeline_started",
        eastern_date=now_eastern.date().isoformat(),
        is_weekday=is_weekday,
        dry_run=dry_run,
    )

    if dry_run:
        _event(
            "dry_run_completed",
            news_action="run",
            reports_action="run" if is_weekday else "skip_weekend",
            report_tickers=list(REPORT_TICKERS),
            model=REPORT_MODEL,
            max_articles=REPORT_ARTICLE_LIMIT,
        )
        return 0

    if not await _run_schema_preflight():
        return 1

    if preflight_only:
        _event("daily_pipeline_preflight_completed")
        return 0

    news_summary = await fetch_and_ingest_watchlist_once(
        async_session_factory,
        force=True,
        trigger_kind="auto",
    )
    _event(
        "news_collection_completed",
        status=news_summary.get("status"),
        tickers=news_summary.get("tickers"),
        articles_returned=news_summary.get("articles_returned"),
        articles_inserted=news_summary.get("articles_inserted"),
        duplicates_ignored=news_summary.get("duplicates_ignored"),
        provider_successes=news_summary.get("provider_successes"),
        provider_failures=news_summary.get("provider_failures"),
    )
    if news_summary.get("status") not in {"completed", "skipped_cadence"}:
        _event("daily_pipeline_failed", reason="news_collection_incomplete")
        return 1

    if not is_weekday:
        _event("reports_skipped", reason="weekend")
        _event("daily_pipeline_completed", reports_generated=0)
        return 0

    quotes = await asyncio.to_thread(_fetch_report_quotes)
    missing_quotes = sorted(set(REPORT_TICKERS) - set(quotes))
    if missing_quotes:
        _event("daily_pipeline_failed", reason="missing_market_quotes", tickers=missing_quotes)
        return 1

    outcomes = []
    for ticker in REPORT_TICKERS:
        outcomes.append(await _generate_report(ticker, quotes[ticker]))

    failures = [item for item in outcomes if item["status"] != "completed"]
    _event(
        "daily_pipeline_completed" if not failures else "daily_pipeline_failed",
        reports_generated=len(outcomes) - len(failures),
        reports_failed=len(failures),
        outcomes=outcomes,
    )
    return 0 if not failures else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate configuration and print the planned weekday/weekend actions.",
    )
    parser.add_argument(
        "--preflight-only",
        action="store_true",
        help="Validate the local database migration state without running ingestion or reports.",
    )
    args = parser.parse_args()
    return asyncio.run(
        run(dry_run=args.dry_run, preflight_only=args.preflight_only)
    )


if __name__ == "__main__":
    raise SystemExit(main())
