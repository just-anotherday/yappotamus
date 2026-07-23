"""Thin command-line adapter over the durable maintenance coordinator."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Sequence, TextIO
from uuid import UUID

from backend.maintenance.article_intelligence.clients import (
    ExportClient, PromptCompatibilityClient, PublisherClient,
)
from backend.maintenance.article_intelligence.config import MaintenanceCLIConfig
from backend.maintenance.article_intelligence.coordinator import CoordinatorResult, MaintenanceCoordinator
from backend.maintenance.article_intelligence.run_store import SQLiteMaintenanceRunStore


def build_coordinator(config: MaintenanceCLIConfig) -> MaintenanceCoordinator:
    config.run_store_path.parent.mkdir(parents=True, exist_ok=True)
    options = {"transport": None, "timeout": config.timeout}
    return MaintenanceCoordinator(
        SQLiteMaintenanceRunStore(config.run_store_path),
        PromptCompatibilityClient(config.production_url, config.api_token, **options),
        ExportClient(config.production_url, config.api_token, **options),
        PublisherClient(config.production_url, config.api_token, **options),
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="article-intelligence-maintenance")
    parser.add_argument("--env-file", type=Path, help="optional dotenv file")
    subparsers = parser.add_subparsers(dest="command", required=True)

    start = subparsers.add_parser("start", help="create and run a resumable maintenance workflow")
    start.add_argument("--model")
    start.add_argument("--client-request-id", type=UUID)
    start.add_argument("--ticker", action="append", dest="tickers")
    start.add_argument("--max-items", type=int, default=25, choices=range(1, 51), metavar="1..50")
    publication = start.add_mutually_exclusive_group()
    publication.add_argument("--dry-run", action="store_true")
    publication.add_argument("--publish", action="store_true")

    status = subparsers.add_parser("status", help="show durable run status")
    status.add_argument("run_id", type=UUID)

    resume = subparsers.add_parser("resume", help="resume fetch or generation without publishing")
    resume.add_argument("run_id", type=UUID)

    dry_run = subparsers.add_parser("dry-run", help="resume and validate publication without writing")
    dry_run.add_argument("run_id", type=UUID)

    publish = subparsers.add_parser("publish", help="resume and publish to production")
    publish.add_argument("run_id", type=UUID)
    return parser


def _result_payload(result: CoordinatorResult) -> dict:
    return {
        "run_id": str(result.run.run_id),
        "client_request_id": str(result.run.client_request_id),
        "state": result.run.state,
        "model": result.run.model,
        "exported": result.exported,
        "generated": result.generated,
        "published": result.published,
        "rejected": result.rejected,
        "retryable": result.retryable,
        "last_error": result.run.last_error,
    }


def _progress(stream: TextIO, event: str, **values: object) -> None:
    print(json.dumps({"event": event, **values}, sort_keys=True), file=stream, flush=True)


async def run_command(args: argparse.Namespace, coordinator: MaintenanceCoordinator,
                      progress: TextIO = sys.stderr) -> CoordinatorResult:
    _progress(progress, "command_started", command=args.command)
    if args.command == "start":
        publish = args.publish or args.dry_run
        result = await coordinator.start(
            model=args.model, client_request_id=args.client_request_id, tickers=args.tickers,
            max_items=args.max_items, publish=publish, dry_run=args.dry_run,
        )
    elif args.command == "status":
        result = coordinator.status(args.run_id)
    elif args.command == "resume":
        result = await coordinator.resume(args.run_id)
    elif args.command == "dry-run":
        result = await coordinator.resume(args.run_id, publish=True, dry_run=True)
    else:
        result = await coordinator.resume(args.run_id, publish=True)
    _progress(progress, "command_completed", command=args.command, **_result_payload(result))
    return result


def main(argv: Sequence[str] | None = None, *, coordinator: MaintenanceCoordinator | None = None,
         stdout: TextIO = sys.stdout, stderr: TextIO = sys.stderr) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        if coordinator is None:
            config = MaintenanceCLIConfig.load(args.env_file)
            coordinator = build_coordinator(config)
        if args.command == "start" and args.model is None:
            args.model = config.model if "config" in locals() else None
            if args.model is None:
                parser.error("--model is required when using an injected coordinator")
        result = asyncio.run(run_command(args, coordinator, stderr))
        print(json.dumps(_result_payload(result), sort_keys=True), file=stdout)
        return 0
    except (EnvironmentError, KeyError, RuntimeError, ValueError) as exc:
        _progress(stderr, "command_failed", command=args.command, error=str(exc))
        return 1
