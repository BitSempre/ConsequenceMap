"""Tests for crash recovery.

The property: **an operation whose outcome is unknown is never retried
automatically, and is never reported as completed.**

The recovery function has no handler access at all. That is how the
guarantee is structural rather than a promise.
"""
from __future__ import annotations

import os
import shutil
import tempfile
import unittest

from consequence_guard.recovery_after_crash import (
    classify_incomplete_operations,
    recover_operations,
)
from consequence_guard.store import GuardStore, OperationState


class RecoveryTestCase(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.mkdtemp(prefix="cm-crash-")
        self.path = os.path.join(self.directory, "guard.sqlite3")
        self.store = GuardStore(self.path)

    def tearDown(self):
        shutil.rmtree(self.directory, ignore_errors=True)

    def _record(self, state, operation_id="op-1"):
        self.store.record_operation(
            operation_id=operation_id, state=state, request_id="r",
            authorization_id="a", operation="file.delete", proposal_hash="h",
            now="2026-11-09T18:00:00.000Z",
        )


class ClassificationTests(RecoveryTestCase):
    """Each interrupted state gets the honest classification."""

    def test_an_operation_that_never_started_is_failed(self):
        self._record(OperationState.RECEIVED)
        report = recover_operations(self.store)
        self.assertEqual(report.count, 1)
        self.assertEqual(
            self.store.operation_state("op-1"), OperationState.FAILED
        )

    def test_a_consumed_but_unstarted_operation_is_failed(self):
        self._record(OperationState.CONSUMED)
        recover_operations(self.store)
        self.assertEqual(
            self.store.operation_state("op-1"), OperationState.FAILED
        )

    def test_an_operation_that_started_is_OUTCOME_UNKNOWN(self):
        self._record(OperationState.EXECUTION_STARTED)
        report = recover_operations(self.store)
        self.assertEqual(
            self.store.operation_state("op-1"), OperationState.OUTCOME_UNKNOWN
        )
        self.assertEqual(len(report.uncertain), 1)

    def test_an_unknown_outcome_is_never_retried(self):
        self._record(OperationState.EXECUTION_STARTED)
        recover_operations(self.store)
        # The operation is not in any state that a retry routine would
        # pick up, and the recovery function does not run anything.
        incomplete = classify_incomplete_operations(self.store)
        self.assertEqual(incomplete, [])

    def test_a_completed_operation_is_left_alone(self):
        self._record(OperationState.COMPLETED)
        report = recover_operations(self.store)
        self.assertEqual(report.count, 0)
        self.assertEqual(
            self.store.operation_state("op-1"), OperationState.COMPLETED
        )

    def test_the_classification_is_audited(self):
        self._record(OperationState.EXECUTION_STARTED)
        recover_operations(self.store)
        events = [r["event"] for r in self.store.audit_records()]
        self.assertIn("guard.recovery.classified", events)

    def test_the_reason_says_the_effect_may_have_happened(self):
        self._record(OperationState.EXECUTION_STARTED)
        report = recover_operations(self.store)
        self.assertIn("may or may not have happened", report.uncertain[0].reason)

    def test_the_reason_for_a_consumed_operation_says_a_new_approval_is_needed(self):
        self._record(OperationState.CONSUMED)
        report = recover_operations(self.store)
        self.assertIn("NEW authorisation", report.recovered[0].reason)


class RestartTests(RecoveryTestCase):
    """The classification survives a restart."""

    def test_recovery_runs_against_a_reopened_store(self):
        self._record(OperationState.EXECUTION_STARTED)
        reopened = GuardStore(self.path)
        report = recover_operations(reopened)
        self.assertEqual(report.count, 1)
        self.assertEqual(
            reopened.operation_state("op-1"), OperationState.OUTCOME_UNKNOWN
        )

    def test_recovery_is_idempotent(self):
        self._record(OperationState.EXECUTION_STARTED)
        recover_operations(self.store)
        second = recover_operations(self.store)
        self.assertEqual(second.count, 0)


if __name__ == "__main__":
    unittest.main()
