"""Connection acquisition, journal mode and profile scope.

MC1/R01: this is the ONLY module in the package that may import a Hermes
module, and it does so LAZILY, inside a function body, behind an
injectable connection-provider seam. Importing this module imports no
Hermes code at all.

MC2/R03: the plugin OWNS the connection. `transaction()` here commits
and rolls back but does NOT close - the host's
`hermes_cli.sqlite_util.transaction()` always closes the connection in
its `finally` block, which would break the multi-statement seal.

MC3/R02: WAL is REQUESTED, not guaranteed. The host falls back to DELETE
under four reachable conditions. The observed mode is recorded.
"""
from __future__ import annotations

import contextlib
import os
import sqlite3
from typing import Callable, Iterator, Optional

#: The plugin's database name, as passed to `plugin_db`.
PLUGIN_DB_NAME = "consequence-map"

#: The relative path of the database inside the plugin data directory.
DB_RELATIVE_PATH = ("plugin-data", PLUGIN_DB_NAME, "data.db")

#: A connection provider: given a path, return an open connection.
ConnectionProvider = Callable[[str], sqlite3.Connection]

#: The provider installed by `set_connection_provider`.
_PROVIDER: Optional[ConnectionProvider] = None


def set_connection_provider(provider: Optional[ConnectionProvider]) -> None:
    """Install (or clear) the connection provider.

    The test suite injects a provider that opens a temporary SQLite file.
    The production default resolves the Hermes home on every call.
    """
    global _PROVIDER
    _PROVIDER = provider


def get_connection_provider() -> ConnectionProvider:
    """The active connection provider."""
    return _PROVIDER if _PROVIDER is not None else hermes_connection_provider


# --------------------------------------------------------------------------
# Profile scope (AC-STORE-16)
# --------------------------------------------------------------------------
def hermes_home() -> str:
    """The Hermes home directory, resolved on EVERY call.

    The specification requires the path to be resolved from
    `get_hermes_home()` on every access, so that a profile change is
    picked up without a restart (AC-STORE-16).

    The import is inside the function: importing this module must not
    import Hermes.
    """
    from hermes_cli.config import get_hermes_home  # noqa: PLC0415 - deliberate lazy import

    return get_hermes_home()


def database_path(home: Optional[str] = None) -> str:
    """The absolute path of the plugin's database.

    Resolved from the Hermes home on every call (AC-STORE-16).
    """
    base = home if home is not None else hermes_home()
    return os.path.join(base, *DB_RELATIVE_PATH)


# --------------------------------------------------------------------------
# The production connection provider
# --------------------------------------------------------------------------
def hermes_connection_provider(path: str) -> sqlite3.Connection:
    """Open the production connection through `plugin_db`.

    This is the single Hermes import site of the package. It is inside a
    function body, so importing `storage.db` imports no Hermes code.

    `plugin_db` sets `row_factory=None` (so rows are TUPLES) and
    `foreign_keys=True` (so the composite foreign key is enforced).
    """
    from plugins.plugin_storage import plugin_db  # noqa: PLC0415 - the single Hermes import

    return plugin_db(PLUGIN_DB_NAME)


def _ensure_parent(path: str) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)


def connect(path: Optional[str] = None, provider: Optional[ConnectionProvider] = None) -> sqlite3.Connection:
    """Open a connection to the plugin's database.

    `path` overrides the resolved location (the test suite uses a
    temporary path). `provider` overrides the connection provider.
    """
    if path is None:
        path = database_path()
    else:
        _ensure_parent(path)
    active = provider if provider is not None else get_connection_provider()
    return active(path)


# --------------------------------------------------------------------------
# Journal mode (AC-STORE-17 / MC3 / R02)
# --------------------------------------------------------------------------
#: The journal modes the host may legitimately grant.
SUPPORTED_JOURNAL_MODES = ("wal", "delete")


def observed_journal_mode(conn: sqlite3.Connection) -> str:
    """The journal mode actually in force on this connection."""
    row = conn.execute("PRAGMA journal_mode").fetchone()
    return str(row[0]).lower() if row else ""


def request_wal(conn: sqlite3.Connection) -> str:
    """Request WAL and return the mode actually obtained.

    The host's `apply_wal_with_fallback` may return DELETE. The caller
    records the observed mode; it does NOT treat DELETE as an error.
    """
    conn.execute("PRAGMA journal_mode=WAL")
    return observed_journal_mode(conn)


def configure_connection(conn: sqlite3.Connection, *, request_wal_mode: bool = True) -> str:
    """Apply the connection settings and return the observed journal mode.

    Foreign keys are enabled (the composite FK is intended to be
    enforced), and the journal mode is requested and then observed.
    """
    conn.execute("PRAGMA foreign_keys=ON")
    if request_wal_mode:
        return request_wal(conn)
    return observed_journal_mode(conn)


# --------------------------------------------------------------------------
# The plugin's own transaction manager (MC2 / R03)
# --------------------------------------------------------------------------
@contextlib.contextmanager
def transaction(conn: sqlite3.Connection, *, immediate: bool = False) -> Iterator[sqlite3.Connection]:
    """The plugin's transaction scope.

    Commits on success, rolls back on error, and **does not close** the
    connection. The host's `hermes_cli.sqlite_util.transaction()` always
    closes the connection in its `finally` block; using it here would
    break the multi-statement seal, so this module provides its own.
    """
    try:
        if immediate:
            conn.execute("BEGIN IMMEDIATE")
        with conn:
            yield conn
    except Exception:
        try:
            conn.rollback()
        except sqlite3.Error:
            pass
        raise
