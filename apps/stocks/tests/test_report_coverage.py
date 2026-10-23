from datetime import datetime, timezone

import pytest

from backend.services.report_coverage_service import coverage_status, expected_report_date, news_reason


@pytest.mark.parametrize("instant,expected", [
    ("2026-10-21T19:00:00+00:00", "2026-10-20"),
    ("2026-10-22T00:30:00+00:00", "2026-10-21"),
    ("2026-10-24T18:00:00+00:00", "2026-10-23"),
    ("2026-10-26T14:00:00+00:00", "2026-10-23"),
    ("2026-11-03T01:29:00+00:00", "2026-10-30"),
    ("2026-11-03T01:30:00+00:00", "2026-11-02"),
])
def test_expected_day_handles_evenings_weekends_and_dst(instant, expected):
    assert expected_report_date(datetime.fromisoformat(instant)).isoformat() == expected


def test_coverage_uses_eastern_report_date_and_distinguishes_missing():
    now = datetime(2026, 10, 21, 19, tzinfo=timezone.utc)
    assert coverage_status(None, now) == "missing"
    assert coverage_status(datetime(2026, 10, 21, 0, 43), now) == "current"
    assert coverage_status(datetime(2026, 10, 20, 0, 43), now) == "outdated"


def test_news_labels_are_explicit_event_matches():
    assert news_reason("Company raises earnings guidance") == "Earnings"
    assert news_reason("Regulator opens antitrust investigation") == "Regulatory"
    assert news_reason("Shares rise today") is None
