"""Test execution.

The project uses stdlib ``unittest``; the Guardian uses it too and adds no
dependency. A module with no configured tests yields NO_TESTS_CONFIGURED,
never PASS.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from . import config

#: The marker the Guardian reports when a module has no tests at all.
NO_TESTS_CONFIGURED = "NO_TESTS_CONFIGURED"


@dataclass
class TestRun:
    """One executed test module."""

    module: str
    passed: int = 0
    failed: int = 0
    errors: int = 0
    skipped: int = 0
    duration: float = 0.0
    timed_out: bool = False
    output: str = ""
    verdict: str = "PASS"
    detail: str = ""

    def to_dict(self) -> dict:
        return {
            "module": self.module,
            "passed": self.passed,
            "failed": self.failed,
            "errors": self.errors,
            "skipped": self.skipped,
            "duration": round(self.duration, 3),
            "timed_out": self.timed_out,
            "verdict": self.verdict,
            "detail": self.detail,
        }


def _parse_counts(stderr: str) -> dict:
    """Extract the per-test counts from unittest's stderr summary.

    The full-suite run concatenates the output of TWO processes, so the
    text can carry more than one "Ran N tests" summary. Every summary
    present is summed, not just the first: taking only the first would
    report the plugin's count while the guard's 134 tests ran unseen,
    and would miss a failure in the second package.
    """
    counts = {"passed": 0, "failed": 0, "errors": 0, "skipped": 0}
    ran = re.findall(r"Ran (\d+) tests?", stderr)
    if ran:
        counts["passed"] = sum(int(n) for n in ran)
    for label, key in (("failures", "failed"), ("errors", "errors")):
        found = re.findall(rf"{label}=(\d+)", stderr)
        if found:
            counts[key] = sum(int(n) for n in found)
    found = re.findall(r"skipped=(\d+)", stderr)
    if found:
        counts["skipped"] = sum(int(n) for n in found)
    return counts


def _module_address(module: str, root: Path = None) -> str:
    """The dotted address of a test module.

    The project has TWO test packages: ``consequence_map.tests`` and
    ``consequence_guard.tests``. A module name is not enough to say
    which one holds it, so the package that actually contains the file
    wins. The name alone would address the wrong package - or no
    package at all, and the run would report a module that does not
    exist.
    """
    base = Path(root) if root else config.PROJECT_ROOT
    for package in ("consequence_map", "consequence_guard"):
        if (base / package / "tests" / (module + ".py")).exists():
            return f"{package}.tests.{module}"
    return f"consequence_map.tests.{module}"


def run_test_module(module: str, timeout: int = None, root: Path = None) -> TestRun:
    """Run one test module of the project suite.

    The module is addressed in whichever test package actually holds it -
    ``consequence_map.tests.<module>`` or ``consequence_guard.tests.<module>`` -
    and the run happens with the project root as the working directory,
    exactly as the Phase 2A suite is run.
    """
    base = Path(root) if root else config.PROJECT_ROOT
    limit = timeout if timeout is not None else config.SELECTIVE_TEST_TIMEOUT
    run = TestRun(module=module)
    started = time.monotonic()
    env = dict(os.environ)
    env["PYTHONPATH"] = str(base) + os.pathsep + env.get("PYTHONPATH", "")
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "unittest", _module_address(module, base), "-v"],
            capture_output=True, text=True, timeout=limit, cwd=str(base), env=env,
        )
    except subprocess.TimeoutExpired as exc:
        run.timed_out = True
        run.duration = time.monotonic() - started
        run.verdict = "BLOCKED"
        run.detail = f"timed out after {limit}s"
        run.output = ((exc.stdout or "") if isinstance(exc.stdout, str) else "")[-4000:]
        return run
    run.duration = time.monotonic() - started
    stderr = proc.stderr or ""
    counts = _parse_counts(stderr)
    run.passed = max(0, counts["passed"] - counts["failed"] - counts["errors"] - counts["skipped"])
    run.failed = counts["failed"]
    run.errors = counts["errors"]
    run.skipped = counts["skipped"]
    run.output = stderr[-6000:]
    if run.failed or run.errors:
        run.verdict = "FAIL"
        run.detail = f"{run.failed} failure(s), {run.errors} error(s)"
    elif counts["passed"] == 0:
        # A module that exists but ran nothing is NOT a pass.
        run.verdict = NO_TESTS_CONFIGURED
        run.detail = "module produced no test cases"
    else:
        run.verdict = "PASS"
        run.detail = f"{run.passed} test(s) passed"
    return run


def select_tests(changed: List[str], root: Path = None) -> List[str]:
    """Choose the test modules to run for a set of changed project paths.

    The mapping is the module-to-test table in config, derived from the
    package's real import graph. A change to a test file runs that test
    module. A change to a high-impact module forces the full set.
    """
    base = Path(root) if root else config.PROJECT_ROOT
    modules = set()
    high_impact = False
    for rel in changed:
        if rel.startswith("consequence_map/tests/"):
            name = rel.rsplit("/", 1)[-1]
            if name.startswith("test_") and name.endswith(".py"):
                modules.add(name[:-3])
            continue
        dotted = config.module_for_path(base / rel)
        if not dotted:
            continue
        if dotted in config.HIGH_IMPACT_MODULES:
            high_impact = True
        for test_module in config.MODULE_TO_TESTS.get(dotted, []):
            modules.add(test_module)
    if high_impact:
        return list(config.FULL_TEST_SET)
    modules.update(config.ALWAYS_RUN_TESTS)
    ordered = [m for m in config.FULL_TEST_SET if m in modules]
    return ordered


def run_full_suite(root: Path = None, timeout: int = None) -> TestRun:
    """Run the whole project suite in one process."""
    base = Path(root) if root else config.PROJECT_ROOT
    limit = timeout if timeout is not None else config.FULL_TEST_TIMEOUT
    run = TestRun(module="FULL_SUITE")
    started = time.monotonic()
    env = dict(os.environ)
    env["PYTHONPATH"] = str(base) + os.pathsep + env.get("PYTHONPATH", "")
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "unittest", "discover",
             "-s", str(base / "consequence_map" / "tests"), "-t", str(base), "-v"],
            capture_output=True, text=True, timeout=limit, cwd=str(base), env=env,
        )
        # The guard's own tests live in a SECOND package. A discover on
        # consequence_map/tests cannot see them, so the full run has to
        # cover both or the security suite is simply never executed.
        try:
            proc2 = subprocess.run(
                [sys.executable, "-m", "unittest", "discover",
                 "-s", str(base / "consequence_guard" / "tests"), "-t", str(base), "-v"],
                capture_output=True, text=True, timeout=limit, cwd=str(base), env=env,
            )
        except subprocess.TimeoutExpired as exc:
            proc2 = subprocess.CompletedProcess(
                proc.args, 1, proc.stdout or "",
                (proc.stderr or "") + "\nGUARD PACKAGE TIMED OUT after %ss" % (limit,),
            )
        proc = subprocess.CompletedProcess(
            proc.args, proc.returncode or proc2.returncode,
            (proc.stdout or "") + (proc2.stdout or ""),
            (proc.stderr or "") + (proc2.stderr or ""),
        )
    except subprocess.TimeoutExpired as exc:
        run.timed_out = True
        run.duration = time.monotonic() - started
        run.verdict = "BLOCKED"
        run.detail = f"full suite timed out after {limit}s"
        return run
    run.duration = time.monotonic() - started
    stderr = proc.stderr or ""
    counts = _parse_counts(stderr)
    run.passed = max(0, counts["passed"] - counts["failed"] - counts["errors"] - counts["skipped"])
    run.failed = counts["failed"]
    run.errors = counts["errors"]
    run.skipped = counts["skipped"]
    run.output = stderr[-8000:]
    if run.failed or run.errors:
        run.verdict = "FAIL"
        run.detail = f"{run.failed} failure(s), {run.errors} error(s)"
    elif run.passed == 0:
        run.verdict = NO_TESTS_CONFIGURED
        run.detail = "the full suite produced no test cases"
    else:
        run.verdict = "PASS"
        run.detail = f"{run.passed} test(s) passed"
    return run
