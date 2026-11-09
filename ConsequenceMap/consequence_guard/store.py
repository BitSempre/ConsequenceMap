"""Durable, atomic single-use of authorizations, and protected state.

Why a database and not a file
------------------------------
The previous implementation kept the set of spent authorizations in
memory. That fails in the ways that matter:

- a process restart forgets it, so a captured authorization can be
  replayed after a reboot;
- two processes each have their own set, so both can consume the same
  authorization.

A SQLite database with an immediate transaction fixes both. The
``INSERT`` of the spent key is the atomic step: the database serialises
the writers, and the first one wins. The second one gets a constraint
violation, not a second execution.

The states of an operation
--------------------------
Consuming an authorization and completing an operation are different
events, and the difference matters. A handler may fail half-way
through, after it has already deleted three of four files. If the
system recorded only "consumed" and "done", a crash in between would
leave an operation that is neither, and a retry would apply the
approved effect twice.

So an operation carries a state:

- ``RECEIVED`` - the request arrived.
- ``VALIDATED`` - the authorization verified.
- ``CONSUMED`` - the authorization was spent. This is the atomic step.
- ``EXECUTION_STARTED`` - the handler was invoked.
- ``COMPLETED`` - the handler returned successfully.
- ``FAILED`` - the handler raised, and the failure is known.
- ``OUTCOME_UNKNOWN`` - the process died between EXECUTION_STARTED and
  COMPLETED. **The effect may or may not have happened.**

``OUTCOME_UNKNOWN`` is the honest answer, and it is not retried
automatically. A retry of an operation whose outcome is unknown applies
an effect the human approved once, a second time. The system says so
and waits for a human.

Fail-closed
-----------
Every method that records something raises :class:`StoreUnavailable`
if the store cannot be written. There is no "carry on without the
audit" path: a protected operation whose audit record cannot be
guaranteed is refused, because an operation that cannot be accounted
for is an operation nobody can prove did or did not happen.

The store is a REFERENCE implementation. What protects it against the
agent on a real installation is the filesystem ACL on the directory and
the file - a property of the deployment, not of this code. What this
code guarantees is the part that is its own: atomicity, durability,
and the refusal to continue when it cannot record.
"""
from __future__ import annotations

import os
import sqlite3
import threading
from contextlib import contextmanager
from typing import Any, Iterator, Mapping, Optional, Sequence

__all__ = [
    "StoreError",
    "StoreUnavailable",
    "OperationState",
    "OPERATION_STATES",
    "GUARD_SCHEMA_VERSION",
    "GuardStore",
    "ConsumptionResult",
]


class StoreError(Exception):
    """Base class for the store's failures."""


class StoreUnavailable(StoreError):
    """The store could not be read or written.

    Raised instead of returning a partial result. A protected
    operation whose audit record cannot be guaranteed is refused.
    """


class OperationState:
    """The states an operation passes through."""

    RECEIVED = "RECEIVED"
    VALIDATED = "VALIDATED"
    CONSUMED = "CONSUMED"
    EXECUTION_STARTED = "EXECUTION_STARTED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    OUTCOME_UNKNOWN = "OUTCOME_UNKNOWN"


#: Every state an operation may be in.
OPERATION_STATES = (
    OperationState.RECEIVED,
    OperationState.VALIDATED,
    OperationState.CONSUMED,
    OperationState.EXECUTION_STARTED,
    OperationState.COMPLETED,
    OperationState.FAILED,
    OperationState.OUTCOME_UNKNOWN,
)

#: The states from which no further automatic progress is made.
TERMINAL_OPERATION_STATES = (
    OperationState.COMPLETED,
    OperationState.FAILED,
)

#: The schema version this implementation writes.
GUARD_SCHEMA_VERSION = 1


class ConsumptionResult:
    """The outcome of an attempt to consume an authorization."""

    def __init__(self, consumed: bool, reason: str = "") -> None:
        self.consumed = consumed
        self.reason = reason

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "<ConsumptionResult consumed=%r reason=%r>" % (
            self.consumed, self.reason
        )


_SCHEMA = """
CREATE TABLE IF NOT EXISTS guard_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS spent_authorizations (
    spent_key      TEXT PRIMARY KEY,
    authorization_id TEXT NOT NULL,
    nonce          TEXT NOT NULL,
    request_id     TEXT NOT NULL,
    operation_id   TEXT NOT NULL,
    consumed_at    TEXT NOT NULL,
    consumed_by    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS operations (
    operation_id   TEXT PRIMARY KEY,
    state          TEXT NOT NULL,
    request_id     TEXT NOT NULL,
    authorization_id TEXT NOT NULL,
    operation      TEXT NOT NULL,
    proposal_hash  TEXT NOT NULL,
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL,
    detail         TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS audit_log (
    sequence     INTEGER PRIMARY KEY AUTOINCREMENT,
    event        TEXT NOT NULL,
    payload      TEXT NOT NULL,
    recorded_at  TEXT NOT NULL,
    previous_hash TEXT NOT NULL,
    record_hash  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS seen_nonces (
    nonce        TEXT PRIMARY KEY,
    seen_at      TEXT NOT NULL,
    operation_id TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS audit_checkpoints (
    checkpoint_id TEXT PRIMARY KEY,
    sequence      INTEGER NOT NULL,
    record_hash   TEXT NOT NULL,
    created_at    TEXT NOT NULL
);
"""


def _canonical_hash(domain: str, document: Mapping[str, Any]) -> str:
    """Hash a document with the platform's canonical form.

    The store uses the SAME canonical form as the rest of the system.
    Two canonical forms would be two sets of rules, and they would
    eventually disagree about what was recorded.
    """
    import hashlib

    from consequence_map.core.canonical import canonical_bytes

    return hashlib.sha256(canonical_bytes(domain, document)).hexdigest()


class GuardStore:
    """The protected state store.

    Thread-safe within a process (a lock serialises the writers) and
    safe across processes (SQLite serialises them). The atomic step is
    the ``INSERT`` into ``spent_authorizations``: it is inside an
    immediate transaction, so two processes racing for the same
    authorization produce exactly one winner.
    """

    #: The domain under which audit records are hashed.
    AUDIT_DOMAIN = "consequencemap.guard.audit.v1"

    def __init__(self, path: str, timeout: float = 10.0) -> None:
        self.path = path
        self._timeout = timeout
        self._lock = threading.RLock()
        self._initialise()

    # -- lifecycle -----------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        """Open a connection with the durability settings we require.

        ``WAL`` gives readers a consistent view while a writer works.
        ``synchronous=FULL`` is the expensive setting: it makes the
        commit durable rather than merely handed to the operating
        system. For a store that decides whether a protected operation
        may proceed, the cost is the point.
        """
        try:
            connection = sqlite3.connect(
                self.path, timeout=self._timeout, isolation_level=None
            )
        except (sqlite3.Error, OSError) as exc:
            raise StoreUnavailable(
                "the guard store could not be opened: %s" % (exc,)
            ) from exc
        try:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute("PRAGMA foreign_keys=ON")
        except sqlite3.Error as exc:
            connection.close()
            raise StoreUnavailable(
                "the guard store could not be configured: %s" % (exc,)
            ) from exc
        return connection

    def _initialise(self) -> None:
        directory = os.path.dirname(os.path.abspath(self.path))
        try:
            if directory and not os.path.isdir(directory):
                os.makedirs(directory, exist_ok=True)
        except OSError as exc:
            # A filesystem failure is a store failure. It is translated
            # here so that every caller sees ONE exception type for
            # "the store is not usable" - and so that no code path can
            # accidentally treat it as something else.
            raise StoreUnavailable(
                "the guard store directory could not be prepared: %s" % (exc,)
            ) from exc
        try:
            connection = self._connect()
            try:
                connection.executescript(_SCHEMA)
                connection.execute(
                    "INSERT OR IGNORE INTO guard_meta (key, value) VALUES (?, ?)",
                    ("schema_version", str(GUARD_SCHEMA_VERSION)),
                )
            finally:
                connection.close()
        except (sqlite3.Error, OSError) as exc:
            raise StoreUnavailable(
                "the guard store could not be prepared: %s" % (exc,)
            ) from exc

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        """An IMMEDIATE transaction.

        IMMEDIATE takes the write lock at the start, so two writers
        cannot both read and then both write. With a deferred
        transaction, the second writer would fail at COMMIT with
        "database is locked" rather than being refused by a
        constraint - which is a different failure and a worse one.
        """
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            try:
                yield connection
            except Exception:
                connection.execute("ROLLBACK")
                raise
            else:
                connection.execute("COMMIT")
        except sqlite3.Error as exc:
            raise StoreUnavailable(
                "the guard store could not complete the transaction: %s"
                % (exc,)
            ) from exc
        finally:
            connection.close()

    def _read(self, statement: str, parameters: Sequence[Any] = ()) -> list:
        connection = self._connect()
        try:
            cursor = connection.execute(statement, tuple(parameters))
            return list(cursor.fetchall())
        except sqlite3.Error as exc:
            raise StoreUnavailable(
                "the guard store could not be read: %s" % (exc,)
            ) from exc
        finally:
            connection.close()

    # -- authorization consumption ------------------------------------

    def consume(
        self,
        *,
        spent_key: str,
        authorization_id: str,
        nonce: str,
        request_id: str,
        operation_id: str,
        consumed_by: str,
        now: str,
    ) -> ConsumptionResult:
        """Consume an authorization, atomically.

        Returns a :class:`ConsumptionResult` whose ``consumed`` is
        ``True`` for exactly one caller. A second caller with the same
        key gets ``consumed=False`` - and, because the check and the
        insert are in the same immediate transaction, the two callers
        cannot both decide they won.
        """
        with self._lock:
            try:
                with self._transaction() as connection:
                    existing = connection.execute(
                        "SELECT spent_key FROM spent_authorizations "
                        "WHERE spent_key = ?",
                        (spent_key,),
                    ).fetchone()
                    if existing is not None:
                        return ConsumptionResult(
                            False,
                            "the authorization was already consumed",
                        )
                    connection.execute(
                        "INSERT INTO spent_authorizations "
                        "(spent_key, authorization_id, nonce, request_id, "
                        " operation_id, consumed_at, consumed_by) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (
                            spent_key, authorization_id, nonce, request_id,
                            operation_id, now, consumed_by,
                        ),
                    )
            except sqlite3.IntegrityError:
                # Another process won the race between the SELECT and
                # the INSERT. The transaction is rolled back, and this
                # caller did not consume it.
                return ConsumptionResult(
                    False, "the authorization was consumed concurrently"
                )
        return ConsumptionResult(True)

    def is_consumed(self, spent_key: str) -> bool:
        rows = self._read(
            "SELECT spent_key FROM spent_authorizations WHERE spent_key = ?",
            (spent_key,),
        )
        return bool(rows)

    def consumption_count(self) -> int:
        rows = self._read("SELECT COUNT(*) FROM spent_authorizations")
        return int(rows[0][0]) if rows else 0

    # -- operation states ----------------------------------------------

    def record_operation(
        self,
        *,
        operation_id: str,
        state: str,
        request_id: str,
        authorization_id: str,
        operation: str,
        proposal_hash: str,
        now: str,
        detail: str = "",
    ) -> None:
        """Record an operation in a state.

        The state must be one of the known states. An unknown state is
        refused rather than stored: a typo in a state name would
        otherwise create a state the recovery logic does not know how
        to interpret.
        """
        if state not in OPERATION_STATES:
            raise StoreError(
                "unknown operation state %r; expected one of %s"
                % (state, ", ".join(OPERATION_STATES))
            )
        with self._lock:
            with self._transaction() as connection:
                connection.execute(
                    "INSERT INTO operations "
                    "(operation_id, state, request_id, authorization_id, "
                    " operation, proposal_hash, created_at, updated_at, detail) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(operation_id) DO UPDATE SET "
                    " state=excluded.state, updated_at=excluded.updated_at, "
                    " detail=excluded.detail",
                    (
                        operation_id, state, request_id, authorization_id,
                        operation, proposal_hash, now, now, detail,
                    ),
                )

    def operation_state(self, operation_id: str) -> Optional[str]:
        rows = self._read(
            "SELECT state FROM operations WHERE operation_id = ?",
            (operation_id,),
        )
        return rows[0][0] if rows else None

    def operations_in_state(self, state: str) -> list:
        rows = self._read(
            "SELECT operation_id, state, operation FROM operations "
            "WHERE state = ? ORDER BY operation_id",
            (state,),
        )
        return [
            {"operation_id": row[0], "state": row[1], "operation": row[2]}
            for row in rows
        ]

    # -- transport nonces ----------------------------------------------

    def record_nonce(
        self,
        nonce: str,
        now: str,
        operation_id: str = "",
    ) -> bool:
        """Record a transport nonce.

        Returns ``True`` if this nonce is new, ``False`` if it has been
        seen before.

        The nonce set is **durable**. An in-memory set is lost when the
        service restarts, which would reopen the transport-level replay
        window every time the service was restarted - and an agent can
        restart a service. The spent set already refuses a replayed
        *authorisation*; this refuses a replayed *request*, which is a
        different thing: a request that is refused for its nonce never
        reaches the authorisation logic at all.

        The insertion is inside an immediate transaction, so two
        processes cannot both record the same nonce as new.
        """
        with self._lock:
            try:
                with self._transaction() as connection:
                    existing = connection.execute(
                        "SELECT nonce FROM seen_nonces WHERE nonce = ?",
                        (nonce,),
                    ).fetchone()
                    if existing is not None:
                        return False
                    connection.execute(
                        "INSERT INTO seen_nonces (nonce, seen_at, operation_id) "
                        "VALUES (?, ?, ?)",
                        (nonce, now, operation_id),
                    )
            except sqlite3.IntegrityError:
                return False
        return True

    def nonce_seen(self, nonce: str) -> bool:
        rows = self._read(
            "SELECT nonce FROM seen_nonces WHERE nonce = ?", (nonce,)
        )
        return bool(rows)

    def nonce_count(self) -> int:
        rows = self._read("SELECT COUNT(*) FROM seen_nonces")
        return int(rows[0][0]) if rows else 0

    # -- audit ---------------------------------------------------------

    def append_audit(self, event: str, payload: Mapping[str, Any], now: str) -> str:
        """Append a record to the audit trail and return its hash.

        The chain is computed inside the transaction, so the previous
        hash and the new hash are consistent with what is committed.
        """
        if not isinstance(event, str) or not event:
            raise StoreError("an audit event needs a name")
        with self._lock:
            with self._transaction() as connection:
                row = connection.execute(
                    "SELECT sequence, record_hash FROM audit_log "
                    "ORDER BY sequence DESC LIMIT 1"
                ).fetchone()
                if row is None:
                    sequence = 0
                    previous_hash = "0" * 64
                else:
                    sequence = int(row[0]) + 1
                    previous_hash = row[1]
                document = {
                    "sequence": sequence,
                    "event": event,
                    "payload": dict(payload),
                    "recorded_at": now,
                    "previous_hash": previous_hash,
                }
                record_hash = _canonical_hash(self.AUDIT_DOMAIN, document)
                connection.execute(
                    "INSERT INTO audit_log "
                    "(sequence, event, payload, recorded_at, previous_hash, "
                    " record_hash) VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        sequence, event,
                        _canonical_text(document["payload"]),
                        now, previous_hash, record_hash,
                    ),
                )
        return record_hash

    def audit_records(self) -> list:
        rows = self._read(
            "SELECT sequence, event, payload, recorded_at, previous_hash, "
            "record_hash FROM audit_log ORDER BY sequence"
        )
        records = []
        for sequence, event, payload, recorded_at, previous_hash, record_hash in rows:
            records.append({
                "sequence": sequence,
                "event": event,
                "payload": payload,
                "recorded_at": recorded_at,
                "previous_hash": previous_hash,
                "record_hash": record_hash,
            })
        return records

    def audit_head(self) -> Optional[str]:
        rows = self._read(
            "SELECT record_hash FROM audit_log ORDER BY sequence DESC LIMIT 1"
        )
        return rows[0][0] if rows else None

    def write_checkpoint(self, checkpoint_id: str, now: str) -> str:
        """Write an integrity checkpoint.

        The checkpoint records the head of the chain at a moment the
        system knows to be correct. A later verification compares the
        chain against it: a chain that was rewritten consistently would
        still verify internally, but it would not match the checkpoint.
        """
        with self._lock:
            with self._transaction() as connection:
                row = connection.execute(
                    "SELECT sequence, record_hash FROM audit_log "
                    "ORDER BY sequence DESC LIMIT 1"
                ).fetchone()
                if row is None:
                    sequence, record_hash = 0, "0" * 64
                else:
                    sequence, record_hash = int(row[0]), row[1]
                connection.execute(
                    "INSERT INTO audit_checkpoints "
                    "(checkpoint_id, sequence, record_hash, created_at) "
                    "VALUES (?, ?, ?, ?) "
                    "ON CONFLICT(checkpoint_id) DO UPDATE SET "
                    " sequence=excluded.sequence, record_hash=excluded.record_hash, "
                    " created_at=excluded.created_at",
                    (checkpoint_id, sequence, record_hash, now),
                )
        return record_hash

    def checkpoints(self) -> list:
        rows = self._read(
            "SELECT checkpoint_id, sequence, record_hash, created_at "
            "FROM audit_checkpoints ORDER BY created_at"
        )
        return [
            {
                "checkpoint_id": row[0],
                "sequence": row[1],
                "record_hash": row[2],
                "created_at": row[3],
            }
            for row in rows
        ]


def _canonical_text(document: Mapping[str, Any]) -> str:
    """The canonical JSON text of a payload, for storage.

    The payload is stored as canonical text rather than as a blob so
    that reading it back gives exactly what was hashed - there is no
    second representation that could differ.
    """
    import json

    from consequence_map.core.canonical import canonical_text

    return canonical_text("consequencemap.guard.payload.v1", document)
