"""Tamper-evident audit records.

The audit trail records what the platform decided and why. A record that
can be silently rewritten is not evidence, so the trail is a **hash
chain**: each record commits to its predecessor.

    record_n.hash = SHA-256(domain || record_n.canonical || record_{n-1}.hash)

Rewriting or removing any record breaks the chain from that point on, and
:func:`verify_chain` detects it.

What this does and does not prove
----------------------------------
It proves that the records are **internally consistent**: no record was
altered, removed or inserted without breaking the chain.

It does **not** prove that the records were not rewritten wholesale. An
attacker who can replace the whole file can recompute the whole chain.
That requires write access to the audit store, which on this platform
means administrative control of the machine - explicitly out of scope of
the threat model, and stated here so the guarantee is not oversold.

The chain is therefore a *detection* mechanism, not a *prevention*
mechanism. Prevention comes from the store living where the agent cannot
write to it; the chain is what lets the owner notice when that boundary
has already been crossed.

Records are canonicalised with the same ASCII-only canonical form used
by the authorization protocol, so a record's bytes are unambiguous.
"""
from __future__ import annotations

import hashlib
from typing import Any, Iterable, List, Mapping, Optional, Sequence, Tuple

from .canonical import CanonicalisationError, canonical_bytes
from .timeutil import now_utc, format_rfc3339

__all__ = [
    "AuditError",
    "ChainBroken",
    "AuditRecord",
    "AuditLog",
    "verify_chain",
    "GENESIS_HASH",
]

#: The predecessor hash of the first record.
GENESIS_HASH = "0" * 64

#: The domain-separation prefix for audit records.
DOMAIN_AUDIT = "consequencemap.audit.v1"


class AuditError(Exception):
    """Base class for audit failures."""


class ChainBroken(AuditError):
    """The hash chain does not verify."""


class AuditRecord:
    """One entry in the audit trail."""

    def __init__(
        self,
        sequence: int,
        event: str,
        payload: Mapping[str, Any],
        recorded_at: str,
        previous_hash: str,
        record_hash: str,
    ) -> None:
        self.sequence = sequence
        self.event = event
        self.payload = dict(payload)
        self.recorded_at = recorded_at
        self.previous_hash = previous_hash
        self.record_hash = record_hash

    def to_mapping(self) -> Mapping[str, Any]:
        return {
            "sequence": self.sequence,
            "event": self.event,
            "payload": self.payload,
            "recorded_at": self.recorded_at,
            "previous_hash": self.previous_hash,
            "record_hash": self.record_hash,
        }

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "AuditRecord":
        return cls(
            sequence=data["sequence"],
            event=data["event"],
            payload=data["payload"],
            recorded_at=data["recorded_at"],
            previous_hash=data["previous_hash"],
            record_hash=data["record_hash"],
        )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "<AuditRecord %d %s>" % (self.sequence, self.event)


def _record_hash(
    sequence: int,
    event: str,
    payload: Mapping[str, Any],
    recorded_at: str,
    previous_hash: str,
) -> str:
    document = {
        "sequence": sequence,
        "event": event,
        "payload": payload,
        "recorded_at": recorded_at,
        "previous_hash": previous_hash,
    }
    return hashlib.sha256(canonical_bytes(DOMAIN_AUDIT, document)).hexdigest()


class AuditLog:
    """An append-only, hash-chained audit trail.

    The log is in-memory and pure: it produces records and verifies them.
    Persisting it is the caller's business, which keeps this module free
    of I/O and testable.
    """

    def __init__(self) -> None:
        self._records: List[AuditRecord] = []

    def append(
        self,
        event: str,
        payload: Mapping[str, Any],
        recorded_at: Optional[str] = None,
    ) -> AuditRecord:
        """Append a record and return it.

        Both authorised and refused operations are recorded. A refusal that
        is not recorded is indistinguishable from an operation that never
        happened, which is exactly the gap an attacker wants.
        """
        if not isinstance(event, str) or not event:
            raise AuditError("an audit event needs a name")
        sequence = len(self._records)
        previous_hash = (
            self._records[-1].record_hash if self._records else GENESIS_HASH
        )
        moment = recorded_at or format_rfc3339(now_utc())
        record_hash = _record_hash(sequence, event, payload, moment, previous_hash)
        record = AuditRecord(
            sequence=sequence,
            event=event,
            payload=payload,
            recorded_at=moment,
            previous_hash=previous_hash,
            record_hash=record_hash,
        )
        self._records.append(record)
        return record

    @property
    def records(self) -> Tuple[AuditRecord, ...]:
        return tuple(self._records)

    def __len__(self) -> int:
        return len(self._records)

    def verify(self) -> None:
        """Raise :class:`ChainBroken` if the chain does not verify."""
        verify_chain(self._records)

    def head_hash(self) -> str:
        """The hash of the last record, or the genesis hash if empty."""
        return self._records[-1].record_hash if self._records else GENESIS_HASH


def verify_chain(records: Sequence[Any]) -> None:
    """Verify a hash chain.

    Checks, for every record in order:

    - the sequence number is the expected one;
    - ``previous_hash`` matches the previous record's ``record_hash``;
    - ``record_hash`` is the hash of the record's own content.

    A record that was altered, removed or inserted breaks at least one of
    these. Raises :class:`ChainBroken` naming the first broken record.
    """
    previous_hash = GENESIS_HASH
    for index, record in enumerate(records):
        if isinstance(record, Mapping):
            record = AuditRecord.from_mapping(record)
        if record.sequence != index:
            raise ChainBroken(
                "record %d has sequence %r: a record was inserted or removed"
                % (index, record.sequence)
            )
        if record.previous_hash != previous_hash:
            raise ChainBroken(
                "record %d does not chain to its predecessor: expected %s, found %s"
                % (index, previous_hash, record.previous_hash)
            )
        expected = _record_hash(
            record.sequence,
            record.event,
            record.payload,
            record.recorded_at,
            record.previous_hash,
        )
        if record.record_hash != expected:
            raise ChainBroken(
                "record %d has been altered: its content does not hash to its "
                "recorded hash" % (index,)
            )
        previous_hash = record.record_hash
