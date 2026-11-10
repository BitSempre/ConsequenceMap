"""Regression tests for the defects found by adversarial probing.

These four tests each correspond to a defect that was PRESENT and
EXPLOITED, and then fixed. They are kept because the next person to
touch this code will try the same thing.

The defects were found by writing probes against the implementation
rather than by reading it, which is why they are worth a permanent
test.
"""
from __future__ import annotations

import unittest

from consequence_map.core.agent import AgentRequest, AgentRequestRejected
from consequence_map.core.audit import AuditLog, ChainBroken, verify_chain
from consequence_map.core.authorization import (
    AuthorizationInvalid,
    InMemorySigner,
    InMemoryVerifier,
    build_authorization,
    build_request,
    verify_authorization,
)
from consequence_map.core.canonical import (
    CanonicalisationError,
    canonical_text,
    domain_hash,
)
from consequence_map.core.timeutil import format_rfc3339, now_utc

from datetime import timedelta


def _future(seconds=600):
    return format_rfc3339(now_utc() + timedelta(seconds=seconds))


def _past(seconds=60):
    return format_rfc3339(now_utc() - timedelta(seconds=seconds))


PROPOSAL = {"action": "delete the report", "resources": ["r.md"], "permissions": ["delete"]}


class ScopeTypeTests(unittest.TestCase):
    """A scope is a list of NAMES. A string is not a list of one name.

    ``set("files:write")`` is ``{'f','i','l','e','s',':','w','r','t'}``.
    Accepting a string turned one scope into nine single-character
    scopes, and a subset comparison could then succeed on a single
    shared character.
    """

    def test_a_string_scope_is_rejected_when_building_a_request(self):
        with self.assertRaises(AuthorizationInvalid):
            build_request(
                proposal=PROPOSAL, project="C", operation="op",
                requested_scope="files:write", requested_by="ag",
                expires_at=_future(),
            )

    def test_a_string_scope_is_rejected_when_building_an_authorization(self):
        request = build_request(
            proposal=PROPOSAL, project="C", operation="op",
            requested_scope=["files:write"], requested_by="ag",
            expires_at=_future(),
        )
        with self.assertRaises(AuthorizationInvalid):
            build_authorization(
                request=request, approved_scope="files:write",
                approved_by="h", public_key_id="k", valid_from=_past(),
                expires_at=request["expires_at"], signature="",
            )

    def test_a_string_scope_on_the_request_is_rejected_on_verification(self):
        signer = InMemorySigner("k")
        request = build_request(
            proposal=PROPOSAL, project="C", operation="op",
            requested_scope=["files:write"], requested_by="ag",
            expires_at=_future(),
        )
        authorization = build_authorization(
            request=request, approved_scope=["files:write"],
            approved_by="h", public_key_id="k", valid_from=_past(),
            expires_at=request["expires_at"], signature="",
        )
        authorization = dict(authorization)
        authorization["signature"] = signer.sign(authorization)
        tampered = dict(request)
        tampered["requested_scope"] = "files:write"
        with self.assertRaises(AuthorizationInvalid):
            verify_authorization(
                proposal=PROPOSAL, request=tampered,
                authorization=authorization,
                verifier=InMemoryVerifier({"k": signer._secret}),
            )

    def test_a_non_string_scope_item_is_rejected(self):
        with self.assertRaises(AuthorizationInvalid):
            build_request(
                proposal=PROPOSAL, project="C", operation="op",
                requested_scope=["files:write", 42], requested_by="ag",
                expires_at=_future(),
            )

    def test_the_agent_surface_rejects_a_string_scope(self):
        with self.assertRaises(AgentRequestRejected):
            AgentRequest(
                operation="file.delete", arguments={}, proposal=PROPOSAL,
                project="C", requested_scope="files:write",
                requested_by="ag", expires_at=_future(),
            )

    def test_a_list_scope_still_works(self):
        request = build_request(
            proposal=PROPOSAL, project="C", operation="op",
            requested_scope=["files:write"], requested_by="ag",
            expires_at=_future(),
        )
        self.assertEqual(request["requested_scope"], ["files:write"])


class NestingDepthTests(unittest.TestCase):
    """A deep document is refused rather than processed."""

    def test_a_document_nested_past_the_limit_is_rejected(self):
        document = {}
        cursor = document
        for _ in range(200):
            cursor["n"] = {}
            cursor = cursor["n"]
        with self.assertRaises(CanonicalisationError):
            canonical_text("d", document)

    def test_a_reasonable_depth_still_works(self):
        document = {}
        cursor = document
        for _ in range(8):
            cursor["n"] = {}
            cursor = cursor["n"]
        canonical_text("d", document)

    def test_a_deep_document_does_not_exhaust_the_stack(self):
        document = {}
        cursor = document
        for _ in range(5000):
            cursor["n"] = {}
            cursor = cursor["n"]
        with self.assertRaises(CanonicalisationError):
            canonical_text("d", document)


class TruncationTests(unittest.TestCase):
    """A prefix of a chain is itself a consistent chain.

    Truncation is only detectable against an anchor that lives outside
    the chain. The functions therefore accept one, and say plainly that
    they cannot detect truncation without it.
    """

    def setUp(self):
        self.log = AuditLog()
        for index in range(5):
            self.log.append("event-%d" % index, {"index": index})
        self.head = self.log.head_hash()

    def test_a_truncated_chain_verifies_without_an_anchor(self):
        # This is the defect: a prefix is internally consistent. The
        # test records the behaviour so that the fix cannot be silently
        # undone, and the next test shows the anchor catching it.
        verify_chain(list(self.log.records)[:3])

    def test_a_truncated_chain_is_caught_by_the_expected_head(self):
        with self.assertRaises(ChainBroken):
            verify_chain(list(self.log.records)[:3], expected_head=self.head)

    def test_a_truncated_chain_is_caught_by_the_expected_length(self):
        with self.assertRaises(ChainBroken):
            verify_chain(list(self.log.records)[:3], expected_length=5)

    def test_the_log_verifies_against_its_own_head(self):
        self.log.verify(expected_head=self.head, expected_length=5)

    def test_an_unchanged_chain_still_verifies(self):
        verify_chain(self.log.records, expected_head=self.head, expected_length=5)

    def test_an_extended_chain_is_caught_by_the_expected_head(self):
        extra = AuditLog()
        extra.append("event-5", {"index": 5})
        extended = list(self.log.records) + list(extra.records)
        with self.assertRaises(ChainBroken):
            verify_chain(extended, expected_head=self.head)


if __name__ == "__main__":
    unittest.main()
