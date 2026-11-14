"""The schema of specification section 3.2, and the separation rules.

AC-STORE-12, AC-SEPR-01, AC-SEPR-02, AC-SEPR-03.
"""
from __future__ import annotations

import unittest

from ..storage.schema import ALL_TABLES, DDL_STATEMENTS, OBSERVATION_TABLES
from .fixtures import DatabaseTestCase


class TestSchemaShape(DatabaseTestCase):
    def test_there_are_exactly_17_tables(self):
        self.assertEqual(len(ALL_TABLES), 17)

    def test_every_table_exists_after_migration(self):
        present = set(self.repo.table_names())
        for table in ALL_TABLES:
            with self.subTest(table=table):
                self.assertIn(table, present)

    def test_the_observation_tables_exclude_the_three_exceptions(self):
        self.assertNotIn("proposal", OBSERVATION_TABLES)
        self.assertNotIn("product_decision", OBSERVATION_TABLES)
        self.assertNotIn("host_authorization", OBSERVATION_TABLES)
        self.assertEqual(len(OBSERVATION_TABLES), 14)

    def test_AC_SEPR_01_the_two_records_are_separate_tables_with_separate_prefixes(self):
        columns = {t: [r[1] for r in self.conn.execute(f"PRAGMA table_info({t})")]
                   for t in ("host_authorization", "product_decision")}
        self.assertIn("id", columns["host_authorization"])
        self.assertIn("id", columns["product_decision"])
        self.assertIn("state", columns["host_authorization"])
        self.assertIn("state", columns["product_decision"])
        self.assertIn("decided_by", columns["product_decision"])
        self.assertIn("authorized_by", columns["host_authorization"])

    def test_AC_SEPR_02_there_is_no_foreign_key_between_the_two_records(self):
        for table in ("host_authorization", "product_decision"):
            with self.subTest(table=table):
                fks = list(self.conn.execute(f"PRAGMA foreign_key_list({table})"))
                targets = {row[2] for row in fks}
                self.assertNotIn("host_authorization", targets)
                self.assertNotIn("product_decision", targets)

    def test_the_forecast_has_the_composite_foreign_key(self):
        # PRAGMA foreign_key_list columns:
        #   0 id, 1 seq, 2 table (the PARENT table), 3 from, 4 to, ...
        # For a composite FK there are two rows, one per column.
        fks = list(self.conn.execute("PRAGMA foreign_key_list(forecast)"))
        self.assertTrue(fks, "forecast must reference proposal")
        froms = sorted(row[3] for row in fks)
        tos = sorted(row[4] for row in fks)
        self.assertEqual(froms, ["proposal_id", "proposal_version"])
        self.assertEqual(tos, ["id", "version"])
        # Both columns belong to the SAME parent table.
        self.assertEqual({row[2] for row in fks}, {"proposal"})

    def test_the_forecast_has_the_seal_column(self):
        columns = [r[1] for r in self.conn.execute("PRAGMA table_info(forecast)")]
        self.assertIn("sealed_at", columns)
        self.assertIn("content_hash", columns)

    def test_the_child_tables_are_keyed_by_forecast_id(self):
        for child in ("forecast_evidence", "forecast_impact", "forecast_risk",
                      "forecast_alternative", "forecast_unknown"):
            with self.subTest(child=child):
                columns = [r[1] for r in self.conn.execute(f"PRAGMA table_info({child})")]
                self.assertEqual(columns[0], "forecast_id")

    def test_the_schema_version_is_recorded(self):
        row = self.conn.execute("SELECT schema_version FROM schema_meta").fetchone()
        self.assertEqual(row[0], 1)


if __name__ == "__main__":
    unittest.main()
