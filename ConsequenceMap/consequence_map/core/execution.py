"""The controlled execution engine.

The executor applies decisions that the security layer has already made.
It does not make security decisions. Its contract is narrow and absolute:

**It performs only the operations on its allowlist, and only when every
verifiable condition holds. Anything it cannot verify is a refusal, not a
default.**

Three properties follow from that and are enforced here:

1. **Default deny.** An operation that is not on the allowlist is refused.
   The allowlist is exhaustive; there is no "generic" operation.
2. **No command strings.** No operation takes a command string. The
   executor never hands a caller-supplied string to a command interpreter
   or to a process launcher. Every operation is a named entry in a
   registry whose implementation is fixed at build time.
3. **The executor does not trust the agent.** It re-derives the hash of the
   proposal itself, re-checks the authorization against its own state, and
   refuses if anything does not line up. A caller that says "the approval
   was checked" is not evidence.

State machine
-------------
::

    PREPARED -> ANALYZING -> REQUIRES_HUMAN_APPROVAL -> APPROVED -> EXECUTING
        ^              |                 |                    |          |
        |              v                 v                    v          v
        +---------- REJECTED          BLOCKED              EXPIRED    EXECUTED
                       |                                    |          |
                       +------------------------------------+          v
                                                          +---------> FAILED

The permitted transitions are enumerated in :data:`ALLOWED_TRANSITIONS`.
A transition that is not in that table is refused. Two terminal states -
``REJECTED`` and ``BLOCKED`` - are also terminal for the *authorisation*:
neither can be revived, and neither can be re-activated by a later
approval. That is what stops a failed attempt from being retried into
success.
"""
from __future__ import annotations

import hashlib
import os
from typing import Any, Callable, Dict, Mapping, Optional, Sequence, Tuple

from .authorization import (
    AuthorizationError,
    Verifier,
    verify_authorization,
)
from .canonical import CanonicalisationError, DOMAIN_AUTHORIZATION, domain_hash

__all__ = [
    "ExecutionError",
    "ExecutionRefused",
    "ExecutionBlocked",
    "STATE_PREPARED",
    "STATE_ANALYZING",
    "STATE_REQUIRES_HUMAN_APPROVAL",
    "STATE_APPROVED",
    "STATE_REJECTED",
    "STATE_BLOCKED",
    "STATE_EXECUTING",
    "STATE_EXECUTED",
    "STATE_FAILED",
    "STATE_EXPIRED",
    "STATE_REVOKED",
    "ALLOWED_TRANSITIONS",
    "TERMINAL_STATES",
    "Operation",
    "OperationRegistry",
    "ExecutionRequest",
    "ExecutionEngine",
]


class ExecutionError(Exception):
    """Base class for execution failures."""


class ExecutionRefused(ExecutionError):
    """The execution was refused: a condition did not hold."""


class ExecutionBlocked(ExecutionError):
    """The execution was blocked: a precondition was missing."""


STATE_PREPARED = "PREPARED"
STATE_ANALYZING = "ANALYZING"
STATE_REQUIRES_HUMAN_APPROVAL = "REQUIRES_HUMAN_APPROVAL"
STATE_APPROVED = "APPROVED"
STATE_REJECTED = "REJECTED"
STATE_BLOCKED = "BLOCKED"
STATE_EXECUTING = "EXECUTING"
STATE_EXECUTED = "EXECUTED"
STATE_FAILED = "FAILED"
STATE_EXPIRED = "EXPIRED"
STATE_REVOKED = "REVOKED"

#: The only transitions the engine will perform.
ALLOWED_TRANSITIONS: Mapping[str, Tuple[str, ...]] = {
    STATE_PREPARED: (STATE_ANALYZING, STATE_REJECTED, STATE_BLOCKED),
    STATE_ANALYZING: (
        STATE_REQUIRES_HUMAN_APPROVAL,
        STATE_APPROVED,
        STATE_REJECTED,
        STATE_BLOCKED,
    ),
    STATE_REQUIRES_HUMAN_APPROVAL: (
        STATE_APPROVED,
        STATE_REJECTED,
        STATE_BLOCKED,
        STATE_EXPIRED,
        STATE_REVOKED,
    ),
    STATE_APPROVED: (STATE_EXECUTING, STATE_EXPIRED, STATE_REVOKED, STATE_BLOCKED),
    STATE_EXECUTING: (STATE_EXECUTED, STATE_FAILED),
    # Terminal states have no outgoing transitions.
    STATE_REJECTED: (),
    STATE_BLOCKED: (),
    STATE_EXECUTED: (),
    STATE_FAILED: (),
    STATE_EXPIRED: (),
    STATE_REVOKED: (),
}

#: States from which no further transition is possible.
TERMINAL_STATES: Tuple[str, ...] = (
    STATE_REJECTED,
    STATE_BLOCKED,
    STATE_EXECUTED,
    STATE_FAILED,
    STATE_EXPIRED,
    STATE_REVOKED,
)


class Operation:
    """One permitted operation.

    An operation is identified by a stable name, belongs to a scope, and
    has a fixed implementation. The implementation receives the validated
    arguments - never a command line.
    """

    def __init__(
        self,
        name: str,
        scope: str,
        handler: Callable[[Mapping[str, Any]], Any],
        description: str = "",
    ) -> None:
        self.name = name
        self.scope = scope
        self.handler = handler
        self.description = description

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "<Operation %s scope=%s>" % (self.name, self.scope)


class OperationRegistry:
    """The allowlist.

    An operation that is not registered does not exist. There is no
    fallback, no dynamic dispatch on caller-supplied names, and no way to
    add an operation at request time.
    """

    def __init__(self, operations: Sequence[Operation] = ()) -> None:
        self._operations: Dict[str, Operation] = {}
        for operation in operations:
            self.register(operation)

    def register(self, operation: Operation) -> None:
        if operation.name in self._operations:
            raise ValueError("operation %r is already registered" % (operation.name,))
        self._operations[operation.name] = operation

    def get(self, name: str) -> Operation:
        try:
            return self._operations[name]
        except KeyError:
            raise ExecutionRefused(
                "operation %r is not on the allowlist" % (name,)
            ) from None

    def names(self) -> Tuple[str, ...]:
        return tuple(sorted(self._operations))

    def scope_of(self, name: str) -> str:
        return self.get(name).scope

    def __len__(self) -> int:
        return len(self._operations)


class ExecutionRequest:
    """Everything the engine needs to attempt one execution."""

    def __init__(
        self,
        *,
        operation: str,
        arguments: Mapping[str, Any],
        proposal: Mapping[str, Any],
        request: Mapping[str, Any],
        authorization: Mapping[str, Any],
    ) -> None:
        self.operation = operation
        # The arguments are stored AS GIVEN, not coerced. Coercing here
        # would let a caller smuggle a non-mapping past the executor's
        # own type check.
        self.arguments = arguments
        self.proposal = proposal
        self.request = request
        self.authorization = authorization


class ExecutionEngine:
    """Applies a decision, under conditions it verifies itself.

    The engine holds the verifier and the revoked-key list. It re-verifies
    the authorization on every execution attempt, so an authorization that
    was revoked, expired or bound to a different proposal cannot be
    executed even if it was verified earlier by someone else.
    """

    def __init__(
        self,
        registry: OperationRegistry,
        verifier: Verifier,
        revoked_key_ids: Sequence[str] = (),
        clock=None,
    ) -> None:
        self.registry = registry
        self.verifier = verifier
        self.revoked_key_ids = tuple(revoked_key_ids)
        self._clock = clock

    # -- state machine -------------------------------------------------

    @staticmethod
    def can_transition(current: str, target: str) -> bool:
        return target in ALLOWED_TRANSITIONS.get(current, ())

    @staticmethod
    def transition(current: str, target: str) -> str:
        if not ExecutionEngine.can_transition(current, target):
            raise ExecutionRefused(
                "transition %s -> %s is not permitted" % (current, target)
            )
        return target

    # -- execution -----------------------------------------------------

    def execute(
        self,
        request: ExecutionRequest,
        *,
        state: str = STATE_PREPARED,
        now: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute the request, or refuse it.

        Returns a result mapping with ``state`` and, on success, ``result``.
        A refusal raises :class:`ExecutionRefused` or
        :class:`ExecutionBlocked`; the caller decides whether that is a
        rejection or a block.
        """
        # 1. The operation must exist. Default deny.
        operation = self.registry.get(request.operation)

        # 2. The state machine must allow the path we are about to take.
        state = self.transition(state, STATE_ANALYZING)
        state = self.transition(state, STATE_REQUIRES_HUMAN_APPROVAL)
        state = self.transition(state, STATE_APPROVED)

        # 3. The authorization is verified AGAIN, here, by the executor.
        #    The caller may have verified it; that is not evidence.
        try:
            verify_authorization(
                proposal=request.proposal,
                request=request.request,
                authorization=request.authorization,
                verifier=self.verifier,
                revoked_key_ids=self.revoked_key_ids,
                now=now,
            )
        except AuthorizationError as exc:
            raise ExecutionRefused(
                "authorization does not hold: %s" % (exc,)
            ) from exc

        # 4. The authorization must grant the operation's scope.
        granted = set(request.authorization.get("approved_scope", ()))
        if operation.scope not in granted:
            raise ExecutionRefused(
                "authorization does not grant scope %r (granted: %s)"
                % (operation.scope, sorted(granted))
            )

        # 5. The arguments must be a mapping, and must not contain a
        #    command. The executor never accepts a command string.
        if not isinstance(request.arguments, Mapping):
            raise ExecutionRefused("arguments must be a mapping")
        for key in request.arguments:
            if key in ("command", "cmd", "shell", "script", "argv"):
                raise ExecutionRefused(
                    "argument %r is not accepted: the executor never takes a "
                    "command" % (key,)
                )

        # 6. Execute, with the state machine reflecting the outcome.
        state = self.transition(state, STATE_EXECUTING)
        try:
            result = operation.handler(request.arguments)
        except ExecutionBlocked:
            raise
        except Exception as exc:
            return {
                "state": self.transition(state, STATE_FAILED),
                "operation": request.operation,
                "error": "%s: %s" % (type(exc).__name__, exc),
            }
        return {
            "state": self.transition(state, STATE_EXECUTED),
            "operation": request.operation,
            "result": result,
        }
