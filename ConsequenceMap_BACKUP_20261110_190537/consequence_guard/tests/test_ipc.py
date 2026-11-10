"""Tests for the transport and the plugin-side client.

The property under test is that the PLUGIN has no capability of its
own. Concretely:

- the plugin-side transport carries no boundary, and says so;
- a caller that is not on the allowlist is refused BEFORE its message
  is read;
- the client has no fallback: if the service is unreachable, the
  operation does not happen;
- the client reads the DECISION, not a separate boolean.
"""
from __future__ import annotations

import os
import shutil
import tempfile
import unittest

from consequence_guard.client import ClientUnavailable, GuardClient
from consequence_guard.crypto import Ed25519Signer, KeyRegistry, generate_private_key
from consequence_guard.ipc import (
    CallerRejected,
    InProcessTransport,
    PipeServerTransport,
    ReferenceClientAuthenticator,
)
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


class TransportTestCase(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.mkdtemp(prefix="cm-ipc-")
        self.store = GuardStore(os.path.join(self.directory, "guard.sqlite3"))
        self.device = Ed25519Signer(generate_private_key())
        self.registry = KeyRegistry({self.device.public_key_id(): self.device.public_key()})
        self.calls = []
        self.policy = GuardPolicy(
            operations=[
                PolicyOperation(
                    identifier="file.delete", scope="files:write",
                    description="Delete one file.",
                    handler=self._handler,
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
            request=request, approved_scope=["files:write"],
            approved_by="the-owner", public_key_id=self.device.public_key_id(),
            valid_from=_past(), expires_at=request["expires_at"], signature="",
        )
        authorization = dict(authorization)
        authorization["signature"] = self.device.sign(authorization)
        return build_request_message(
            nonce=nonce, operation_id="file.delete", proposal=PROPOSAL,
            authorization=authorization, requested_scope=["files:write"],
            issued_at=format_rfc3339(now_utc()),
        )


class BoundaryHonestyTests(TransportTestCase):
    """A transport says whether it provides a boundary."""

    def test_the_in_process_transport_admits_it_has_no_boundary(self):
        transport = InProcessTransport(self.service)
        self.assertFalse(transport.provides_boundary)

    def test_the_pipe_server_transport_declares_a_boundary(self):
        transport = PipeServerTransport(
            self.service,
            ReferenceClientAuthenticator({"sid": "S-1-5-21-allowed"}),
            allowed_sids=("S-1-5-21-allowed",),
        )
        self.assertTrue(transport.provides_boundary)


class CallerAuthenticationTests(TransportTestCase):
    """The pipe name proves nothing; the caller's identity does."""

    def _transport(self, sid, allowed=("S-1-5-21-allowed",)):
        return PipeServerTransport(
            self.service,
            ReferenceClientAuthenticator({"sid": sid}),
            allowed_sids=allowed,
        )

    def test_an_allowed_caller_is_accepted(self):
        transport = self._transport("S-1-5-21-allowed")
        response = transport.serve_connection(self._message())
        self.assertEqual(response["decision"], DECISION_ALLOW)
        self.assertEqual(len(self.calls), 1)

    def test_a_caller_outside_the_allowlist_is_refused(self):
        transport = self._transport("S-1-5-21-INTERACTIVE")
        with self.assertRaises(CallerRejected):
            transport.serve_connection(self._message())
        self.assertEqual(self.calls, [])

    def test_a_refused_caller_sends_no_message(self):
        """The refusal happens BEFORE the message is read."""
        transport = self._transport("S-1-5-21-INTERACTIVE")
        with self.assertRaises(CallerRejected):
            transport.serve_connection({"anything": "at all"})
        self.assertEqual(self.calls, [])

    def test_an_unauthenticatable_caller_is_refused(self):
        class _Broken:
            def authenticate(self):
                raise RuntimeError("the token could not be read")

        transport = PipeServerTransport(
            self.service, _Broken(), allowed_sids=("S-1-5-21-allowed",)
        )
        with self.assertRaises(CallerRejected):
            transport.serve_connection(self._message())
        self.assertEqual(self.calls, [])


class ClientTests(TransportTestCase):
    """The plugin proposes; it does not decide."""

    def test_the_client_receives_the_guards_decision(self):
        client = GuardClient(InProcessTransport(self.service))
        response = client.request_execution(
            nonce="n-1", operation_id="file.delete", proposal=PROPOSAL,
            authorization=self._message()["authorization"],
            requested_scope=["files:write"],
            issued_at=format_rfc3339(now_utc()),
        )
        self.assertEqual(response["decision"], DECISION_ALLOW)
        self.assertTrue(client.is_allowed(response))

    def test_the_client_has_no_fallback_when_the_service_is_unreachable(self):
        class _Dead:
            def send(self, message):
                raise OSError("the pipe is not there")

        client = GuardClient(_Dead())
        with self.assertRaises(ClientUnavailable):
            client.request_execution(
                nonce="n-1", operation_id="file.delete", proposal=PROPOSAL,
                authorization={}, requested_scope=["files:write"],
                issued_at=format_rfc3339(now_utc()),
            )
        self.assertEqual(self.calls, [])

    def test_the_client_refuses_an_unreadable_response(self):
        class _Lying:
            def send(self, message):
                return {"decision": "ALLOW", "reason": "ok", "surprise": 1}

        client = GuardClient(_Lying())
        with self.assertRaises(ClientUnavailable):
            client.request_execution(
                nonce="n-1", operation_id="file.delete", proposal=PROPOSAL,
                authorization={}, requested_scope=["files:write"],
                issued_at=format_rfc3339(now_utc()),
            )

    def test_the_client_reads_the_decision_not_a_boolean(self):
        client = GuardClient(InProcessTransport(self.service))
        self.assertFalse(client.is_allowed({"decision": DECISION_DENY}))
        self.assertFalse(client.is_allowed({"decision": "INDETERMINATE"}))
        self.assertFalse(client.is_allowed({}))


if __name__ == "__main__":
    unittest.main()
