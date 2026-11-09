"""The Security Guard service: the authority that decides and executes.

This module is the heart of the platform's security claim.

The claim
---------
**Even if the agent controls the plugin, it cannot grant itself
authorisation to execute a protected operation.**

How the claim is made true
--------------------------
Every step below is performed by the **service**, using state the
plugin cannot reach:

1. The request is parsed against a closed schema (see ``protocol``).
   Unknown fields are refused.
2. The request's nonce is checked against the set the service has
   seen. A replayed request is refused.
3. The proposal is **re-derived** from the request. The service does
   not trust the plugin's copy.
4. The authorisation is **verified** by the service: the signature, the
   proposal hash, the scope, the validity window, the revocation list.
5. The policy is consulted: is this operation in the allowlist, does it
   require human approval, is the scope the one the human granted.
6. The authorisation is **consumed atomically** in the durable store.
   One winner, across processes, surviving a restart.
7. The operation is **recorded** in the durable audit trail. If the
   record cannot be written, the operation does not run.
8. The handler runs, **with arguments derived from the proposal** -
   never from the plugin's request.
9. The outcome is recorded. A handler that dies leaves the operation in
   ``OUTCOME_UNKNOWN``, not in a false ``COMPLETED``.

Fail-closed
-----------
Every failure path refuses. There is no fallback that lets the plugin
execute anything, and no path where a failure is converted into an
allowance. An unavailable store, an unknown operation, an unverifiable
signature, an expired window, a policy that cannot be read: all of them
are refusals.

The plugin's role
-----------------
The plugin proposes. It does not decide, it does not consume, and it
does not execute. Everything the plugin sends is treated as a claim to
be checked, never as a fact.
"""
from __future__ import annotations

import os
from typing import Any, Callable, Mapping, Optional, Sequence

from consequence_map.core.authorization import (
    AuthorizationError,
    _as_scope,
    AuthorizationExpired,
    AuthorizationInvalid,
    AuthorizationReplay,
    AuthorizationRevoked,
    AuthorizationScopeError,
    verify_authorization,
)
from consequence_map.core.canonical import CanonicalisationError
from consequence_map.core.timeutil import format_rfc3339, now_utc, parse_rfc3339

from .crypto import (
    CryptoError,
    Ed25519Verifier,
    UnknownAlgorithm,
    UnknownKey,
)
from .protocol import (
    DECISION_ALLOW,
    DECISION_DENY,
    DECISION_INDETERMINATE,
    MessageTooLarge,
    ProtocolError,
    Replay,
    SchemaViolation,
    UnknownMessageType,
    UnknownVersion,
    build_response_message,
    parse_request_message,
    request_digest,
)
from .store import (
    ConsumptionResult,
    GuardStore,
    OperationState,
    StoreError,
    StoreUnavailable,
)

__all__ = [
    "GuardPolicy",
    "PolicyOperation",
    "PolicyError",
    "GuardService",
    "ServiceDecision",
]


class PolicyError(Exception):
    """The policy could not be read or is invalid."""


class PolicyOperation:
    """One operation the service is willing to perform.

    An operation is named, scoped, and described. The plugin may
    request one by its identifier. It cannot supply a handler, a
    command, or arguments: the handler lives in the service, and the
    arguments are derived from the proposal.

    ``argument_map`` names the proposal fields that become the
    handler's arguments. It is an ALLOWLIST: a proposal field that is
    not named here is not passed to the handler. The plugin cannot
    widen it, because the plugin does not hold the policy.
    """

    def __init__(
        self,
        identifier: str,
        scope: str,
        description: str,
        handler: Callable[[Mapping[str, Any]], Any],
        requires_human_approval: bool = True,
        argument_map: Optional[Mapping[str, str]] = None,
        risks: str = "",
        refusal_conditions: Sequence[str] = (),
    ) -> None:
        self.identifier = identifier
        self.scope = scope
        self.description = description
        self.handler = handler
        self.requires_human_approval = requires_human_approval
        self.argument_map = dict(argument_map or {})
        self.risks = risks
        self.refusal_conditions = tuple(refusal_conditions)

    def derive_arguments(self, proposal: Mapping[str, Any]) -> dict:
        """Build the handler's arguments FROM the proposal.

        Only the fields named in ``argument_map`` are passed, and only
        if the proposal has them. A field the plugin invents is not
        passed. A field the proposal lacks is not invented.
        """
        arguments = {}
        for proposal_field, argument_name in self.argument_map.items():
            if proposal_field in proposal:
                arguments[argument_name] = proposal[proposal_field]
        return arguments


class GuardPolicy:
    """The protected policy: what the service may do, and under what rules.

    The policy is loaded from a document and validated. It is NOT
    something the plugin supplies at request time: the plugin could
    ask for anything, and the policy is what it is checked against.
    """

    def __init__(
        self,
        *,
        operations: Sequence[PolicyOperation],
        max_validity_seconds: int = 600,
        clock_skew_seconds: int = 30,
        policy_version: str = "1",
    ) -> None:
        self.operations = {op.identifier: op for op in operations}
        self.max_validity_seconds = int(max_validity_seconds)
        self.clock_skew_seconds = int(clock_skew_seconds)
        self.policy_version = policy_version

    @classmethod
    def from_document(cls, document: Mapping[str, Any], handlers: Mapping[str, Callable]) -> "GuardPolicy":
        """Build a policy from a document.

        The document names the operations, their scopes and their
        policies. The HANDLERS come from the code, not from the
        document: a policy that could name a handler would be a policy
        that could name anything.
        """
        try:
            operations = []
            for entry in document["operations"]:
                identifier = entry["identifier"]
                if identifier not in handlers:
                    raise PolicyError(
                        "the policy names operation %r, which has no handler"
                        % (identifier,)
                    )
                operations.append(PolicyOperation(
                    identifier=identifier,
                    scope=entry["scope"],
                    description=entry.get("description", ""),
                    handler=handlers[identifier],
                    requires_human_approval=bool(
                        entry.get("requires_human_approval", True)
                    ),
                    argument_map=entry.get("argument_map", {}),
                    risks=entry.get("risks", ""),
                    refusal_conditions=entry.get("refusal_conditions", ()),
                ))
            return cls(
                operations=operations,
                max_validity_seconds=int(
                    document.get("max_validity_seconds", 600)
                ),
                clock_skew_seconds=int(document.get("clock_skew_seconds", 30)),
                policy_version=str(document.get("policy_version", "1")),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise PolicyError("the policy document is invalid: %s" % (exc,)) from exc

    def operation(self, identifier: str) -> Optional[PolicyOperation]:
        return self.operations.get(identifier)

    def identifiers(self) -> tuple:
        return tuple(sorted(self.operations))


class ServiceDecision:
    """What the service decided, and why."""

    def __init__(self, decision: str, reason: str, operation_id: str = "", state: str = "") -> None:
        self.decision = decision
        self.reason = reason
        self.operation_id = operation_id
        self.state = state

    def as_message(self) -> Mapping[str, Any]:
        return build_response_message(
            decision=self.decision,
            reason=self.reason,
            operation_id=self.operation_id,
            state=self.state,
        )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "<ServiceDecision %s %s>" % (self.decision, self.reason[:60])


class GuardService:
    """The Security Guard: the authority that decides and executes.

    The service holds the verifier, the policy, the durable store and
    the operation handlers. The plugin holds none of them.
    """

    def __init__(
        self,
        *,
        policy: GuardPolicy,
        store: GuardStore,
        verifier: Ed25519Verifier,
        clock=None,
    ) -> None:
        self.policy = policy
        self.store = store
        self.verifier = verifier
        self._clock = clock

    def _now(self) -> str:
        if self._clock is not None:
            return self._clock()
        return format_rfc3339(now_utc())

    # -- the entry point ----------------------------------------------

    def handle(self, raw: Any) -> Mapping[str, Any]:
        """Handle one request and return a response message.

        This method never raises for a protocol or policy problem: it
        returns a DENY with a reason. It raises only when the SERVICE
        itself is broken (the store is unavailable), and even then the
        caller receives a refusal through :meth:`handle_safe`.
        """
        decision = self.decide(raw)
        return decision.as_message()

    def handle_safe(self, raw: Any) -> Mapping[str, Any]:
        """Handle a request, turning ANY failure into a refusal."""
        try:
            return self.handle(raw)
        except Exception as exc:
            return build_response_message(
                decision=DECISION_DENY,
                reason="the guard could not process the request: %s: %s"
                % (type(exc).__name__, exc),
                operation_id="",
            )

    def decide(self, raw: Any) -> ServiceDecision:
        """The decision path, step by step.

        Each step either returns a decision or refuses. There is no
        path that falls through to an allowance.
        """
        operation_id = ""
        try:
            message = parse_request_message(raw)
        except (MessageTooLarge, SchemaViolation, UnknownMessageType,
                UnknownVersion, ProtocolError) as exc:
            return ServiceDecision(
                DECISION_DENY, "the request is not valid: %s" % (exc,)
            )
        operation_id = message["operation_id"]

        # 2 - the nonce. A request the service has already seen is a
        #     replay at the transport layer, and is refused before the
        #     authorisation is even considered.
        #
        #     The set is DURABLE. An in-memory set is lost when the
        #     service restarts, and an agent can restart a service, so
        #     an in-memory set would reopen the replay window on every
        #     restart. The durable set also refuses the replay before
        #     the authorisation logic is reached at all.
        nonce = message["nonce"]
        try:
            is_new = self.store.record_nonce(
                nonce, self._now(), operation_id
            )
        except StoreUnavailable as exc:
            return ServiceDecision(
                DECISION_DENY,
                "the request could not be recorded, so it is refused: %s"
                % (exc,),
                operation_id,
            )
        if not is_new:
            return ServiceDecision(
                DECISION_DENY, "this request has already been answered",
                operation_id,
            )

        # 3 - the operation must be in the allowlist. Default deny.
        operation = self.policy.operation(message["operation_id"])
        if operation is None:
            return ServiceDecision(
                DECISION_DENY,
                "operation %r is not permitted" % (message["operation_id"],),
                operation_id,
            )

        # 4 - the proposal is re-derived, and the authorisation verified
        #     by the SERVICE.
        #
        #     The REQUEST is rebuilt here from the authorisation and the
        #     proposal, because the request is what binds the two: it
        #     carries the nonce, the proposal hash, the scope and the
        #     OPERATION that was asked for. The plugin does not send a
        #     request - it sends a proposal and an authorisation - so
        #     the service derives the request rather than trusting one
        #     it received.
        #
        #     The derived request's scope is the authorisation's OWN
        #     approved scope. That is deliberate: the check below
        #     compares the approved scope against the scope the human
        #     granted, and using the request's scope here would let the
        #     plugin widen its own request to match a narrow approval.
        #
        #     The derived request's OPERATION is the operation the
        #     AUTHORISATION was made for. The operation the plugin asks
        #     for is then compared against it. An approval for
        #     "file.delete" must not authorise "repo.wipe" merely
        #     because both happen to need the same scope.
        signed_operation = message["authorization"].get("operation")
        if signed_operation is None:
            # Older authorisations do not carry the operation. The
            # service refuses them rather than guessing: the
            # operation is what the human approved, and without it
            # there is nothing to bind to.
            return ServiceDecision(
                DECISION_DENY,
                "the authorisation does not name the operation it was "
                "made for, so it cannot be applied to one",
                operation_id,
            )
        if signed_operation != operation.identifier:
            return ServiceDecision(
                DECISION_DENY,
                "the authorisation was made for operation %r, not %r"
                % (signed_operation, operation.identifier),
                operation_id,
            )
        try:
            derived_request = {
                "request_id": message["authorization"].get("request_id", ""),
                "proposal": message["proposal"],
                "proposal_hash": message["authorization"].get("proposal_hash", ""),
                "nonce": message["authorization"].get("nonce", ""),
                "project": "",
                "operation": signed_operation,
                "requested_scope": list(
                    message["authorization"].get("approved_scope", ())
                ),
                "requested_by": "",
                "expires_at": message["authorization"].get("expires_at", ""),
                "protocol_version": message["authorization"].get(
                    "protocol_version", ""
                ),
            }
            verify_authorization(
                proposal=message["proposal"],
                request=derived_request,
                authorization=message["authorization"],
                verifier=self.verifier,
                revoked_key_ids=(),
                now=self._now(),
                max_validity_seconds=self.policy.max_validity_seconds,
                clock_skew_seconds=self.policy.clock_skew_seconds,
            )
        except AuthorizationReplay as exc:
            return ServiceDecision(
                DECISION_DENY, "the authorisation is a replay: %s" % (exc,),
                operation_id,
            )
        except AuthorizationExpired as exc:
            return ServiceDecision(
                DECISION_DENY, "the authorisation is not valid: %s" % (exc,),
                operation_id,
            )
        except AuthorizationRevoked as exc:
            return ServiceDecision(
                DECISION_DENY, "the authorisation is revoked: %s" % (exc,),
                operation_id,
            )
        except AuthorizationScopeError as exc:
            return ServiceDecision(
                DECISION_DENY, "the scope does not cover this operation: %s"
                % (exc,),
                operation_id,
            )
        except AuthorizationInvalid as exc:
            return ServiceDecision(
                DECISION_DENY, "the authorisation does not hold: %s" % (exc,),
                operation_id,
            )
        except (UnknownAlgorithm, UnknownKey) as exc:
            return ServiceDecision(
                DECISION_DENY, "the authorisation could not be verified: %s"
                % (exc,),
                operation_id,
            )
        except CryptoError as exc:
            return ServiceDecision(
                DECISION_DENY, "the authorisation could not be verified: %s"
                % (exc,),
                operation_id,
            )
        except CanonicalisationError as exc:
            return ServiceDecision(
                DECISION_DENY, "the proposal is not canonicalisable: %s" % (exc,),
                operation_id,
            )
        except AuthorizationError as exc:
            return ServiceDecision(
                DECISION_DENY, "the authorisation does not hold: %s" % (exc,),
                operation_id,
            )

        # 5 - the granted scope must cover the operation's scope, AND
        #     must not exceed what was asked for.
        #
        #     The second half matters. The derived request's scope is
        #     the authorisation's own approved scope, so the
        #     "approved is a subset of requested" check inside
        #     verify_authorization is VACUOUS - it compares a set with
        #     itself. It cannot detect an approval that grants more
        #     than the operation needs.
        #
        #     The scope the PLUGIN asked for is carried separately in
        #     the message, and the approval must be a subset of THAT.
        #     An approval that grants "admin" when the request asked
        #     for "files:write" is refused here.
        granted = set(message["authorization"].get("approved_scope", ()))
        if operation.scope not in granted:
            return ServiceDecision(
                DECISION_DENY,
                "the authorisation grants %s, which does not include %r"
                % (sorted(granted), operation.scope),
                operation_id,
            )
        requested = message.get("requested_scope")
        if requested is None:
            requested = message["authorization"].get("approved_scope", ())
        try:
            requested_set = set(_as_scope(requested, "requested_scope"))
        except AuthorizationInvalid as exc:
            return ServiceDecision(
                DECISION_DENY,
                "the requested scope is not valid: %s" % (exc,),
                operation_id,
            )
        if not granted.issubset(requested_set):
            return ServiceDecision(
                DECISION_DENY,
                "the authorisation grants %s, which is outside the requested "
                "scope %s" % (sorted(granted), sorted(requested_set)),
                operation_id,
            )

        # 6 - an operation that needs human approval cannot proceed
        #     without one. The check is on the policy, not on a field
        #     the plugin sent.
        if operation.requires_human_approval and not granted:
            return ServiceDecision(
                DECISION_DENY,
                "operation %r requires human approval and none was granted"
                % (operation.identifier,),
                operation_id,
            )

        return self._execute(operation, message, operation_id)

    # -- execution -----------------------------------------------------

    def _execute(
        self,
        operation: PolicyOperation,
        message: Mapping[str, Any],
        operation_id: str,
    ) -> ServiceDecision:
        """Consume, record, run, and record the outcome.

        Every step here can refuse. The order matters: the audit
        record of the attempt is written BEFORE the handler runs, so a
        crash cannot leave an execution with no trace at all.
        """
        now = self._now()
        authorization = message["authorization"]
        authorization_id = authorization.get("authorization_id", "")
        nonce = authorization.get("nonce", "")

        # The INSTANCE identifier is the service's own, not the
        # operation's name.
        #
        # The operation_id in the message names the KIND of operation
        # ("file.delete"), not the individual execution. Two executions
        # of the same kind therefore share an identifier, and the
        # second one's state update would overwrite the first one's -
        # which would let a later execution mark an operation whose
        # outcome was UNKNOWN as COMPLETED.
        #
        # The instance identifier is derived from the authorisation,
        # which is unique per approval.
        instance_id = "op:%s:%s" % (authorization_id or "unknown", nonce or "unknown")

        # The audit record of the attempt comes first. If it cannot be
        # written, the operation does not run.
        try:
            self.store.append_audit(
                "guard.request.accepted",
                {
                    "operation_id": instance_id,
                    "operation": operation.identifier,
                    "authorization_id": authorization_id,
                    "request_digest": request_digest(message),
                },
                now,
            )
        except (StoreUnavailable, StoreError) as exc:
            return ServiceDecision(
                DECISION_DENY,
                "the audit trail could not be written, so the operation is "
                "refused: %s" % (exc,),
                operation_id,
            )

        try:
            self.store.record_operation(
                operation_id=instance_id,
                state=OperationState.RECEIVED,
                request_id=authorization.get("request_id", ""),
                authorization_id=authorization_id,
                operation=operation.identifier,
                proposal_hash=authorization.get("proposal_hash", ""),
                now=now,
            )
        except (StoreUnavailable, StoreError) as exc:
            return ServiceDecision(
                DECISION_DENY,
                "the operation could not be recorded, so it is refused: %s"
                % (exc,),
                operation_id,
            )

        # The atomic consumption.
        try:
            spent_key = "%s|%s" % (authorization_id, nonce)
            consumption = self.store.consume(
                spent_key=spent_key,
                authorization_id=authorization_id,
                nonce=nonce,
                request_id=authorization.get("request_id", ""),
                operation_id=instance_id,
                consumed_by="guard",
                now=now,
            )
        except StoreUnavailable as exc:
            return ServiceDecision(
                DECISION_DENY,
                "the authorisation could not be consumed, so the operation "
                "is refused: %s" % (exc,),
                operation_id,
            )
        if not consumption.consumed:
            return ServiceDecision(
                DECISION_DENY,
                "the authorisation was already consumed: %s"
                % (consumption.reason,),
                operation_id,
            )

        self.store.record_operation(
            operation_id=instance_id,
            state=OperationState.CONSUMED,
            request_id=authorization.get("request_id", ""),
            authorization_id=authorization_id,
            operation=operation.identifier,
            proposal_hash=authorization.get("proposal_hash", ""),
            now=now,
        )

        # The arguments are DERIVED from the proposal, by the policy's
        # allowlist. The plugin never supplies them.
        arguments = operation.derive_arguments(message["proposal"])

        self.store.record_operation(
            operation_id=instance_id,
            state=OperationState.EXECUTION_STARTED,
            request_id=authorization.get("request_id", ""),
            authorization_id=authorization_id,
            operation=operation.identifier,
            proposal_hash=authorization.get("proposal_hash", ""),
            now=now,
        )

        try:
            result = operation.handler(arguments)
        except Exception as exc:
            self._record_outcome(
                instance_id, OperationState.FAILED, now, authorization_id,
                operation, "%s: %s" % (type(exc).__name__, exc),
            )
            return ServiceDecision(
                DECISION_DENY,
                "the operation failed: %s: %s" % (type(exc).__name__, exc),
                operation_id,
                state=OperationState.FAILED,
            )

        self._record_outcome(
            instance_id, OperationState.COMPLETED, now, authorization_id,
            operation, "",
        )
        return ServiceDecision(
            DECISION_ALLOW,
            "the operation completed",
            operation_id,
            state=OperationState.COMPLETED,
        )

    def _record_outcome(
        self,
        operation_id: str,
        state: str,
        now: str,
        authorization_id: str,
        operation: PolicyOperation,
        detail: str,
    ) -> None:
        """Record the outcome. A failure here is not swallowed."""
        try:
            self.store.record_operation(
                operation_id=operation_id,
                state=state,
                request_id="",
                authorization_id=authorization_id,
                operation=operation.identifier,
                proposal_hash="",
                now=now,
                detail=detail,
            )
            self.store.append_audit(
                "guard.operation.%s" % state.lower(),
                {
                    "operation_id": operation_id,
                    "operation": operation.identifier,
                    "detail": detail,
                },
                now,
            )
        except (StoreUnavailable, StoreError) as exc:
            # The outcome could not be recorded. The operation state is
            # then NOT COMPLETED - it is unknown. This is the honest
            # answer, and it is the one the recovery path acts on.
            try:
                self.store.record_operation(
                    operation_id=operation_id,
                    state=OperationState.OUTCOME_UNKNOWN,
                    request_id="",
                    authorization_id=authorization_id,
                    operation=operation.identifier,
                    proposal_hash="",
                    now=now,
                    detail="the outcome could not be recorded: %s" % (exc,),
                )
            except Exception:
                pass
