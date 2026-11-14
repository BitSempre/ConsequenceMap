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
    """One entry in the audit trail.

    A record is **immutable**. Once written, its content cannot change:
    the fields are read-only and the payload is a frozen snapshot.

    The chain detects an altered record, but detection is not
    prevention. An audit trail whose records can be rewritten after the
    fact is not an audit trail - it is a suggestion that something
    happened. Making the record immutable means the only way to change
    the history is to build a different history, which produces a
    different chain and a different head hash.
    """

    __slots__ = ("_sequence", "_event", "_payload", "_recorded_at",
                 "_previous_hash", "_record_hash")

    def __init__(
        self,
        sequence: int,
        event: str,
        payload: Mapping[str, Any],
        recorded_at: str,
        previous_hash: str,
        record_hash: str,
    ) -> None:
        object.__setattr__(self, "_sequence", sequence)
        object.__setattr__(self, "_event", event)
        object.__setattr__(self, "_payload", _freeze(payload))
        object.__setattr__(self, "_recorded_at", recorded_at)
        object.__setattr__(self, "_previous_hash", previous_hash)
        object.__setattr__(self, "_record_hash", record_hash)

    @property
    def sequence(self) -> int:
        return self._sequence

    @property
    def event(self) -> str:
        return self._event

    @property
    def payload(self) -> Mapping[str, Any]:
        return self._payload

    @property
    def recorded_at(self) -> str:
        return self._recorded_at

    @property
    def previous_hash(self) -> str:
        return self._previous_hash

    @property
    def record_hash(self) -> str:
        return self._record_hash

    def __setattr__(self, name: str, value: Any) -> None:
        raise AttributeError(
            "an audit record is immutable: %r cannot be changed" % (name,)
        )

    def __delattr__(self, name: str) -> None:
        raise AttributeError(
            "an audit record is immutable: %r cannot be deleted" % (name,)
        )

    def to_mapping(self) -> Mapping[str, Any]:
        return {
            "sequence": self.sequence,
            "event": self.event,
            "payload": _thaw(self.payload),
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


def _thaw(value: Any) -> Any:
    """Turn a frozen snapshot back into ordinary containers.

    The canonical form needs plain mappings and lists. The frozen
    payload uses tuples for sequences and read-only mappings, so it is
    converted here for the hash and for anything a caller wants to read.
    """
    if isinstance(value, FrozenMapping):
        return value.to_plain()
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    if isinstance(value, frozenset):
        return sorted(value)
    return value


class FrozenMapping(Mapping):
    """A read-only mapping.

    A plain dict would still be mutable, and a frozen payload built out
    of plain dicts would not be frozen at all - only the top level
    would resist a change.
    """

    __slots__ = ("_data",)

    def __init__(self, data: Mapping[str, Any]) -> None:
        object.__setattr__(self, "_data", dict(data))

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __iter__(self):
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return repr(self._data)

    def __setitem__(self, key, value) -> None:
        raise TypeError("a frozen mapping cannot be changed")

    def __delitem__(self, key) -> None:
        raise TypeError("a frozen mapping cannot be changed")

    def __setattr__(self, name, value) -> None:
        raise TypeError("a frozen mapping cannot be changed")

    def __delattr__(self, name) -> None:
        raise TypeError("a frozen mapping cannot be changed")

    def to_plain(self) -> dict:
        """A mutable copy, for the canonical form."""
        return {key: _thaw(item) for key, item in self._data.items()}


def _freeze(value: Any) -> Any:
    """Return a read-only snapshot of a payload.

    The snapshot is deep: a nested dict or list is frozen too, so
    ``record.payload["nested"]["key"] = x`` cannot change what was
    recorded.
    """
    if isinstance(value, Mapping):
        return FrozenMapping(
            {key: _freeze(item) for key, item in value.items()}
        )
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(value)
    return value


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
        # An event name is a single line. A newline in it would let a
        # crafted event forge the appearance of two records in a log that
        # a human reads.
        if any(character in event for character in "\r\n\x00"):
            raise AuditError(
                "an audit event name must not contain control characters"
            )
        sequence = len(self._records)
        previous_hash = (
            self._records[-1].record_hash if self._records else GENESIS_HASH
        )
        moment = recorded_at or format_rfc3339(now_utc())
        record_hash = _record_hash(
            sequence, event, _thaw(_freeze(payload)), moment, previous_hash
        )
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

    def verify(
        self,
        expected_head: Optional[str] = None,
        expected_length: Optional[int] = None,
    ) -> None:
        """Raise :class:`ChainBroken` if the chain does not verify.

        Pass ``expected_head`` or ``expected_length`` to detect a
        truncated chain; without an external anchor, truncation cannot be
        seen.
        """
        verify_chain(
            self._records,
            expected_head=expected_head,
            expected_length=expected_length,
        )

    def head_hash(self) -> str:
        """The hash of the last record, or the genesis hash if empty."""
        return self._records[-1].record_hash if self._records else GENESIS_HASH


def verify_chain(
    records: Sequence[Any],
    expected_head: Optional[str] = None,
    expected_length: Optional[int] = None,
) -> None:
    """Verify a hash chain.

    Checks, for every record in order:

    - the sequence number is the expected one;
    - ``previous_hash`` matches the previous record's ``record_hash``;
    - ``record_hash`` is the hash of the record's own content.

    A record that was altered, removed or inserted breaks at least one of
    these. Raises :class:`ChainBroken` naming the first broken record.

    **Truncation.** A chain verifies happily when its tail has been cut
    off, because a prefix is itself a consistent chain. Detecting that
    needs an anchor from outside the chain, which is what the two
    optional arguments are:

    - ``expected_head`` - the hash of the last record, as recorded
      elsewhere. With it, a truncated chain fails.
    - ``expected_length`` - how many records the chain should have. With
      it, a truncated chain fails too.

    Without either, **truncation is undetectable**, and this function
    does not pretend otherwise. The anchor must live somewhere the agent
    cannot write; that is a deployment requirement, and it is the same
    requirement that protects the trust anchor.
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
            _thaw(record.payload),
            record.recorded_at,
            record.previous_hash,
        )
        if record.record_hash != expected:
            raise ChainBroken(
                "record %d has been altered: its content does not hash to its "
                "recorded hash" % (index,)
            )
        previous_hash = record.record_hash

    if expected_length is not None and len(records) != expected_length:
        raise ChainBroken(
            "the chain has %d record(s), expected %d: records were removed "
            "from the end" % (len(records), expected_length)
        )
    if expected_head is not None:
        actual_head = previous_hash
        if actual_head != expected_head:
            raise ChainBroken(
                "the chain's head is %s, expected %s: the chain was truncated "
                "or extended" % (actual_head, expected_head)
            )
