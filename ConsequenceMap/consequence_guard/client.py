"""The plugin-side client of the Security Guard.

This is what the plugin calls. It can PROPOSE and it can ASK. It
cannot decide, it cannot consume an authorisation, and it cannot
execute an operation.

The important property is what it does NOT contain:

- no private key;
- no policy;
- no store;
- no fallback path that executes anything locally.

If the service is unavailable, the operation does not happen and the
plugin is told why. A local fallback would be precisely the hole the
architecture exists to close: the agent controls the plugin, so any
capability the plugin can exercise without the service is a capability
the agent has.
"""
from __future__ import annotations

from typing import Any, Mapping, Optional

from .ipc import InProcessTransport, PipeClientTransport, Transport
from .protocol import (
    DECISION_ALLOW,
    DECISION_DENY,
    DECISION_INDETERMINATE,
    build_request_message,
    parse_response_message,
)

__all__ = ["GuardClient", "ClientUnavailable"]


class ClientUnavailable(Exception):
    """The Security Guard could not be reached.

    The caller must treat this as a refusal. There is no fallback.
    """


class GuardClient:
    """The plugin's window onto the Security Guard."""

    def __init__(self, transport: Optional[Transport] = None) -> None:
        self._transport = transport if transport is not None else PipeClientTransport()

    def transport(self) -> Transport:
        return self._transport

    def request_execution(
        self,
        *,
        nonce: str,
        operation_id: str,
        proposal: Mapping[str, Any],
        authorization: Mapping[str, Any],
        issued_at: str,
    ) -> Mapping[str, Any]:
        """Ask the guard to perform an operation.

        Returns the guard's response. The plugin does NOT interpret it
        as permission on its own authority: the response says the
        service decided, and the plugin presents it.
        """
        message = build_request_message(
            nonce=nonce,
            operation_id=operation_id,
            proposal=proposal,
            authorization=authorization,
            issued_at=issued_at,
        )
        try:
            response = self._transport.send(message)
        except Exception as exc:
            raise ClientUnavailable(
                "the Security Guard could not be reached: %s" % (exc,)
            ) from exc
        try:
            return parse_response_message(response)
        except Exception as exc:
            raise ClientUnavailable(
                "the Security Guard's response could not be understood: %s"
                % (exc,)
            ) from exc

    def is_allowed(self, response: Mapping[str, Any]) -> bool:
        """Whether the guard allowed the operation.

        This reads the DECISION, not a separate boolean. A response
        carrying both a decision and a contradictory flag is refused
        by the protocol layer before it reaches here.
        """
        return response.get("decision") == DECISION_ALLOW
