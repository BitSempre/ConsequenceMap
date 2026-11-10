"""Integration tests for the lifecycle.

The lifecycle is the link the domain model and the storage layer did
not have: the code that walks one operation from the proposal, through
the forecast, the decision, the execution and the outcome, and keeps
the four parts tied to each other.

These tests exercise the **whole chain** against a real database -
the same SQLite schema, the same triggers, the same immutability
rules. They are the evidence that the product's signature experience
(the forecast beside the outcome) is executable, not merely modelled.

They also pin the three properties that matter:

1. the forecast is immutable once sealed;
2. the product decision and the host authorization are separate
   records, never merged;
3. an outcome that cannot be verified stays UNVERIFIED and yields an
   INCONCLUSIVE verdict.
"""
from __future__ import annotations

import unittest

from ..domain import records as R
from ..lifecycle import Lifecycle, LifecycleError, derive_verdict
from .fixtures import TS, DatabaseTestCase, make_forecast, make_proposal


class LifecycleTestCase(DatabaseTestCase):
    def setUp(self):
        super().setUp()
        self.lifecycle = Lifecycle(self.repo)
        self.proposal = make_proposal()
        self.repo.write_proposal(self.proposal)
        self.forecast = make_forecast()
        self.forecast.summary = "the file will be rewritten; confidence is low"

    def _execution(self, forecast_id=None):
        return R.Execution(
            id="exe_555555555555",
            forecast_id=forecast_id or self.forecast.id,
            started_at=TS,
            status="COMPLETED",
            source="hook",
            ended_at=TS,
        )


class TheWholeChainTests(LifecycleTestCase):
    def test_the_chain_runs_from_forecast_to_comparison(self):
        """Forecast -> decision -> execution -> outcome -> comparison."""
        self.lifecycle.record_forecast(self.forecast)
        self.lifecycle.seal_forecast(self.forecast.id)

        decision = R.ProductDecision(
            id="pdec_666666666666", forecast_id=self.forecast.id,
            proposal_id=self.proposal.id, proposal_version=1,
            state="ACCEPTED", decided_by="user", decided_at=TS,
            surface="desktop")
        self.lifecycle.record_decision(decision)

        authorization = R.HostAuthorization(
            id="auth_777777777777", forecast_id=self.forecast.id,
            proposal_id=self.proposal.id, proposal_version=1,
            state="PENDING", provenance="HOST_APPROVAL_HOOK",
            authorized_by="NONE", observed_choice="", observed_via="hook",
            reason="UNKNOWN", created_at=TS, escalation_expected=True,
            tool_call_id="tc_1", rule_key="cm:%s:E-HIGH" % self.forecast.id,
            pattern_key="plugin_rule:cm:%s:E-HIGH" % self.forecast.id)
        self.lifecycle.record_authorization(authorization)

        execution = self._execution()
        self.lifecycle.record_execution(execution)

        outcome = R.Outcome(
            id="out_888888888888", forecast_id=self.forecast.id,
            execution_id=execution.id, recorded_at=TS, recorded_by="plugin",
            verification_method="FILE_DIFF",
            summary="the file was rewritten as forecast",
            observations=[
                R.OutcomeObservation(
                    id="ob_999999999999", target="reports/daily.md",
                    observation="the file was rewritten",
                    label="OBSERVED", evidence_source_kind="FILESYSTEM",
                    evidence_ref="digest:abc", confidence="HIGH"),
            ])
        self.lifecycle.record_outcome(outcome)

        comparison = self.lifecycle.compare(
            forecast=self.forecast, outcome=outcome,
            comparison_id="cmp_121212121212", created_at=TS)

        self.assertEqual(comparison.verdict, "ALIGNED")
        self.assertEqual(self.count("forecast"), 1)
        self.assertEqual(self.count("product_decision"), 1)
        self.assertEqual(self.count("host_authorization"), 1)
        self.assertEqual(self.count("execution"), 1)
        self.assertEqual(self.count("outcome"), 1)
        self.assertEqual(self.count("comparison"), 1)

    def test_the_forecast_is_immutable_after_it_is_sealed(self):
        """A sealed forecast cannot change, even through the lifecycle."""
        self.lifecycle.record_forecast(self.forecast)
        self.lifecycle.seal_forecast(self.forecast.id)
        before = self.rows("forecast")[0]
        with self.assertRaises(Exception):
            self.lifecycle.record_forecast(self.forecast)
        after = self.rows("forecast")[0]
        self.assertEqual(before, after)

    def test_the_decision_and_the_authorization_are_separate_records(self):
        """They are correlated for display and never merged."""
        self.lifecycle.record_forecast(self.forecast)
        self.lifecycle.seal_forecast(self.forecast.id)
        self.lifecycle.record_decision(R.ProductDecision(
            id="pdec_131313131313", forecast_id=self.forecast.id,
            proposal_id=self.proposal.id, proposal_version=1,
            state="ACCEPTED", decided_by="user", decided_at=TS,
            surface="desktop"))
        self.lifecycle.record_authorization(R.HostAuthorization(
            id="auth_141414141414", forecast_id=self.forecast.id,
            proposal_id=self.proposal.id, proposal_version=1,
            state="HUMAN_APPROVED", provenance="HOST_APPROVAL_HOOK",
            authorized_by="USER", observed_choice="once", observed_via="hook",
            reason="SINGLE_QUERY_APPROVE", created_at=TS,
            escalation_expected=True, tool_call_id="tc_1"))
        self.assertEqual(self.count("product_decision"), 1)
        self.assertEqual(self.count("host_authorization"), 1)
        # Neither table holds a row of the other's kind: the product
        # decision has no authorization state, and the authorization has
        # no product state.
        decision = self.rows("product_decision")[0]
        authorization = self.rows("host_authorization")[0]
        self.assertIn(self.forecast.id, (tuple(decision) + tuple(authorization)))
        self.assertNotIn("HUMAN_APPROVED", tuple(decision))
        self.assertNotIn("ACCEPTED", tuple(authorization))

    def test_an_unverified_outcome_yields_an_inconclusive_verdict(self):
        """Nobody can vouch for it, so the forecast is neither
        confirmed nor refuted."""
        self.lifecycle.record_forecast(self.forecast)
        self.lifecycle.seal_forecast(self.forecast.id)
        outcome = R.Outcome(
            id="out_151515151515", forecast_id=self.forecast.id,
            execution_id="exe_555555555555", recorded_at=TS,
            recorded_by="plugin", verification_method="UNVERIFIED",
            summary="the outcome could not be verified",
            observations=[
                R.OutcomeObservation(
                    id="ob_161616161616", target="reports/daily.md",
                    observation="unknown", label="NOT_VERIFIABLE",
                    evidence_source_kind="FILESYSTEM", evidence_ref="",
                    confidence="LOW"),
            ])
        self.lifecycle.record_outcome(outcome)
        comparison = self.lifecycle.compare(
            forecast=self.forecast, outcome=outcome,
            comparison_id="cmp_171717171717", created_at=TS)
        self.assertEqual(comparison.verdict, "INCONCLUSIVE")
        self.assertIn("inconclusive", comparison.accuracy_note)

    def test_a_diverged_outcome_says_so(self):
        self.lifecycle.record_forecast(self.forecast)
        self.lifecycle.seal_forecast(self.forecast.id)
        outcome = R.Outcome(
            id="out_181818181818", forecast_id=self.forecast.id,
            execution_id="exe_555555555555", recorded_at=TS,
            recorded_by="plugin", verification_method="FILE_DIFF",
            summary="something else happened",
            observations=[
                R.OutcomeObservation(
                    id="ob_191919191919", target="reports/daily.md",
                    observation="the file was deleted", label="UNEXPECTED",
                    evidence_source_kind="FILESYSTEM", evidence_ref="digest:x",
                    confidence="HIGH"),
            ])
        verdict, counts = derive_verdict(outcome)
        self.assertEqual(verdict, "DIVERGED")
        self.assertEqual(counts["UNEXPECTED"], 1)


class CopyLintTests(LifecycleTestCase):
    def test_a_summary_with_guarantee_language_is_refused(self):
        """AC-DATA-18: a prediction is never presented as a guarantee."""
        self.forecast.summary = "this will guarantee the file is written"
        with self.assertRaises(LifecycleError):
            self.lifecycle.record_forecast(self.forecast)
        self.assertEqual(self.count("forecast"), 0)

    def test_a_honest_summary_is_accepted(self):
        self.lifecycle.record_forecast(self.forecast)
        self.assertEqual(self.count("forecast"), 1)


if __name__ == "__main__":
    unittest.main()
