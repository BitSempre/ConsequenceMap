"""Regression tests for the independent reviewer's findings.

An independent reviewer, working from a logic excerpt with no access to
the repository, returned five findings. Each was checked against the
real code before anything was changed. Two were real; three were not.

THE TWO THAT WERE REAL:

D-20  the EXECUTOR kept no audit trail. The guard audited every
      decision, but the executor - the thing that actually performs
      the operation - recorded nothing. So an execution that was
      REFUSED left no trace, and the audit log's own docstring claims
      that refusals are recorded. The claim was true of the guard and
      false of the executor.

D-21  the authorization is produced by the PHONE and verified by the
      PC, and the two have different clocks. A phone whose clock is a
      little behind produces an authorization that looks expired to
      the PC, and a slightly-wrong phone looks exactly like a replay.

THE THREE THAT WERE NOT:

- "the nonce check runs before the request_id check, which allows a
  replay". The nonce is a BINDING between an authorization and a
  request, not a replay detector - there is no store of seen nonces.
  An attacker who reuses a nonce with a different request_id is
  refused by the request_id check that follows. The actual replay
  defence is the executor's spent-authorization set.

- "_as_scope does not verify the type before casting". It does: a
  string is rejected, then anything that is not a list or a tuple is
  rejected, then every item is checked to be a string.

- "the non-ASCII key is escaped rather than rejected". It is rejected.
  That was fixed before the review ran; the excerpt the reviewer was
  given predated the fix.

The tests below pin the two real fixes, and pin the three rejections
too - a finding that was tested and rejected should stay tested.
"""
from __future__ import annotations

import unittest

from consequence_map.core.authorization import (
    CLOCK_SKEW_SECONDS,
    AuthorizationExpired,
    AuthorizationInvalid,
    AuthorizationReplay,
    InMemorySigner,
    InMemoryVerifier,
    build_authorization,
    build_request,
    verify_authorization,
)
from consequence_map.core.audit import ChainBroken
from consequence_map.core.execution import (
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


class ExecutorAuditTests(unittest.TestCase):
    """The executor records every attempt, including the refusals."""

    def setUp(self):
        self.signer = InMemorySigner("k")
        self.verifier = InMemoryVerifier({"k": self.signer._secret})
        self.registry = OperationRegistry([
            Operation("file.delete", "files:write", lambda a: {"deleted": a.get("path")}),
        ])
        self.engine = ExecutionEngine(self.registry, self.verifier)
        self.request = build_request(
            proposal=PROPOSAL, project="C", operation="file.delete",
            requested_scope=["files:write"], requested_by="ag",
            expires_at=_future(),
        )
        self.authorization = build_authorization(
            request=self.request, approved_scope=["files:write"],
            approved_by="h", public_key_id="k", valid_from=_past(),
            expires_at=self.request["expires_at"], signature="",
        )
        self.authorization = dict(self.authorization)
        self.authorization["signature"] = self.signer.sign(self.authorization)

    def _execution_request(self, authorization=None):
        return ExecutionRequest(
            operation="file.delete", arguments={"path": "r.md"},
            proposal=PROPOSAL, request=self.request,
            authorization=authorization if authorization is not None else self.authorization,
        )

    def test_a_successful_execution_is_recorded(self):
        self.engine.execute(self._execution_request(), state=STATE_PREPARED)
        events = [r.event for r in self.engine.audit.records]
        self.assertIn("execution.completed", events)

    def test_a_refused_execution_is_recorded(self):
        forged = dict(self.authorization)
        forged["signature"] = "0" * 64
        with self.assertRaises(ExecutionRefused):
            self.engine.execute(self._execution_request(forged), state=STATE_PREPARED)
        events = [r.event for r in self.engine.audit.records]
        self.assertIn("execution.refused", events)

    def test_the_refusal_records_the_reason(self):
        forged = dict(self.authorization)
        forged["signature"] = "0" * 64
        with self.assertRaises(ExecutionRefused):
            self.engine.execute(self._execution_request(forged), state=STATE_PREPARED)
        record = self.engine.audit.records[-1]
        self.assertTrue(record.payload["reason"])
        self.assertEqual(record.payload["operation"], "file.delete")

    def test_an_unregistered_operation_is_recorded_as_refused(self):
        with self.assertRaises(Exception):
            self.engine.execute(
                ExecutionRequest(
                    operation="not.registered", arguments={}, proposal=PROPOSAL,
                    request=self.request, authorization=self.authorization,
                ),
                state=STATE_PREPARED,
            )
        events = [r.event for r in self.engine.audit.records]
        self.assertIn("execution.refused", events)

    def test_the_audit_chain_verifies(self):
        self.engine.execute(self._execution_request(), state=STATE_PREPARED)
        self.engine.audit.verify()

    def test_the_audit_can_be_shared_with_the_guard(self):
        from consequence_map.core.audit import AuditLog
        shared = AuditLog()
        engine = ExecutionEngine(self.registry, self.verifier, audit=shared)
        engine.execute(self._execution_request(), state=STATE_PREPARED)
        self.assertEqual(len(shared), 1)


class ClockSkewTests(unittest.TestCase):
    """A phone whose clock is a little wrong is not an attack."""

    def setUp(self):
        self.signer = InMemorySigner("k")
        self.verifier = InMemoryVerifier({"k": self.signer._secret})
        self.request = build_request(
            proposal=PROPOSAL, project="C", operation="file.delete",
            requested_scope=["files:write"], requested_by="ag",
            expires_at=_future(),
        )

    def _authorization(self, valid_from, expires_at):
        authorization = build_authorization(
            request=self.request, approved_scope=["files:write"],
            approved_by="h", public_key_id="k", valid_from=valid_from,
            expires_at=expires_at, signature="",
        )
        authorization = dict(authorization)
        authorization["signature"] = self.signer.sign(authorization)
        return authorization

    def test_a_phone_behind_by_less_than_the_tolerance_is_accepted(self):
        phone_now = now_utc() - timedelta(seconds=CLOCK_SKEW_SECONDS // 2)
        authorization = self._authorization(
            format_rfc3339(phone_now),
            format_rfc3339(phone_now + timedelta(seconds=600)),
        )
        verify_authorization(
            proposal=PROPOSAL, request=self.request,
            authorization=authorization, verifier=self.verifier,
        )

    def test_a_phone_behind_by_more_than_the_tolerance_is_refused(self):
        # The phone is behind by ten tolerances, and its window has
        # already closed as far as the PC is concerned. The PC refuses:
        # a phone this far out of step is not an attack, it is a clock
        # problem - but the approval cannot be used.
        phone_now = now_utc() - timedelta(seconds=CLOCK_SKEW_SECONDS * 10)
        authorization = self._authorization(
            format_rfc3339(phone_now - timedelta(seconds=60)),
            format_rfc3339(phone_now + timedelta(seconds=10)),
        )
        with self.assertRaises(AuthorizationExpired):
            verify_authorization(
                proposal=PROPOSAL, request=self.request,
                authorization=authorization, verifier=self.verifier,
            )

    def test_the_tolerance_is_a_parameter(self):
        phone_now = now_utc() - timedelta(seconds=CLOCK_SKEW_SECONDS * 10)
        authorization = self._authorization(
            format_rfc3339(phone_now),
            format_rfc3339(phone_now + timedelta(seconds=600)),
        )
        verify_authorization(
            proposal=PROPOSAL, request=self.request,
            authorization=authorization, verifier=self.verifier,
            clock_skew_seconds=CLOCK_SKEW_SECONDS * 20,
        )

    def test_an_authorization_that_is_not_yet_valid_is_still_refused(self):
        # The tolerance applies to the EXPIRY side only. A phone saying
        # "this is good from later" is a clock problem, not a reason to
        # accept early.
        #
        # The window is short enough to stay inside the validity policy,
        # because the policy is checked before the window is.
        future_start = now_utc() + timedelta(seconds=10)
        authorization = self._authorization(
            format_rfc3339(future_start),
            format_rfc3339(future_start + timedelta(seconds=60)),
        )
        with self.assertRaises(AuthorizationExpired):
            verify_authorization(
                proposal=PROPOSAL, request=self.request,
                authorization=authorization, verifier=self.verifier,
            )


class RejectedFindingTests(unittest.TestCase):
    """Findings that were checked and rejected stay checked."""

    def setUp(self):
        self.signer = InMemorySigner("k")
        self.verifier = InMemoryVerifier({"k": self.signer._secret})
        self.request = build_request(
            proposal=PROPOSAL, project="C", operation="file.delete",
            requested_scope=["files:write"], requested_by="ag",
            expires_at=_future(),
        )
        self.authorization = build_authorization(
            request=self.request, approved_scope=["files:write"],
            approved_by="h", public_key_id="k", valid_from=_past(),
            expires_at=self.request["expires_at"], signature="",
        )
        self.authorization = dict(self.authorization)
        self.authorization["signature"] = self.signer.sign(self.authorization)

    def test_a_reused_nonce_with_a_different_request_id_is_refused(self):
        """The reviewer's finding: the nonce check runs first.

        It is refused - by the request_id check that follows. The nonce
        is a binding, not a replay detector.
        """
        altered = dict(self.request)
        altered["request_id"] = "req-ALTERED"
        with self.assertRaises(AuthorizationInvalid):
            verify_authorization(
                proposal=PROPOSAL, request=altered,
                authorization=self.authorization, verifier=self.verifier,
            )

    def test_a_changed_nonce_with_the_same_request_id_is_refused(self):
        altered = dict(self.request)
        altered["nonce"] = "a-different-nonce"
        with self.assertRaises(AuthorizationReplay):
            verify_authorization(
                proposal=PROPOSAL, request=altered,
                authorization=self.authorization, verifier=self.verifier,
            )

    def test_a_string_scope_is_refused(self):
        """The reviewer's finding: _as_scope does not check the type.

        It does.
        """
        with self.assertRaises(AuthorizationInvalid):
            build_request(
                proposal=PROPOSAL, project="C", operation="file.delete",
                requested_scope="files:write", requested_by="ag",
                expires_at=_future(),
            )

    def test_a_non_list_scope_is_refused(self):
        with self.assertRaises(AuthorizationInvalid):
            build_request(
                proposal=PROPOSAL, project="C", operation="file.delete",
                requested_scope={"files:write"}, requested_by="ag",
                expires_at=_future(),
            )

    def test_a_non_ascii_key_is_refused(self):
        """The reviewer's finding: non-ASCII keys are escaped.

        They are rejected. This was fixed before the review ran.
        """
        from consequence_map.core.canonical import (
            CanonicalisationError,
            canonical_text,
        )
        with self.assertRaises(CanonicalisationError):
            canonical_text("d", {"\u00e9": "x"})


if __name__ == "__main__":
    unittest.main()
