"""Controlled auto-repair, in three levels.

Level 1 - automatic: deterministic, reversible, mechanical fixes.
Level 2 - assisted: the Guardian proposes; a human or the agent applies.
Level 3 - human only: the Guardian stops and reports.

The ineligible set is not a policy knob: a request to repair an ineligible
kind is refused in code, regardless of configuration.
"""
from __future__ import annotations

import ast
import io
import os
import re
import tokenize
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

from . import config
from .classify import DECISION, DOCUMENTATION, IMPLEMENTATION, NORMATIVE, TEST

#: Repair levels.
LEVEL_AUTO = 1
LEVEL_ASSISTED = 2
LEVEL_HUMAN = 3

#: The kinds a repair may never touch. TEST is here because a failing test
#: is evidence about the specification, not a defect to be edited away.
INELIGIBLE_KINDS = frozenset({NORMATIVE, DECISION, TEST})


@dataclass
class RepairProposal:
    """One proposed or applied repair."""

    path: str
    level: int
    kind: str
    description: str
    applied: bool = False
    before_hash: str = ""
    after_hash: str = ""
    reverted: bool = False
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "level": self.level,
            "kind": self.kind,
            "description": self.description,
            "applied": self.applied,
            "before_hash": self.before_hash,
            "after_hash": self.after_hash,
            "reverted": self.reverted,
            "error": self.error,
        }


@dataclass
class RepairOutcome:
    """What the repair stage did in one cycle."""

    proposals: List[RepairProposal] = field(default_factory=list)
    attempts: int = 0
    stopped: bool = False
    stop_reason: str = ""

    def to_dict(self) -> dict:
        return {
            "attempts": self.attempts,
            "stopped": self.stopped,
            "stop_reason": self.stop_reason,
            "proposals": [p.to_dict() for p in self.proposals],
        }


def classify_failure(kind: str, path: Optional[str] = None) -> int:
    """The repair level a failure of this kind and location permits.

    Level 1 only for a deterministic, reversible, mechanical defect in a
    file that is not a protected product surface. Everything else is
    Level 2 or Level 3.
    """
    if kind in INELIGIBLE_KINDS:
        return LEVEL_HUMAN if kind in (NORMATIVE, DECISION) else LEVEL_ASSISTED
    if path and config.is_protected(path):
        return LEVEL_HUMAN
    return LEVEL_AUTO


def _split_line_ending(line: str) -> Tuple[str, str]:
    """Split a line into (body, line-ending)."""
    for ending in ("\r\n", "\n", "\r"):
        if line.endswith(ending):
            return line[: -len(ending)], ending
    return line, ""


def _strip_trailing_whitespace(source: str) -> Tuple[str, int]:
    """Remove trailing whitespace on each line. Returns (new, count).

    The line ending is split off first: stripping a whole line would also
    remove the newline, and the removed characters would then be re-appended
    unchanged.
    """
    lines = source.splitlines(keepends=True)
    changed = 0
    out = []
    for line in lines:
        body, ending = _split_line_ending(line)
        stripped = body.rstrip(" \t")
        if stripped != body:
            changed += 1
        out.append(stripped + ending)
    return "".join(out), changed


def _ensure_final_newline(source: str) -> Tuple[str, int]:
    """Ensure the file ends with exactly one newline."""
    if not source:
        return source, 0
    stripped = source.rstrip("\n")
    if stripped == source:
        return source + "\n", 1
    if source.endswith("\n"):
        return stripped + "\n", 1
    return source + "\n", 1


def find_unused_imports(source: str) -> List[str]:
    """Names imported but never referenced in the module.

    A conservative syntactic analysis: a name is reported only when it does
    not appear as a Name, an attribute base, or in ``__all__``. No import is
    ever removed automatically from a module that re-exports via ``__all__``
    or a star import.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    imported = {}  # local name -> (module, original, lineno)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                local = alias.asname or alias.name.split(".")[0]
                imported[local] = (alias.name, local, node.lineno)
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                continue  # relative import: leave it alone
            for alias in node.names:
                if alias.name == "*":
                    continue
                local = alias.asname or alias.name
                imported[local] = (node.module or "", local, node.lineno)
    if not imported:
        return []
    used = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            used.add(node.id)
        elif isinstance(node, ast.Attribute):
            base = node
            while isinstance(base, ast.Attribute):
                base = base.value
            if isinstance(base, ast.Name):
                used.add(base.id)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            used.add(node.value)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "__all__":
                    for elt in getattr(node.value, "elts", []):
                        if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                            used.add(elt.value)
    return sorted(name for name in imported if name not in used)


def remove_unused_imports(source: str, names: List[str]) -> Tuple[str, int]:
    """Remove the named imports from the source. Returns (new, count)."""
    if not names:
        return source, 0
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return source, 0
    lines = source.splitlines(keepends=True)
    drop = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            keep = [a for a in node.names if (a.asname or a.name.split(".")[0]) not in names]
            if len(keep) != len(node.names):
                if not keep:
                    for ln in range(node.lineno, (node.end_lineno or node.lineno) + 1):
                        drop.add(ln)
                else:
                    indent = " " * node.col_offset
                    names_txt = ", ".join(
                        a.name + (f" as {a.asname}" if a.asname else "") for a in keep
                    )
                    replacement = f"{indent}import {names_txt}\n"
                    for ln in range(node.lineno, (node.end_lineno or node.lineno) + 1):
                        drop.add(ln)
                    lines[node.lineno - 1] = replacement
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                continue
            keep = [a for a in node.names if (a.asname or a.name) not in names]
            if len(keep) != len(node.names):
                if not keep:
                    for ln in range(node.lineno, (node.end_lineno or node.lineno) + 1):
                        drop.add(ln)
                else:
                    indent = " " * node.col_offset
                    names_txt = ", ".join(
                        a.name + (f" as {a.asname}" if a.asname else "") for a in keep
                    )
                    module = ("." * node.level) + (node.module or "")
                    replacement = f"{indent}from {module} import {names_txt}\n"
                    for ln in range(node.lineno, (node.end_lineno or node.lineno) + 1):
                        drop.add(ln)
                    lines[node.lineno - 1] = replacement
    if not drop:
        return source, 0
    kept = [line for idx, line in enumerate(lines, start=1) if idx not in drop]
    return "".join(kept), len(drop)


def apply_level1_fixes(path: Path, source: str) -> Tuple[str, List[str]]:
    """Apply the permitted mechanical fixes. Returns (new_source, notes).

    Only two fixes are permitted: trailing whitespace, and a missing final
    newline. Unused-import removal is offered as a Level 2 proposal because
    it changes the module's namespace and can alter import side effects.
    """
    notes = []
    result, count = _strip_trailing_whitespace(source)
    if count:
        notes.append(f"removed trailing whitespace on {count} line(s)")
    result, changed = _ensure_final_newline(result)
    if changed:
        notes.append("ensured a single final newline")
    return result, notes


def apply_level1_fixes_in_project(path: Path, source: str, project_rel: str = None):
    """Apply the Level 1 fixes, refusing manifest-covered files.

    A file covered by the Phase 2A manifest is part of a delivered, hashed
    phase. Rewriting it would invalidate that baseline, so the Guardian
    reports the defect and leaves the file alone.
    """
    if project_rel and config.is_manifest_protected(project_rel):
        return source, []
    return apply_level1_fixes(path, source)


def read_file_text(path: Path) -> Optional[str]:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


class RepairSuspended(RuntimeError):
    """Raised when a write is attempted while automatic repair is suspended."""


def write_file_text(path: Path, content: str, root: Path = None) -> bool:
    """Write the file atomically. Returns True on success.

    This is the ONLY function in the Guardian that writes to a project
    source file, so it is the single choke point for the automatic-repair
    capability. When the repair policy suspends automatic repair, every
    write is refused here — whichever path reached it.

    The policy is consulted for the project ROOT the file belongs to. The
    caller passes the cycle root; when it is omitted the global
    PROJECT_ROOT is used, which is the owner-controlled policy for the
    production project.
    """
    if not config.auto_repair_enabled(root):
        raise RepairSuspended(
            "automatic repair is suspended by the repair policy; "
            "no file was written"
        )
    try:
        tmp = path.with_suffix(path.suffix + ".guardian-tmp")
        tmp.write_text(content, encoding="utf-8", newline="\n")
        os.replace(tmp, path)
        return True
    except OSError:
        return False


def repair_is_sane(original: str, fixed: str) -> bool:
    """True when the repair does not drastically shrink the file.

    A mechanical formatting fix removes whitespace; it never removes most of
    a file. A repair that would is a sign that the file was already
    corrupted, and applying it would bury the corruption.
    """
    if len(original) == 0:
        return True
    return len(fixed) >= int(len(original) * config.MIN_REPAIR_SIZE_RATIO)
