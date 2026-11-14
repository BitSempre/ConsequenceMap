"""Forward-only, transactional migrations (specification section 3.7).

`schema_meta.schema_version` records the applied version. A migration is
applied inside a transaction: a failure rolls back and leaves the
database at its previous version (AC-STORE-19).

A database whose `schema_version` is NEWER than this build supports is
opened READ-ONLY (AC-STORE-18) - a newer schema may contain
constraints this build does not know, and writing into it would corrupt
a database the user may roll back to.
"""
from __future__ import annotations

import sqlite3
from typing import List, NamedTuple, Sequence

from .db import transaction
from .schema import create_schema
from .triggers import create_triggers


class Migration(NamedTuple):
    """One forward-only migration step."""

    version: int
    name: str
    apply: object  # callable(conn) -> None


class MigrationError(RuntimeError):
    """Raised when a migration cannot be applied."""


class NewerSchemaError(MigrationError):
    """Raised when the database is newer than this build supports."""


def current_version(conn: sqlite3.Connection) -> int:
    """The applied schema version, or 0 for a fresh database."""
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_meta'"
    ).fetchone()
    if row is None:
        return 0
    version = conn.execute("SELECT MAX(schema_version) FROM schema_meta").fetchone()
    return int(version[0]) if version and version[0] is not None else 0


def is_read_only_required(conn: sqlite3.Connection, supported_version: int) -> bool:
    """True when the database is newer than this build supports."""
    return current_version(conn) > supported_version


def _migration_001(conn: sqlite3.Connection) -> None:
    """Create the schema of specification section 3.2 and its trigger family."""
    create_schema(conn)
    create_triggers(conn)


#: The migration chain. Forward-only: there is no `down`.
MIGRATIONS: Sequence[Migration] = (
    Migration(1, "initial_schema", _migration_001),
)

#: The schema version this build supports.
SUPPORTED_VERSION = MIGRATIONS[-1].version


def apply_migrations(conn: sqlite3.Connection, *, supported_version: int = SUPPORTED_VERSION) -> int:
    """Apply every pending migration, each in its own transaction.

    Returns the resulting schema version. A failure rolls the failing
    migration back and leaves the earlier ones applied - each migration
    is independently transactional.
    """
    version = current_version(conn)
    if version > supported_version:
        raise NewerSchemaError(
            f"the database schema is version {version}, newer than the "
            f"supported version {supported_version}; open it read-only"
        )
    for migration in MIGRATIONS:
        if migration.version <= version:
            continue
        with transaction(conn, immediate=True):
            migration.apply(conn)
            conn.execute(
                "INSERT OR REPLACE INTO schema_meta(schema_version, applied_at) "
                "VALUES (?, datetime('now'))",
                (migration.version,),
            )
        version = migration.version
    return version


def open_for_write(conn: sqlite3.Connection, *, supported_version: int = SUPPORTED_VERSION) -> bool:
    """Prepare `conn` for writing.

    Returns False when the database is newer than this build supports -
    the caller must then open it read-only (AC-STORE-18).
    """
    if is_read_only_required(conn, supported_version):
        return False
    apply_migrations(conn, supported_version=supported_version)
    return True
