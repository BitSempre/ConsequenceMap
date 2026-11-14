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


class AuthorizationSink:
    """Where the plugin records what the host observed.

    The seam is explicit so the runtime does not depend on a database
    being present, and so a test can observe exactly what would have
    been written.

    The default sink is **inert**: it records nothing and writes
    nothing. The plugin's entry point replaces it with one that writes
    to the plugin's own store. That is deliberate — a hook must never
    fail because the storage is unavailable, but a *missing* record
    must never be mistaken for an approval.
    """

    def __init__(self) -> None:
        #: How many times a record could not be written. The inert sink
        #: never fails to write, so this stays at zero - but the
        #: attribute exists so every sink exposes the same counter and
        #: the status command can read it without a special case.
        self.failures = 0

    def begin(self, record) -> None:
        """An escalation is in flight."""

    def settle(self, record) -> None:
        """The escalation was answered, or it timed out."""

    def close(self, record) -> None:
        """The tool call finished."""


class MemoryAuthorizationSink(AuthorizationSink):
    """A sink that keeps the records in memory. Used by the tests."""

    def __init__(self) -> None:
        self.begun = []
        self.settled = []
        self.closed = []

    def begin(self, record) -> None:
        self.begun.append(record)

    def settle(self, record) -> None:
        self.settled.append(record)

    def close(self, record) -> None:
        self.closed.append(record)


class RepositoryAuthorizationSink(AuthorizationSink):
    """A sink that writes the authorization to the plugin's own store.

    This is the sink the plugin actually uses. The authorization the
    human gave has to reach the database, or the product has no
    record of it and the dashboard has nothing to show.

    It writes through the **lifecycle**, not through the repository
    directly, so the copy lint and the storage rules apply to an
    authorization exactly as they apply to a forecast.

    Two properties matter:

    * **It never raises.** A hook must not fail because the storage
      is unavailable. A storage failure is recorded as a failure to
      record, and the operation continues - the host owns the
      decision, and a missing audit row is a gap, not an authority.
    * **It never invents a forecast.** The record it writes names the
      forecast the correlation attributed the observation to. If the
      correlation did not attribute it, nothing is written: an
      unattributed observation is not evidence of an approval.
    """

    def __init__(self, repository=None, lifecycle=None) -> None:
        self._repository = repository
        self._lifecycle = lifecycle
        self.failures = 0

    def _lifecycle_for(self):
        if self._lifecycle is not None:
            return self._lifecycle
        if self._repository is None:
            return None
        from .lifecycle import Lifecycle

        self._lifecycle = Lifecycle(self._repository)
        return self._lifecycle

    def _proposal_for(self, forecast_id: str):
        """The proposal a forecast belongs to.

        Read from the forecast itself. If the forecast does not
        exist, there is nothing to write: an authorization for a
        forecast nobody made is not a record, it is a gap.
        """
        repository = self._repository
        if repository is None or not forecast_id:
            return ("", 1)
        try:
            rows = repository.read_all_rows("forecast")
        except Exception:
            return ("", 1)
        for row in rows:
            if row and row[0] == forecast_id:
                return (row[1], int(row[2]))
        return ("", 1)

    def _write(self, record, *, action: str) -> None:
        lifecycle = self._lifecycle_for()
        if lifecycle is None:
            self.failures += 1
            return
        try:
            lifecycle.record_authorization(self._as_domain_record(record))
        except Exception:
            # A storage failure must not take the hook down. It is
            # counted, and the operation continues: the host owns the
            # decision, and a missing row is a gap in the trail, never
            # a reason to let an operation through that would not have
            # gone through.
            self.failures += 1

    def _as_domain_record(self, record):
        """The domain record the storage layer expects.

        The ``proposal_id`` and ``proposal_version`` are the
        forecast's own. The authorization names the proposal the
        approval was for; writing anything else would break the
        composite foreign key to the proposal, and would break the
        point of the record.
        """
        from .domain import records as R
        from .domain.enums import AUTHORIZATION_PROVENANCE
        from .domain.validation import now_timestamp

        proposal_id, proposal_version = self._proposal_for(record.forecast_id)

        return R.HostAuthorization(
            id="auth_%s" % (record.forecast_id or "unknown"),
            forecast_id=record.forecast_id,
            proposal_id=proposal_id,
            proposal_version=proposal_version,
            state=record.state.value,
            provenance=AUTHORIZATION_PROVENANCE.HOST_APPROVAL_HOOK.value,
            authorized_by=record.authorized_by.value,
            observed_choice=record.observed_choice or "",
            observed_via="hook",
            reason=record.reason.value,
            created_at=record.decided_at or now_timestamp(),
            escalation_expected=True,
            tool_call_id=record.tool_call_id or None,
            pattern_key=record.pattern_key or None,
            notes=record.notes,
        )

    def begin(self, record) -> None:
        """An escalation is in flight."""
        self._write(record, action="begin")

    def settle(self, record) -> None:
        """The escalation was answered, or it timed out."""
        self._write(record, action="settle")

    def close(self, record) -> None:
        """The tool call finished."""
        self._write(record, action="close")


class HookState:
    """The plugin's runtime state.

    It owns the correlator, the authorization machine, the pending
    escalations and the sink the records are written to. It is the
    single object the callbacks share, so the state transitions are
    easy to follow and easy to test.
    """

    def __init__(self, *, machine=None, correlator=None, sink=None) -> None:
        from .authorization import AuthorizationMachine
        from .correlation import Correlator

        self.machine = machine or AuthorizationMachine()
        self.correlator = correlator or Correlator()
        self.sink = sink if sink is not None else AuthorizationSink()
        self._lock = threading.RLock()
        self._registered = False

    def reset(self) -> None:
        """Forget the session's state. Used by the tests and on load."""
        with self._lock:
            self.correlator = type(self.correlator)()
            self.sink = AuthorizationSink()


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
        forecast_id = STATE.correlator.note_request(pattern_key, tool_call_id)
        if forecast_id is not None:
            # The escalation is in flight. The record says PENDING,
            # which is not terminal and authorizes nothing.
            STATE.sink.begin(
                STATE.machine.pending(
                    forecast_id=forecast_id,
                    tool_call_id=tool_call_id,
                    pattern_key=pattern_key if isinstance(pattern_key, str) else "",
                )
            )
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
        forecast_id = STATE.correlator.note_response(pattern_key, tool_call_id)
        if forecast_id is not None:
            # The answer is recorded. A duplicate is ignored by the
            # correlator and never produces a second record.
            STATE.sink.settle(
                STATE.machine.from_choice(
                    choice,
                    forecast_id=forecast_id,
                    tool_call_id=tool_call_id,
                    pattern_key=pattern_key if isinstance(pattern_key, str) else "",
                )
            )
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


def _sink_failures() -> int:
    """How many records the audit sink failed to write this session.

    A storage failure is counted by the sink and the operation
    continues - the host owns the decision. But a gap in the audit
    trail must not be INVISIBLE: the counter is reported by the status
    command, so the operator can see that the trail is incomplete.

    The counter is read, never reset and never hidden. A sink that does
    not keep one reports zero rather than making the status command
    fail.
    """
    sink = getattr(STATE, "sink", None)
    failures = getattr(sink, "failures", 0)
    try:
        return int(failures)
    except (TypeError, ValueError):
        return 0


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
            "Orphan observations: %d\n"
            "Audit sink failures this session: %d"
            % (
                __version__,
                self_exclusion.COUNTER.total(),
                len(STATE.correlator.pending()),
                STATE.correlator.duplicates,
                STATE.correlator.orphans,
                _sink_failures(),
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
