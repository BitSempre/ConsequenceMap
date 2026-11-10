"""Tests for the Phase 2B runtime modules.

Five modules, each tested against the behaviour the specification
requires:

* ``correlation`` - attribution, the eight edge cases, the duplicate
  and orphan counters;
* ``authorization`` - the thirteen states, and the rule that only an
  observed human approval authorizes anything;
* ``paths`` - the six-step containment algorithm, and the protected
  patterns;
* ``self_exclusion`` - RECUR-1 through RECUR-9;
* ``hooks`` - the five callbacks, and what each may and may not do.

These modules import nothing from Hermes, so the suite runs anywhere.
"""
from __future__ import annotations

import os
import tempfile
import unittest

from ..authorization import (
    AuthorizationMachine,
    AuthorizationRecord,
    state_for_choice,
)
from ..correlation import (
    Correlator,
    expected_pattern_key,
    make_rule_key,
    parse_pattern_key,
)
from ..domain.enums import AUTHORIZATION_STATE, AUTHORIZED_BY
from ..paths import (
    PathError,
    applies_to_operation,
    is_protected,
    resolve_path,
    root_digest,
)
from .. import self_exclusion


class RuleKeyTests(unittest.TestCase):
    def test_the_plugin_never_includes_the_host_prefix(self):
        key = make_rule_key("fc_abc", "E-HIGH")
        self.assertEqual(key, "cm:fc_abc:E-HIGH")
        self.assertNotIn("plugin_rule:", key)

    def test_the_expected_pattern_key_is_what_the_observer_sees(self):
        self.assertEqual(
            expected_pattern_key("fc_abc", "E-HIGH"),
            "plugin_rule:cm:fc_abc:E-HIGH",
        )

    def test_an_unknown_rule_is_refused(self):
        with self.assertRaises(ValueError):
            make_rule_key("fc_abc", "E-NONSENSE")

    def test_the_observed_key_is_parsed_back(self):
        self.assertEqual(
            parse_pattern_key("plugin_rule:cm:fc_abc:E-HIGH"),
            ("fc_abc", "E-HIGH"),
        )

    def test_another_plugin_s_key_is_not_ours(self):
        """EC-8: the host's own approval is not ours."""
        self.assertIsNone(parse_pattern_key("plugin_rule:cm:other:E-HIGH:x"))
        self.assertIsNone(parse_pattern_key("builtin_rule:whatever"))
        self.assertIsNone(parse_pattern_key(None))


class CorrelationTests(unittest.TestCase):
    def setUp(self):
        self.correlator = Correlator()
        self.pattern = expected_pattern_key("fc_abc", "E-HIGH")

    def test_an_observation_with_the_matching_pattern_is_attributed(self):
        self.correlator.register(
            forecast_id="fc_abc", rule="E-HIGH", pattern_key=self.pattern
        )
        self.assertEqual(
            self.correlator.attribute(pattern_key=self.pattern), "fc_abc"
        )

    def test_an_observation_without_a_pattern_is_not_attributed(self):
        """EC-2: an orphan observation belongs to nobody."""
        self.correlator.register(
            forecast_id="fc_abc", rule="E-HIGH", pattern_key=self.pattern
        )
        self.assertIsNone(self.correlator.attribute(pattern_key=""))
        self.assertEqual(self.correlator.orphans, 0)

    def test_an_empty_tool_call_id_is_absent_not_a_match(self):
        """EC-1: an empty id is not a match."""
        self.correlator.register(
            forecast_id="fc_abc", rule="E-HIGH", pattern_key=self.pattern,
            tool_call_id="tc_1",
        )
        self.assertIsNone(
            self.correlator.attribute(pattern_key="", tool_call_id="")
        )

    def test_the_tool_call_id_is_a_second_channel(self):
        """P-CORR-1: the channels are alternatives, not conjuncts."""
        self.correlator.register(
            forecast_id="fc_abc", rule="E-HIGH", pattern_key=self.pattern,
            tool_call_id="tc_1",
        )
        self.assertEqual(
            self.correlator.attribute(pattern_key="", tool_call_id="tc_1"),
            "fc_abc",
        )

    def test_a_duplicate_response_is_ignored_and_counted(self):
        """EC-3: the first observation wins."""
        self.correlator.register(
            forecast_id="fc_abc", rule="E-HIGH", pattern_key=self.pattern
        )
        self.assertIsNotNone(
            self.correlator.note_response(self.pattern, "tc_1")
        )
        self.assertIsNone(self.correlator.note_response(self.pattern, "tc_1"))
        self.assertEqual(self.correlator.duplicates, 1)

    def test_an_escalation_that_was_never_asked_for_is_not_attributed(self):
        """escalation_expected false means no attribution."""
        self.correlator.register(
            forecast_id="fc_abc", rule="E-HIGH", pattern_key=self.pattern
        )
        self.assertIsNone(
            self.correlator.attribute(
                pattern_key=self.pattern, escalation_expected=False
            )
        )

    def test_an_expired_escalation_is_listed(self):
        self.correlator.register(
            forecast_id="fc_abc", rule="E-HIGH", pattern_key=self.pattern,
            deadline=100.0,
        )
        self.assertEqual(self.correlator.expired(now=101.0), ("fc_abc",))
        self.assertEqual(self.correlator.expired(now=99.0), ())

    def test_the_two_channels_never_produce_an_ambiguous_approval(self):
        """EC-7: an ambiguous match is never HUMAN_APPROVED."""
        self.correlator.register(
            forecast_id="fc_abc", rule="E-HIGH",
            pattern_key=expected_pattern_key("fc_abc", "E-HIGH"),
            tool_call_id="tc_1",
        )
        self.correlator.register(
            forecast_id="fc_def", rule="E-HIGH",
            pattern_key=expected_pattern_key("fc_def", "E-HIGH"),
            tool_call_id="tc_1",
        )
        result = self.correlator.attribute(
            pattern_key="", tool_call_id="tc_1",
            pending_forecasts=("fc_abc", "fc_def"),
        )
        self.assertIsNone(result)


class AuthorizationStateTests(unittest.TestCase):
    def setUp(self):
        self.machine = AuthorizationMachine()

    def test_each_choice_maps_to_its_state(self):
        self.assertEqual(
            state_for_choice("once"), AUTHORIZATION_STATE.HUMAN_APPROVED
        )
        self.assertEqual(
            state_for_choice("deny"), AUTHORIZATION_STATE.HUMAN_REJECTED
        )
        self.assertEqual(
            state_for_choice("timeout"), AUTHORIZATION_STATE.APPROVAL_TIMEOUT
        )
        self.assertEqual(
            state_for_choice("cancelled"), AUTHORIZATION_STATE.APPROVAL_CANCELLED
        )
        self.assertEqual(
            state_for_choice("notify_failed"), AUTHORIZATION_STATE.TRANSPORT_FAILED
        )
        self.assertEqual(
            state_for_choice("smart_approve"),
            AUTHORIZATION_STATE.GUARDIAN_APPROVED,
        )
        self.assertEqual(
            state_for_choice("smart_deny"), AUTHORIZATION_STATE.GUARDIAN_REJECTED
        )

    def test_an_unknown_choice_is_unknown(self):
        """An unknown choice is neither an approval nor a refusal."""
        self.assertIsNone(state_for_choice("something_new"))
        record = self.machine.from_choice("something_new")
        self.assertEqual(record.state, AUTHORIZATION_STATE.UNKNOWN)
        self.assertFalse(record.is_approval)

    def test_a_timeout_is_not_a_refusal(self):
        """The confusion the specification names as high-risk."""
        timeout = self.machine.from_choice("timeout")
        refusal = self.machine.from_choice("deny")
        self.assertNotEqual(timeout.state, refusal.state)
        self.assertEqual(timeout.authorized_by, AUTHORIZED_BY.NONE)
        self.assertEqual(refusal.authorized_by, AUTHORIZED_BY.USER)
        self.assertFalse(timeout.is_approval)

    def test_a_cancelled_prompt_is_not_a_refusal(self):
        cancelled = self.machine.from_choice("cancelled")
        refusal = self.machine.from_choice("deny")
        self.assertNotEqual(cancelled.state, refusal.state)
        self.assertEqual(cancelled.authorized_by, AUTHORIZED_BY.NONE)

    def test_the_guardian_is_never_recorded_as_the_human(self):
        guardian = self.machine.from_choice("smart_approve")
        self.assertEqual(guardian.authorized_by, AUTHORIZED_BY.GUARDIAN_LLM)
        self.assertNotEqual(guardian.authorized_by, AUTHORIZED_BY.USER)

    def test_only_a_real_approval_authorizes(self):
        self.assertTrue(self.machine.from_choice("once").is_approval)
        self.assertTrue(self.machine.from_choice("smart_approve").is_approval)
        for choice in (
            "deny", "timeout", "cancelled", "notify_failed", "smart_deny",
        ):
            self.assertFalse(self.machine.from_choice(choice).is_approval)
        self.assertFalse(self.machine.not_observed().is_approval)
        self.assertFalse(self.machine.unknown().is_approval)
        self.assertFalse(self.machine.not_required().is_approval)

    def test_a_tool_that_ran_with_no_approval_is_automatic(self):
        """EC-6."""
        allowed = self.machine.from_tool_fate(ran=True)
        denied = self.machine.from_tool_fate(ran=False)
        self.assertEqual(
            allowed.state, AUTHORIZATION_STATE.AUTOMATICALLY_ALLOWED
        )
        self.assertEqual(
            denied.state, AUTHORIZATION_STATE.AUTOMATICALLY_DENIED
        )
        # An automatic allowance is not a human approval.
        self.assertFalse(allowed.is_approval)

    def test_the_deadline_is_the_host_wait_plus_the_grace(self):
        """DEC-16, mechanism M-1."""
        machine = AuthorizationMachine(grace_seconds=30)
        deadline = machine.deadline_for(escalated_at=1000.0, host_timeout=300)
        self.assertEqual(deadline, 1330.0)
        self.assertTrue(
            machine.expired(escalated_at=1000.0, host_timeout=300, now=1331.0)
        )
        self.assertFalse(
            machine.expired(escalated_at=1000.0, host_timeout=300, now=1329.0)
        )


class PathContainmentTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="cm-path-")
        self.root = self.directory.name
        self.inside = os.path.join(self.root, "reports")
        os.makedirs(self.inside)

    def tearDown(self):
        self.directory.cleanup()

    def test_a_path_inside_the_root_is_contained(self):
        result = resolve_path(
            os.path.join(self.inside, "daily.md"), self.root
        )
        self.assertTrue(result.contained)

    def test_a_relative_path_is_anchored_to_the_root(self):
        result = resolve_path("reports/daily.md", self.root)
        self.assertTrue(result.contained)

    def test_a_traversal_outside_the_root_is_refused(self):
        result = resolve_path("../../outside.txt", self.root)
        self.assertFalse(result.contained)

    def test_an_absolute_path_outside_the_root_is_refused(self):
        result = resolve_path(os.path.join(self.root, "..", "..", "x.txt"), self.root)
        self.assertFalse(result.contained)

    def test_a_sibling_with_the_root_as_a_prefix_is_refused(self):
        """The naive prefix check would wrongly pass this."""
        sibling = self.root + "-other"
        os.makedirs(sibling, exist_ok=True)
        try:
            result = resolve_path(os.path.join(sibling, "x.txt"), self.root)
            self.assertFalse(result.contained)
        finally:
            os.rmdir(sibling)

    def test_the_root_digest_is_stable_and_not_a_path(self):
        first = root_digest(self.root)
        self.assertEqual(first, root_digest(self.root))
        self.assertNotIn(self.root, first)
        self.assertEqual(len(first), 64)

    def test_a_protected_pattern_matches_the_resolved_path(self):
        target = os.path.join(self.inside, "daily.md")
        self.assertTrue(
            is_protected(target, ["**/reports/**"], root=self.root)
        )
        self.assertFalse(is_protected(target, [], root=self.root))

    def test_e_protected_applies_only_to_write_operations(self):
        self.assertTrue(applies_to_operation("FILE_WRITE"))
        self.assertTrue(applies_to_operation("FILE_DELETE"))
        self.assertTrue(applies_to_operation("FILE_PATCH"))
        self.assertFalse(applies_to_operation("COMMAND"))
        self.assertFalse(applies_to_operation("EXTERNAL_CALL"))

    def test_an_empty_path_is_refused(self):
        with self.assertRaises(PathError):
            resolve_path("", self.root)


class SelfExclusionTests(unittest.TestCase):
    def setUp(self):
        self_exclusion.COUNTER.reset()

    def test_the_plugin_s_own_tools_are_excluded(self):
        for name in self_exclusion.REGISTERED_TOOLS:
            self.assertTrue(self_exclusion.is_excluded(name))

    def test_a_host_tool_is_not_excluded(self):
        self.assertFalse(self_exclusion.is_excluded("write_file"))
        self.assertFalse(self_exclusion.is_excluded("terminal"))

    def test_a_non_string_is_not_excluded(self):
        """The plugin does not guess."""
        self.assertFalse(self_exclusion.is_excluded(None))
        self.assertFalse(self_exclusion.is_excluded(42))

    def test_every_registered_tool_uses_the_reserved_prefix(self):
        """RECUR-2: the namespace cannot collide."""
        for name in self_exclusion.REGISTERED_TOOLS:
            self.assertTrue(name.startswith(self_exclusion.TOOL_PREFIX))

    def test_the_excluded_set_is_frozen(self):
        """RECUR-7: it cannot be widened at runtime."""
        self.assertIsInstance(self_exclusion.EXCLUDED_TOOL_NAMES, frozenset)
        with self.assertRaises(AttributeError):
            self_exclusion.EXCLUDED_TOOL_NAMES.add("write_file")

    def test_the_exclusion_leaves_a_trace(self):
        """RECUR-9."""
        self_exclusion.record_exclusion("consequence_map_forecast")
        self.assertEqual(self_exclusion.COUNTER.count("consequence_map_forecast"), 1)
        self.assertEqual(self_exclusion.COUNTER.total(), 1)
        self.assertIn("consequence_map_forecast", self_exclusion.COUNTER.snapshot())

    def test_the_internal_operations_are_excluded_too(self):
        """RECUR-6."""
        for name in self_exclusion.INTERNAL_OPERATIONS:
            self.assertTrue(self_exclusion.is_excluded(name))


class PendingStateTests(unittest.TestCase):
    """The one state that is not terminal.

    ``PENDING`` says an escalation is in flight. It says nothing about
    whether the human will answer, and it authorizes nothing.
    """

    def setUp(self):
        from ..authorization import AuthorizationMachine

        self.machine = AuthorizationMachine()

    def test_pending_is_derivable(self):
        record = self.machine.pending(forecast_id="fc_1")
        self.assertEqual(record.state, AUTHORIZATION_STATE.PENDING)
        self.assertEqual(record.authorized_by, AUTHORIZED_BY.NONE)

    def test_pending_authorizes_nothing(self):
        self.assertFalse(self.machine.pending().is_approval)

    def test_pending_is_the_only_non_terminal_state(self):
        """Everything else is an answer, a refusal, or an absence."""
        for choice in (
            "once", "deny", "timeout", "cancelled", "notify_failed",
            "smart_approve", "smart_deny",
        ):
            record = self.machine.from_choice(choice)
            self.assertNotEqual(record.state, AUTHORIZATION_STATE.PENDING)


class HookRecordTests(unittest.TestCase):
    """The hooks record what the host observed.

    The sink is the seam. A hook must never fail because the storage
    is unavailable, but a missing record must never be mistaken for
    an approval.
    """

    def setUp(self):
        from .. import hooks

        self.hooks = hooks
        self.hooks.STATE.reset()
        self.sink = hooks.MemoryAuthorizationSink()
        self.hooks.STATE.sink = self.sink
        self_exclusion.COUNTER.reset()
        self.pattern = "plugin_rule:cm:fc_abc:E-HIGH"

    def _register(self):
        self.hooks.STATE.correlator.register(
            forecast_id="fc_abc", rule="E-HIGH", pattern_key=self.pattern,
            tool_call_id="tc_1",
        )

    def test_an_escalation_in_flight_is_recorded_as_pending(self):
        self._register()
        self.hooks.on_pre_approval_request(
            pattern_key=self.pattern, tool_call_id="tc_1",
        )
        self.assertEqual(len(self.sink.begun), 1)
        self.assertEqual(self.sink.begun[0].state, AUTHORIZATION_STATE.PENDING)
        self.assertFalse(self.sink.begun[0].is_approval)

    def test_the_answer_is_recorded_as_the_state_it_is(self):
        self._register()
        self.hooks.on_pre_approval_request(
            pattern_key=self.pattern, tool_call_id="tc_1",
        )
        self.hooks.on_post_approval_response(
            pattern_key=self.pattern, tool_call_id="tc_1", choice="once",
        )
        self.assertEqual(len(self.sink.settled), 1)
        self.assertEqual(
            self.sink.settled[0].state, AUTHORIZATION_STATE.HUMAN_APPROVED
        )
        self.assertTrue(self.sink.settled[0].is_approval)

    def test_a_refusal_is_recorded_as_a_refusal(self):
        self._register()
        self.hooks.on_pre_approval_request(
            pattern_key=self.pattern, tool_call_id="tc_1",
        )
        self.hooks.on_post_approval_response(
            pattern_key=self.pattern, tool_call_id="tc_1", choice="deny",
        )
        self.assertEqual(
            self.sink.settled[0].state, AUTHORIZATION_STATE.HUMAN_REJECTED
        )
        self.assertFalse(self.sink.settled[0].is_approval)

    def test_an_orphan_response_records_nothing(self):
        """EC-2: an observation that belongs to nobody is not recorded."""
        self.hooks.on_post_approval_response(
            pattern_key=self.pattern, tool_call_id="tc_1", choice="once",
        )
        self.assertEqual(self.sink.settled, [])

    def test_a_duplicate_response_records_once(self):
        """EC-3: the first observation wins."""
        self._register()
        self.hooks.on_pre_approval_request(
            pattern_key=self.pattern, tool_call_id="tc_1",
        )
        for _ in range(2):
            self.hooks.on_post_approval_response(
                pattern_key=self.pattern, tool_call_id="tc_1", choice="once",
            )
        self.assertEqual(len(self.sink.settled), 1)
        self.assertEqual(self.hooks.STATE.correlator.duplicates, 1)

    def test_an_excluded_tool_records_nothing(self):
        """RECUR-3: the plugin's own calls leave no trace."""
        self.hooks.on_pre_approval_request(
            tool_name="consequence_map_forecast",
            pattern_key=self.pattern, tool_call_id="tc_1",
        )
        self.assertEqual(self.sink.begun, [])
        self.assertEqual(self_exclusion.COUNTER.total(), 1)


class HookTests(unittest.TestCase):
    def setUp(self):
        from .. import hooks

        self.hooks = hooks
        self.hooks.STATE.reset()
        self_exclusion.COUNTER.reset()

    def test_the_transform_hook_never_returns_a_replacement(self):
        """RECUR-8: it is registered as a declaration and never used."""
        payload = {"result": {"value": 1}, "tool_name": "write_file"}
        self.assertIsNone(self.hooks.on_transform_tool_result(**payload))
        self.assertEqual(payload["result"], {"value": 1})

    def test_an_excluded_tool_call_produces_no_escalation(self):
        """RECUR-3: complete invisibility."""
        result = self.hooks.on_pre_tool_call(
            tool_name="consequence_map_forecast",
            consequence_map_escalation={"rule_key": "cm:fc_1:E-HIGH"},
        )
        self.assertIsNone(result)
        self.assertEqual(self_exclusion.COUNTER.total(), 1)

    def test_a_non_excluded_tool_with_no_escalation_proceeds(self):
        result = self.hooks.on_pre_tool_call(tool_name="write_file")
        self.assertIsNone(result)

    def test_an_escalation_produces_the_host_shape(self):
        result = self.hooks.on_pre_tool_call(
            tool_name="write_file",
            consequence_map_escalation={
                "rule_key": "cm:fc_1:E-HIGH",
                "message": "this writes a protected file",
            },
        )
        self.assertIsNotNone(result)
        self.assertEqual(result["action"], "approve")
        self.assertEqual(result["rule_key"], "cm:fc_1:E-HIGH")

    def test_the_observer_hooks_return_none(self):
        """The host ignores their return values; they change nothing."""
        self.assertIsNone(self.hooks.on_pre_approval_request(
            pattern_key="plugin_rule:cm:fc_1:E-HIGH", tool_call_id="tc_1",
        ))
        self.assertIsNone(self.hooks.on_post_approval_response(
            pattern_key="plugin_rule:cm:fc_1:E-HIGH", tool_call_id="tc_1",
            choice="once",
        ))
        self.assertIsNone(self.hooks.on_post_tool_call(
            pattern_key="plugin_rule:cm:fc_1:E-HIGH", tool_call_id="tc_1",
            status="ok",
        ))

    def test_the_command_reports_the_state_and_claims_nothing(self):
        output = self.hooks.on_command("status")
        self.assertIn("ConsequenceMap", output)
        self.assertIn("Excluded tool calls", output)

    def test_the_command_rejects_an_unknown_argument(self):
        output = self.hooks.on_command("nonsense")
        self.assertIn("Usage:", output)


if __name__ == "__main__":
    unittest.main()
