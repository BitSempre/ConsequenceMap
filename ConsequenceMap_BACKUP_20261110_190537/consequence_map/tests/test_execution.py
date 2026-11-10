"""Adversarial tests for the controlled execution engine.

Scenarios: T13 (commands outside the allowlist), T14 (bypassing the
authorization), T16 (the agent's account touching protected files), T22 (a
module accepting an invalid state), T23 (the operation changed after
approval), T11 (the security service unavailable).
"""
from __future__ import annotations

import unittest

from consequence_map.core.authorization import (
    InMemorySigner,
    InMemoryVerifier,
    build_authorization,
    build_request,
    verify_authorization,
)
from consequence_map.core.execution import (
    ALLOWED_TRANSITIONS,
    STATE_APPROVED,
    STATE_BLOCKED,
    STATE_EXECUTING,
    STATE_EXPIRED,
    STATE_EXECUTED,
    STATE_FAILED,
    STATE_PREPARED,
    STATE_REJECTED,
    STATE_REQUIRES_HUMAN_APPROVAL,
    ExecutionBlocked,
    ExecutionEngine,
    ExecutionRefused,
    ExecutionRequest,
    Operation,
    OperationRegistry,
)
from consequence_map.core.timeutil import format_rfc3339, now_utc

from datetime import timedelta


def _future(seconds=600):
    return format_rfc3339(now_utc() + timedelta(seconds=seconds))


def _past(seconds=600):
    return format_rfc3339(now_utc() - timedelta(seconds=seconds))


PROPOSAL = {
    "action": "delete the report file",
    "resources": ["reports/report.md"],
    "permissions": ["delete"],
}


class ExecutionTestCase(unittest.TestCase):
    def setUp(self):
        self.calls = []

        def _delete(arguments):
            self.calls.append(dict(arguments))
            return {"deleted": arguments.get("path")}

        def _read(arguments):
            self.calls.append(dict(arguments))
            return {"content": "ok"}

        self.registry = OperationRegistry([
            Operation("file.delete", "files:write", _delete, "Delete one file"),
            Operation("file.read", "files:read", _read, "Read one file"),
        ])
        self.signer = InMemorySigner("key-1")
        self.verifier = InMemoryVerifier({"key-1": self.signer._secret})
        self.engine = ExecutionEngine(self.registry, self.verifier)

    def _request(self, **overrides):
        # The request and the authorization share one expiry: an
        # authorization may not outlive the request it answers, and two
        # separately computed timestamps differ by a millisecond.
        expires_at = _future(900)
        request = build_request(
            proposal=PROPOSAL,
            project="ConsequenceMap",
            operation="file.delete",
            requested_scope=["files:write", "files:read"],
            requested_by="hermes-agent",
            expires_at=expires_at,
        )
        authorization = build_authorization(
            request=request,
            approved_scope=["files:write"],
            approved_by="human",
            public_key_id=self.signer.public_key_id(),
            valid_from=_past(60),
            expires_at=expires_at,
            signature="",
        )
        authorization = dict(authorization)
        authorization["signature"] = self.signer.sign(authorization)
        base = dict(
            operation="file.delete",
            arguments={"path": "reports/report.md"},
            proposal=PROPOSAL,
            request=request,
            authorization=authorization,
        )
        base.update(overrides)
        return ExecutionRequest(**base)


class AllowlistTests(ExecutionTestCase):
    # T13 - the agent tries to execute commands outside the allowlist
    def test_t13_an_unregistered_operation_is_refused(self):
        request = self._request(operation="shell.exec")
        with self.assertRaises(ExecutionRefused):
            self.engine.execute(request)

    def test_t13_no_operation_accepts_a_command_string(self):
        for argument in ("command", "cmd", "shell", "script", "argv"):
            request = self._request(arguments={"path": "x", argument: "calc.exe"})
            with self.assertRaises(ExecutionRefused):
                self.engine.execute(request)

    def test_t13_the_registry_is_exhaustive_and_closed(self):
        self.assertEqual(self.registry.names(), ("file.delete", "file.read"))
        with self.assertRaises(ExecutionRefused):
            self.registry.get("os.system")

    def test_t13_duplicate_registration_is_refused(self):
        with self.assertRaises(ValueError):
            self.registry.register(
                Operation("file.delete", "files:write", lambda a: None)
            )

    def test_t13_arguments_must_be_a_mapping(self):
        request = self._request(arguments=["file.txt"])
        with self.assertRaises(ExecutionRefused):
            self.engine.execute(request)


class AuthorizationBindingTests(ExecutionTestCase):
    # T14 - the agent tries to bypass the authorization
    def test_t14_execution_without_a_valid_authorization_is_refused(self):
        request = self._request(authorization={"forged": True})
        with self.assertRaises(ExecutionRefused):
            self.engine.execute(request)

    def test_t14_a_tampered_signature_is_refused(self):
        request = self._request()
        authorization = dict(request.authorization)
        authorization["signature"] = "0" * 64
        request.authorization = authorization
        with self.assertRaises(ExecutionRefused):
            self.engine.execute(request)

    # T23 - the operation changed after the authorization
    def test_t23_a_changed_proposal_is_refused(self):
        request = self._request()
        request.proposal = dict(PROPOSAL)
        request.proposal["action"] = "delete the whole repository"
        with self.assertRaises(ExecutionRefused):
            self.engine.execute(request)

    def test_t23_an_argument_outside_the_approved_operation_is_refused(self):
        # The authorization grants file.delete; asking for a different
        # operation under the same authorization must not work.
        request = self._request(operation="file.read")
        with self.assertRaises(ExecutionRefused):
            self.engine.execute(request)

    def test_an_authorization_without_the_operation_scope_is_refused(self):
        request = self._request()
        authorization = dict(request.authorization)
        authorization["approved_scope"] = ["files:read"]
        authorization["signature"] = self.signer.sign(authorization)
        request.authorization = authorization
        with self.assertRaises(ExecutionRefused):
            self.engine.execute(request)

    def test_a_revoked_key_is_refused_at_execution_time(self):
        engine = ExecutionEngine(
            self.registry, self.verifier, revoked_key_ids=["key-1"]
        )
        with self.assertRaises(ExecutionRefused):
            engine.execute(self._request())

    def test_an_expired_authorization_is_refused_at_execution_time(self):
        request = self._request()
        authorization = dict(request.authorization)
        authorization["valid_from"] = _past(1200)
        authorization["expires_at"] = _past(600)
        authorization["signature"] = self.signer.sign(authorization)
        request.authorization = authorization
        with self.assertRaises(ExecutionRefused):
            self.engine.execute(request)


class StateMachineTests(ExecutionTestCase):
    # T22 - a module accepts an invalid state from another module
    def test_t22_an_undeclared_transition_is_refused(self):
        self.assertFalse(ExecutionEngine.can_transition(STATE_REJECTED, STATE_APPROVED))
        self.assertFalse(ExecutionEngine.can_transition(STATE_BLOCKED, STATE_EXECUTING))
        self.assertFalse(ExecutionEngine.can_transition(STATE_EXECUTED, STATE_EXECUTING))
        with self.assertRaises(ExecutionRefused):
            ExecutionEngine.transition(STATE_REJECTED, STATE_APPROVED)

    def test_t22_terminal_states_have_no_outgoing_transitions(self):
        for state in (STATE_REJECTED, STATE_BLOCKED, STATE_EXECUTED, STATE_FAILED,
                      STATE_EXPIRED):
            self.assertEqual(ALLOWED_TRANSITIONS[state], (), state)

    def test_the_happy_path_executes(self):
        result = self.engine.execute(self._request())
        self.assertEqual(result["state"], STATE_EXECUTED)
        self.assertEqual(result["result"], {"deleted": "reports/report.md"})
        self.assertEqual(len(self.calls), 1)

    def test_a_failing_operation_reports_failed_not_executed(self):
        def _boom(arguments):
            raise RuntimeError("disk on fire")

        registry = OperationRegistry([
            Operation("file.delete", "files:write", _boom)
        ])
        engine = ExecutionEngine(registry, self.verifier)
        request = self._request()
        result = engine.execute(request)
        self.assertEqual(result["state"], STATE_FAILED)
        self.assertIn("disk on fire", result["error"])

    def test_a_blocked_operation_is_reported_as_blocked(self):
        def _blocked(arguments):
            raise ExecutionBlocked("the file is locked")

        registry = OperationRegistry([
            Operation("file.delete", "files:write", _blocked)
        ])
        engine = ExecutionEngine(registry, self.verifier)
        with self.assertRaises(ExecutionBlocked):
            engine.execute(self._request())


class NoTrustInCallerTests(ExecutionTestCase):
    # T11 - the security service is unavailable
    def test_t11_a_missing_verifier_refuses_rather_than_allowing(self):
        class _BrokenVerifier:
            def verify(self, public_key_id, payload, signature):
                raise RuntimeError("the verification service is down")

        engine = ExecutionEngine(self.registry, _BrokenVerifier())
        with self.assertRaises(Exception):
            engine.execute(self._request())
        self.assertEqual(self.calls, [], "the operation must not have run")


if __name__ == "__main__":
    unittest.main()
