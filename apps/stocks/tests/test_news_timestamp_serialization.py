from datetime import datetime, timedelta, timezone

from backend.lib.timestamps import utc_isoformat
from backend.models.news_schemas import NewsArticleOut


def test_news_article_output_marks_naive_database_timestamps_as_utc():
    payload = NewsArticleOut(
        id=1,
        pub_date=datetime(2026, 8, 14, 18, 0),
        imported_at=datetime(2026, 8, 14, 18, 5, 12, 345678),
    ).model_dump(mode="json")

    assert payload["pub_date"] == "2026-08-14T18:00:00Z"
    assert payload["imported_at"] == "2026-08-14T18:05:12.345678Z"


def test_utc_isoformat_normalizes_aware_values_to_utc():
    eastern_summer = timezone(-timedelta(hours=4))

    assert utc_isoformat(datetime(2026, 8, 14, 14, 0, tzinfo=eastern_summer)) == (
        "2026-08-14T18:00:00Z"
    )
    assert utc_isoformat(None) is None
