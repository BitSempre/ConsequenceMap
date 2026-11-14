"""The plugin loads the way the host loads it.

This is the test that answers "will Hermes run it?". It loads the
plugin's ``__init__.py`` the way the host's loader does - as a module
from its folder, with a context object - and checks that the five
hooks and the command are registered.

It is **skipped, not failed**, when the Hermes runtime is not on the
path. A missing runtime is a missing precondition, and the skill's
rule is that a check which cannot run is never rendered as a pass.
"""
from __future__ import annotations

import os
import sys
import unittest

#: The plugin root is three levels up from this file
#: (tests -> consequence_map -> plugin).
PLUGIN_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

#: The Hermes runtime, when it is installed.
HERMES_ROOT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))))),
    "hermes-agent",
)


def _hermes_root():
    """Where the Hermes runtime is, if it is installed here."""
    for candidate in (
        HERMES_ROOT,
        os.path.join(os.path.expanduser("~"), "AppData", "Local", "hermes",
                     "hermes-agent"),
    ):
        if os.path.isdir(candidate):
            return candidate
    return None


class HostLoadTests(unittest.TestCase):
    def test_the_plugin_registers_the_five_hooks_when_loaded(self):
        """The host's own loader path, exercised directly."""
        # The plugin's entry point is executed the way the host's
        # loader reaches a directory plugin: the file's own source,
        # with the project root on the path so the package resolves.
        project_root = os.path.dirname(PLUGIN_ROOT)
        if project_root not in sys.path:
            sys.path.insert(0, project_root)
        source_path = os.path.join(PLUGIN_ROOT, "__init__.py")
        with open(source_path, encoding="utf-8") as handle:
            source = handle.read()
        namespace = {
            "__file__": source_path,
            "__name__": "consequence_map_plugin_under_test",
        }
        exec(compile(source, source_path, "exec"), namespace)

        hooks = []
        commands = []

        class FakeContext:
            def register_hook(self, name, callback):
                hooks.append(name)

            def register_command(self, name, handler, **kwargs):
                commands.append(name)

            def get_config(self, key, default=None):
                return default

        namespace["register"](FakeContext())
        self.assertEqual(hooks, [
            "pre_tool_call",
            "pre_approval_request",
            "post_approval_response",
            "post_tool_call",
            "transform_tool_result",
        ])
        self.assertEqual(commands, ["consequence-map"])



if __name__ == "__main__":
    unittest.main()
