"""The repair policy is fail-closed.

An automatic repair is a capability. The owner suspended it. A policy
that cannot be read - absent, unreadable, malformed, or carrying a
value that is not a boolean - must therefore resolve to SUSPENDED.

Only an explicit ``"auto_repair": true`` in a readable policy file
enables the capability, and only for the root that file belongs to.

These tests are behavioural: they write a policy, ask the Guardian
whether repair is permitted, and check the answer. Nothing here
inspects the source text.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from quality_guardian import config, repair  # noqa: E402


class RepairPolicyIsFailClosed(unittest.TestCase):
    """A policy that cannot grant permission must not grant it."""

    def setUp(self):
        self.directory = tempfile.mkdtemp(prefix="cm-policy-closed-")
        self.addCleanup(shutil.rmtree, self.directory, True)
        self.root = Path(self.directory) / "project"
        (self.root / "quality_guardian" / "state").mkdir(parents=True)
        (self.root / "consequence_map").mkdir()
        self.policy_file = (
            self.root / "quality_guardian" / "state" / "repair-policy.json"
        )

    def _write_policy(self, text: str) -> None:
        self.policy_file.write_text(text, encoding="utf-8")

    def _assert_refused(self, label: str) -> None:
        """A write into this root must be refused."""
        target = self.root / "consequence_map" / "_probe.py"
        self.assertFalse(target.exists(), "%s: the probe file exists" % (label,))
        with self.assertRaises(
            repair.RepairSuspended,
            msg="%s: the write was NOT refused" % (label,),
        ):
            repair.write_file_text(target, "x = 1\n", root=self.root)
        self.assertFalse(target.exists(), "%s: the file was written" % (label,))

    def test_the_default_is_repair_suspended(self):
        """The default must be the safe one."""
        self.assertIs(config.DEFAULT_AUTO_REPAIR, False)

    def test_an_absent_policy_refuses_the_repair(self):
        self.assertFalse(self.policy_file.exists())
        self.assertIs(config.auto_repair_enabled(self.root), False)
        self._assert_refused("absent policy")

    def test_an_unreadable_policy_refuses_the_repair(self):
        """A file that cannot be decoded must not enable repair."""
        self.policy_file.write_bytes(b"\xff\xfe\x00binary junk")
        self.assertIs(config.auto_repair_enabled(self.root), False)
        self._assert_refused("unreadable policy")

    def test_a_malformed_json_policy_refuses_the_repair(self):
        self._write_policy("{ this is not json ")
        self.assertIs(config.auto_repair_enabled(self.root), False)
        self._assert_refused("malformed JSON policy")

    def test_a_policy_that_is_not_an_object_refuses_the_repair(self):
        self._write_policy(json.dumps(["auto_repair", "true"]))
        self.assertIs(config.auto_repair_enabled(self.root), False)
        self._assert_refused("policy that is not an object")

    def test_a_non_boolean_auto_repair_refuses_the_repair(self):
        for value in ("sim", 1, None, [], {}):
            self._write_policy(json.dumps({"auto_repair": value}))
            self.assertIs(
                config.auto_repair_enabled(self.root),
                False,
                msg="a non-boolean auto_repair (%r) enabled repair" % (value,),
            )
            self._assert_refused("non-boolean auto_repair (%r)" % (value,))

    def test_an_explicit_false_policy_refuses_the_repair(self):
        self._write_policy(json.dumps({"auto_repair": False}))
        self.assertIs(config.auto_repair_enabled(self.root), False)
        self._assert_refused("explicit false policy")

    def test_an_explicit_true_policy_permits_the_repair(self):
        """The only thing that enables the capability."""
        self._write_policy(json.dumps({"auto_repair": True}))
        self.assertIs(config.auto_repair_enabled(self.root), True)
        target = self.root / "consequence_map" / "_probe.py"
        self.assertTrue(repair.write_file_text(target, "x = 1\n", root=self.root))
        self.assertTrue(target.exists())

    def test_the_permission_is_scoped_to_its_own_root(self):
        """A policy in one root does not enable repair in another."""
        self._write_policy(json.dumps({"auto_repair": True}))
        other = Path(self.directory) / "other-project"
        (other / "quality_guardian" / "state").mkdir(parents=True)
        (other / "consequence_map").mkdir()
        self.assertIs(config.auto_repair_enabled(self.root), True)
        self.assertIs(config.auto_repair_enabled(other), False)
        target = other / "consequence_map" / "_probe.py"
        with self.assertRaises(repair.RepairSuspended):
            repair.write_file_text(target, "x = 1\n", root=other)
        self.assertFalse(target.exists())

    def test_the_production_policy_is_not_consulted_for_an_isolated_root(self):
        """A root without a policy does not inherit the production one.

        The production policy says suspended. A root with no policy of
        its own must also be suspended - and must not be able to reach
        the production tree.
        """
        self.assertIs(config.auto_repair_enabled(), False)
        self.assertIs(config.auto_repair_enabled(self.root), False)


class ProductionPolicyIsIntact(unittest.TestCase):
    """The production policy is the owner's decision and stays as it is."""

    def test_the_production_policy_still_suspends_repair(self):
        policy_file = config.PROJECT_ROOT / "quality_guardian" / "state" / "repair-policy.json"
        self.assertTrue(policy_file.exists(), "the production policy file is missing")
        data = json.loads(policy_file.read_text(encoding="utf-8"))
        self.assertIs(data["auto_repair"], False)


if __name__ == "__main__":
    unittest.main()
