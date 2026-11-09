"""Shared fixtures: a temporary database and deterministic sample records.

No Hermes import. The connection provider is injected (MC1), and the
redactor is injected (PR-1).
"""
from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from typing import Any, Dict, List, Optional

from ..domain import records as R
from ..redaction import boundary
from ..storage import db as db_module
from ..storage.migrations import apply_migrations
from ..storage.repository import Repository

TS = "2026-11-07T16:42:11.905Z"


def deterministic_redactor(text: str) -> str:
    """The redactor used by the suite. Deterministic and Hermes-free."""
    return boundary.default_redactor(text)


def temp_provider(path: str) -> sqlite3.Connection:
    """A connection provider over a temporary file."""
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


class DatabaseTestCase(unittest.TestCase):
    """A test case with an isolated temporary database.

    The provider is injected, so the suite never needs Hermes on the
    path. The connection is closed and the directory removed on teardown.
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="cm-test-", ignore_cleanup_errors=True)
        self.db_path = os.path.join(self._tmp.name, "data.db")
        boundary.set_redactor(deterministic_redactor)
        self.conn = db_module.connect(self.db_path, provider=temp_provider)
        apply_migrations(self.conn)
        self.repo = Repository(self.conn)

    def tearDown(self) -> None:
        try:
            self.conn.close()
        finally:
            boundary.set_redactor(None)
            self._tmp.cleanup()

    # -- helpers ------------------------------------------------------
    def rows(self, table: str) -> List[Any]:
        return self.repo.read_all_rows(table)

    def count(self, table: str) -> int:
        return len(self.rows(table))


def make_proposal(**overrides: Any) -> R.Proposal:
    """A valid proposal (FILESYSTEM target, non-empty scope.excluded)."""
    proposal = R.Proposal(
        id="prop_aaaaaaaaaaaa",
        version=1,
        created_at=TS,
        actor="agent",
        action="write a report file",
        operation="FILE_WRITE",
        target_kind="FILESYSTEM",
        target={"paths": ["reports/daily.md"]},
        scope={"included": ["reports/"], "excluded": ["secrets/"]},
        preconditions=["workspace exists"],
        expected_outputs=["reports/daily.md"],
        external_side_effects=[],
        rollback="delete the file",
        session_id="sess_1",
        turn_id="turn_1",
        tool_call_id="tc_1",
    )
    for key, value in overrides.items():
        setattr(proposal, key, value)
    return proposal


def make_forecast(**overrides: Any) -> R.Forecast:
    """A valid forecast: LOW severity, one alternative, all collections present."""
    forecast = R.Forecast(
        id="fc_bbbbbbbbbbbb",
        proposal_id="prop_aaaaaaaaaaaa",
        proposal_version=1,
        created_at=TS,
        generator={"provider": "local", "model": "none", "purpose": "test",
                   "scanner_version": "1", "deterministic": True, "root": "C:\\root"},
        confidence_overall="LOW",
        summary="the file will be rewritten; confidence is low",
        content_hash="0" * 64,
        sealed_at=None,
        evidence=[
            R.Evidence(id="ev_111111111111", claim="the file exists",
                       classification="VERIFIED_FACT", source_kind="FILESYSTEM",
                       source_ref="reports/daily.md", observed_at=TS,
                       confidence="LOW", limitations="none"),
        ],
        impact=[
            R.Impact(id="im_222222222222", target="reports/daily.md",
                     impact_class="FILES", relation="DIRECT",
                     classification="VERIFIED_FACT", severity_contribution="LOW",
                     confidence="LOW", reason="the file is rewritten", observable=True),
        ],
        risk=R.Risk(severity="LOW", confidence="LOW", reversibility="EASY",
                    reason="the change is reversible", escalation_rule="E-NONE",
                    requires_human_approval=False, dimension_caveats=[]),
        alternatives=[
            R.Alternative(id="alt_333333333333", description="write to a new file",
                          expected_benefit="keeps the old content",
                          impact_reduction="no overwrite", tradeoffs="extra file",
                          residual_uncertainty="low", recommended=True),
        ],
        unknowns=[
            R.Unknown(id="unk_444444444444", question="will the disk fill?",
                      why_it_matters="the write could fail",
                      evidence_that_would_resolve="disk usage"),
        ],
    )
    for key, value in overrides.items():
        setattr(forecast, key, value)
    return forecast


def write_sealed_forecast(case: DatabaseTestCase, proposal: Optional[R.Proposal] = None,
                          forecast: Optional[R.Forecast] = None) -> R.Forecast:
    """Write a proposal and a SEALED forecast. Returns the forecast."""
    proposal = proposal if proposal is not None else make_proposal()
    forecast = forecast if forecast is not None else make_forecast()
    case.repo.write_proposal(proposal)
    case.repo.write_forecast(forecast)
    case.repo.seal_forecast(forecast.id)
    return forecast
