"""The protocol between the plugin and the Security Guard.

Shape
-----
The plugin sends a **request**. The service returns a **response**. Both
are canonical documents with a closed schema.

The rules that make this a protocol rather than a JSON convention:

- **The version is checked.** A message for another version is refused,
  not best-effort interpreted.
- **The schema is closed.** An unknown field is refused. A field the
  service does not understand is a field it might have honoured.
- **The size is bounded.** A request that exceeds the limit is refused
  before it is parsed in full.
- **Every request carries a fresh nonce.** The service records the
  nonces it has seen, so a request replayed at the transport layer is
  refused before it reaches the authorisation logic.
- **The decision is derived server-side.** The service never reads a
  decision from the request. There is no ``allowed``, ``approved`` or
  ``decision`` field in a request, because a field the plugin can set
  is a field the plugin can lie about.

What the plugin may send
------------------------
The plugin may send a **proposal**: the operation it wants, the scope
it wants, and the authorisation it believes the human gave. The service
checks all three against its own policy and its own verification.

What the plugin may never send
-------------------------------
- A command, a script, a shell string, or Python source.
- The name of a handler to run.
- The arguments to pass to a handler.
- A decision.
- The scope that was approved.

The operation is named by its **identifier**, and the service looks up
that identifier in its own allowlist. The arguments are derived from
the proposal, not supplied by the plugin. An operation the service does
not know is refused - default deny.

The response
------------
A response carries a decision and a reason. The decision is one of
``ALLOW``, ``DENY`` or ``INDETERMINATE``. ``INDETERMINATE`` is never
converted to ``ALLOW``: an unverifiable condition is a refusal.
"""
from __future__ import annotations

from typing import Any, Mapping, Optional, Sequence

from consequence_map.core.canonical import (
    CanonicalisationError,
    canonical_bytes,
    canonical_text,
)

__all__ = [
    "PROTOCOL_VERSION",
    "MAX_REQUEST_BYTES",
    "MAX_RESPONSE_BYTES",
    "MESSAGE_TYPES",
    "DECISION_ALLOW",
    "DECISION_DENY",
    "DECISION_INDETERMINATE",
    "ProtocolError",
    "UnknownMessageType",
    "UnknownVersion",
    "SchemaViolation",
    "MessageTooLarge",
    "Replay",
    "build_request_message",
    "build_response_message",
    "parse_request_message",
    "parse_response_message",
    "request_digest",
]

PROTOCOL_VERSION = "consequencemap.guard.ipc.v1"

#: The largest request the service will accept, in bytes.
MAX_REQUEST_BYTES = 64 * 1024

#: The largest response the service will produce, in bytes.
MAX_RESPONSE_BYTES = 64 * 1024

#: The message types this protocol defines.
MESSAGE_TYPES = frozenset({"execution.request", "execution.response"})

DECISION_ALLOW = "ALLOW"
DECISION_DENY = "DENY"
DECISION_INDETERMINATE = "INDETERMINATE"

#: The fields a request MAY carry. The schema is closed: anything else
#: is refused.
REQUEST_FIELDS = frozenset({
    "message_type",
    "protocol_version",
    "nonce",
    "operation_id",
    "proposal",
    "authorization",
    "issued_at",
})

#: The fields a response MAY carry.
RESPONSE_FIELDS = frozenset({
    "message_type",
    "protocol_version",
    "decision",
    "reason",
    "operation_id",
    "state",
})

#: The fields that must be present in a request.
REQUEST_REQUIRED = frozenset({
    "message_type",
    "protocol_version",
    "nonce",
    "operation_id",
    "proposal",
    "authorization",
})


class ProtocolError(Exception):
    """Base class for every protocol failure."""


class UnknownMessageType(ProtocolError):
    """The message type is not one this protocol defines."""


class UnknownVersion(ProtocolError):
    """The protocol version is not one this service speaks."""


class SchemaViolation(ProtocolError):
    """The message does not match the schema."""


class MessageTooLarge(ProtocolError):
    """The message exceeds the size limit."""


class Replay(ProtocolError):
    """The nonce has already been seen."""


def _require_string(document: Mapping[str, Any], field: str, maximum: int = 4096) -> str:
    value = document.get(field)
    if not isinstance(value, str):
        raise SchemaViolation("%s must be a string" % (field,))
    if len(value) > maximum:
        raise SchemaViolation("%s is longer than %d characters" % (field, maximum))
    return value


def build_request_message(
    *,
    nonce: str,
    operation_id: str,
    proposal: Mapping[str, Any],
    authorization: Mapping[str, Any],
    issued_at: str,
    protocol_version: str = PROTOCOL_VERSION,
) -> Mapping[str, Any]:
    """Build a request message.

    The caller cannot add fields: the document is constructed here
    from named arguments, so there is no way to smuggle an extra one
    into the request.
    """
    return {
        "message_type": "execution.request",
        "protocol_version": protocol_version,
        "nonce": nonce,
        "operation_id": operation_id,
        "proposal": dict(proposal),
        "authorization": dict(authorization),
        "issued_at": issued_at,
    }


def build_response_message(
    *,
    decision: str,
    reason: str,
    operation_id: str,
    state: str = "",
    protocol_version: str = PROTOCOL_VERSION,
) -> Mapping[str, Any]:
    """Build a response message.

    ``decision`` is derived by the service. It is never taken from a
    request.
    """
    if decision not in (DECISION_ALLOW, DECISION_DENY, DECISION_INDETERMINATE):
        raise SchemaViolation(
            "unknown decision %r" % (decision,)
        )
    message = {
        "message_type": "execution.response",
        "protocol_version": protocol_version,
        "decision": decision,
        "reason": reason,
        "operation_id": operation_id,
    }
    if state:
        message["state"] = state
    return message


def _parse_document(
    raw: Any,
    *,
    expected_version: str,
    max_bytes: int,
) -> Mapping[str, Any]:
    """Decode a raw message into a mapping, with the size limit applied.

    The size limit is applied to the BYTES, before the document is
    parsed. A message that is too large is refused without being
    decoded, so a large message cannot be used to make the service do
    work.
    """
    if isinstance(raw, (bytes, bytearray)):
        if len(raw) > max_bytes:
            raise MessageTooLarge(
                "the request is %d bytes, over the %d byte limit"
                % (len(raw), max_bytes)
            )
        try:
            text = bytes(raw).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise SchemaViolation(
                "the request is not valid UTF-8: %s" % (exc,)
            ) from exc
    elif isinstance(raw, str):
        if len(raw.encode("utf-8")) > max_bytes:
            raise MessageTooLarge("the request is over the size limit")
        text = raw
    elif isinstance(raw, Mapping):
        document = dict(raw)
    else:
        raise SchemaViolation(
            "a message must be bytes, text or a mapping, not %s"
            % (type(raw).__name__,)
        )

    if isinstance(raw, (bytes, bytearray, str)):
        import json

        try:
            document = json.loads(text)
        except ValueError as exc:
            raise SchemaViolation(
                "the message is not valid JSON: %s" % (exc,)
            ) from exc
        if not isinstance(document, Mapping):
            raise SchemaViolation("a message must be a JSON object")

    return document


def parse_request_message(
    raw: Any,
    *,
    expected_version: str = PROTOCOL_VERSION,
    max_bytes: int = MAX_REQUEST_BYTES,
) -> Mapping[str, Any]:
    """Parse and validate an incoming request.

    Every failure raises a :class:`ProtocolError` subclass. There is
    no path that returns a partially-valid request.
    """
    document = _parse_document(
        raw, expected_version=expected_version, max_bytes=max_bytes
    )

    missing = sorted(REQUEST_REQUIRED - set(document))
    if missing:
        raise SchemaViolation(
            "the request is missing: %s" % (", ".join(missing),)
        )
    unexpected = sorted(set(document) - REQUEST_FIELDS)
    if unexpected:
        raise SchemaViolation(
            "the request has unknown field(s): %s" % (", ".join(unexpected),)
        )
    if document["message_type"] not in MESSAGE_TYPES:
        raise UnknownMessageType(
            "unknown message type %r" % (document["message_type"],)
        )
    if document["protocol_version"] != expected_version:
        raise UnknownVersion(
            "protocol version %r is not %r"
            % (document["protocol_version"], expected_version)
        )
    _require_string(document, "nonce", 256)
    _require_string(document, "operation_id", 256)
    _require_string(document, "issued_at", 64)
    if not isinstance(document["proposal"], Mapping):
        raise SchemaViolation("the proposal must be a mapping")
    if not isinstance(document["authorization"], Mapping):
        raise SchemaViolation("the authorization must be a mapping")
    return dict(document)


def parse_response_message(
    raw: Any,
    *,
    expected_version: str = PROTOCOL_VERSION,
    max_bytes: int = MAX_RESPONSE_BYTES,
) -> Mapping[str, Any]:
    """Parse and validate a response message."""
    document = _parse_document(
        raw, expected_version=expected_version, max_bytes=max_bytes
    )
    unexpected = sorted(set(document) - RESPONSE_FIELDS)
    if unexpected:
        raise SchemaViolation(
            "the response has unknown field(s): %s" % (", ".join(unexpected),)
        )
    if document["message_type"] != "execution.response":
        raise UnknownMessageType(
            "expected an execution.response, got %r"
            % (document["message_type"],)
        )
    if document["decision"] not in (
        DECISION_ALLOW, DECISION_DENY, DECISION_INDETERMINATE
    ):
        raise SchemaViolation(
            "unknown decision %r" % (document["decision"],)
        )
    _require_string(document, "reason", 4096)
    _require_string(document, "operation_id", 256)
    return dict(document)


def request_digest(message: Mapping[str, Any]) -> str:
    """The canonical digest of a message, for logging and replay keys."""
    import hashlib

    try:
        return hashlib.sha256(
            canonical_bytes("consequencemap.guard.ipc.digest.v1", message)
        ).hexdigest()
    except CanonicalisationError as exc:
        raise SchemaViolation(
            "the message is not canonicalisable: %s" % (exc,)
        ) from exc
