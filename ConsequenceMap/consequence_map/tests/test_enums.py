"""The 18 closed enumerations (AC-DATA-03)."""
from __future__ import annotations

import unittest

from ..domain import enums


class TestEnumerationShape(unittest.TestCase):
    def test_there_are_exactly_18_enumerations(self):
        self.assertEqual(len(enums.ENUMS), 18)

    def test_there_are_13_shared_and_5_authorization(self):
        self.assertEqual(len(enums.SHARED_ENUM_NAMES), 13)
        self.assertEqual(len(enums.AUTHORIZATION_ENUM_NAMES), 5)

    def test_the_two_sets_partition_the_enumerations(self):
        combined = set(enums.SHARED_ENUM_NAMES) | set(enums.AUTHORIZATION_ENUM_NAMES)
        self.assertEqual(combined, set(enums.ENUMS))

    def test_every_enumeration_is_non_empty(self):
        for name, values in enums.ALL_VALUES.items():
            with self.subTest(enum=name):
                self.assertGreater(len(values), 0)


class TestClosedSet(unittest.TestCase):
    def test_AC_DATA_03_a_member_validates(self):
        self.assertEqual(
            enums.validate_enum("CONFIDENCE", "HIGH"), "HIGH"
        )

    def test_AC_DATA_03_an_unknown_value_is_an_error_not_a_default(self):
        with self.assertRaises(enums.EnumValidationError):
            enums.validate_enum("CONFIDENCE", "VERY_HIGH")

    def test_the_error_names_the_allowed_members(self):
        with self.assertRaises(enums.EnumValidationError) as ctx:
            enums.validate_enum("SEVERITY", "EXTREME")
        self.assertIn("MODERATE", str(ctx.exception))

    def test_validation_is_case_sensitive(self):
        with self.assertRaises(enums.EnumValidationError):
            enums.validate_enum("CONFIDENCE", "high")

    def test_is_valid_enum_reports_without_raising(self):
        self.assertTrue(enums.is_valid_enum("CONFIDENCE", "LOW"))
        self.assertFalse(enums.is_valid_enum("CONFIDENCE", "nope"))

    def test_the_authorization_state_has_13_members(self):
        self.assertEqual(len(enums.ALL_VALUES["AUTHORIZATION_STATE"]), 13)

    def test_the_authorization_state_contains_the_transport_failure_member(self):
        self.assertIn("TRANSPORT_FAILED", enums.ALL_VALUES["AUTHORIZATION_STATE"])

    def test_the_authorized_by_contains_the_guardian_member(self):
        self.assertIn("GUARDIAN_LLM", enums.ALL_VALUES["AUTHORIZED_BY"])

    def test_an_unknown_enumeration_name_is_an_error(self):
        with self.assertRaises(enums.EnumValidationError):
            enums.validate_enum("NO_SUCH_ENUM", "X")


if __name__ == "__main__":
    unittest.main()
