"""Regression tests for the ninth round: the operation binding and the scope.

Two defects were found by the adversarial review of the guard, and both
were confirmed by a probe before being fixed.

D-22  THE OPERATION WAS NOT BOUND TO THE SIGNATURE. The service derived
      the request from the authorisation, and the derived request's
      operation field was set to the operation the PLUGIN asked for.
      So an approval signed for "file.delete" could be presented for
      "repo.wipe", provided both needed the same scope. The probe
      executed "repo.wipe" with an approval for "file.delete" and the
      service said ALLOW.

      The authorisation now carries the operation it was made for, and
      the service refuses an approval whose operation differs from the
      one being requested.

D-23  THE SCOPE CHECK WAS VACUOUS. The derived request's scope was the
      authorisation's OWN approved scope, so verify_authorization's
      "approved is a subset of requested" compared a set with itself.
      It could not detect an approval that grants more than the
      operation needs.

      The requested scope now travels in the message, separately from
      the approval, and the approval must be a subset of THAT.
"""
from __future__ import annotations

import os
import shutil
import tempfile
import unittest

from consequence_guard.crypto import Ed25519Signer, KeyRegistry, generate_private_key
from consequence_guard.policy import GuardPolicy, PolicyOperation
from consequence_guard.protocol import (
    DECISION_ALLOW,
    DECISION_DENY,
    build_request_message,
)
from consequence_guard.service import GuardService
from consequence_guard.store import GuardStore

from consequence_map.core.authorization import build_authorization, build_request
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


class BindingTestCase(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.mkdtemp(prefix="cm-bind-")
        self.store = GuardStore(os.path.join(self.directory, "guard.sqlite3"))
        self.device = Ed25519Signer(generate_private_key())
        self.registry = KeyRegistry({self.device.public_key_id(): self.device.public_key()})
        self.calls = []
        self.policy = GuardPolicy(
            operations=[
                PolicyOperation(
                    identifier="file.delete", scope="files:write",
                    description="Delete one file.",
                    handler=self._handler, argument_map={"path": "path"},
                ),
                PolicyOperation(
                    identifier="repo.wipe", scope="files:write",
                    description="Delete the repository.",
                    handler=self._handler, argument_map={"path": "path"},
                ),
            ],
            max_validity_seconds=600,
        )
        self.service = GuardService(
            policy=self.policy, store=self.store, verifier=self.registry.verifier()
        )

    def tearDown(self):
        shutil.rmtree(self.directory, ignore_errors=True)

    def _handler(self, arguments):
        self.calls.append(dict(arguments))
        return {"ok": True}

    def _authorisation(self, operation="file.delete", scope=("files:write",)):
        request = build_request(
            proposal=PROPOSAL, project="C", operation=operation,
            requested_scope=list(scope), requested_by="agent",
            expires_at=_future(),
        )
        authorization = build_authorization(
            request=request, approved_scope=list(scope), approved_by="h",
            public_key_id=self.device.public_key_id(), valid_from=_past(),
            expires_at=request["expires_at"], signature="",
        )
        authorization = dict(authorization)
        authorization["signature"] = self.device.sign(authorization)
        return request, authorization

    def _message(self, operation_id="file.delete", authorization=None,
                 requested_scope=("files:write",), nonce="n-1"):
        if authorization is None:
            request, authorization = self._authorisation()
        return build_request_message(
            nonce=nonce, operation_id=operation_id, proposal=PROPOSAL,
            authorization=authorization, requested_scope=list(requested_scope),
            issued_at=format_rfc3339(now_utc()),
        )


class OperationBindingTests(BindingTestCase):
    """The approval is for one operation."""

    def test_an_approval_for_another_operation_is_refused(self):
        """The defect: repo.wipe executed with an approval for file.delete."""
        request, authorization = self._authorisation(operation="file.delete")
        decision = self.service.decide(
            self._message(operation_id="repo.wipe", authorization=authorization)
        )
        self.assertEqual(decision.decision, DECISION_DENY)
        self.assertIn("was made for operation", decision.reason)
        self.assertEqual(self.calls, [])

    def test_the_approval_for_the_right_operation_is_accepted(self):
        request, authorization = self._authorisation(operation="file.delete")
        decision = self.service.decide(
            self._message(operation_id="file.delete", authorization=authorization)
        )
        self.assertEqual(decision.decision, DECISION_ALLOW)
        self.assertEqual(len(self.calls), 1)

    def test_the_authorisation_carries_the_operation(self):
        request, authorization = self._authorisation(operation="file.delete")
        self.assertEqual(authorization["operation"], "file.delete")

    def test_an_authorisation_without_an_operation_is_refused(self):
        request, authorization = self._authorisation()
        stripped = dict(authorization)
        del stripped["operation"]
        # Re-sign so the signature is valid for the stripped document.
        stripped["signature"] = self.device.sign(stripped)
        decision = self.service.decide(self._message(authorization=stripped))
        self.assertEqual(decision.decision, DECISION_DENY)


class ScopeBindingTests(BindingTestCase):
    """The approval grants no more than was asked for."""

    def test_an_approval_granting_more_than_requested_is_refused(self):
        """The defect: the scope check compared a set with itself."""
        request, authorization = self._authorisation(scope=("files:write", "admin"))
        decision = self.service.decide(
            self._message(
                authorization=authorization,
                requested_scope=("files:write",),
            )
        )
        self.assertEqual(decision.decision, DECISION_DENY)
        self.assertIn("outside the requested scope", decision.reason)
        self.assertEqual(self.calls, [])

    def test_an_approval_matching_the_requested_scope_is_accepted(self):
        request, authorization = self._authorisation(scope=("files:write",))
        decision = self.service.decide(
            self._message(
                authorization=authorization,
                requested_scope=("files:write",),
            )
        )
        self.assertEqual(decision.decision, DECISION_ALLOW)

    def test_a_narrower_approval_than_requested_is_accepted(self):
        """The human may grant less than was asked. That is their right."""
        request, authorization = self._authorisation(scope=("files:write",))
        decision = self.service.decide(
            self._message(
                authorization=authorization,
                requested_scope=("files:write", "files:read"),
            )
        )
        self.assertEqual(decision.decision, DECISION_ALLOW)


if __name__ == "__main__":
    unittest.main()
