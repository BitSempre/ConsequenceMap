"""The Security Guard: a decision boundary the agent does not control.

The problem this module addresses
--------------------------------
The Quality Guardian today runs **in-process**, as a plugin inside the
agent's own runtime. That means the agent can read the Guardian's
configuration, and - because the Guardian runs with the agent's
credentials - the agent can write to whatever the Guardian can write.

An in-process guard is not a trust boundary. It is a function call.

What a boundary requires
------------------------
For the Guard to be a boundary rather than a function call, three things
must hold:

1. **It must run in a different process.** A separate process has its own
   memory, its own file handles and its own lifetime.
2. **It must run under a different identity.** Otherwise the agent, running
   as the same account, can do what the Guard can do.
3. **The agent must not be able to choose its inputs.** The Guard must
   re-derive what it needs, not accept the agent's word.

This module implements the third. It implements the first two as an
**interface** with a documented contract, because a separate process
running as a different Windows identity cannot be created from inside the
agent's process without privileges the agent should not have.

What this module does
---------------------
It is the **decision logic** of the guard, separated from its **deployment**.
The logic is pure: given a request and a verification context, it returns
a decision and a reason. The deployment (which process, which identity,
which transport) is a separate concern.

The decisions are deliberately coarse:

- ``ALLOW`` - every condition held.
- ``DENY`` - a condition failed, or the request was not in the allowlist.
- ``INDETERMINATE`` - a condition could not be evaluated. This is
  **never** folded into ALLOW.

That last one is the whole point. The incident audit's central finding was
that a failed verification could be rendered as a warning and the
operation could continue. ``INDETERMINATE`` cannot be silently upgraded.

The guard records every decision, including the denials. A refusal that
is not recorded is indistinguishable from an operation that never
happened.
"""
from __future__ import annotations

from typing import Any, Mapping, Optional, Sequence

from .audit import AuditLog
from .authorization import (
    AuthorizationError,
    Verifier,
    verify_authorization,
)
from .canonical import CanonicalisationError
from .execution import (
    ExecutionEngine,
    ExecutionError,
    ExecutionRefused,
    OperationRegistry,
)

__all__ = [
    "DECISION_ALLOW",
    "DECISION_DENY",
    "DECISION_INDETERMINATE",
    "GuardDecision",
    "VerificationContext",
    "SecurityGuard",
    "GuardUnavailable",
]

DECISION_ALLOW = "ALLOW"
DECISION_DENY = "DENY"
DECISION_INDETERMINATE = "INDETERMINATE"


class GuardUnavailable(Exception):
    """The guard could not be reached or could not decide.

    Raised by the deployment layer, not by the decision logic. The caller
    must treat it as a refusal, never as a pass.
    """


class GuardDecision:
    """The guard's answer, with the reason attached."""

    def __init__(
        self,
        decision: str,
        reason: str,
        *,
        checks: Optional[Mapping[str, bool]] = None,
        detail: Optional[Mapping[str, Any]] = None,
    ) -> None:
        if decision not in (DECISION_ALLOW, DECISION_DENY, DECISION_INDETERMINATE):
            raise ValueError("unknown decision %r" % (decision,))
        self.decision = decision
        self.reason = reason
        self.checks = dict(checks or {})
        self.detail = dict(detail or {})

    @property
    def allowed(self) -> bool:
        return self.decision == DECISION_ALLOW

    def to_mapping(self) -> Mapping[str, Any]:
        return {
            "decision": self.decision,
            "reason": self.reason,
            "checks": dict(self.checks),
            "detail": dict(self.detail),
        }

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "<GuardDecision %s: %s>" % (self.decision, self.reason)


class VerificationContext:
    """Everything the guard needs, gathered by the deployment layer.

    The guard does not read these from the agent. It receives them from
    the layer that has the authority to read them - which, in a correct
    deployment, is a different identity from the agent's.
    """

    def __init__(
        self,
        *,
        proposal: Mapping[str, Any],
        request: Mapping[str, Any],
        authorization: Mapping[str, Any],
        operation: str,
        arguments: Mapping[str, Any],
        revoked_key_ids: Sequence[str] = (),
        now: Optional[str] = None,
        policy_version: str = "consequencemap.policy.v1",
    ) -> None:
        self.proposal = proposal
        self.request = request
        self.authorization = authorization
        self.operation = operation
        self.arguments = arguments
        self.revoked_key_ids = tuple(revoked_key_ids)
        self.now = now
        self.policy_version = policy_version

    def to_mapping(self) -> Mapping[str, Any]:
        return {
            "proposal_hash": self.request.get("proposal_hash"),
            "operation": self.operation,
            "policy_version": self.policy_version,
            "requested_by": self.request.get("requested_by"),
        }


class SecurityGuard:
    """The decision logic of the Security Guard.

    It owns the verifier, the operation registry, the revoked-key list and
    the audit log. It makes no decision it cannot justify with a check it
    actually performed.
    """

    def __init__(
        self,
        registry: OperationRegistry,
        verifier: Verifier,
        audit: Optional[AuditLog] = None,
        revoked_key_ids: Sequence[str] = (),
    ) -> None:
        self.registry = registry
        self.verifier = verifier
        self.audit = audit if audit is not None else AuditLog()
        self.revoked_key_ids = tuple(revoked_key_ids)
        self._engine = ExecutionEngine(
            registry, verifier, revoked_key_ids=self.revoked_key_ids
        )

    # -- the decision -------------------------------------------------

    def decide(self, context: VerificationContext) -> GuardDecision:
        """Decide whether the operation may proceed.

        The checks run in a fixed order and every one of them is recorded.
        The first failure decides the outcome, and the reason names it.
        """
        checks: dict = {}

        # 1. The operation must be on the allowlist. Default deny.
        try:
            operation = self.registry.get(context.operation)
            checks["operation_on_allowlist"] = True
        except ExecutionRefused as exc:
            checks["operation_on_allowlist"] = False
            return self._refuse(
                context, str(exc), checks, event="guard.denied.allowlist"
            )

        # 2. The proposal must be canonicalisable. If it is not, the
        #    authorization cannot be bound to it.
        try:
            from .canonical import domain_hash, DOMAIN_AUTHORIZATION

            domain_hash(DOMAIN_AUTHORIZATION, {"proposal": context.proposal})
            checks["proposal_canonicalisable"] = True
        except CanonicalisationError as exc:
            checks["proposal_canonicalisable"] = False
            return self._refuse(
                context, "the proposal is not canonicalisable: %s" % (exc,),
                checks, event="guard.denied.proposal",
            )

        # 3. The authorization must hold. This is re-verified here, by the
        #    guard, against the guard's own verifier and revocation list.
        try:
            verify_authorization(
                proposal=context.proposal,
                request=context.request,
                authorization=context.authorization,
                verifier=self.verifier,
                revoked_key_ids=self.revoked_key_ids,
                now=context.now,
            )
            checks["authorization_valid"] = True
        except AuthorizationError as exc:
            checks["authorization_valid"] = False
            return self._refuse(
                context, "the authorization does not hold: %s" % (exc,),
                checks, event="guard.denied.authorization",
            )

        # 4. The authorization must grant the operation's scope.
        granted = set(context.authorization.get("approved_scope", ()))
        checks["scope_granted"] = operation.scope in granted
        if not checks["scope_granted"]:
            return self._refuse(
                context,
                "the authorization does not grant scope %r" % (operation.scope,),
                checks, event="guard.denied.scope",
            )

        # 5. The arguments must not carry a command.
        forbidden = {"command", "cmd", "shell", "script", "argv"}
        offending = forbidden.intersection(context.arguments or {})
        checks["no_command_arguments"] = not offending
        if offending:
            return self._refuse(
                context,
                "the arguments carry a command field: %s" % (sorted(offending),),
                checks, event="guard.denied.command",
            )

        # 6. The operation must be executable in the current state.
        from .execution import STATE_PREPARED

        try:
            self._engine.can_transition(STATE_PREPARED, "ANALYZING")
            checks["state_transition_permitted"] = True
        except Exception as exc:  # pragma: no cover - defensive
            checks["state_transition_permitted"] = False
            return self._refuse(
                context, "the state machine refused the transition: %s" % (exc,),
                checks, event="guard.denied.state",
            )

        self.audit.append(
            "guard.allowed",
            {
                "operation": context.operation,
                "scope": operation.scope,
                "proposal_hash": context.request.get("proposal_hash"),
                "authorized_by": context.authorization.get("approved_by"),
            },
        )
        return GuardDecision(
            DECISION_ALLOW,
            "every condition held",
            checks=checks,
            detail={"scope": operation.scope},
        )

    def _refuse(
        self,
        context: VerificationContext,
        reason: str,
        checks: Mapping[str, bool],
        event: str,
    ) -> GuardDecision:
        # The refusal is recorded. A refusal that leaves no trace is
        # indistinguishable from an operation that never happened.
        self.audit.append(
            event,
            {
                "operation": context.operation,
                "reason": reason,
                "proposal_hash": context.request.get("proposal_hash"),
                "checks": dict(checks),
            },
        )
        return GuardDecision(DECISION_DENY, reason, checks=checks)

    # -- the execution -------------------------------------------------

    def execute(self, context: VerificationContext):
        """Decide, and execute only if the decision is ALLOW.

        The execution engine re-verifies the authorization itself, so a
        decision and an execution cannot diverge.
        """
        decision = self.decide(context)
        if not decision.allowed:
            raise ExecutionRefused(decision.reason)
        from .execution import ExecutionRequest

        request = ExecutionRequest(
            operation=context.operation,
            arguments=context.arguments,
            proposal=context.proposal,
            request=context.request,
            authorization=context.authorization,
        )
        return self._engine.execute(request, now=context.now)
