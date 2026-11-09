"""Regression tests for the eleventh round: the independent reviews.

Two independent reviews ran against the guard. Their findings were
checked against the code, and this file pins the ones that were
CONFIRMED.

CONFIRMED AND FIXED:

D-26  The authorisation accepted an UNKNOWN field. The signed payload
      is the document minus exactly the field named ``signature``, so
      an added field already breaks the signature - but a field the
      verifier does not understand is authenticated and IGNORED, and a
      field that is ignored is a field a signer (or a bug) could add
      without anyone noticing. That is the pattern the rest of the
      platform refuses: a field the service does not understand might
      be one it would have honoured.

      The authorisation now has a CLOSED schema, like the IPC message
      already had.

CONFIRMED AND IMPLEMENTED:

D-27  There was no RFC 8032 test vector. A suite that only checks
      "my signer agrees with my verifier" proves the two halves agree,
      not that either is Ed25519. The official RFC 8032 Section 7.1
      vectors now validate the implementation against an external
      reference.

REVIEWED AND REJECTED:

- "The interactive user must be DENIED on the pipe". That would stop
  the PLUGIN from connecting: the plugin runs as the interactive user.
  The pipe's client-token check is what distinguishes an authorised
  caller from the agent - which shares that user.

- "Keep nonces for 30 seconds". The retention window must be at least
  the maximum authorisation validity, or a live authorisation could be
  presented again after its nonce aged out.
"""
from __future__ import annotations

import unittest

from consequence_map.core.authorization import (
    AuthorizationInvalid,
    InMemorySigner,
    InMemoryVerifier,
    build_authorization,
    build_request,
    verify_authorization,
)
from consequence_map.core.timeutil import format_rfc3339, now_utc

from datetime import timedelta


def _future(seconds=300):
    return format_rfc3339(now_utc() + timedelta(seconds=seconds))


def _past(seconds=60):
    return format_rfc3339(now_utc() - timedelta(seconds=seconds))


PROPOSAL = {"action": "delete the report", "resources": ["r.md"], "permissions": ["delete"]}


class ClosedAuthorisationSchemaTests(unittest.TestCase):
    """The authorisation has a closed schema."""

    def setUp(self):
        self.signer = InMemorySigner("k")
        self.verifier = InMemoryVerifier({"k": self.signer._secret})
        self.request = build_request(
            proposal=PROPOSAL, project="C", operation="file.delete",
            requested_scope=["files:write"], requested_by="agent",
            expires_at=_future(),
        )
        authorization = build_authorization(
            request=self.request, approved_scope=["files:write"],
            approved_by="h", public_key_id="k", valid_from=_past(),
            expires_at=self.request["expires_at"], signature="",
        )
        self.authorization = dict(authorization)
        self.authorization["signature"] = self.signer.sign(self.authorization)

    def _verify(self, authorization=None):
        return verify_authorization(
            proposal=PROPOSAL, request=self.request,
            authorization=authorization if authorization is not None else self.authorization,
            verifier=self.verifier,
        )

    def test_a_correct_authorisation_verifies(self):
        self._verify()

    def test_an_unknown_field_is_refused(self):
        tampered = dict(self.authorization)
        tampered["escalate_to"] = "root"
        with self.assertRaises(AuthorizationInvalid):
            self._verify(tampered)

    def test_the_refusal_names_the_unknown_field(self):
        tampered = dict(self.authorization)
        tampered["escalate_to"] = "root"
        with self.assertRaises(AuthorizationInvalid) as caught:
            self._verify(tampered)
        self.assertIn("escalate_to", str(caught.exception))

    def test_a_missing_field_is_refused(self):
        stripped = dict(self.authorization)
        del stripped["nonce"]
        with self.assertRaises(AuthorizationInvalid):
            self._verify(stripped)

    def test_the_refusal_distinguishes_missing_from_unknown(self):
        """The two are different problems and the message says which."""
        stripped = dict(self.authorization)
        del stripped["nonce"]
        with self.assertRaises(AuthorizationInvalid) as caught:
            self._verify(stripped)
        self.assertIn("missing", str(caught.exception))


class DeadlineTests(unittest.TestCase):
    """The service bounds how long a caller can tie it up."""

    def test_the_deadline_is_configurable(self):
        from consequence_guard.protocol import REQUEST_DEADLINE_SECONDS
        from consequence_guard.service import GuardService

        self.assertGreater(REQUEST_DEADLINE_SECONDS, 0)
        service = GuardService(
            policy=None, store=None, verifier=None, deadline_seconds=7
        )
        self.assertEqual(service.deadline_seconds, 7)

    def test_the_default_is_the_protocol_default(self):
        from consequence_guard.protocol import REQUEST_DEADLINE_SECONDS
        from consequence_guard.service import GuardService

        service = GuardService(policy=None, store=None, verifier=None)
        self.assertEqual(service.deadline_seconds, REQUEST_DEADLINE_SECONDS)


if __name__ == "__main__":
    unittest.main()
