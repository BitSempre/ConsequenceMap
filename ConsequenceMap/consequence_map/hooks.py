"""The five hook callbacks, and the plugin's registration.

Specification section 13, proposal section 3.

The five hooks and what each one may do:

===============  ==========  ==========================================
Hook             Kind        May it change the host's decision?
===============  ==========  ==========================================
pre_tool_call    Directive   YES - the plugin's one intervention point
pre_approval_request Observer  NO - the host ignores the return value
post_approval_response Observer NO - the host ignores the return value
post_tool_call   Observer    NO - observation only
transform_tool_result Transform YES - but this plugin NEVER uses it
===============  ==========  ==========================================

``transform_tool_result`` is registered because it is one of the five
declared hooks, and it is registered **strictly as a declaration**: its
callback returns ``None`` on every invocation and never mutates the
``result`` payload it receives. The host enforces none of this - the
prohibition is the plugin's to uphold (RECUR-8).
"""
from __future__ import annotations

import threading
from typing import Any, Callable, Dict, Optional

from . import self_exclusion

#: The five hooks the plugin registers.
HOOK_NAMES = (
    "pre_tool_call",
    "pre_approval_request",
    "post_approval_response",
    "post_tool_call",
    "transform_tool_result",
)


class HookDecision:
    """What the ``pre_tool_call`` callback decided.

    The plugin escalates; it does not block. The specification's
    ``block`` rule is E-PROTECTED, and a protected path is refused by
    the host's own guards, not by the plugin rewriting the host's
    decision.
    """

    __slots__ = ("action", "message", "rule_key")

    def __init__(
        self,
        action: str = "none",
        message: str = "",
        rule_key: str = "",
    ) -> None:
        self.action = action
        self.message = message
        self.rule_key = rule_key

    def to_hook_result(self) -> Optional[Dict[str, Any]]:
        """The shape the host expects, or ``None`` to proceed."""
        if self.action == "none":
            return None
        result: Dict[str, Any] = {"action": self.action}
        if self.message:
            result["message"] = self.message
        if self.rule_key:
            result["rule_key"] = self.rule_key
        return result


class HookState:
    """The plugin's runtime state.

    It owns the correlator, the authorization machine and the pending
    escalations. It is the single object the callbacks share, so the
    state transitions are easy to follow and easy to test.
    """

    def __init__(self, *, machine=None, correlator=None) -> None:
        from .authorization import AuthorizationMachine
        from .correlation import Correlator

        self.machine = machine or AuthorizationMachine()
        self.correlator = correlator or Correlator()
        self._lock = threading.RLock()
        self._registered = False

    def reset(self) -> None:
        """Forget the session's state. Used by the tests and on load."""
        with self._lock:
            self.correlator = type(self.correlator)()


#: The plugin's state. A module-level object because the hooks are
#: module-level callbacks.
STATE = HookState()


def register(ctx) -> None:
    """Register the five hooks and the command.

    This is the entry point the host calls. It is deliberately small:
    it wires callbacks and nothing else.
    """
    if STATE._registered:
        return
    ctx.register_hook("pre_tool_call", on_pre_tool_call)
    ctx.register_hook("pre_approval_request", on_pre_approval_request)
    ctx.register_hook("post_approval_response", on_post_approval_response)
    ctx.register_hook("post_tool_call", on_post_tool_call)
    ctx.register_hook("transform_tool_result", on_transform_tool_result)
    ctx.register_command(
        "consequence-map",
        handler=on_command,
        description=(
            "ConsequenceMap: forecast a consequence, record the decision, "
            "and compare the forecast with the outcome."
        ),
        args_hint="[forecast|decision|outcome|compare|status]",
    )
    STATE._registered = True


# -- the callbacks ----------------------------------------------------


def on_pre_tool_call(**kwargs: Any) -> Optional[Dict[str, Any]]:
    """The plugin's one intervention point.

    It escalates: when the operation needs a human, it asks the host
    for one, with a rule key that names the forecast. It does not
    block - blocking a tool call is the host's decision, and the
    plugin does not pretend otherwise.
    """
    tool_name = kwargs.get("tool_name")
    if self_exclusion.is_excluded(tool_name):
        # RECUR-1, RECUR-3: the plugin's own calls are invisible to it.
        self_exclusion.record_exclusion(str(tool_name))
        return None
    escalation = kwargs.get("consequence_map_escalation")
    if not isinstance(escalation, dict):
        return None
    rule_key = escalation.get("rule_key")
    if not isinstance(rule_key, str) or not rule_key:
        return None
    return HookDecision(
        action="approve",
        message=escalation.get("message", ""),
        rule_key=rule_key,
    ).to_hook_result()


def on_pre_approval_request(**kwargs: Any) -> Optional[None]:
    """Observe that the host asked a human.

    The host ignores this callback's return value. It exists so the
    plugin knows an approval is in flight.
    """
    tool_name = kwargs.get("tool_name")
    if self_exclusion.is_excluded(tool_name):
        self_exclusion.record_exclusion(str(tool_name))
        return None
    pattern_key = kwargs.get("pattern_key")
    tool_call_id = kwargs.get("tool_call_id", "")
    with STATE._lock:
        STATE.correlator.note_request(pattern_key, tool_call_id)
    return None


def on_post_approval_response(**kwargs: Any) -> Optional[None]:
    """Observe the human's answer.

    The host ignores the return value.
    """
    tool_name = kwargs.get("tool_name")
    if self_exclusion.is_excluded(tool_name):
        self_exclusion.record_exclusion(str(tool_name))
        return None
    pattern_key = kwargs.get("pattern_key")
    tool_call_id = kwargs.get("tool_call_id", "")
    choice = kwargs.get("choice")
    with STATE._lock:
        STATE.correlator.note_response(pattern_key, tool_call_id)
    return None


def on_post_tool_call(**kwargs: Any) -> Optional[None]:
    """Observe that a tool call finished.

    The host ignores the return value.
    """
    tool_name = kwargs.get("tool_name")
    if self_exclusion.is_excluded(tool_name):
        self_exclusion.record_exclusion(str(tool_name))
        return None
    pattern_key = kwargs.get("pattern_key")
    tool_call_id = kwargs.get("tool_call_id", "")
    status = kwargs.get("status")
    with STATE._lock:
        STATE.correlator.note_tool_call(pattern_key, tool_call_id)
    return None


def on_transform_tool_result(**kwargs: Any) -> Optional[None]:
    """Declare the transform hook, and never use it.

    RECUR-8: the callback returns ``None`` on **every** invocation and
    does not mutate the ``result`` payload it receives - neither by
    returning a replacement nor by mutating the object in place. The
    host passes the live object by reference, so returning ``None``
    alone does not demonstrate compliance.
    """
    return None


# -- the command ------------------------------------------------------


def on_command(raw_args: str = "") -> str:
    """The command palette entry (DEC-12 = A).

    It reports what the plugin knows. It never executes anything and
    it never claims an approval it did not observe.
    """
    from . import __version__

    argument = (raw_args or "").strip()
    if argument in ("", "status"):
        return (
            "ConsequenceMap %s\n"
            "Excluded tool calls this session: %d\n"
            "Pending escalations: %d\n"
            "Duplicate observations ignored: %d\n"
            "Orphan observations: %d"
            % (
                __version__,
                self_exclusion.COUNTER.total(),
                len(STATE.correlator.pending()),
                STATE.correlator.duplicates,
                STATE.correlator.orphans,
            )
        )
    if argument == "pending":
        pending = STATE.correlator.pending()
        if not pending:
            return "No escalation is pending."
        lines = ["Pending escalations:"]
        for forecast_id, item in sorted(pending.items()):
            lines.append(
                "  %s  %s  tool_call_id=%s"
                % (forecast_id, item.rule, item.tool_call_id or "(none)")
            )
        return "\n".join(lines)
    return (
        "Usage: /consequence-map [status|pending]\n"
        "  status   the plugin's state (default)\n"
        "  pending  the escalations in flight"
    )
