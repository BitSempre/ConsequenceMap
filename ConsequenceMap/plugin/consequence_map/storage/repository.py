"""The single write-path owner for every table (specification section 3.5).

Exactly one writer per table; the Desktop half is read-only over the
database (AC-STORE-15). This module is that writer.

PR-2: redaction is applied INSIDE the storage layer, beneath every write
path. Every free-text field that reaches the database goes through
`redaction.boundary` here, so no caller can bypass it.

Section 3.4: there is NO write path from `outcome`, `outcome_observation`,
`comparison`, `comparison_item`, `host_authorization` or
`product_decision` to any `forecast*` table (AC-STORE-11). This module
has no method that can do it, and the static audit test proves it.

Rows are TUPLES, not `sqlite3.Row`: `plugin_db` sets `row_factory=None`
(MC7/R04). Columns are addressed by index.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from ..domain import records as R
from ..domain.validation import now_timestamp
from ..redaction.boundary import redact_and_cap, redact_for_storage
from .db import transaction
from .schema import COLUMN_ORDER

def _dumps(value: Any) -> str:
    """Deterministic JSON: sorted keys, compact separators (M-8)."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _row(table: str, values: Mapping[str, Any]) -> Tuple[Any, ...]:
    """Build a tuple row in the table's canonical column order."""
    order = COLUMN_ORDER[table]
    return tuple(values.get(column) for column in order)


def _insert(conn: sqlite3.Connection, table: str, values: Mapping[str, Any]) -> None:
    order = COLUMN_ORDER[table]
    placeholders = ",".join("?" for _ in order)
    columns = ",".join(order)
    conn.execute(
        f"INSERT INTO {table} ({columns}) VALUES ({placeholders})",
        _row(table, values),
    )


def digest(value: Any) -> str:
    """The sha256 digest of a value. Raw arguments and results are NEVER stored."""
    if isinstance(value, bytes):
        payload = value
    else:
        payload = str(value).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


class AlreadySealedError(RuntimeError):
    """Raised when a forecast is sealed twice. The seal happens once."""

    def __init__(self, forecast_id: str) -> None:
        super().__init__(f"forecast {forecast_id} is already sealed")
        self.forecast_id = forecast_id


class Repository:
    """The single write-path owner for every table."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    # ------------------------------------------------------------------
    # proposal
    # ------------------------------------------------------------------
    def write_proposal(self, proposal: R.Proposal) -> str:
        """Write one proposal version. Redaction is applied to `action`."""
        proposal.validate()
        action, _changed, _truncated = redact_and_cap(proposal.action, "proposal.action")
        values = {
            "id": proposal.id,
            "version": proposal.version,
            "created_at": proposal.created_at,
            "actor": proposal.actor,
            "action": action,
            "operation": proposal.operation,
            "target_kind": proposal.target_kind,
            "target_json": _dumps(proposal.target),
            "scope_json": _dumps(proposal.scope),
            "preconditions_json": _dumps(proposal.preconditions) if proposal.preconditions is not None else None,
            "expected_outputs_json": _dumps(proposal.expected_outputs) if proposal.expected_outputs is not None else None,
            "external_side_effects_json": _dumps(proposal.external_side_effects) if proposal.external_side_effects is not None else None,
            "rollback": proposal.rollback,
            "session_id": proposal.session_id,
            "turn_id": proposal.turn_id,
            "tool_call_id": proposal.tool_call_id,
        }
        with transaction(self.conn):
            _insert(self.conn, "proposal", values)
        return proposal.id

    # ------------------------------------------------------------------
    # forecast
    # ------------------------------------------------------------------
    def write_forecast(self, forecast: R.Forecast) -> str:
        """Write a forecast header and all its children, unsealed.

        The children are written here so the seal protocol can run as one
        transaction (section 3.3). `content_hash` must already be computed
        (AC-STORE-09) - the seal trigger permits no other column change.
        """
        forecast.validate()
        summary, _c, _t = redact_and_cap(forecast.summary, "forecast.summary")
        generator = dict(forecast.generator)
        # PATH-1: the authorized root is never persisted verbatim. Only a
        # stable 16-hex digest of the resolved root is stored.
        if "root" in generator:
            generator["root_digest"] = digest(generator.pop("root"))[:16]
        values = {
            "id": forecast.id,
            "proposal_id": forecast.proposal_id,
            "proposal_version": forecast.proposal_version,
            "created_at": forecast.created_at,
            "generator_json": _dumps(generator),
            "confidence_overall": forecast.confidence_overall,
            "summary": summary,
            "content_hash": forecast.content_hash,
            "sealed_at": None,
        }
        with transaction(self.conn, immediate=True):
            _insert(self.conn, "forecast", values)
            for item in (forecast.evidence or []):
                self._insert_evidence(forecast.id, item)
            for item in (forecast.impact or []):
                self._insert_impact(forecast.id, item)
            if forecast.risk is not None:
                self._insert_risk(forecast.id, forecast.risk)
            for item in (forecast.alternatives or []):
                self._insert_alternative(forecast.id, item)
            for item in (forecast.unknowns or []):
                self._insert_unknown(forecast.id, item)
        return forecast.id

    def seal_forecast(self, forecast_id: str, sealed_at: Optional[str] = None) -> str:
        """The single permitted UPDATE on `forecast` (section 3.3).

        The UPDATE is guarded by `sealed_at IS NULL`, so a second seal
        matches ZERO rows and does not fire the trigger. The returned
        value is the seal timestamp; `seal_forecast` raises if the row
        was already sealed, so a caller cannot mistake a no-op for a
        seal.
        """
        stamp = sealed_at or now_timestamp()
        with transaction(self.conn, immediate=True):
            cursor = self.conn.execute(
                "UPDATE forecast SET sealed_at = ? WHERE id = ? AND sealed_at IS NULL",
                (stamp, forecast_id),
            )
            sealed = cursor.rowcount == 1
        if not sealed:
            raise AlreadySealedError(forecast_id)
        return stamp

    def _insert_evidence(self, forecast_id: str, item: R.Evidence) -> None:
        item.validate()
        claim, _c, _t = redact_and_cap(item.claim, "evidence.claim")
        source_ref, _c, _t = redact_and_cap(item.source_ref, "evidence.source_ref")
        limitations, _c, _t = redact_and_cap(item.limitations, "evidence.limitations")
        _insert(self.conn, "forecast_evidence", {
            "forecast_id": forecast_id, "id": item.id, "claim": claim,
            "classification": item.classification, "source_kind": item.source_kind,
            "source_ref": source_ref, "observed_at": item.observed_at,
            "confidence": item.confidence, "limitations": limitations,
        })

    def _insert_impact(self, forecast_id: str, item: R.Impact) -> None:
        item.validate()
        target, _c, _t = redact_and_cap(item.target, "impact.target")
        reason, _c, _t = redact_and_cap(item.reason, "impact.reason")
        _insert(self.conn, "forecast_impact", {
            "forecast_id": forecast_id, "id": item.id, "target": target,
            "impact_class": item.impact_class, "relation": item.relation,
            "classification": item.classification,
            "severity_contribution": item.severity_contribution,
            "confidence": item.confidence, "reason": reason,
            "observable": 1 if item.observable else 0,
        })

    def _insert_risk(self, forecast_id: str, risk: R.Risk) -> None:
        risk.validate()
        reason, _c, _t = redact_and_cap(risk.reason, "forecast_risk.reason")
        _insert(self.conn, "forecast_risk", {
            "forecast_id": forecast_id, "severity": risk.severity,
            "confidence": risk.confidence, "reversibility": risk.reversibility,
            "reason": reason, "escalation_rule": risk.escalation_rule,
            "requires_human_approval": 1 if risk.requires_human_approval else 0,
            "dimension_caveats_json": _dumps(risk.dimension_caveats),
        })

    def _insert_alternative(self, forecast_id: str, item: R.Alternative) -> None:
        item.validate()
        description, _c, _t = redact_and_cap(item.description, "alternative.description")
        _insert(self.conn, "forecast_alternative", {
            "forecast_id": forecast_id, "id": item.id, "description": description,
            "expected_benefit": item.expected_benefit,
            "impact_reduction": item.impact_reduction,
            "tradeoffs": item.tradeoffs,
            "residual_uncertainty": item.residual_uncertainty,
            "recommended": 1 if item.recommended else 0,
        })

    def _insert_unknown(self, forecast_id: str, item: R.Unknown) -> None:
        item.validate()
        question, _c, _t = redact_and_cap(item.question, "unknown.question")
        why, _c, _t = redact_and_cap(item.why_it_matters, "unknown.why_it_matters")
        resolve, _c, _t = redact_and_cap(
            item.evidence_that_would_resolve, "unknown.evidence_that_would_resolve"
        )
        _insert(self.conn, "forecast_unknown", {
            "forecast_id": forecast_id, "id": item.id, "question": question,
            "why_it_matters": why, "evidence_that_would_resolve": resolve,
        })

    # ------------------------------------------------------------------
    # host_authorization / product_decision
    # ------------------------------------------------------------------
    def write_host_authorization(self, record: R.HostAuthorization) -> str:
        """Write one authorization observation."""
        record.validate()
        notes, _c, _t = redact_and_cap(record.notes, "host_authorization.notes")
        values = {
            "id": record.id, "forecast_id": record.forecast_id,
            "proposal_id": record.proposal_id,
            "proposal_version": record.proposal_version,
            "tool_call_id": record.tool_call_id, "rule_key": record.rule_key,
            "pattern_key": record.pattern_key, "state": record.state,
            "provenance": record.provenance, "authorized_by": record.authorized_by,
            "observed_choice": record.observed_choice,
            "observed_via": record.observed_via, "reason": record.reason,
            "created_at": record.created_at, "resolved_at": record.resolved_at,
            "escalation_expected": 1 if record.escalation_expected else 0,
            "notes": notes, "supersedes": record.supersedes,
        }
        with transaction(self.conn):
            _insert(self.conn, "host_authorization", values)
        return record.id

    def resolve_host_authorization(self, record_id: str, resolved_at: Optional[str] = None,
                                   notes: Optional[str] = None) -> str:
        """Finalise a pending authorization exactly once (AUTH-12)."""
        stamp = resolved_at or now_timestamp()
        safe_notes = redact_for_storage(notes, field="host_authorization.notes")
        with transaction(self.conn, immediate=True):
            self.conn.execute(
                "UPDATE host_authorization SET resolved_at = ?, notes = ? "
                "WHERE id = ? AND resolved_at IS NULL",
                (stamp, safe_notes, record_id),
            )
        return stamp

    def write_product_decision(self, record: R.ProductDecision) -> str:
        """Append one product decision. Never updates an existing row (PD-1)."""
        record.validate()
        note, _c, _t = redact_and_cap(record.scope_note, "product_decision.scope_note")
        values = {
            "id": record.id, "forecast_id": record.forecast_id,
            "proposal_id": record.proposal_id,
            "proposal_version": record.proposal_version, "state": record.state,
            "decided_by": record.decided_by, "decided_at": record.decided_at,
            "surface": record.surface, "scope_note": note,
            "supersedes": record.supersedes,
        }
        with transaction(self.conn):
            _insert(self.conn, "product_decision", values)
        return record.id

    # ------------------------------------------------------------------
    # execution
    # ------------------------------------------------------------------
    def write_execution(self, execution: R.Execution) -> str:
        """Write one execution and its tool calls."""
        execution.validate()
        values = {
            "id": execution.id, "forecast_id": execution.forecast_id,
            "host_authorization_id": execution.host_authorization_id,
            "product_decision_id": execution.product_decision_id,
            "started_at": execution.started_at, "ended_at": execution.ended_at,
            "status": execution.status, "trigger_tool": execution.trigger_tool,
            "source": execution.source, "tool_call_id": execution.tool_call_id,
            "error_type": execution.error_type,
        }
        with transaction(self.conn):
            _insert(self.conn, "execution", values)
            for seq, call in enumerate(execution.tool_calls, start=1):
                _insert(self.conn, "execution_tool_call", {
                    "execution_id": execution.id, "seq": seq,
                    "tool_name": call.tool_name, "args_digest": call.args_digest,
                    "result_digest": call.result_digest, "status": call.status,
                    "duration_ms": call.duration_ms, "error_type": call.error_type,
                })
        return execution.id

    # ------------------------------------------------------------------
    # outcome
    # ------------------------------------------------------------------
    def write_outcome(self, outcome: R.Outcome) -> str:
        """Write one outcome and its observations."""
        outcome.validate()
        summary, _c, _t = redact_and_cap(outcome.summary, "outcome.summary")
        values = {
            "id": outcome.id, "forecast_id": outcome.forecast_id,
            "execution_id": outcome.execution_id, "recorded_at": outcome.recorded_at,
            "recorded_by": outcome.recorded_by,
            "verification_method": outcome.verification_method,
            "summary": summary,
        }
        with transaction(self.conn):
            _insert(self.conn, "outcome", values)
            for obs in outcome.observations:
                observation, _c, _t = redact_and_cap(
                    obs.observation, "outcome_observation.observation"
                )
                target, _c, _t = redact_and_cap(obs.target, "outcome_observation.target")
                _insert(self.conn, "outcome_observation", {
                    "outcome_id": outcome.id, "id": obs.id, "target": target,
                    "observation": observation, "label": obs.label,
                    "evidence_source_kind": obs.evidence_source_kind,
                    "evidence_ref": obs.evidence_ref, "confidence": obs.confidence,
                })
        return outcome.id

    # ------------------------------------------------------------------
    # comparison
    # ------------------------------------------------------------------
    def write_comparison(self, comparison: R.Comparison) -> str:
        """Write one comparison and its items."""
        comparison.validate()
        note, _c, _t = redact_and_cap(comparison.accuracy_note, "comparison.accuracy_note")
        values = {
            "id": comparison.id, "forecast_id": comparison.forecast_id,
            "outcome_id": comparison.outcome_id, "created_at": comparison.created_at,
            "verdict": comparison.verdict, "counts_json": _dumps(comparison.counts),
            "accuracy_note": note,
        }
        with transaction(self.conn):
            _insert(self.conn, "comparison", values)
            for item in comparison.items:
                item_note, _c, _t = redact_and_cap(item.note, "comparison_item.note")
                _insert(self.conn, "comparison_item", {
                    "comparison_id": comparison.id, "id": item.id,
                    "origin": item.origin, "forecast_ref": item.forecast_ref,
                    "forecast_ref_kind": item.forecast_ref_kind,
                    "observed_ref": item.observed_ref, "label": item.label,
                    "note": item_note,
                })
        return comparison.id

    def write_alternative_evaluation(self, evaluation: R.AlternativeEvaluation) -> str:
        """Write one alternative evaluation."""
        evaluation.validate()
        rationale, _c, _t = redact_and_cap(evaluation.rationale, "alternative.rationale")
        values = {
            "id": evaluation.id, "forecast_id": evaluation.forecast_id,
            "alternative_id": evaluation.alternative_id,
            "disposition": evaluation.disposition, "rationale": rationale,
            "evaluated_at": evaluation.evaluated_at,
        }
        with transaction(self.conn):
            _insert(self.conn, "alternative_evaluation", values)
        return evaluation.id

    # ------------------------------------------------------------------
    # Read paths
    # ------------------------------------------------------------------
    def read_sealed_forecasts(self) -> List[Tuple[Any, ...]]:
        """Every SEALED forecast.

        An unsealed forecast is invisible to every read path
        (AC-STORE-10, AC-DATA-16).
        """
        return list(self.conn.execute(
            "SELECT * FROM forecast WHERE sealed_at IS NOT NULL ORDER BY id"
        ))

    def read_forecast(self, forecast_id: str) -> Optional[Tuple[Any, ...]]:
        """One SEALED forecast, or None when it is unsealed or absent."""
        return self.conn.execute(
            "SELECT * FROM forecast WHERE id = ? AND sealed_at IS NOT NULL",
            (forecast_id,),
        ).fetchone()

    def read_all_rows(self, table: str) -> List[Tuple[Any, ...]]:
        """Every row of `table`. Used by the storage-inspection tests."""
        if table not in COLUMN_ORDER:
            raise KeyError(f"unknown table {table}")
        return list(self.conn.execute(f"SELECT * FROM {table}"))

    def table_names(self) -> List[str]:
        """Every table in the database."""
        return [r[0] for r in self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )]
