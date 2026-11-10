"""Real cryptographic signing for the authorization protocol.

This module replaces the placeholder keyed-hash signer with **Ed25519**
signatures produced by the ``cryptography`` library.

Why this module exists
----------------------
The in-memory signer proved the *protocol*: that a payload is bound,
that tampering is detected, that a replay fails. It proved nothing
about unforgeability, because the key was in the same process as the
verifier. An agent that controls the process controls the key.

A signature is different in kind from a hash:

- a **hash** gives integrity: "these bytes have not changed". It says
  nothing about *who* produced them. Anyone can hash.
- a **signature** gives authenticity and integrity together: "these
  bytes were produced by the holder of this private key, and have not
  changed since". That requires a private key the verifier does not
  hold.
- a **signature does not prove the content is TRUE.** It proves the
  content is authentic and intact under the keys and protocol in use.
  Whether the approved operation is *wise* remains a human judgement.
- a **signature is not an authorization.** It is evidence that a
  specific party approved a specific document. The authorization is the
  decision the platform derives from that evidence, and the execution is
  the effect. Four different things.

What this module does NOT do
----------------------------
- It does not implement any cryptographic primitive. Ed25519 comes from
  the ``cryptography`` library.
- It does not store private keys. A private key is loaded from a
  provider the caller supplies; this module never writes one to disk.
- It does not decide anything. It signs and verifies. The decision is
  derived elsewhere, from the verification result.

Algorithm agility
-----------------
The algorithm is named in the document, and only algorithms on the
allowlist are honoured. An unknown or unauthorised algorithm id is
**rejected outright**, not treated as a verification failure: a
document that names an algorithm we do not implement is not a document
we failed to verify, it is a document we do not understand.

The canonical form
-------------------
What gets signed is the canonical bytes of the authorization document
with the ``signature`` field removed, under the authorization domain.
Removing exactly one named field is the rule - not "the fields we
recognise". That distinction matters: if the rule were "strip the
fields we know about", an attacker could ADD an unknown field and have
it excluded from the signed payload. The rule is "strip the field named
``signature``, sign everything else, including any field we do not
recognise". An unknown field therefore **changes the bytes that are
signed**, and a signature over the original document will not verify
against the modified one.
"""
from __future__ import annotations

import base64
import binascii
import os
from typing import Any, Mapping, Optional, Sequence

from consequence_map.core.authorization import Signer, Verifier
from consequence_map.core.canonical import CanonicalisationError, canonical_bytes

__all__ = [
    "CryptoError",
    "UnknownAlgorithm",
    "UnknownKey",
    "MalformedSignature",
    "MalformedPublicKey",
    "ALGORITHMS",
    "ALGORITHM_ED25519",
    "Ed25519Signer",
    "Ed25519Verifier",
    "KeyRegistry",
    "encode_public_key",
    "decode_public_key",
    "encode_signature",
    "decode_signature",
    "generate_private_key",
]


class CryptoError(Exception):
    """Base class for every cryptographic failure."""


class UnknownAlgorithm(CryptoError):
    """The document names an algorithm that is not on the allowlist."""


class UnknownKey(CryptoError):
    """The document names a key this verifier does not know."""


class MalformedSignature(CryptoError):
    """The signature is not a well-formed value of the named algorithm."""


class MalformedPublicKey(CryptoError):
    """The public key is not a well-formed value of the named algorithm."""


#: The identifier for Ed25519. It is a NAME, not a choice: a document
#: carries this string, and the allowlist maps it to an implementation.
ALGORITHM_ED25519 = "ed25519"

#: The algorithms this implementation is willing to verify.
#:
#: This is an ALLOWLIST, not a registry of what exists. An algorithm
#: that is not here is refused. Adding one is a deliberate act with a
#: security review behind it, not a side effect of installing a library.
ALGORITHMS = frozenset({ALGORITHM_ED25519})


def _ed25519():
    """Import Ed25519 from ``cryptography`` or fail clearly.

    The import is local so that the module can be imported (and its
    absence detected and reported) without a stack trace at import
    time, which would be indistinguishable from a broken install.
    """
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PrivateKey,
            Ed25519PublicKey,
        )
    except ImportError as exc:  # pragma: no cover - environment specific
        raise CryptoError(
            "Ed25519 support requires the 'cryptography' package: %s" % (exc,)
        ) from exc
    return Ed25519PrivateKey, Ed25519PublicKey


def generate_private_key():
    """Generate a fresh Ed25519 private key.

    The key is returned as an object. It is never written to disk by
    this module: where a private key lives is the caller's decision, and
    on the target architecture it is the phone's secure hardware.
    """
    Ed25519PrivateKey, _ = _ed25519()
    return Ed25519PrivateKey.generate()


def encode_public_key(public_key) -> str:
    """Encode an Ed25519 public key as base64url without padding.

    The raw 32 bytes are the canonical encoding. base64url makes the
    key safe to carry in JSON, a URL, or a QR code without escaping.
    Padding is omitted so that the encoding has exactly one form -
    ``=``-padded and unpadded base64 are the same value but different
    strings, and a string comparison would treat them as different
    keys.
    """
    _, Ed25519PublicKey = _ed25519()
    if isinstance(public_key, Ed25519PublicKey):
        raw = public_key.public_bytes_raw()
    else:
        raw = bytes(public_key)
    if len(raw) != 32:
        raise MalformedPublicKey(
            "an Ed25519 public key is 32 bytes, got %d" % (len(raw),)
        )
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_public_key(encoded: str):
    """Decode a base64url (unpadded) Ed25519 public key."""
    if not isinstance(encoded, str):
        raise MalformedPublicKey("a public key must be a string")
    padding = "=" * (-len(encoded) % 4)
    try:
        raw = base64.urlsafe_b64decode(encoded + padding)
    except (binascii.Error, ValueError) as exc:
        raise MalformedPublicKey(
            "the public key is not valid base64url: %s" % (exc,)
        ) from exc
    if len(raw) != 32:
        raise MalformedPublicKey(
            "an Ed25519 public key is 32 bytes, got %d" % (len(raw),)
        )
    _, Ed25519PublicKey = _ed25519()
    return Ed25519PublicKey.from_public_bytes(raw)


def encode_signature(signature: bytes) -> str:
    """Encode a signature as base64url without padding.

    A signature is 64 bytes. base64url is used for the same reason as
    for the public key: one canonical string form, safe in JSON and in
    a URL.
    """
    return base64.urlsafe_b64encode(bytes(signature)).decode("ascii").rstrip("=")


def decode_signature(encoded: str) -> bytes:
    """Decode a base64url (unpadded) signature."""
    if not isinstance(encoded, str):
        raise MalformedSignature("a signature must be a string")
    padding = "=" * (-len(encoded) % 4)
    try:
        raw = base64.urlsafe_b64decode(encoded + padding)
    except (binascii.Error, ValueError) as exc:
        raise MalformedSignature(
            "the signature is not valid base64url: %s" % (exc,)
        ) from exc
    if len(raw) != 64:
        raise MalformedSignature(
            "an Ed25519 signature is 64 bytes, got %d" % (len(raw),)
        )
    return raw


class Ed25519Signer(Signer):
    """Signs authorizations with an Ed25519 private key.

    The private key is held by the caller and passed in. This class
    never writes it anywhere, and never sends it anywhere.
    """

    def __init__(self, private_key, key_id: Optional[str] = None) -> None:
        self._private_key = private_key
        self._key_id = key_id

    def public_key_id(self) -> str:
        if self._key_id is not None:
            return self._key_id
        public = self._private_key.public_key()
        return encode_public_key(public)

    def public_key(self) -> str:
        """The encoded public key, for distribution to verifiers."""
        return encode_public_key(self._private_key.public_key())

    def sign(self, authorization: Mapping[str, Any]) -> str:
        """Sign the authorization and return the encoded signature.

        The bytes signed are the canonical bytes of the document with
        exactly the ``signature`` field removed. Every other field is
        included, whether or not this implementation recognises it.
        """
        payload = self.signing_payload(authorization)
        signature = self._private_key.sign(payload)
        return encode_signature(signature)


class Ed25519Verifier(Verifier):
    """Verifies Ed25519 signatures against a set of known public keys.

    The verifier knows only public keys. A private key that reaches
    this class is a design error, and it raises rather than accepting
    it, because a verifier that can sign is not a verifier.
    """

    def __init__(
        self,
        public_keys: Mapping[str, str],
        revoked_key_ids: Sequence[str] = (),
        algorithms: Sequence[str] = tuple(ALGORITHMS),
    ) -> None:
        self._keys = dict(public_keys)
        self._revoked = frozenset(revoked_key_ids)
        self._algorithms = frozenset(algorithms)

    def algorithm(self) -> str:
        return ALGORITHM_ED25519

    def is_revoked(self, key_id: str) -> bool:
        return key_id in self._revoked

    def verify(
        self,
        public_key_id: str,
        payload: bytes,
        signature: str,
        algorithm: str = ALGORITHM_ED25519,
    ) -> bool:
        """Verify a signature.

        Returns ``False`` for a signature that does not verify. Raises
        for a request the verifier cannot even interpret - an unknown
        algorithm, an unknown key, a revoked key, a malformed
        signature. The distinction matters: "this is not valid" and
        "I do not know what this is" are different answers, and
        collapsing them hides an attack.
        """
        if algorithm not in self._algorithms:
            raise UnknownAlgorithm(
                "algorithm %r is not authorised; this implementation "
                "accepts %s" % (algorithm, ", ".join(sorted(self._algorithms)))
            )
        if public_key_id in self._revoked:
            raise UnknownKey("key %r is revoked" % (public_key_id,))
        encoded = self._keys.get(public_key_id)
        if encoded is None:
            raise UnknownKey("key %r is not known" % (public_key_id,))
        raw_signature = decode_signature(signature)
        public_key = decode_public_key(encoded)
        try:
            public_key.verify(raw_signature, payload)
        except Exception:
            # The library raises InvalidSignature. Any other exception
            # is a bug rather than a bad signature, and is not swallowed
            # silently - but it is still a failed verification, not a
            # pass.
            return False
        return True


class KeyRegistry:
    """The set of keys a service trusts, and which of them are revoked.

    Revocation is part of the registry rather than a separate list, so
    that a key cannot be trusted in one place and revoked in another.
    """

    def __init__(
        self,
        public_keys: Mapping[str, str],
        revoked_key_ids: Sequence[str] = (),
        algorithms: Sequence[str] = tuple(ALGORITHMS),
    ) -> None:
        self._keys = dict(public_keys)
        self._revoked = frozenset(revoked_key_ids)
        self._algorithms = frozenset(algorithms)

    def add(self, key_id: str, encoded_public_key: str) -> None:
        self._keys[key_id] = encoded_public_key

    def revoke(self, key_id: str) -> None:
        self._revoked = self._revoked | {key_id}

    def is_revoked(self, key_id: str) -> bool:
        return key_id in self._revoked

    def known(self, key_id: str) -> bool:
        return key_id in self._keys

    def verifier(self) -> Ed25519Verifier:
        return Ed25519Verifier(
            self._keys,
            revoked_key_ids=tuple(self._revoked),
            algorithms=tuple(self._algorithms),
        )
