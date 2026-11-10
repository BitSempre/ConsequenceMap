"""The isolated test environment for the Guardian's own tests.

Every test that exercises a repair runs against a COPY of the project in a
temporary directory. The production tree is never modified by a test.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path


def make_isolated_project() -> Path:
    """A minimal, self-contained project tree for Guardian tests.

    It mirrors the shape the Guardian depends on — a package with a tests
    directory, a dependency inventory and a manifest — so the detection,
    selection and repair logic runs against something real without
    touching the production tree.
    """
    root = Path(tempfile.mkdtemp(prefix="cm-guardian-test-"))
    pkg = root / "consequence_map"
    tests = pkg / "tests"
    tests.mkdir(parents=True)
    (pkg / "__init__.py").write_text('"""A test package."""\n', encoding="utf-8")
    (pkg / "dependencies.py").write_text(
        '"""The dependency inventory."""\n'
        "PRODUCTION_DEPENDENCIES: tuple = ()\n"
        "PYTHON_DEPENDENCIES: list = []\n",
        encoding="utf-8",
    )
    (pkg / "sample.py").write_text(
        '"""A module under test."""\n\n\n'
        "def add(left, right):\n"
        '    """Add two numbers."""\n'
        "    return left + right\n",
        encoding="utf-8",
    )
    (tests / "__init__.py").write_text("", encoding="utf-8")
    (tests / "test_sample.py").write_text(
        "import unittest\n\n"
        "from consequence_map.sample import add\n\n\n"
        "class AddTest(unittest.TestCase):\n"
        "    def test_add(self):\n"
        "        self.assertEqual(add(2, 3), 5)\n",
        encoding="utf-8",
    )
    # The isolated project carries an EXPLICIT repair policy. Without one,
    # an absent policy resolves to "repair suspended" — the safe default —
    # and the tests that exercise the repair path could not run. The
    # permission is granted HERE, in the disposable copy only; the
    # production policy is never touched by a test.
    state = root / "quality_guardian" / "state"
    state.mkdir(parents=True)
    (state / "repair-policy.json").write_text(
        json.dumps({"auto_repair": True, "source": "isolated-test-project"},
                   indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    docs = root / "docs"
    docs.mkdir()
    (docs / "PHASE-2A-MANIFEST.md").write_text(
        "# Manifest\n\n| File | Bytes | SHA-256 |\n|---|---|---|\n",
        encoding="utf-8",
    )
    return root


class IsolatedProjectTestCase(unittest.TestCase):
    """Base class that gives each test its own disposable project copy."""

    def setUp(self):
        self.root = make_isolated_project()
        self.addCleanup(shutil.rmtree, self.root, True)
