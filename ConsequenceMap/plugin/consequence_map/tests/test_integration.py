"""The integration layer (L3 of the local suite).

AC-DATA-16, AC-DATA-24, AC-STORE-10 - the read-path behaviours - and
the seal concurrency fixture (MC8/R12).

These run against a real SQLite database in a temporary directory, in
both journal modes the host supports.
"""
from __future__ import annotations

import os
import sqlite3
import tempfile
import threading
import unittest

from ..storage import db as db_module
from ..storage.migrations import apply_migrations
from ..storage.repository import Repository
from .fixtures import (
    TS,
    deterministic_redactor,
    make_forecast,
    make_proposal,
    temp_provider,
)


class TestReadPathsAfterSeal(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="cm-int-", ignore_cleanup_errors=True)
        self.db_path = os.path.join(self._tmp.name, "data.db")
        self.conn = db_module.connect(self.db_path, provider=temp_provider)
        apply_migrations(self.conn)
        self.repo = Repository(self.conn)

    def tearDown(self):
        try:
            self.conn.close()
        finally:
            self._tmp.cleanup()

    def test_AC_DATA_16_a_sealed_forecast_is_returned_by_the_read_path(self):
        from ..redaction import boundary

        boundary.set_redactor(deterministic_redactor)
        try:
            self.repo.write_proposal(make_proposal())
            forecast = make_forecast()
            self.repo.write_forecast(forecast)
            self.repo.seal_forecast(forecast.id)
        finally:
            boundary.set_redactor(None)
        rows = self.repo.read_sealed_forecasts()
        self.assertEqual(len(rows), 1)
        self.assertIsNotNone(rows[0][8])

    def test_AC_STORE_10_an_unsealed_forecast_is_invisible(self):
        from ..redaction import boundary

        boundary.set_redactor(deterministic_redactor)
        try:
            self.repo.write_proposal(make_proposal())
            forecast = make_forecast()
            self.repo.write_forecast(forecast)
        finally:
            boundary.set_redactor(None)
        self.assertEqual(self.repo.read_sealed_forecasts(), [])
        self.assertIsNone(self.repo.read_forecast(forecast.id))

    def test_AC_DATA_24_the_forecast_is_unchanged_after_the_outcome(self):
        from ..domain import records as R
        from ..redaction import boundary

        boundary.set_redactor(deterministic_redactor)
        try:
            self.repo.write_proposal(make_proposal())
            forecast = make_forecast()
            self.repo.write_forecast(forecast)
            self.repo.seal_forecast(forecast.id)
            before = self.conn.execute(
                "SELECT content_hash, summary FROM forecast WHERE id = ?",
                (forecast.id,)).fetchone()
            execution = R.Execution(id="exe_1", forecast_id=forecast.id,
                                     started_at=TS, status="COMPLETED", source="hook")
            self.repo.write_execution(execution)
            outcome = R.Outcome(id="out_1", forecast_id=forecast.id,
                                execution_id=execution.id, recorded_at=TS,
                                recorded_by="agent", verification_method="MANUAL",
                                summary="checked", observations=[])
            self.repo.write_outcome(outcome)
        finally:
            boundary.set_redactor(None)
        after = self.conn.execute(
            "SELECT content_hash, summary FROM forecast WHERE id = ?",
            (forecast.id,)).fetchone()
        self.assertEqual(before, after)


class TestSealConcurrency(unittest.TestCase):
    """MC8/R12: exactly one of two concurrent seals succeeds.

    The barrier removes the race from the outcome; what remains is the
    lock, which is the behaviour under test.
    """

    def _run_race(self, journal_mode):
        with tempfile.TemporaryDirectory(prefix="cm-race-",
                                         ignore_cleanup_errors=True) as tmp:
            path = os.path.join(tmp, "data.db")
            setup = db_module.connect(path, provider=temp_provider)
            apply_migrations(setup)
            setup.execute(f"PRAGMA journal_mode={journal_mode}")
            from ..redaction import boundary

            boundary.set_redactor(deterministic_redactor)
            try:
                repo = Repository(setup)
                repo.write_proposal(make_proposal())
                forecast = make_forecast()
                repo.write_forecast(forecast)
            finally:
                boundary.set_redactor(None)
            setup.close()

            barrier = threading.Barrier(2)
            results = []
            lock = threading.Lock()

            def attempt():
                conn = db_module.connect(path, provider=temp_provider)
                try:
                    conn.execute(f"PRAGMA journal_mode={journal_mode}")
                    # The barrier is OUTSIDE the transaction. A write
                    # transaction takes the database's write lock, so two
                    # threads synchronising inside one could never both
                    # reach the barrier - the first would hold the lock
                    # while the second waited for it.
                    barrier.wait(timeout=10)
                    try:
                        conn.execute("BEGIN IMMEDIATE")
                        cursor = conn.execute(
                            "UPDATE forecast SET sealed_at = ? WHERE id = ? AND sealed_at IS NULL",
                            (TS, forecast.id))
                        conn.commit()
                        # A second seal matches ZERO rows because the row
                        # is already sealed. The trigger does not fire in
                        # that case - the rowcount is what distinguishes
                        # the winner from the loser.
                        with lock:
                            results.append("sealed" if cursor.rowcount == 1 else "rejected")
                    except sqlite3.Error:
                        try:
                            conn.rollback()
                        except sqlite3.Error:
                            pass
                        with lock:
                            results.append("rejected")
                finally:
                    conn.close()

            threads = [threading.Thread(target=attempt) for _ in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=20)

            check = db_module.connect(path, provider=temp_provider)
            try:
                row = check.execute(
                    "SELECT sealed_at FROM forecast WHERE id = ?", (forecast.id,)
                ).fetchone()
                children = check.execute(
                    "SELECT COUNT(*) FROM forecast_evidence WHERE forecast_id = ?",
                    (forecast.id,)).fetchone()[0]
            finally:
                check.close()
            return results, row[0], children

    def test_exactly_one_seal_succeeds_in_wal_mode(self):
        results, sealed_at, children = self._run_race("wal")
        self.assertEqual(results.count("sealed"), 1, f"results={results}")
        self.assertEqual(results.count("rejected"), 1, f"results={results}")
        self.assertIsNotNone(sealed_at)
        self.assertEqual(children, 1)

    def test_exactly_one_seal_succeeds_in_delete_mode(self):
        results, sealed_at, children = self._run_race("delete")
        self.assertEqual(results.count("sealed"), 1, f"results={results}")
        self.assertEqual(results.count("rejected"), 1, f"results={results}")
        self.assertIsNotNone(sealed_at)
        self.assertEqual(children, 1)

    def test_the_race_is_stable_across_twenty_iterations(self):
        for iteration in range(20):
            with self.subTest(iteration=iteration):
                results, sealed_at, _children = self._run_race("wal")
                self.assertEqual(results.count("sealed"), 1, f"results={results}")


if __name__ == "__main__":
    unittest.main()
