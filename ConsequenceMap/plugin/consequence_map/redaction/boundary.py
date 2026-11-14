"""Redaction and length caps at the write boundary.

PR-1: every field marked redacted passes through the redactor before it
is written. PR-2: redaction is applied INSIDE the storage layer, beneath
every write path - which is why `storage/repository.py` calls into this
module, and why nothing else may write to the database directly.

The redactor FAILS CLOSED. If it raises, the write fails with
`REDACTION_UNAVAILABLE` and the unredacted value is never persisted
(AC-PRIV-02).

The redactor is INJECTABLE. The production default calls the host's
`agent.redact.redact_sensitive_text`; the test suite injects a deterministic
local implementation so the suite never needs Hermes on the path.
"""

from __future__ import annotations

import re
from typing import Callable, Dict, Optional, Tuple

from ..domain.validation import FIELD_CAPS, TRUNCATION_MARKER

#: The error code raised when the redactor fails (PR-1 fails closed).
REDACTION_UNAVAILABLE = "REDACTION_UNAVAILABLE"


class RedactionUnavailable(RuntimeError):
    """Raised when the redactor fails. The write MUST NOT proceed."""

    def __init__(self, detail: str = "") -> None:
        super().__init__(REDACTION_UNAVAILABLE if not detail else f"{REDACTION_UNAVAILABLE}: {detail}")
        self.code = REDACTION_UNAVAILABLE


#: The redactor callable: text in, redacted text out.
Redactor = Callable[[str], str]

_REDACTOR: Optional[Redactor] = None

#: Patterns the plugin adds. Additive only - they can never weaken a
#: built-in pattern (PR-3).
_ADDITIONAL_PATTERNS: Tuple[re.Pattern, ...] = (
    re.compile(r"(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{16,}"),  # GitHub tokens
    re.compile(r"sk-[A-Za-z0-9]{20,}"),  # OpenAI-style keys
    re.compile(r"AKIA[0-9A-Z]{16}"),  # AWS access key ids
    re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),  # Slack tokens
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),  # private keys
)

#: The built-in secret shapes the plugin sweeps for, independent of the host.
#: The patterns are built with explicit character classes rather than
#: the shorthand escapes, because a word boundary written as a literal
#: backslash-b inside a raw string is two characters, not a boundary -
#: and the resulting pattern silently matches nothing.
_BUILTIN_PATTERNS: Tuple[re.Pattern, ...] = (
    re.compile(r"(?i)(?:api[_-]?key|secret|password|passwd|token)[ \t]*[:=][ \t]*\S+"),
    re.compile(r"(?i)Bearer[ \t]+[A-Za-z0-9._-]{10,}"),
    re.compile(r"(?i)(?:aws|azure|gcp)[_-]?(?:secret|access)[_-]?key[ \t]*[:=][ \t]*\S+"),
)


def set_redactor(redactor: Optional[Redactor]) -> None:
    """Install (or clear) the redactor. The test suite injects one."""
    global _REDACTOR
    _REDACTOR = redactor


def get_redactor() -> Redactor:
    """The active redactor."""
    return _REDACTOR if _REDACTOR is not None else host_redactor


def host_redactor(text: str) -> str:
    """The production redactor: the host's `redact_sensitive_text`.

    PR-1 names `agent.redact.redact_sensitive_text(text)`. The import is
    inside the function so importing this module imports no Hermes code.
    """
    from agent.redact import redact_sensitive_text  # noqa: PLC0415 - deliberate lazy import

    return redact_sensitive_text(text)


def default_redactor(text: str) -> str:
    """A deterministic local redactor, used by the test suite.

    It applies the built-in patterns and the additive plugin patterns.
    It is NOT the production redactor - the production redactor is the
    host's - but it lets the suite run without Hermes on the path.
    """
    result = text
    for pattern in _BUILTIN_PATTERNS + _ADDITIONAL_PATTERNS:
        result = pattern.sub("[REDACTED]", result)
    return result


def redact_for_storage(text: Optional[str], *, field: str = "field") -> str:
    """Redact `text` for persistence.

    Fails closed: if the redactor raises, `RedactionUnavailable` is
    raised and the caller MUST NOT persist the original (AC-PRIV-02).
    """
    if text is None:
        return ""
    if not isinstance(text, str):
        raise RedactionUnavailable(f"{field} must be a string")
    redactor = get_redactor()
    try:
        return redactor(text)
    except Exception as exc:  # noqa: BLE001 - the whole point is to fail closed
        raise RedactionUnavailable(f"{field}: {exc}") from exc


def apply_cap(text: Optional[str], field: str) -> Tuple[str, bool]:
    """Apply the documented cap for `field` and report the truncation."""
    from ..domain.validation import cap_text

    if field not in FIELD_CAPS:
        raise KeyError(f"no documented cap for {field}")
    return cap_text(text, FIELD_CAPS[field], field)


def redact_and_cap(text: Optional[str], field: str) -> Tuple[str, bool, bool]:
    """Redact then cap. Returns `(text, redacted_changed, truncated)`."""
    original = text or ""
    redacted = redact_for_storage(original, field=field)
    changed = redacted != original
    capped, truncated = apply_cap(redacted, field)
    return capped, changed, truncated


#: The fields that must be redacted, from specification section 8.1a.
#: The repository uses this to decide what passes through the boundary.
REDACTED_FIELDS: Tuple[str, ...] = (
    "proposal.action",
    "forecast.summary",
    "evidence.claim",
    "evidence.source_ref",
    "evidence.limitations",
    "impact.target",
    "impact.reason",
    "forecast_risk.reason",
    "unknown.question",
    "unknown.why_it_matters",
    "unknown.evidence_that_would_resolve",
    "alternative.description",
    "alternative.expected_benefit",
    "alternative.impact_reduction",
    "alternative.tradeoffs",
    "alternative.residual_uncertainty",
    "alternative.rationale",
    "host_authorization.notes",
    "product_decision.scope_note",
    "outcome.summary",
    "outcome_observation.observation",
    "outcome_observation.target",
    "comparison.accuracy_note",
    "comparison_item.note",
)
