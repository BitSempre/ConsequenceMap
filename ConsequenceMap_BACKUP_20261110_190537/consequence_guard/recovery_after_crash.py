"""Recovery after a crash, and the honest answer about what happened.

The problem
-----------
An operation passes through several states, and the process can die
between any two of them. The dangerous window is between
``EXECUTION_STARTED`` and ``COMPLETED``: the handler may have already
deleted a file when the process dies.

Three wrong answers are available, and all three are tempting:

1. **Assume it did not happen.** Then a retry applies the approved
   effect a second time. A "delete one report" becomes "delete two".
2. **Assume it did happen.** Then a failed operation is reported as a
   success, and the human is told something untrue.
3. **Retry automatically.** Same problem as (1), but without a human
   in the loop.

The only defensible answer is ``OUTCOME_UNKNOWN``: the effect may or
may not have happened, the system says so, and it does NOT retry.

What recovery does
------------------
On startup the service looks for operations in a non-terminal state
and classifies them:

- ``RECEIVED`` or ``VALIDATED`` - nothing ran. The operation can be
  discarded, or re-proposed. The authorisation was not consumed, so it
  may still be valid.
- ``CONSUMED`` - the authorisation was spent but the handler did not
  start. The effect definitely did not happen. The operation may be
  re-proposed, but the authorisation is spent and would be refused -
  so a NEW authorisation is needed.
- ``EXECUTION_STARTED`` - **the effect may or may not have happened.**
  The state becomes ``OUTCOME_UNKNOWN`` and waits for a human.
- ``OUTCOME_UNKNOWN`` - already known to be uncertain.

The rule that matters
---------------------
**An operation whose outcome is unknown is never retried
automatically.** Not by the service, not by a recovery routine, not by
a watchdog. A human decides, and the decision is audited.

This is why the store keeps an operation state rather than only a
spent-set. A spent-set can answer "was this authorisation used?" but
it cannot answer "what happened to the operation that used it?".
"""
from __future__ import annotations

from typing import Any, Mapping, Optional, Sequence

from .store import GuardStore, OperationState, StoreError, StoreUnavailable

__all__ = [
    "RecoveryReport",
    "RecoveredOperation",
    "classify_incomplete_operations",
    "recover_operations",
]


class RecoveredOperation:
    """One operation found in a non-terminal state at startup."""

    def __init__(
        self,
        operation_id: str,
        previous_state: str,
        recovered_state: str,
        reason: str,
    ) -> None:
        self.operation_id = operation_id
        self.previous_state = previous_state
        self.recovered_state = recovered_state
        self.reason = reason

    def as_dict(self) -> Mapping[str, Any]:
        return {
            "operation_id": self.operation_id,
            "previous_state": self.previous_state,
            "recovered_state": self.recovered_state,
            "reason": self.reason,
        }

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "<RecoveredOperation %s %s -> %s>" % (
            self.operation_id, self.previous_state, self.recovered_state
        )


class RecoveryReport:
    """What recovery found."""

    def __init__(self, recovered: Sequence[RecoveredOperation]) -> None:
        self.recovered = list(recovered)

    @property
    def uncertain(self) -> list:
        """The operations whose outcome is unknown."""
        return [
            operation
            for operation in self.recovered
            if operation.recovered_state == OperationState.OUTCOME_UNKNOWN
        ]

    @property
    def count(self) -> int:
        return len(self.recovered)

    def as_dict(self) -> Mapping[str, Any]:
        return {
            "recovered": [operation.as_dict() for operation in self.recovered],
            "uncertain_count": len(self.uncertain),
        }

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "<RecoveryReport %d recovered, %d uncertain>" % (
            self.count, len(self.uncertain)
        )


def classify_incomplete_operations(store: GuardStore) -> list:
    """Every operation in a non-terminal state."""
    found = []
    for state in (
        OperationState.RECEIVED,
        OperationState.VALIDATED,
        OperationState.CONSUMED,
        OperationState.EXECUTION_STARTED,
    ):
        found.extend(store.operations_in_state(state))
    return found


def recover_operations(store: GuardStore, now: Optional[str] = None) -> RecoveryReport:
    """Classify the operations left behind by a crash.

    This function NEVER retries an operation and NEVER re-runs a
    handler. It only classifies and records. The reason it can be that
    conservative is that it has no handler access at all.
    """
    from consequence_map.core.timeutil import format_rfc3339, now_utc

    moment = now or format_rfc3339(now_utc())
    recovered = []

    for entry in classify_incomplete_operations(store):
        previous = entry["state"]
        if previous in (OperationState.RECEIVED, OperationState.VALIDATED):
            # Nothing ran. The operation never started.
            new_state = OperationState.FAILED
            reason = (
                "the operation was interrupted before it started; its "
                "authorisation was not spent, so it may be proposed again"
            )
        elif previous == OperationState.CONSUMED:
            # The authorisation was spent but the handler did not start.
            new_state = OperationState.FAILED
            reason = (
                "the authorisation was consumed but the operation did not "
                "start; the effect did not happen, and a NEW authorisation "
                "is needed because the old one is spent"
            )
        else:  # EXECUTION_STARTED
            # The handler ran, or began to. The effect may have happened.
            new_state = OperationState.OUTCOME_UNKNOWN
            reason = (
                "the process stopped while the operation was running; the "
                "effect may or may not have happened and must be checked "
                "by a human before anything is retried"
            )

        try:
            store.record_operation(
                operation_id=entry["operation_id"],
                state=new_state,
                request_id="",
                authorization_id="",
                operation=entry["operation"],
                proposal_hash="",
                now=moment,
                detail=reason,
            )
            store.append_audit(
                "guard.recovery.classified",
                {
                    "operation_id": entry["operation_id"],
                    "previous_state": previous,
                    "recovered_state": new_state,
                    "reason": reason,
                },
                moment,
            )
        except (StoreUnavailable, StoreError):
            # The classification could not be recorded. The operation
            # stays where it was, which is itself ambiguous - but the
            # store is broken and there is nothing better to do than
            # fail loudly rather than pretend.
            raise

        recovered.append(
            RecoveredOperation(entry["operation_id"], previous, new_state, reason)
        )

    return RecoveryReport(recovered)
