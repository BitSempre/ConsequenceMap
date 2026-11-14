"""The sealing and immutability trigger family.

MC4/R06: the family is GENERATED from the schema, not transcribed from the
specification's illustrative block. The printed block in section 3.3 covers
only `forecast_evidence` and has no child-table UPDATE or DELETE trigger -
so `UPDATE forecast_evidence` and `DELETE FROM forecast_evidence` both
succeed against it. This module emits the complete family:

  2 triggers on `forecast`:
    forecast_seal_only   - permits exactly one transition, NULL -> timestamp
    forecast_no_delete   - DELETE always aborts

  3 triggers on each of the 5 forecast child tables:
    <child>_no_insert_after_seal  - INSERT aborts when the parent is sealed
    <child>_no_update             - UPDATE always aborts
    <child>_no_delete             - DELETE always aborts

  2 triggers on each of the 14 observation tables (section 3.4):
    <table>_no_update            - UPDATE always aborts
    <table>_no_delete            - DELETE always aborts

  2 triggers on product_decision (PD-1, append-only):
    product_decision_no_update
    product_decision_no_delete

  2 triggers on host_authorization (AUTH-12, immutable once resolved):
    host_authorization_no_update
    host_authorization_no_delete

Total: 2 + 15 + 28 + 2 + 2 = 49 triggers.
"""
from __future__ import annotations

from typing import List, Sequence

from .schema import ALL_TABLES, FORECAST_CHILD_TABLES, OBSERVATION_TABLES

#: The columns of `forecast` that the seal may not change.
_FORECAST_IMMUTABLE_COLUMNS = (
    "id",
    "proposal_id",
    "proposal_version",
    "created_at",
    "generator_json",
    "confidence_overall",
    "summary",
    "content_hash",
)


def seal_only_trigger() -> str:
    """The single permitted UPDATE on `forecast`."""
    unchanged = (chr(10) + " AND ").join(
        f"NEW.{column} IS OLD.{column}" for column in _FORECAST_IMMUTABLE_COLUMNS
    )
    return f"""
    CREATE TRIGGER forecast_seal_only BEFORE UPDATE ON forecast
    WHEN NOT (
         OLD.sealed_at IS NULL
     AND NEW.sealed_at IS NOT NULL
     AND {unchanged})
    BEGIN SELECT RAISE(ABORT, 'forecast rows are immutable except for the one-time seal'); END;
    """


def no_delete_trigger(table: str) -> str:
    """A DELETE trigger that always aborts."""
    return f"""
    CREATE TRIGGER {table}_no_delete BEFORE DELETE ON {table}
    BEGIN SELECT RAISE(ABORT, '{table} rows are immutable'); END;
    """


def no_update_trigger(table: str) -> str:
    """An UPDATE trigger that always aborts."""
    return f"""
    CREATE TRIGGER {table}_no_update BEFORE UPDATE ON {table}
    BEGIN SELECT RAISE(ABORT, '{table} rows are immutable'); END;
    """


def no_insert_after_seal_trigger(child: str) -> str:
    """An INSERT trigger that aborts once the parent forecast is sealed."""
    return f"""
    CREATE TRIGGER {child}_no_insert_after_seal BEFORE INSERT ON {child}
    WHEN (SELECT sealed_at FROM forecast WHERE id = NEW.forecast_id) IS NOT NULL
    BEGIN SELECT RAISE(ABORT, 'forecast is sealed'); END;
    """


def host_authorization_immutable_after_resolve_trigger() -> str:
    """AUTH-12: a resolved `host_authorization` is immutable.

    The row may be finalised exactly once (resolved_at NULL -> timestamp).
    After that, no column may change. A correction is a NEW row linked
    by `supersedes`.
    """
    return """
    CREATE TRIGGER host_authorization_resolve_once BEFORE UPDATE ON host_authorization
    WHEN NOT (
         OLD.resolved_at IS NULL
     AND NEW.resolved_at IS NOT NULL
     AND NEW.id IS OLD.id
     AND NEW.forecast_id IS OLD.forecast_id
     AND NEW.proposal_id IS OLD.proposal_id
     AND NEW.proposal_version IS OLD.proposal_version
     AND NEW.state IS OLD.state
     AND NEW.provenance IS OLD.provenance
     AND NEW.authorized_by IS OLD.authorized_by
     AND NEW.observed_choice IS OLD.observed_choice
     AND NEW.observed_via IS OLD.observed_via
     AND NEW.reason IS OLD.reason
     AND NEW.created_at IS OLD.created_at
     AND NEW.escalation_expected IS OLD.escalation_expected)
    BEGIN SELECT RAISE(ABORT, 'host_authorization is immutable once resolved'); END;
    """


def trigger_statements(child_tables: Sequence[str] = FORECAST_CHILD_TABLES) -> List[str]:
    """The complete trigger family, generated from the schema.

    `child_tables` is a parameter so the family is derived from the schema
    rather than from a hand-written list. The test suite asserts the
    count and the per-table coverage.
    """
    statements: List[str] = [seal_only_trigger(), no_delete_trigger("forecast")]

    for child in child_tables:
        statements.append(no_insert_after_seal_trigger(child))
        statements.append(no_update_trigger(child))
        statements.append(no_delete_trigger(child))

    # Section 3.4: every observation entity rejects UPDATE and DELETE.
    # `forecast` is excluded - its UPDATE is the seal, handled above.
    # The forecast CHILD tables are excluded whatever subset was passed:
    # the child loop above is the single authority for them.
    for table in OBSERVATION_TABLES:
        if table in FORECAST_CHILD_TABLES or table == "forecast":
            continue
        statements.append(no_update_trigger(table))
        statements.append(no_delete_trigger(table))

    # PD-1: a product_decision is append-only.
    statements.append(no_update_trigger("product_decision"))
    statements.append(no_delete_trigger("product_decision"))

    # AUTH-12: a host_authorization is immutable once resolved.
    statements.append(host_authorization_immutable_after_resolve_trigger())
    statements.append(no_delete_trigger("host_authorization"))

    return statements


def create_triggers(conn, child_tables: Sequence[str] = FORECAST_CHILD_TABLES) -> int:
    """Install the trigger family. Returns the number of triggers created."""
    statements = trigger_statements(child_tables)
    for statement in statements:
        conn.execute(statement)
    return len(statements)
