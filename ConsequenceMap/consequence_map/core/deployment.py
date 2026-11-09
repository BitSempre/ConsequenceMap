"""The interface between the Security Guard and its deployment.

The decision logic in :mod:`consequence_map.core.guard` is pure. This
module defines the **contract** the deployment must satisfy, so that the
logic can be hosted somewhere the agent cannot reach.

Why the contract is separate from the logic
-------------------------------------------
A trust boundary is a property of a **deployment**, not of a function.
The same decision logic running in the agent's process is not a boundary;
the same logic running under a separate identity the agent cannot write
to is. So the logic must not decide *for itself* that it is trustworthy.

This module therefore states what the deployment must provide, and
nothing about how. The platform ships with:

- an **in-process adapter**, used for development and for the tests; it
  provides no boundary and says so;
- a **Windows service adapter**, the production shape: a separate
  process, a separate service identity, a named pipe with an explicit
  security descriptor, and a store in a location the agent's account
  cannot write.

What the deployment must guarantee
----------------------------------
1. **Process separation.** The guard is not in the agent's process.
2. **Identity separation.** The guard does not run as the agent's
   account.
3. **Store separation.** The guard's verifier, its revocation list and
   its audit store are not writable by the agent's account.
4. **Authenticated transport.** The agent may *ask*; only the guard may
   *answer*, and the answer is the guard's own.
5. **Fail closed.** If the guard is unreachable, the answer is a
   refusal. There is no local fallback that approves.

Point 5 is the one that is easiest to get wrong. A local cache of
"last known good" decisions, or an in-process fallback when the service
is down, would silently restore the very boundary the service exists to
provide. :func:`GuardUnavailable` exists so that the failure has a
name, and the deployment raises it rather than answering.

What the deployment must NOT do
-------------------------------
- accept a decision from the agent and pass it on;
- accept a verifier or a revocation list from the agent;
- let the agent choose the policy version;
- answer "allow" when it cannot reach its own store.
"""
from __future__ import annotations

from typing import Any, Mapping, Optional, Protocol

from .guard import (
    DECISION_ALLOW,
    DECISION_DENY,
    DECISION_INDETERMINATE,
    GuardDecision,
    GuardUnavailable,
)

__all__ = [
    "GuardUnavailable",
    "GuardTransport",
    "GuardDeployment",
    "InProcessDeployment",
    "ContractViolation",
]


class ContractViolation(Exception):
    """The deployment violated the guard contract."""


class GuardTransport(Protocol):
    """The transport between the agent and the guard deployment.

    ``ask`` returns the guard's own decision. It never returns a
    decision the agent supplied, and it never returns ``None``.
    """

    def ask(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        ...


class GuardDeployment:
    """The base class for a deployment.

    It implements the parts that must be identical everywhere - the
    refusal on unavailability, and the refusal of a decision that did not
    come from the guard - and leaves the transport to the subclass.
    """

    #: Whether this deployment actually provides a trust boundary. The
    #: in-process deployment does NOT, and says so.
    provides_boundary = False

    #: The fields a compliant transport returns. The schema is closed.
    RESPONSE_FIELDS = frozenset({"decision", "reason", "allowed", "checks", "detail"})

    def __init__(self, transport: Optional[GuardTransport] = None) -> None:
        self._transport = transport

    def decide(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        """Ask the guard, and return its decision.

        Raises :class:`GuardUnavailable` when the guard cannot be
        reached. The caller must treat that as a refusal. This method
        deliberately has no fallback path.
        """
        if self._transport is None:
            raise GuardUnavailable(
                "no guard transport is configured: the decision cannot be "
                "obtained, so it is refused"
            )
        try:
            answer = self._transport.ask(payload)
        except GuardUnavailable:
            raise
        except Exception as exc:
            raise GuardUnavailable(
                "the guard could not be reached: %s: %s"
                % (type(exc).__name__, exc)
            ) from exc
        if not isinstance(answer, Mapping):
            raise ContractViolation(
                "the guard transport returned %s, not a decision"
                % (type(answer).__name__,)
            )
        decision = answer.get("decision")
        if decision not in (DECISION_ALLOW, DECISION_DENY, DECISION_INDETERMINATE):
            raise ContractViolation(
                "the guard transport returned an unknown decision %r" % (decision,)
            )
        if "reason" not in answer:
            raise ContractViolation("the guard transport returned no reason")
        # The response schema is closed. An unexpected field means the
        # transport is not the thing this contract describes.
        unexpected = sorted(set(answer) - self.RESPONSE_FIELDS)
        if unexpected:
            raise ContractViolation(
                "the guard transport returned unexpected field(s): %s"
                % (", ".join(unexpected),)
            )
        # The 'allowed' flag must AGREE with the decision.
        #
        # Both fields are part of the contract, and a consumer is
        # entitled to read either. If a transport could return
        # decision=DENY with allowed=True, then a consumer that read
        # 'allowed' would act on a denial as if it were a permission.
        # That is the whole failure this platform exists to prevent,
        # arriving through a field nobody thought to cross-check.
        if "allowed" in answer:
            if not isinstance(answer["allowed"], bool):
                raise ContractViolation(
                    "the guard transport returned a non-boolean 'allowed': %r"
                    % (answer["allowed"],)
                )
            expected = decision == DECISION_ALLOW
            if answer["allowed"] != expected:
                raise ContractViolation(
                    "the guard transport contradicts itself: decision %r "
                    "with allowed=%r" % (decision, answer["allowed"])
                )
        return dict(answer)

    def refuse(self, reason: str) -> Mapping[str, Any]:
        """The refusal a deployment returns when it cannot answer.

        It is a denial with a reason, not an absence. An absence is
        indistinguishable from a request that was never made.
        """
        return {
            "decision": DECISION_DENY,
            "reason": reason,
            "allowed": False,
            "checks": {},
        }


class InProcessDeployment(GuardDeployment):
    """The development and test deployment: no boundary at all.

    It is honest about that. A deployment that claims a boundary it
    does not provide is worse than one that admits it has none, because
    the claim changes how the rest of the system is written.
    """

    provides_boundary = False

    def __init__(self, transport: Optional[GuardTransport] = None) -> None:
        super().__init__(transport)

    def describe(self) -> Mapping[str, Any]:
        return {
            "kind": "in-process",
            "provides_boundary": False,
            "warning": (
                "This deployment runs inside the agent's own process. It "
                "provides NO trust boundary. It exists for development and "
                "for tests, and must not be used in production."
            ),
        }
