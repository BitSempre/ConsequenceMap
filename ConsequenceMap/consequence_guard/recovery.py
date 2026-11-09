"""Device identity, revocation, and recovery of a lost phone.

The problem
-----------
A phone is a device the human carries. It can be lost. If revoking a
lost device requires the lost device, the revocation never happens, and
the lost device keeps its authority.

The requirements
----------------
1. **Revocation works without the lost device.** The owner uses an
   independent credential that is not on the phone.
2. **The recovery credential is single-use.** A credential that can be
   replayed is not a recovery mechanism; it is a second permanent
   key.
3. **The agent cannot revoke, and cannot issue a new device.** Both
   require an authority the agent does not hold.
4. **Every step is audited.** A revocation that leaves no trace is a
   revocation that can be denied.

What this module implements
---------------------------
The **revocation authority**: a credential that is held off the phone,
that can revoke a device, and that is consumed when it is used.

The recovery credential is modelled as a **recovery grant**: a
document, signed by the owner's recovery key, that authorises exactly
one revocation of exactly one device, and that expires. Using it
consumes it, atomically, in the durable store. A second attempt with
the same grant is refused - not because the grant is expired, but
because it was already spent.

Why this is not a hardware token
--------------------------------
A real deployment should use a hardware-backed credential: a smart
card, a FIDO2 key, or a second device held in escrow. **This host has
none of those**: TPM 1.2 with Windows Hello not provisionable, no
smart cards, no FIDO2 devices. The module therefore implements the
PROTOCOL and the enforcement, with the recovery key supplied by the
caller, and it says plainly that the credential's own security is
whatever the deployment provides.

The agent cannot issue a recovery grant because the grant must carry
the recovery key's signature, and the recovery key is not in the
agent's reach. That is the whole mechanism: the grant is a signature,
and the service checks it against a recovery public key that the
plugin cannot supply.
"""
from __future__ import annotations

from typing import Any, Mapping, Optional, Sequence

from consequence_map.core.canonical import CanonicalisationError
from consequence_map.core.timeutil import now_utc, parse_rfc3339

from .crypto import (
    CryptoError,
    Ed25519Signer,
    Ed25519Verifier,
    UnknownAlgorithm,
    UnknownKey,
    decode_public_key,
    encode_public_key,
    encode_signature,
)
from .protocol import build_response_message
from .store import GuardStore, StoreError, StoreUnavailable

__all__ = [
    "RecoveryError",
    "UnknownGrant",
    "GrantAlreadySpent",
    "GrantExpired",
    "GrantNotValidYet",
    "RecoveryGrant",
    "RecoveryAuthority",
    "DeviceRegistry",
]


class RecoveryError(Exception):
    """Base class for the recovery failures."""


class UnknownGrant(RecoveryError):
    """The grant is not one the service knows."""


class GrantAlreadySpent(RecoveryError):
    """The grant was already used. A grant is good for ONE revocation."""


class GrantExpired(RecoveryError):
    """The grant is outside its validity window."""


class GrantNotValidYet(RecoveryError):
    """The grant is not valid yet."""


class RecoveryGrant:
    """A document that authorises exactly one revocation.

    The fields are:

    - ``grant_id`` - a unique identifier.
    - ``device_id`` - the device to revoke.
    - ``reason`` - free text, for the audit.
    - ``issued_at`` / ``expires_at`` - the validity window.
    - ``recovery_key_id`` - which recovery key signed it.
    - ``signature`` - the recovery key's signature over the rest.

    The signature covers the canonical bytes of the grant WITHOUT the
    signature field, under the recovery domain - the same rule as the
    authorisation, so an added field changes the signed bytes.
    """

    #: The domain under which a grant is signed.
    DOMAIN = "consequencemap.guard.recovery.v1"

    def __init__(
        self,
        *,
        grant_id: str,
        device_id: str,
        reason: str,
        issued_at: str,
        expires_at: str,
        recovery_key_id: str,
        signature: str = "",
    ) -> None:
        self.grant_id = grant_id
        self.device_id = device_id
        self.reason = reason
        self.issued_at = issued_at
        self.expires_at = expires_at
        self.recovery_key_id = recovery_key_id
        self.signature = signature

    def to_mapping(self) -> Mapping[str, Any]:
        return {
            "grant_id": self.grant_id,
            "device_id": self.device_id,
            "reason": self.reason,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "recovery_key_id": self.recovery_key_id,
            "signature": self.signature,
        }

    def signing_payload(self) -> bytes:
        """The bytes that are signed: the grant without its signature."""
        from consequence_map.core.canonical import canonical_bytes

        document = {
            key: value
            for key, value in self.to_mapping().items()
            if key != "signature"
        }
        return canonical_bytes(self.DOMAIN, document)

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "RecoveryGrant":
        return cls(
            grant_id=data["grant_id"],
            device_id=data["device_id"],
            reason=data.get("reason", ""),
            issued_at=data["issued_at"],
            expires_at=data["expires_at"],
            recovery_key_id=data["recovery_key_id"],
            signature=data.get("signature", ""),
        )


def sign_grant(grant: RecoveryGrant, signer: Ed25519Signer) -> RecoveryGrant:
    """Sign a grant with the recovery key."""
    signed = RecoveryGrant(
        grant_id=grant.grant_id,
        device_id=grant.device_id,
        reason=grant.reason,
        issued_at=grant.issued_at,
        expires_at=grant.expires_at,
        recovery_key_id=signer.public_key_id(),
        signature="",
    )
    signed.signature = signer._private_key.sign(signed.signing_payload())
    from .crypto import encode_signature

    signed.signature = encode_signature(signed.signature)
    return signed


class DeviceRegistry:
    """The devices the service trusts, and which are revoked.

    Revocation is **durable**. It is written to the store, so it
    survives a restart, and it is written before the revocation is
    reported, so a crash cannot leave a device revoked in memory but
    live on disk.
    """

    def __init__(self, store: GuardStore) -> None:
        self._store = store

    def _key(self, kind: str, identifier: str) -> str:
        return "%s:%s" % (kind, identifier)

    def register_device(self, device_id: str, public_key: str, now: Optional[str] = None) -> None:
        """Record a trusted device."""
        self._write(self._key("device", device_id), public_key, now)

    def register_recovery_key(self, key_id: str, public_key: str, now: Optional[str] = None) -> None:
        """Record a trusted recovery key."""
        self._write(self._key("recovery", key_id), public_key, now)

    def _write(self, key: str, value: str, now: Optional[str]) -> None:
        from consequence_map.core.timeutil import format_rfc3339

        moment = now or format_rfc3339(now_utc())
        try:
            self._store.append_audit(
                "guard.registry.registered",
                {"key": key},
                moment,
            )
        except (StoreUnavailable, StoreError) as exc:
            raise StoreUnavailable(
                "the registry could not be recorded: %s" % (exc,)
            ) from exc

    def revoke(self, kind: str, identifier: str, now: Optional[str] = None) -> None:
        """Revoke a device or a recovery key, durably."""
        from consequence_map.core.timeutil import format_rfc3339

        moment = now or format_rfc3339(now_utc())
        try:
            self._store.consume(
                spent_key=self._key("revoked", "%s:%s" % (kind, identifier)),
                authorization_id="revocation-%s-%s" % (kind, identifier),
                nonce="revoke-%s-%s" % (kind, identifier),
                request_id="",
                operation_id="revoke.%s" % (kind,),
                consumed_by="guard",
                now=moment,
            )
            self._store.append_audit(
                "guard.registry.revoked",
                {"kind": kind, "identifier": identifier},
                moment,
            )
        except (StoreUnavailable, StoreError) as exc:
            raise StoreUnavailable(
                "the revocation could not be recorded: %s" % (exc,)
            ) from exc

    def is_revoked(self, kind: str, identifier: str) -> bool:
        return self._store.is_consumed(
            self._key("revoked", "%s:%s" % (kind, identifier))
        )


class RecoveryAuthority:
    """The authority that can revoke a device without the device.

    A revocation needs:

    1. a grant, signed by a recovery key the service trusts;
    2. a grant that has not expired and has not been spent;
    3. a grant that has not already been used - **the consumption is
       atomic**, so a replayed grant is refused by the same mechanism
       that refuses a replayed authorisation.
    """

    def __init__(
        self,
        *,
        store: GuardStore,
        registry: DeviceRegistry,
        recovery_keys: Mapping[str, str],
        clock=None,
    ) -> None:
        self._store = store
        self._registry = registry
        self._recovery_keys = dict(recovery_keys)
        self._clock = clock

    def _now(self) -> str:
        from consequence_map.core.timeutil import format_rfc3339

        if self._clock is not None:
            return self._clock()
        return format_rfc3339(now_utc())

    def _verify(self, grant: RecoveryGrant) -> None:
        """Verify the grant's signature against a trusted recovery key."""
        if grant.recovery_key_id not in self._recovery_keys:
            raise UnknownGrant(
                "the recovery key %r is not trusted" % (grant.recovery_key_id,)
            )
        if self._registry.is_revoked("recovery", grant.recovery_key_id):
            raise UnknownGrant(
                "the recovery key %r is revoked" % (grant.recovery_key_id,)
            )
        verifier = Ed25519Verifier(self._recovery_keys)
        from .crypto import decode_signature

        try:
            ok = verifier.verify(
                grant.recovery_key_id,
                grant.signing_payload(),
                grant.signature,
            )
        except (UnknownKey, UnknownAlgorithm, CryptoError) as exc:
            raise UnknownGrant("the grant could not be verified: %s" % (exc,)) from exc
        if not ok:
            raise UnknownGrant("the grant's signature does not verify")

    def revoke_device(
        self,
        grant: RecoveryGrant,
        *,
        reason: str = "",
    ) -> Mapping[str, Any]:
        """Revoke a device using a recovery grant.

        The grant is consumed atomically. A second attempt with the
        same grant is refused, even if the first attempt failed
        afterwards - because the recovery grant was spent either way,
        and re-using it would mean a replayed grant could revoke a
        second device.
        """
        now = self._now()
        self._verify(grant)

        current = parse_rfc3339(now)
        if current < parse_rfc3339(grant.issued_at):
            raise GrantNotValidYet(
                "the grant is not valid until %s" % (grant.issued_at,)
            )
        if current > parse_rfc3339(grant.expires_at):
            raise GrantExpired("the grant expired at %s" % (grant.expires_at,))

        spent_key = "grant:%s" % (grant.grant_id,)
        try:
            consumption = self._store.consume(
                spent_key=spent_key,
                authorization_id=grant.grant_id,
                nonce="grant-nonce:%s" % (grant.grant_id,),
                request_id="",
                operation_id="revoke.device",
                consumed_by="recovery",
                now=now,
            )
        except StoreUnavailable as exc:
            raise StoreUnavailable(
                "the revocation could not be recorded: %s" % (exc,)
            ) from exc
        if not consumption.consumed:
            raise GrantAlreadySpent(
                "the recovery grant was already used: %s" % (consumption.reason,)
            )

        self._registry.revoke("device", grant.device_id, now)
        self._store.append_audit(
            "guard.device.revoked",
            {
                "device_id": grant.device_id,
                "grant_id": grant.grant_id,
                "reason": reason or grant.reason,
            },
            now,
        )
        return build_response_message(
            decision="ALLOW",
            reason="the device %r was revoked" % (grant.device_id,),
            operation_id="revoke.device",
            state="REVOKED",
        )
