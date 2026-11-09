"""The shell-hook entry point.

Hermes spawns this script with a JSON payload on stdin whenever a
configured hook event fires. The script:

* reads the payload,
* decides whether the event is relevant to this project,
* runs a Guardian cycle,
* writes the persistent report,
* prints the directive JSON the runtime understands.

For ``post_tool_call`` the directive is always empty: that event is an
observer and its return value is ignored. For ``pre_verify`` it may be
``{"action": "continue", "message": ...}``, which keeps the agent working
until the verification passes.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# The Guardian package lives next to this script's project root.
_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from quality_guardian import config, detect, guardian  # noqa: E402


def _read_payload() -> dict:
    """The JSON payload Hermes writes to stdin, or an empty dict."""
    try:
        raw = sys.stdin.read()
    except Exception:
        return {}
    if not raw or not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _is_project_path(path: str, root: Path = None) -> bool:
    """True when the path is inside the project root.

    The root is a parameter so the rule can be tested against an isolated
    copy of the project without touching the production tree.
    """
    base = Path(root) if root else config.PROJECT_ROOT
    try:
        resolved = Path(path).resolve()
        base = base.resolve()
    except (OSError, ValueError):
        return False
    try:
        resolved.relative_to(base)
    except ValueError:
        return False
    return True


def handle_post_tool_call(payload: dict) -> int:
    """After a write: verify only if the write touched this project."""
    tool_name = payload.get("tool_name")
    tool_input = payload.get("tool_input")
    candidates = detect.paths_from_tool_input(tool_input)
    relevant = [p for p in candidates if _is_project_path(p)]
    if not relevant:
        # The write did not touch this project. Stay silent and cheap.
        return 0
    cycle = guardian.run_cycle(trigger=f"post_tool_call:{tool_name}", changed=None)
    guardian.finalize(cycle)
    # post_tool_call is an observer: its return value is ignored.
    return 0


def handle_pre_verify(payload: dict) -> int:
    """The end-of-turn gate: keep the agent going while verification fails."""
    changed = payload.get("extra", {}).get("changed_paths")
    if not isinstance(changed, list):
        changed = None
    cycle = guardian.run_cycle(trigger="pre_verify", changed=changed, force_full=True)
    guardian.finalize(cycle)
    verdict = cycle.result.worst
    # Only a hard failure keeps the agent working. A WARNING is reported
    # and recorded, but it must not trap the turn in a nudge loop.
    if verdict in ("FAIL", "NOT_VERIFIED", "BLOCKED"):
        summary = _summarise(cycle)
        directive = {
            "action": "continue",
            "message": (
                "ConsequenceMap quality verification did not pass "
                f"(verdict {verdict}). Fix the issue and re-run the tests; "
                f"do not finish the turn until it passes. Details: {summary}"
            ),
        }
        sys.stdout.write(json.dumps(directive))
        sys.stdout.flush()
    return 0


def _summarise(cycle) -> str:
    """A one-line summary of the unresolved findings."""
    parts = []
    for check in cycle.result.checks:
        if check.verdict in ("FAIL", "NOT_VERIFIED", "BLOCKED"):
            parts.append(f"{check.name}: {check.detail}")
    return " | ".join(parts[:4]) or "no detail"


def main(argv=None) -> int:
    payload = _read_payload()
    event = payload.get("hook_event_name")
    try:
        if event == "post_tool_call":
            return handle_post_tool_call(payload)
        if event == "pre_verify":
            return handle_pre_verify(payload)
    except Exception as exc:  # never break the agent's turn
        sys.stderr.write(f"quality-guardian hook error: {type(exc).__name__}: {exc}\n")
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
