"""Tests for the Security Guard decision logic.

Scenarios: T01 (the agent alters the policy), T03 (the agent grants
itself privileges), T04 (the agent fabricates an authorization), T13
(commands outside the allowlist), T15 (the agent alters the audit
records), T22 (a module accepts an invalid state).

The property under test throughout: a failure is a refusal. There is no
path where an unverifiable condition becomes an approval.
"""
from __future__ import annotations

import unittest

from consequence_map.core.audit import ChainBroken
from consequence_map.core.authorization import (
    InMemorySigner,
    InMemoryVerifier,
    build_authorization,
    build_request,
)
from consequence_map.core.execution import ExecutionRefused, Operation, OperationRegistry
from consequence_map.core.guard import (
    DECISION_ALLOW,
    DECISION_DENY,
    DECISION_INDETERMINATE,
    GuardDecision,
    SecurityGuard,
    VerificationContext,
)
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


class GuardTestCase(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.registry = OperationRegistry([
            Operation("file.delete", "files:write",
                      lambda a: self.calls.append(dict(a)) or {"deleted": True}),
            Operation("file.read", "files:read",
                      lambda a: self.calls.append(dict(a)) or {"content": "ok"}),
        ])
        self.signer = InMemorySigner("key-1")
        self.verifier = InMemoryVerifier({"key-1": self.signer._secret})
        self.guard = SecurityGuard(self.registry, self.verifier)
        # The request and the authorization must share the same expiry:
        # an authorization may not outlive the request it answers, and two
        # separately computed timestamps differ by a millisecond.
        self.expires_at = _future(900)
        self.request = build_request(
            proposal=PROPOSAL,
            project="ConsequenceMap",
            operation="file.delete",
            requested_scope=["files:write", "files:read"],
            requested_by="hermes-agent",
            expires_at=self.expires_at,
        )
        authorization = build_authorization(
            request=self.request,
            approved_scope=["files:write"],
            approved_by="human",
            public_key_id=self.signer.public_key_id(),
            valid_from=_past(),
            expires_at=self.expires_at,
            signature="",
        )
        self.authorization = dict(authorization)
        self.authorization["signature"] = self.signer.sign(self.authorization)

    def _context(self, **overrides):
        base = dict(
            proposal=PROPOSAL,
            request=self.request,
            authorization=self.authorization,
            operation="file.delete",
            arguments={"path": "reports/report.md"},
        )
        base.update(overrides)
        return VerificationContext(**base)


class GuardDecisionTests(GuardTestCase):
    def test_a_valid_request_is_allowed(self):
        decision = self.guard.decide(self._context())
        self.assertEqual(decision.decision, DECISION_ALLOW)
        self.assertTrue(decision.allowed)

    def test_every_check_is_recorded(self):
        decision = self.guard.decide(self._context())
        for name in ("operation_on_allowlist", "proposal_canonicalisable",
                     "authorization_valid", "scope_granted",
                     "no_command_arguments", "state_transition_permitted"):
            self.assertIn(name, decision.checks)
            self.assertTrue(decision.checks[name], name)

    # T13 - the agent tries to execute commands outside the allowlist
    def test_t13_an_operation_outside_the_allowlist_is_denied(self):
        decision = self.guard.decide(self._context(operation="shell.exec"))
        self.assertEqual(decision.decision, DECISION_DENY)
        self.assertFalse(decision.checks["operation_on_allowlist"])

    def test_t13_a_command_argument_is_denied(self):
        decision = self.guard.decide(
            self._context(arguments={"path": "x", "command": "calc.exe"})
        )
        self.assertEqual(decision.decision, DECISION_DENY)
        self.assertFalse(decision.checks["no_command_arguments"])

    # T04 - the agent tries to fabricate an authorization
    def test_t04_a_forged_authorization_is_denied(self):
        forged = dict(self.authorization)
        forged["signature"] = "0" * 64
        decision = self.guard.decide(self._context(authorization=forged))
        self.assertEqual(decision.decision, DECISION_DENY)
        self.assertFalse(decision.checks["authorization_valid"])

    def test_t04_a_missing_authorization_is_denied(self):
        decision = self.guard.decide(self._context(authorization={}))
        self.assertEqual(decision.decision, DECISION_DENY)

    # T03 - the agent tries to grant itself privileges
    def test_t03_an_authorization_without_the_scope_is_denied(self):
        authorization = dict(self.authorization)
        authorization["approved_scope"] = ["files:read"]
        authorization["signature"] = self.signer.sign(authorization)
        decision = self.guard.decide(self._context(authorization=authorization))
        self.assertEqual(decision.decision, DECISION_DENY)
        self.assertFalse(decision.checks["scope_granted"])

    def test_a_revoked_key_is_denied(self):
        guard = SecurityGuard(self.registry, self.verifier, revoked_key_ids=["key-1"])
        decision = guard.decide(self._context())
        self.assertEqual(decision.decision, DECISION_DENY)

    def test_an_expired_authorization_is_denied(self):
        authorization = dict(self.authorization)
        authorization["valid_from"] = _past(1200)
        authorization["expires_at"] = _past(600)
        authorization["signature"] = self.signer.sign(authorization)
        decision = self.guard.decide(self._context(authorization=authorization))
        self.assertEqual(decision.decision, DECISION_DENY)

    # T01 - the agent tries to alter the policy
    def test_t01_a_non_canonicalisable_proposal_is_denied(self):
        decision = self.guard.decide(self._context(proposal={"x": "caf\u00e9"}))
        self.assertEqual(decision.decision, DECISION_DENY)
        self.assertFalse(decision.checks["proposal_canonicalisable"])

    # T15 - the agent alters the audit records
    def test_t15_a_denial_is_recorded(self):
        self.guard.decide(self._context(operation="shell.exec"))
        self.assertEqual(len(self.guard.audit), 1)
        self.assertEqual(self.guard.audit.records[0].event, "guard.denied.allowlist")

    def test_t15_an_allowance_is_recorded(self):
        self.guard.decide(self._context())
        self.assertEqual(len(self.guard.audit), 1)
        self.assertEqual(self.guard.audit.records[0].event, "guard.allowed")

    def test_t15_the_audit_chain_detects_alteration(self):
        self.guard.decide(self._context())
        self.guard.audit.records[0].payload = {"operation": "os.system"}
        with self.assertRaises(ChainBroken):
            self.guard.audit.verify()


class IndeterminateTests(GuardTestCase):
    """The central property: an unverifiable condition is never an approval."""

    def test_an_unknown_decision_value_is_rejected(self):
        with self.assertRaises(ValueError):
            GuardDecision("MAYBE", "not a decision")

    def test_indeterminate_is_not_allowed(self):
        decision = GuardDecision(DECISION_INDETERMINATE, "could not verify")
        self.assertFalse(decision.allowed)
        self.assertNotEqual(decision.decision, DECISION_ALLOW)

    def test_a_verifier_that_raises_is_not_treated_as_allow(self):
        class _Broken:
            def verify(self, public_key_id, payload, signature):
                raise RuntimeError("the verification service is unavailable")

        guard = SecurityGuard(self.registry, _Broken())
        with self.assertRaises(Exception):
            guard.decide(self._context())
        # The operation must not have run.
        self.assertEqual(self.calls, [])

    def test_a_missing_operation_is_denied_not_ignored(self):
        decision = self.guard.decide(self._context(operation="does.not.exist"))
        self.assertEqual(decision.decision, DECISION_DENY)


class GuardExecutionTests(GuardTestCase):
    def test_execution_runs_only_after_an_allow(self):
        result = self.guard.execute(self._context())
        self.assertEqual(result["state"], "EXECUTED")
        self.assertEqual(len(self.calls), 1)

    def test_execution_refuses_when_the_guard_denies(self):
        with self.assertRaises(ExecutionRefused):
            self.guard.execute(self._context(operation="shell.exec"))
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()
