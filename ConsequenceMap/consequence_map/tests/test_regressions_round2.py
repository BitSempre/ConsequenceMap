"""Regression tests for the second round of adversarial probing.

Same purpose as ``test_regressions.py``: each test pins a defect that
was present and EXPLOITED, then fixed.

The round-two findings were mostly about **input validation at the
edges** - a request that lies about its own proposal, a timestamp that
cannot be parsed, a field the schema does not define, a command-shaped
argument that only got refused further down the chain.
"""
from __future__ import annotations

import unittest

from consequence_map.core.agent import AgentRequestRejected, AgentSurface, HermesAdapter
from consequence_map.core.analysis import ForecastNotQualified, QualificationError, qualify_forecast
from consequence_map.core.audit import AuditError, AuditLog
from consequence_map.core.authorization import (
    AuthorizationInvalid,
    InMemorySigner,
    InMemoryVerifier,
    build_authorization,
    build_request,
    verify_authorization,
)
from consequence_map.core.deployment import ContractViolation, GuardDeployment
from consequence_map.core.execution import Operation, OperationRegistry
from consequence_map.core.guard import SecurityGuard
from consequence_map.core.timeutil import TimeError, format_rfc3339, now_utc

from datetime import timedelta


def _future(seconds=600):
    return format_rfc3339(now_utc() + timedelta(seconds=seconds))


def _past(seconds=60):
    return format_rfc3339(now_utc() - timedelta(seconds=seconds))


PROPOSAL = {"action": "delete the report", "resources": ["r.md"], "permissions": ["delete"]}


class RequestHonestyTests(unittest.TestCase):
    """The request must not be able to describe a different proposal.

    The verifier checks the proposal it is GIVEN. If the request's own
    copy of the proposal could differ, the request would be displaying
    one thing and being verified against another.
    """

    def setUp(self):
        self.signer = InMemorySigner("k")
        self.verifier = InMemoryVerifier({"k": self.signer._secret})
        self.request = build_request(
            proposal=PROPOSAL, project="C", operation="op",
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

    def test_a_request_with_a_different_proposal_is_rejected(self):
        lying = dict(self.request)
        lying["proposal"] = {"action": "delete everything"}
        with self.assertRaises(AuthorizationInvalid):
            verify_authorization(
                proposal=PROPOSAL, request=lying,
                authorization=self.authorization, verifier=self.verifier,
            )

    def test_a_request_with_a_non_mapping_proposal_is_rejected(self):
        lying = dict(self.request)
        lying["proposal"] = [1, 2, 3]
        with self.assertRaises(AuthorizationInvalid):
            verify_authorization(
                proposal=PROPOSAL, request=lying,
                authorization=self.authorization, verifier=self.verifier,
            )


class TimestampValidationTests(unittest.TestCase):
    """An unparseable timestamp must be refused at construction.

    A request carrying a timestamp that cannot be read would be accepted
    at construction and rejected at verification - and in between it
    would be a request the agent could hold open indefinitely.
    """

    def test_a_request_with_an_unparseable_expiry_is_refused(self):
        with self.assertRaises(TimeError):
            build_request(
                proposal=PROPOSAL, project="C", operation="op",
                requested_scope=["files:write"], requested_by="ag",
                expires_at="not-a-timestamp",
            )

    def test_an_authorization_with_an_unparseable_window_is_refused(self):
        request = build_request(
            proposal=PROPOSAL, project="C", operation="op",
            requested_scope=["files:write"], requested_by="ag",
            expires_at=_future(),
        )
        with self.assertRaises(TimeError):
            build_authorization(
                request=request, approved_scope=["files:write"],
                approved_by="h", public_key_id="k", valid_from="not-a-time",
                expires_at=request["expires_at"], signature="",
            )


class ClosedSchemaTests(unittest.TestCase):
    """Unknown fields and command-shaped arguments are refused at the edge."""

    def setUp(self):
        self.registry = OperationRegistry([
            Operation("file.delete", "files:write", lambda a: None),
        ])
        self.signer = InMemorySigner("k")
        self.guard = SecurityGuard(
            self.registry, InMemoryVerifier({"k": self.signer._secret})
        )
        self.surface = AgentSurface(self.guard, HermesAdapter())

    def _raw(self, **overrides):
        base = dict(
            tool="file.delete", arguments={}, proposal=PROPOSAL, project="C",
            scope=["files:write"], actor="ag", expires_at=_future(),
        )
        base.update(overrides)
        return base

    def test_an_unknown_field_is_refused(self):
        with self.assertRaises(AgentRequestRejected):
            self.surface.propose(self._raw(surprise_field="x"))

    def test_a_command_shaped_argument_is_refused(self):
        with self.assertRaises(AgentRequestRejected):
            self.surface.propose(self._raw(arguments={"cmd": "calc.exe"}))

    def test_a_command_shaped_argument_is_refused_at_any_case(self):
        for name in ("command", "cmd", "shell", "script", "argv"):
            with self.assertRaises(AgentRequestRejected):
                self.surface.propose(self._raw(arguments={name: "x"}))


class ForecastShapeTests(unittest.TestCase):
    """The forecast's collections must be collections."""

    def _forecast(self, **overrides):
        base = dict(
            content_hash="a" * 64, summary="s", confidence_overall="HIGH",
            evidence=[], unknowns=[{"id": "u"}], risk={},
        )
        base.update(overrides)
        return base

    def test_unknowns_must_be_a_list(self):
        with self.assertRaises(QualificationError):
            qualify_forecast(self._forecast(unknowns={"x": 1}))

    def test_evidence_must_be_a_list(self):
        with self.assertRaises(QualificationError):
            qualify_forecast(self._forecast(evidence={"x": 1}))


class AuditEventTests(unittest.TestCase):
    """An event name is one line. A newline in it could forge a record."""

    def test_an_event_with_a_newline_is_refused(self):
        with self.assertRaises(AuditError):
            AuditLog().append("event" + chr(10) + "forged", {})

    def test_an_event_with_a_null_byte_is_refused(self):
        with self.assertRaises(AuditError):
            AuditLog().append("event" + chr(0) + "x", {})

    def test_an_ordinary_event_is_accepted(self):
        log = AuditLog()
        log.append("execution.completed", {"path": "a"})
        log.verify()


class DeploymentSchemaTests(unittest.TestCase):
    """The transport's response schema is closed."""

    def test_an_unexpected_field_is_refused(self):
        class _Transport:
            def ask(self, payload):
                return {"decision": "ALLOW", "reason": "r", "surprise": 1}

        with self.assertRaises(ContractViolation):
            GuardDeployment(_Transport()).decide({})

    def test_a_normal_response_is_accepted(self):
        class _Transport:
            def ask(self, payload):
                return {"decision": "ALLOW", "reason": "r"}

        self.assertEqual(
            GuardDeployment(_Transport()).decide({})["decision"], "ALLOW"
        )


if __name__ == "__main__":
    unittest.main()
