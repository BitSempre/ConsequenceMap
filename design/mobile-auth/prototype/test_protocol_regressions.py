"""Regression tests for the mobile protocol's fifth-round defects.

Two defects were found by attacking the PROTOTYPE, which had never been
probed - only the core had been.

D-15  ``escape_tree`` escaped values but not KEYS. The canonical form
      refuses a non-ASCII key outright, so the prototype could build a
      tree the canonicaliser would reject. The phone and the PC would
      disagree about what was approved.

D-16  the fields the phone DISPLAYS to the human - the affected
      resources and the consequence summary - lived BESIDE the proposal
      rather than inside it. The proposal is what gets hashed and signed,
      so those fields were outside the hash and outside the signature.
      An attacker could change what the phone showed without
      invalidating the approval: the request still verified, because the
      verifier only ever looked at the proposal.

D-16 is the serious one. The human approves what they see, and what
they saw was not protected by anything.
"""
from __future__ import annotations

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from protocol import (  # noqa: E402
    InMemoryPhoneSigner,
    InMemoryPhoneVerifier,
    build_approval_request,
    canonical_payload,
    escape_for_canonical,
    escape_tree,
    verify_approval,
    verify_binding,
)
from consequence_map.core.authorization import (  # noqa: E402
    AuthorizationInvalid,
    build_authorization,
)
from consequence_map.core.canonical import CanonicalisationError  # noqa: E402
from consequence_map.core.timeutil import format_rfc3339, now_utc  # noqa: E402

from datetime import timedelta  # noqa: E402


def _future(seconds=600):
    return format_rfc3339(now_utc() + timedelta(seconds=seconds))


def _past(seconds=60):
    return format_rfc3339(now_utc() - timedelta(seconds=seconds))


PROPOSAL = {
    "action": "delete the quarterly report",
    "resources": ["reports/q3.md"],
    "permissions": ["delete"],
}


class EscapeTests(unittest.TestCase):
    """Keys are escaped as well as values."""

    def test_a_non_ascii_key_is_escaped(self):
        tree = escape_tree({"k": "v", "\u00e9": "x"})
        self.assertIn("\\u00e9", tree)
        self.assertNotIn("\u00e9", tree)

    def test_an_escaped_tree_canonicalises(self):
        payload = canonical_payload({"k": "v", "\u00e9": "x"})
        self.assertTrue(payload.isascii())

    def test_the_escaped_key_is_the_only_key(self):
        tree = escape_tree({"k": "v", "\u00e9": "x"})
        self.assertEqual(sorted(tree.keys()), ["\\u00e9", "k"])


class DisplayBindingTests(unittest.TestCase):
    """What the human sees is what is signed."""

    def setUp(self):
        self.signer = InMemoryPhoneSigner("pk")
        self.verifier = InMemoryPhoneVerifier({"pk": self.signer._secret})
        self.request = build_approval_request(
            proposal=PROPOSAL, project="C", operation="file.delete",
            affected_resources=["reports/q3.md"],
            requested_permissions=["files:write"],
            consequence_summary="Deletes the quarterly report.",
            requested_by="agent", expires_at=_future(),
        )
        authorization = build_authorization(
            request=self.request, approved_scope=["files:write"],
            approved_by="the-owner", public_key_id="pk", valid_from=_past(),
            expires_at=self.request["expires_at"], signature="",
        )
        self.authorization = dict(authorization)
        self.authorization["signature"] = self.signer.sign(self.authorization)

    def test_a_correct_approval_verifies(self):
        verify_approval(
            proposal=PROPOSAL, request=self.request,
            authorization=self.authorization, verifier=self.verifier,
        )

    def test_an_added_affected_resource_is_rejected(self):
        tampered = dict(self.request)
        tampered["affected_resources"] = ["reports/q3.md", "secrets/keys.txt"]
        with self.assertRaises(AuthorizationInvalid):
            verify_approval(
                proposal=PROPOSAL, request=tampered,
                authorization=self.authorization, verifier=self.verifier,
            )

    def test_a_changed_consequence_summary_is_rejected(self):
        tampered = dict(self.request)
        tampered["consequence_summary"] = "Deletes one harmless file."
        with self.assertRaises(AuthorizationInvalid):
            verify_approval(
                proposal=PROPOSAL, request=tampered,
                authorization=self.authorization, verifier=self.verifier,
            )

    def test_two_requests_with_different_resources_have_different_hashes(self):
        other = build_approval_request(
            proposal=PROPOSAL, project="C", operation="file.delete",
            affected_resources=["reports/q3.md", "secrets/keys.txt"],
            requested_permissions=["files:write"],
            consequence_summary="Deletes the quarterly report.",
            requested_by="agent", expires_at=_future(),
        )
        self.assertNotEqual(self.request["proposal_hash"], other["proposal_hash"])

    def test_two_requests_with_different_summaries_have_different_hashes(self):
        other = build_approval_request(
            proposal=PROPOSAL, project="C", operation="file.delete",
            affected_resources=["reports/q3.md"],
            requested_permissions=["files:write"],
            consequence_summary="Deletes one harmless file.",
            requested_by="agent", expires_at=_future(),
        )
        self.assertNotEqual(self.request["proposal_hash"], other["proposal_hash"])

    def test_the_binding_check_follows_the_same_rule(self):
        self.assertTrue(verify_binding(
            proposal=PROPOSAL, request=self.request,
            authorization=self.authorization,
        ))
        tampered = dict(self.request)
        tampered["affected_resources"] = ["reports/q3.md", "secrets/keys.txt"]
        self.assertFalse(verify_binding(
            proposal=PROPOSAL, request=tampered,
            authorization=self.authorization,
        ))

    def test_the_display_fields_are_inside_the_signed_proposal(self):
        self.assertIn("affected_resources", self.request["proposal"])
        self.assertIn("consequence_summary", self.request["proposal"])


if __name__ == "__main__":
    unittest.main()
