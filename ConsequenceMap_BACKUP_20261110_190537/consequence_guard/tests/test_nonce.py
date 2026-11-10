"""Regression tests for the durable transport nonce.

The Red Team's first finding was that the transport nonce set was in
memory, and therefore lost on a service restart. An agent can restart
a service, so an in-memory set reopens the transport-level replay
window on every restart.

The finding is REAL for the nonce set. It is worth being precise about
what it does and does not enable:

- the **spent set** is durable and already refuses a replayed
  *authorisation*;
- the **nonce set** refuses a replayed *request*, which is a different
  thing: a refused request never reaches the authorisation logic at
  all, and a request that is replayed with a *different* authorisation
  is caught by the authorisation checks rather than by the nonce.

So the in-memory set was a weaker defence than it should have been,
not an open door. It is now durable, and the refusal is fail-closed:
if the nonce cannot be recorded, the request is refused.
"""
from __future__ import annotations

import os
import shutil
import tempfile
import unittest

from consequence_guard.crypto import Ed25519Signer, KeyRegistry, generate_private_key
from consequence_guard.policy import GuardPolicy, PolicyOperation
from consequence_guard.protocol import build_request_message
from consequence_guard.service import GuardService
from consequence_guard.store import GuardStore


class NonceStoreTests(unittest.TestCase):
    """The nonce set itself."""

    def setUp(self):
        self.directory = tempfile.mkdtemp(prefix="cm-nonce-")
        self.path = os.path.join(self.directory, "guard.sqlite3")
        self.store = GuardStore(self.path)

    def tearDown(self):
        shutil.rmtree(self.directory, ignore_errors=True)

    def test_a_new_nonce_is_recorded(self):
        self.assertTrue(self.store.record_nonce("n-1", "2026-11-09T18:00:00.000Z"))

    def test_the_same_nonce_is_refused_the_second_time(self):
        self.store.record_nonce("n-1", "2026-11-09T18:00:00.000Z")
        self.assertFalse(self.store.record_nonce("n-1", "2026-11-09T18:00:01.000Z"))

    def test_a_nonce_survives_a_restart(self):
        self.store.record_nonce("n-1", "2026-11-09T18:00:00.000Z")
        second = GuardStore(self.path)
        self.assertFalse(second.record_nonce("n-1", "2026-11-09T18:00:01.000Z"))
        self.assertEqual(second.nonce_count(), 1)

    def test_a_seen_nonce_is_reported(self):
        self.store.record_nonce("n-1", "2026-11-09T18:00:00.000Z")
        self.assertTrue(self.store.nonce_seen("n-1"))
        self.assertFalse(self.store.nonce_seen("n-2"))


class ServiceNonceTests(unittest.TestCase):
    """The service refuses a replayed request."""

    def setUp(self):
        self.directory = tempfile.mkdtemp(prefix="cm-nonce-svc-")
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
        from consequence_map.core.authorization import (
            build_authorization,
            build_request,
        )
        from consequence_map.core.timeutil import format_rfc3339, now_utc
        from datetime import timedelta

        proposal = {"action": "a", "path": "r.md"}
        request = build_request(
            proposal=proposal, project="C", operation="file.delete",
            requested_scope=["files:write"], requested_by="agent",
            expires_at=format_rfc3339(now_utc() + timedelta(seconds=300)),
        )
        authorization = build_authorization(
            request=request, approved_scope=["files:write"], approved_by="h",
            public_key_id=self.device.public_key_id(),
            valid_from=format_rfc3339(now_utc() - timedelta(seconds=60)),
            expires_at=request["expires_at"], signature="",
        )
        authorization = dict(authorization)
        authorization["signature"] = self.device.sign(authorization)
        return build_request_message(
            nonce=nonce, operation_id="file.delete", proposal=proposal,
            authorization=authorization, requested_scope=["files:write"],
            issued_at=format_rfc3339(now_utc()),
        )

    def test_a_replayed_request_is_refused(self):
        message = self._message()
        self.service.decide(message)
        decision = self.service.decide(message)
        self.assertEqual(decision.decision, "DENY")
        self.assertIn("already been answered", decision.reason)
        self.assertEqual(len(self.calls), 1)

    def test_a_replayed_request_is_refused_after_a_restart(self):
        """The defect: the in-memory set was lost on a restart."""
        message = self._message()
        self.service.decide(message)
        restarted = GuardService(
            policy=self.policy,
            store=GuardStore(self.path),
            verifier=self.registry.verifier(),
        )
        decision = restarted.decide(message)
        self.assertEqual(decision.decision, "DENY")
        self.assertIn("already been answered", decision.reason)
        self.assertEqual(len(self.calls), 1)


if __name__ == "__main__":
    unittest.main()
