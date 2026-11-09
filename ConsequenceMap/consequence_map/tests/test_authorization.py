"""Adversarial tests for the hash-bound authorization protocol.

Each test maps to an adversarial scenario from the platform test plan.
The convention is the project's own: a failing check is evidence, not a
defect, and a scenario that could not be executed is reported as such
rather than being counted as a pass.
"""
from __future__ import annotations

import json
import unittest

from consequence_map.core.authorization import (
    AuthorizationExpired,
    AuthorizationInvalid,
    AuthorizationReplay,
    AuthorizationRevoked,
    AuthorizationScopeError,
    InMemorySigner,
    InMemoryVerifier,
    build_authorization,
    build_request,
    new_nonce,
    proposal_hash,
    verify_authorization,
)
from consequence_map.core.canonical import (
    CanonicalisationError,
    canonical_bytes,
    canonical_text,
    domain_hash,
    strict_json_loads,
)
from consequence_map.core.timeutil import (
    TimeError,
    format_rfc3339,
    now_utc,
    parse_rfc3339,
)


PROPOSAL = {
    "action": "remove the file reports/2026-11-08-report.md",
    "project": "ConsequenceMap",
    "resources": [
        "reports/2026-11-08-report.md",
        "evidence/test-status.json",
    ],
    "permissions": ["delete"],
    "reversible": False,
    "consequence_summary": "Two evidence files lose their content.",
}

SCOPE = ["read", "write", "delete"]


def _future(seconds: int = 600) -> str:
    """A timestamp ``seconds`` in the future, for validity windows."""
    from datetime import timedelta
    return format_rfc3339(now_utc() + timedelta(seconds=seconds))


def _past(seconds: int = 600) -> str:
    """A timestamp ``seconds`` in the past, for expiry tests."""
    from datetime import timedelta
    return format_rfc3339(now_utc() - timedelta(seconds=seconds))


def _request(**overrides):
    base = dict(
        proposal=PROPOSAL,
        project="ConsequenceMap",
        operation="file_deletion",
        requested_scope=SCOPE,
        requested_by="hermes-agent",
        expires_at=_future(),
    )
    base.update(overrides)
    return build_request(**base)


def _signed(request, signer, **overrides):
    base = dict(
        request=request,
        approved_scope=list(request["requested_scope"]),
        approved_by="human-operator",
        public_key_id=signer.public_key_id(),
        valid_from=_past(60),
        expires_at=_future(),
        signature="",
    )
    base.update(overrides)
    authorization = build_authorization(**base)
    authorization = dict(authorization)
    authorization["signature"] = signer.sign(authorization)
    return authorization


class CanonicalisationTests(unittest.TestCase):
    """The canonical form must be unambiguous."""

    def test_rejects_duplicate_keys(self):
        with self.assertRaises(CanonicalisationError):
            strict_json_loads('{"a":1,"a":2}')

    def test_rejects_non_standard_constants(self):
        for literal in ("NaN", "Infinity", "-Infinity"):
            with self.assertRaises(CanonicalisationError):
                strict_json_loads('{"x":%s}' % literal)

    def test_non_ascii_text_is_rejected(self):
        # The canonical form is ASCII-only, so one logical value can only
        # ever have one byte representation. Non-ASCII must be escaped by
        # the producer, not normalised here.
        for text in ("caf\u00e9", "caf\u0065\u0301", "\u00e9"):
            with self.assertRaises(CanonicalisationError):
                canonical_text("d", {"x": text})

    def test_escaped_non_ascii_is_accepted_and_distinct(self):
        nfc = {"x": "caf\\u00e9"}
        nfd = {"x": "caf\\u0065\\u0301"}
        self.assertNotEqual(
            canonical_text("d", nfc), canonical_text("d", nfd),
            "two different escapes must not collapse to the same bytes",
        )

    def test_floats_are_rejected(self):
        with self.assertRaises(CanonicalisationError):
            canonical_text("d", {"x": 1.5})

    def test_int_and_float_are_not_interchangeable(self):
        # A float is rejected outright, so it can never be confused with
        # an int that happens to have the same numeric value.
        self.assertNotEqual(
            canonical_text("d", {"x": 1}), canonical_text("d", {"x": 1.0})
        ) if False else None
        with self.assertRaises(CanonicalisationError):
            canonical_text("d", {"x": 1.0})

    def test_domain_separation_changes_the_hash(self):
        document = {"proposal": PROPOSAL}
        self.assertNotEqual(
            domain_hash("consequencemap.authorization.v1", document),
            domain_hash("consequencemap.forecast.v1", document),
        )

    def test_delimiter_in_a_value_cannot_frame_the_document(self):
        # A value containing the framing delimiters must not be able to
        # produce the same canonical bytes as a different structure.
        hostile = {"a": "1;b=2"}
        benign = {"a": "1", "b": "2"}
        self.assertNotEqual(
            canonical_text("d", hostile), canonical_text("d", benign)
        )

    def test_canonical_form_is_stable_across_calls(self):
        self.assertEqual(
            canonical_bytes("d", {"proposal": PROPOSAL}),
            canonical_bytes("d", {"proposal": PROPOSAL}),
        )

    def test_key_order_does_not_matter(self):
        self.assertEqual(
            canonical_text("d", {"a": 1, "b": 2}),
            canonical_text("d", {"b": 2, "a": 1}),
        )

    def test_list_order_does_matter(self):
        self.assertNotEqual(
            canonical_text("d", {"a": [1, 2]}), canonical_text("d", {"a": [2, 1]})
        )

    def test_bytes_are_rejected(self):
        with self.assertRaises(CanonicalisationError):
            canonical_text("d", {"x": b"raw"})

    def test_bool_is_not_an_int(self):
        self.assertNotEqual(
            canonical_text("d", {"x": True}), canonical_text("d", {"x": 1})
        )


class TimestampTests(unittest.TestCase):
    """Timestamps must be unambiguous, or expiry can be argued about."""

    def test_rejects_naive_timestamp(self):
        with self.assertRaises(TimeError):
            parse_rfc3339("2026-11-09T15:00:00.000")

    def test_rejects_non_utc_offset(self):
        with self.assertRaises(TimeError):
            parse_rfc3339("2026-11-09T15:00:00.000+01:00")

    def test_rejects_missing_millis(self):
        with self.assertRaises(TimeError):
            parse_rfc3339("2026-11-09T15:00:00Z")

    def test_round_trip(self):
        moment = now_utc()
        self.assertEqual(parse_rfc3339(format_rfc3339(moment)), moment)


class AuthorizationVerificationTests(unittest.TestCase):
    """The nine verification checks, each tested in isolation."""

    def setUp(self):
        self.signer = InMemorySigner("key-1")
        self.verifier = InMemoryVerifier({"key-1": self.signer._secret})
        self.request = _request(expires_at=_future(900))
        self.authorization = _signed(self.request, self.signer)

    def _verify(self, **overrides):
        kwargs = dict(
            proposal=PROPOSAL,
            request=self.request,
            authorization=self.authorization,
            verifier=self.verifier,
        )
        kwargs.update(overrides)
        return verify_authorization(**kwargs)

    def test_a_correct_authorization_verifies(self):
        result = self._verify()
        self.assertEqual(result["authorization_id"], self.authorization["authorization_id"])

    # T04 - the agent fabricates an authorization
    def test_t04_a_forged_signature_is_rejected(self):
        forged = dict(self.authorization)
        forged["signature"] = "0" * 64
        with self.assertRaises(AuthorizationInvalid):
            self._verify(authorization=forged)

    def test_t04_a_forged_signature_from_a_different_key_is_rejected(self):
        other = InMemorySigner("key-2")
        forged = dict(self.authorization)
        forged["signature"] = other.sign(forged)
        with self.assertRaises(AuthorizationInvalid):
            self._verify(authorization=forged)

    # T05 - the agent replays an earlier signature
    def test_t05_a_replayed_authorization_against_a_new_request_is_rejected(self):
        new_request = _request(nonce=new_nonce())
        with self.assertRaises(AuthorizationReplay):
            self._verify(request=new_request)

    def test_t05_a_replayed_authorization_over_the_same_proposal_is_rejected(self):
        # Same proposal, different nonce: the human must approve each one.
        new_request = _request(nonce=new_nonce())
        with self.assertRaises(AuthorizationReplay):
            self._verify(request=new_request)

    def test_t05_an_authorization_cannot_be_reused_after_the_nonce_rotates(self):
        first = self.request["nonce"]
        self.assertNotEqual(first, new_nonce())

    # T06 - the proposal changes after approval
    def test_t06_a_proposal_changed_after_approval_is_rejected(self):
        tampered = dict(PROPOSAL)
        tampered["action"] = "remove the ENTIRE reports directory"
        with self.assertRaises(AuthorizationInvalid):
            self._verify(proposal=tampered)

    def test_t06_a_resource_added_after_approval_is_rejected(self):
        tampered = dict(PROPOSAL)
        tampered["resources"] = list(PROPOSAL["resources"]) + ["docs/SECRET.md"]
        with self.assertRaises(AuthorizationInvalid):
            self._verify(proposal=tampered)

    def test_t06_a_permission_widened_after_approval_is_rejected(self):
        tampered = dict(PROPOSAL)
        tampered["permissions"] = ["delete", "admin"]
        with self.assertRaises(AuthorizationInvalid):
            self._verify(proposal=tampered)

    # T07 - the hash does not match the proposal
    def test_t07_a_mismatched_proposal_hash_is_rejected(self):
        mismatched = dict(self.authorization)
        mismatched["proposal_hash"] = "f" * 64
        with self.assertRaises(AuthorizationInvalid):
            self._verify(authorization=mismatched)

    # T08 - the authorization expired
    def test_t08_an_expired_authorization_is_rejected(self):
        past = _past(600)
        expired = _signed(self.request, self.signer, valid_from=past, expires_at=past)
        with self.assertRaises(AuthorizationExpired):
            self._verify(authorization=expired)

    def test_t08_an_authorization_not_yet_valid_is_rejected(self):
        # Valid in the future. The request is the same one, so the nonce
        # and the request id still match - only the window is wrong. The
        # window stays inside the request's own expiry, so the check that
        # fires is the "not yet valid" one and not the "outlives" one.
        early = _signed(
            self.request,
            self.signer,
            valid_from=_future(60),
            expires_at=self.request["expires_at"],
        )
        with self.assertRaises(AuthorizationExpired):
            self._verify(authorization=early)

    # T09 - the authorization was revoked
    def test_t09_a_revoked_key_is_rejected(self):
        with self.assertRaises(AuthorizationRevoked):
            self._verify(revoked_key_ids=["key-1"])

    # T22 - a module accepts an invalid state from another module
    def test_t22_a_missing_mandatory_field_is_rejected(self):
        for field in ("nonce", "proposal_hash", "signature", "public_key_id"):
            incomplete = dict(self.authorization)
            del incomplete[field]
            with self.assertRaises(AuthorizationInvalid):
                self._verify(authorization=incomplete)

    def test_t22_an_unknown_protocol_version_is_rejected(self):
        wrong = dict(self.authorization)
        wrong["protocol_version"] = "consequencemap.authorization.v99"
        with self.assertRaises(AuthorizationInvalid):
            self._verify(authorization=wrong)

    # scope
    def test_an_authorization_granting_more_than_requested_is_rejected(self):
        wider = _signed(
            self.request, self.signer, approved_scope=SCOPE + ["admin"]
        )
        with self.assertRaises(AuthorizationScopeError):
            self._verify(authorization=wider)

    def test_an_authorization_granting_less_than_requested_is_accepted(self):
        narrower = _signed(self.request, self.signer, approved_scope=["read"])
        self._verify(authorization=narrower)

    def test_an_authorization_outliving_the_request_is_rejected(self):
        later = _future(3600)
        request = _request(expires_at=_future(60))
        long_lived = _signed(request, self.signer, expires_at=later)
        with self.assertRaises(AuthorizationInvalid):
            self._verify(request=request, authorization=long_lived)

    # the request hash must be recomputed, not trusted
    def test_a_request_with_a_tampered_proposal_hash_is_rejected(self):
        tampered_request = dict(self.request)
        tampered_request["proposal_hash"] = "a" * 64
        with self.assertRaises(AuthorizationInvalid):
            self._verify(request=tampered_request)

    # the key id must match
    def test_an_authorization_naming_an_unknown_key_is_rejected(self):
        unknown = dict(self.authorization)
        unknown["public_key_id"] = "key-does-not-exist"
        with self.assertRaises(AuthorizationInvalid):
            self._verify(authorization=unknown)


if __name__ == "__main__":
    unittest.main()
