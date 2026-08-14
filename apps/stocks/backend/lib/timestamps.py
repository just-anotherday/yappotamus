"""Helpers for serializing database timestamps at API boundaries."""

from datetime import datetime, timezone
from typing import overload


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
