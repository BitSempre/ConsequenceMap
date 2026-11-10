"""Envelope, timestamp and cap validation (AC-DATA-01, AC-DATA-02, AC-PRIV-19)."""
from __future__ import annotations

import unittest

from ..domain import validation as V


class TestEnvelope(unittest.TestCase):
    def test_AC_DATA_01_a_valid_envelope_is_accepted(self):
        env = {"schema_version": 1, "kind": "forecast", "id": "fc_1",
               "created_at": V.now_timestamp(), "data": {}}
        self.assertIs(V.validate_envelope(env), env)

    def test_AC_DATA_01_an_unknown_major_version_is_rejected(self):
        with self.assertRaises(V.ValidationError):
            V.validate_envelope({"schema_version": 2})

    def test_AC_DATA_01_a_missing_schema_version_is_rejected(self):
        with self.assertRaises(V.ValidationError):
            V.validate_envelope({"kind": "forecast"})

    def test_AC_DATA_01_a_non_integer_schema_version_is_rejected(self):
        with self.assertRaises(V.ValidationError):
            V.validate_envelope({"schema_version": "1"})

    def test_AC_DATA_01_a_boolean_schema_version_is_rejected(self):
        # bool is an int subclass; True must not be read as version 1.
        with self.assertRaises(V.ValidationError):
            V.validate_envelope({"schema_version": True})

    def test_AC_DATA_01_unknown_minor_fields_are_ignored(self):
        env = {"schema_version": 1, "unknown_minor_field": "x"}
        self.assertIs(V.validate_envelope(env), env)

    def test_AC_DATA_01_a_non_mapping_is_rejected(self):
        with self.assertRaises(V.ValidationError):
            V.validate_envelope(["schema_version", 1])


class TestTimestamp(unittest.TestCase):
    def test_AC_DATA_02_a_valid_timestamp_is_accepted(self):
        self.assertEqual(
            V.validate_timestamp("2026-11-07T16:42:11.905Z"), "2026-11-07T16:42:11.905Z"
        )

    def test_AC_DATA_02_a_timestamp_without_milliseconds_is_rejected(self):
        with self.assertRaises(V.TimestampError):
            V.validate_timestamp("2026-11-07T16:42:11Z")

    def test_AC_DATA_02_a_timestamp_with_an_offset_is_rejected(self):
        with self.assertRaises(V.TimestampError):
            V.validate_timestamp("2026-11-07T16:42:11.905+00:00")

    def test_AC_DATA_02_a_non_utc_timestamp_is_rejected(self):
        with self.assertRaises(V.TimestampError):
            V.validate_timestamp("2026-11-07T16:42:11.905")

    def test_AC_DATA_02_an_impossible_calendar_date_is_rejected(self):
        with self.assertRaises(V.TimestampError):
            V.validate_timestamp("2026-02-31T00:00:00.000Z")

    def test_AC_DATA_02_a_lowercase_z_is_rejected(self):
        with self.assertRaises(V.TimestampError):
            V.validate_timestamp("2026-11-07T16:42:11.905z")

    def test_AC_DATA_02_a_non_string_is_rejected(self):
        with self.assertRaises(V.TimestampError):
            V.validate_timestamp(20261107)

    def test_now_timestamp_has_millisecond_precision(self):
        self.assertRegex(V.now_timestamp(), r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")


class TestCaps(unittest.TestCase):
    def test_a_short_value_is_unchanged_and_not_truncated(self):
        text, truncated = V.cap_text("short", 100)
        self.assertEqual(text, "short")
        self.assertFalse(truncated)

    def test_an_over_long_value_is_truncated_at_the_cap(self):
        text, truncated = V.cap_text("x" * 500, 100)
        self.assertEqual(len(text), 100)
        self.assertTrue(truncated)

    def test_the_truncation_marker_is_present(self):
        text, _ = V.cap_text("x" * 500, 100)
        self.assertTrue(text.endswith(V.TRUNCATION_MARKER))

    def test_the_documented_caps_are_applied(self):
        for field, cap in (("proposal.action", 400), ("forecast.summary", 400),
                           ("evidence.claim", 500), ("comparison.accuracy_note", 1000)):
            with self.subTest(field=field):
                text, truncated = V.validate_cap("y" * (cap + 10), field)
                self.assertEqual(len(text), cap)
                self.assertTrue(truncated)

    def test_an_undocumented_field_is_an_error(self):
        with self.assertRaises(V.CapError):
            V.validate_cap("x", "not.a.field")


class TestClosedSetHelper(unittest.TestCase):
    def test_a_member_is_accepted(self):
        self.assertEqual(V.validate_closed_set("a", ("a", "b"), "f"), "a")

    def test_a_non_member_is_rejected(self):
        with self.assertRaises(V.ValidationError):
            V.validate_closed_set("c", ("a", "b"), "f")


if __name__ == "__main__":
    unittest.main()
