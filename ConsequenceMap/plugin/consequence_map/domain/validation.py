"""Envelope, timestamp, closed-set and length-cap validation.

Specification sections 2.1, 8.3 and 8.5. Pure: no Hermes import, no I/O.
"""
from __future__ import annotations

import re
from typing import Any, Iterable, Mapping, Optional, Sequence, Tuple

from .enums import EnumValidationError, validate_enum

#: RFC 3339 UTC with exactly millisecond precision.
#: 2026-11-07T16:42:11.905Z
RFC3339_MILLIS = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$"
)

#: The truncation marker required by specification section 8.5.
TRUNCATION_MARKER = "…[truncated]"

#: Field-length caps from specification section 8.5.
FIELD_CAPS: Mapping[str, int] = {
    "proposal.action": 400,
    "forecast.summary": 400,
    "evidence.claim": 500,
    "evidence.source_ref": 300,
    "evidence.limitations": 300,
    "impact.target": 300,
    "impact.reason": 300,
    "forecast_risk.reason": 500,
    "unknown.question": 300,
    "unknown.why_it_matters": 300,
    "unknown.evidence_that_would_resolve": 300,
    "alternative.description": 500,
    "alternative.expected_benefit": 300,
    "alternative.impact_reduction": 300,
    "alternative.tradeoffs": 300,
    "alternative.residual_uncertainty": 300,
    "alternative.rationale": 300,
    "host_authorization.notes": 500,
    "product_decision.scope_note": 500,
    "outcome.summary": 500,
    "outcome_observation.observation": 400,
    "outcome_observation.target": 300,
    "comparison.accuracy_note": 1000,
    "comparison_item.note": 300,
    "execution_tool_call.tool_name": 300,
}


class ValidationError(ValueError):
    """Raised when a value violates the data contract."""


class TimestampError(ValidationError):
    """Raised when a timestamp is not RFC 3339 UTC with millisecond precision."""


class CapError(ValidationError):
    """Raised when a cap cannot be applied."""


# --------------------------------------------------------------------------
# Timestamps (AC-DATA-02)
# --------------------------------------------------------------------------
def validate_timestamp(value: Any, field: str = "timestamp") -> str:
    """Validate an RFC 3339 UTC timestamp with millisecond precision.

    The pattern is deliberately strict: no offsets other than `Z`, no
    missing milliseconds, no lowercase `z`, no space separator. A
    non-conforming timestamp is rejected, never coerced.
    """
    if not isinstance(value, str):
        raise TimestampError(f"{field} must be a string, got {type(value).__name__}")
    if not RFC3339_MILLIS.match(value):
        raise TimestampError(
            f"{field} must be RFC 3339 UTC with millisecond precision "
            f"(YYYY-MM-DDTHH:MM:SS.sssZ), got {value!r}"
        )
    # Calendar validity: the regex accepts 2026-02-31, datetime does not.
    from datetime import datetime

    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ")
    except ValueError:
        raise TimestampError(f"{field} is not a valid calendar timestamp: {value!r}") from None
    return value


def now_timestamp() -> str:
    """The current UTC instant as an RFC 3339 millisecond-precision string."""
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + f"{datetime.now(timezone.utc).microsecond // 1000:03d}Z"


# --------------------------------------------------------------------------
# Envelope (AC-DATA-01)
# --------------------------------------------------------------------------
def validate_envelope(envelope: Any) -> Mapping[str, Any]:
    """Validate the root envelope of specification section 2.12.

    Every envelope carries `schema_version = 1`. An unknown MAJOR version
    is rejected; unknown MINOR fields are ignored.

    "Major" is the leading component: `1` is major 1. A version of `1` is
    accepted, `2` is rejected (unknown major), and `0` is rejected (older
    major). Extra keys in the envelope are ignored, not rejected.
    """
    if not isinstance(envelope, Mapping):
        raise ValidationError(f"envelope must be a mapping, got {type(envelope).__name__}")
    if "schema_version" not in envelope:
        raise ValidationError("envelope is missing schema_version")
    version = envelope["schema_version"]
    if not isinstance(version, int) or isinstance(version, bool):
        raise ValidationError(f"schema_version must be an integer, got {version!r}")
    if version != 1:
        raise ValidationError(
            f"unknown major schema_version {version}; this build supports version 1"
        )
    return envelope


# --------------------------------------------------------------------------
# Length caps (AC-PRIV-19)
# --------------------------------------------------------------------------
def cap_text(value: Optional[str], cap: int, field: str = "field") -> Tuple[str, bool]:
    """Truncate `value` at `cap` characters with the section 8.5 marker.

    Returns `(text, truncated)`. The marker is appended after truncation,
    so the result is `cap` characters long in total - the cap is a bound
    on the stored value, not on the payload before the marker.
    """
    if value is None:
        return "", False
    if not isinstance(value, str):
        raise ValidationError(f"{field} must be a string, got {type(value).__name__}")
    if len(value) <= cap:
        return value, False
    keep = max(0, cap - len(TRUNCATION_MARKER))
    return value[:keep] + TRUNCATION_MARKER, True


def validate_cap(value: Optional[str], field: str) -> Tuple[str, bool]:
    """Apply the documented cap for `field` (section 8.5)."""
    if field not in FIELD_CAPS:
        raise CapError(f"no documented cap for {field}")
    return cap_text(value, FIELD_CAPS[field], field)


# --------------------------------------------------------------------------
# Closed sets (AC-DATA-03)
# --------------------------------------------------------------------------
def validate_closed_set(value: Any, allowed: Iterable[str], field: str) -> str:
    """Validate `value` against an explicit closed set."""
    allowed = tuple(allowed)
    if value not in allowed:
        raise ValidationError(
            f"{field} must be one of {', '.join(allowed)}; got {value!r}"
        )
    return value


def validate_enum_field(name: str, value: Any, field: Optional[str] = None) -> str:
    """Validate `value` against a named closed enumeration."""
    try:
        return validate_enum(name, value)
    except EnumValidationError as exc:
        raise ValidationError(f"{field or name}: {exc}") from None


# --------------------------------------------------------------------------
# Booleans and identifiers
# --------------------------------------------------------------------------
def validate_bool(value: Any, field: str) -> bool:
    """Validate a strict boolean - `0`/`1` are accepted, `"true"` is not."""
    if isinstance(value, bool):
        return value
    if value in (0, 1):
        return bool(value)
    raise ValidationError(f"{field} must be a boolean, got {value!r}")


def validate_identifier(value: Any, prefix: str, field: str) -> str:
    """Validate an opaque identifier with a stable prefix."""
    if not isinstance(value, str):
        raise ValidationError(f"{field} must be a string, got {type(value).__name__}")
    if not value.startswith(prefix):
        raise ValidationError(f"{field} must start with {prefix!r}, got {value!r}")
    return value


def require_fields(record: Any, required: Sequence[str], entity: str) -> None:
    """Raise when any of `required` is missing or `None` in `record`.

    Accepts a mapping or a dataclass instance - the domain records are
    dataclasses, so the accessor is chosen accordingly.
    """
    if isinstance(record, Mapping):
        get = record.get
    else:
        get = lambda name: getattr(record, name, None)  # noqa: E731
    missing = [name for name in required if get(name) is None]
    if missing:
        raise ValidationError(
            f"{entity} is missing mandatory field(s): {', '.join(sorted(missing))}"
        )
