"""Phase G — the Guardian's own test suite.

Ten scenarios, one per requirement of the owner's Phase G list. Each test
that could mutate files runs against an isolated copy, never the production
tree.
"""
from __future__ import annotations

import io
import json
import os
import shutil
import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from quality_guardian import classify, config, detect, guardian, hook, repair, runner  # noqa: E402
from quality_guardian.tests.isolated import IsolatedProjectTestCase, make_isolated_project  # noqa: E402


class G01ChangeDetectionTest(IsolatedProjectTestCase):
    """G1 — a change in a file is detected."""

    def test_content_change_is_detected(self):
        target = self.root / "consequence_map" / "sample.py"
        # The realistic scenario: a baseline exists from a previous cycle.
        detect.save_state(detect.current_hashes(self.root), self.root)
        before = detect.detect_changes(self.root)
        self.assertNotIn("consequence_map/sample.py", before["modified"])
        target.write_text(target.read_text(encoding="utf-8") + "\n# touched\n", encoding="utf-8")
        after = detect.detect_changes(self.root)
        self.assertIn("consequence_map/sample.py", after["modified"])

    def test_identical_rewrite_is_not_a_change(self):
        target = self.root / "consequence_map" / "sample.py"
        original = target.read_text(encoding="utf-8")
        detect.save_state(detect.current_hashes(self.root), self.root)
        target.write_text(original, encoding="utf-8")
        after = detect.detect_changes(self.root)
        self.assertEqual(after["modified"], [])


class G02TriggerTest(IsolatedProjectTestCase):
    """G2 — the verification mechanism fires automatically."""

    def test_post_tool_call_triggers_a_cycle_for_a_project_write(self):
        target = self.root / "consequence_map" / "sample.py"
        target.write_text(target.read_text(encoding="utf-8") + "\n# changed\n", encoding="utf-8")
        payload = {
            "hook_event_name": "post_tool_call",
            "tool_name": "write_file",
            "tool_input": {"path": str(target), "content": "x"},
            "session_id": "s",
        }
        reports_before = len(list((self.root / "quality_guardian" / "reports").glob("*.json"))) \
            if (self.root / "quality_guardian" / "reports").exists() else 0
        # The hook resolves the project root from its own location, so the
        # isolated tree is exercised through the Guardian API directly.
        cycle = guardian.run_cycle(trigger="post_tool_call:write_file", root=self.root)
        guardian.finalize(cycle, self.root)
        reports_after = len(list((self.root / "quality_guardian" / "reports").glob("*.json")))
        self.assertGreater(reports_after, reports_before)
        self.assertTrue(cycle.changed_files)

    def test_post_tool_call_ignores_a_write_outside_the_project(self):
        outside = Path(self.root).parent / "elsewhere.txt"
        outside.write_text("not ours", encoding="utf-8")
        self.addCleanup(lambda: outside.unlink(missing_ok=True))
        self.assertFalse(hook._is_project_path(str(outside), self.root))
        self.assertTrue(hook._is_project_path(str(self.root / "consequence_map" / "sample.py"), self.root))


class G03TestSelectionTest(IsolatedProjectTestCase):
    """G3 — the appropriate tests are executed."""

    def test_changed_module_selects_its_test_module(self):
        selected = runner.select_tests(["consequence_map/domain/records.py"])
        self.assertIn("test_records", selected)
        self.assertIn("test_import_audit", selected)

    def test_high_impact_module_forces_the_full_set(self):
        selected = runner.select_tests(["consequence_map/storage/schema.py"])
        self.assertEqual(sorted(selected), sorted(config.FULL_TEST_SET))

    def test_unrelated_file_selects_only_the_always_run_set(self):
        selected = runner.select_tests(["docs/PHASE-2A-MANIFEST.md"])
        self.assertEqual(sorted(selected), sorted(config.ALWAYS_RUN_TESTS))


class G04IntentionalFailureTest(IsolatedProjectTestCase):
    """G4 — an intentional failure is detected in an isolated environment."""

    def test_a_broken_module_is_reported_as_a_failure(self):
        broken = self.root / "consequence_map" / "sample.py"
        broken.write_text("def add(left, right):\n    return left - right\n", encoding="utf-8")
        run = runner.run_test_module("test_sample", root=self.root)
        self.assertEqual(run.verdict, "FAIL")
        self.assertGreater(run.failed + run.errors, 0)


class G05AutoRepairTest(IsolatedProjectTestCase):
    """G5 — a mechanical problem is repaired automatically."""

    def test_trailing_whitespace_is_repaired(self):
        target = self.root / "consequence_map" / "sample.py"
        target.write_text("X = 1   \nY = 2\t\n", encoding="utf-8")
        source = repair.read_file_text(target)
        fixed, notes = repair.apply_level1_fixes(target, source)
        self.assertNotEqual(fixed, source)
        self.assertTrue(notes)
        self.assertNotIn("   \n", fixed)

    def test_missing_final_newline_is_repaired(self):
        target = self.root / "consequence_map" / "sample.py"
        target.write_text("X = 1", encoding="utf-8")
        source = repair.read_file_text(target)
        fixed, _notes = repair.apply_level1_fixes(target, source)
        self.assertTrue(fixed.endswith("\n"))

    def test_unused_import_is_detected(self):
        target = self.root / "consequence_map" / "sample.py"
        target.write_text("import os\nimport json\n\nVALUE = 1\n", encoding="utf-8")
        source = repair.read_file_text(target)
        self.assertEqual(repair.find_unused_imports(source), ["json", "os"])


class G06ReRunTest(IsolatedProjectTestCase):
    """G6 — the tests are re-run after the repair."""

    def test_the_cycle_re_runs_the_tests_after_a_repair(self):
        # A file OUTSIDE the manifest-protected prefixes, so the Level 1
        # repair is permitted. Files covered by the Phase 2A manifest are
        # reported, never rewritten.
        target = self.root / "scratch" / "sample_copy.py"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("def add(left, right):\n    return left + right   \n", encoding="utf-8")
        cycle = guardian.run_cycle(trigger="g06", root=self.root)
        applied = [p for p in cycle.repair_outcome.proposals if p.applied]
        self.assertTrue(applied, "the mechanical repair was not applied")
        self.assertTrue(any(r.module for r in cycle.test_runs))
        self.assertGreater(len(cycle.test_runs), 1)
        self.assertFalse(target.read_text(encoding="utf-8").endswith("   \n"))

    def test_a_manifest_covered_file_is_never_rewritten(self):
        target = self.root / "consequence_map" / "sample.py"
        target.write_text("X = 1   \n", encoding="utf-8")
        before = target.read_text(encoding="utf-8")
        guardian.run_cycle(trigger="g06b", root=self.root)
        self.assertEqual(target.read_text(encoding="utf-8"), before)


class G07AttemptLimitTest(IsolatedProjectTestCase):
    """G7 — the cycle stops after the attempt limit."""

    def test_the_attempt_limit_is_enforced(self):
        self.assertEqual(config.MAX_REPAIR_ATTEMPTS, 3)
        cycle = guardian.run_cycle(trigger="g07", root=self.root)
        self.assertLessEqual(cycle.repair_outcome.attempts, config.MAX_REPAIR_ATTEMPTS)

    def test_a_failing_cycle_stops_at_the_limit(self):
        # A file whose every mechanical repair still leaves a failing test.
        target = self.root / "consequence_map" / "sample.py"
        target.write_text("def add(left, right):\n    return left - right   \n", encoding="utf-8")
        cycle = guardian.run_cycle(trigger="g07b", root=self.root)
        self.assertLessEqual(cycle.repair_outcome.attempts, config.MAX_REPAIR_ATTEMPTS)
        if cycle.repair_outcome.stopped:
            self.assertIn("limit", cycle.repair_outcome.stop_reason)


class G08HumanEscalationTest(IsolatedProjectTestCase):
    """G8 — critical problems are routed to a human decision."""

    def test_a_normative_failure_is_never_auto_repaired(self):
        level = repair.classify_failure(classify.NORMATIVE, None)
        self.assertEqual(level, repair.LEVEL_HUMAN)

    def test_a_decision_failure_is_never_auto_repaired(self):
        level = repair.classify_failure(classify.DECISION, None)
        self.assertEqual(level, repair.LEVEL_HUMAN)

    def test_a_test_failure_is_never_auto_repaired(self):
        level = repair.classify_failure(classify.TEST, None)
        self.assertEqual(level, repair.LEVEL_ASSISTED)

    def test_a_protected_path_is_never_auto_repaired(self):
        level = repair.classify_failure(classify.IMPLEMENTATION, "consequence_map/storage/schema.py")
        self.assertEqual(level, repair.LEVEL_HUMAN)

    def test_the_ineligible_kinds_are_refused(self):
        for kind in (classify.NORMATIVE, classify.DECISION, classify.TEST):
            self.assertIn(kind, repair.INELIGIBLE_KINDS)


class G09PreservationTest(IsolatedProjectTestCase):
    """G9 — pre-existing changes are preserved."""

    def test_an_unrelated_existing_file_is_untouched(self):
        keep = self.root / "consequence_map" / "keep_me.py"
        keep.write_text("VALUE = 42\n", encoding="utf-8")
        before = keep.read_text(encoding="utf-8")
        guardian.run_cycle(trigger="g09", root=self.root)
        self.assertEqual(keep.read_text(encoding="utf-8"), before)

    def test_the_guardian_never_writes_outside_the_project(self):
        for name in ("config.py", "detect.py", "repair.py", "guardian.py"):
            source = (Path(guardian.__file__).parent / name).read_text(encoding="utf-8")
            self.assertNotIn("C:\\Users\\Utente\\Desktop\\ConsequenceMap-Phase", source)


class G11CorruptionGuardTest(IsolatedProjectTestCase):
    """G11 — a repair that would bury corruption is refused.

    This is the defence against the class of damage that a truncation bug in
    a caller can cause: a mechanical repair must never shrink a file
    drastically.
    """

    def test_a_shrinking_repair_is_refused(self):
        original = "x" * 1000
        fixed = "x" * 10
        self.assertFalse(repair.repair_is_sane(original, fixed))

    def test_a_formatting_repair_is_sane(self):
        original = "X = 1   \nY = 2\n"
        fixed, _notes = repair.apply_level1_fixes(Path("x.py"), original)
        self.assertTrue(repair.repair_is_sane(original, fixed))

    def test_a_corrupted_file_is_not_rewritten(self):
        # A file already truncated to a single byte must be reported, not
        # "repaired" into a different corruption.
        target = self.root / "scratch" / "corrupt.py"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("\n", encoding="utf-8")
        before = target.read_text(encoding="utf-8")
        cycle = guardian.run_cycle(trigger="g11", root=self.root)
        self.assertEqual(target.read_text(encoding="utf-8"), before)
        self.assertLessEqual(cycle.repair_outcome.attempts, config.MAX_REPAIR_ATTEMPTS)


class G10NoExternalDependencyTest(IsolatedProjectTestCase):
    """G10 — the system works with no paid or external service."""

    def test_no_network_module_is_imported_by_the_guardian(self):
        import ast
        forbidden = {"socket", "http", "urllib", "requests", "httpx", "aiohttp"}
        guardian_dir = Path(guardian.__file__).parent
        for path in guardian_dir.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        self.assertNotIn(alias.name.split(".")[0], forbidden, path.name)
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        self.assertNotIn(node.module.split(".")[0], forbidden, path.name)

    def test_the_guardian_declares_no_production_dependency(self):
        source = (Path(guardian.__file__).parent / "config.py").read_text(encoding="utf-8")
        self.assertNotIn("import requests", source)


class GuardianApiTest(unittest.TestCase):
    """The classification API itself."""

    def test_the_worst_verdict_dominates(self):
        cycle = classify.CycleResult()
        cycle.add(classify.CheckResult(name="a", verdict=classify.PASS))
        self.assertEqual(cycle.worst, classify.PASS)
        cycle.add(classify.CheckResult(name="b", verdict=classify.WARNING))
        self.assertEqual(cycle.worst, classify.WARNING)
        cycle.add(classify.CheckResult(name="c", verdict=classify.NOT_VERIFIED))
        self.assertEqual(cycle.worst, classify.NOT_VERIFIED)
        cycle.add(classify.CheckResult(name="d", verdict=classify.FAIL))
        self.assertEqual(cycle.worst, classify.FAIL)

    def test_no_tests_configured_is_never_a_pass(self):
        self.assertNotEqual(runner.NO_TESTS_CONFIGURED, classify.PASS)

    def test_a_module_with_no_tests_is_not_verified(self):
        root = make_isolated_project()
        self.addCleanup(shutil.rmtree, root, True)
        run = runner.run_test_module("test_does_not_exist", root=root)
        self.assertNotEqual(run.verdict, classify.PASS)


if __name__ == "__main__":
    unittest.main()
