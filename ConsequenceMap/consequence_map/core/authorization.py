"""The hash-bound human authorization protocol.

This module defines what a ConsequenceMap approval IS, and how one is
checked. It does not sign anything: signing happens on an external
device the agent cannot reach (see the mobile authorization design). It
verifies.

The protocol
------------
A **proposal** is the operation the agent wants to perform. It is a plain
mapping. Its **proposal hash** is the SHA-256 of its canonical bytes under
the authorization domain.

An **authorization request** is what is shown to the human. It carries the
proposal itself - not just its hash - so the human can read what they are
approving, plus the fields a decision needs: who is asking, what scope is
requested, when it expires, and a nonce that makes this request unique.

An **authorization** is what the human's device returns. It carries:

- the ``proposal_hash`` the human actually saw and approved;
- the ``nonce`` of the request it answers;
- the identity of the approving key;
- the validity window;
- the signature over the canonical bytes of the authorization.

Verification is a sequence of independent checks. **Any one of them
failing means the authorization does not apply.** There is no path that
treats a missing check as a pass - that is the property the incident
audit found missing in the previous design.

Checks, in order:

1. the request is well formed and every mandatory field is present;
2. the authorization is well formed and every mandatory field is present;
3. the authorization's ``proposal_hash`` equals the **recomputed** hash of
   the proposal (not the hash carried in the request - that is the point);
4. the authorization's ``nonce`` equals the request's nonce;
5. the authorization's scope is equal to or narrower than the request's;
6. the authorization's ``expires_at`` is not later than the request's;
7. the current time is within the validity window;
8. the approving key is not revoked;
9. the signature verifies against the approving key's public key over the
   canonical bytes of the authorization.

Check 3 is what makes a later edit to the proposal invalid. Check 4 is
what makes a replay of an old approval against a new request fail.
"""
from __future__ import annotations

import hashlib
import os
from typing import Any, Mapping, Optional, Sequence, Tuple

from .timeutil import format_rfc3339, now_utc, parse_rfc3339
from .canonical import (
    CanonicalisationError,
    DOMAIN_AUTHORIZATION,
    canonical_bytes,
    domain_hash,
    strict_json_loads,
)

def _constant_time_equal(left: str, right: str) -> bool:
    """Compare two hex strings without leaking their contents by timing."""
    if len(left) != len(right):
        return False
    difference = 0
    for a, b in zip(left, right):
        difference |= ord(a) ^ ord(b)
    return difference == 0


__all__ = [
    "AuthorizationError",
    "AuthorizationInvalid",
    "AuthorizationExpired",
    "AuthorizationRevoked",
    "AuthorizationReplay",
    "AuthorizationScopeError",
    "MANDATORY_REQUEST_FIELDS",
    "MANDATORY_AUTHORIZATION_FIELDS",
    "build_request",
    "proposal_hash",
    "build_authorization",
    "verify_authorization",
    "new_nonce",
    "Signer",
    "Verifier",
    "InMemorySigner",
    "MAX_VALIDITY_SECONDS",
]


class AuthorizationError(Exception):
    """Base class for every authorization failure."""


class AuthorizationInvalid(AuthorizationError):
    """The authorization is malformed or does not match the proposal."""


class AuthorizationExpired(AuthorizationError):
    """The authorization is outside its validity window."""


class AuthorizationRevoked(AuthorizationError):
    """The approving key has been revoked."""


class AuthorizationReplay(AuthorizationError):
    """The authorization answers a different request (nonce mismatch)."""


class AuthorizationScopeError(AuthorizationError):
    """The authorization requests more than the request allows."""


#: Every field a request MUST carry.
MANDATORY_REQUEST_FIELDS: Sequence[str] = (
    "request_id",
    "proposal",  # the operation itself, so the approver can read it
    "proposal_hash",
    "nonce",
    "project",
    "operation",
    "requested_scope",
    "requested_by",
    "expires_at",
    "protocol_version",
)

#: Every field an authorization MUST carry.
MANDATORY_AUTHORIZATION_FIELDS: Sequence[str] = (
    "authorization_id",
    "request_id",
    "proposal_hash",
    "nonce",
    "approved_scope",
    "approved_by",
    "public_key_id",
    "valid_from",
    "expires_at",
    "signature",
    "protocol_version",
)

#: The longest a request may stay open, and the longest an
#: authorization may stay valid.
#:
#: This is the **exposure window** for a captured authorization. An
#: approval that is stolen can be used until it expires - and, before
#: the executor's spent-authorization set existed, until it was spent.
#: The shorter this is, the smaller the exposure.
#:
#: The value here is a **conservative default, not a decision**. The
#: real number is question Q-5 in the residual-risk register, and it
#: belongs to the project owner: it balances the exposure of a
#: captured approval against the time a human needs to answer. Until
#: that decision is made, the platform refuses anything longer than
#: this rather than accepting an unbounded window.
#:
#: The policy is a **parameter**, not a constant baked into the
#: protocol: a deployment given a different answer uses a different
#: value without changing the protocol.
MAX_VALIDITY_SECONDS = 3600


def _assert_window_is_bounded(
    valid_from: str,
    expires_at: str,
    *,
    max_seconds: int,
    what: str,
) -> None:
    """Refuse a validity window longer than the policy allows.

    The window is measured from ``valid_from`` to ``expires_at``. A
    window that starts in the past is fine - the human may have been
    given the request earlier - but it may not END further ahead than
    the policy allows.
    """
    start = parse_rfc3339(valid_from)
    end = parse_rfc3339(expires_at)
    span = (end - start).total_seconds()
    if span > max_seconds:
        raise AuthorizationInvalid(
            "%s is open for %d seconds, which is longer than the %d second "
            "policy allows" % (what, int(span), max_seconds)
        )


PROTOCOL_VERSION = "consequencemap.authorization.v1"


def new_nonce() -> str:
    """Return a fresh 256-bit nonce, hex encoded.

    ``os.urandom`` is the OS CSPRNG. The bytes are hashed with SHA-256
    before use so that the nonce's distribution does not depend on the
    entropy source's internal representation.
    """
    return hashlib.sha256(os.urandom(32)).hexdigest()


def proposal_hash(proposal: Mapping[str, Any]) -> str:
    """Return the canonical hash of a proposal."""
    return domain_hash(DOMAIN_AUTHORIZATION, {"proposal": proposal})


def build_request(
    *,
    proposal: Mapping[str, Any],
    project: str,
    operation: str,
    requested_scope: Sequence[str],
    requested_by: str,
    expires_at: str,
    request_id: Optional[str] = None,
    nonce: Optional[str] = None,
    max_validity_seconds: int = MAX_VALIDITY_SECONDS,
) -> Mapping[str, Any]:
    """Build an authorization request.

    ``expires_at`` is an RFC 3339 timestamp string. The caller decides the
    window; this module only records it and later checks the window.
    """
    # The expiry is parsed here, not later. A request carrying an
    # unparseable timestamp would be accepted here and rejected at
    # verification - and in between, it would be a request the agent
    # could hold open indefinitely.
    parse_rfc3339(expires_at)
    # A request may not ask for more time than the policy allows. The
    # window is measured from now, because a request has no valid_from:
    # it is being made now.
    _assert_window_is_bounded(
        format_rfc3339(now_utc()),
        expires_at,
        max_seconds=max_validity_seconds,
        what="the request",
    )
    request = {
        "request_id": request_id or ("req-" + os.urandom(16).hex()),
        "proposal": proposal,
        "proposal_hash": proposal_hash(proposal),
        "nonce": nonce or new_nonce(),
        "project": project,
        "operation": operation,
        "requested_scope": list(_as_scope(requested_scope, "requested_scope")),
        "requested_by": requested_by,
        "expires_at": expires_at,
        "protocol_version": PROTOCOL_VERSION,
    }
    return request


def build_authorization(
    *,
    request: Mapping[str, Any],
    approved_scope: Sequence[str],
    approved_by: str,
    public_key_id: str,
    valid_from: str,
    expires_at: str,
    signature: str,
    authorization_id: Optional[str] = None,
    max_validity_seconds: int = MAX_VALIDITY_SECONDS,
) -> Mapping[str, Any]:
    """Build an authorization over a request.

    ``signature`` is produced by the external signer over the canonical
    bytes of the authorization *without* the ``signature`` field. See
    :meth:`Signer.signing_payload`.
    """
    # Both window endpoints are parsed here, for the same reason.
    parse_rfc3339(valid_from)
    parse_rfc3339(expires_at)
    _assert_window_is_bounded(
        valid_from,
        expires_at,
        max_seconds=max_validity_seconds,
        what="the authorization",
    )
    return {
        "authorization_id": authorization_id or ("auth-" + os.urandom(16).hex()),
        "request_id": request["request_id"],
        "proposal_hash": request["proposal_hash"],
        "nonce": request["nonce"],
        "approved_scope": list(_as_scope(approved_scope, "approved_scope")),
        "approved_by": approved_by,
        "public_key_id": public_key_id,
        "valid_from": valid_from,
        "expires_at": expires_at,
        "signature": signature,
        "protocol_version": PROTOCOL_VERSION,
    }


def _require_fields(document: Mapping[str, Any], fields: Sequence[str], what: str) -> None:
    missing = [name for name in fields if name not in document]
    if missing:
        raise AuthorizationInvalid(
            "%s is missing mandatory field(s): %s" % (what, ", ".join(missing))
        )


def _as_scope(value: Any, what: str) -> Tuple[str, ...]:
    """Normalise a scope into a tuple of strings, or refuse it.

    A scope is a SET OF NAMES. A bare string is not a set of one name --
    it is an iterable of characters, and ``set("files:write")`` is
    ``{'f','i','l','e','s',':','w','r','t'}``. Accepting a string here
    would silently turn one scope into nine, and a comparison against
    another string could then succeed on a single shared character.

    So a string is rejected outright. The caller passes a list.
    """
    if isinstance(value, str):
        raise AuthorizationInvalid(
            "%s must be a list of names, not a string: a string would be "
            "read as a sequence of characters" % (what,)
        )
    if not isinstance(value, (list, tuple)):
        raise AuthorizationInvalid(
            "%s must be a list of names" % (what,)
        )
    for item in value:
        if not isinstance(item, str):
            raise AuthorizationInvalid(
                "%s must contain only strings" % (what,)
            )
    return tuple(value)


def _scope_is_subset(approved: Sequence[str], requested: Sequence[str]) -> bool:
    """True when ``approved`` grants nothing outside ``requested``."""
    return set(approved).issubset(set(requested))


class Signer:
    """Interface for an external signing device.

    A production implementation runs on the phone's secure hardware. This
    interface exists so the protocol can be tested without one, and so the
    protocol never has to know where the key lives.
    """

    def public_key_id(self) -> str:
        raise NotImplementedError

    def signing_payload(self, authorization: Mapping[str, Any]) -> bytes:
        """Return the bytes the signer signs.

        The signature field is removed, so the payload is the
        authorization without its own signature.
        """
        payload = {
            key: value
            for key, value in authorization.items()
            if key != "signature"
        }
        return canonical_bytes(DOMAIN_AUTHORIZATION, payload)

    def sign(self, authorization: Mapping[str, Any]) -> str:
        raise NotImplementedError


class Verifier:
    """Interface for verifying a signature against a public key."""

    def verify(self, public_key_id: str, payload: bytes, signature: str) -> bool:
        raise NotImplementedError


class InMemorySigner(Signer):
    """A test-only signer that uses HMAC as a stand-in for a real signature.

    **This is not a signature.** It proves the *protocol* - that a payload
    is bound, that tampering is detected, that replay fails. It proves
    nothing about unforgeability, because the key is in the same process.
    A production build MUST supply a real signer backed by a device the
    agent cannot reach.
    """

    def __init__(self, key_id: str, secret: Optional[bytes] = None) -> None:
        self._key_id = key_id
        self._secret = secret or os.urandom(32)

    def public_key_id(self) -> str:
        return self._key_id

    def sign(self, authorization: Mapping[str, Any]) -> str:
        return hashlib.blake2b(
            self.signing_payload(authorization), key=self._secret, digest_size=32
        ).hexdigest()


class InMemoryVerifier(Verifier):
    """A test-only verifier matching :class:`InMemorySigner`."""

    def __init__(self, secrets_by_key_id: Mapping[str, bytes]) -> None:
        self._secrets = dict(secrets_by_key_id)

    def verify(self, public_key_id: str, payload: bytes, signature: str) -> bool:
        secret = self._secrets.get(public_key_id)
        if secret is None:
            return False
        expected = hashlib.blake2b(
            payload, key=secret, digest_size=32
        ).hexdigest()
        # Constant-time comparison: a timing side channel on the MAC would
        # leak the expected value byte by byte.
        return _constant_time_equal(expected, signature)


def verify_authorization(
    *,
    proposal: Mapping[str, Any],
    request: Mapping[str, Any],
    authorization: Mapping[str, Any],
    verifier: Verifier,
    revoked_key_ids: Sequence[str] = (),
    now: Optional[str] = None,
    parse_timestamp=None,
    max_validity_seconds: Optional[int] = None,
) -> Mapping[str, Any]:
    """Verify that ``authorization`` authorises exactly ``proposal``.

    Returns the authorization on success. Raises the specific failure
    subclass otherwise. **Every** check is mandatory; there is no
    "best effort" path and no check whose failure is tolerated.

    ``now`` and ``parse_timestamp`` exist so the expiry check is testable
    without waiting. They default to the current UTC time and a strict
    RFC 3339 parser.
    """
    from .timeutil import now_utc

    parse = parse_timestamp or parse_rfc3339
    current = parse(now) if now is not None else now_utc()

    # 1 - the request is well formed
    _require_fields(request, MANDATORY_REQUEST_FIELDS, "request")
    # 2 - the authorization is well formed
    _require_fields(authorization, MANDATORY_AUTHORIZATION_FIELDS, "authorization")

    if authorization["protocol_version"] != PROTOCOL_VERSION:
        raise AuthorizationInvalid(
            "authorization protocol_version %r is not %r"
            % (authorization["protocol_version"], PROTOCOL_VERSION)
        )

    # 3 - the hash is RECOMPUTED from the proposal, not trusted from the request.
    #     And the request's OWN copy of the proposal must be the same
    #     document - otherwise the request could display one proposal and
    #     be verified against another. Two different documents, two
    #     different hashes, one authorization.
    if "proposal" in request:
        request_proposal = request["proposal"]
        if not isinstance(request_proposal, Mapping):
            raise AuthorizationInvalid(
                "the request's proposal must be a mapping"
            )
        try:
            request_hash = proposal_hash(request_proposal)
        except CanonicalisationError as exc:
            raise AuthorizationInvalid(
                "the request's proposal is not canonicalisable: %s" % (exc,)
            )
        try:
            recomputed = proposal_hash(proposal)
        except CanonicalisationError as exc:
            raise AuthorizationInvalid(
                "proposal is not canonicalisable: %s" % (exc,)
            )
        if request_hash != recomputed:
            raise AuthorizationInvalid(
                "the request's proposal does not match the proposal being "
                "verified: they hash to %s and %s"
                % (request_hash, recomputed)
            )
    try:
        recomputed = proposal_hash(proposal)
    except CanonicalisationError as exc:
        raise AuthorizationInvalid("proposal is not canonicalisable: %s" % (exc,))
    if authorization["proposal_hash"] != recomputed:
        raise AuthorizationInvalid(
            "authorization does not match the proposal: the proposal's "
            "canonical hash is %s, the authorization names %s"
            % (recomputed, authorization["proposal_hash"])
        )
    # The REQUEST carries its own copy of the proposal hash. That copy is
    # what the human was shown, so it must agree with the proposal too -
    # otherwise a request could display one hash and carry another.
    if request["proposal_hash"] != recomputed:
        raise AuthorizationInvalid(
            "request's proposal_hash %s does not match the proposal's "
            "canonical hash %s" % (request["proposal_hash"], recomputed)
        )

    # 4 - the request and the authorization must agree on what was asked
    if authorization["nonce"] != request["nonce"]:
        # The nonce is what makes each request unique. A mismatch means
        # this authorization was produced for a DIFFERENT request - the
        # replay case - whatever the request id says.
        raise AuthorizationReplay(
            "authorization nonce %r does not match the request nonce %r"
            % (authorization["nonce"], request["nonce"])
        )
    if authorization["request_id"] != request["request_id"]:
        raise AuthorizationInvalid(
            "authorization answers request %r, not %r"
            % (authorization["request_id"], request["request_id"])
        )

    # 5 - the authorization may not grant more than was requested
    approved_scope = _as_scope(authorization["approved_scope"], "approved_scope")
    requested_scope = _as_scope(request["requested_scope"], "requested_scope")
    if not _scope_is_subset(approved_scope, requested_scope):
        raise AuthorizationScopeError(
            "authorization approves %r, which is outside the requested scope %r"
            % (sorted(approved_scope), sorted(requested_scope))
        )

    # 6 - the authorization may not outlive the request
    if parse(authorization["expires_at"]) > parse(request["expires_at"]):
        raise AuthorizationInvalid(
            "authorization expires at %s, after the request's %s"
            % (authorization["expires_at"], request["expires_at"])
        )

    # 7 - the validity window must not exceed the policy. This is
    #     re-checked here, not only at construction, because the
    #     verifier is what grants the permission: a document built under
    #     a laxer policy must not be honoured under a stricter one.
    if max_validity_seconds is not None:
        _assert_window_is_bounded(
            authorization["valid_from"],
            authorization["expires_at"],
            max_seconds=max_validity_seconds,
            what="the authorization",
        )

    # 8 - the current time must be inside the validity window
    if current < parse(authorization["valid_from"]):
        raise AuthorizationExpired(
            "authorization is not valid until %s" % (authorization["valid_from"],)
        )
    if current > parse(authorization["expires_at"]):
        raise AuthorizationExpired(
            "authorization expired at %s" % (authorization["expires_at"],)
        )

    # 9 - revocation
    if authorization["public_key_id"] in set(revoked_key_ids):
        raise AuthorizationRevoked(
            "key %r is revoked" % (authorization["public_key_id"],)
        )

    # 10 - the signature
    payload = {
        key: value for key, value in authorization.items() if key != "signature"
    }
    try:
        payload_bytes = canonical_bytes(DOMAIN_AUTHORIZATION, payload)
    except CanonicalisationError as exc:
        raise AuthorizationInvalid("authorization is not canonicalisable: %s" % (exc,))
    if not verifier.verify(
        authorization["public_key_id"], payload_bytes, authorization["signature"]
    ):
        raise AuthorizationInvalid("signature does not verify")

    return authorization
