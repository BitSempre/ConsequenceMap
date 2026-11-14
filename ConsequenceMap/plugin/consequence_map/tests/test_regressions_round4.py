"""Regression tests for the fourth round: single-use authorizations.

The fourth round was run by an independent reviewer working from a
logic excerpt, and it found a defect the three earlier rounds had
missed - one that the design documents had also missed, because they
had documented a *different* risk as the residual one.

The finding: the executor's state machine guards transitions, but the
STATE is supplied by the caller. A caller that passes PREPARED again
runs the handler a second time with the same approval. The engine held
no memory of what it had already spent.

The threat model had said:

    "An authorization replayed within its validity window against the
     identical request is accepted - by design, because that is the
     same operation, approved once, still valid."

That is true of the AUTHORIZATION. It was not true of the EXECUTION.
"Approved once" had become "executed three times", which is a
different thing entirely.
"""
from __future__ import annotations

import unittest

from consequence_map.core.authorization import (
    InMemorySigner,
    InMemoryVerifier,
    build_authorization,
    build_request,
)
from consequence_map.core.execution import (
    ConsumedAuthorizations,
    ExecutionEngine,
    ExecutionRefused,
    ExecutionRequest,
    Operation,
    OperationRegistry,
    STATE_PREPARED,
)
from consequence_map.core.timeutil import format_rfc3339, now_utc

from datetime import timedelta


def _future(seconds=600):
    return format_rfc3339(now_utc() + timedelta(seconds=seconds))


def _past(seconds=60):
    return format_rfc3339(now_utc() - timedelta(seconds=seconds))


PROPOSAL = {"action": "delete the report", "resources": ["r.md"], "permissions": ["delete"]}


class SingleUseTests(unittest.TestCase):
    """An approval is good for ONE execution."""

    def setUp(self):
        self.signer = InMemorySigner("k")
        self.verifier = InMemoryVerifier({"k": self.signer._secret})
        self.request = build_request(
            proposal=PROPOSAL, project="C", operation="file.delete",
            requested_scope=["files:write"], requested_by="ag",
            expires_at=_future(),
        )
        authorization = build_authorization(
            request=self.request, approved_scope=["files:write"],
            approved_by="h", public_key_id="k", valid_from=_past(),
            expires_at=self.request["expires_at"], signature="",
        )
        self.authorization = dict(authorization)
        self.authorization["signature"] = self.signer.sign(self.authorization)
        self.calls = []
        self.registry = OperationRegistry([
            Operation("file.delete", "files:write", self._handler),
        ])
        self.engine = ExecutionEngine(self.registry, self.verifier)
        self.execution_request = ExecutionRequest(
            operation="file.delete", arguments={"path": "r.md"},
            proposal=PROPOSAL, request=self.request,
            authorization=self.authorization,
        )

    def _handler(self, arguments):
        self.calls.append(dict(arguments))
        return {"deleted": arguments.get("path")}

    def test_the_first_execution_succeeds(self):
        result = self.engine.execute(self.execution_request, state=STATE_PREPARED)
        self.assertEqual(result["state"], "EXECUTED")
        self.assertEqual(len(self.calls), 1)

    def test_the_second_execution_is_refused(self):
        self.engine.execute(self.execution_request, state=STATE_PREPARED)
        with self.assertRaises(ExecutionRefused):
            self.engine.execute(self.execution_request, state=STATE_PREPARED)

    def test_the_handler_runs_exactly_once(self):
        for _ in range(3):
            try:
                self.engine.execute(self.execution_request, state=STATE_PREPARED)
            except ExecutionRefused:
                pass
        self.assertEqual(len(self.calls), 1)

    def test_a_different_authorization_is_still_accepted(self):
        self.engine.execute(self.execution_request, state=STATE_PREPARED)
        second_request = build_request(
            proposal=PROPOSAL, project="C", operation="file.delete",
            requested_scope=["files:write"], requested_by="ag",
            expires_at=_future(),
        )
        authorization = build_authorization(
            request=second_request, approved_scope=["files:write"],
            approved_by="h", public_key_id="k", valid_from=_past(),
            expires_at=second_request["expires_at"], signature="",
        )
        authorization = dict(authorization)
        authorization["signature"] = self.signer.sign(authorization)
        other = ExecutionRequest(
            operation="file.delete", arguments={"path": "r.md"},
            proposal=PROPOSAL, request=second_request,
            authorization=authorization,
        )
        result = self.engine.execute(other, state=STATE_PREPARED)
        self.assertEqual(result["state"], "EXECUTED")
        self.assertEqual(len(self.calls), 2)

    def test_a_shared_store_survives_two_engines(self):
        """The store must be shareable - an engine that forgets on
        restart would let a captured authorization be replayed."""
        shared = ConsumedAuthorizations()
        first = ExecutionEngine(self.registry, self.verifier, consumed=shared)
        first.execute(self.execution_request, state=STATE_PREPARED)
        second = ExecutionEngine(self.registry, self.verifier, consumed=shared)
        with self.assertRaises(ExecutionRefused):
            second.execute(self.execution_request, state=STATE_PREPARED)
        self.assertEqual(len(self.calls), 1)

    def test_the_key_covers_the_id_and_the_nonce(self):
        key = ConsumedAuthorizations.key_for(self.authorization)
        self.assertIn(self.authorization["authorization_id"], key)
        self.assertIn(self.authorization["nonce"], key)

    def test_an_authorization_with_no_identity_is_refused(self):
        with self.assertRaises(ExecutionRefused):
            ConsumedAuthorizations.key_for({"approved_scope": ["files:write"]})


if __name__ == "__main__":
    unittest.main()
