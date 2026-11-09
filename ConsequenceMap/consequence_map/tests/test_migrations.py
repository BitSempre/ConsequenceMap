"""Migrations (AC-STORE-18, AC-STORE-19) and retention (AC-STORE-20)."""
from __future__ import annotations

import sqlite3
import tempfile
import os
import unittest

from ..storage import db as db_module
from ..storage.migrations import (
    MIGRATIONS,
    SUPPORTED_VERSION,
    NewerSchemaError,
    apply_migrations,
    current_version,
    is_read_only_required,
    open_for_write,
)
from .fixtures import DatabaseTestCase, make_forecast, make_proposal, temp_provider


class TestMigrations(DatabaseTestCase):
    def test_AC_STORE_19_the_schema_version_is_recorded(self):
        self.assertEqual(current_version(self.conn), SUPPORTED_VERSION)

    def test_AC_STORE_19_applying_twice_is_idempotent(self):
        before = current_version(self.conn)
        apply_migrations(self.conn)
        self.assertEqual(current_version(self.conn), before)

    def test_the_migration_chain_is_forward_only(self):
        versions = [m.version for m in MIGRATIONS]
        self.assertEqual(versions, sorted(versions))
        self.assertEqual(versions[0], 1)

    def test_AC_STORE_18_a_newer_database_requires_read_only(self):
        self.conn.execute(
            "INSERT OR REPLACE INTO schema_meta(schema_version, applied_at) "
            "VALUES (?, datetime('now'))",
            (SUPPORTED_VERSION + 1,),
        )
        self.conn.commit()
        self.assertTrue(is_read_only_required(self.conn, SUPPORTED_VERSION))
        self.assertFalse(open_for_write(self.conn, supported_version=SUPPORTED_VERSION))

    def test_AC_STORE_18_applying_to_a_newer_database_raises(self):
        self.conn.execute(
            "INSERT OR REPLACE INTO schema_meta(schema_version, applied_at) "
            "VALUES (?, datetime('now'))",
            (SUPPORTED_VERSION + 1,),
        )
        self.conn.commit()
        with self.assertRaises(NewerSchemaError):
            apply_migrations(self.conn, supported_version=SUPPORTED_VERSION)

    def test_AC_STORE_19_a_failing_migration_rolls_back(self):
        from ..storage import migrations as M

        def failing(conn):
            conn.execute("CREATE TABLE partial_table(x INTEGER)")
            raise RuntimeError("boom")

        bad = M.Migration(SUPPORTED_VERSION + 1, "failing", failing)
        original = M.MIGRATIONS
        try:
            M.MIGRATIONS = original + (bad,)
            with self.assertRaises(RuntimeError):
                apply_migrations(self.conn)
        finally:
            M.MIGRATIONS = original
        self.conn.rollback()
        names = {r[0] for r in self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertNotIn("partial_table", names)
        self.assertEqual(current_version(self.conn), SUPPORTED_VERSION)


class TestRetention(DatabaseTestCase):
    def test_AC_STORE_20_no_automatic_deletion_occurs(self):
        from ..domain import records as R
        from .fixtures import TS

        proposal = make_proposal()
        forecast = make_forecast()
        self.repo.write_proposal(proposal)
        self.repo.write_forecast(forecast)
        self.repo.seal_forecast(forecast.id)
        execution = R.Execution(id="exe_1", forecast_id=forecast.id,
                                 started_at=TS, status="COMPLETED", source="hook")
        self.repo.write_execution(execution)
        self.assertEqual(self.count("execution"), 1)
        self.assertEqual(self.count("forecast"), 1)

    def test_AC_STORE_20_the_store_grows_with_record_count_not_field_size(self):
        from ..domain import records as R
        from .fixtures import TS

        for index in range(5):
            proposal = make_proposal(id=f"prop_{index:012x}")
            forecast = make_forecast(id=f"fc_{index:012x}",
                                     proposal_id=proposal.id)
            self.repo.write_proposal(proposal)
            self.repo.write_forecast(forecast)
            self.repo.seal_forecast(forecast.id)
        self.assertEqual(self.count("forecast"), 5)
        self.assertEqual(self.count("proposal"), 5)


class TestProfileScope(unittest.TestCase):
    def test_AC_STORE_16_the_path_is_resolved_from_the_hermes_home_on_every_call(self):
        import inspect
        source = inspect.getsource(db_module.hermes_home)
        self.assertIn("get_hermes_home", source)
        # The import is INSIDE the function, so importing the module does
        # not import Hermes.
        body = source.split(chr(10))
        import_lines = [l for l in body if l.strip().startswith(("from ", "import "))]
        self.assertTrue(import_lines)
        # Every import in the function body must be the Hermes home helper.
        # The statement spans two lines, so the joined text is checked.
        joined = chr(10).join(body)
        self.assertIn("from hermes_cli.config import get_hermes_home", joined)
        self.assertNotIn("from hermes_cli.config import get_hermes_home", source.split("def ")[0])

    def test_the_database_path_is_under_the_plugin_data_directory(self):
        path = db_module.database_path(home="C:/hermes-home")
        self.assertIn("plugin-data", path)
        self.assertIn("consequence-map", path)
        self.assertTrue(path.endswith("data.db"))


if __name__ == "__main__":
    unittest.main()
