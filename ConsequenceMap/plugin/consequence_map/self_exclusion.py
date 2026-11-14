"""Self-exclusion: the plugin never observes its own operations.

Specification section 4.8, requirements RECUR-1 through RECUR-9.

The plugin registers ``pre_tool_call`` and ``post_tool_call``. Those
hooks fire for **every** tool call in the session, including the
plugin's own. The host applies no plugin-origin filter. Without a
guard, the plugin would analyse its own analysis, and its own
escalation could block the very operation needed to finish the
forecast.

This module is deliberately inert: it imports nothing from Hermes, and
it holds only frozen strings. RECUR-7 requires the excluded set to be
frozen at import, with no configuration path that widens it - such a
path would be a way around the plugin's own gating.
"""
from __future__ import annotations

import threading
from typing import FrozenSet, Tuple

#: The reserved prefix every tool this plugin registers carries.
#: RECUR-2: the namespace makes the excluded set mechanically
#: derivable and collision-free against host or third-party tools.
TOOL_PREFIX = "consequence_map_"

#: The tools this plugin registers. Every one of them is invisible to
#: the plugin's own hooks (RECUR-1, RECUR-2, RECUR-3).
REGISTERED_TOOLS: Tuple[str, ...] = (
    "consequence_map_forecast",
    "consequence_map_decision",
    "consequence_map_outcome",
    "consequence_map_compare",
)

#: The internal operations the plugin performs on its own behalf.
#: RECUR-6: the Desktop surfaces and the plugin's own bookkeeping are
#: excluded as well.
INTERNAL_OPERATIONS: Tuple[str, ...] = (
    "consequence_map_internal_persist",
    "consequence_map_internal_read",
    "consequence_map_internal_sweep",
    "consequence_map_internal_render",
)

#: The complete excluded set. RECUR-7: a frozenset, with no setter and
#: no configuration key that could extend it.
EXCLUDED_TOOL_NAMES: FrozenSet[str] = frozenset(
    REGISTERED_TOOLS + INTERNAL_OPERATIONS
)


class ExclusionCounter:
    """A per-session count of the excluded calls (RECUR-9).

    The exclusion leaves a trace. A non-zero count with zero recorded
    forecasts is a detectable misconfiguration, not a silent one.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counts: dict[str, int] = {}

    def record(self, tool_name: str) -> None:
        with self._lock:
            self._counts[tool_name] = self._counts.get(tool_name, 0) + 1

    def count(self, tool_name: str) -> int:
        with self._lock:
            return self._counts.get(tool_name, 0)

    def total(self) -> int:
        with self._lock:
            return sum(self._counts.values())

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return dict(self._counts)

    def reset(self) -> None:
        with self._lock:
            self._counts.clear()


#: The process-wide counter. The plugin records into it and logs the
#: total per session.
COUNTER = ExclusionCounter()


def is_excluded(tool_name: object) -> bool:
    """Whether this tool call is the plugin's own.

    The comparison is by exact name against the frozen set. An empty
    or non-string name is not excluded: the plugin does not guess.
    """
    if not isinstance(tool_name, str):
        return False
    return tool_name in EXCLUDED_TOOL_NAMES


def record_exclusion(tool_name: str) -> None:
    """Count an excluded call (RECUR-9)."""
    COUNTER.record(tool_name)
