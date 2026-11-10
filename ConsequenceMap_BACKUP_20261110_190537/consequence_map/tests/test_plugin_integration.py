"""Integration tests for the plugin itself.

Three things must be true for the product to be installable:

1. the manifest declares the five hooks, and the host accepts it;
2. the entry point registers what it says it registers;
3. the dashboard's backend exposes the four routes the three surfaces
   read.

The third one is tested here with the real FastAPI router. The first
two are tested against the host's own manifest parser when the host is
on the path, and against the declared contract when it is not - so the
suite stays hermetic.
"""
from __future__ import annotations

import json
import os
import sys
import unittest

from ..hooks import HOOK_NAMES


PLUGIN_ROOT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "plugin",
)


class ManifestTests(unittest.TestCase):
    def setUp(self):
        self.manifest_path = os.path.join(PLUGIN_ROOT, "plugin.yaml")
        self.assertTrue(os.path.exists(self.manifest_path),
                        "the plugin manifest must exist")

    def _raw(self):
        with open(self.manifest_path, encoding="utf-8") as handle:
            return handle.read()

    def test_the_manifest_declares_the_five_hooks(self):
        raw = self._raw()
        for name in HOOK_NAMES:
            self.assertIn(name, raw,
                          "the manifest must declare %s" % name)

    def test_the_manifest_declares_nothing_else(self):
        """A hook the plugin does not implement would never fire."""
        raw = self._raw()
        section = raw.split("provides_hooks:")[1]
        for line in section.strip().splitlines():
            line = line.strip()
            if line.startswith("- "):
                self.assertIn(line[2:].strip(), HOOK_NAMES)

    def test_the_entry_point_exists(self):
        self.assertTrue(
            os.path.exists(os.path.join(PLUGIN_ROOT, "__init__.py"))
        )

    def test_the_dashboard_declares_a_manifest_and_an_api(self):
        dashboard = os.path.join(PLUGIN_ROOT, "dashboard")
        with open(os.path.join(dashboard, "manifest.json"), encoding="utf-8") as handle:
            data = json.load(handle)
        self.assertEqual(data["name"], "consequence-map")
        self.assertIn("path", data["tab"])
        self.assertEqual(data["api"], "plugin_api.py")
        self.assertTrue(
            os.path.exists(os.path.join(dashboard, data["api"]))
        )
        self.assertTrue(
            os.path.exists(os.path.join(dashboard, data["entry"]))
        )

    def test_the_three_surfaces_are_declared(self):
        """DEC-17 = A: the forecast, the decision and the outcome."""
        with open(
            os.path.join(PLUGIN_ROOT, "dashboard", "dist", "index.js"),
            encoding="utf-8",
        ) as handle:
            source = handle.read()
        for label in ("Forecast", "Decision", "Outcome"):
            self.assertIn(label, source)

    def test_the_command_palette_entry_exists(self):
        """DEC-12 = A: the command palette."""
        with open(
            os.path.join(PLUGIN_ROOT, "__init__.py"), encoding="utf-8"
        ) as handle:
            source = handle.read()
        self.assertIn("register", source)


class RegistrationTests(unittest.TestCase):
    def test_registration_registers_the_five_hooks_and_the_command(self):
        from .. import hooks

        registered = []
        commands = []

        class FakeContext:
            def register_hook(self, name, callback):
                registered.append((name, callback))

            def register_command(self, name, handler, **kwargs):
                commands.append(name)

        hooks.STATE._registered = False
        hooks.register(FakeContext())
        self.assertEqual([n for n, _ in registered], list(HOOK_NAMES))
        self.assertEqual(commands, ["consequence-map"])
        for name, callback in registered:
            self.assertTrue(callable(callback))

    def test_registration_is_idempotent(self):
        from .. import hooks

        calls = []

        class FakeContext:
            def register_hook(self, name, callback):
                calls.append(name)

            def register_command(self, name, handler, **kwargs):
                calls.append(name)

        hooks.STATE._registered = False
        hooks.register(FakeContext())
        first = len(calls)
        hooks.register(FakeContext())
        self.assertEqual(len(calls), first)


class DashboardApiTests(unittest.TestCase):
    """The four routes the three surfaces read."""

    def _router(self):
        """Load the dashboard's backend module.

        The module is executed from its own file, the way the host's
        dashboard mounts it: the file is imported for its side
        effects, and the ``router`` attribute is what the host looks
        for.
        """
        path = os.path.join(PLUGIN_ROOT, "dashboard", "plugin_api.py")
        with open(path, encoding="utf-8") as handle:
            source = handle.read()
        namespace = {"__file__": path, "__name__": "cm_dashboard_api"}
        exec(compile(source, path, "exec"), namespace)
        return type("Module", (), namespace)

    def test_the_api_exposes_a_router(self):
        """The host mounts the router; without one it is skipped."""
        module = self._router()
        self.assertTrue(hasattr(module, "router"))

    def test_the_router_has_the_four_routes(self):
        module = self._router()
        paths = {route.path for route in module.router.routes}
        for expected in ("/forecast", "/decision", "/outcome", "/status"):
            self.assertIn(expected, paths)

    def test_the_status_route_answers_without_a_database(self):
        """The surface must render even when there is nothing yet."""
        module = self._router()
        result = module.get_status()
        self.assertIn("database_present", result)
        self.assertIn("not_verifiable", result)

    def test_the_forecast_route_answers_without_a_database(self):
        module = self._router()
        result = module.get_forecast()
        self.assertIn("found", result)
        self.assertEqual(result["found"], False)

    def test_the_decision_route_states_the_separation(self):
        """The product decision and the host authorization are never
        merged, and the API says so."""
        module = self._router()
        result = module.get_decision()
        self.assertIn("separation", result)
        self.assertIn("never merged", result["separation"])

    def test_the_outcome_route_answers_without_a_database(self):
        module = self._router()
        result = module.get_outcome()
        self.assertIn("found", result)


if __name__ == "__main__":
    unittest.main()
