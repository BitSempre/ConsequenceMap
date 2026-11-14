"""Tests for the Consequence Intelligence policy layer.

The rules under test are the ones that stop an agent's plausible-sounding
analysis from being treated as fact.
"""
from __future__ import annotations

import unittest

from consequence_map.core.analysis import (
    CLASS_INFERENCE,
    CLASS_NOT_VERIFIABLE,
    CLASS_UNKNOWN,
    CLASS_VERIFIED_FACT,
    CONFIDENCE_RANK,
    ForecastNotQualified,
    QualificationError,
    aggregate_confidence,
    classify_claim,
    confidence_rank,
    comparison_verdict,
    qualify_forecast,
)


def _forecast(**overrides):
    base = dict(
        content_hash="a" * 64,
        summary="Deleting the report removes two evidence files.",
        confidence_overall="MEDIUM",
        evidence=[
            {"id": "e1", "claim": "the file exists", "classification": "VERIFIED_FACT",
             "source_kind": "filesystem", "confidence": "HIGH"},
        ],
        impact=[],
        risk={"severity": "MEDIUM", "confidence": "MEDIUM", "reversibility": "LOW",
              "reason": "the content is gone", "requires_human_approval": True},
        alternatives=[],
        unknowns=[
            {"id": "u1", "question": "is the file referenced elsewhere?",
             "why_it_matters": "a stale reference would break a later run",
             "evidence_that_would_resolve": "a repository-wide grep"},
        ],
    )
    base.update(overrides)
    return base


class ClassificationTests(unittest.TestCase):
    def test_a_fact_with_a_source_stays_a_fact(self):
        self.assertEqual(
            classify_claim(CLASS_VERIFIED_FACT, source_kind="filesystem"),
            CLASS_VERIFIED_FACT,
        )

    def test_a_fact_without_a_source_is_rejected(self):
        with self.assertRaises(QualificationError):
            classify_claim(CLASS_VERIFIED_FACT)

    def test_an_unverified_claim_is_downgraded(self):
        self.assertEqual(
            classify_claim(CLASS_VERIFIED_FACT, source_kind="filesystem", verified=False),
            CLASS_NOT_VERIFIABLE,
        )
        self.assertEqual(
            classify_claim(CLASS_INFERENCE, verified=False),
            CLASS_NOT_VERIFIABLE,
        )

    def test_an_unknown_stays_unknown(self):
        self.assertEqual(
            classify_claim(CLASS_UNKNOWN, verified=False), CLASS_UNKNOWN
        )

    def test_an_unknown_classification_is_rejected(self):
        with self.assertRaises(QualificationError):
            classify_claim("PROBABLY_FINE")


class ConfidenceTests(unittest.TestCase):
    def test_the_aggregate_is_the_weakest_claim(self):
        self.assertEqual(
            aggregate_confidence(["HIGH", "HIGH", "LOW"]), "LOW"
        )

    def test_an_empty_set_has_no_confidence(self):
        self.assertEqual(aggregate_confidence([]), "NONE")

    def test_an_unrecognised_level_ranks_lowest(self):
        self.assertEqual(confidence_rank("VERY_HIGH"), -1)


class ComparisonTests(unittest.TestCase):
    def test_a_full_match_is_matched(self):
        self.assertEqual(comparison_verdict(matched=5, total=5), "MATCHED")

    def test_a_partial_match_is_partial_not_matched(self):
        self.assertEqual(comparison_verdict(matched=3, total=5), "PARTIAL")

    def test_no_match_is_contradicted(self):
        self.assertEqual(comparison_verdict(matched=0, total=5), "CONTRADICTED")

    def test_an_unknown_dimension_makes_it_partial(self):
        self.assertEqual(
            comparison_verdict(matched=5, total=5, unknown_dimensions=1), "PARTIAL"
        )

    def test_nothing_to_compare_is_not_evaluable(self):
        self.assertEqual(comparison_verdict(matched=0, total=0), "NOT_EVALUABLE")


class QualificationTests(unittest.TestCase):
    def test_a_complete_forecast_qualifies(self):
        result = qualify_forecast(_forecast())
        self.assertTrue(result["qualified"])
        self.assertEqual(result["unknown_count"], 1)

    def test_an_unsealed_forecast_does_not_qualify(self):
        with self.assertRaises(ForecastNotQualified) as caught:
            qualify_forecast(_forecast(content_hash=""))
        self.assertIn("not sealed", str(caught.exception))

    def test_a_forecast_without_unknowns_does_not_qualify(self):
        with self.assertRaises(ForecastNotQualified) as caught:
            qualify_forecast(_forecast(unknowns=[]))
        self.assertIn("records no unknowns", str(caught.exception))

    def test_a_fact_without_a_source_does_not_qualify(self):
        forecast = _forecast(evidence=[
            {"id": "e1", "claim": "the file exists", "classification": "VERIFIED_FACT",
             "confidence": "HIGH"},
        ])
        with self.assertRaises(ForecastNotQualified) as caught:
            qualify_forecast(forecast)
        self.assertIn("without a source", str(caught.exception))

    def test_an_unknown_classification_does_not_qualify(self):
        forecast = _forecast(evidence=[
            {"id": "e1", "claim": "x", "classification": "PROBABLY",
             "source_kind": "fs", "confidence": "HIGH"},
        ])
        with self.assertRaises(ForecastNotQualified) as caught:
            qualify_forecast(forecast)
        self.assertIn("unknown classification", str(caught.exception))

    def test_a_forecast_without_confidence_does_not_qualify(self):
        with self.assertRaises(ForecastNotQualified) as caught:
            qualify_forecast(_forecast(confidence_overall=None))
        self.assertIn("no overall confidence", str(caught.exception))

    def test_approval_with_no_confidence_does_not_qualify(self):
        with self.assertRaises(ForecastNotQualified) as caught:
            qualify_forecast(_forecast(confidence_overall="NONE"))
        self.assertIn("states no confidence", str(caught.exception))

    def test_the_refusal_names_every_problem(self):
        forecast = _forecast(content_hash="", unknowns=[], confidence_overall=None)
        with self.assertRaises(ForecastNotQualified) as caught:
            qualify_forecast(forecast)
        message = str(caught.exception)
        self.assertIn("not sealed", message)
        self.assertIn("records no unknowns", message)
        self.assertIn("no overall confidence", message)


if __name__ == "__main__":
    unittest.main()
