"""The 18 closed enumerations of specification section 2.2.

Every enumeration is CLOSED: an unknown value is a validation error, never
a silent default (specification section 2.1, AC-DATA-03).

13 shared enumerations plus 5 authorization enumerations = 18.
"""
from __future__ import annotations

from enum import Enum
from typing import Dict, Tuple

class EVIDENCE_CLASS(str, Enum):
    VERIFIED_FACT = "VERIFIED_FACT"
    INFERENCE = "INFERENCE"
    UNKNOWN = "UNKNOWN"

class CONFIDENCE(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"

class SEVERITY(str, Enum):
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

class REVERSIBILITY(str, Enum):
    EASY = "EASY"
    CONDITIONAL = "CONDITIONAL"
    DIFFICULT = "DIFFICULT"
    IRREVERSIBLE = "IRREVERSIBLE"

class RELATION(str, Enum):
    DIRECT = "DIRECT"
    DEPENDENT = "DEPENDENT"
    INFERRED = "INFERRED"
    UNKNOWN_RELATION = "UNKNOWN_RELATION"

class IMPACT_CLASS(str, Enum):
    FILES = "FILES"
    APIS = "APIS"
    DEPENDENCIES = "DEPENDENCIES"
    CONFIG_SECRETS = "CONFIG_SECRETS"
    DATA = "DATA"
    SERVICES = "SERVICES"
    NETWORK = "NETWORK"
    USERS = "USERS"
    COST = "COST"
    SECURITY = "SECURITY"

class TARGET_KIND(str, Enum):
    FILESYSTEM = "FILESYSTEM"
    API = "API"
    DEPENDENCY = "DEPENDENCY"
    CONFIG = "CONFIG"
    SERVICE = "SERVICE"
    NETWORK = "NETWORK"
    DATA = "DATA"
    EXTERNAL_SYSTEM = "EXTERNAL_SYSTEM"
    UNKNOWN = "UNKNOWN"

class OBSERVED_OUTCOME(str, Enum):
    OBSERVED = "OBSERVED"
    NOT_OBSERVED = "NOT_OBSERVED"
    UNEXPECTED = "UNEXPECTED"
    NOT_VERIFIABLE = "NOT_VERIFIABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"

class VERIFICATION_METHOD(str, Enum):
    DETERMINISTIC_CHECK = "DETERMINISTIC_CHECK"
    FILE_DIFF = "FILE_DIFF"
    TOOL_OBSERVATION = "TOOL_OBSERVATION"
    MANUAL = "MANUAL"
    UNVERIFIED = "UNVERIFIED"

class COMPARISON_VERDICT(str, Enum):
    ALIGNED = "ALIGNED"
    PARTIALLY_ALIGNED = "PARTIALLY_ALIGNED"
    DIVERGED = "DIVERGED"
    INCONCLUSIVE = "INCONCLUSIVE"

class SOURCE_KIND(str, Enum):
    FILESYSTEM = "FILESYSTEM"
    TOOL_OUTPUT = "TOOL_OUTPUT"
    MANIFEST = "MANIFEST"
    SOURCE_CODE = "SOURCE_CODE"
    DOCUMENTATION = "DOCUMENTATION"
    MODEL_INFERENCE = "MODEL_INFERENCE"
    ABSENCE_OF_EVIDENCE = "ABSENCE_OF_EVIDENCE"

class COMPARISON_ORIGIN(str, Enum):
    PREDICTED = "PREDICTED"
    UNEXPECTED = "UNEXPECTED"

class ALTERNATIVE_DISPOSITION(str, Enum):
    ADOPTED = "ADOPTED"
    REJECTED = "REJECTED"
    NOT_EVALUATED = "NOT_EVALUATED"

class AUTHORIZATION_STATE(str, Enum):
    HUMAN_APPROVED = "HUMAN_APPROVED"
    HUMAN_REJECTED = "HUMAN_REJECTED"
    AUTOMATICALLY_ALLOWED = "AUTOMATICALLY_ALLOWED"
    AUTOMATICALLY_DENIED = "AUTOMATICALLY_DENIED"
    APPROVAL_NOT_REQUIRED = "APPROVAL_NOT_REQUIRED"
    APPROVAL_NOT_OBSERVED = "APPROVAL_NOT_OBSERVED"
    APPROVAL_TIMEOUT = "APPROVAL_TIMEOUT"
    APPROVAL_CANCELLED = "APPROVAL_CANCELLED"
    PENDING = "PENDING"
    UNKNOWN = "UNKNOWN"
    GUARDIAN_APPROVED = "GUARDIAN_APPROVED"
    GUARDIAN_REJECTED = "GUARDIAN_REJECTED"
    TRANSPORT_FAILED = "TRANSPORT_FAILED"

class AUTHORIZATION_PROVENANCE(str, Enum):
    HOST_APPROVAL_HOOK = "HOST_APPROVAL_HOOK"
    HOST_TOOL_FATE = "HOST_TOOL_FATE"
    NOT_APPLICABLE = "NOT_APPLICABLE"

class AUTHORIZATION_REASON(str, Enum):
    ALLOWLIST = "ALLOWLIST"
    YOLO_OR_MODE_OFF = "YOLO_OR_MODE_OFF"
    SINGLE_QUERY_APPROVE = "SINGLE_QUERY_APPROVE"
    UNATTENDED_APPROVE = "UNATTENDED_APPROVE"
    UNATTENDED_DENY = "UNATTENDED_DENY"
    NO_HUMAN_PRESENT = "NO_HUMAN_PRESENT"
    GATEWAY_NOTIFY_FAILED = "GATEWAY_NOTIFY_FAILED"
    GATE_ERROR = "GATE_ERROR"
    GUARDIAN_VERDICT = "GUARDIAN_VERDICT"
    UNKNOWN = "UNKNOWN"

class AUTHORIZED_BY(str, Enum):
    USER = "USER"
    GUARDIAN_LLM = "GUARDIAN_LLM"
    SYSTEM = "SYSTEM"
    NONE = "NONE"

class PRODUCT_DECISION_STATE(str, Enum):
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    ALTERNATIVE_REQUESTED = "ALTERNATIVE_REQUESTED"
    NOT_ASKED = "NOT_ASKED"
    SUPERSEDED = "SUPERSEDED"

#: Every enumeration in the specification, keyed by name. The validator
#: asserts this mapping has exactly 18 entries.
ENUMS: Dict[str, type] = {
    "EVIDENCE_CLASS": EVIDENCE_CLASS,
    "CONFIDENCE": CONFIDENCE,
    "SEVERITY": SEVERITY,
    "REVERSIBILITY": REVERSIBILITY,
    "RELATION": RELATION,
    "IMPACT_CLASS": IMPACT_CLASS,
    "TARGET_KIND": TARGET_KIND,
    "OBSERVED_OUTCOME": OBSERVED_OUTCOME,
    "VERIFICATION_METHOD": VERIFICATION_METHOD,
    "COMPARISON_VERDICT": COMPARISON_VERDICT,
    "SOURCE_KIND": SOURCE_KIND,
    "COMPARISON_ORIGIN": COMPARISON_ORIGIN,
    "ALTERNATIVE_DISPOSITION": ALTERNATIVE_DISPOSITION,
    "AUTHORIZATION_STATE": AUTHORIZATION_STATE,
    "AUTHORIZATION_PROVENANCE": AUTHORIZATION_PROVENANCE,
    "AUTHORIZATION_REASON": AUTHORIZATION_REASON,
    "AUTHORIZED_BY": AUTHORIZED_BY,
    "PRODUCT_DECISION_STATE": PRODUCT_DECISION_STATE,
}

#: The 13 shared (non-authorization) enumerations.
SHARED_ENUM_NAMES: Tuple[str, ...] = (
    "EVIDENCE_CLASS",
    "CONFIDENCE",
    "SEVERITY",
    "REVERSIBILITY",
    "RELATION",
    "IMPACT_CLASS",
    "TARGET_KIND",
    "OBSERVED_OUTCOME",
    "VERIFICATION_METHOD",
    "COMPARISON_VERDICT",
    "SOURCE_KIND",
    "COMPARISON_ORIGIN",
    "ALTERNATIVE_DISPOSITION",
)

#: The 5 authorization enumerations.
AUTHORIZATION_ENUM_NAMES: Tuple[str, ...] = (
    "AUTHORIZATION_STATE",
    "AUTHORIZATION_PROVENANCE",
    "AUTHORIZATION_REASON",
    "AUTHORIZED_BY",
    "PRODUCT_DECISION_STATE",
)

#: Every member value of every enumeration, as plain strings.
ALL_VALUES: Dict[str, Tuple[str, ...]] = {
    name: tuple(m.value for m in enum_cls)
    for name, enum_cls in ENUMS.items()
}


class EnumValidationError(ValueError):
    """Raised when a value is not a member of a closed enumeration."""


def validate_enum(name: str, value: str) -> str:
    """Validate `value` against the closed enumeration `name`.

    Returns the value unchanged when it is a member. Raises
    `EnumValidationError` otherwise - there is no silent default and no
    case-folding (AC-DATA-03).
    """
    try:
        enum_cls = ENUMS[name]
    except KeyError:
        raise EnumValidationError(f"unknown enumeration: {name}") from None
    for member in enum_cls:
        if member.value == value:
            return member.value
    allowed = ", ".join(m.value for m in enum_cls)
    raise EnumValidationError(
        f"{name} is a closed enumeration; {value!r} is not a member (allowed: {allowed})"
    )


def is_valid_enum(name: str, value: str) -> bool:
    """True when `value` is a member of the closed enumeration `name`."""
    try:
        validate_enum(name, value)
    except EnumValidationError:
        return False
    return True
