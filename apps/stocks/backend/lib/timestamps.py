"""UTC database instants, Eastern calendar boundaries, and API serialization."""

from datetime import date, datetime, time, timedelta, timezone
from typing import overload
from zoneinfo import ZoneInfo

EASTERN = ZoneInfo("America/New_York")


def eastern_date(now: datetime | None = None) -> date:
    """Return the app's calendar date; legacy naive instants represent UTC."""
    instant = now if now is not None else datetime.now(timezone.utc)
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    return instant.astimezone(EASTERN).date()


def eastern_day_bounds(day: date | None = None) -> tuple[datetime, datetime]:
    """Eastern midnight-to-midnight as a half-open UTC-naive DB range.

    Convert each midnight separately so DST days correctly span 23 or 25 hours.
    Stored instants remain UTC; only calendar-day interpretation uses Eastern.
    """
    day = day if day is not None else eastern_date()
    return tuple(
        datetime.combine(value, time.min, tzinfo=EASTERN)
        .astimezone(timezone.utc).replace(tzinfo=None)
        for value in (day, day + timedelta(days=1))
    )


def utc_now_naive() -> datetime:
    """Return the current UTC wall clock for legacy UTC-naive DB columns.

    The value is intentionally naive because existing report tables use
    ``TIMESTAMP WITHOUT TIME ZONE``. Its UTC semantics are restored explicitly
    by :func:`utc_isoformat` at API boundaries.
    """

    return datetime.now(timezone.utc).replace(tzinfo=None)


@overload
def utc_isoformat(value: datetime) -> str:
    ...


@overload
def utc_isoformat(value: None) -> None:
    ...


def utc_isoformat(value: datetime | None) -> str | None:
    """Serialize a UTC instant with an explicit timezone designator.

    Legacy database columns store UTC as ``TIMESTAMP WITHOUT TIME ZONE``.
    Attaching UTC here preserves that storage contract while preventing API
    consumers from interpreting the value as local wall-clock time.
    """

    if value is None:
        return None

    normalized = (
        value.replace(tzinfo=timezone.utc)
        if value.tzinfo is None
        else value.astimezone(timezone.utc)
    )
    return normalized.isoformat().replace("+00:00", "Z")
