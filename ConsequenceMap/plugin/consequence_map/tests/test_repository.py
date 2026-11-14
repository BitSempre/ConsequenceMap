"""The repository: one write path per table, read paths, and privacy.

AC-DATA-16, AC-DATA-21, AC-DATA-24, AC-STORE-09, AC-STORE-10, AC-STORE-11,
AC-STORE-15, AC-SEPR-11, AC-SEPR-12, AC-PATH-20, AC-PATH-22.
"""
from __future__ import annotations

import json
import unittest

from ..domain import records as R
from ..storage.repository import Repository, digest
from .fixtures import (
    TS,
    DatabaseTestCase,
    make_forecast,
    make_proposal,
    write_sealed_forecast,
)


class TestWritePaths(DatabaseTestCase):
    def test_AC_SEPR_11_a_supersedes_chain_appends_and_preserves_the_prior_row(self):
        proposal = make_proposal()
        forecast = write_sealed_forecast(self, proposal)
        first = R.ProductDecision(
            id="pdec_111111111111", forecast_id=forecast.id,
            proposal_id=proposal.id, proposal_version=1, state="NOT_ASKED",
            decided_by="system", decided_at=TS, surface="none")
        self.repo.write_product_decision(first)
        second = R.ProductDecision(
            id="pdec_222222222222", forecast_id=forecast.id,
            proposal_id=proposal.id, proposal_version=1, state="ACCEPTED",
            decided_by="user", decided_at=TS, surface="desktop",
            supersedes=first.id)
        self.repo.write_product_decision(second)
        rows = self.rows("product_decision")
        self.assertEqual(len(rows), 2)
        # The prior row is intact.
        prior = [r for r in rows if r[0] == first.id][0]
        self.assertEqual(prior[4], "NOT_ASKED")
        # The new row links to it.
        newer = [r for r in rows if r[0] == second.id][0]
        self.assertEqual(newer[9], first.id)

    def test_AC_SEPR_12_a_rejected_decision_needs_no_authorization_row(self):
        proposal = make_proposal()
        forecast = write_sealed_forecast(self, proposal)
        decision = R.ProductDecision(
            id="pdec_333333333333", forecast_id=forecast.id,
            proposal_id=proposal.id, proposal_version=1, state="REJECTED",
            decided_by="user", decided_at=TS, surface="desktop")
        self.repo.write_product_decision(decision)
        self.assertEqual(self.count("host_authorization"), 0)
        self.assertEqual(self.count("product_decision"), 1)
        # It is displayable: a read returns it.
        rows = self.rows("product_decision")
        self.assertEqual(rows[0][4], "REJECTED")

    def test_AC_DATA_21_tool_arguments_are_stored_only_as_digests(self):
        proposal = make_proposal()
        forecast = write_sealed_forecast(self, proposal)
        execution = R.Execution(
            id="exe_555555555555", forecast_id=forecast.id, started_at=TS,
            status="COMPLETED", source="hook",
            tool_calls=[R.ToolCall(tool_name="read", args_digest=digest("SECRET-ARGS"),
                                    result_digest=digest("SECRET-RESULT"),
                                    status="ok", duration_ms=3)])
        self.repo.write_execution(execution)
        blob = " ".join(str(v) for v in self.rows("execution_tool_call")[0])
        self.assertNotIn("SECRET-ARGS", blob)
        self.assertNotIn("SECRET-RESULT", blob)
        self.assertEqual(len(self.rows("execution_tool_call")[0][3]), 64)

    def test_AC_STORE_11_there_is_no_write_path_from_the_outcome_side_to_a_forecast(self):
        import inspect
        from ..storage import repository as repo_module

        source = inspect.getsource(repo_module)
        # Every write method names its table explicitly; none of the
        # outcome-side tables can reach a forecast table.
        for table in ("outcome", "outcome_observation", "comparison",
                      "comparison_item", "host_authorization", "product_decision"):
            for line in source.split(chr(10)):
                if f'"{table}"' in line and "INSERT INTO" in line:
                    self.assertNotIn("forecast", line)

    def test_AC_STORE_15_exactly_one_write_method_per_table(self):
        import inspect
        from ..storage import repository as repo_module

        methods = [name for name, _ in inspect.getmembers(repo_module.Repository,
                                                          inspect.isfunction)
                   if name.startswith("write_")]
        self.assertEqual(sorted(methods), [
            "write_alternative_evaluation", "write_comparison", "write_execution",
            "write_forecast", "write_host_authorization", "write_outcome",
            "write_product_decision", "write_proposal",
        ])

    def test_AC_PATH_20_the_authorized_root_is_never_persisted_verbatim(self):
        proposal = make_proposal()
        forecast = make_forecast(generator={
            "provider": "local", "model": "none", "purpose": "test",
            "scanner_version": "1", "deterministic": True,
            "root": "C:\\Users\\Someone\\PrivateFolder"})
        self.repo.write_proposal(proposal)
        self.repo.write_forecast(forecast)
        blob = " ".join(str(v) for v in self.rows("forecast")[0])
        self.assertNotIn("PrivateFolder", blob)
        self.assertNotIn("C:\\Users", blob)
        stored = json.loads(self.rows("forecast")[0][4])
        self.assertIn("root_digest", stored)
        self.assertNotIn("root", stored)
        self.assertEqual(len(stored["root_digest"]), 16)

    def test_AC_PATH_22_the_digest_is_stable_across_writes(self):
        proposal = make_proposal()
        forecast = make_forecast(generator={
            "provider": "local", "model": "none", "purpose": "test",
            "scanner_version": "1", "deterministic": True, "root": "C:\\root"})
        self.repo.write_proposal(proposal)
        self.repo.write_forecast(forecast)
        first = json.loads(self.rows("forecast")[0][4])["root_digest"]
        other = make_forecast(id="fc_cccccccccccc", generator={
            "provider": "local", "model": "none", "purpose": "test",
            "scanner_version": "1", "deterministic": True, "root": "C:\\root"})
        self.repo.write_forecast(other)
        second = json.loads([r for r in self.rows("forecast") if r[0] == other.id][0][4])["root_digest"]
        self.assertEqual(first, second)


class TestReadPaths(DatabaseTestCase):
    def test_AC_STORE_10_an_unsealed_forecast_is_invisible_to_every_read_path(self):
        proposal = make_proposal()
        forecast = make_forecast()
        self.repo.write_proposal(proposal)
        self.repo.write_forecast(forecast)
        self.assertEqual(self.repo.read_sealed_forecasts(), [])
        self.assertIsNone(self.repo.read_forecast(forecast.id))

    def test_AC_DATA_16_a_forecast_returned_by_a_read_path_is_sealed(self):
        write_sealed_forecast(self)
        rows = self.repo.read_sealed_forecasts()
        self.assertEqual(len(rows), 1)
        self.assertIsNotNone(rows[0][8])  # sealed_at

    def test_AC_STORE_09_the_content_hash_is_computed_before_the_header_insert(self):
        """The seal trigger permits no other column change, so the hash
        must already be correct when the header is written."""
        import sqlite3

        proposal = make_proposal()
        forecast = make_forecast(content_hash="a" * 64)
        self.repo.write_proposal(proposal)
        self.repo.write_forecast(forecast)
        stored = self.rows("forecast")[0]
        self.assertEqual(stored[7], "a" * 64)
        # The seal succeeds, which proves the hash column was already right.
        self.repo.seal_forecast(forecast.id)
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute("UPDATE forecast SET content_hash = ? WHERE id = ?",
                              ("b" * 64, forecast.id))
        self.conn.rollback()

    def test_AC_DATA_24_a_comparison_references_the_forecast_that_existed(self):
        proposal = make_proposal()
        forecast = write_sealed_forecast(self, proposal)
        execution = R.Execution(id="exe_1", forecast_id=forecast.id,
                                 started_at=TS, status="COMPLETED", source="hook")
        self.repo.write_execution(execution)
        outcome = R.Outcome(id="out_1", forecast_id=forecast.id,
                            execution_id=execution.id, recorded_at=TS,
                            recorded_by="agent", verification_method="MANUAL",
                            summary="checked", observations=[])
        self.repo.write_outcome(outcome)
        comparison = R.Comparison(
            id="cmp_1", forecast_id=forecast.id, outcome_id=outcome.id,
            created_at=TS, verdict="ALIGNED",
            counts={"OBSERVED": 0, "NOT_OBSERVED": 0, "UNEXPECTED": 0,
                    "NOT_VERIFIABLE": 1, "NOT_APPLICABLE": 0},
            accuracy_note="no unexpected items were found",
            items=[R.ComparisonItem(id="ci_1", origin="PREDICTED",
                                    forecast_ref="ev_111111111111",
                                    forecast_ref_kind="evidence",
                                    label="NOT_VERIFIABLE", note="")])
        self.repo.write_comparison(comparison)
        stored = self.rows("comparison")[0]
        self.assertEqual(stored[1], forecast.id)
        # The forecast was NOT rewritten to match the observation.
        self.assertEqual(self.rows("forecast")[0][7], forecast.content_hash)
        self.assertEqual(self.count("forecast"), 1)


if __name__ == "__main__":
    unittest.main()
