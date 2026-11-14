"""The layered import rule (MC1/R01).

domain/         - no Hermes import
storage/db.py   - exactly one Hermes import, inside a function body
storage/ (rest) - no Hermes import
tests/          - no Hermes import, no network import
whole package   - no socket/http/urllib
"""
from __future__ import annotations

import ast
import os
import unittest

PACKAGE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: The Hermes module roots.
HERMES_ROOTS = ("hermes_cli", "hermes_state_wal", "plugins", "agent", "tools", "apps")

#: The network-capable modules the package must not import.
NETWORK_MODULES = ("socket", "http", "urllib", "requests", "httpx", "aiohttp")


def python_files(subdir=None):
    root = os.path.join(PACKAGE, subdir) if subdir else PACKAGE
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for name in sorted(files):
            if name.endswith(".py"):
                yield os.path.join(base, name)


def imported_modules(path):
    """Every module name imported by the file at `path`."""
    with open(path, encoding="utf-8") as handle:
        tree = ast.parse(handle.read(), filename=path)
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                names.append("." * node.level + (node.module or ""))
            elif node.module:
                names.append(node.module)
    return names


def top_level(name):
    return name.lstrip(".").split(".")[0]


class TestDomainPurity(unittest.TestCase):
    def test_the_domain_imports_no_hermes_module(self):
        for path in python_files("domain"):
            with self.subTest(file=os.path.basename(path)):
                for name in imported_modules(path):
                    self.assertNotIn(top_level(name), HERMES_ROOTS,
                                     f"{path} imports {name}")

    def test_the_domain_imports_only_the_standard_library_and_its_own_package(self):
        allowed = {
            "dataclasses", "datetime", "enum", "json", "os", "pathlib", "re",
            "sqlite3", "typing", "hashlib", "contextlib", "tempfile", "abc",
            "collections", "functools", "itertools", "textwrap", "unittest",
            "shutil", "sys", "inspect", "ast", "__future__", "enum",
        }
        for path in python_files("domain"):
            with self.subTest(file=os.path.basename(path)):
                for name in imported_modules(path):
                    if name.startswith("."):
                        continue
                    root = top_level(name)
                    self.assertTrue(
                        root in allowed or root == "consequence_map",
                        f"{path} imports {name}, which is neither stdlib nor the package",
                    )


class TestStoragePurity(unittest.TestCase):
    def test_only_storage_db_imports_a_hermes_module(self):
        offenders = []
        for path in python_files("storage"):
            for name in imported_modules(path):
                if top_level(name) in HERMES_ROOTS:
                    if os.path.basename(path) != "db.py":
                        offenders.append(f"{path} imports {name}")
        self.assertEqual(offenders, [])

    def test_the_seam_import_is_inside_a_function_body(self):
        path = os.path.join(PACKAGE, "storage", "db.py")
        with open(path, encoding="utf-8") as handle:
            tree = ast.parse(handle.read(), filename=path)
        module_level_hermes = []
        for node in tree.body:
            if isinstance(node, ast.Import):
                module_level_hermes.extend(a.name for a in node.names
                                           if top_level(a.name) in HERMES_ROOTS)
            elif isinstance(node, ast.ImportFrom) and node.module:
                if top_level(node.module) in HERMES_ROOTS:
                    module_level_hermes.append(node.module)
        self.assertEqual(module_level_hermes, [],
                         "the Hermes import must be inside a function body")

    def test_the_seam_import_is_exactly_the_plugin_storage(self):
        path = os.path.join(PACKAGE, "storage", "db.py")
        with open(path, encoding="utf-8") as handle:
            source = handle.read()
        hermes_imports = [line.strip() for line in source.split(chr(10))
                          if ("from plugins" in line or "from hermes" in line
                              or "from agent" in line)]
        self.assertEqual(len(hermes_imports), 2,
                         "exactly two Hermes import sites: the home helper and plugin_db")
        self.assertTrue(any("plugins.plugin_storage" in line for line in hermes_imports))
        self.assertTrue(any("hermes_cli.config" in line for line in hermes_imports))


class TestTestHermeticity(unittest.TestCase):
    def test_the_tests_import_no_hermes_module(self):
        for path in python_files("tests"):
            with self.subTest(file=os.path.basename(path)):
                for name in imported_modules(path):
                    self.assertNotIn(top_level(name), HERMES_ROOTS,
                                     f"{path} imports {name}")

    def test_the_tests_import_no_network_module(self):
        for path in python_files("tests"):
            with self.subTest(file=os.path.basename(path)):
                for name in imported_modules(path):
                    self.assertNotIn(top_level(name), NETWORK_MODULES,
                                     f"{path} imports {name}")


class TestNoEgress(unittest.TestCase):
    def test_no_module_imports_a_network_capable_module(self):
        offenders = []
        for path in python_files():
            for name in imported_modules(path):
                if top_level(name) in NETWORK_MODULES:
                    offenders.append(f"{path} imports {name}")
        self.assertEqual(offenders, [])

    def test_no_module_uses_subprocess_or_shell(self):
        offenders = []
        for path in python_files():
            if os.path.basename(path).startswith("test_"):
                continue
            with open(path, encoding="utf-8") as handle:
                source = handle.read()
            for needle in ("subprocess", "os.system", "os.popen", "shell=True"):
                if needle in source:
                    offenders.append(f"{path} mentions {needle}")
        self.assertEqual(offenders, [])

    def test_no_module_opens_a_network_socket(self):
        offenders = []
        for path in python_files():
            if os.path.abspath(path) == os.path.abspath(__file__):
                # This test file names the calls it searches for.
                continue
            with open(path, encoding="utf-8") as handle:
                source = handle.read()
            for needle in ("socket.socket", "urllib.request", "http.client"):
                if needle in source:
                    offenders.append(f"{path} mentions {needle}")
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
