"""Redaction and caps at the write boundary.

PR-1, PR-2 (AC-PRIV-01, AC-PRIV-02, AC-PRIV-03, AC-PRIV-05, AC-PRIV-19),
and the credential-file exclusion (AC-PRIV-22).
"""
from __future__ import annotations

import unittest

from ..redaction import boundary
from ..redaction.boundary import REDACTION_UNAVAILABLE, RedactionUnavailable
from .fixtures import DatabaseTestCase, make_forecast, make_proposal


class TestRedactionUnit(unittest.TestCase):
    def setUp(self):
        boundary.set_redactor(boundary.default_redactor)

    def tearDown(self):
        boundary.set_redactor(None)

    def test_a_secret_shaped_value_is_redacted(self):
        out = boundary.redact_for_storage("api_key=sk-abcdefghijklmnopqrstuvwxyz")
        self.assertNotIn("sk-abcdefghijklmnopqrstuvwxyz", out)

    def test_a_bearer_token_is_redacted(self):
        out = boundary.redact_for_storage("Authorization: Bearer abcdefghijklmnop")
        self.assertNotIn("abcdefghijklmnop", out)

    def test_a_private_key_is_redacted(self):
        out = boundary.redact_for_storage("-----BEGIN RSA PRIVATE KEY-----")
        self.assertNotIn("BEGIN RSA PRIVATE KEY", out)

    def test_an_ordinary_string_is_unchanged(self):
        self.assertEqual(boundary.redact_for_storage("reports/daily.md"),
                         "reports/daily.md")

    def test_PR1_a_raising_redactor_fails_closed(self):
        def broken(text):
            raise RuntimeError("redactor exploded")

        boundary.set_redactor(broken)
        with self.assertRaises(RedactionUnavailable) as ctx:
            boundary.redact_for_storage("some text", field="proposal.action")
        self.assertEqual(ctx.exception.code, REDACTION_UNAVAILABLE)

    def test_AC_PRIV_19_the_cap_is_applied_after_redaction(self):
        text, changed, truncated = boundary.redact_and_cap("x" * 600, "evidence.claim")
        self.assertEqual(len(text), 500)
        self.assertTrue(truncated)

    def test_the_truncation_is_reported(self):
        _text, _changed, truncated = boundary.redact_and_cap("short", "evidence.claim")
        self.assertFalse(truncated)


class TestRedactionAtTheWriteBoundary(DatabaseTestCase):
    def test_AC_PRIV_01_a_secret_in_a_free_text_field_never_reaches_the_database(self):
        proposal = make_proposal(action="write api_key=sk-abcdefghijklmnopqrstuvwxyz")
        self.repo.write_proposal(proposal)
        rows = self.rows("proposal")
        stored = " ".join(str(value) for value in rows[0])
        self.assertNotIn("sk-abcdefghijklmnopqrstuvwxyz", stored)

    def test_AC_PRIV_05_no_credential_is_persisted_in_any_field(self):
        proposal = make_proposal(action="token=ghp_abcdefghijklmnopqrstuvwxyz012345")
        forecast = make_forecast(summary="password: hunter2secretvalue")
        self.repo.write_proposal(proposal)
        self.repo.write_forecast(forecast)
        for table in ("proposal", "forecast", "forecast_evidence", "forecast_impact",
                      "forecast_risk", "forecast_alternative", "forecast_unknown"):
            with self.subTest(table=table):
                for row in self.rows(table):
                    blob = " ".join(str(value) for value in row)
                    self.assertNotIn("ghp_abcdefghijklmnopqrstuvwxyz012345", blob)
                    self.assertNotIn("hunter2secretvalue", blob)

    def test_AC_PRIV_02_a_raising_redactor_prevents_the_write(self):
        def broken(text):
            raise RuntimeError("redactor exploded")

        boundary.set_redactor(broken)
        try:
            with self.assertRaises(RedactionUnavailable):
                self.repo.write_proposal(make_proposal(action="api_key=sk-123"))
        finally:
            boundary.set_redactor(boundary.default_redactor)
        # The write did not happen: no proposal row exists.
        self.assertEqual(self.count("proposal"), 0)

    def test_AC_PRIV_19_an_over_long_field_is_truncated_with_the_marker(self):
        proposal = make_proposal(action="a" * 600)
        self.repo.write_proposal(proposal)
        stored = self.rows("proposal")[0][4]  # the `action` column
        self.assertEqual(len(stored), 400)
        self.assertTrue(stored.endswith("…[truncated]"))

    def test_AC_PRIV_19_the_cap_matrix_is_applied_per_field(self):
        forecast = make_forecast(summary="s" * 600)
        forecast.evidence[0].claim = "c" * 600
        forecast.evidence[0].source_ref = "r" * 400
        # The forecast references the proposal (composite FK), so the
        # parent must exist first.
        self.repo.write_proposal(make_proposal())
        self.repo.write_forecast(forecast)
        self.assertEqual(len(self.rows("forecast")[0][6]), 400)          # summary
        self.assertEqual(len(self.rows("forecast_evidence")[0][2]), 500)  # claim
        self.assertEqual(len(self.rows("forecast_evidence")[0][5]), 300)  # source_ref


class TestCredentialFileExclusion(unittest.TestCase):
    def test_AC_PRIV_22_the_package_never_reads_a_credential_file(self):
        """No module in the package opens a credential file."""
        import os
        import re

        package = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        offenders = []
        pattern = re.compile(r"\.aws|credentials|\.netrc|\.npmrc|id_rsa|\.pem",
                             re.IGNORECASE)
        for root, dirs, files in os.walk(package):
            dirs[:] = [d for d in dirs if d not in ("__pycache__",)]
            for name in files:
                if not name.endswith(".py"):
                    continue
                path = os.path.join(root, name)
                with open(path, encoding="utf-8") as handle:
                    for number, line in enumerate(handle, 1):
                        if "open(" in line and pattern.search(line):
                            offenders.append(f"{name}:{number}: {line.strip()}")
        self.assertEqual(offenders, [],
                         "the package must never open a credential file")

    def test_AC_PRIV_22_the_environment_is_never_read(self):
        import os
        import re

        package = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        offenders = []
        needles = ("os." + "environ", "get" + "env")
        for root, dirs, files in os.walk(package):
            dirs[:] = [d for d in dirs if d not in ("__pycache__",)]
            for name in files:
                if not name.endswith(".py"):
                    continue
                path = os.path.join(root, name)
                if os.path.abspath(path) == os.path.abspath(__file__):
                    # This test file names the needles it searches for.
                    continue
                with open(path, encoding="utf-8") as handle:
                    for number, line in enumerate(handle, 1):
                        if any(needle in line for needle in needles):
                            offenders.append(f"{name}:{number}: {line.strip()}")
        self.assertEqual(offenders, [], "the plugin never reads the environment")


if __name__ == "__main__":
    unittest.main()
