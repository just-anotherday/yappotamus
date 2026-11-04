"""Retry pending uploads without regenerating reports; optionally enqueue history."""
import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func, select
from backend.config.database import async_session_factory, engine
from backend.models.report import AnalysisReportModel
from backend.models.report_publication import ReportPublication
from backend.services.report_publishing import publish_pending, publishing_target, queue_report


async def run(*, backfill=False):
    if not publishing_target():
        raise SystemExit("Set REPORT_PUBLISH_URL and REPORT_PUBLISH_TOKEN before publishing")
    try:
        if backfill:
            # Bounded transactions, no report regeneration, and unique local report IDs.
            last_id = 0
            while True:
                async with async_session_factory() as session:
                    reports = list((await session.scalars(select(AnalysisReportModel).where(
                        AnalysisReportModel.id > last_id,
                    ).order_by(AnalysisReportModel.id).limit(100))).all())
                    if not reports:
                        break
                    for report in reports:
                        await queue_report(session, report)
                    last_id = reports[-1].id
                    await session.commit()
        result = await publish_pending(limit=500)
        async with async_session_factory() as session:
            pending = await session.scalar(select(func.count()).select_from(ReportPublication).where(ReportPublication.published_at.is_(None)))
        print(json.dumps({**result, "pending": pending}))
        return 1 if pending else 0
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backfill", action="store_true", help="Queue existing saved analysis reports as well as new reports")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run(backfill=args.backfill)))
