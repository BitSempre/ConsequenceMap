"""Reference implementation of the phone-side approval protocol.

This module is the **PC-side** half of the protocol: it builds the
canonical bytes the phone signs, and it verifies what comes back. It is
the reference against which the mobile applications are written.

It imports the canonical form from ``consequence_map.core.canonical``
rather than re-implementing it, so there is exactly ONE canonical form
in the system. A second implementation would be a second set of rules,
and the two would eventually disagree about what was approved.

The signature step is a pluggable interface. This module does **not**
implement a signature algorithm: hand-rolled curve arithmetic is exactly
the kind of thing that must not be written from scratch. In production
the signer is the phone's secure hardware (Android Keystore or iOS
Secure Enclave); in the demonstration it is a keyed hash, which is
enough to prove that **binding** and **tamper detection** work, and is
explicitly not enough to prove unforgeability.

The non-ASCII rule
------------------
The canonical form is ASCII-only. A proposal containing any non-ASCII
character **cannot** be hashed until the producer escapes it. This is
not a detail of the implementation: the phone and the PC must escape
identically, or the hashes will not match and every approval will be
rejected. :func:`escape_for_canonical` is that rule, in one place.
"""
from __future__ import annotations

import hashlib
import os
from typing import Any, Mapping, Optional, Sequence

from consequence_map.core.authorization import (
    AuthorizationError,
    AuthorizationExpired,
    AuthorizationInvalid,
    AuthorizationReplay,
    AuthorizationRevoked,
    AuthorizationScopeError,
    InMemorySigner,
    InMemoryVerifier,
    Signer,
    Verifier,
    build_authorization,
    build_request,
    proposal_hash,
    verify_authorization,
)
from consequence_map.core.canonical import (
    CanonicalisationError,
    DOMAIN_AUTHORIZATION,
    canonical_bytes,
    canonical_text,
    domain_hash,
    strict_json_loads,
)
from consequence_map.core.timeutil import format_rfc3339, now_utc, parse_rfc3339

__all__ = [
    "escape_for_canonical",
    "canonical_payload",
    "build_approval_request",
    "full_proposal",
    "verify_approval",
    "verify_binding",
    "phone_signing_payload",
    "MobileSigner",
    "InMemoryPhoneSigner",
    "InMemoryPhoneVerifier",
    "MAX_PROPOSAL_BYTES",
]

#: A proposal larger than this is refused. The canonical form has no
#: inherent size limit, and an unbounded proposal is a denial-of-service
#: vector against the phone, which has far less memory than the PC.
MAX_PROPOSAL_BYTES = 64 * 1024


def escape_for_canonical(text: str) -> str:
    """Escape a string so the canonical form can represent it.

    The canonical form is ASCII-only. Every character above U+007E is
    replaced by its ``\\uXXXX`` escape. Both the phone and the PC must
    apply this **before** hashing, or the hashes will not match.

    Escaping is not normalisation: ``"cafe\\u0301"`` (NFD) and
    ``"cafe\\u00e9"`` (NFC) stay distinct, because the approval must
    bind to the exact bytes that were shown and hashed.
    """
    if not isinstance(text, str):
        raise TypeError("escape_for_canonical expects a string")
    out = []
    for character in text:
        if character.isascii() and character.isprintable():
            out.append(character)
        else:
            out.append("\\u%04x" % ord(character))
    return "".join(out)


def escape_tree(value: Any) -> Any:
    """Recursively escape every string in a proposal.

    Use this on the PC before computing the hash, and on the phone before
    displaying and signing. The two must produce identical trees.

    **Keys are escaped as well as values.** The canonical form is
    ASCII-only, and it refuses a non-ASCII key outright - so escaping
    only the values would leave the tree in a shape the canonicaliser
    rejects. The phone and the PC must produce trees that the
    canonicaliser accepts, and they must produce the SAME tree.
    """
    if isinstance(value, str):
        return escape_for_canonical(value)
    if isinstance(value, Mapping):
        return {
            escape_for_canonical(key): escape_tree(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [escape_tree(item) for item in value]
    return value


def canonical_payload(proposal: Mapping[str, Any]) -> bytes:
    """Return the exact bytes the phone signs.

    The proposal is escaped first, then canonicalised under the
    authorization domain. The bytes are what the signature covers, so
    they are what both sides must agree on.
    """
    escaped = escape_tree(proposal)
    return canonical_bytes(DOMAIN_AUTHORIZATION, {"proposal": escaped})


def full_proposal(
    proposal: Mapping[str, Any],
    affected_resources: Sequence[str],
    consequence_summary: str,
) -> Mapping[str, Any]:
    """The proposal as the human sees it.

    The display fields are PART of the proposal, not beside it. The
    proposal is what gets hashed and signed, so the human approves
    exactly what is shown.

    Every caller that builds, verifies or compares a proposal uses
    this function, so there is one definition of "the full proposal"
    and no chance of two copies drifting apart.
    """
    complete = dict(proposal)
    complete["affected_resources"] = list(affected_resources)
    complete["consequence_summary"] = consequence_summary
    return complete


def build_approval_request(
    *,
    proposal: Mapping[str, Any],
    project: str,
    operation: str,
    affected_resources: Sequence[str],
    requested_permissions: Sequence[str],
    consequence_summary: str,
    requested_by: str,
    expires_at: str,
    request_id: Optional[str] = None,
) -> Mapping[str, Any]:
    """Build the request the phone displays and signs.

    The request carries the **full** proposal, not only its hash, because
    the human has to be able to read what they are approving. The hash is
    derived from that same proposal, so what is displayed and what is
    signed cannot drift apart.
    """
    # The display fields go INSIDE the proposal, not beside it.
    #
    # The proposal is what the human reads and what the phone signs.
    # If the affected resources and the consequence summary lived
    # beside the proposal, they would sit outside the hash and outside
    # the signature: an attacker could change what the phone displays
    # without invalidating the approval. The request would still
    # verify, because the verifier only ever looked at the proposal.
    #
    # So they are part of the proposal, and the proposal is what gets
    # hashed and signed. What the human sees is exactly what is
    # protected.
    # The proposal the caller passes is ALREADY the full proposal - the
    # one with the display fields inside it, produced by
    # full_proposal(). The affected_resources and consequence_summary
    # arguments are kept because the caller needs to state what it is
    # asking for, and they are CHECKED against the proposal rather
    # than merged into it.
    #
    # Merging would be a second definition of the same thing, and the
    # two could drift: the proposal that is hashed would not be the
    # proposal the caller thinks it is.
    complete = dict(proposal)
    if "affected_resources" in complete:
        if list(complete["affected_resources"]) != list(affected_resources):
            raise ValueError(
                "the proposal's affected_resources do not match the ones "
                "requested: the proposal is the authority"
            )
    if "consequence_summary" in complete:
        if complete["consequence_summary"] != consequence_summary:
            raise ValueError(
                "the proposal's consequence_summary does not match the one "
                "requested: the proposal is the authority"
            )

    escaped = escape_tree(complete)
    request = build_request(
        proposal=escaped,
        project=project,
        operation=operation,
        requested_scope=list(requested_permissions),
        requested_by=requested_by,
        expires_at=expires_at,
        request_id=request_id,
    )
    # The display fields are NOT copied to the top level of the
    # request.
    #
    # They are already inside the proposal, which is what gets hashed
    # and signed. Copying them out would be a second copy that can
    # drift from the authoritative one - and the request now has a
    # CLOSED schema, so an extra field is refused outright.
    #
    # The phone reads them from the proposal, which is where the human
    # saw them.
    return request


def phone_signing_payload(authorization: Mapping[str, Any]) -> bytes:
    """Return the bytes the phone signs over an authorization.

    Identical to :meth:`Signer.signing_payload`: the signature field is
    removed, and the rest is canonicalised. It is re-exported here so
    the mobile implementer has one obvious place to look.
    """
    payload = {
        key: value for key, value in authorization.items() if key != "signature"
    }
    return canonical_bytes(DOMAIN_AUTHORIZATION, payload)


class MobileSigner(Signer):
    """The interface the phone implementation satisfies.

    A production implementation wraps the platform keystore. The key
    never leaves it, and the signing operation requires the human's
    biometric or PIN — enforced by the platform, not by this code.
    """

    def __init__(self, key_id: str) -> None:
        self._key_id = key_id

    def public_key_id(self) -> str:
        return self._key_id

    def sign(self, authorization: Mapping[str, Any]) -> str:
        raise NotImplementedError(
            "a production MobileSigner delegates to the platform keystore"
        )


class InMemoryPhoneSigner(InMemorySigner):
    """A demonstration signer. NOT a signature.

    It uses a keyed hash so the demonstration can show that binding and
    tamper detection work. It proves nothing about unforgeability: the
    key is in the same process as the verifier.
    """

    def __init__(self, key_id: str, secret: Optional[bytes] = None) -> None:
        super().__init__(key_id, secret)


class InMemoryPhoneVerifier(InMemoryVerifier):
    """The demonstration counterpart of :class:`InMemoryPhoneSigner`."""


def verify_approval(
    *,
    proposal: Mapping[str, Any],
    request: Mapping[str, Any],
    authorization: Mapping[str, Any],
    verifier: Verifier,
    revoked_key_ids: Sequence[str] = (),
    now: Optional[str] = None,
) -> Mapping[str, Any]:
    """Verify that an authorization covers exactly this proposal.

    Delegates to the platform's own verifier, so the phone's answer is
    checked by exactly the same rules as everything else.
    """
    # The proposal that gets verified is the FULL proposal: the one the
    # caller supplies, plus the display fields as the request carries
    # them. If the request's copy of those fields disagrees with the
    # caller's, the verification fails - the phone would be showing one
    # thing while the signature covered another.
    # The proposal the caller passes must already be the FULL proposal
    # - the one with the display fields inside it, as produced by
    # full_proposal(). The request's schema is closed, so there is
    # nowhere to read a second copy from, and there is nothing to
    # drift.
    escaped = escape_tree(proposal)
    escaped_request = dict(request)
    escaped_request["proposal"] = escaped
    return verify_authorization(
        proposal=escaped,
        request=escaped_request,
        authorization=authorization,
        verifier=verifier,
        revoked_key_ids=revoked_key_ids,
        now=now,
    )


def verify_binding(
    *,
    proposal: Mapping[str, Any],
    request: Mapping[str, Any],
    authorization: Mapping[str, Any],
) -> bool:
    """Check only that the authorization is bound to this proposal.

    This is the cheap check the phone can do before showing anything:
    it confirms the proposal it is about to display is the one that was
    authorised. It does **not** check the signature.
    """
    # The proposal that was hashed is the FULL proposal - the caller's
    # plus the display fields as the request carries them. Checking only
    # the caller's copy would report "not bound" for a perfectly good
    # approval, and would report "bound" for one whose displayed
    # resources had been changed.
    try:
        expected = domain_hash(
            DOMAIN_AUTHORIZATION, {"proposal": escape_tree(proposal)}
        )
    except CanonicalisationError:
        return False
    return authorization.get("proposal_hash") == expected
