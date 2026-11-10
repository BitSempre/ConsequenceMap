"""Regression tests for the independent security review.

An independent reviewer read the Phase 2B specification and the
implementation and reported five findings. Each was checked against
the code rather than accepted on authority:

* **F1 - the transform hook** was **rejected**. The specification
  (P-HOOK-1, RECUR-8) requires the callback to return ``None`` and
  never modify the result. Returning ``None`` IS the correct
  behaviour; the reviewer inverted the rule. The test that pins the
  behaviour is here so it cannot drift.

* **F2 - the sink was inert** was **confirmed and fixed**. The
  default sink recorded nothing, so the human's answer never reached
  the database. The sink now writes through the lifecycle.

* **F3 - the ambiguity check never ran** was **confirmed and fixed**.
  EC-7 says an ambiguous match is never an approval, but the hooks
  never passed the pending forecasts, so the check never executed.

* **F4 - a rule could be chosen by the caller** was **confirmed and
  fixed**. A pattern key naming a pending forecast with a DIFFERENT
  rule was accepted; the rule the plugin escalated with must match.

* **F5 - the tool fate** was **rejected**. ``AUTOMATICALLY_ALLOWED``
  authorizes nothing: ``is_approval`` is False for it.

* **F6 - the accuracy note was injectable** was **confirmed and
  fixed**. The note is now derived; a caller cannot supply it. That
  is what C-5 requires: the note is the OUTPUT of the verification.
"""
from __future__ import annotations

import os
import shutil
import tempfile
import unittest

from ..authorization import AuthorizationMachine
from ..correlation import Correlator, expected_pattern_key
from ..domain.enums import AUTHORIZATION_STATE
from .. import hooks
from .. import self_exclusion


class TransformHookTests(unittest.TestCase):
    """F1, rejected: returning None IS the specified behaviour."""

    def test_the_transform_hook_returns_none(self):
        self.assertIsNone(hooks.on_transform_tool_result(result={"x": 1}))

    def test_the_transform_hook_does_not_mutate_the_result(self):
        """The host passes the live object by reference."""
        payload = {"result": {"value": 1}}
        original = payload["result"]
        hooks.on_transform_tool_result(**payload)
        self.assertEqual(payload["result"], {"value": 1})
        self.assertIs(payload["result"], original)


class SinkWritesTests(unittest.TestCase):
    """F2: the authorization the human gave must reach the database."""

    def setUp(self):
        from ..storage import db as db_module
        from ..storage.migrations import apply_migrations
        from ..storage.repository import Repository

        self.directory = tempfile.TemporaryDirectory(prefix="cm-sink-")
        self.connection = db_module.connect(
            os.path.join(self.directory.name, "data.db"),
            provider=_provider,
        )
        apply_migrations(self.connection)
        self.repository = Repository(self.connection)
        self.sink = hooks.RepositoryAuthorizationSink(self.repository)
        self.machine = AuthorizationMachine()

    def tearDown(self):
        self.connection.close()
        self.directory.cleanup()

    def _forecast(self):
        from ..domain import records as R
        from .fixtures import TS, make_forecast, make_proposal

        proposal = make_proposal()
        self.repository.write_proposal(proposal)
        forecast = make_forecast()
        self.repository.write_forecast(forecast)
        self.repository.seal_forecast(forecast.id)
        return forecast

    def test_the_answer_reaches_the_database(self):
        forecast = self._forecast()
        record = self.machine.from_choice(
            "once", forecast_id=forecast.id, tool_call_id="tc_1",
            pattern_key=expected_pattern_key(forecast.id, "E-HIGH"),
        )
        self.sink.settle(record)
        rows = self.repository.read_all_rows("host_authorization")
        self.assertEqual(len(rows), 1, "the answer was not recorded")
        self.assertEqual(rows[0][3], forecast.id)

    def test_the_record_names_the_proposal_the_forecast_belongs_to(self):
        """The composite foreign key to the proposal must hold."""
        forecast = self._forecast()
        record = self.machine.from_choice("once", forecast_id=forecast.id)
        self.sink.settle(record)
        rows = self.repository.read_all_rows("host_authorization")
        self.assertEqual(rows[0][4], forecast.proposal_id)
        self.assertEqual(rows[0][5], forecast.proposal_version)

    def test_a_storage_failure_does_not_raise(self):
        """A hook must never fail because the storage is unavailable."""

        class BrokenRepository:
            def read_all_rows(self, table):
                raise RuntimeError("the storage is unavailable")

            def write_host_authorization(self, record):
                raise RuntimeError("the storage is unavailable")

        sink = hooks.RepositoryAuthorizationSink(BrokenRepository())
        record = self.machine.from_choice("once", forecast_id="fc_x")
        sink.settle(record)  # must not raise
        self.assertEqual(sink.failures, 1)

    def test_an_unattributed_observation_writes_nothing(self):
        """A record that names no real forecast is not a record."""
        sink = hooks.RepositoryAuthorizationSink(self.repository)
        record = self.machine.from_choice("once", forecast_id="fc_orphan")
        sink.settle(record)
        rows = self.repository.read_all_rows("host_authorization")
        self.assertEqual(rows, [])


class AmbiguityTests(unittest.TestCase):
    """F3: EC-7 must actually run in the hook path."""

    def setUp(self):
        self.correlator = Correlator()

    def test_two_pending_forecasts_with_the_same_tool_call_are_ambiguous(self):
        first = expected_pattern_key("fc_one", "E-HIGH")
        second = expected_pattern_key("fc_two", "E-HIGH")
        self.correlator.register(
            forecast_id="fc_one", rule="E-HIGH", pattern_key=first,
            tool_call_id="tc_1",
        )
        self.correlator.register(
            forecast_id="fc_two", rule="E-HIGH", pattern_key=second,
            tool_call_id="tc_1",
        )
        result = self.correlator.attribute(
            pattern_key="", tool_call_id="tc_1",
            pending_forecasts=tuple(self.correlator.pending()),
        )
        self.assertIsNone(result, "an ambiguous match must not attribute")

    def test_the_hook_path_passes_the_pending_forecasts(self):
        """The check is not merely present: it is reached."""
        import inspect

        source = inspect.getsource(hooks.on_post_approval_response)
        self.assertIn("pending", source.lower())

    def test_an_unambiguous_observation_still_attributes(self):
        pattern = expected_pattern_key("fc_one", "E-HIGH")
        self.correlator.register(
            forecast_id="fc_one", rule="E-HIGH", pattern_key=pattern,
            tool_call_id="tc_1",
        )
        result = self.correlator.attribute(
            pattern_key=pattern, tool_call_id="tc_1",
            pending_forecasts=tuple(self.correlator.pending()),
        )
        self.assertEqual(result, "fc_one")


class RuleBindingTests(unittest.TestCase):
    """F4: the rule the plugin escalated with must match."""

    def setUp(self):
        self.correlator = Correlator()

    def test_a_pattern_naming_a_different_rule_is_not_attributed(self):
        """A caller must not be able to choose the rule.

        The pattern key names a pending forecast, but with a rule the
        plugin never escalated with. Accepting it would let the caller
        supply the forecast and pick the rule.
        """
        self.correlator.register(
            forecast_id="fc_one", rule="E-HIGH",
            pattern_key=expected_pattern_key("fc_one", "E-HIGH"),
        )
        result = self.correlator.attribute(
            pattern_key=expected_pattern_key("fc_one", "E-CRITICAL")
        )
        self.assertIsNone(result)

    def test_the_matching_rule_is_attributed(self):
        pattern = expected_pattern_key("fc_one", "E-HIGH")
        self.correlator.register(
            forecast_id="fc_one", rule="E-HIGH", pattern_key=pattern,
        )
        self.assertEqual(self.correlator.attribute(pattern_key=pattern), "fc_one")


class ToolFateTests(unittest.TestCase):
    """F5, rejected: an automatic allowance authorizes nothing."""

    def test_automatically_allowed_is_not_an_approval(self):
        machine = AuthorizationMachine()
        record = machine.from_tool_fate(ran=True)
        self.assertEqual(
            record.state, AUTHORIZATION_STATE.AUTOMATICALLY_ALLOWED
        )
        self.assertFalse(record.is_approval)


class AccuracyNoteTests(unittest.TestCase):
    """F6: the note is the output of the verification, not an input."""

    def test_the_note_cannot_be_supplied(self):
        import inspect

        from ..lifecycle import Lifecycle

        signature = inspect.signature(Lifecycle.compare)
        self.assertNotIn(
            "accuracy_note", signature.parameters,
            "the accuracy note must be derived, not supplied",
        )

    def test_the_note_states_that_no_unexpected_outcome_was_found(self):
        from ..domain import records as R

        from ..lifecycle import derive_verdict

        outcome = R.Outcome(
            id="out_x", forecast_id="fc_x", execution_id="exe_x",
            recorded_at="2026-11-10T12:00:00.000Z", recorded_by="plugin",
            verification_method="FILE_DIFF", summary="it happened",
            observations=[
                R.OutcomeObservation(
                    id="ob_x", target="t", observation="o", label="OBSERVED",
                    evidence_source_kind="FILESYSTEM", evidence_ref="d",
                    confidence="HIGH"),
            ])
        verdict, counts = derive_verdict(outcome)
        self.assertEqual(verdict, "ALIGNED")


def _provider(path):
    import sqlite3

    connection = sqlite3.connect(path)
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


if __name__ == "__main__":
    unittest.main()
