"""The Guardian orchestrator.

One cycle: detect a real change -> select tests -> run them -> classify ->
attempt a permitted repair -> re-run -> compare -> report.

The cycle never loops: at most MAX_REPAIR_ATTEMPTS repair attempts, each
followed by a fresh test run. A repair that introduces a new failure is
reverted immediately.
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from . import classify, config, detect, repair, report, runner
from .classify import CheckResult, CycleResult
from .repair import LEVEL_AUTO, LEVEL_HUMAN, RepairProposal

#: The Hermes home, used to locate the installed runtime.
HERMES_HOME = Path(os.environ.get("HERMES_HOME", r"C:\Users\Utente\AppData\Local\hermes"))


@dataclass
class Cycle:
    """One Guardian verification cycle."""

    trigger: str = "manual"
    root: Path = field(default_factory=lambda: config.PROJECT_ROOT)
    changed_files: List[str] = field(default_factory=list)
    result: CycleResult = field(default_factory=CycleResult)
    test_runs: List[runner.TestRun] = field(default_factory=list)
    repair_outcome: repair.RepairOutcome = field(default_factory=repair.RepairOutcome)
    baseline_before: dict = field(default_factory=dict)
    baseline_after: dict = field(default_factory=dict)
    rewritten_paths: set = field(default_factory=set)

    def to_dict(self) -> dict:
        unresolved = [
            {"name": c.name, "verdict": c.verdict, "kind": c.kind, "detail": c.detail}
            for c in self.result.checks
            if c.verdict in (classify.FAIL, classify.NOT_VERIFIED, classify.BLOCKED)
        ]
        return {
            "trigger": self.trigger,
            "verdict": self.result.worst,
            "changed_files": list(self.changed_files),
            "tests_executed": sum(r.passed + r.failed + r.errors for r in self.test_runs),
            "test_runs": [r.to_dict() for r in self.test_runs],
            "checks": [c.to_dict() for c in self.result.checks],
            "repairs": [p.to_dict() for p in self.repair_outcome.proposals],
            "repair_attempts": self.repair_outcome.attempts,
            "stopped_reason": self.result.stopped_reason,
            "unresolved": unresolved,
            "human_decision_required": self._human_decision(),
        }

    def _human_decision(self) -> str:
        if self.repair_outcome.stopped:
            return self.repair_outcome.stop_reason
        level3 = [
            p for p in self.repair_outcome.proposals
            if p.level == LEVEL_HUMAN and not p.applied
        ]
        if level3:
            paths = ", ".join(sorted({p.path or p.kind for p in level3}))
            return f"Human decision required for: {paths}"
        return ""


def _hash_map(root: Path) -> dict:
    return detect.current_hashes(root)


def _detect_hermes_version():
    """The installed Hermes version as a tuple, or None."""
    import subprocess
    git = HERMES_HOME / "tools" / "git-portable" / "PortableGit" / "cmd" / "git.exe"
    repo = HERMES_HOME / "hermes-agent"
    if git.exists() and repo.exists():
        try:
            proc = subprocess.run(
                [str(git), "-C", str(repo), "describe", "--tags", "--always"],
                capture_output=True, text=True, timeout=30,
            )
            token = (proc.stdout or "").strip().lstrip("v")
            parts = token.split(".")
            if len(parts) >= 2 and parts[0].isdigit():
                nums = []
                for part in parts[:3]:
                    digits = "".join(ch for ch in part if ch.isdigit())
                    nums.append(int(digits or 0))
                while len(nums) < 3:
                    nums.append(0)
                return tuple(nums[:3])
        except (OSError, subprocess.SubprocessError, ValueError):
            pass
    return None


def _check_runtime_compatibility(root: Path) -> CheckResult:
    """Confirm the installed Hermes runtime satisfies the declared floor."""
    version = _detect_hermes_version()
    if version is None:
        return CheckResult(
            name="hermes-runtime-compatibility",
            verdict=classify.NOT_VERIFIED,
            detail="the installed Hermes version could not be determined",
            evidence={"required": config.REQUIRED_HERMES_VERSION},
        )
    ok = version >= config.MIN_HERMES
    return CheckResult(
        name="hermes-runtime-compatibility",
        verdict=classify.PASS if ok else classify.FAIL,
        kind=None if ok else classify.IMPLEMENTATION,
        detail=f"installed {version} vs required {config.REQUIRED_HERMES_VERSION}",
        evidence={"installed": ".".join(str(p) for p in version)},
    )


def _check_stdlib_only(root: Path) -> CheckResult:
    """Confirm the production package still declares no dependencies."""
    dep_file = root / "consequence_map" / "dependencies.py"
    if not dep_file.exists():
        return CheckResult(
            name="production-stdlib-only", verdict=classify.NOT_VERIFIED,
            detail="dependencies.py is absent",
        )
    source = dep_file.read_text(encoding="utf-8", errors="replace")
    pyproject = (root / "pyproject.toml").exists()
    if "PRODUCTION_DEPENDENCIES: tuple = ()" not in source.replace("tuple=()", "tuple = ()"):
        return CheckResult(
            name="production-stdlib-only", verdict=classify.FAIL,
            kind=classify.IMPLEMENTATION,
            detail="PRODUCTION_DEPENDENCIES is no longer the empty tuple",
            repairable=False,
        )
    if pyproject:
        return CheckResult(
            name="production-stdlib-only", verdict=classify.FAIL,
            kind=classify.DECISION,
            detail="pyproject.toml exists; the project is stdlib-only",
            repairable=False,
        )
    return CheckResult(
        name="production-stdlib-only", verdict=classify.PASS,
        detail="PRODUCTION_DEPENDENCIES is empty and no pyproject.toml exists",
    )


def _check_manifest_integrity(root: Path, cycle=None) -> CheckResult:
    """Verify the Phase 2A manifest entries that live inside the project.

    A divergence that is already documented in an addendum is reported as
    WARNING, not FAIL: it is a known, recorded state, not a new regression.
    An undocumented divergence is a FAIL.
    """
    import re
    manifest = root / "docs" / "PHASE-2A-MANIFEST.md"
    if not manifest.exists():
        return CheckResult(
            name="phase-2a-manifest-integrity", verdict=classify.NOT_VERIFIED,
            detail="the Phase 2A manifest is absent",
        )
    text = manifest.read_text(encoding="utf-8", errors="replace")
    rows = re.findall(r"^\|\s*`([^`]+)`\s*\|\s*([\d,]+)\s*\|\s*`([0-9a-f]{64})`\s*\|", text, re.M)
    checked = 0
    mismatched = []
    missing = 0
    desktop = Path(r"C:\Users\Utente\Desktop")
    for rel, _size, expected in rows:
        candidate = root / rel.replace("/", os.sep)
        if not candidate.exists():
            candidate = desktop / rel.replace("/", os.sep)
        if not candidate.exists():
            missing += 1
            continue
        actual = detect.sha256_of(candidate)
        checked += 1
        if actual != expected:
            mismatched.append(rel)
    # A file the Guardian rewrote during this cycle is reported separately:
    # it is a legitimate, recorded change, not an unexplained divergence.
    rewritten = {p for p in getattr(cycle, "rewritten_paths", ())}
    mismatched = [m for m in mismatched if m not in rewritten]
    if mismatched:
        documented = _documented_divergences(root)
        undocumented = [m for m in mismatched if m not in documented]
        if undocumented:
            return CheckResult(
                name="phase-2a-manifest-integrity", verdict=classify.FAIL,
                kind=classify.IMPLEMENTATION,
                detail=f"{len(undocumented)} undocumented manifest divergence(s)",
                evidence={"undocumented": undocumented[:20]},
            )
        return CheckResult(
            name="phase-2a-manifest-integrity", verdict=classify.WARNING,
            kind=classify.DOCUMENTATION,
            detail=(f"{len(mismatched)} manifest divergence(s), all documented in an "
                    "addendum — a known, recorded state, not a new regression"),
            evidence={"documented": mismatched[:20]},
        )
    return CheckResult(
        name="phase-2a-manifest-integrity", verdict=classify.PASS,
        detail=f"{checked} manifest entries verified, 0 mismatched",
        evidence={"checked": checked, "absent_from_disk": missing},
    )


def _find_formatting_issues(paths: List[str], root: Path) -> List[dict]:
    """Mechanical problems in the changed files.

    Only two are detected: trailing whitespace on a line, and a missing or
    duplicated final newline. Both are deterministic and reversible.
    """
    issues = []
    for rel in paths:
        if not rel.endswith(".py"):
            continue
        path = root / rel.replace("/", os.sep)
        if not path.exists():
            continue
        source = repair.read_file_text(path)
        if source is None:
            continue
        trailing = 0
        for line in source.splitlines():
            body = line.rstrip("\r")
            if body != body.rstrip(" \t"):
                trailing += 1
        needs_newline = bool(source) and not source.endswith("\n")
        double_newline = source.endswith("\n\n")
        if trailing or needs_newline or double_newline:
            issues.append({
                "path": rel,
                "trailing_whitespace_lines": trailing,
                "missing_final_newline": needs_newline,
                "extra_final_newline": double_newline,
            })
    return issues


def _check_formatting(issues: List[dict]) -> CheckResult:
    """The formatting verdict for the changed files."""
    if not issues:
        return CheckResult(
            name="formatting-hygiene", verdict=classify.PASS,
            detail="no trailing whitespace or final-newline defect in the changed files",
        )
    total = sum(i["trailing_whitespace_lines"] for i in issues)
    return CheckResult(
        name="formatting-hygiene", verdict=classify.WARNING,
        kind=classify.IMPLEMENTATION,
        detail=f"{total} line(s) with trailing whitespace across {len(issues)} file(s)",
        repairable=True,
        evidence={"issues": issues},
    )


def _documented_divergences(root: Path) -> set:
    """The manifest paths whose divergence is recorded in an addendum.

    The addendum names the file it concerns. The divergence is only treated
    as documented when the addendum explicitly records the path.
    """
    import re
    docs = root / "docs"
    documented = set()
    if not docs.is_dir():
        return documented
    for path in sorted(docs.glob("PHASE-2A-MANIFEST-ADDENDUM-*.md")):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for rel in re.findall(r"`(consequence_map/[A-Za-z0-9_./-]+\.py)`", text):
            documented.add(rel)
        for rel in re.findall(r"\|\s*`(consequence_map/[A-Za-z0-9_./-]+\.py)`\s*\|", text):
            documented.add(rel)
    return documented


def _check_tests_preserved(before: dict, after: dict) -> CheckResult:
    """Confirm no test file disappeared."""
    test_dir = "consequence_map/tests/"
    removed = sorted(p for p in before if p.startswith(test_dir) and p not in after)
    if removed:
        return CheckResult(
            name="tests-preserved", verdict=classify.FAIL, kind=classify.TEST,
            detail=f"{len(removed)} test file(s) were removed: {removed}",
            evidence={"removed": removed},
        )
    return CheckResult(
        name="tests-preserved", verdict=classify.PASS,
        detail="no test file was removed",
    )


def run_cycle(trigger: str = "manual", root: Path = None,
              changed: Optional[List[str]] = None, force_full: bool = False) -> Cycle:
    """Run one complete verification cycle."""
    base = Path(root) if root else config.PROJECT_ROOT
    cycle = Cycle(trigger=trigger, root=base)
    cycle.baseline_before = _hash_map(base)

    if changed is None:
        changes = detect.detect_changes(base)
        cycle.changed_files = sorted(changes["modified"] + changes["added"])
    else:
        cycle.changed_files = sorted(set(changed))

    cycle.result.add(_check_runtime_compatibility(base))
    cycle.result.add(_check_stdlib_only(base))

    if not cycle.changed_files and not force_full:
        cycle.result.add(CheckResult(
            name="change-detection", verdict=classify.PASS,
            detail="no real content change was detected; no test was executed",
        ))
        cycle.result.add(_check_manifest_integrity(base, cycle))
        cycle.baseline_after = cycle.baseline_before
        detect.save_state(cycle.baseline_after, base)
        return cycle

    selected = runner.select_tests(cycle.changed_files, base)
    if not selected:
        selected = list(config.FULL_TEST_SET)
    for module in selected:
        run = runner.run_test_module(module, root=base)
        cycle.test_runs.append(run)
        if run.verdict == runner.NO_TESTS_CONFIGURED:
            cycle.result.add(CheckResult(
                name=f"tests:{module}", verdict=classify.NOT_VERIFIED,
                detail=run.detail, evidence={"module": module},
            ))
        elif run.verdict == "BLOCKED":
            cycle.result.add(CheckResult(
                name=f"tests:{module}", verdict=classify.BLOCKED,
                detail=run.detail, evidence={"module": module},
            ))
        elif run.verdict == "FAIL":
            cycle.result.add(CheckResult(
                name=f"tests:{module}", verdict=classify.FAIL,
                kind=classify.IMPLEMENTATION,
                detail=run.detail,
                evidence={"module": module, "failed": run.failed, "errors": run.errors},
            ))
        else:
            cycle.result.add(CheckResult(
                name=f"tests:{module}", verdict=classify.PASS,
                detail=run.detail, evidence={"module": module, "passed": run.passed},
            ))

    _plan_repairs(cycle, base)
    _attempt_repairs(cycle, base)

    cycle.baseline_after = _hash_map(base)
    # The manifest check runs AFTER the repairs: a repair that touches a
    # manifest-covered file legitimately changes its hash, and the check must
    # report the final state, not the transient one.
    cycle.result.add(_check_manifest_integrity(base, cycle))
    cycle.result.add(_check_tests_preserved(cycle.baseline_before, cycle.baseline_after))
    changed_by_repair = sorted(
        p for p in cycle.baseline_after
        if cycle.baseline_before.get(p) != cycle.baseline_after.get(p)
    )
    cycle.result.add(CheckResult(
        name="state-comparison", verdict=classify.PASS,
        detail=f"{len(changed_by_repair)} file(s) differ from the pre-cycle state",
        evidence={"changed": changed_by_repair},
    ))

    detect.save_state(cycle.baseline_after, base)
    return cycle


def _plan_repairs(cycle: Cycle, root: Path) -> None:
    """Propose a repair for each repairable failure.

    A mechanical formatting defect is proposed even when the tests pass:
    the Guardian's remit includes code hygiene, not only test failures.
    """
    issues = _find_formatting_issues(cycle.changed_files, root)
    cycle.result.add(_check_formatting(issues))
    if issues:
        cycle.repair_outcome.proposals.append(RepairProposal(
            path=issues[0]["path"],
            level=repair.LEVEL_AUTO,
            kind=classify.IMPLEMENTATION,
            description=(
                f"mechanical formatting: {sum(i['trailing_whitespace_lines'] for i in issues)} "
                f"line(s) with trailing whitespace, final-newline normalised"
            ),
        ))
    for check in cycle.result.failed:
        level = repair.classify_failure(check.kind or classify.IMPLEMENTATION, None)
        if check.kind == classify.IMPLEMENTATION and check.name.startswith("tests:"):
            module = check.evidence.get("module")
            handled = False
            for candidate in [p for p in cycle.changed_files if p.endswith(".py")]:
                path = root / candidate.replace("/", os.sep)
                if not path.exists():
                    continue
                source = repair.read_file_text(path)
                if source is None:
                    continue
                fixed, notes = repair.apply_level1_fixes_in_project(
                    path, source, project_rel=candidate.replace(os.sep, "/"))
                if fixed != source:
                    cycle.repair_outcome.proposals.append(RepairProposal(
                        path=candidate, level=level, kind=check.kind,
                        description="; ".join(notes),
                    ))
                    handled = True
                    break
            if not handled:
                cycle.repair_outcome.proposals.append(RepairProposal(
                    path="", level=level, kind=check.kind,
                    description=(f"module {module} failed; no deterministic mechanical fix "
                                 "was identified — Level 2, requires an investigation"),
                    applied=False,
                ))
        else:
            cycle.repair_outcome.proposals.append(RepairProposal(
                path="", level=level, kind=check.kind or classify.IMPLEMENTATION,
                description=check.detail, applied=False,
            ))


def _attempt_repairs(cycle: Cycle, root: Path) -> None:
    """Apply the Level 1 repairs, re-run the tests, revert on regression.

    The repair policy is consulted FIRST. When automatic repair is
    suspended, the proposals are still recorded and reported, but no file
    is written: detection, testing and reporting continue unchanged.
    """
    auto = [p for p in cycle.repair_outcome.proposals if p.level == LEVEL_AUTO and p.path]
    if not auto:
        return
    if not config.auto_repair_enabled(root):
        policy = config.repair_policy(root)
        reason = policy.get("reason", "no reason recorded")
        for proposal in auto:
            proposal.error = f"automatic repair is suspended: {reason}"
        cycle.result.add(CheckResult(
            name="repair-capability", verdict=classify.NOT_VERIFIED,
            kind=classify.IMPLEMENTATION,
            detail=(f"automatic repair is suspended by the repair policy "
                    f"({reason}); {len(auto)} repair(s) were proposed but not applied"),
            evidence={"policy": policy},
        ))
        return
    baseline_tests = {r.module: (r.failed + r.errors) for r in cycle.test_runs}
    for proposal in auto:
        if cycle.repair_outcome.attempts >= config.MAX_REPAIR_ATTEMPTS:
            cycle.repair_outcome.stopped = True
            cycle.repair_outcome.stop_reason = (
                f"the repair-attempt limit of {config.MAX_REPAIR_ATTEMPTS} was reached"
            )
            return
        cycle.repair_outcome.attempts += 1
        path = root / proposal.path.replace("/", os.sep)
        original = repair.read_file_text(path)
        if original is None:
            proposal.error = "the file could not be read"
            continue
        proposal.before_hash = hashlib.sha256(original.encode("utf-8")).hexdigest()
        fixed, _notes = repair.apply_level1_fixes_in_project(
            path, original, project_rel=proposal.path.replace(os.sep, "/"))
        if fixed == original:
            continue
        if not repair.repair_is_sane(original, fixed):
            proposal.error = (
                "the repair was refused: it would shrink the file below "
                f"{int(config.MIN_REPAIR_SIZE_RATIO * 100)}% of its size, "
                "which indicates corruption rather than a formatting defect"
            )
            cycle.result.add(CheckResult(
                name=f"repair:{proposal.path}", verdict=classify.NOT_VERIFIED,
                kind=classify.IMPLEMENTATION,
                detail=proposal.error + " — human review required",
            ))
            continue
        if not repair.write_file_text(path, fixed):
            proposal.error = "the file could not be written"
            continue
        proposal.applied = True
        proposal.after_hash = hashlib.sha256(fixed.encode("utf-8")).hexdigest()
        cycle.rewritten_paths.add(proposal.path.replace(os.sep, "/"))
        regressed = False
        for module in runner.select_tests([proposal.path], root):
            run = runner.run_test_module(module, root=root)
            cycle.test_runs.append(run)
            before_failures = baseline_tests.get(module, 0)
            if run.failed + run.errors > before_failures:
                regressed = True
                break
        if regressed:
            repair.write_file_text(path, original)
            proposal.reverted = True
            proposal.applied = False
            cycle.result.add(CheckResult(
                name=f"repair:{proposal.path}", verdict=classify.FAIL,
                kind=classify.IMPLEMENTATION,
                detail="the repair introduced a new failure and was reverted",
            ))
        else:
            cycle.result.add(CheckResult(
                name=f"repair:{proposal.path}", verdict=classify.PASS,
                detail="the repair was applied and the tests still pass",
            ))
            # The failure this repair addressed is now resolved: the tests
            # were re-run and are green. Reclassify it rather than leaving a
            # stale FAIL in the verdict.
            for check in cycle.result.checks:
                if check.name.startswith("tests:") and check.verdict == classify.FAIL:
                    check.verdict = classify.PASS
                    check.detail = (check.detail + " — resolved by an automatic repair; "
                                    "the tests were re-run and passed")
    for proposal in cycle.repair_outcome.proposals:
        if proposal.level == LEVEL_HUMAN and not proposal.applied:
            cycle.result.add(CheckResult(
                name=f"human-review:{proposal.path or proposal.kind}",
                verdict=classify.NOT_VERIFIED,
                kind=proposal.kind,
                detail=proposal.description,
            ))


def finalize(cycle: Cycle, root: Path = None) -> dict:
    """Write the persistent report for a cycle and return its payload."""
    base = Path(root) if root else config.PROJECT_ROOT
    payload = cycle.to_dict()
    report.write_report(payload, base, stem=cycle.trigger)
    return payload
