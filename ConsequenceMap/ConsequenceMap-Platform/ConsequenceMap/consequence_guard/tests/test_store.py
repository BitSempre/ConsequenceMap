"""Tests for the durable guard store.

The two properties this store exists to provide are:

1. **Atomic single-use.** Two processes that race for the same
   authorization produce exactly ONE winner. Not "usually one" - one.
2. **Durability.** A restart does not forget what was spent.

Everything else in the store is in service of those two.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest

from consequence_guard.store import (
    ConsumptionResult,
    GuardStore,
    OperationState,
    StoreError,
    StoreUnavailable,
)

PROJECT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _store(directory, name="guard.sqlite3"):
    return GuardStore(os.path.join(directory, name))


class ConsumptionTests(unittest.TestCase):
    """One authorization, one consumption."""

    def setUp(self):
        self.directory = tempfile.mkdtemp(prefix="cm-guard-")
        self.store = _store(self.directory)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.directory, ignore_errors=True)

    def _consume(self, key="key-1", **overrides):
        arguments = dict(
            spent_key=key,
            authorization_id="auth-1",
            nonce="nonce-1",
            request_id="req-1",
            operation_id="op-1",
            consumed_by="guard",
            now="2026-11-09T18:00:00.000Z",
        )
        arguments.update(overrides)
        return self.store.consume(**arguments)

    def test_the_first_consumption_succeeds(self):
        result = self._consume()
        self.assertTrue(result.consumed)
        self.assertEqual(result.reason, "")

    def test_the_second_consumption_is_refused(self):
        self._consume()
        result = self._consume()
        self.assertFalse(result.consumed)
        self.assertIn("already", result.reason)

    def test_a_consumed_authorization_is_recorded(self):
        self._consume()
        self.assertTrue(self.store.is_consumed("key-1"))
        self.assertFalse(self.store.is_consumed("key-2"))

    def test_different_authorizations_do_not_collide(self):
        self.assertTrue(self._consume(key="key-1").consumed)
        self.assertTrue(self._consume(key="key-2").consumed)
        self.assertEqual(self.store.consumption_count(), 2)


class DurabilityTests(unittest.TestCase):
    """A restart does not forget."""

    def setUp(self):
        self.directory = tempfile.mkdtemp(prefix="cm-guard-")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.directory, ignore_errors=True)

    def test_a_consumption_survives_a_restart(self):
        first = _store(self.directory)
        first.consume(
            spent_key="key-1", authorization_id="auth-1", nonce="n",
            request_id="r", operation_id="o", consumed_by="g",
            now="2026-11-09T18:00:00.000Z",
        )
        second = _store(self.directory)
        self.assertTrue(second.is_consumed("key-1"))
        result = second.consume(
            spent_key="key-1", authorization_id="auth-1", nonce="n",
            request_id="r", operation_id="o", consumed_by="g",
            now="2026-11-09T18:00:01.000Z",
        )
        self.assertFalse(result.consumed)

    def test_operations_survive_a_restart(self):
        first = _store(self.directory)
        first.record_operation(
            operation_id="op-1", state=OperationState.CONSUMED,
            request_id="r", authorization_id="a", operation="file.delete",
            proposal_hash="h", now="2026-11-09T18:00:00.000Z",
        )
        second = _store(self.directory)
        self.assertEqual(
            second.operation_state("op-1"), OperationState.CONSUMED
        )


class OperationStateTests(unittest.TestCase):
    """The operation state machine is recorded, not assumed."""

    def setUp(self):
        self.directory = tempfile.mkdtemp(prefix="cm-guard-")
        self.store = _store(self.directory)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.directory, ignore_errors=True)

    def _record(self, state, operation_id="op-1"):
        self.store.record_operation(
            operation_id=operation_id, state=state, request_id="r",
            authorization_id="a", operation="file.delete", proposal_hash="h",
            now="2026-11-09T18:00:00.000Z",
        )

    def test_an_unknown_state_is_refused(self):
        with self.assertRaises(StoreError):
            self._record("MADE_UP_STATE")

    def test_a_state_transition_is_recorded(self):
        self._record(OperationState.RECEIVED)
        self._record(OperationState.CONSUMED)
        self.assertEqual(
            self.store.operation_state("op-1"), OperationState.CONSUMED
        )

    def test_operations_with_an_unknown_outcome_can_be_found(self):
        self._record(OperationState.EXECUTION_STARTED)
        self._record(OperationState.OUTCOME_UNKNOWN)
        found = self.store.operations_in_state(OperationState.OUTCOME_UNKNOWN)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["operation_id"], "op-1")


class AuditTests(unittest.TestCase):
    """The chain, the checkpoints, and the failure modes."""

    def setUp(self):
        self.directory = tempfile.mkdtemp(prefix="cm-guard-")
        self.store = _store(self.directory)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.directory, ignore_errors=True)

    def test_records_are_appended_in_order(self):
        for index in range(4):
            self.store.append_audit(
                "event-%d" % index, {"index": index}, "2026-11-09T18:00:00.000Z"
            )
        records = self.store.audit_records()
        self.assertEqual([r["sequence"] for r in records], [0, 1, 2, 3])

    def test_the_chain_links(self):
        for index in range(3):
            self.store.append_audit("e", {"i": index}, "2026-11-09T18:00:00.000Z")
        records = self.store.audit_records()
        for index in range(1, len(records)):
            self.assertEqual(
                records[index]["previous_hash"], records[index - 1]["record_hash"]
            )

    def test_a_checkpoint_records_the_head(self):
        self.store.append_audit("e", {}, "2026-11-09T18:00:00.000Z")
        head = self.store.audit_head()
        self.store.write_checkpoint("cp-1", "2026-11-09T18:00:01.000Z")
        checkpoints = self.store.checkpoints()
        self.assertEqual(checkpoints[0]["record_hash"], head)

    def test_the_audit_survives_a_restart(self):
        self.store.append_audit("e", {"x": 1}, "2026-11-09T18:00:00.000Z")
        second = _store(self.directory)
        self.assertEqual(len(second.audit_records()), 1)


class ConcurrencyTests(unittest.TestCase):
    """Two PROCESSES. One winner.

    Threads would not prove it: the GIL would serialise them and the
    test would pass for the wrong reason. The point of the durable
    store is that the guarantee holds across processes.
    """

    def setUp(self):
        self.directory = tempfile.mkdtemp(prefix="cm-guard-")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.directory, ignore_errors=True)

    def test_two_processes_race_for_one_authorization(self):
        path = os.path.join(self.directory, "guard.sqlite3")
        worker = os.path.join(self.directory, "worker.py")
        with open(worker, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(textwrap.dedent(
                """
                import json, sys
                sys.path.insert(0, %r)
                from consequence_guard.store import GuardStore

                store = GuardStore(sys.argv[1])
                result = store.consume(
                    spent_key="contended",
                    authorization_id="auth-1",
                    nonce="n",
                    request_id="r",
                    operation_id="o",
                    consumed_by=sys.argv[2],
                    now="2026-11-09T18:00:00.000Z",
                )
                print(json.dumps({"consumed": result.consumed,
                                  "reason": result.reason}))
                """
            ) % PROJECT)

        processes = [
            subprocess.Popen(
                [sys.executable, worker, path, "worker-%d" % index],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )
            for index in range(2)
        ]
        outputs = []
        for process in processes:
            out, err = process.communicate(timeout=120)
            self.assertEqual(process.returncode, 0, err)
            outputs.append(json.loads(out.strip().splitlines()[-1]))

        winners = [o for o in outputs if o["consumed"]]
        self.assertEqual(
            len(winners), 1,
            "exactly one process must consume the authorization, got %r" % (outputs,),
        )
        store = _store(self.directory)
        self.assertEqual(store.consumption_count(), 1)


class FailClosedTests(unittest.TestCase):
    """An unavailable store is a refusal, not an accident."""

    def setUp(self):
        self.directory = tempfile.mkdtemp(prefix="cm-guard-")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.directory, ignore_errors=True)

    def test_an_unwritable_location_is_refused(self):
        # A path whose parent is a FILE, not a directory.
        blocker = os.path.join(self.directory, "blocker")
        with open(blocker, "w", encoding="utf-8") as handle:
            handle.write("not a directory")
        with self.assertRaises(StoreUnavailable):
            GuardStore(os.path.join(blocker, "guard.sqlite3"))

    def test_a_directory_instead_of_a_database_is_refused(self):
        directory = os.path.join(self.directory, "as-directory")
        os.makedirs(directory)
        with self.assertRaises(StoreUnavailable):
            GuardStore(directory)


if __name__ == "__main__":
    unittest.main()
