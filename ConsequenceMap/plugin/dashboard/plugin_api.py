"""ConsequenceMap's dashboard backend.

Mounted by the host at ``/api/plugins/consequence-map/``.

It exposes the three Desktop surfaces of DEC-17=A over one set of
endpoints, all reading the plugin's own SQLite database:

* **Forecast** - what was predicted, the evidence behind it, the
  risks and the alternatives.
* **Decision** - what was decided, and who authorized it.
* **Outcome** - what actually happened, and the comparison with the
  forecast.

The read path is deliberately narrow: it returns rows, never a path
outside the plugin's own database, and never a raw secret. The
write path is not exposed at all - the plugin writes through its own
repository, from its own hooks.
"""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter

router = APIRouter()

#: Where the plugin's database lives. The host's public storage API
#: is used when it is available; this is the fallback for the
#: in-process demonstration.
def _database_path() -> Optional[str]:
    explicit = os.environ.get("CONSEQUENCE_MAP_DB")
    if explicit:
        return explicit
    home = os.environ.get("HERMES_HOME") or os.path.expanduser("~/.hermes")
    candidate = Path(home) / "plugin-data" / "consequence-map" / "data.db"
    return str(candidate) if candidate.exists() else None


def _connect() -> Optional[sqlite3.Connection]:
    path = _database_path()
    if not path or not os.path.exists(path):
        return None
    try:
        connection = sqlite3.connect(path)
        connection.row_factory = sqlite3.Row
        return connection
    except sqlite3.Error:
        return None


def _rows(statement: str, parameters: tuple = ()) -> List[Dict[str, Any]]:
    connection = _connect()
    if connection is None:
        return []
    try:
        cursor = connection.execute(statement, parameters)
        return [dict(row) for row in cursor.fetchall()]
    except sqlite3.Error:
        return []
    finally:
        connection.close()


@router.get("/forecast")
def get_forecast(forecast_id: str = "") -> Dict[str, Any]:
    """The forecast, its evidence, its risks and its alternatives."""
    if forecast_id:
        forecasts = _rows(
            "SELECT * FROM forecast WHERE forecast_id = ?", (forecast_id,)
        )
        if not forecasts:
            return {"found": False, "forecast": None, "evidence": [],
                    "risks": [], "alternatives": [], "unknowns": []}
        evidence = _rows(
            "SELECT * FROM forecast_evidence WHERE forecast_id = ?", (forecast_id,)
        )
        risks = _rows(
            "SELECT * FROM forecast_risk WHERE forecast_id = ?", (forecast_id,)
        )
        alternatives = _rows(
            "SELECT * FROM forecast_alternative WHERE forecast_id = ?",
            (forecast_id,),
        )
        unknowns = _rows(
            "SELECT * FROM forecast_unknown WHERE forecast_id = ?", (forecast_id,)
        )
        return {
            "found": True,
            "forecast": forecasts[0],
            "evidence": evidence,
            "risks": risks,
            "alternatives": alternatives,
            "unknowns": unknowns,
        }
    forecasts = _rows("SELECT * FROM forecast ORDER BY created_at DESC LIMIT 50")
    return {"found": bool(forecasts), "forecast": None, "forecasts": forecasts,
            "evidence": [], "risks": [], "alternatives": [], "unknowns": []}


@router.get("/decision")
def get_decision(forecast_id: str = "") -> Dict[str, Any]:
    """The product decision, and the host's authorization record.

    The two are returned side by side and never merged. The product's
    decision is the agent's own reasoning; the authorization is the
    host's record of what a human did.
    """
    decisions = _rows(
        "SELECT * FROM product_decision ORDER BY decided_at DESC LIMIT 50"
    )
    authorizations = _rows(
        "SELECT * FROM host_authorization ORDER BY requested_at DESC LIMIT 50"
    )
    if forecast_id:
        decisions = [d for d in decisions if d.get("forecast_id") == forecast_id]
        authorizations = [
            a for a in authorizations if a.get("forecast_id") == forecast_id
        ]
    return {
        "found": bool(decisions or authorizations),
        "decisions": decisions,
        "authorizations": authorizations,
        "separation": (
            "The product decision is the agent's reasoning. The host "
            "authorization is what a human did. They are correlated for "
            "display only and are never merged."
        ),
    }


@router.get("/outcome")
def get_outcome(forecast_id: str = "") -> Dict[str, Any]:
    """What actually happened, and the comparison with the forecast."""
    outcomes = _rows("SELECT * FROM outcome ORDER BY observed_at DESC LIMIT 50")
    observations = _rows(
        "SELECT * FROM outcome_observation ORDER BY observed_at DESC LIMIT 200"
    )
    comparisons = _rows(
        "SELECT * FROM comparison ORDER BY compared_at DESC LIMIT 50"
    )
    comparison_items = _rows(
        "SELECT * FROM comparison_item ORDER BY rowid DESC LIMIT 500"
    )
    if forecast_id:
        outcomes = [o for o in outcomes if o.get("forecast_id") == forecast_id]
        comparisons = [
            c for c in comparisons if c.get("forecast_id") == forecast_id
        ]
        outcome_ids = {o.get("outcome_id") for o in outcomes}
        observations = [
            o for o in observations if o.get("outcome_id") in outcome_ids
        ]
        comparison_ids = {c.get("comparison_id") for c in comparisons}
        comparison_items = [
            i for i in comparison_items
            if i.get("comparison_id") in comparison_ids
        ]
    return {
        "found": bool(outcomes or comparisons),
        "outcomes": outcomes,
        "observations": observations,
        "comparisons": comparisons,
        "comparison_items": comparison_items,
    }


@router.get("/status")
def get_status() -> Dict[str, Any]:
    """Whether the plugin has anything to show, and what it cannot show."""
    path = _database_path()
    counts = {}
    if path and os.path.exists(path):
        for table in (
            "forecast", "forecast_evidence", "product_decision",
            "host_authorization", "execution", "outcome", "comparison",
        ):
            rows = _rows("SELECT COUNT(*) AS n FROM %s" % table)
            counts[table] = rows[0]["n"] if rows else 0
    return {
        "database": path,
        "database_present": bool(path and os.path.exists(path)),
        "counts": counts,
        "not_verifiable": (
            "An outcome with no observation stays NOT_VERIFIABLE. It is "
            "never presented as a confirmation."
        ),
    }
