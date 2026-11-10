"""Path resolution and containment.

Specification section 7, proposal section 7.

The normative algorithm, transferred from specification section 7.2:

1. Expand "~" using the host's profile-aware home.
2. On Windows, translate an MSYS drive path.
3. If relative, anchor to the authorized root.
4. Resolve symlinks and junctions: ``os.path.realpath(path)``.
5. Containment test: ``Path(resolved).is_relative_to(Path(root_real))``.
6. Compare with ``os.path.normcase`` for case-insensitivity.

**Never** a raw ``startswith`` on the unresolved path. On this host a
naive prefix check wrongly passes a junction escape.

**What this does not claim (R-TOCTOU-1).** The path, *resolved at the
moment of analysis*, was inside the authorized root. It says nothing
about the write that follows: the plugin cannot close the window
between the check and the host's write without an OS handle with
``FILE_FLAG_OPEN_REPARSE_POINT`` semantics, and that is not in scope.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional, Sequence, Tuple

#: The write and delete operations. E-PROTECTED applies to these and
#: to nothing else - the criterion is the proposal's operation, not
#: the tool's name.
WRITE_OPERATIONS: frozenset = frozenset(
    {"FILE_WRITE", "FILE_DELETE", "FILE_PATCH"}
)


class PathError(Exception):
    """The path could not be resolved or contained."""


class PathResolution:
    """The result of resolving one path."""

    __slots__ = ("original", "resolved", "root", "contained", "reason")

    def __init__(
        self,
        *,
        original: str,
        resolved: str,
        root: str,
        contained: bool,
        reason: str = "",
    ) -> None:
        self.original = original
        self.resolved = resolved
        self.root = root
        self.contained = contained
        self.reason = reason

    def __repr__(self) -> str:  # pragma: no cover - diagnostic only
        return "<PathResolution contained=%s %r>" % (self.contained, self.resolved)


def _expand_home(path: str, home: Optional[str] = None) -> str:
    """Step 1: expand "~".

    The home is injected rather than read from the process
    environment: the plugin does not read it for this, because the
    host owns the profile-aware home.
    """
    if not path.startswith("~"):
        return path
    # The home is **injected**. The plugin does not read the process
    # environment and does not import the host's home resolver: the
    # caller passes the profile-aware home the host already knows.
    base = home if home is not None else os.path.expanduser("~")
    if path == "~":
        return base
    if path.startswith("~/") or path.startswith("~" + chr(92)):
        return os.path.join(base, path[2:])
    return path


def _translate_msys(path: str) -> str:
    r"""Step 2: translate an MSYS drive path on Windows.

    ``/c/Users/x`` becomes ``C:\Users\x``. On a non-Windows host
    this is a no-op, and a POSIX path is returned unchanged.
    """
    if os.name != "nt":
        return path
    match = re.match(r"^/([A-Za-z])/(.*)$", path)
    if match is None:
        return path
    drive = match.group(1).upper()
    rest = match.group(2).replace("/", os.sep)
    return "%s:%s%s" % (drive, os.sep, rest)


def resolve_path(
    path: str,
    root: str,
    *,
    home: Optional[str] = None,
) -> PathResolution:
    """Resolve one path against the authorized root and test containment.

    The six normative steps, in order.
    """
    if not isinstance(path, str) or not path:
        raise PathError("a path is required")
    if not isinstance(root, str) or not root:
        raise PathError("the authorized root is required")

    original = path

    # Step 1.
    candidate = _expand_home(path, home)
    # Step 2.
    candidate = _translate_msys(candidate)
    # Step 3: a relative path is anchored to the authorized root.
    if not os.path.isabs(candidate):
        candidate = os.path.join(root, candidate)
    # Step 4: resolve symlinks and junctions.
    resolved = os.path.realpath(candidate)
    root_real = os.path.realpath(root)
    # Steps 5 and 6: containment, case-normalised.
    try:
        contained = Path(os.path.normcase(resolved)).is_relative_to(
            Path(os.path.normcase(root_real))
        )
    except (ValueError, OSError):
        contained = False
    reason = "" if contained else "the path resolves outside the authorized root"
    return PathResolution(
        original=original,
        resolved=resolved,
        root=root_real,
        contained=contained,
        reason=reason,
    )


def root_digest(root: str) -> str:
    """A digest of the authorized root.

    The root is recorded on every forecast as a **digest only**. The
    full path is never persisted, because a path is identifying.
    """
    import hashlib

    normalised = os.path.normcase(os.path.realpath(root)).encode("utf-8")
    return hashlib.sha256(normalised).hexdigest()


def _match_pattern(pattern: str, path: str) -> bool:
    """Match one protected-path pattern.

    ``**`` matches multiple segments. The comparison is on the
    normalised absolute path, with forward slashes.
    """
    slash = chr(92)
    regex = re.escape(pattern.replace(slash, "/"))
    regex = regex.replace(r"\*\*/", r"(?:.*/)?")
    regex = regex.replace(r"\*\*", r".*")
    regex = regex.replace(r"\*", r"[^/]*")
    return re.fullmatch(regex, path) is not None


def _normalise_for_match(path: str) -> str:
    """The normalised, forward-slash form used for matching."""
    return os.path.normcase(path).replace(chr(92), "/")


def is_protected(
    path: str,
    patterns: Sequence[str],
    *,
    root: Optional[str] = None,
) -> bool:
    """Whether the resolved absolute path matches a protected pattern.

    Specification section 7.5: the match is against the **resolved
    absolute path**, with ``**`` for multi-segment matching,
    normalised to forward slashes; a relative pattern is anchored to
    the authorized root; ``os.path.normcase`` is applied. An empty
    list means no protected paths.
    """
    if not patterns:
        return False
    resolved = os.path.realpath(path) if os.path.isabs(path) else path
    resolved = _normalise_for_match(resolved)
    for pattern in patterns:
        if not pattern:
            continue
        candidate = pattern
        if not os.path.isabs(candidate):
            if root is None:
                continue
            candidate = os.path.join(root, candidate)
        candidate = _normalise_for_match(os.path.realpath(candidate))
        if _match_pattern(candidate, resolved):
            return True
    return False


def applies_to_operation(operation: str) -> bool:
    """Whether E-PROTECTED applies to this proposal operation."""
    return operation in WRITE_OPERATIONS
