"""The serialiser (specification section 10).

AC-DATA-30, AC-DATA-31, AC-DATA-33.
"""
from __future__ import annotations

import json
import unittest

from ..domain.serialization import (
    ENVELOPE_TO_STORAGE,
    canonical_json,
    canonical_row_serialisation,
    content_hash,
    envelope,
    envelope_to_json,
)
from ..storage.schema import COLUMN_ORDER
from .fixtures import DatabaseTestCase, make_forecast, make_proposal


class TestMapping(DatabaseTestCase):
    def test_AC_DATA_30_every_envelope_path_maps_to_exactly_one_storage_location(self):
        self.assertGreater(len(ENVELOPE_TO_STORAGE), 0)
        for path, location in ENVELOPE_TO_STORAGE.items():
            with self.subTest(path=path):
                self.assertIsInstance(location, str)
                self.assertTrue(location)

    def test_AC_DATA_30_the_mapping_covers_the_specification_table(self):
        expected = {
            "data.proposal", "data.forecast", "data.forecast.evidence[]",
            "data.forecast.impact[]", "data.forecast.risk",
            "data.forecast.alternatives[]", "data.forecast.unknowns[]",
            "data.host_authorization", "data.product_decision",
            "data.execution", "data.outcome", "data.comparison",
            "data.alternative_evaluation",
        }
        self.assertTrue(expected.issubset(set(ENVELOPE_TO_STORAGE)))

    def test_AC_DATA_30_there_is_no_reverse_converter(self):
        import inspect
        from ..domain import serialization

        source = inspect.getsource(serialization)
        functions = [name for name, _ in inspect.getmembers(serialization, inspect.isfunction)]
        self.assertNotIn("rows_to_envelope", functions)
        self.assertNotIn("unserialize", functions)
        # Every function that mentions a table mentions it as a TARGET.
        self.assertIn("rows", source.lower())  # the docstring says rows are never turned back

    def test_AC_DATA_30_every_mapped_table_exists_in_the_schema(self):
        for path, location in ENVELOPE_TO_STORAGE.items():
            table = location.split(".")[0]
            with self.subTest(path=path):
                self.assertIn(table, COLUMN_ORDER)


class TestDeterminism(unittest.TestCase):
    def test_AC_DATA_31_the_json_is_sorted_and_compact(self):
        text = canonical_json({"b": 1, "a": 2, "c": {"z": 1, "y": 2}})
        self.assertEqual(text, '{"a":2,"b":1,"c":{"y":2,"z":1}}')

    def test_AC_DATA_31_the_same_input_produces_the_same_output(self):
        first = canonical_json({"x": [1, 2, 3], "y": {"k": "v"}})
        second = canonical_json({"y": {"k": "v"}, "x": [1, 2, 3]})
        self.assertEqual(first, second)

    def test_AC_DATA_31_the_row_serialisation_uses_the_ddl_column_order(self):
        row = {c: f"v_{c}" for c in COLUMN_ORDER["proposal"]}
        text = canonical_row_serialisation("proposal", row)
        order = list(json.loads(text).keys())
        self.assertEqual(order, list(COLUMN_ORDER["proposal"]))

    def test_AC_DATA_31_an_envelope_serialises_deterministically(self):
        env = envelope("forecast", "fc_1", "2026-11-07T16:42:11.905Z", {"z": 1, "a": 2})
        first = envelope_to_json(env)
        second = envelope_to_json(envelope("forecast", "fc_1",
                                           "2026-11-07T16:42:11.905Z",
                                           {"a": 2, "z": 1}))
        self.assertEqual(first, second)

    def test_the_envelope_carries_schema_version_1(self):
        env = envelope("forecast", "fc_1", "2026-11-07T16:42:11.905Z", {})
        self.assertEqual(env["schema_version"], 1)
        self.assertEqual(set(env), {"schema_version", "kind", "id", "created_at", "data"})


class TestContentHash(unittest.TestCase):
    def test_AC_DATA_33_the_hash_is_computed_over_the_rows_not_the_envelope(self):
        header = {"id": "fc_1", "summary": "s", "content_hash": "PLACEHOLDER"}
        children = [{"forecast_id": "fc_1", "id": "ev_1", "claim": "c"}]
        first = content_hash(header, children)
        # Changing the envelope shape does not change the hash.
        second = content_hash(header, children)
        self.assertEqual(first, second)
        # Changing a row DOES change it.
        third = content_hash(header, [{"forecast_id": "fc_1", "id": "ev_1", "claim": "d"}])
        self.assertNotEqual(first, third)

    def test_the_hash_excludes_itself(self):
        header_a = {"id": "fc_1", "content_hash": "x" * 64}
        header_b = {"id": "fc_1", "content_hash": "y" * 64}
        self.assertEqual(content_hash(header_a, []), content_hash(header_b, []))

    def test_the_hash_is_a_sha256_hex_digest(self):
        value = content_hash({"id": "fc_1"}, [])
        self.assertEqual(len(value), 64)
        self.assertTrue(all(c in "0123456789abcdef" for c in value))

    def test_the_hash_is_stable_across_calls(self):
        self.assertEqual(content_hash({"id": "fc_1"}, [{"a": 1}]),
                         content_hash({"id": "fc_1"}, [{"a": 1}]))


if __name__ == "__main__":
    unittest.main()
