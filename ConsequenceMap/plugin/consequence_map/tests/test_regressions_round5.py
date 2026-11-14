"""Regression tests for the sixth round: the agent boundary and the contract.

The sixth round attacked the places where the AGENT is the adversary:
the surface it calls, the contract the guard transport speaks, and the
policy that bounds how long an approval stays usable.

Two defects were found, and one policy gap that was closed.

D-17  the guard transport could return a decision and an ``allowed``
      flag that DISAGREED - ``decision=DENY`` with ``allowed=True``.
      Both are part of the contract, and a consumer is entitled to read
      either. The agent's surface reads ``allowed``. So a transport
      could hand the agent a denial dressed as a permission.

D-18  nothing bounded how long an approval could stay open. The
      exposure window for a captured authorization was whatever the
      requester asked for - the agent could ask for ten years. That
      number is question Q-5 in the residual-risk register, and it is
      the owner's decision, but the platform must not accept an
      unbounded window while that decision is pending.
"""
from __future__ import annotations

import unittest

from consequence_map.core.authorization import (
    AuthorizationInvalid,
    InMemorySigner,
    InMemoryVerifier,
    MAX_VALIDITY_SECONDS,
    build_authorization,
    build_request,
)
from consequence_map.core.deployment import ContractViolation, GuardDeployment
from consequence_map.core.timeutil import format_rfc3339, now_utc

from datetime import timedelta


def _future(seconds=600):
    return format_rfc3339(now_utc() + timedelta(seconds=seconds))


def _past(seconds=60):
    return format_rfc3339(now_utc() - timedelta(seconds=seconds))


PROPOSAL = {"action": "delete the report", "resources": ["r.md"], "permissions": ["delete"]}


class TransportAgreementTests(unittest.TestCase):
    """The decision and the flag must agree."""

    def _deployment(self, answer):
        class _Transport:
            def ask(self, payload):
                return answer
        return GuardDeployment(_Transport())

    def test_a_denial_with_allowed_true_is_refused(self):
        with self.assertRaises(ContractViolation):
            self._deployment({"decision": "DENY", "reason": "r", "allowed": True}).decide({})

    def test_an_allow_with_allowed_false_is_refused(self):
        with self.assertRaises(ContractViolation):
            self._deployment({"decision": "ALLOW", "reason": "r", "allowed": False}).decide({})

    def test_a_non_boolean_allowed_is_refused(self):
        with self.assertRaises(ContractViolation):
            self._deployment({"decision": "ALLOW", "reason": "r", "allowed": "yes"}).decide({})

    def test_an_allow_with_allowed_true_is_accepted(self):
        answer = self._deployment(
            {"decision": "ALLOW", "reason": "r", "allowed": True}
        ).decide({})
        self.assertEqual(answer["decision"], "ALLOW")

    def test_a_denial_with_allowed_false_is_accepted(self):
        answer = self._deployment(
            {"decision": "DENY", "reason": "r", "allowed": False}
        ).decide({})
        self.assertEqual(answer["decision"], "DENY")

    def test_a_decision_without_the_flag_is_accepted(self):
        answer = self._deployment({"decision": "DENY", "reason": "r"}).decide({})
        self.assertEqual(answer["decision"], "DENY")


class ValidityWindowTests(unittest.TestCase):
    """An approval may not stay open longer than the policy allows."""

    def _request(self, **overrides):
        base = dict(
            proposal=PROPOSAL, project="C", operation="file.delete",
            requested_scope=["files:write"], requested_by="ag",
            expires_at=_future(600),
        )
        base.update(overrides)
        return build_request(**base)

    def test_a_request_beyond_the_policy_is_refused(self):
        with self.assertRaises(AuthorizationInvalid):
            self._request(expires_at=_future(MAX_VALIDITY_SECONDS + 3600))

    def test_a_ten_year_request_is_refused(self):
        with self.assertRaises(AuthorizationInvalid):
            self._request(expires_at=_future(3600 * 24 * 365 * 10))

    def test_a_request_inside_the_policy_is_accepted(self):
        request = self._request(expires_at=_future(MAX_VALIDITY_SECONDS - 60))
        self.assertIsNotNone(request["request_id"])

    def test_an_authorization_beyond_the_policy_is_refused(self):
        request = self._request(expires_at=_future(600))
        with self.assertRaises(AuthorizationInvalid):
            build_authorization(
                request=request, approved_scope=["files:write"],
                approved_by="h", public_key_id="k", valid_from=_past(60),
                expires_at=_future(MAX_VALIDITY_SECONDS + 3600), signature="",
            )

    def test_the_policy_is_a_parameter_not_a_constant(self):
        request = build_request(
            proposal=PROPOSAL, project="C", operation="file.delete",
            requested_scope=["files:write"], requested_by="ag",
            expires_at=_future(MAX_VALIDITY_SECONDS + 3600),
            max_validity_seconds=MAX_VALIDITY_SECONDS * 10,
        )
        self.assertIsNotNone(request["request_id"])

    def test_a_tight_policy_refuses_what_a_loose_one_accepts(self):
        with self.assertRaises(AuthorizationInvalid):
            build_request(
                proposal=PROPOSAL, project="C", operation="file.delete",
                requested_scope=["files:write"], requested_by="ag",
                expires_at=_future(600), max_validity_seconds=60,
            )


if __name__ == "__main__":
    unittest.main()
