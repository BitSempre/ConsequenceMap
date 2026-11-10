"""The domain rules of specification section 2.

P-1..P-4 (proposal), F-1..F-5 (forecast), E-1..E-2 (execution),
O-1..O-2 (outcome), C-1..C-6 (comparison), PD-* and AUTH-*.
"""
from __future__ import annotations

import unittest

from ..domain import records as R
from ..domain.validation import ValidationError
from .fixtures import TS, make_forecast, make_proposal


class TestProposalRules(unittest.TestCase):
    def test_a_valid_proposal_validates(self):
        self.assertIs(make_proposal().validate().id, "prop_aaaaaaaaaaaa")

    def test_AC_DATA_05_P1_scope_excluded_must_be_present(self):
        proposal = make_proposal(scope={"included": ["a/"]})
        with self.assertRaises(ValidationError) as ctx:
            proposal.validate()
        self.assertIn("P-1", str(ctx.exception))

    def test_AC_DATA_05_P1_scope_excluded_must_be_non_empty(self):
        proposal = make_proposal(scope={"included": ["a/"], "excluded": []})
        with self.assertRaises(ValidationError) as ctx:
            proposal.validate()
        self.assertIn("P-1", str(ctx.exception))

    def test_AC_DATA_06_P2_a_filesystem_target_requires_a_non_empty_paths_list(self):
        proposal = make_proposal(target={"paths": []})
        with self.assertRaises(ValidationError) as ctx:
            proposal.validate()
        self.assertIn("P-2", str(ctx.exception))

    def test_AC_DATA_06_P2_a_filesystem_target_requires_the_paths_key(self):
        proposal = make_proposal(target={})
        with self.assertRaises(ValidationError) as ctx:
            proposal.validate()
        self.assertIn("P-2", str(ctx.exception))

    def test_AC_DATA_07_P3_a_non_filesystem_target_is_not_rejected(self):
        proposal = make_proposal(target_kind="API",
                                 target={"symbol": "foo", "service": "svc"})
        self.assertIs(proposal.validate().target_kind, "API")

    def test_AC_DATA_08_P4_an_undeterminable_target_kind_is_unknown(self):
        proposal = make_proposal(target_kind="UNKNOWN", target={"description": "?"})
        self.assertIs(proposal.validate().target_kind, "UNKNOWN")

    def test_an_unknown_target_kind_is_rejected(self):
        proposal = make_proposal(target_kind="TELEPATHY")
        with self.assertRaises(ValidationError):
            proposal.validate()

    def test_an_invalid_timestamp_is_rejected(self):
        with self.assertRaises(ValidationError):
            make_proposal(created_at="2026-11-07").validate()


class TestForecastRules(unittest.TestCase):
    def test_a_valid_forecast_validates(self):
        self.assertIs(make_forecast().validate().id, "fc_bbbbbbbbbbbb")

    def test_AC_DATA_09_an_absent_collection_is_an_error(self):
        # "Missing" means ABSENT (None), not empty. An empty collection is
        # present but carries no rows - that distinction is what keeps
        # F-3 (severity >= MODERATE needs an alternative) non-vacuous.
        for collection in ("evidence", "impact", "alternatives", "unknowns"):
            with self.subTest(collection=collection):
                forecast = make_forecast()
                setattr(forecast, collection, None)
                with self.assertRaises(ValidationError) as ctx:
                    forecast.validate()
                self.assertIn("AC-DATA-09", str(ctx.exception))

    def test_AC_DATA_09_an_empty_collection_is_present_not_missing(self):
        # F-3 supplies the conditional requirement for alternatives.
        forecast = make_forecast()
        forecast.alternatives = []
        self.assertIs(forecast.validate().id, "fc_bbbbbbbbbbbb")

    def test_AC_DATA_09_a_missing_risk_is_an_error(self):
        forecast = make_forecast(risk=None)
        with self.assertRaises(ValidationError) as ctx:
            forecast.validate()
        self.assertIn("AC-DATA-09", str(ctx.exception))

    def test_AC_DATA_11_F1_an_unknown_relation_edge_requires_unknown_evidence(self):
        forecast = make_forecast()
        forecast.impact[0].relation = "UNKNOWN_RELATION"
        with self.assertRaises(ValidationError) as ctx:
            forecast.validate()
        self.assertIn("F-1", str(ctx.exception))

    def test_AC_DATA_11_F1_with_unknown_evidence_is_accepted(self):
        forecast = make_forecast()
        forecast.impact[0].relation = "UNKNOWN_RELATION"
        forecast.evidence[0].classification = "UNKNOWN"
        forecast.confidence_overall = "LOW"
        self.assertIs(forecast.validate().id, "fc_bbbbbbbbbbbb")

    def test_AC_DATA_12_F2_an_inferred_edge_must_be_an_inference(self):
        forecast = make_forecast()
        forecast.impact[0].relation = "INFERRED"
        with self.assertRaises(ValidationError) as ctx:
            forecast.validate()
        self.assertIn("F-2", str(ctx.exception))

    def test_AC_DATA_12_F2_with_the_right_classification_is_accepted(self):
        forecast = make_forecast()
        forecast.impact[0].relation = "INFERRED"
        forecast.impact[0].classification = "INFERENCE"
        self.assertIs(forecast.validate().id, "fc_bbbbbbbbbbbb")

    def test_AC_DATA_13_F3_severity_moderate_requires_an_alternative(self):
        forecast = make_forecast()
        forecast.risk.severity = "MODERATE"
        forecast.alternatives = []
        with self.assertRaises(ValidationError) as ctx:
            forecast.validate()
        self.assertIn("F-3", str(ctx.exception))

    def test_AC_DATA_13_F3_severity_high_requires_an_alternative(self):
        forecast = make_forecast()
        forecast.risk.severity = "HIGH"
        forecast.alternatives = []
        with self.assertRaises(ValidationError) as ctx:
            forecast.validate()
        self.assertIn("F-3", str(ctx.exception))

    def test_AC_DATA_13_F3_severity_low_does_not_require_an_alternative(self):
        forecast = make_forecast()
        forecast.alternatives = []
        self.assertIs(forecast.validate().id, "fc_bbbbbbbbbbbb")

    def test_AC_DATA_14_F4_an_unobservable_edge_must_be_unknown_and_low(self):
        forecast = make_forecast()
        forecast.impact[0].observable = False
        with self.assertRaises(ValidationError) as ctx:
            forecast.validate()
        self.assertIn("F-4", str(ctx.exception))

    def test_AC_DATA_14_F4_with_low_confidence_is_accepted(self):
        forecast = make_forecast()
        forecast.impact[0].observable = False
        forecast.impact[0].classification = "UNKNOWN"
        forecast.impact[0].confidence = "LOW"
        forecast.risk.dimension_caveats = ["the dimension is unobservable"]
        self.assertIs(forecast.validate().id, "fc_bbbbbbbbbbbb")

    def test_AC_DATA_15_F5_an_unobservable_edge_requires_dimension_caveats(self):
        forecast = make_forecast()
        forecast.impact[0].observable = False
        forecast.impact[0].classification = "UNKNOWN"
        forecast.impact[0].confidence = "LOW"
        forecast.risk.dimension_caveats = []
        with self.assertRaises(ValidationError) as ctx:
            forecast.validate()
        self.assertIn("F-5", str(ctx.exception))

    def test_AC_DATA_17_overall_confidence_is_the_lowest_of_the_material_claims(self):
        forecast = make_forecast()
        forecast.evidence[0].confidence = "HIGH"
        forecast.impact[0].confidence = "MEDIUM"
        forecast.confidence_overall = "MEDIUM"
        self.assertIs(forecast.validate().id, "fc_bbbbbbbbbbbb")

    def test_AC_DATA_17_an_overstated_overall_confidence_is_rejected(self):
        forecast = make_forecast()
        forecast.evidence[0].confidence = "LOW"
        forecast.impact[0].confidence = "LOW"
        forecast.confidence_overall = "HIGH"
        with self.assertRaises(ValidationError) as ctx:
            forecast.validate()
        self.assertIn("AC-DATA-17", str(ctx.exception))

    def test_AC_DATA_10_evidence_needs_a_classification_and_source_ref(self):
        forecast = make_forecast()
        forecast.evidence[0].source_ref = ""
        with self.assertRaises(ValidationError):
            forecast.validate()


class TestExecutionRules(unittest.TestCase):
    def _execution(self, **kw):
        base = dict(id="exe_555555555555", forecast_id="fc_bbbbbbbbbbbb",
                    started_at=TS, status="COMPLETED", source="hook")
        base.update(kw)
        return R.Execution(**base)

    def test_a_valid_execution_validates(self):
        self.assertIs(self._execution().validate().id, "exe_555555555555")

    def test_AC_DATA_19_E1_an_unknown_status_is_accepted(self):
        self.assertEqual(self._execution(status="UNKNOWN_STATUS").validate().status,
                         "UNKNOWN_STATUS")

    def test_AC_DATA_19_E1_an_issued_command_is_never_completed(self):
        # The rule is expressed in the domain: an execution whose host
        # reported no result carries UNKNOWN_STATUS. The mapping helper
        # enforces it.
        from ..domain.records import execution_status_for_result
        self.assertEqual(execution_status_for_result(None), "UNKNOWN_STATUS")

    def test_AC_DATA_20_E2_a_blocked_execution_records_the_error_type(self):
        with self.assertRaises(ValidationError) as ctx:
            self._execution(status="BLOCKED").validate()
        self.assertIn("E-2", str(ctx.exception))

    def test_AC_DATA_20_E2_distinguishes_plugin_block_from_tool_error(self):
        self.assertEqual(self._execution(status="BLOCKED",
                                         error_type="plugin_block").validate().error_type,
                         "plugin_block")
        self.assertEqual(self._execution(status="BLOCKED",
                                         error_type="tool_error").validate().error_type,
                         "tool_error")

    def test_AC_DATA_20_E2_an_unknown_error_type_is_rejected(self):
        with self.assertRaises(ValidationError) as ctx:
            self._execution(status="BLOCKED", error_type="mystery").validate()
        self.assertIn("E-2", str(ctx.exception))

    def test_a_tool_call_requires_a_sha256_digest(self):
        execution = self._execution(tool_calls=[
            R.ToolCall(tool_name="read", args_digest="raw-secret-value",
                       result_digest="0" * 64, status="ok", duration_ms=1)
        ])
        with self.assertRaises(ValidationError) as ctx:
            execution.validate()
        self.assertIn("section 8.2", str(ctx.exception))


class TestOutcomeRules(unittest.TestCase):
    def _make_outcome(self, method="DETERMINISTIC_CHECK", labels=("OBSERVED",)):
        obs = [
            R.OutcomeObservation(id="ob_666666666666", target="reports/daily.md",
                                 observation="the file changed",
                                 label=label, evidence_source_kind="FILESYSTEM",
                                 evidence_ref="reports/daily.md", confidence="LOW")
            for label in labels
        ]
        return R.Outcome(id="out_777777777777", forecast_id="fc_bbbbbbbbbbbb",
                          execution_id="exe_555555555555", recorded_at=TS,
                          recorded_by="agent", verification_method=method,
                          summary="checked the file", observations=obs)

    def test_a_valid_outcome_validates(self):
        self.assertIs(self._make_outcome().validate().id, "out_777777777777")

    def test_AC_DATA_22_O2_an_observed_observation_requires_an_evidence_ref(self):
        outcome = self._make_outcome()
        outcome.observations[0].evidence_ref = ""
        with self.assertRaises(ValidationError) as ctx:
            outcome.validate()
        self.assertIn("O-2", str(ctx.exception))

    def test_AC_DATA_23_O1_unverified_forces_not_verifiable_or_not_applicable(self):
        outcome = self._make_outcome(method="UNVERIFIED", labels=("OBSERVED",))
        with self.assertRaises(ValidationError) as ctx:
            outcome.validate()
        self.assertIn("O-1", str(ctx.exception))

    def test_AC_DATA_23_O1_unverified_accepts_not_verifiable(self):
        outcome = self._make_outcome(method="UNVERIFIED", labels=("NOT_VERIFIABLE",))
        self.assertIs(outcome.validate().id, "out_777777777777")


class TestComparisonRules(unittest.TestCase):
    def _comparison(self, items=None, counts=None, note="one unexpected item"):
        items = items if items is not None else [
            R.ComparisonItem(id="ci_888888888888", origin="UNEXPECTED",
                             observed_ref="ob_1", label="UNEXPECTED", note="")
        ]
        counts = counts if counts is not None else {
            "OBSERVED": 0, "NOT_OBSERVED": 0, "UNEXPECTED": 1,
            "NOT_VERIFIABLE": 0, "NOT_APPLICABLE": 0,
        }
        return R.Comparison(id="cmp_999999999999", forecast_id="fc_bbbbbbbbbbbb",
                             outcome_id="out_777777777777", created_at=TS,
                             verdict="DIVERGED", counts=counts,
                             accuracy_note=note, items=items)

    def test_a_valid_comparison_validates(self):
        self.assertIs(self._comparison().validate().id, "cmp_999999999999")

    def test_AC_DATA_25_C2_counts_must_equal_the_item_counts(self):
        comparison = self._comparison(counts={
            "OBSERVED": 3, "NOT_OBSERVED": 0, "UNEXPECTED": 1,
            "NOT_VERIFIABLE": 0, "NOT_APPLICABLE": 0})
        with self.assertRaises(ValidationError) as ctx:
            comparison.validate()
        self.assertIn("C-2", str(ctx.exception))

    def test_AC_DATA_25_C2_the_sum_of_counts_must_equal_the_item_count(self):
        comparison = self._comparison(counts={
            "OBSERVED": 1, "NOT_OBSERVED": 0, "UNEXPECTED": 1,
            "NOT_VERIFIABLE": 0, "NOT_APPLICABLE": 0})
        with self.assertRaises(ValidationError) as ctx:
            comparison.validate()
        self.assertIn("C-2", str(ctx.exception))

    def test_AC_DATA_26_C3_an_unexpected_item_has_a_null_forecast_ref(self):
        item = R.ComparisonItem(id="ci_1", origin="UNEXPECTED",
                                forecast_ref="ev_1", observed_ref="ob_1",
                                label="UNEXPECTED", note="")
        with self.assertRaises(ValidationError) as ctx:
            item.validate()
        self.assertIn("C-3", str(ctx.exception))

    def test_AC_DATA_26_C3_an_unexpected_item_needs_a_non_null_observed_ref(self):
        item = R.ComparisonItem(id="ci_1", origin="UNEXPECTED",
                                observed_ref=None, label="UNEXPECTED", note="")
        with self.assertRaises(ValidationError) as ctx:
            item.validate()
        self.assertIn("C-3", str(ctx.exception))

    def test_AC_DATA_27_C4_forecast_ref_kind_alternative_is_rejected(self):
        item = R.ComparisonItem(id="ci_1", origin="PREDICTED",
                                forecast_ref="alt_1", forecast_ref_kind="alternative",
                                label="OBSERVED", note="")
        with self.assertRaises(ValidationError) as ctx:
            item.validate()
        self.assertIn("C-4", str(ctx.exception))

    def test_AC_DATA_28_C5_no_unexpected_item_requires_the_note_to_say_so(self):
        items = [R.ComparisonItem(id="ci_1", origin="PREDICTED",
                                  forecast_ref="ev_1", forecast_ref_kind="evidence",
                                  label="OBSERVED", note="")]
        counts = {"OBSERVED": 1, "NOT_OBSERVED": 0, "UNEXPECTED": 0,
                  "NOT_VERIFIABLE": 0, "NOT_APPLICABLE": 0}
        with self.assertRaises(ValidationError) as ctx:
            self._comparison(items=items, counts=counts,
                             note="everything matched").validate()
        self.assertIn("C-5", str(ctx.exception))

    def test_AC_DATA_28_C5_is_accepted_with_the_note(self):
        items = [R.ComparisonItem(id="ci_1", origin="PREDICTED",
                                  forecast_ref="ev_1", forecast_ref_kind="evidence",
                                  label="OBSERVED", note="")]
        counts = {"OBSERVED": 1, "NOT_OBSERVED": 0, "UNEXPECTED": 0,
                  "NOT_VERIFIABLE": 0, "NOT_APPLICABLE": 0}
        comparison = self._comparison(items=items, counts=counts,
                                      note="no unexpected items were found")
        self.assertIs(comparison.validate().id, "cmp_999999999999")


class TestProductDecisionRules(unittest.TestCase):
    def _decision(self, **kw):
        base = dict(id="pdec_101010101010", forecast_id="fc_bbbbbbbbbbbb",
                    proposal_id="prop_aaaaaaaaaaaa", proposal_version=1,
                    state="ACCEPTED", decided_by="user", decided_at=TS,
                    surface="desktop")
        base.update(kw)
        return R.ProductDecision(**base)

    def test_a_valid_decision_validates(self):
        self.assertIs(self._decision().validate().id, "pdec_101010101010")

    def test_PD5_accepted_requires_decided_by_user(self):
        with self.assertRaises(ValidationError) as ctx:
            self._decision(decided_by="system").validate()
        self.assertIn("PD-5", str(ctx.exception))

    def test_PD4_the_plugin_cannot_accept_on_the_users_behalf(self):
        with self.assertRaises(ValidationError) as ctx:
            self._decision(state="REJECTED", decided_by="system").validate()
        self.assertIn("PD-4", str(ctx.exception))

    def test_PD3_not_asked_is_the_default_and_needs_no_human(self):
        self.assertIs(self._decision(state="NOT_ASKED", decided_by="system").validate().state,
                      "NOT_ASKED")


class TestHostAuthorizationRules(unittest.TestCase):
    def _auth(self, **kw):
        base = dict(id="auth_121212121212", forecast_id="fc_bbbbbbbbbbbb",
                    proposal_id="prop_aaaaaaaaaaaa", proposal_version=1,
                    state="HUMAN_APPROVED", provenance="HOST_APPROVAL_HOOK",
                    authorized_by="USER", observed_choice="once",
                    observed_via="post_approval_response", reason="UNKNOWN",
                    created_at=TS, escalation_expected=True,
                    pattern_key="plugin_rule:cm:fc_bbbbbbbbbbbb:rule")
        base.update(kw)
        return R.HostAuthorization(**base)

    def test_a_valid_authorization_validates(self):
        self.assertIs(self._auth().validate().id, "auth_121212121212")

    def test_AUTH1_human_approved_requires_escalation_expected(self):
        with self.assertRaises(ValidationError) as ctx:
            self._auth(escalation_expected=False).validate()
        self.assertIn("AUTH-1", str(ctx.exception))

    def test_AUTH1_human_approved_requires_an_observed_choice(self):
        with self.assertRaises(ValidationError) as ctx:
            self._auth(observed_choice="deny").validate()
        self.assertIn("AUTH-1", str(ctx.exception))

    def test_AUTH1d_human_approved_requires_a_matching_channel(self):
        with self.assertRaises(ValidationError) as ctx:
            self._auth(pattern_key=None, tool_call_id=None).validate()
        self.assertIn("AUTH-1d", str(ctx.exception))

    def test_AUTH1d_a_non_matching_pattern_key_is_absent(self):
        with self.assertRaises(ValidationError) as ctx:
            self._auth(pattern_key="plugin_rule:cm:fc_other:rule").validate()
        self.assertIn("AUTH-1d", str(ctx.exception))

    def test_AUTH1b_an_empty_tool_call_id_is_absent_not_a_match(self):
        with self.assertRaises(ValidationError) as ctx:
            self._auth(pattern_key=None, tool_call_id="").validate()
        self.assertIn("AUTH-1d", str(ctx.exception))

    def test_AUTH1a_the_tool_call_channel_alone_is_sufficient(self):
        record = self._auth(pattern_key=None, tool_call_id="tc_1")
        self.assertIs(record.validate().id, "auth_121212121212")

    def test_AUTH2_human_rejected_requires_deny(self):
        with self.assertRaises(ValidationError) as ctx:
            self._auth(state="HUMAN_REJECTED", observed_choice="once").validate()
        self.assertIn("AUTH-2", str(ctx.exception))

    def test_AUTH4_cancelled_requires_the_cancelled_choice(self):
        with self.assertRaises(ValidationError) as ctx:
            self._auth(state="APPROVAL_CANCELLED", observed_choice="timeout").validate()
        self.assertIn("AUTH-4", str(ctx.exception))

    def test_AUTH5b_automatically_allowed_excludes_the_guardian(self):
        with self.assertRaises(ValidationError) as ctx:
            self._auth(state="AUTOMATICALLY_ALLOWED", authorized_by="GUARDIAN_LLM",
                       observed_choice="").validate()
        self.assertIn("AUTH-5b", str(ctx.exception))

    def test_AUTH11_a_guardian_state_requires_the_guardian_as_authorized_by(self):
        with self.assertRaises(ValidationError) as ctx:
            self._auth(state="GUARDIAN_APPROVED", observed_choice="smart_approve",
                       authorized_by="USER").validate()
        self.assertIn("AUTH-11", str(ctx.exception))

    def test_AUTH7_approval_not_required_requires_no_escalation(self):
        with self.assertRaises(ValidationError) as ctx:
            self._auth(state="APPROVAL_NOT_REQUIRED", escalation_expected=True).validate()
        self.assertIn("AUTH-7", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
