"""The end-to-end demonstration.

Run it::

    python -m demo.consequence_map_demo

It walks one operation through the whole product loop - proposal,
forecast, decision, authorization, execution, outcome, comparison -
against a real temporary SQLite database with the real schema and the
real triggers, and prints what a reviewer would see.

It is honest about what it is: the **product lifecycle** runs for
real. The Hermes integration - the hooks and the Desktop surfaces -
is exercised by the test suite, not by this script. The script says
so at the end.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from consequence_map.domain import records as R
from consequence_map.lifecycle import Lifecycle
from consequence_map.storage import db as db_module
from consequence_map.storage.migrations import apply_migrations
from consequence_map.storage.repository import Repository

TS = "2026-11-10T12:00:00.000Z"


def _provider(path):
    import sqlite3

    connection = sqlite3.connect(path)
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def _heading(text):
    print()
    print("=" * 74)
    print(text)
    print("=" * 74)


def _show(label, value):
    print("  %-28s %s" % (label + ":", value))


def main() -> int:
    directory = tempfile.mkdtemp(prefix="cm-demo-")
    database = os.path.join(directory, "data.db")
    connection = db_module.connect(database, provider=_provider)
    apply_migrations(connection)
    repository = Repository(connection)
    lifecycle = Lifecycle(repository)

    try:
        _heading("CONSEQUENCEMAP - see what happens before it happens")
        print("  A proposal becomes a forecast, the forecast becomes a")
        print("  decision, the decision becomes an execution, and the")
        print("  execution is compared with what was predicted.")

        # ---- 1. the proposal ------------------------------------------
        _heading("1. WHAT WAS ABOUT TO HAPPEN")
        proposal = R.Proposal(
            id="prop_000000000001", version=1, created_at=TS, actor="agent",
            action="overwrite the quarterly report",
            operation="FILE_WRITE", target_kind="FILESYSTEM",
            target={"paths": ["reports/q3.md"]},
            scope={"included": ["reports/"], "excluded": ["secrets/"]},
            preconditions=["the workspace exists"],
            expected_outputs=["reports/q3.md"],
            external_side_effects=[], rollback="restore the previous file",
            session_id="sess_demo", turn_id="turn_demo",
            tool_call_id="tc_demo",
        )
        repository.write_proposal(proposal)
        _show("action", proposal.action)
        _show("target", proposal.target["paths"][0])
        _show("rollback", proposal.rollback)

        # ---- 2. the forecast ------------------------------------------
        _heading("2. WHAT CONSEQUENCEMAP PREDICTED")
        forecast = R.Forecast(
            id="fc_0000000000001", proposal_id=proposal.id,
            proposal_version=1, created_at=TS,
            generator={"provider": "local", "model": "none",
                       "purpose": "demo", "scanner_version": "1",
                       "deterministic": True, "root": "C:/demo"},
            confidence_overall="MEDIUM",
            summary="the quarterly report is overwritten; the previous "
                    "content is lost unless the backup exists",
            content_hash="0" * 64,
            evidence=[
                R.Evidence(id="ev_0000000000001",
                           claim="reports/q3.md exists and is writable",
                           classification="VERIFIED_FACT",
                           source_kind="FILESYSTEM",
                           source_ref="reports/q3.md", observed_at=TS,
                           confidence="HIGH", limitations="none"),
                R.Evidence(id="ev_0000000000002",
                           claim="no backup of the previous content exists",
                           classification="INFERENCE",
                           source_kind="FILESYSTEM",
                           source_ref="reports/", observed_at=TS,
                           confidence="MEDIUM",
                           limitations="the backup location was not searched"),
            ],
            impact=[
                R.Impact(id="im_0000000000001", target="reports/q3.md",
                         impact_class="FILES", relation="DIRECT",
                         classification="VERIFIED_FACT",
                         severity_contribution="MODERATE", confidence="MEDIUM",
                         reason="the file's content is replaced",
                         observable=True),
            ],
            risk=R.Risk(severity="MODERATE", confidence="MEDIUM",
                        reversibility="DIFFICULT",
                        reason="the previous content cannot be recovered "
                               "without a backup",
                        escalation_rule="E-NONE",
                        requires_human_approval=False, dimension_caveats=[]),
            alternatives=[
                R.Alternative(id="alt_0000000000001",
                              description="write to reports/q3-new.md instead",
                              expected_benefit="the old report is kept",
                              impact_reduction="nothing is overwritten",
                              tradeoffs="two files to reconcile",
                              residual_uncertainty="low", recommended=True),
            ],
            unknowns=[
                R.Unknown(id="unk_0000000000001",
                          question="is the report already backed up?",
                          why_it_matters="a backup would make this reversible",
                          evidence_that_would_resolve="the backup directory"),
            ],
        )
        lifecycle.record_forecast(forecast)
        lifecycle.seal_forecast(forecast.id)
        _show("summary", forecast.summary)
        _show("confidence", forecast.confidence_overall)
        _show("severity", forecast.risk.severity)
        _show("reversibility", forecast.risk.reversibility)
        print("  evidence:")
        for item in forecast.evidence:
            print("    [%-14s] %s" % (item.classification, item.claim))
        print("  alternatives:")
        for item in forecast.alternatives:
            print("    %s - %s" % (
                "recommended" if item.recommended else "available", item.description
            ))
        print("  unknown:")
        for item in forecast.unknowns:
            print("    %s" % item.question)

        # ---- 3. the decision ------------------------------------------
        _heading("3. WHAT WAS DECIDED")
        decision = R.ProductDecision(
            id="pdec_00000000001", forecast_id=forecast.id,
            proposal_id=proposal.id, proposal_version=1, state="ACCEPTED",
            decided_by="user", decided_at=TS, surface="desktop",
        )
        lifecycle.record_decision(decision)
        _show("state", decision.state)
        _show("decided by", decision.decided_by)
        _show("surface", decision.surface)

        # ---- 4. the authorization -------------------------------------
        _heading("4. WHO AUTHORIZED IT")
        authorization = R.HostAuthorization(
            id="auth_000000000001", forecast_id=forecast.id,
            proposal_id=proposal.id, proposal_version=1, state="PENDING",
            provenance="HOST_APPROVAL_HOOK", authorized_by="NONE",
            observed_choice="", observed_via="hook", reason="UNKNOWN",
            created_at=TS, escalation_expected=True, tool_call_id="tc_demo",
            rule_key="cm:%s:E-NONE" % forecast.id,
            pattern_key="plugin_rule:cm:%s:E-NONE" % forecast.id,
        )
        lifecycle.record_authorization(authorization)
        _show("state (pending)", authorization.state)
        _show("escalation expected", authorization.escalation_expected)
        _show("rule key", authorization.rule_key)
        print("  the product decision and the host authorization are two")
        print("  records. They are correlated for display and never merged.")

        # ---- 5. the execution -----------------------------------------
        _heading("5. WHAT ACTUALLY HAPPENED")
        execution = R.Execution(
            id="exe_000000000001", forecast_id=forecast.id, started_at=TS,
            status="COMPLETED", source="hook", ended_at=TS,
            product_decision_id=decision.id,
            host_authorization_id=authorization.id,
            trigger_tool="write_file", tool_call_id="tc_demo",
        )
        lifecycle.record_execution(execution)
        _show("status", execution.status)
        _show("source", execution.source)
        _show("trigger", execution.trigger_tool)

        # ---- 6. the outcome -------------------------------------------
        _heading("6. THE OUTCOME, AND THE COMPARISON")
        outcome = R.Outcome(
            id="out_000000000001", forecast_id=forecast.id,
            execution_id=execution.id, recorded_at=TS, recorded_by="plugin",
            verification_method="FILE_DIFF",
            summary="the report was overwritten and the previous content "
                    "was not recoverable",
            observations=[
                R.OutcomeObservation(
                    id="ob_000000000001", target="reports/q3.md",
                    observation="the file exists with the new content",
                    label="OBSERVED", evidence_source_kind="FILESYSTEM",
                    evidence_ref="digest:demo", confidence="HIGH"),
                R.OutcomeObservation(
                    id="ob_000000000002", target="the previous content",
                    observation="no copy of the previous content was found",
                    label="OBSERVED", evidence_source_kind="FILESYSTEM",
                    evidence_ref="digest:demo", confidence="HIGH"),
            ],
        )
        lifecycle.record_outcome(outcome)
        _show("verification", outcome.verification_method)
        _show("summary", outcome.summary)

        comparison = lifecycle.compare(
            forecast=forecast, outcome=outcome,
            comparison_id="cmp_000000000001", created_at=TS)
        _show("VERDICT", comparison.verdict)
        _show("note", comparison.accuracy_note)
        print("  dimension by dimension:")
        for item in comparison.items:
            print("    [%-12s] %s" % (item.label, item.note))

        # ---- 7. what remains unknown ---------------------------------
        _heading("7. WHAT REMAINS UNKNOWN")
        print("  The forecast asked whether the report was backed up.")
        print("  The comparison says the outcome was observed, but that")
        print("  question was not part of the observation, so it stays")
        print("  unknown. The product says so rather than implying it")
        print("  was answered.")

        # ---- 8. the immutability --------------------------------------
        _heading("8. THE FORECAST DID NOT CHANGE")
        before = repository.read_all_rows("forecast")[0]
        try:
            forecast.summary = "the quarterly report is safely backed up"
            lifecycle.record_forecast(forecast)
            print("  ERROR: the sealed forecast was modified")
            return 1
        except Exception as exc:
            after = repository.read_all_rows("forecast")[0]
            print("  a second write was refused: %s" % type(exc).__name__)
            print("  the stored forecast is unchanged: %s" % (before == after))
        print("  the comparison lives beside the forecast, not inside it.")

        _heading("WHAT THIS DEMONSTRATION IS")
        print("  REAL: the domain model, the storage layer, the schema, the")
        print("  triggers, the immutability rule, and the whole lifecycle")
        print("  from proposal to comparison, against a real database.")
        print("  NOT EXERCISED HERE: the Hermes host integration. The five")
        print("  hooks, the command palette and the three Desktop surfaces")
        print("  are covered by the test suite, not by this script.")
        print()
        return 0
    finally:
        connection.close()
        shutil.rmtree(directory, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
