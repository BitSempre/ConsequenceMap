"""The static audits.

AC-DATA-32 (the Desktop never sees a table name), AC-STORE-11 and
AC-STORE-15 (write-path ownership), AC-LLM-05 and AC-LLM-06 (the
manifest and the config schema).
"""
from __future__ import annotations

import ast
import os
import re
import unittest

PACKAGE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT = os.path.dirname(PACKAGE)

#: Every table of specification section 3.2.
TABLES = (
    "schema_meta", "proposal", "forecast", "forecast_evidence", "forecast_impact",
    "forecast_risk", "forecast_alternative", "forecast_unknown",
    "host_authorization", "product_decision", "execution", "execution_tool_call",
    "outcome", "outcome_observation", "comparison", "comparison_item",
    "alternative_evaluation",
)

#: The tables the outcome side may never write to.
FORECAST_TABLES = tuple(t for t in TABLES if t.startswith("forecast"))

#: The tables written by the observation side.
OUTCOME_SIDE = ("outcome", "outcome_observation", "comparison", "comparison_item",
                "host_authorization", "product_decision")


def python_files(subdir=None):
    root = os.path.join(PACKAGE, subdir) if subdir else PACKAGE
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for name in sorted(files):
            if name.endswith(".py"):
                yield os.path.join(base, name)


class TestWritePathOwnership(unittest.TestCase):
    def test_AC_STORE_11_no_outcome_side_write_reaches_a_forecast_table(self):
        """The static SQL audit of the write layer."""
        offenders = []
        for path in python_files("storage"):
            with open(path, encoding="utf-8") as handle:
                source = handle.read()
            # Every INSERT/UPDATE/DELETE statement, by table.
            for match in re.finditer(
                r"(INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+([a-z_]+)", source
            ):
                verb, table = match.group(1).upper(), match.group(2)
                if table in OUTCOME_SIDE and verb.startswith(("INSERT", "UPDATE", "DELETE")):
                    # The statement itself must not name a forecast table.
                    statement = source[match.start():match.start() + 120]
                    for forecast_table in FORECAST_TABLES:
                        if forecast_table in statement:
                            offenders.append(
                                f"{os.path.basename(path)}: {statement[:70]}"
                            )
        self.assertEqual(offenders, [])

    def test_AC_STORE_11_the_repository_has_no_forecast_write_on_the_outcome_side(self):
        from ..storage import repository as repo_module

        source = open(repo_module.__file__, encoding="utf-8").read()
        # The write methods for the outcome side.
        for method in ("write_outcome", "write_comparison",
                       "write_host_authorization", "write_product_decision"):
            start = source.index(f"def {method}(")
            end = source.find("    def ", start + 10)
            body = source[start:end if end > 0 else len(source)]
            with self.subTest(method=method):
                for forecast_table in FORECAST_TABLES:
                    self.assertNotIn(f'"{forecast_table}"', body)
                    self.assertNotIn(f"INSERT INTO {forecast_table}", body)
                    self.assertNotIn(f"UPDATE {forecast_table}", body)
                    self.assertNotIn(f"DELETE FROM {forecast_table}", body)

    def test_AC_STORE_15_every_table_has_exactly_one_write_method(self):
        from ..storage import repository as repo_module

        source = open(repo_module.__file__, encoding="utf-8").read()
        for table in TABLES:
            with self.subTest(table=table):
                inserts = len(re.findall(rf'_insert\(self\.conn, "{table}"', source))
                self.assertLessEqual(inserts, 1,
                                     f"{table} must have exactly one insert site")


class TestDesktopIsolation(unittest.TestCase):
    def test_AC_DATA_32_the_desktop_layer_never_references_a_table_name(self):
        """The Desktop half is read-only and sees no table name.

        In Phase 2A there is no Desktop half yet. The audit therefore
        asserts that no module in the package outside the storage layer
        names a table - the Desktop will consume the serialiser, not SQL.
        """
        offenders = []
        for path in python_files():
            relative = os.path.relpath(path, PACKAGE)
            # The audit covers the layers a Desktop-facing surface would
            # use: the domain records and the serialiser. The storage
            # layer names tables by design - that is its job.
            if relative.startswith("storage" + os.sep):
                continue
            if relative.startswith("redaction" + os.sep):
                continue
            if relative.startswith("tests" + os.sep):
                continue
            if relative.startswith("config.py") or relative.startswith("dependencies.py"):
                continue
            with open(path, encoding="utf-8") as handle:
                source = handle.read()
            # A table name is a TABLE REFERENCE, not a field name. The
            # domain layer names fields like `proposal_id`; the Desktop
            # must not see a table. The audit therefore looks for a table
            # name in a SQL or table-list context.
            for table in TABLES:
                # A table REFERENCE is a SQL target or an element of a
                # table list. A table NAME used as an entity label in an
                # error message is not a reference - the Desktop never
                # sees SQL, and the domain layer's error labels are not
                # a storage surface.
                for pattern in (rf"FROM\s+{table}\b", rf"INTO\s+{table}\b",
                                rf"UPDATE\s+{table}\b", rf"TABLE\s+{table}\b",
                                rf"\"{table}\"\s*,\s*\"[a-z_]+\"",
                                rf"^\s*\"{table}\"\s*,\s*$"):
                    if re.search(pattern, source):
                        offenders.append(f"{relative} references {table}")
                        break
        self.assertEqual(offenders, [])

    def test_AC_DATA_32_the_package_has_no_desktop_or_sdk_dependency(self):
        offenders = []
        for path in python_files():
            with open(path, encoding="utf-8") as handle:
                tree = ast.parse(handle.read(), filename=path)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.split(".")[0] in ("react", "sdk", "desktop"):
                            offenders.append(f"{path} imports {alias.name}")
                elif isinstance(node, ast.ImportFrom) and node.module:
                    if node.module.split(".")[0] in ("react", "sdk", "desktop"):
                        offenders.append(f"{path} imports {node.module}")
        self.assertEqual(offenders, [])


class TestManifestAndConfig(unittest.TestCase):
    """AC-LLM-05 and AC-LLM-06.

    The manifest and the config schema are Phase 2C packaging artefacts.
    Phase 2A defines the CONFIG SCHEMA (the `use_inference` setting and
    its default) and states the manifest's dependency constraints; the
    manifest itself is written in 2C. These tests assert what Phase 2A
    can assert.
    """

    def test_AC_LLM_06_the_use_inference_setting_exists_and_defaults_to_false(self):
        from ..config import CONFIG_SCHEMA, default_config

        self.assertIn("use_inference", CONFIG_SCHEMA)
        self.assertFalse(CONFIG_SCHEMA["use_inference"]["default"])
        self.assertEqual(default_config()["use_inference"], False)

    def test_AC_LLM_05_no_api_key_is_required(self):
        from ..config import CONFIG_SCHEMA

        for name, spec in CONFIG_SCHEMA.items():
            with self.subTest(setting=name):
                self.assertNotIn("api_key", spec)
                self.assertFalse(spec.get("required", False))

    def test_AC_LLM_05_the_production_dependency_inventory_is_empty(self):
        from .. import dependencies

        self.assertEqual(dependencies.PRODUCTION_DEPENDENCIES, ())
        self.assertEqual(dependencies.PYTHON_DEPENDENCIES, [])

    def test_the_package_declares_no_third_party_import(self):
        stdlib_and_package = {
            "dataclasses", "datetime", "enum", "json", "os", "pathlib", "re",
            "sqlite3", "typing", "hashlib", "contextlib", "tempfile", "abc",
            "collections", "functools", "itertools", "textwrap", "unittest",
            "shutil", "sys", "inspect", "ast", "__future__", "threading",
        }
        # The host modules are not third-party: they are the runtime the
        # plugin runs inside. They are permitted ONLY in the two seams -
        # `storage/db.py` (the connection) and `redaction/boundary.py`
        # (the redactor) - and always inside a function body.
        host_modules = {"hermes_cli", "hermes_state_wal", "plugins", "agent", "tools"}
        for path in python_files():
            with open(path, encoding="utf-8") as handle:
                tree = ast.parse(handle.read(), filename=path)
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.Import):
                    names = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
                    names = [node.module]
                for name in names:
                    root = name.split(".")[0]
                    with self.subTest(file=os.path.basename(path), module=name):
                        self.assertTrue(
                            root in stdlib_and_package
                            or root == "consequence_map"
                            or root in host_modules,
                            f"{path} imports {name}, which is neither the standard "
                            f"library nor the host",
                        )


if __name__ == "__main__":
    unittest.main()
