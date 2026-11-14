"""Regression tests for the seventh round: the audit trail's own integrity.

The seventh round attacked the audit log and the analysis layer - the
two areas the earlier rounds had touched least.

One defect was found in the audit log:

D-19  an ``AuditRecord`` was a mutable object, and ``append`` returned
      the live internal object. Anyone holding that reference - or the
      log's own ``records`` view - could rewrite a record after the
      fact. The chain DID detect the rewrite, but detection is not
      prevention: an audit trail whose records can be rewritten is not
      an audit trail, it is a suggestion that something happened.

The fix makes a record immutable and its payload a deep, read-only
snapshot.

The analysis layer produced no defect. Its checks - the weakest-link
confidence aggregation, the closed classification vocabulary, the
refusal of an unverified claim - all held under probing.
"""
from __future__ import annotations

import unittest

from consequence_map.core.analysis import (
    QualificationError,
    aggregate_confidence,
    classify_claim,
    comparison_verdict,
    qualify_forecast,
)
from consequence_map.core.audit import AuditLog, ChainBroken, verify_chain


class RecordImmutabilityTests(unittest.TestCase):
    """A written record cannot be rewritten."""

    def setUp(self):
        self.log = AuditLog()
        self.record = self.log.append("execution.completed", {"path": "r.md"})

    def test_the_event_cannot_be_changed(self):
        with self.assertRaises(AttributeError):
            self.record.event = "execution.approved"

    def test_the_payload_cannot_be_changed(self):
        with self.assertRaises(AttributeError):
            self.record.payload = {"path": "secrets"}

    def test_the_hash_cannot_be_changed(self):
        with self.assertRaises(AttributeError):
            self.record.record_hash = "0" * 64

    def test_the_sequence_cannot_be_changed(self):
        with self.assertRaises(AttributeError):
            self.record.sequence = 99

    def test_a_field_cannot_be_deleted(self):
        with self.assertRaises(AttributeError):
            del self.record.event

    def test_the_record_is_still_readable(self):
        self.assertEqual(self.record.event, "execution.completed")
        self.assertEqual(self.record.payload["path"], "r.md")
        self.assertEqual(self.record.sequence, 0)

    def test_the_chain_still_verifies(self):
        self.log.verify()


class PayloadSnapshotTests(unittest.TestCase):
    """The payload is a deep snapshot, not a reference."""

    def test_mutating_the_caller_dict_does_not_change_the_log(self):
        log = AuditLog()
        payload = {"nested": {"key": "original"}}
        log.append("event", payload)
        payload["nested"]["key"] = "changed"
        self.assertEqual(log.records[0].payload["nested"]["key"], "original")

    def test_a_nested_payload_cannot_be_mutated_through_the_record(self):
        log = AuditLog()
        log.append("event", {"nested": {"key": "original"}})
        with self.assertRaises(TypeError):
            log.records[0].payload["nested"]["key"] = "changed"

    def test_a_list_inside_the_payload_cannot_be_mutated(self):
        log = AuditLog()
        log.append("event", {"items": ["a", "b"]})
        with self.assertRaises(TypeError):
            log.records[0].payload["items"][0] = "changed"

    def test_the_chain_verifies_with_a_frozen_payload(self):
        log = AuditLog()
        log.append("a", {"x": {"y": [1, 2, 3]}})
        log.append("b", {"z": "text"})
        log.verify()


class AnalysisIntegrityTests(unittest.TestCase):
    """The analysis layer held under probing."""

    def test_an_unverified_claim_is_never_presented_as_a_fact(self):
        self.assertEqual(
            classify_claim("VERIFIED_FACT", verified=False), "NOT_VERIFIABLE"
        )

    def test_an_inference_is_downgraded_when_it_cannot_be_confirmed(self):
        self.assertEqual(
            classify_claim("INFERENCE", verified=False), "NOT_VERIFIABLE"
        )

    def test_the_aggregate_is_the_weakest_link(self):
        self.assertEqual(
            aggregate_confidence(["HIGH", "LOW", "MEDIUM"]), "LOW"
        )

    def test_an_empty_aggregate_is_none(self):
        self.assertEqual(aggregate_confidence([]), "NONE")

    def test_a_comparison_with_no_dimensions_is_not_evaluable(self):
        self.assertEqual(
            comparison_verdict(matched=0, total=0), "NOT_EVALUABLE"
        )

    def test_a_comparison_with_unknown_dimensions_is_partial(self):
        self.assertEqual(
            comparison_verdict(matched=3, total=3, unknown_dimensions=1),
            "PARTIAL",
        )

    def test_a_partial_match_is_partial_not_matched(self):
        self.assertEqual(comparison_verdict(matched=2, total=3), "PARTIAL")

    def test_a_full_match_is_matched(self):
        self.assertEqual(comparison_verdict(matched=3, total=3), "MATCHED")

    def test_an_unknown_classification_is_refused(self):
        with self.assertRaises(QualificationError):
            classify_claim("PROBABLY_FINE")

    def test_a_forecast_without_unknowns_does_not_qualify(self):
        from consequence_map.core.analysis import ForecastNotQualified
        with self.assertRaises(ForecastNotQualified):
            qualify_forecast({
                "content_hash": "a" * 64,
                "summary": "s",
                "confidence_overall": "HIGH",
                "evidence": [],
                "unknowns": [],
                "risk": {},
            })


if __name__ == "__main__":
    unittest.main()
