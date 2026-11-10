"""Result classification.

Five verdicts, and a failure taxonomy that decides whether a repair may be
attempted. The verdict is a fact about a run; the kind is a fact about the
defect. The two are deliberately separate.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

#: The five verdicts. Only PASS asserts that a check ran and held.
PASS = "PASS"
FAIL = "FAIL"
WARNING = "WARNING"
NOT_VERIFIED = "NOT_VERIFIED"
BLOCKED = "BLOCKED"

VERDICTS = (PASS, FAIL, WARNING, NOT_VERIFIED, BLOCKED)

#: Failure kinds. A kind, not a severity, decides repair eligibility.
IMPLEMENTATION = "IMPLEMENTATION"
TEST = "TEST"
DOCUMENTATION = "DOCUMENTATION"
NORMATIVE = "NORMATIVE"
DECISION = "DECISION"

KINDS = (IMPLEMENTATION, TEST, DOCUMENTATION, NORMATIVE, DECISION)

#: Kinds a repair may never touch.
NEVER_AUTO_REPAIR = frozenset({NORMATIVE, DECISION, TEST})


@dataclass
class CheckResult:
    """The outcome of one check."""

    name: str
    verdict: str
    kind: Optional[str] = None
    detail: str = ""
    repairable: bool = False
    evidence: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "verdict": self.verdict,
            "kind": self.kind,
            "detail": self.detail,
            "repairable": self.repairable,
            "evidence": self.evidence,
        }


@dataclass
class CycleResult:
    """The outcome of one Guardian cycle."""

    checks: List[CheckResult] = field(default_factory=list)
    repairs: List[dict] = field(default_factory=list)
    stopped_reason: Optional[str] = None

    def add(self, result: CheckResult) -> CheckResult:
        self.checks.append(result)
        return result

    def by_verdict(self, verdict: str) -> List[CheckResult]:
        return [c for c in self.checks if c.verdict == verdict]

    @property
    def failed(self) -> List[CheckResult]:
        return self.by_verdict(FAIL)

    @property
    def unverified(self) -> List[CheckResult]:
        return self.by_verdict(NOT_VERIFIED)

    @property
    def blocked(self) -> List[CheckResult]:
        return self.by_verdict(BLOCKED)

    @property
    def warnings(self) -> List[CheckResult]:
        return self.by_verdict(WARNING)

    @property
    def worst(self) -> str:
        """The verdict that dominates the cycle.

        FAIL dominates NOT_VERIFIED, which dominates BLOCKED, which
        dominates WARNING, which dominates PASS. A cycle with any FAIL is
        never reported as PASS.
        """
        for verdict in (FAIL, NOT_VERIFIED, BLOCKED, WARNING):
            if self.by_verdict(verdict):
                return verdict
        return PASS

    def to_dict(self) -> dict:
        return {
            "worst_verdict": self.worst,
            "checks": [c.to_dict() for c in self.checks],
            "repairs": self.repairs,
            "stopped_reason": self.stopped_reason,
        }


def overall(checks: List[CheckResult]) -> str:
    """The dominating verdict of a list of check results."""
    return CycleResult(checks=list(checks)).worst
