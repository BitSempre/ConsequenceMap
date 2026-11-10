"""The transport between the plugin and the Security Guard.

Why a named pipe
----------------
A named pipe is a local, kernel-mediated object. Three properties
matter, and each one is doing work:

- **Local only.** A pipe has no port and no network binding, so it is
  not reachable from another machine. A loopback socket would be, and
  a loopback socket's "only local" claim depends on the firewall.
- **ACL-enforced.** The pipe carries a security descriptor, and the
  kernel checks it on every connection. The service's own directory
  ACL is not enough: the pipe is the thing the plugin actually opens.
- **Attributable.** The service can ask the kernel who connected.
  A socket cannot be tied to a caller identity as directly.

Why the pipe name is not authentication
----------------------------------------
The pipe NAME proves nothing. Anything that can open the pipe can
send a message through it. So the service authenticates the CALLER:

- the service reads the client's process token (Windows), and
- compares the caller's SID against the policy's allowlist, and
- rejects a caller that is not allowed.

On this host the enforcement of that identity is a **seam**: the
``ClientAuthenticator`` interface, with a Windows implementation that
uses the pipe's client token and a reference implementation that
reports the identity it is given. The Windows path needs a real
service install and is NOT exercised here; the seam is, and it is
tested.

What the transport does NOT do
------------------------------
- It does not decide anything. A message that arrives is a claim.
- It does not execute anything.
- It does not hold the private key.
- It does not carry a decision back that the plugin can rely on
  without checking that the decision came from the service.

For the same reason, a response carries the decision AND the reason,
and the two must agree - a response claiming ``ALLOW`` with a reason
that reads like a refusal is a contradiction, and it is refused.
"""
from __future__ import annotations

import os
from typing import Any, Mapping, Optional, Sequence

from .protocol import (
    DECISION_ALLOW,
    DECISION_DENY,
    DECISION_INDETERMINATE,
    MessageTooLarge,
    ProtocolError,
    SchemaViolation,
    UnknownMessageType,
    UnknownVersion,
    build_request_message,
    parse_response_message,
)

__all__ = [
    "TransportError",
    "CallerRejected",
    "ClientAuthenticator",
    "WindowsPipeClientAuthenticator",
    "ReferenceClientAuthenticator",
    "Transport",
    "InProcessTransport",
    "PipeServerTransport",
    "PipeClientTransport",
    "DEFAULT_PIPE_NAME",
]

#: The pipe the service listens on. It is a LOCAL namespace pipe, so
#: it exists only on this machine and only for this session of the
#: machine's uptime (unless made persistent).
DEFAULT_PIPE_NAME = r"\\.\pipe\ConsequenceMapGuard"


class TransportError(Exception):
    """The transport could not carry the message."""


class CallerRejected(Exception):
    """The caller is not allowed to use this transport."""


class ClientAuthenticator:
    """Decides whether a caller may talk to the service.

    This is the seam where the trust boundary is enforced. The
    reference implementation says "yes" to whoever holds the token it
    was given; the Windows implementation reads the real client token.
    """

    def authenticate(self) -> Mapping[str, Any]:
        """Return the caller's identity, or raise :class:`CallerRejected`."""
        raise NotImplementedError

    def is_allowed(self, identity: Mapping[str, Any], allowed_sids: Sequence[str]) -> bool:
        """Whether this identity is on the allowlist."""
        sid = identity.get("sid")
        return bool(sid) and sid in set(allowed_sids)


class ReferenceClientAuthenticator(ClientAuthenticator):
    """A caller authenticator for tests and for the in-process transport.

    It reports the identity it was constructed with. It is NOT a
    security boundary: anyone who can construct one can claim any
    identity. It exists so that the *policy* around the boundary can
    be tested without a Windows service install.
    """

    def __init__(self, identity: Optional[Mapping[str, Any]] = None) -> None:
        self._identity = dict(identity or {"sid": "S-1-5-21-reference"})

    def authenticate(self) -> Mapping[str, Any]:
        return dict(self._identity)


class WindowsPipeClientAuthenticator(ClientAuthenticator):
    """The Windows implementation: read the client's token.

    On a real service, the server obtains the client's token from the
    pipe (``ImpersonateNamedPipeClient`` followed by
    ``GetTokenInformation``), reads the SID, and reverts the
    impersonation immediately.

    **This class cannot be exercised on this host.** It needs a real
    named-pipe server running as a service, which the mission forbids
    installing. It is here as the specification of what the production
    implementation must do, and the tests that touch it are marked as
    requiring an installed service.
    """

    def authenticate(self) -> Mapping[str, Any]:
        raise NotImplementedError(
            "the Windows client authenticator requires a running named-pipe "
            "service; it cannot be exercised without installing one"
        )


class Transport:
    """The interface a message travels over."""

    def send(self, message: Mapping[str, Any]) -> Mapping[str, Any]:
        """Send a message and return the response."""
        raise NotImplementedError


class InProcessTransport(Transport):
    """A transport that calls the service directly.

    This is the DEVELOPMENT transport. It provides no boundary at all -
    the caller is in the same process as the service. It says so, and
    the service it is wired to is told so, so that a deployment cannot
    accidentally claim a boundary it does not have.
    """

    #: Whether this transport actually provides a trust boundary. It
    #: does NOT.
    provides_boundary = False

    def __init__(self, service) -> None:
        self._service = service

    def send(self, message: Mapping[str, Any]) -> Mapping[str, Any]:
        return self._service.handle_safe(message)


class PipeServerTransport(Transport):
    """The service side of the named pipe.

    The server accepts a connection, authenticates the caller,
    enforces the size limit, parses the message, and hands it to the
    service. It never decides anything itself.
    """

    provides_boundary = True

    def __init__(
        self,
        service,
        authenticator: ClientAuthenticator,
        *,
        allowed_sids: Sequence[str] = (),
        pipe_name: str = DEFAULT_PIPE_NAME,
        max_bytes: int = 64 * 1024,
    ) -> None:
        self._service = service
        self._authenticator = authenticator
        self._allowed_sids = tuple(allowed_sids)
        self._pipe_name = pipe_name
        self._max_bytes = max_bytes

    def pipe_name(self) -> str:
        return self._pipe_name

    def authenticate_caller(self) -> Mapping[str, Any]:
        """Authenticate the caller and check it against the allowlist.

        The check happens BEFORE the message is read. A caller that is
        not allowed never gets to send a message.
        """
        try:
            identity = self._authenticator.authenticate()
        except CallerRejected:
            raise
        except Exception as exc:
            raise CallerRejected(
                "the caller could not be authenticated: %s" % (exc,)
            ) from exc
        if not self._authenticator.is_allowed(identity, self._allowed_sids):
            raise CallerRejected(
                "the caller %r is not allowed to use this service"
                % (identity.get("sid"),)
            )
        return identity

    def serve_connection(self, raw: Any) -> Mapping[str, Any]:
        """Handle one connection's payload."""
        self.authenticate_caller()
        from .protocol import parse_request_message

        try:
            message = parse_request_message(raw, max_bytes=self._max_bytes)
        except (ProtocolError, MessageTooLarge, SchemaViolation,
                UnknownMessageType, UnknownVersion) as exc:
            return {
                "message_type": "execution.response",
                "protocol_version": "consequencemap.guard.ipc.v1",
                "decision": DECISION_DENY,
                "reason": "the request is not valid: %s" % (exc,),
                "operation_id": "",
            }
        return self._service.handle_safe(message)


class PipeClientTransport(Transport):
    """The plugin side of the named pipe.

    The plugin opens the pipe, sends the request, and reads the
    response. It holds no key, no policy and no store. If the service
    is unavailable, the plugin is told so and the operation does not
    happen - there is no local fallback, because a local fallback is
    exactly the path the agent would use.
    """

    provides_boundary = False

    def __init__(self, pipe_name: str = DEFAULT_PIPE_NAME) -> None:
        self._pipe_name = pipe_name

    def pipe_name(self) -> str:
        return self._pipe_name

    def send(self, message: Mapping[str, Any]) -> Mapping[str, Any]:
        """Send a message over the pipe.

        The Windows implementation opens the pipe with
        ``CreateFile`` and reads a length-prefixed frame. It is not
        exercised on this host.
        """
        raise NotImplementedError(
            "the pipe client requires a running named-pipe service; it "
            "cannot be exercised without installing one"
        )
