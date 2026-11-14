"""Tests for the agent surface.

The property under test: the agent can PROPOSE and ASK, and nothing else.
In particular it cannot approve its own proposal, and it cannot widen
the allowlist.
"""
from __future__ import annotations

import unittest

from consequence_map.core.agent import (
    AgentRequestRejected,
    AgentSurface,
    HermesAdapter,
)
from consequence_map.core.authorization import (
    InMemorySigner,
    InMemoryVerifier,
    build_authorization,
)
from consequence_map.core.execution import Operation, OperationRegistry
from consequence_map.core.guard import SecurityGuard
from consequence_map.core.timeutil import format_rfc3339, now_utc

from datetime import timedelta


def _future(seconds=600):
    return format_rfc3339(now_utc() + timedelta(seconds=seconds))


def _past(seconds=60):
    return format_rfc3339(now_utc() - timedelta(seconds=seconds))


PROPOSAL = {
    "action": "delete the report file",
    "resources": ["reports/report.md"],
    "permissions": ["delete"],
}


class AgentSurfaceTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.registry = OperationRegistry([
            Operation("file.delete", "files:write",
                      lambda a: self.calls.append(dict(a)) or {"deleted": True}),
        ])
        self.signer = InMemorySigner("key-1")
        self.verifier = InMemoryVerifier({"key-1": self.signer._secret})
        self.guard = SecurityGuard(self.registry, self.verifier)
        self.adapter = HermesAdapter()
        self.surface = AgentSurface(self.guard, self.adapter)

    def _raw(self, **overrides):
        base = dict(
            tool="file.delete",
            arguments={"path": "reports/report.md"},
            proposal=PROPOSAL,
            project="ConsequenceMap",
            scope=["files:write"],
            actor="hermes-agent",
            expires_at=_future(900),
            summary="delete one report file",
        )
        base.update(overrides)
        return base

    # -- propose -------------------------------------------------------

    def test_propose_returns_a_request_with_the_proposal_hash(self):
        request = self.surface.propose(self._raw())
        self.assertEqual(len(request["proposal_hash"]), 64)
        self.assertEqual(len(request["nonce"]), 64)
        self.assertIn("proposal", request)

    def test_propose_carries_the_real_proposal_for_the_human(self):
        request = self.surface.propose(self._raw())
        self.assertEqual(request["proposal"], PROPOSAL)

    def test_each_request_gets_a_distinct_nonce(self):
        first = self.surface.propose(self._raw())
        second = self.surface.propose(self._raw())
        self.assertNotEqual(first["nonce"], second["nonce"])

    def test_propose_rejects_an_operation_outside_the_allowlist(self):
        with self.assertRaises(AgentRequestRejected):
            self.surface.propose(self._raw(tool="shell.exec"))

    def test_propose_rejects_a_request_without_a_proposal(self):
        raw = self._raw()
        del raw["proposal"]
        with self.assertRaises(AgentRequestRejected):
            self.surface.propose(raw)

    def test_propose_rejects_a_non_canonicalisable_proposal(self):
        with self.assertRaises(AgentRequestRejected):
            self.surface.propose(self._raw(proposal={"x": "caf\u00e9"}))

    def test_propose_rejects_a_request_without_an_expiry(self):
        with self.assertRaises(AgentRequestRejected):
            self.surface.propose(self._raw(expires_at=""))

    def test_propose_rejects_non_mapping_arguments(self):
        with self.assertRaises(AgentRequestRejected):
            self.surface.propose(self._raw(arguments=["a"]))

    # -- decide --------------------------------------------------------

    def _authorization(self, request, scope=("files:write",)):
        authorization = build_authorization(
            request=request,
            approved_scope=list(scope),
            approved_by="human",
            public_key_id=self.signer.public_key_id(),
            valid_from=_past(),
            expires_at=request["expires_at"],
            signature="",
        )
        authorization = dict(authorization)
        authorization["signature"] = self.signer.sign(authorization)
        return authorization

    def test_a_valid_authorization_is_allowed(self):
        request = self.surface.propose(self._raw())
        authorization = self._authorization(request)
        result = self.surface.decide(
            request=request, authorization=authorization,
            arguments={"path": "reports/report.md"},
        )
        self.assertTrue(result["allowed"])
        self.assertEqual(result["decision"], "ALLOW")

    def test_a_forged_authorization_is_denied(self):
        request = self.surface.propose(self._raw())
        authorization = self._authorization(request)
        authorization = dict(authorization)
        authorization["signature"] = "0" * 64
        result = self.surface.decide(request=request, authorization=authorization)
        self.assertFalse(result["allowed"])
        self.assertEqual(result["decision"], "DENY")

    def test_the_agent_cannot_approve_by_asserting_it(self):
        # The agent supplies an "approval" that it produced itself.
        request = self.surface.propose(self._raw())
        forged = dict(request)
        forged["approved_by"] = "human"
        forged["signature"] = "0" * 64
        result = self.surface.decide(request=request, authorization=forged)
        self.assertFalse(result["allowed"])

    def test_an_expired_request_is_denied(self):
        request = self.surface.propose(self._raw(expires_at=_past(1200)))
        authorization = self._authorization(request)
        result = self.surface.decide(request=request, authorization=authorization)
        self.assertFalse(result["allowed"])

    # -- status --------------------------------------------------------

    def test_status_exposes_only_the_allowlist(self):
        status = self.surface.status()
        self.assertEqual(status["operations"], [
            {"name": "file.delete", "scope": "files:write"}
        ])

    def test_status_leaks_nothing_about_the_guard(self):
        status = str(self.surface.status())
        for forbidden in ("verifier", "revoked", "policy", "secret", "key-1"):
            self.assertNotIn(forbidden, status)


if __name__ == "__main__":
    unittest.main()
