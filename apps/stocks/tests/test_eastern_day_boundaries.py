"""Calendar dates use Eastern midnights, while stored instants remain UTC."""

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session as ORMSession

from backend.lib.timestamps import eastern_date, eastern_day_bounds
from backend.routers import analysis_reports
from backend.models.news import NewsArticle
from backend.services import ai_worker
from backend.services.news_query_service import query_news


@pytest.mark.parametrize("day,start,end", [
    (date(2026, 10, 23), datetime(2026, 10, 23, 4), datetime(2026, 10, 24, 4)),
    (date(2026, 1, 23), datetime(2026, 1, 23, 5), datetime(2026, 1, 24, 5)),
    (date(2026, 3, 8), datetime(2026, 3, 8, 5), datetime(2026, 3, 9, 4)),
    (date(2026, 11, 1), datetime(2026, 11, 1, 4), datetime(2026, 11, 2, 5)),
])
def test_eastern_midnights_include_both_dst_transitions(day, start, end):
    assert eastern_day_bounds(day) == (start, end)


@pytest.mark.parametrize("instant,expected", [
    (datetime(2026, 10, 24, 0, 3), date(2026, 10, 23)),
    (datetime(2026, 10, 24, 3, 59, tzinfo=timezone.utc), date(2026, 10, 23)),
    (datetime(2026, 10, 24, 4, tzinfo=timezone.utc), date(2026, 10, 24)),
    (datetime(2026, 1, 24, 4, 59, tzinfo=timezone.utc), date(2026, 1, 23)),
])
def test_eastern_date_does_not_roll_over_at_utc_midnight(instant, expected):
    assert eastern_date(instant) == expected


class EmptyResult:
    def scalar(self): return 0
    def scalar_one_or_none(self): return None
    def fetchall(self): return []
    def all(self): return []


@pytest.fixture
def news_session():
    engine = create_engine("sqlite://")
    with engine.connect() as connection:
        connection.execute(text("""CREATE TABLE news_articles (
            id BIGINT PRIMARY KEY, finnhub_id TEXT, ticker TEXT, title TEXT,
            summary TEXT, provider_name TEXT, article_url TEXT, thumbnail_url TEXT,
            pub_date DATETIME, raw_json JSON, imported_at DATETIME)"""))

        class Session:
            def __init__(self): self.statements = []

            async def execute(self, statement):
                self.statements.append(statement)
                if "FROM news_articles" in str(statement):
                    return orm_session.execute(statement)
                return EmptyResult()

        with ORMSession(bind=connection) as orm_session:
            yield connection, Session()
    engine.dispose()


def add_article(connection, ident, published, imported):
    connection.execute(NewsArticle.__table__.insert().values(
        id=ident, ticker="AMD", title="Headline", pub_date=published, imported_at=imported,
    ))


@pytest.mark.asyncio
@pytest.mark.parametrize("day", [date(2026, 10, 23), date(2026, 3, 8), date(2026, 11, 1)])
async def test_news_date_filter_includes_entire_eastern_day(news_session, day):
    connection, session = news_session
    start, end = eastern_day_bounds(day)
    for ident, instant in enumerate([start - timedelta(microseconds=1), start,
                                    end - timedelta(microseconds=1), end], 1):
        add_article(connection, ident, instant, instant)
    # Null publication timestamps still fall back to ingestion time.
    add_article(connection, 5, None, end - timedelta(seconds=1))
    rows, count = await query_news(session, start_date=day.isoformat(), end_date=day.isoformat())
    assert count == 3
    assert {row.id for row in rows} == {2, 3, 5}


@pytest.mark.asyncio
async def test_activity_today_counts_the_eastern_day_after_utc_midnight(news_session, monkeypatch):
    connection, session = news_session
    bounds = eastern_day_bounds(date(2026, 10, 23))
    monkeypatch.setattr(analysis_reports, "eastern_day_bounds", lambda: bounds)
    start, end = bounds
    add_article(connection, 1, start, start)
    add_article(connection, 2, end - timedelta(microseconds=1), start)
    add_article(connection, 3, None, start)
    add_article(connection, 4, end, end)
    add_article(connection, 5, start - timedelta(seconds=1), start - timedelta(seconds=1))
    result = await analysis_reports.get_pipeline_status(session)
    assert result["news"]["total_articles"] == 5
    assert result["news"]["articles_today"] == 3
    assert {row["id"] for row in result["news"]["recent_articles"]} == {1, 2, 3}


def test_report_calendar_filters_are_eastern_and_explicit_instants_keep_offsets():
    assert analysis_reports._parse_date("2026-03-08", "from_date") == datetime(2026, 3, 8, 5)
    assert analysis_reports._parse_date("2026-03-08", "to_date") == datetime(2026, 3, 9, 4)
    assert analysis_reports._parse_date("2026-10-23T20:03:00-04:00", "from_date") == datetime(2026, 10, 24, 0, 3)
    assert analysis_reports._parse_date("2026-10-24T00:03:00Z", "from_date") == datetime(2026, 10, 24, 0, 3)


@pytest.mark.asyncio
async def test_daily_market_report_groups_by_eastern_day(monkeypatch):
    now = datetime(2026, 10, 24, 0, 3)
    monkeypatch.setattr(ai_worker, "utc_now_naive", lambda: now)
    statements = []
    added = []

    class Session:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return False
        async def execute(self, statement):
            statements.append(statement)
            if "FROM ai_company_reports" in str(statement):
                report = SimpleNamespace(asset_id=1, ticker="AMD", overall_sentiment="Bullish", confidence_score=75)
                return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [report]))
            return EmptyResult()
        def add(self, row): added.append(row)
        async def commit(self): pass

    worker = ai_worker.AIWorker(Session)
    await worker._handle_market_report(SimpleNamespace())
    daily_query = next(stmt for stmt in statements if "FROM ai_market_reports" in str(stmt))
    assert set(daily_query.compile().params.values()) == {
        datetime(2026, 10, 23, 4), datetime(2026, 10, 24, 4),
    }
    assert added[0].report_date == now  # Store the UTC instant, not Eastern wall time.
