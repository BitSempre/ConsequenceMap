"""Regression tests for the third round of adversarial probing.

Round three looked at the areas rounds one and two did not: the
canonical form's key handling, the analysis layer's vocabulary, and
the time parser.

Two defects were found:

- map KEYS were held to a different rule from map VALUES. A value had
  to be ASCII; a key did not. That broke the promise the canonical
  form makes about its own output, and it opened a normalisation trap:
  the same key written in composed or decomposed form is two different
  byte strings that display the same, so two logically identical
  documents could hash to two different values.

- ``qualify_forecast`` only tested the confidence against ``NONE``. Any
  other label, including one the platform has never heard of, passed
  through and would be shown to the human who is about to authorise
  the operation.
"""
from __future__ import annotations

import unittest

from consequence_map.core.analysis import ForecastNotQualified, qualify_forecast
from consequence_map.core.canonical import (
    CanonicalisationError,
    canonical_text,
    domain_hash,
)


class CanonicalKeyTests(unittest.TestCase):
    """A key is held to the same rule as a value."""

    def test_a_non_ascii_key_is_refused(self):
        with self.assertRaises(CanonicalisationError):
            canonical_text("d", {"\u00e9": "x"})

    def test_a_non_ascii_value_is_refused(self):
        with self.assertRaises(CanonicalisationError):
            canonical_text("d", {"k": "\u00e9"})

    def test_the_canonical_form_is_ascii(self):
        self.assertTrue(canonical_text("d", {"k": "v"}).isascii())

    def test_a_composed_and_a_decomposed_key_are_both_refused(self):
        # "e" followed by a combining acute accent, and the single
        # precomposed character. Different byte strings, same display.
        decomposed = "e\u0301"
        composed = "\u00e9"
        self.assertNotEqual(composed, decomposed)
        self.assertEqual(len(composed), 1)
        self.assertEqual(len(decomposed), 2)
        for key in (composed, decomposed):
            with self.assertRaises(CanonicalisationError):
                canonical_text("d", {key: "x"})

    def test_an_ascii_key_is_fine(self):
        self.assertEqual(canonical_text("d", {"k": "v"}), "d\nm:k=s:1:v")


class ForecastConfidenceTests(unittest.TestCase):
    """A confidence the platform does not define cannot be shown."""

    def _forecast(self, **overrides):
        base = dict(
            content_hash="a" * 64, summary="s", confidence_overall="HIGH",
            evidence=[], unknowns=[{"id": "u"}], risk={},
        )
        base.update(overrides)
        return base

    def test_an_unknown_confidence_does_not_qualify(self):
        with self.assertRaises(ForecastNotQualified):
            qualify_forecast(self._forecast(confidence_overall="NAO-EXISTE"))

    def test_a_missing_confidence_does_not_qualify(self):
        forecast = self._forecast()
        del forecast["confidence_overall"]
        with self.assertRaises(ForecastNotQualified):
            qualify_forecast(forecast)

    def test_a_known_confidence_qualifies(self):
        result = qualify_forecast(self._forecast())
        self.assertTrue(result["qualified"])
        self.assertEqual(result["confidence_overall"], "HIGH")


if __name__ == "__main__":
    unittest.main()
