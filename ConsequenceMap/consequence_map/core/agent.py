"""Agent integration: the surface an agent is allowed to touch.

The rule this module enforces
-----------------------------
**The agent gets a narrow, documented, verifiable surface. It does not
get the privileged functions.**

What the agent may do:
- propose an operation;
- build an authorization request;
- ask the guard to decide;
- read the decision and the reason.

What the agent may NOT do:
- verify an authorization (that is the guard's, and the guard's verifier
  is not the agent's to reach);
- write to the authorization or audit stores;
- choose the policy;
- name an operation that is not on the allowlist;
- declare an operation approved.

The adapter
-----------
An adapter translates an agent's request into the platform's vocabulary.
Adapters are per-agent-family, but they share one contract, so the core
never learns anything about any particular agent. That is what keeps the
core independent of its host.

The contract is deliberately small, because a large surface is the
problem, not the solution.
"""
from __future__ import annotations

from typing import Any, Mapping, Optional, Protocol, Sequence

from .authorization import build_request, proposal_hash
from .canonical import CanonicalisationError
from .execution import ExecutionRefused, OperationRegistry
from .guard import GuardDecision, SecurityGuard, VerificationContext

__all__ = [
    "AgentRequest",
    "AgentAdapter",
    "HermesAdapter",
    "AgentSurface",
    "AgentRequestRejected",
]


class AgentRequestRejected(Exception):
    """The agent's request was not well formed, or not permitted."""


class AgentRequest:
    """What an agent asks for.

    An agent states an intention. It does not state an authorization, and
    it cannot: the fields that would make it one are not its to fill.
    """

    def __init__(
        self,
        *,
        operation: str,
        arguments: Mapping[str, Any],
        proposal: Mapping[str, Any],
        project: str,
        requested_scope: Sequence[str],
        requested_by: str,
        expires_at: str,
        summary: str = "",
    ) -> None:
        self.operation = operation
        self.arguments = dict(arguments)
        self.proposal = proposal
        self.project = project
        self.requested_scope = list(requested_scope)
        self.requested_by = requested_by
        self.expires_at = expires_at
        self.summary = summary


class AgentAdapter(Protocol):
    """What every adapter must provide."""

    name: str

    def to_request(self, raw: Mapping[str, Any]) -> AgentRequest:
        """Translate the agent's payload into an :class:`AgentRequest`."""
        ...

    def to_result(self, decision: GuardDecision) -> Mapping[str, Any]:
        """Render a decision for the agent."""
        ...


class HermesAdapter:
    """The adapter for the Hermes host.

    It maps Hermes-shaped payloads onto the platform's vocabulary. It
    performs no security decision and holds no credential.
    """

    name = "hermes"

    def to_request(self, raw: Mapping[str, Any]) -> AgentRequest:
        """Translate a Hermes tool-call payload into an agent request.

        The host's field names are read inline rather than through a
        lookup table: the table named a storage column, and the package
        audit forbids the domain layer from naming one.

        The proposal is required. An operation without a proposal cannot
        be bound to an authorization, so it is rejected here rather than
        failing later.
        """
        if not isinstance(raw, Mapping):
            raise AgentRequestRejected("an agent request must be a mapping")
        missing = [k for k in ("tool", "proposal") if k not in raw]
        if missing:
            raise AgentRequestRejected(
                "the agent request is missing: %s" % (", ".join(missing),)
            )
        proposal = raw["proposal"]
        if not isinstance(proposal, Mapping):
            raise AgentRequestRejected("the proposal must be a mapping")
        try:
            proposal_hash(proposal)
        except CanonicalisationError as exc:
            raise AgentRequestRejected(
                "the proposal is not canonicalisable: %s" % (exc,)
            )
        arguments = raw.get("arguments", {})
        if not isinstance(arguments, Mapping):
            raise AgentRequestRejected("the arguments must be a mapping")
        return AgentRequest(
            operation=raw["tool"],
            arguments=arguments,
            proposal=proposal,
            project=raw.get("project", ""),
            requested_scope=raw.get("scope", []),
            requested_by=raw.get("actor", "unknown-agent"),
            expires_at=raw.get("expires_at", ""),
            summary=raw.get("summary", ""),
        )

    def to_result(self, decision: GuardDecision) -> Mapping[str, Any]:
        """Render a decision for the agent to read."""
        return {
            "allowed": decision.allowed,
            "decision": decision.decision,
            "reason": decision.reason,
            "checks": dict(decision.checks),
        }


class AgentSurface:
    """The narrow surface an agent is given.

    The surface is what the agent can call. It is constructed with the
    guard - never with the guard's internals - and it refuses anything
    that is not one of the three permitted calls.
    """

    def __init__(
        self,
        guard: SecurityGuard,
        adapter: AgentAdapter,
        registry: Optional[OperationRegistry] = None,
    ) -> None:
        self._guard = guard
        self._adapter = adapter
        self._registry = registry if registry is not None else guard.registry

    # -- what the agent may call --------------------------------------

    def propose(self, raw: Mapping[str, Any]) -> Mapping[str, Any]:
        """Turn the agent's payload into an authorization request.

        This is the ONLY way an agent influences what will be asked. The
        request carries the proposal itself, so the human sees the real
        content, and the hash, so the answer is bound to it.
        """
        request = self._adapter.to_request(raw)
        if request.operation not in self._registry.names():
            raise AgentRequestRejected(
                "operation %r is not on the allowlist" % (request.operation,)
            )
        if not request.expires_at:
            raise AgentRequestRejected(
                "an authorization request must carry an expiry"
            )
        built = build_request(
            proposal=request.proposal,
            project=request.project,
            operation=request.operation,
            requested_scope=request.requested_scope,
            requested_by=request.requested_by,
            expires_at=request.expires_at,
        )
        # The FULL request is returned, not a summary: the guard's
        # verification checks mandatory fields, and a request that has
        # been trimmed on the way out would be rejected by the guard for
        # the wrong reason. The summary is derived from the full request.
        return {
            "request_id": built["request_id"],
            "proposal_hash": built["proposal_hash"],
            "nonce": built["nonce"],
            "expires_at": built["expires_at"],
            "operation": request.operation,
            "requested_scope": list(request.requested_scope),
            "proposal": request.proposal,
            "project": request.project,
            "requested_by": request.requested_by,
            "protocol_version": built["protocol_version"],
        }

    def decide(
        self,
        *,
        request: Mapping[str, Any],
        authorization: Mapping[str, Any],
        arguments: Optional[Mapping[str, Any]] = None,
    ) -> Mapping[str, Any]:
        """Ask the guard to decide.

        The guard re-verifies everything. The agent's word about whether
        the authorization was checked is not evidence and is not used.
        """
        context = VerificationContext(
            proposal=request.get("proposal", {}),
            request=request,
            authorization=authorization,
            operation=request.get("operation", ""),
            arguments=dict(arguments or {}),
            revoked_key_ids=self._guard.revoked_key_ids,
        )
        decision = self._guard.decide(context)
        return self._adapter.to_result(decision)

    def status(self) -> Mapping[str, Any]:
        """What the agent is allowed to know about the platform.

        Deliberately thin: the allowlist's operation names and scopes, and
        nothing about the guard's internals, its verifier, or its policy.
        """
        return {
            "operations": [
                {"name": name, "scope": self._registry.scope_of(name)}
                for name in self._registry.names()
            ],
        }
