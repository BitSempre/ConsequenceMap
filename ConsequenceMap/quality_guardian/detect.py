"""Real change detection.

The Guardian must not run tests when nothing actually changed. This module
compares the SHA-256 of every tracked file against the last recorded state,
so a rewrite with identical content is NOT a change, and a touched file
whose content did not move is NOT a change either.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Dict, Iterable, List

from . import config


def sha256_of(path: Path) -> str:
    """The SHA-256 of a file's bytes, or "" when it cannot be read."""
    try:
        digest = hashlib.sha256()
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(65536), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except (OSError, ValueError):
        return ""


def tracked_files(root: Path = None) -> List[Path]:
    """Every tracked source file under the project root.

    Excludes the Guardian's own tree, caches and version-control metadata,
    so the Guardian never reacts to its own writes.
    """
    base = Path(root) if root else config.PROJECT_ROOT
    out: List[Path] = []
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = sorted(
            d for d in dirnames
            if d not in config.EXCLUDED_DIRS
            and (Path(dirpath) / d) != config.GUARDIAN_DIR
        )
        for name in sorted(filenames):
            if Path(name).suffix not in config.TRACKED_SUFFIXES:
                continue
            candidate = Path(dirpath) / name
            if candidate.is_file():
                out.append(candidate)
    return out


def current_hashes(root: Path = None) -> Dict[str, str]:
    """Map every tracked file's project-relative path to its SHA-256."""
    base = Path(root) if root else config.PROJECT_ROOT
    result: Dict[str, str] = {}
    for path in tracked_files(base):
        try:
            rel = path.relative_to(base).as_posix()
        except ValueError:
            continue
        result[rel] = sha256_of(path)
    return result


def _state_path(root: Path = None) -> Path:
    base = Path(root) if root else config.PROJECT_ROOT
    return base / "quality_guardian" / "state" / "last-seen.json"


def load_state(root: Path = None) -> Dict[str, str]:
    """The last recorded hash map. An empty map on first run."""
    path = _state_path(root)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    hashes = data.get("hashes")
    return hashes if isinstance(hashes, dict) else {}


def save_state(hashes: Dict[str, str], root: Path = None) -> None:
    """Record the current hash map as the new baseline."""
    path = _state_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"hashes": hashes}
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=1, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)


def detect_changes(root: Path = None, previous: Dict[str, str] = None) -> Dict[str, List[str]]:
    """Compare the tree against the recorded baseline.

    Returns {"modified": [...], "added": [...], "removed": [...]}, each
    sorted. A file whose content is byte-identical to the baseline is not
    reported, even if it was rewritten.
    """
    base = Path(root) if root else config.PROJECT_ROOT
    before = load_state(base) if previous is None else previous
    after = current_hashes(base)
    modified = sorted(p for p in after if p in before and after[p] != before[p])
    added = sorted(p for p in after if p not in before)
    removed = sorted(p for p in before if p not in after)
    return {"modified": modified, "added": added, "removed": removed}


def changed_paths(root: Path = None) -> List[str]:
    """Every changed project-relative path, sorted."""
    changes = detect_changes(root)
    return sorted(changes["modified"] + changes["added"])


def paths_from_tool_input(tool_input) -> List[str]:
    """Best-effort extraction of written paths from a Hermes tool payload.

    The hook payload carries the tool's arguments. Only the known
    path-bearing keys are read; nothing is executed or interpreted.
    """
    if not isinstance(tool_input, dict):
        return []
    out: List[str] = []
    for key in ("path", "file_path", "filename", "target"):
        value = tool_input.get(key)
        if isinstance(value, str) and value:
            out.append(value)
    edits = tool_input.get("edits")
    if isinstance(edits, list):
        for edit in edits:
            if isinstance(edit, dict):
                value = edit.get("path")
                if isinstance(value, str) and value:
                    out.append(value)
    return out
