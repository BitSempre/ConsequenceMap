"""Strict RFC 3339 time handling.

The authorization protocol compares timestamps, so the comparison must not
depend on a lenient parser. Python's ``datetime.fromisoformat`` accepts
several forms that RFC 3339 does not, and it accepts a naive timestamp
with no offset - which would silently be interpreted in the local zone.

Every timestamp handled here is UTC with exactly millisecond precision and
an explicit ``Z``, matching the convention already used by the forecast
layer (``domain/validation.py``).
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional

__all__ = [
    "TimeError",
    "RFC3339_MILLIS",
    "parse_rfc3339",
    "format_rfc3339",
    "now_utc",
]


class TimeError(ValueError):
    """Raised when a timestamp is not RFC 3339 UTC with millisecond precision."""


#: 2026-11-09T15:42:11.905Z
RFC3339_MILLIS = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})\.(\d{3})Z$"
)


def parse_rfc3339(text: str) -> datetime:
    """Parse a strict RFC 3339 UTC timestamp with millisecond precision."""
    if not isinstance(text, str):
        raise TimeError("timestamp must be a string, got %r" % (type(text).__name__,))
    match = RFC3339_MILLIS.match(text)
    if match is None:
        raise TimeError(
            "timestamp %r is not RFC 3339 UTC with millisecond precision "
            "(expected YYYY-MM-DDTHH:MM:SS.sssZ)" % (text,)
        )
    year, month, day, hour, minute, second, millis = (int(g) for g in match.groups())
    try:
        return datetime(
            year, month, day, hour, minute, second, millis * 1000, tzinfo=timezone.utc
        )
    except ValueError as exc:
        raise TimeError("timestamp %r is not a valid instant: %s" % (text, exc))


def format_rfc3339(moment: datetime) -> str:
    """Format a datetime as RFC 3339 UTC with millisecond precision."""
    if moment.tzinfo is None:
        raise TimeError("refusing to format a naive datetime")
    moment = moment.astimezone(timezone.utc)
    return "%04d-%02d-%02dT%02d:%02d:%02d.%03dZ" % (
        moment.year, moment.month, moment.day,
        moment.hour, moment.minute, moment.second,
        moment.microsecond // 1000,
    )


def now_utc() -> datetime:
    """Return the current UTC time, truncated to millisecond precision."""
    moment = datetime.now(timezone.utc)
    return moment.replace(microsecond=(moment.microsecond // 1000) * 1000)
