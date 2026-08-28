"""Helpers for serializing database timestamps at API boundaries."""

from datetime import datetime, timezone
from typing import overload


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
