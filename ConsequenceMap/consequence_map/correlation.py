"""Correlation: attributing a host event to a forecast.

Specification section 4, proposal sections 4.1 to 4.4.

The chain is::

    forecast_id -> proposal_version -> rule_key -> tool_call_id
                -> approval_request -> approval_response
                -> post_tool_call -> outcome

The plugin supplies ``rule_key = "cm:<forecast_id>:<rule>"`` and never
includes the host's ``plugin_rule:`` prefix - the host adds that. The
observer sees the prefixed form.

An observation is attributed to a forecast **only if** every condition
holds (AUTH-1a/AUTH-1b/AUTH-1c). Any failure means the observation is
not attributed, and the authorization state becomes ``UNKNOWN`` or
``APPROVAL_NOT_OBSERVED`` - never ``HUMAN_APPROVED``.
"""
from __future__ import annotations

import threading
from typing import Any, Dict, Mapping, Optional, Tuple

#: The prefix the HOST adds to the plugin's rule key. The plugin never
#: includes it (P-KEY-1).
HOST_RULE_PREFIX = "plugin_rule:"

#: The plugin's own prefix (P-KEY-1).
PLUGIN_RULE_PREFIX = "cm:"

#: The escalation rules of specification section 6.1 (P-KEY-2).
ESCALATION_RULES: Tuple[str, ...] = (
    "E-PROTECTED",
    "E-CRITICAL",
    "E-HIGH",
    "E-IRREVERSIBLE",
    "E-HIGH-LOWCONF",
    "E-MODERATE",
)

#: The rules that produce an escalation. Only these three.
ESCALATING_RULES: frozenset = frozenset(
    {"E-CRITICAL", "E-HIGH", "E-IRREVERSIBLE"}
)


def make_rule_key(forecast_id: str, rule: str) -> str:
    """Build the plugin's rule key.

    The plugin supplies ``cm:<forecast_id>:<rule>`` and never includes
    the host's prefix (P-KEY-1). The rule must be one of the
    specification's escalation rules (P-KEY-2).
    """
    if not forecast_id:
        raise ValueError("the forecast id is required")
    if rule not in ESCALATION_RULES:
        raise ValueError(
            "unknown escalation rule %r; expected one of %s"
            % (rule, ", ".join(ESCALATION_RULES))
        )
    return "%s%s:%s" % (PLUGIN_RULE_PREFIX, forecast_id, rule)


def expected_pattern_key(forecast_id: str, rule: str) -> str:
    """The ``pattern_key`` the observer will see for this forecast."""
    return HOST_RULE_PREFIX + make_rule_key(forecast_id, rule)


def parse_pattern_key(pattern_key: object) -> Optional[Tuple[str, str]]:
    """Split an observed ``pattern_key`` into (forecast_id, rule).

    Returns ``None`` for anything that is not this plugin's own key
    (EC-8: another approval may be in flight, and it belongs to
    someone else).
    """
    if not isinstance(pattern_key, str):
        return None
    if not pattern_key.startswith(HOST_RULE_PREFIX):
        return None
    remainder = pattern_key[len(HOST_RULE_PREFIX):]
    if not remainder.startswith(PLUGIN_RULE_PREFIX):
        return None
    body = remainder[len(PLUGIN_RULE_PREFIX):]
    parts = body.split(":")
    if len(parts) != 2:
        return None
    forecast_id, rule = parts
    if not forecast_id or rule not in ESCALATION_RULES:
        return None
    return forecast_id, rule


def _as_text(value: object) -> str:
    """A string, or the empty string. An absent id is ABSENT."""
    if isinstance(value, str):
        return value
    return ""


class PendingEscalation:
    """One escalation the plugin asked the host to make."""

    __slots__ = (
        "forecast_id",
        "rule",
        "pattern_key",
        "tool_call_id",
        "session_id",
        "task_id",
        "deadline",
        "observed_request",
        "observed_response",
        "dedup_key",
    )

    def __init__(
        self,
        *,
        forecast_id: str,
        rule: str,
        pattern_key: str,
        tool_call_id: str = "",
        session_id: str = "",
        task_id: str = "",
        deadline: Optional[float] = None,
    ) -> None:
        self.forecast_id = forecast_id
        self.rule = rule
        self.pattern_key = pattern_key
        self.tool_call_id = tool_call_id
        self.session_id = session_id
        self.task_id = task_id
        self.deadline = deadline
        self.observed_request = False
        self.observed_response = False
        self.dedup_key = (pattern_key, tool_call_id)

    def __repr__(self) -> str:  # pragma: no cover - diagnostic only
        return "<PendingEscalation %s %s>" % (self.forecast_id, self.rule)


class CorrelationError(Exception):
    """The correlation state is inconsistent and cannot be used."""


class Correlator:
    """The per-session correlation state.

    It holds the pending escalations, attributes observations to
    forecasts, and counts the duplicates it ignores (EC-3).

    It is deliberately not thread-safe by itself; the caller owns the
    lock. This keeps the state transitions easy to reason about and
    easy to test.
    """

    def __init__(self) -> None:
        self._pending: Dict[str, PendingEscalation] = {}
        self._by_pattern: Dict[str, str] = {}
        self._duplicates = 0
        self._orphans = 0
        self._ambiguities = 0

    # -- registration --------------------------------------------------

    def register(
        self,
        *,
        forecast_id: str,
        rule: str,
        pattern_key: str,
        tool_call_id: str = "",
        session_id: str = "",
        task_id: str = "",
        deadline: Optional[float] = None,
    ) -> PendingEscalation:
        """Record that the plugin escalated for this forecast.

        The key is the forecast identity, so a second escalation for
        the same forecast replaces the first rather than accumulating.
        """
        pending = PendingEscalation(
            forecast_id=forecast_id,
            rule=rule,
            pattern_key=pattern_key,
            tool_call_id=tool_call_id,
            session_id=session_id,
            task_id=task_id,
            deadline=deadline,
        )
        self._pending[forecast_id] = pending
        self._by_pattern[pattern_key] = forecast_id
        return pending

    # -- attribution ---------------------------------------------------

    def attribute(
        self,
        *,
        pattern_key: object,
        tool_call_id: object = "",
        escalation_expected: bool = True,
        pending_forecasts: Optional[Tuple[str, ...]] = None,
    ) -> Optional[str]:
        """Return the forecast id this observation belongs to.

        Returns ``None`` when the observation is not attributed, which
        is the safe answer: the caller then records ``UNKNOWN`` or
        ``APPROVAL_NOT_OBSERVED``, never an approval.

        The rules (AUTH-1a/AUTH-1b/AUTH-1c, P-CORR-1, P-CORR-2):

        1. ``escalation_expected`` must be true.
        2. At least one channel must be present AND matching:
           the ``pattern_key``, or the ``tool_call_id``. An empty
           ``tool_call_id`` is ABSENT, not a match (EC-1).
        3. The observation must be internally consistent.
        4. Attribution must not rely on target-set overlap, which
           identifies candidates, not provenance.
        """
        if not escalation_expected:
            return None

        observed_pattern = _as_text(pattern_key)
        observed_tool = _as_text(tool_call_id)

        parsed = parse_pattern_key(observed_pattern)
        matched: Optional[str] = None

        if parsed is not None:
            forecast_id, rule = parsed
            # The channel must MATCH: the forecast must be one the
            # plugin actually escalated for.
            known = self._by_pattern.get(observed_pattern)
            if known is not None and known == forecast_id:
                matched = forecast_id
            elif forecast_id in self._pending:
                # The pattern names a pending escalation. The forecast
                # identity came from the plugin itself, because only
                # an escalation the plugin made is pending here.
                #
                # The rule must ALSO be one the plugin escalated with.
                # A pattern key naming a pending forecast with a
                # DIFFERENT rule is not the key the plugin produced,
                # and accepting it would let a caller supply the
                # forecast id and choose the rule.
                pending = self._pending[forecast_id]
                if pending.rule != rule:
                    # The rule does not match the one the plugin
                    # escalated with. This is not the key the plugin
                    # produced, so it is not attributed.
                    self._orphans += 1
                    return None
                matched = forecast_id

        if matched is None and observed_tool:
            # The second channel: an exact tool_call_id match on a
            # pending escalation (EC-7 resolution step (a)).
            for forecast_id, pending in self._pending.items():
                if pending.tool_call_id and pending.tool_call_id == observed_tool:
                    matched = forecast_id
                    break

        if matched is None:
            if parsed is not None:
                # EC-2: the pattern is ours but no request was seen.
                self._orphans += 1
            return None

        # EC-7: more than one candidate would be ambiguous. A HUMAN_
        # APPROVED is never produced from an ambiguous match.
        if pending_forecasts is not None:
            candidates = [
                f for f in pending_forecasts
                if f == matched or self._pending.get(f) is not None
            ]
            if len(candidates) > 1:
                self._ambiguities += 1
                return None

        return matched

    # -- observations --------------------------------------------------

    def note_request(self, pattern_key: object, tool_call_id: object = "") -> Optional[str]:
        """Note that the host asked for approval.

        Returns the forecast id, or ``None`` for an orphan.
        """
        forecast_id = self.attribute(
            pattern_key=pattern_key,
            tool_call_id=tool_call_id,
            escalation_expected=True,
            pending_forecasts=tuple(self._pending),
        )
        if forecast_id is None:
            return None
        pending = self._pending.get(forecast_id)
        if pending is not None:
            pending.observed_request = True
        return forecast_id

    def note_response(self, pattern_key: object, tool_call_id: object = "") -> Optional[str]:
        """Note the human's answer.

        EC-3: the first observation of a given (tool_call_id,
        pattern_key, choice) wins. A duplicate is ignored **and
        counted**, and produces no second row.
        """
        forecast_id = self.attribute(
            pattern_key=pattern_key,
            tool_call_id=tool_call_id,
            escalation_expected=True,
            pending_forecasts=tuple(self._pending),
        )
        if forecast_id is None:
            return None
        pending = self._pending.get(forecast_id)
        if pending is None:
            return None
        if pending.observed_response:
            self._duplicates += 1
            return None
        pending.observed_response = True
        return forecast_id

    def note_tool_call(self, pattern_key: object, tool_call_id: object = "") -> Optional[str]:
        """Note that a tool call ran or was blocked.

        EC-6: a tool that ran with no approval request observed is
        ``AUTOMATICALLY_ALLOWED``; one that was blocked is
        ``AUTOMATICALLY_DENIED``.
        """
        return self.attribute(
            pattern_key=pattern_key,
            tool_call_id=tool_call_id,
            escalation_expected=True,
        )

    # -- housekeeping --------------------------------------------------

    def settle(self, forecast_id: str) -> None:
        """Forget a settled escalation."""
        pending = self._pending.pop(forecast_id, None)
        if pending is not None:
            self._by_pattern.pop(pending.pattern_key, None)

    def pending(self) -> Dict[str, PendingEscalation]:
        return dict(self._pending)

    def expired(self, now: float) -> Tuple[str, ...]:
        """The forecast ids whose deadline has passed (EC-5)."""
        return tuple(
            forecast_id
            for forecast_id, pending in self._pending.items()
            if pending.deadline is not None and pending.deadline <= now
        )

    @property
    def duplicates(self) -> int:
        return self._duplicates

    @property
    def orphans(self) -> int:
        return self._orphans

    @property
    def ambiguities(self) -> int:
        return self._ambiguities
