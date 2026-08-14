from datetime import datetime

from backend.models.report_schemas import AnalysisReportDetail, ReportSummaryOut


def test_report_summary_marks_naive_created_at_as_utc():
    payload = ReportSummaryOut(
        id=1,
        report_number=1,
        ticker="AAPL",
        overall_sentiment="Neutral",
        confidence_score=50,
        articles_count=2,
        model_used="test-model",
        prompt_version="2.0",
        created_at=datetime(2026, 8, 14, 18, 0),
    ).model_dump(mode="json")

    assert payload["created_at"] == "2026-08-14T18:00:00Z"


def test_report_detail_marks_naive_created_at_as_utc():
    payload = AnalysisReportDetail(
        id=1,
        ticker="AAPL",
        report_data={},
        articles_count=2,
        model_used="test-model",
        prompt_version="2.0",
        created_at=datetime(2026, 1, 14, 18, 0),
    ).model_dump(mode="json")

    assert payload["created_at"] == "2026-01-14T18:00:00Z"
