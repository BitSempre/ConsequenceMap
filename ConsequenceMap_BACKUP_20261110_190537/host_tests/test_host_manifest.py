"""The Hermes runtime accepts the plugin's manifest.

This test lives **outside** the ``consequence_map`` package on
purpose: it imports the host's own manifest parser, and the package's
import audit requires the package's tests never to import a host
module.

A missing runtime is a missing precondition, not a failure: the test
is skipped, never reported as a pass.
"""
from __future__ import annotations

import os
import sys
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN_ROOT = os.path.join(PROJECT_ROOT, "plugin")


def _hermes_root():
    """Where the Hermes runtime is, if it is installed here."""
    home = os.path.expanduser("~")
    candidates = [
        os.path.join(
            home, "AppData", "Local", "hermes", "hermes-agent"
        ),
    ]
    for candidate in candidates:
        if os.path.isdir(candidate):
            return candidate
    return None


class HostManifestTests(unittest.TestCase):
    def test_the_host_parses_the_plugin_manifest(self):
        root = _hermes_root()
        if root is None:
            self.skipTest("the Hermes runtime is not installed on this host")
        if root not in sys.path:
            sys.path.insert(0, root)
        try:
            from pathlib import Path

            from hermes_cli.plugins_manifest import parse_manifest_file

            manifest = parse_manifest_file(
                Path(PLUGIN_ROOT) / "plugin.yaml",
                Path(PLUGIN_ROOT),
                "user",
                "consequence-map",
            )
        except ImportError:
            self.skipTest("the Hermes runtime is not importable here")
        finally:
            if root in sys.path:
                sys.path.remove(root)

        self.assertIsNotNone(manifest, "the host must parse the manifest")
        self.assertEqual(manifest.name, "consequence-map")
        self.assertEqual(len(manifest.provides_hooks), 5)
        for hook in (
            "pre_tool_call",
            "pre_approval_request",
            "post_approval_response",
            "post_tool_call",
            "transform_tool_result",
        ):
            self.assertIn(hook, manifest.provides_hooks)

    def test_the_manifest_names_a_hook_the_plugin_does_not_register(self):
        """A hook the manifest declares but the plugin does not
        register would never fire."""
        root = _hermes_root()
        if root is None:
            self.skipTest("the Hermes runtime is not installed on this host")
        if root not in sys.path:
            sys.path.insert(0, root)
        try:
            from pathlib import Path

            from hermes_cli.plugins_manifest import parse_manifest_file
        except ImportError:
            self.skipTest("the Hermes runtime is not importable here")
        finally:
            if root in sys.path:
                sys.path.remove(root)

        manifest = parse_manifest_file(
            Path(PLUGIN_ROOT) / "plugin.yaml",
            Path(PLUGIN_ROOT),
            "user",
            "consequence-map",
        )
        project_root = PROJECT_ROOT
        if project_root not in sys.path:
            sys.path.insert(0, project_root)
        from consequence_map.hooks import HOOK_NAMES

        self.assertEqual(sorted(manifest.provides_hooks), sorted(HOOK_NAMES))


if __name__ == "__main__":
    unittest.main()
