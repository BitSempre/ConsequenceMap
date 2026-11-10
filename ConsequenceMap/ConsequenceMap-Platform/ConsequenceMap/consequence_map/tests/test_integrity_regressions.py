"""Referential integrity across the decision chain.

An independent security review found that the five tables that carry
the decision, the execution and the outcome have **no foreign keys**.
A row may name a forecast that does not exist, an execution that does
not exist, an outcome that does not exist.

That is the chain the product is built on. A forecast is sealed; a
decision is made about it; an authorisation is recorded for it; the
execution runs against it; the outcome is observed for it; and the
comparison puts the two side by side. If any of those references may
dangle, the chain can be broken in the middle and the product will
report a comparison between things that were never related.

The forecast table has had a composite foreign key to the proposal
since Phase 2A. The other five tables have none.

These tests are the proof that the gap is real and that the fix
closes it.
"""
from __future__ import annotations

import unittest

from ..domain import records as R
from .fixtures import TS, DatabaseTestCase, make_forecast, make_proposal


class OrphanReferenceTests(DatabaseTestCase):
    """A reference to something that does not exist must be refused."""

    def test_an_authorization_for_a_forecast_that_does_not_exist_is_refused(self):
        """A host_authorization must name a forecast that exists.

        Without the foreign key, an authorization can be recorded for
        a forecast nobody ever made. It would then be attributed to
        that forecast by the display correlation, and the product
        would show an approval for a proposal that does not exist.
        """
        with self.assertRaises(Exception):
            self.repo.write_host_authorization(R.HostAuthorization(
                id="auth_orphan_000001", forecast_id="fc_does_not_exist",
                proposal_id="prop_does_not_exist", proposal_version=1,
                state="HUMAN_APPROVED", provenance="HOST_APPROVAL_HOOK",
                authorized_by="USER", observed_choice="once",
                observed_via="hook", reason="SINGLE_QUERY_APPROVE",
                created_at=TS, escalation_expected=True, tool_call_id="tc_1"))

    def test_a_decision_for_a_forecast_that_does_not_exist_is_refused(self):
        with self.assertRaises(Exception):
            self.repo.write_product_decision(R.ProductDecision(
                id="pdec_orphan_00001", forecast_id="fc_does_not_exist",
                proposal_id="prop_does_not_exist", proposal_version=1,
                state="ACCEPTED", decided_by="user", decided_at=TS,
                surface="desktop"))

    def test_an_execution_for_a_forecast_that_does_not_exist_is_refused(self):
        with self.assertRaises(Exception):
            self.repo.write_execution(R.Execution(
                id="exe_orphan_000001", forecast_id="fc_does_not_exist",
                started_at=TS, status="COMPLETED", source="hook"))

    def test_an_outcome_for_an_execution_that_does_not_exist_is_refused(self):
        with self.assertRaises(Exception):
            self.repo.write_outcome(R.Outcome(
                id="out_orphan_000001", forecast_id="fc_does_not_exist",
                execution_id="exe_does_not_exist", recorded_at=TS,
                recorded_by="plugin", verification_method="UNVERIFIED",
                summary="the outcome cannot be verified"))

    def test_a_comparison_for_an_outcome_that_does_not_exist_is_refused(self):
        with self.assertRaises(Exception):
            self.repo.write_comparison(R.Comparison(
                id="cmp_orphan_000001", forecast_id="fc_does_not_exist",
                outcome_id="out_does_not_exist", created_at=TS,
                verdict="ALIGNED", counts={}, accuracy_note="no unexpected"))


class TheChainHoldsTests(DatabaseTestCase):
    """The normal chain still works, with the keys in place."""

    def setUp(self):
        super().setUp()
        self.proposal = make_proposal()
        self.repo.write_proposal(self.proposal)
        self.forecast = make_forecast()
        self.repo.write_forecast(self.forecast)
        self.repo.seal_forecast(self.forecast.id)

    def test_the_whole_chain_is_accepted(self):
        """The fix must not break the normal path."""
        decision = R.ProductDecision(
            id="pdec_chain_00001", forecast_id=self.forecast.id,
            proposal_id=self.proposal.id, proposal_version=1,
            state="ACCEPTED", decided_by="user", decided_at=TS,
            surface="desktop")
        self.repo.write_product_decision(decision)

        authorization = R.HostAuthorization(
            id="auth_chain_000001", forecast_id=self.forecast.id,
            proposal_id=self.proposal.id, proposal_version=1,
            state="HUMAN_APPROVED", provenance="HOST_APPROVAL_HOOK",
            authorized_by="USER", observed_choice="once",
            observed_via="hook", reason="SINGLE_QUERY_APPROVE",
            created_at=TS, escalation_expected=True, tool_call_id="tc_1",
            rule_key="cm:%s:E-HIGH" % self.forecast.id,
            pattern_key="plugin_rule:cm:%s:E-HIGH" % self.forecast.id)
        self.repo.write_host_authorization(authorization)

        execution = R.Execution(
            id="exe_chain_0000001", forecast_id=self.forecast.id,
            started_at=TS, status="COMPLETED", source="hook",
            host_authorization_id=authorization.id,
            product_decision_id=decision.id)
        self.repo.write_execution(execution)

        outcome = R.Outcome(
            id="out_chain_0000001", forecast_id=self.forecast.id,
            execution_id=execution.id, recorded_at=TS, recorded_by="plugin",
            verification_method="FILE_DIFF", summary="it happened")
        self.repo.write_outcome(outcome)

        comparison = R.Comparison(
            id="cmp_chain_0000001", forecast_id=self.forecast.id,
            outcome_id=outcome.id, created_at=TS, verdict="ALIGNED",
            counts={}, accuracy_note="no unexpected outcome was found")
        self.repo.write_comparison(comparison)

        self.assertEqual(self.count("host_authorization"), 1)
        self.assertEqual(self.count("product_decision"), 1)
        self.assertEqual(self.count("execution"), 1)
        self.assertEqual(self.count("outcome"), 1)
        self.assertEqual(self.count("comparison"), 1)


if __name__ == "__main__":
    unittest.main()
