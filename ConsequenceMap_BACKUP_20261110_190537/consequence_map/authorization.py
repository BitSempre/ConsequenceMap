"""The authorization state machine.

Specification section 5, proposal section 5.

Thirteen states, and the rule that matters most: **no state is
reachable except through a real observation.** A state the plugin
infers is weaker than a state it observed, and the plugin says so
with ``UNKNOWN`` rather than inventing an approval.

The domain already defines the thirteen values, the provenance, the
reason and the author. This module derives the state from a host
event; it does not define a second vocabulary.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Optional

from .domain.enums import (
    AUTHORIZATION_PROVENANCE,
    AUTHORIZATION_REASON,
    AUTHORIZATION_STATE,
    AUTHORIZED_BY,
)

#: The host's approval choices, as the runtime emits them. The
#: distinction matters: a timeout is not a refusal, and a cancelled
#: prompt is not an answer.
CHOICE_APPROVE = "approve"
CHOICE_DENY = "deny"
CHOICE_TIMEOUT = "timeout"
CHOICE_CANCELLED = "cancelled"
CHOICE_NOTIFY_FAILED = "notify_failed"
CHOICE_SMART_APPROVE = "smart_approve"
CHOICE_SMART_DENY = "smart_deny"

#: The choices the host uses for an approval, by kind.
ONCE = "once"
SESSION = "session"
ALWAYS = "always"


class AuthorizationError(Exception):
    """The authorization state could not be derived."""


def state_for_choice(choice: object) -> Optional[AUTHORIZATION_STATE]:
    """The state a host approval choice produces.

    Returns ``None`` for a choice this runtime does not define. The
    caller then records ``UNKNOWN`` - an unknown choice is not
    silently treated as a refusal, and not as an approval.
    """
    if choice in (ONCE, SESSION, ALWAYS):
        return AUTHORIZATION_STATE.HUMAN_APPROVED
    if choice == CHOICE_DENY:
        return AUTHORIZATION_STATE.HUMAN_REJECTED
    if choice == CHOICE_TIMEOUT:
        return AUTHORIZATION_STATE.APPROVAL_TIMEOUT
    if choice == CHOICE_CANCELLED:
        return AUTHORIZATION_STATE.APPROVAL_CANCELLED
    if choice == CHOICE_NOTIFY_FAILED:
        return AUTHORIZATION_STATE.TRANSPORT_FAILED
    if choice == CHOICE_SMART_APPROVE:
        return AUTHORIZATION_STATE.GUARDIAN_APPROVED
    if choice == CHOICE_SMART_DENY:
        return AUTHORIZATION_STATE.GUARDIAN_REJECTED
    return None


def author_for_state(state: AUTHORIZATION_STATE) -> AUTHORIZED_BY:
    """Who authorized it, from the state.

    A timeout has no author: nobody answered. A refusal has the
    user, because the user pressed the button.
    """
    if state == AUTHORIZATION_STATE.HUMAN_APPROVED:
        return AUTHORIZED_BY.USER
    if state == AUTHORIZATION_STATE.HUMAN_REJECTED:
        return AUTHORIZED_BY.USER
    if state in (
        AUTHORIZATION_STATE.GUARDIAN_APPROVED,
        AUTHORIZATION_STATE.GUARDIAN_REJECTED,
    ):
        # The Guardian is an LLM, not a human. It is never recorded as
        # the user, and never as an automatic allowance.
        return AUTHORIZED_BY.GUARDIAN_LLM
    if state in (
        AUTHORIZATION_STATE.APPROVAL_NOT_REQUIRED,
        AUTHORIZATION_STATE.AUTOMATICALLY_ALLOWED,
    ):
        return AUTHORIZED_BY.SYSTEM
    return AUTHORIZED_BY.NONE


def reason_for_state(state: AUTHORIZATION_STATE) -> AUTHORIZATION_REASON:
    """Why the state is what it is."""
    if state == AUTHORIZATION_STATE.HUMAN_APPROVED:
        return AUTHORIZATION_REASON.SINGLE_QUERY_APPROVE
    if state == AUTHORIZATION_STATE.HUMAN_REJECTED:
        return AUTHORIZATION_REASON.NO_HUMAN_PRESENT
    if state in (
        AUTHORIZATION_STATE.GUARDIAN_APPROVED,
        AUTHORIZATION_STATE.GUARDIAN_REJECTED,
    ):
        return AUTHORIZATION_REASON.GUARDIAN_VERDICT
    if state == AUTHORIZATION_STATE.APPROVAL_TIMEOUT:
        return AUTHORIZATION_REASON.NO_HUMAN_PRESENT
    if state == AUTHORIZATION_STATE.APPROVAL_CANCELLED:
        return AUTHORIZATION_REASON.NO_HUMAN_PRESENT
    if state == AUTHORIZATION_STATE.TRANSPORT_FAILED:
        return AUTHORIZATION_REASON.GATEWAY_NOTIFY_FAILED
    if state in (
        AUTHORIZATION_STATE.AUTOMATICALLY_ALLOWED,
        AUTHORIZATION_STATE.AUTOMATICALLY_DENIED,
    ):
        return AUTHORIZATION_REASON.ALLOWLIST
    if state == AUTHORIZATION_STATE.APPROVAL_NOT_REQUIRED:
        return AUTHORIZATION_REASON.ALLOWLIST
    return AUTHORIZATION_REASON.UNKNOWN


def provenance_for_source(source: str) -> AUTHORIZATION_PROVENANCE:
    """Where the observation came from."""
    if source == "approval_hook":
        return AUTHORIZATION_PROVENANCE.HOST_APPROVAL_HOOK
    if source == "tool_fate":
        return AUTHORIZATION_PROVENANCE.HOST_TOOL_FATE
    return AUTHORIZATION_PROVENANCE.NOT_APPLICABLE


class AuthorizationRecord:
    """One authorization state, ready to be persisted.

    It carries the state, who authorized it, why, and the notes that
    make an ambiguous or weak observation auditable.
    """

    __slots__ = (
        "state",
        "authorized_by",
        "reason",
        "provenance",
        "notes",
        "forecast_id",
        "tool_call_id",
        "pattern_key",
        "decided_at",
    )

    def __init__(
        self,
        state: AUTHORIZATION_STATE,
        *,
        forecast_id: str = "",
        tool_call_id: str = "",
        pattern_key: str = "",
        decided_by: Optional[AUTHORIZED_BY] = None,
        reason: Optional[AUTHORIZATION_REASON] = None,
        provenance: AUTHORIZATION_PROVENANCE = AUTHORIZATION_PROVENANCE.NOT_APPLICABLE,
        notes: str = "",
        decided_at: Optional[str] = None,
    ) -> None:
        self.state = state
        self.authorized_by = decided_by or author_for_state(state)
        self.reason = reason or reason_for_state(state)
        self.provenance = provenance
        self.notes = notes
        self.forecast_id = forecast_id
        self.tool_call_id = tool_call_id
        self.pattern_key = pattern_key
        self.decided_at = decided_at

    @property
    def is_approval(self) -> bool:
        """Whether this state authorizes anything.

        Only a real human approval and a Guardian verdict do. Every
        other state - including ``UNKNOWN`` and
        ``APPROVAL_NOT_OBSERVED`` - does not.
        """
        return self.state in (
            AUTHORIZATION_STATE.HUMAN_APPROVED,
            AUTHORIZATION_STATE.GUARDIAN_APPROVED,
        )

    def to_mapping(self) -> dict:
        return {
            "state": self.state.value,
            "authorized_by": self.authorized_by.value,
            "reason": self.reason.value,
            "provenance": self.provenance.value,
            "notes": self.notes,
            "forecast_id": self.forecast_id,
            "tool_call_id": self.tool_call_id,
            "pattern_key": self.pattern_key,
            "decided_at": self.decided_at,
        }

    def __repr__(self) -> str:  # pragma: no cover - diagnostic only
        return "<AuthorizationRecord %s>" % self.state.value


class AuthorizationMachine:
    """Derives the authorization state from the host's events.

    The machine holds no state of its own beyond the deadline. Every
    state is derived from an observation, and the absence of an
    observation is itself an observation - the weaker state.
    """

    def __init__(self, *, grace_seconds: int = 30) -> None:
        if grace_seconds < 0:
            raise ValueError("the grace period cannot be negative")
        self.grace_seconds = grace_seconds

    # -- the observations ----------------------------------------------

    def from_choice(
        self,
        choice: object,
        *,
        forecast_id: str = "",
        tool_call_id: str = "",
        pattern_key: str = "",
        decided_at: Optional[str] = None,
    ) -> AuthorizationRecord:
        """The state produced by an observed approval response."""
        state = state_for_choice(choice)
        if state is None:
            # An unknown choice is not an approval and not a refusal.
            return AuthorizationRecord(
                AUTHORIZATION_STATE.UNKNOWN,
                forecast_id=forecast_id,
                tool_call_id=tool_call_id,
                pattern_key=pattern_key,
                provenance=provenance_for_source("approval_hook"),
                notes="the host reported an approval choice this runtime "
                      "does not define: %r" % (choice,),
                decided_at=decided_at,
            )
        return AuthorizationRecord(
            state,
            forecast_id=forecast_id,
            tool_call_id=tool_call_id,
            pattern_key=pattern_key,
            provenance=provenance_for_source("approval_hook"),
            decided_at=decided_at,
        )

    def from_tool_fate(
        self,
        *,
        ran: bool,
        forecast_id: str = "",
        tool_call_id: str = "",
        pattern_key: str = "",
        decided_at: Optional[str] = None,
    ) -> AuthorizationRecord:
        """The state produced by a tool call with no approval observed.

        EC-6: the host ran the tool and nobody was asked, so the
        outcome was automatic. The plugin records that plainly rather
        than claiming an approval it never saw.
        """
        state = (
            AUTHORIZATION_STATE.AUTOMATICALLY_ALLOWED
            if ran
            else AUTHORIZATION_STATE.AUTOMATICALLY_DENIED
        )
        return AuthorizationRecord(
            state,
            forecast_id=forecast_id,
            tool_call_id=tool_call_id,
            pattern_key=pattern_key,
            provenance=provenance_for_source("tool_fate"),
            notes="the tool call completed with no approval request observed",
            decided_at=decided_at,
        )

    def pending(
        self,
        *,
        forecast_id: str = "",
        tool_call_id: str = "",
        pattern_key: str = "",
        decided_at: Optional[str] = None,
    ) -> AuthorizationRecord:
        """The plugin asked, and no answer has arrived yet.

        ``PENDING`` is the one state that is **not** terminal. It says
        an escalation is in flight - it says nothing about whether the
        human will answer, and it never authorizes anything.
        """
        return AuthorizationRecord(
            AUTHORIZATION_STATE.PENDING,
            forecast_id=forecast_id,
            tool_call_id=tool_call_id,
            pattern_key=pattern_key,
            provenance=provenance_for_source("approval_hook"),
            notes="the escalation is in flight; no answer has arrived",
            decided_at=decided_at,
        )

    def not_required(self, *, forecast_id: str = "") -> AuthorizationRecord:
        """No escalation was expected, so none was needed."""
        return AuthorizationRecord(
            AUTHORIZATION_STATE.APPROVAL_NOT_REQUIRED,
            forecast_id=forecast_id,
            provenance=provenance_for_source("tool_fate"),
            notes="the operation was not escalated",
        )

    def not_observed(
        self,
        *,
        forecast_id: str = "",
        tool_call_id: str = "",
        pattern_key: str = "",
        decided_at: Optional[str] = None,
        notes: str = "",
    ) -> AuthorizationRecord:
        """The plugin asked and never saw an answer.

        EC-5 and AUTH-8: a crash and a timeout look the same to the
        plugin, so it records the weaker state. It never records an
        approval it did not observe.
        """
        return AuthorizationRecord(
            AUTHORIZATION_STATE.APPROVAL_NOT_OBSERVED,
            forecast_id=forecast_id,
            tool_call_id=tool_call_id,
            pattern_key=pattern_key,
            provenance=provenance_for_source("approval_hook"),
            notes=notes or "the escalation was never answered",
            decided_at=decided_at,
        )

    def unknown(
        self,
        *,
        forecast_id: str = "",
        tool_call_id: str = "",
        pattern_key: str = "",
        decided_at: Optional[str] = None,
        notes: str = "",
    ) -> AuthorizationRecord:
        """The observations were contradictory or unmatchable."""
        return AuthorizationRecord(
            AUTHORIZATION_STATE.UNKNOWN,
            forecast_id=forecast_id,
            tool_call_id=tool_call_id,
            pattern_key=pattern_key,
            provenance=provenance_for_source("approval_hook"),
            notes=notes or "the observations could not be attributed",
            decided_at=decided_at,
        )

    # -- the deadline --------------------------------------------------

    def deadline_for(self, *, escalated_at: float, host_timeout: int) -> float:
        """When the plugin stops waiting (DEC-16, mechanism M-1).

        The plugin's own deadline is the host's wait **plus** a grace
        period. The host owns the wait; the plugin only keeps the
        record pending a little longer so a late answer is not lost.
        """
        return escalated_at + float(host_timeout) + float(self.grace_seconds)

    def expired(
        self,
        *,
        escalated_at: float,
        host_timeout: int,
        now: Optional[float] = None,
    ) -> bool:
        """Whether the deadline has passed."""
        moment = (
            datetime.now(timezone.utc).timestamp() if now is None else now
        )
        return moment >= self.deadline_for(
            escalated_at=escalated_at, host_timeout=host_timeout
        )
