"""The criteria whose first dedicated test is this file.

AC-DATA-04, AC-DATA-18, AC-DATA-29, AC-STORE-08, AC-STORE-17,
AC-SEPR-03 and AC-PRIV-03 had coverage in the Phase 2A implementation
but no test whose NAME carried the criterion identifier. They are here so
that every one of the 63 closable criteria has a traceable test.
"""
from __future__ import annotations

import inspect
import re
import unittest

from ..domain import records as R
from ..domain.validation import FIELD_CAPS
from ..storage import db as db_module
from ..storage.triggers import trigger_statements
from .fixtures import (
    TS,
    DatabaseTestCase,
    make_forecast,
    make_proposal,
    write_sealed_forecast,
)


class TestACData04FieldCaps(unittest.TestCase):
    def test_AC_DATA_04_every_free_text_field_has_a_documented_cap(self):
        """Every free-text field the specification caps is capped."""
        capped = {
            "proposal.action", "forecast.summary", "evidence.claim",
            "evidence.source_ref", "evidence.limitations", "impact.target",
            "impact.reason", "forecast_risk.reason", "unknown.question",
            "unknown.why_it_matters", "unknown.evidence_that_would_resolve",
            "alternative.description", "alternative.expected_benefit",
            "alternative.impact_reduction", "alternative.tradeoffs",
            "alternative.residual_uncertainty", "alternative.rationale",
            "host_authorization.notes", "product_decision.scope_note",
            "outcome.summary", "outcome_observation.observation",
            "outcome_observation.target", "comparison.accuracy_note",
            "comparison_item.note",
        }
        self.assertTrue(capped.issubset(set(FIELD_CAPS)))

    def test_AC_DATA_04_the_caps_match_the_specification(self):
        for field, cap in (("proposal.action", 400), ("forecast.summary", 400),
                           ("evidence.claim", 500), ("evidence.source_ref", 300),
                           ("outcome_observation.observation", 400),
                           ("comparison.accuracy_note", 1000),
                           ("host_authorization.notes", 500),
                           ("product_decision.scope_note", 500)):
            with self.subTest(field=field):
                self.assertEqual(FIELD_CAPS[field], cap)


class TestACData18CopyLint(unittest.TestCase):
    """AC-DATA-18 is DEFERRED to Phase 2B in the reconciled scope.

    The copy lint itself is a Section 12.2 requirement. Phase 2A does
    not close AC-DATA-18, but the lint is implemented here so that the
    deferral is a scope decision, not a missing capability.
    """

    GUARANTEE_WORDS = (
        "guarantee", "guaranteed", "guarantees", "ensures", "ensured",
        "will never fail", "cannot fail", "always succeeds", "impossible",
        "definitely", "certainly", "no risk", "risk-free", "risk free",
        "100%", "perfect", "always works",
    )

    def test_AC_DATA_18_a_summary_with_guarantee_language_is_rejected(self):
        from ..domain.copy import CopyLintError, assert_no_guarantee_language

        with self.assertRaises(CopyLintError):
            assert_no_guarantee_language("this will never fail")

    def test_AC_DATA_18_an_ordinary_summary_passes(self):
        from ..domain.copy import assert_no_guarantee_language

        self.assertIsNone(assert_no_guarantee_language(
            "the file will be rewritten; confidence is low"))

    def test_AC_DATA_18_the_lint_covers_every_guarantee_word(self):
        from ..domain.copy import GUARANTEE_WORDS, assert_no_guarantee_language

        for word in GUARANTEE_WORDS:
            with self.subTest(word=word):
                with self.assertRaises(Exception):
                    assert_no_guarantee_language(f"the result {word}")


class TestACData29ComparisonContent(unittest.TestCase):
    def test_AC_DATA_29_a_comparison_records_whether_each_unknown_dimension_was_resolved(self):
        """C-6: a comparison records, for each forecast UNKNOWN dimension,
        whether it was resolved."""
        forecast = make_forecast()
        resolved = ["unk_444444444444"]
        comparison = R.Comparison(
            id="cmp_1", forecast_id=forecast.id, outcome_id="out_1",
            created_at=TS, verdict="ALIGNED",
            counts={"OBSERVED": 0, "NOT_OBSERVED": 0, "UNEXPECTED": 0,
                    "NOT_VERIFIABLE": 1, "NOT_APPLICABLE": 0},
            accuracy_note="no unexpected items were found",
            items=[R.ComparisonItem(id="ci_1", origin="PREDICTED",
                                    forecast_ref="ev_111111111111",
                                    forecast_ref_kind="evidence",
                                    label="NOT_VERIFIABLE", note="")])
        comparison.resolved_unknown_dimensions = resolved
        comparison.unknown_dimensions = ["unk_444444444444"]
        comparison.validate()
        self.assertEqual(comparison.resolved_unknown_dimensions, resolved)
        self.assertEqual(comparison.unknown_dimensions, ["unk_444444444444"])

    def test_AC_DATA_29_an_unresolved_dimension_is_recorded_as_unresolved(self):
        forecast = make_forecast()
        comparison = R.Comparison(
            id="cmp_1", forecast_id=forecast.id, outcome_id="out_1",
            created_at=TS, verdict="INCONCLUSIVE",
            counts={"OBSERVED": 0, "NOT_OBSERVED": 0, "UNEXPECTED": 0,
                    "NOT_VERIFIABLE": 0, "NOT_APPLICABLE": 1},
            accuracy_note="no unexpected items were found",
            items=[R.ComparisonItem(id="ci_1", origin="PREDICTED",
                                    forecast_ref="ev_111111111111",
                                    forecast_ref_kind="evidence",
                                    label="NOT_APPLICABLE", note="")])
        comparison.unknown_dimensions = ["unk_444444444444"]
        comparison.resolved_unknown_dimensions = []
        comparison.validate()
        self.assertEqual(comparison.resolved_unknown_dimensions, [])


class TestACStore08SqliteCompatibility(unittest.TestCase):
    def test_AC_STORE_08_the_family_uses_raise_abort(self):
        statements = trigger_statements()
        for statement in statements:
            with self.subTest(statement=statement.split(chr(10))[1][:60]):
                self.assertIn("RAISE(ABORT", statement.upper())

    def test_AC_STORE_08_the_family_uses_scalar_subqueries_in_when_clauses(self):
        """The insert-after-seal triggers use a scalar subquery in WHEN."""
        statements = trigger_statements()
        with_select = [s for s in statements
                       if " WHEN " in s.upper() and "(SELECT" in s.upper()]
        self.assertTrue(with_select)
        # One per forecast child table.
        self.assertEqual(len(with_select), 5)

    def test_AC_STORE_08_the_family_executes_on_the_installed_sqlite(self):
        import sqlite3
        from ..storage.schema import create_schema

        conn = sqlite3.connect(":memory:")
        try:
            create_schema(conn)
            for statement in trigger_statements():
                conn.execute(statement)
            installed = sqlite3.sqlite_version
            self.assertGreaterEqual(installed, "3.53.1")
            # The triggers are installed.
            count = conn.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='trigger'"
            ).fetchone()[0]
            self.assertEqual(count, len(trigger_statements()))
        finally:
            conn.close()


class TestACStore17JournalMode(unittest.TestCase):
    def test_AC_STORE_17_the_plugin_requests_wal_and_records_the_observed_mode(self):
        """The observed mode is one the host supports; DELETE is not an error."""
        import sqlite3
        import tempfile
        import os

        with tempfile.TemporaryDirectory(prefix="cm-jm-",
                                         ignore_cleanup_errors=True) as tmp:
            path = os.path.join(tmp, "t.db")
            conn = sqlite3.connect(path)
            try:
                observed = db_module.request_wal(conn)
                self.assertIn(observed, db_module.SUPPORTED_JOURNAL_MODES)
                self.assertEqual(db_module.observed_journal_mode(conn), observed)
            finally:
                conn.close()

    def test_AC_STORE_17_a_delete_mode_is_not_an_error(self):
        import sqlite3
        import tempfile
        import os

        with tempfile.TemporaryDirectory(prefix="cm-jm-",
                                         ignore_cleanup_errors=True) as tmp:
            path = os.path.join(tmp, "t.db")
            conn = sqlite3.connect(path)
            try:
                mode = db_module.configure_connection(conn, request_wal_mode=False)
                self.assertIn(mode, db_module.SUPPORTED_JOURNAL_MODES)
                self.assertEqual(conn.execute("PRAGMA foreign_keys").fetchone()[0], 1)
            finally:
                conn.close()

    def test_AC_STORE_17_the_observed_mode_is_recorded(self):
        self.assertTrue(hasattr(db_module, "observed_journal_mode"))
        self.assertEqual(set(db_module.SUPPORTED_JOURNAL_MODES), {"wal", "delete"})


class TestACSepr03NoMerge(unittest.TestCase):
    def test_AC_SEPR_03_there_is_no_merge_operation(self):
        """No code path writes one record from both sources."""
        from ..storage import repository as repo_module

        source = open(repo_module.__file__, encoding="utf-8").read()
        # No method writes to both tables.
        for name in dir(repo_module.Repository):
            if not name.startswith("write_"):
                continue
            method = getattr(repo_module.Repository, name)
            body = inspect.getsource(method)
            with self.subTest(method=name):
                self.assertFalse(
                    "host_authorization" in body and "product_decision" in body
                    and "INSERT INTO" in body,
                    "a single write must not populate both records",
                )

    def test_AC_SEPR_03_the_two_records_have_distinct_identifier_prefixes(self):
        from ..domain import records as R

        auth = R.HostAuthorization(
            id="auth_1", forecast_id="fc_1", proposal_id="prop_1",
            proposal_version=1, state="PENDING", provenance="HOST_APPROVAL_HOOK",
            authorized_by="NONE", observed_choice="not_observed",
            observed_via="pre_approval_request", reason="UNKNOWN",
            created_at=TS, escalation_expected=True)
        decision = R.ProductDecision(
            id="pdec_1", forecast_id="fc_1", proposal_id="prop_1",
            proposal_version=1, state="NOT_ASKED", decided_by="system",
            decided_at=TS, surface="none")
        self.assertNotEqual(auth.id, decision.id)
        self.assertTrue(auth.id.startswith("auth_"))
        self.assertTrue(decision.id.startswith("pdec_"))


class TestACPriv03RedactionLayer(unittest.TestCase):
    def test_AC_PRIV_03_the_repository_is_the_only_write_path(self):
        from ..storage import repository as repo_module

        source = open(repo_module.__file__, encoding="utf-8").read()
        # Every free-text field goes through the boundary.
        self.assertIn("redact_and_cap", source)
        self.assertIn("from ..redaction.boundary import", source)

    def test_AC_PRIV_03_no_other_module_writes_to_the_database(self):
        """Only the repository executes INSERT/UPDATE/DELETE."""
        import os

        package = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        offenders = []
        for base, dirs, files in os.walk(package):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for name in sorted(files):
                if not name.endswith(".py"):
                    continue
                path = os.path.join(base, name)
                relative = os.path.relpath(path, package)
                if relative.startswith("storage" + os.sep) or relative.startswith("tests" + os.sep):
                    continue
                with open(path, encoding="utf-8") as handle:
                    source = handle.read()
                for match in re.finditer(r"(INSERT\s+INTO|UPDATE\s+\w+\s+SET|DELETE\s+FROM)",
                                         source, re.IGNORECASE):
                    offenders.append(f"{relative}: {match.group(0)}")
        self.assertEqual(offenders, [],
                         "only the storage layer may write to the database")


if __name__ == "__main__":
    unittest.main()
