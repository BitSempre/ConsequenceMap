"""The trigger family (AC-STORE-01 .. AC-STORE-08, MC4/R06).

The family is GENERATED, not transcribed. These tests execute it against
the installed SQLite.
"""
from __future__ import annotations

import sqlite3
import unittest

from ..storage import triggers as T
from ..storage.schema import ALL_TABLES, FORECAST_CHILD_TABLES, OBSERVATION_TABLES
from .fixtures import DatabaseTestCase, make_forecast, make_proposal, write_sealed_forecast


class TestTriggerFamilyShape(unittest.TestCase):
    def test_the_family_covers_every_forecast_child_table(self):
        statements = T.trigger_statements()
        for child in FORECAST_CHILD_TABLES:
            with self.subTest(child=child):
                joined = " ".join(statements)
                self.assertIn(f"{child}_no_insert_after_seal", joined)
                self.assertIn(f"{child}_no_update", joined)
                self.assertIn(f"{child}_no_delete", joined)

    def test_the_family_is_generated_from_the_schema_parameter(self):
        statements = T.trigger_statements(["forecast_evidence"])
        joined = " ".join(statements)
        self.assertIn("forecast_evidence_no_update", joined)
        self.assertNotIn("forecast_impact_no_update", joined)

    def test_the_observation_tables_all_reject_update_and_delete(self):
        statements = T.trigger_statements()
        joined = " ".join(statements)
        for table in OBSERVATION_TABLES:
            if table in FORECAST_CHILD_TABLES:
                continue
            with self.subTest(table=table):
                if table == "forecast":
                    # `forecast` permits exactly ONE update - the seal - so
                    # it has `forecast_seal_only`, not `forecast_no_update`.
                    self.assertIn("forecast_seal_only", joined)
                else:
                    self.assertIn(f"{table}_no_update", joined)
                self.assertIn(f"{table}_no_delete", joined)

    def test_the_family_uses_raise_abort_and_scalar_subqueries(self):
        statements = T.trigger_statements()
        joined = " ".join(statements).upper()
        self.assertIn("RAISE(ABORT", joined)
        self.assertIn("(SELECT SEALED_AT FROM FORECAST", joined)


class TestSealTriggers(DatabaseTestCase):
    def setUp(self):
        super().setUp()
        self.proposal = make_proposal()
        self.forecast = make_forecast()
        self.repo.write_proposal(self.proposal)
        self.repo.write_forecast(self.forecast)

    def _abort(self, sql, params=()):
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(sql, params)
        self.conn.rollback()

    def test_AC_STORE_01_the_first_seal_succeeds(self):
        self.repo.seal_forecast(self.forecast.id)
        row = self.conn.execute(
            "SELECT sealed_at FROM forecast WHERE id = ?", (self.forecast.id,)
        ).fetchone()
        self.assertIsNotNone(row[0])

    def test_AC_STORE_01_a_second_seal_is_rejected(self):
        self.repo.seal_forecast(self.forecast.id)
        self._abort("UPDATE forecast SET sealed_at = ? WHERE id = ?",
                    ("2026-11-08T00:00:00.000Z", self.forecast.id))

    def test_AC_STORE_02_the_only_permitted_update_is_the_seal(self):
        self._abort("UPDATE forecast SET summary = 'tampered' WHERE id = ?",
                    (self.forecast.id,))

    def test_AC_STORE_02_a_content_hash_change_is_rejected(self):
        self._abort("UPDATE forecast SET content_hash = ? WHERE id = ?",
                    ("f" * 64, self.forecast.id))

    def test_AC_STORE_03_unsealing_is_rejected(self):
        self.repo.seal_forecast(self.forecast.id)
        self._abort("UPDATE forecast SET sealed_at = NULL WHERE id = ?",
                    (self.forecast.id,))

    def test_AC_STORE_04_a_multi_column_tamper_is_rejected_in_one_statement(self):
        self._abort(
            "UPDATE forecast SET summary = 'x', confidence_overall = 'HIGH' WHERE id = ?",
            (self.forecast.id,),
        )

    def test_AC_STORE_05_delete_is_always_rejected(self):
        self._abort("DELETE FROM forecast WHERE id = ?", (self.forecast.id,))

    def test_AC_STORE_06_an_insert_after_the_seal_is_rejected(self):
        self.repo.seal_forecast(self.forecast.id)
        self._abort(
            "INSERT INTO forecast_evidence (forecast_id, id, claim, classification, "
            "source_kind, source_ref, observed_at, confidence) "
            "VALUES (?, 'ev_x', 'c', 'VERIFIED_FACT', 'FILESYSTEM', 'r', "
            "'2026-11-07T00:00:00.000Z', 'LOW')",
            (self.forecast.id,),
        )

    def test_AC_STORE_07_a_child_update_is_rejected(self):
        # forecast_risk has no `id` column - its primary key is forecast_id.
        key_column = {"forecast_risk": "severity"}
        for child in FORECAST_CHILD_TABLES:
            with self.subTest(child=child):
                column = key_column.get(child, "id")
                self._abort(f"UPDATE {child} SET {column} = 'x' WHERE forecast_id = ?",
                            (self.forecast.id,))

    def test_AC_STORE_07_a_child_delete_is_rejected(self):
        for child in FORECAST_CHILD_TABLES:
            with self.subTest(child=child):
                self._abort(f"DELETE FROM {child} WHERE forecast_id = ?",
                            (self.forecast.id,))

    def test_R06_a_child_insert_after_the_seal_is_rejected_for_every_child(self):
        self.repo.seal_forecast(self.forecast.id)
        inserts = {
            "forecast_evidence": (
                "INSERT INTO forecast_evidence (forecast_id, id, claim, classification, "
                "source_kind, source_ref, observed_at, confidence) "
                "VALUES (?, 'ev_x', 'c', 'VERIFIED_FACT', 'FILESYSTEM', 'r', "
                "'2026-11-07T00:00:00.000Z', 'LOW')"),
            "forecast_impact": (
                "INSERT INTO forecast_impact (forecast_id, id, target, impact_class, "
                "relation, classification, severity_contribution, confidence, reason, "
                "observable) VALUES (?, 'im_x', 't', 'FILES', 'DIRECT', 'VERIFIED_FACT', "
                "'LOW', 'LOW', 'r', 1)"),
            "forecast_risk": (
                "INSERT INTO forecast_risk (forecast_id, severity, confidence, "
                "reversibility, reason, escalation_rule, requires_human_approval, "
                "dimension_caveats_json) VALUES (?, 'LOW', 'LOW', 'EASY', 'r', 'E-NONE', "
                "0, '[]')"),
            "forecast_alternative": (
                "INSERT INTO forecast_alternative (forecast_id, id, description, "
                "expected_benefit, impact_reduction, tradeoffs, residual_uncertainty, "
                "recommended) VALUES (?, 'alt_x', 'd', 'b', 'i', 't', 'u', 0)"),
            "forecast_unknown": (
                "INSERT INTO forecast_unknown (forecast_id, id, question, "
                "why_it_matters, evidence_that_would_resolve) "
                "VALUES (?, 'unk_x', 'q', 'w', 'e')"),
        }
        for child, sql in inserts.items():
            with self.subTest(child=child):
                self._abort(sql, (self.forecast.id,))

    def test_the_data_is_intact_after_every_abort(self):
        self.repo.seal_forecast(self.forecast.id)
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute("DELETE FROM forecast WHERE id = ?", (self.forecast.id,))
        self.conn.rollback()
        for child in FORECAST_CHILD_TABLES:
            with self.subTest(child=child):
                count = self.conn.execute(
                    f"SELECT COUNT(*) FROM {child} WHERE forecast_id = ?",
                    (self.forecast.id,),
                ).fetchone()[0]
                self.assertEqual(count, 1)


class TestObservationImmutability(DatabaseTestCase):
    def test_AC_STORE_12_every_observation_table_rejects_update_and_delete(self):
        from ..domain import records as R
        from .fixtures import TS

        proposal = make_proposal()
        forecast = make_forecast()
        self.repo.write_proposal(proposal)
        self.repo.write_forecast(forecast)
        self.repo.seal_forecast(forecast.id)

        auth = R.HostAuthorization(
            id="auth_121212121212", forecast_id=forecast.id,
            proposal_id=proposal.id, proposal_version=1,
            state="AUTOMATICALLY_ALLOWED", provenance="HOST_TOOL_FATE",
            authorized_by="SYSTEM", observed_choice="not_observed",
            observed_via="post_tool_call", reason="UNKNOWN", created_at=TS,
            escalation_expected=True,
        )
        self.repo.write_host_authorization(auth)
        decision = R.ProductDecision(
            id="pdec_101010101010", forecast_id=forecast.id,
            proposal_id=proposal.id, proposal_version=1, state="NOT_ASKED",
            decided_by="system", decided_at=TS, surface="none",
        )
        self.repo.write_product_decision(decision)
        execution = R.Execution(id="exe_555555555555", forecast_id=forecast.id,
                                 started_at=TS, status="COMPLETED", source="hook")
        self.repo.write_execution(execution)
        outcome = R.Outcome(id="out_777777777777", forecast_id=forecast.id,
                             execution_id=execution.id, recorded_at=TS,
                             recorded_by="agent", verification_method="MANUAL",
                             summary="checked", observations=[])
        self.repo.write_outcome(outcome)
        comparison = R.Comparison(
            id="cmp_999999999999", forecast_id=forecast.id, outcome_id=outcome.id,
            created_at=TS, verdict="INCONCLUSIVE",
            counts={"OBSERVED": 0, "NOT_OBSERVED": 0, "UNEXPECTED": 0,
                    "NOT_VERIFIABLE": 0, "NOT_APPLICABLE": 0},
            accuracy_note="no unexpected items were found", items=[])
        self.repo.write_comparison(comparison)

        # An UPDATE over zero rows fires no trigger, so every observation
        # table must hold a row before the immutability is asserted.
        self._write_every_observation_row(auth, decision, execution, outcome, comparison)

        # Every observation table must reject UPDATE and DELETE.
        for table in OBSERVATION_TABLES:
            if table in ("schema_meta",):
                continue
            with self.subTest(table=table):
                columns = [r[1] for r in self.conn.execute(f"PRAGMA table_info({table})")]
                key = columns[0]
                rows = self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                self.assertGreater(rows, 0, f"{table} must hold a row")
                with self.assertRaises(sqlite3.IntegrityError):
                    self.conn.execute(f"UPDATE {table} SET {key} = {key}")
                self.conn.rollback()
                with self.assertRaises(sqlite3.IntegrityError):
                    self.conn.execute(f"DELETE FROM {table}")
                self.conn.rollback()

    def _write_every_observation_row(self, auth, decision, execution, outcome, comparison):
        """Write one row into every observation table that can hold one."""
        from ..domain import records as R
        from .fixtures import TS

        self.conn.execute(
            "INSERT INTO execution_tool_call (execution_id, seq, tool_name, "
            "args_digest, result_digest, status, duration_ms) "
            "VALUES (?, 1, 'read', ?, ?, 'ok', 5)",
            (execution.id, "a" * 64, "b" * 64),
        )
        self.conn.execute(
            "INSERT INTO outcome_observation (outcome_id, id, target, observation, "
            "label, evidence_source_kind, evidence_ref, confidence) "
            "VALUES (?, 'ob_1', 't', 'o', 'NOT_VERIFIABLE', 'FILESYSTEM', 'ref', 'LOW')",
            (outcome.id,),
        )
        self.conn.execute(
            "INSERT INTO comparison_item (comparison_id, id, origin, forecast_ref, "
            "forecast_ref_kind, observed_ref, label, note) "
            "VALUES (?, 'ci_1', 'PREDICTED', 'ev_1', 'evidence', 'ob_1', "
            "'NOT_VERIFIABLE', '')",
            (comparison.id,),
        )
        self.conn.execute(
            "INSERT INTO alternative_evaluation (id, forecast_id, alternative_id, "
            "disposition, rationale, evaluated_at) "
            "VALUES ('ae_1', ?, 'alt_1', 'NOT_EVALUATED', NULL, ?)",
            (comparison.forecast_id, TS),
        )
        self.conn.commit()

    def test_AC_STORE_13_a_resolved_authorization_is_immutable(self):
        from ..domain import records as R
        from .fixtures import TS

        proposal = make_proposal()
        forecast = make_forecast()
        self.repo.write_proposal(proposal)
        self.repo.write_forecast(forecast)
        self.repo.seal_forecast(forecast.id)
        auth = R.HostAuthorization(
            id="auth_121212121212", forecast_id=forecast.id,
            proposal_id=proposal.id, proposal_version=1,
            state="PENDING", provenance="HOST_APPROVAL_HOOK", authorized_by="NONE",
            observed_choice="not_observed", observed_via="pre_approval_request",
            reason="UNKNOWN", created_at=TS, escalation_expected=True,
        )
        self.repo.write_host_authorization(auth)
        self.repo.resolve_host_authorization(auth.id)
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                "UPDATE host_authorization SET state = 'HUMAN_APPROVED' WHERE id = ?",
                (auth.id,),
            )
        self.conn.rollback()

    def test_AC_STORE_14_a_product_decision_is_append_only(self):
        from ..domain import records as R
        from .fixtures import TS

        proposal = make_proposal()
        forecast = make_forecast()
        self.repo.write_proposal(proposal)
        self.repo.write_forecast(forecast)
        self.repo.seal_forecast(forecast.id)
        decision = R.ProductDecision(
            id="pdec_101010101010", forecast_id=forecast.id,
            proposal_id=proposal.id, proposal_version=1, state="NOT_ASKED",
            decided_by="system", decided_at=TS, surface="none")
        self.repo.write_product_decision(decision)
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                "UPDATE product_decision SET state = 'ACCEPTED' WHERE id = ?",
                (decision.id,))
        self.conn.rollback()
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute("DELETE FROM product_decision WHERE id = ?", (decision.id,))
        self.conn.rollback()


if __name__ == "__main__":
    unittest.main()
