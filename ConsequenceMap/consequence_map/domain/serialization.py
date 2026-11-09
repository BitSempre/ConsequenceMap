"""Envelope <-> relational model (specification section 10).

The RELATIONAL model is authoritative; the envelope is the wire form.

M-6: every envelope field has exactly one storage location. The mapping
    table below is that mapping, and it is the ONLY mapping.
M-7: the serialiser is the only code that produces an envelope. There is
    no reverse converter - a row set is never turned back into an
    envelope by this module.
M-8: serialisation is deterministic - sorted keys, fixed field order,
    RFC 3339 timestamps.
M-10: `content_hash` is computed over the canonical ROW serialisation,
    not over the envelope serialisation.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Mapping, Optional, Sequence

from ..storage.schema import COLUMN_ORDER

#: The envelope path -> storage location mapping of specification section 10.
#: One entry per envelope path; each maps to exactly ONE storage location.
ENVELOPE_TO_STORAGE: Mapping[str, str] = {
    "data.proposal": "proposal",
    "data.forecast": "forecast.generator_json",
    "data.forecast.evidence[]": "forecast_evidence",
    "data.forecast.impact[]": "forecast_impact",
    "data.forecast.risk": "forecast_risk.dimension_caveats_json",
    "data.forecast.alternatives[]": "forecast_alternative",
    "data.forecast.unknowns[]": "forecast_unknown",
    "data.host_authorization": "host_authorization",
    "data.product_decision": "product_decision",
    "data.execution": "execution",
    "data.execution.tool_calls[]": "execution_tool_call",
    "data.outcome": "outcome",
    "data.outcome.observations[]": "outcome_observation",
    "data.comparison": "comparison.counts_json",
    "data.comparison.items[]": "comparison_item",
    "data.alternative_evaluation": "alternative_evaluation",
}


def canonical_json(value: Any) -> str:
    """Deterministic JSON: sorted keys, compact separators, UTF-8 (M-8)."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def canonical_row_serialisation(table: str, row: Mapping[str, Any]) -> str:
    """The canonical serialisation of ONE row.

    Used for `content_hash` (M-10). The field order is the table's DDL
    column order - NOT sorted alphabetically: M-8 requires a FIXED field
    order, and the DDL order is the fixed one. The JSON is otherwise
    deterministic (compact separators, UTF-8), so the hash is stable
    across runs and across Python versions.
    """
    if table not in COLUMN_ORDER:
        raise KeyError(f"unknown table {table}")
    ordered = {column: row.get(column) for column in COLUMN_ORDER[table]}
    return json.dumps(ordered, separators=(",", ":"), ensure_ascii=False)


def content_hash(header: Mapping[str, Any], children: Sequence[Mapping[str, Any]]) -> str:
    """The sha256 over the canonical ROW serialisation (M-10, AC-DATA-33).

    The hash is computed over the rows, NOT over the envelope. The header
    is serialised without its own `content_hash` field, because the hash
    cannot include itself.
    """
    header_payload = {
        key: value for key, value in header.items() if key != "content_hash"
    }
    payload = {
        "header": header_payload,
        "children": [dict(child) for child in children],
    }
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def envelope(kind: str, identifier: str, created_at: str, data: Mapping[str, Any]) -> Dict[str, Any]:
    """Build a root envelope (specification section 2.12).

    `schema_version` is 1 (AC-DATA-01). The envelope carries only the
    four documented keys.
    """
    return {
        "schema_version": 1,
        "kind": kind,
        "id": identifier,
        "created_at": created_at,
        "data": dict(data),
    }


def envelope_to_json(env: Mapping[str, Any]) -> str:
    """The wire form of an envelope: deterministic JSON (M-8)."""
    return canonical_json(env)


def build_forecast_envelope(
    forecast_row: Mapping[str, Any],
    evidence: Sequence[Mapping[str, Any]],
    impact: Sequence[Mapping[str, Any]],
    risk: Mapping[str, Any],
    alternatives: Sequence[Mapping[str, Any]],
    unknowns: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    """Build the `forecast` envelope from its rows.

    This is the ONLY producer of a forecast envelope (M-7).
    """
    generator = forecast_row.get("generator_json")
    if isinstance(generator, str):
        generator = json.loads(generator)
    caveats = risk.get("dimension_caveats_json")
    if isinstance(caveats, str):
        caveats = json.loads(caveats)
    data = {
        "id": forecast_row.get("id"),
        "proposal_id": forecast_row.get("proposal_id"),
        "proposal_version": forecast_row.get("proposal_version"),
        "created_at": forecast_row.get("created_at"),
        "generator": generator,
        "confidence_overall": forecast_row.get("confidence_overall"),
        "summary": forecast_row.get("summary"),
        "content_hash": forecast_row.get("content_hash"),
        "sealed_at": forecast_row.get("sealed_at"),
        "evidence": [dict(e) for e in evidence],
        "impact": [dict(i) for i in impact],
        "risk": {
            "severity": risk.get("severity"),
            "confidence": risk.get("confidence"),
            "reversibility": risk.get("reversibility"),
            "reason": risk.get("reason"),
            "escalation_rule": risk.get("escalation_rule"),
            "requires_human_approval": bool(risk.get("requires_human_approval")),
            "dimension_caveats": caveats or [],
        },
        "alternatives": [dict(a) for a in alternatives],
        "unknowns": [dict(u) for u in unknowns],
    }
    return envelope("forecast", str(forecast_row.get("id")), str(forecast_row.get("created_at")), data)
