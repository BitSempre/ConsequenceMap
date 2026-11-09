"""Tests for the Security Guard service.

The central test in this file is the one the whole platform exists
for:

    **The agent cannot grant itself authorisation.**

That is tested by having the "agent" act as the plugin: it sends a
request with a forged authorisation, one signed by a key it holds, one
that names an operation that is not in the allowlist, and one that
carries a decision field of its own. Every one is refused.

The rest of the file covers the fail-closed paths: an unavailable
store, an unknown operation, an expired authorisation, a replay, and a
handler that fails.
"""
from __future__ import annotations

import os
import shutil
import tempfile
import unittest

from consequence_guard.crypto import (
    Ed25519Signer,
    KeyRegistry,
    generate_private_key,
)
from consequence_guard.policy import GuardPolicy, PolicyOperation
from consequence_guard.protocol import (
    DECISION_ALLOW,
    DECISION_DENY,
    build_request_message,
)
from consequence_guard.service import GuardService
from consequence_guard.store import GuardStore, OperationState

from consequence_map.core.authorization import (
    build_authorization,
    build_request,
)
from consequence_map.core.timeutil import format_rfc3339, now_utc

from datetime import timedelta


def _future(seconds=300):
    return format_rfc3339(now_utc() + timedelta(seconds=seconds))


def _past(seconds=60):
    return format_rfc3339(now_utc() - timedelta(seconds=seconds))


PROPOSAL = {
    "action": "delete the quarterly report",
    "resources": ["reports/q3.md"],
    "permissions": ["delete"],
    "path": "reports/q3.md",
}


class GuardTestCase(unittest.TestCase):
    """A service with one permitted operation and one trusted device."""

    def setUp(self):
        self.directory = tempfile.mkdtemp(prefix="cm-svc-")
        self.store = GuardStore(os.path.join(self.directory, "guard.sqlite3"))
        self.device_key = generate_private_key()
        self.device = Ed25519Signer(self.device_key)
        self.registry = KeyRegistry({
            self.device.public_key_id(): self.device.public_key(),
        })
        self.policy = GuardPolicy(
            operations=[
                PolicyOperation(
                    identifier="file.delete",
                    scope="files:write",
                    description="Delete one file.",
                    handler=self._handler,
                    argument_map={"path": "path"},
                ),
                PolicyOperation(
                    identifier="report.read",
                    scope="files:read",
                    description="Read a report.",
                    handler=self._handler,
                    argument_map={"path": "path"},
                ),
            ],
            max_validity_seconds=600,
            clock_skew_seconds=30,
        )
        self.service = GuardService(
            policy=self.policy, store=self.store, verifier=self.registry.verifier()
        )
        self.calls = []

    def tearDown(self):
        shutil.rmtree(self.directory, ignore_errors=True)

    def _handler(self, arguments):
        self.calls.append(dict(arguments))
        return {"ok": True}

    def _authorisation(self, scope=("files:write",), signer=None, proposal=None):
        """Build a valid authorisation, signed by the trusted device."""
        signer = signer or self.device
        request = build_request(
            proposal=proposal if proposal is not None else PROPOSAL,
            project="ConsequenceMap", operation="file.delete",
            requested_scope=list(scope), requested_by="agent",
            expires_at=_future(),
        )
        authorization = build_authorization(
            request=request, approved_scope=list(scope),
            approved_by="the-owner", public_key_id=signer.public_key_id(),
            valid_from=_past(), expires_at=request["expires_at"], signature="",
        )
        authorization = dict(authorization)
        authorization["signature"] = signer.sign(authorization)
        return request, authorization

    def _request(self, **overrides):
        request, authorization = self._authorisation()
        message = build_request_message(
            nonce=overrides.pop("nonce", "nonce-1"),
            operation_id=overrides.pop("operation_id", "file.delete"),
            proposal=overrides.pop("proposal", PROPOSAL),
            authorization=overrides.pop("authorization", authorization),
            issued_at=overrides.pop("issued_at", format_rfc3339(now_utc())),
        )
        message.update(overrides)
        return message


class SelfAuthorisationTests(GuardTestCase):
    """The agent cannot grant itself authorisation."""

    def test_a_request_with_a_forged_signature_is_refused(self):
        request, authorization = self._authorisation()
        forged = dict(authorization)
        forged["signature"] = "A" * 86
        message = self._request(authorization=forged)
        decision = self.service.decide(message)
        self.assertEqual(decision.decision, DECISION_DENY)

    def test_a_request_signed_by_an_unknown_key_is_refused(self):
        rogue = Ed25519Signer(generate_private_key())
        request, authorization = self._authorisation(signer=rogue)
        message = self._request(authorization=authorization)
        decision = self.service.decide(message)
        self.assertEqual(decision.decision, DECISION_DENY)

    def test_a_request_that_carries_its_own_decision_is_refused(self):
        """The plugin may not send a decision. The field is unknown."""
        request, authorization = self._authorisation()
        message = self._request(authorization=authorization)
        message["decision"] = "ALLOW"
        message["allowed"] = True
        decision = self.service.decide(message)
        self.assertEqual(decision.decision, DECISION_DENY)
        self.assertIn("unknown field", decision.reason)

    def test_a_request_for_an_operation_outside_the_allowlist_is_refused(self):
        request, authorization = self._authorisation()
        message = self._request(
            operation_id="os.system", authorization=authorization
        )
        decision = self.service.decide(message)
        self.assertEqual(decision.decision, DECISION_DENY)
        self.assertIn("not permitted", decision.reason)

    def test_a_request_with_a_scope_the_operation_does_not_need_is_refused(self):
        """The authorisation grants files:write, but the operation is
        file.delete, whose scope IS files:write - so this one is
        allowed. The read operation must not be executed with a
        write authorisation."""
        request, authorization = self._authorisation(scope=("files:read",))
        message = self._request(
            operation_id="file.delete", authorization=authorization
        )
        decision = self.service.decide(message)
        self.assertEqual(decision.decision, DECISION_DENY)
        self.assertIn("does not include", decision.reason)

    def test_an_expired_authorisation_is_refused(self):
        request = build_request(
            proposal=PROPOSAL, project="C", operation="file.delete",
            requested_scope=["files:write"], requested_by="agent",
            expires_at=_future(),
        )
        authorization = build_authorization(
            request=request, approved_scope=["files:write"],
            approved_by="the-owner", public_key_id=self.device.public_key_id(),
            valid_from=_past(600), expires_at=_past(30), signature="",
        )
        authorization = dict(authorization)
        authorization["signature"] = self.device.sign(authorization)
        message = self._request(authorization=authorization)
        decision = self.service.decide(message)
        self.assertEqual(decision.decision, DECISION_DENY)

    def test_a_tampered_proposal_is_refused(self):
        request, authorization = self._authorisation()
        tampered = dict(PROPOSAL)
        tampered["resources"] = ["reports/q3.md", "secrets/keys.txt"]
        message = self._request(proposal=tampered, authorization=authorization)
        decision = self.service.decide(message)
        self.assertEqual(decision.decision, DECISION_DENY)
        self.assertEqual(len(self.calls), 0)

    def test_the_handler_does_not_run_on_any_refusal(self):
        for message in (
            self._request(authorization=dict(self._authorisation()[1], signature="A" * 86)),
            self._request(operation_id="os.system"),
        ):
            self.service.decide(message)
        self.assertEqual(self.calls, [])


class HappyPathTests(GuardTestCase):
    """A valid request runs exactly one operation."""

    def test_a_valid_request_is_allowed(self):
        message = self._request()
        decision = self.service.decide(message)
        self.assertEqual(decision.decision, DECISION_ALLOW)
        self.assertEqual(len(self.calls), 1)

    def test_the_handler_receives_the_derived_arguments(self):
        self.service.decide(self._request())
        self.assertEqual(self.calls, [{"path": "reports/q3.md"}])

    def test_the_handler_does_not_receive_unlisted_proposal_fields(self):
        proposal = dict(PROPOSAL)
        proposal["secret_injected"] = "value"
        request, authorization = self._authorisation(proposal=proposal)
        message = self._request(proposal=proposal, authorization=authorization)
        self.service.decide(message)
        self.assertNotIn("secret_injected", self.calls[0])

    def test_the_operation_is_recorded_as_completed(self):
        message = self._request()
        self.service.decide(message)
        self.assertEqual(
            self.store.operation_state("file.delete"), OperationState.COMPLETED
        )

    def test_the_audit_records_the_attempt(self):
        self.service.decide(self._request())
        events = [r["event"] for r in self.store.audit_records()]
        self.assertIn("guard.request.accepted", events)
        self.assertIn("guard.operation.completed", events)

    def test_a_replayed_request_is_refused(self):
        message = self._request()
        self.service.decide(message)
        decision = self.service.decide(message)
        self.assertEqual(decision.decision, DECISION_DENY)
        self.assertIn("already been answered", decision.reason)
        self.assertEqual(len(self.calls), 1)

    def test_the_same_authorisation_under_a_new_nonce_is_refused(self):
        """The transport nonce is not the only defence.

        A second request with a fresh transport nonce carries the SAME
        authorisation, and the spent set refuses it.
        """
        request, authorization = self._authorisation()
        self.service.decide(self._request(nonce="n-1", authorization=authorization))
        decision = self.service.decide(self._request(nonce="n-2", authorization=authorization))
        self.assertEqual(decision.decision, DECISION_DENY)
        self.assertIn("already consumed", decision.reason)
        self.assertEqual(len(self.calls), 1)


class FailClosedTests(GuardTestCase):
    """Nothing runs when the service cannot account for it."""

    def test_an_unavailable_store_refuses_the_operation(self):
        broken = GuardService(
            policy=self.policy,
            store=self._broken_store(),
            verifier=self.registry.verifier(),
        )
        decision = broken.decide(self._request())
        self.assertEqual(decision.decision, DECISION_DENY)
        self.assertEqual(len(self.calls), 0)

    def _broken_store(self):
        class _Broken:
            def append_audit(self, *args, **kwargs):
                from consequence_guard.store import StoreUnavailable
                raise StoreUnavailable("the disk is full")

            def record_operation(self, *args, **kwargs):
                from consequence_guard.store import StoreUnavailable
                raise StoreUnavailable("the disk is full")

            def consume(self, *args, **kwargs):
                from consequence_guard.store import StoreUnavailable
                raise StoreUnavailable("the disk is full")
        return _Broken()

    def test_a_failing_handler_leaves_the_operation_failed_not_completed(self):
        def failing(arguments):
            raise RuntimeError("the file was locked")
        policy = GuardPolicy(
            operations=[
                PolicyOperation(
                    identifier="file.delete", scope="files:write",
                    description="d", handler=failing,
                    argument_map={"path": "path"},
                ),
            ],
            max_validity_seconds=600,
        )
        service = GuardService(
            policy=policy, store=self.store, verifier=self.registry.verifier()
        )
        decision = service.decide(self._request())
        self.assertEqual(decision.decision, DECISION_DENY)
        self.assertEqual(
            self.store.operation_state("file.delete"), OperationState.FAILED
        )

    def test_handle_safe_turns_any_failure_into_a_refusal(self):
        response = self.service.handle_safe(object())
        self.assertEqual(response["decision"], DECISION_DENY)


if __name__ == "__main__":
    unittest.main()
