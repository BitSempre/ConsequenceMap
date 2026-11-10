"""Regression tests for the tenth round: the operation instance identifier.

D-25  THE OPERATION_ID NAMED THE KIND OF OPERATION, NOT THE INSTANCE.

      The message's operation_id is the name in the policy's allowlist
      - "file.delete". Two executions of the same kind therefore shared
      an identifier, and the second one's state update OVERWROTE the
      first one's, because record_operation upserts by operation_id.

      That breaks the recovery guarantee. If execution A was left in
      OUTCOME_UNKNOWN by a crash, and execution B of the same kind
      completed afterwards, B's upsert would mark A as COMPLETED - and
      the platform would report an operation as finished whose effect
      may never have happened. The very failure the state machine
      exists to prevent.

      The instance identifier is now the service's own, derived from
      the authorisation: unique per approval, because the approval is
      unique.
"""
from __future__ import annotations

import os
import shutil
import tempfile
import unittest

from consequence_guard.crypto import Ed25519Signer, KeyRegistry, generate_private_key
from consequence_guard.policy import GuardPolicy, PolicyOperation
from consequence_guard.protocol import build_request_message
from consequence_guard.recovery_after_crash import recover_operations
from consequence_guard.service import GuardService
from consequence_guard.store import GuardStore, OperationState

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


class InstanceIdentifierTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.mkdtemp(prefix="cm-inst-")
        self.path = os.path.join(self.directory, "guard.sqlite3")
        self.store = GuardStore(self.path)
        self.device = Ed25519Signer(generate_private_key())
        self.registry = KeyRegistry({self.device.public_key_id(): self.device.public_key()})
        self.calls = []
        self.policy = GuardPolicy(
            operations=[
                PolicyOperation(
                    identifier="file.delete", scope="files:write",
                    description="d", handler=self._handler,
                    argument_map={"path": "path"},
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

    def _message(self, nonce="n-1"):
        request = build_request(
            proposal=PROPOSAL, project="C", operation="file.delete",
            requested_scope=["files:write"], requested_by="agent",
            expires_at=_future(),
        )
        authorization = build_authorization(
            request=request, approved_scope=["files:write"], approved_by="h",
            public_key_id=self.device.public_key_id(), valid_from=_past(),
            expires_at=request["expires_at"], signature="",
        )
        authorization = dict(authorization)
        authorization["signature"] = self.device.sign(authorization)
        return build_request_message(
            nonce=nonce, operation_id="file.delete", proposal=PROPOSAL,
            authorization=authorization, requested_scope=["files:write"],
            issued_at=format_rfc3339(now_utc()),
        )

    def test_two_executions_of_the_same_operation_get_separate_records(self):
        """The defect: both executions shared one state row."""
        self.service.decide(self._message("n-1"))
        self.service.decide(self._message("n-2"))
        self.assertEqual(len(self.calls), 2)
        completed = self.store.operations_in_state(OperationState.COMPLETED)
        self.assertEqual(
            len(completed), 2,
            "each execution must have its own state record, got %r" % (completed,),
        )

    def test_the_records_have_different_identifiers(self):
        self.service.decide(self._message("n-1"))
        self.service.decide(self._message("n-2"))
        completed = self.store.operations_in_state(OperationState.COMPLETED)
        identifiers = {entry["operation_id"] for entry in completed}
        self.assertEqual(len(identifiers), 2)

    def test_an_unknown_outcome_is_not_overwritten_by_a_later_execution(self):
        """The guarantee the state machine exists to protect.

        Execution A is left EXECUTION_STARTED by a crash. Execution B
        of the same kind runs afterwards. A must still be uncertain.
        """
        self.service.decide(self._message("n-1"))
        instance = self.store.operations_in_state(OperationState.COMPLETED)[0]
        # Simulate a crash on a DIFFERENT execution of the same kind.
        self.store.record_operation(
            operation_id="op:crashed:nonce", state=OperationState.EXECUTION_STARTED,
            request_id="r", authorization_id="a", operation="file.delete",
            proposal_hash="h", now=format_rfc3339(now_utc()),
        )
        # A later execution of the same kind completes.
        self.service.decide(self._message("n-2"))
        # Recovery classifies the crashed one, and the completed one
        # is untouched.
        recover_operations(self.store)
        self.assertEqual(
            self.store.operation_state("op:crashed:nonce"),
            OperationState.OUTCOME_UNKNOWN,
        )
        self.assertEqual(
            self.store.operation_state(instance["operation_id"]),
            OperationState.COMPLETED,
        )


if __name__ == "__main__":
    unittest.main()
