"""Fast, database-only watchlist coverage and recent news summaries."""
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.lib.timestamps import utc_isoformat

EASTERN = ZoneInfo("America/New_York")
NEWS_EVENTS = (
    ("Earnings", r"\b(earnings|quarterly results|profit warning|guidance)\b"),
    ("Deal", r"\b(acquisition|acquire[sd]?|merger|takeover)\b"),
    ("Regulatory", r"\b(antitrust|lawsuit|investigation|regulator|recall)\b"),
    ("Company event", r"\b(dividend|stock split|layoffs|bankruptcy|ceo)\b"),
)


def expected_report_date(now: datetime):
    """Most recent weekday whose 20:30 Eastern run is due (not an exchange calendar)."""
    local = now.astimezone(EASTERN)
    day = local.date()
    if (local.hour, local.minute) < (20, 30):
        day -= timedelta(days=1)
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day


def coverage_status(created_at: datetime | None, now: datetime) -> str:
    if created_at is None:
        return "missing"
    aware = created_at.replace(tzinfo=timezone.utc) if created_at.tzinfo is None else created_at
    return "current" if aware.astimezone(EASTERN).date() >= expected_report_date(now) else "outdated"


def news_reason(title: str) -> str | None:
    return next((label for label, pattern in NEWS_EVENTS if re.search(pattern, title, re.I)), None)


async def get_report_coverage(session: AsyncSession) -> dict:
    now = datetime.now(timezone.utc)
    # Latest report lookup uses the existing ticker/created_at index and excludes JSON bodies.
    rows = (await session.execute(text("""
        SELECT w.ticker, COALESCE(NULLIF(a.name, ''), w.ticker) AS company_name,
               r.id AS report_id, r.created_at, r.overall_sentiment, r.confidence_score
        FROM watchlist w
        LEFT JOIN assets a ON a.primary_ticker = w.ticker
        LEFT JOIN LATERAL (
            SELECT id, created_at, overall_sentiment, confidence_score
            FROM analysis_reports WHERE ticker = w.ticker
            ORDER BY created_at DESC, id DESC LIMIT 1
        ) r ON true
        ORDER BY w.position, w.ticker
    """))).mappings().all()
    items = [dict(row, status=coverage_status(row["created_at"], now),
                  created_at=utc_isoformat(row["created_at"])) for row in rows]
    counts = {status: sum(item["status"] == status for item in items)
              for status in ("current", "outdated", "missing")}
    candidates = (await session.execute(text("""
        SELECT n.id, n.ticker, n.title, n.provider_name, n.pub_date, n.article_url
        FROM news_articles n
        WHERE EXISTS (SELECT 1 FROM watchlist w WHERE w.ticker = n.ticker)
          AND n.pub_date >= :since AND n.pub_date <= :now AND n.title IS NOT NULL
        ORDER BY n.pub_date DESC, n.id DESC LIMIT 200
    """), {"since": (now - timedelta(hours=72)).replace(tzinfo=None),
           "now": now.replace(tzinfo=None)})).mappings().all()
    seen = set()
    per_ticker = {}
    news = []
    for row in candidates:
        reason = news_reason(row["title"])
        key = re.sub(r"\W+", " ", row["title"]).strip().casefold()
        if reason and key not in seen and per_ticker.get(row["ticker"], 0) < 2:
            seen.add(key)
            per_ticker[row["ticker"]] = per_ticker.get(row["ticker"], 0) + 1
            news.append(dict(row, reason=reason, pub_date=utc_isoformat(row["pub_date"])))
        if len(news) == 6:
            break
    fresh = sorted((item for item in items if item["status"] == "current"),
                   key=lambda item: item["created_at"], reverse=True)[:6]
    return {"as_of": utc_isoformat(now), "expected_date": expected_report_date(now).isoformat(),
            "total": len(items), "counts": counts, "items": items,
            "fresh_reports": fresh, "important_news": news}
