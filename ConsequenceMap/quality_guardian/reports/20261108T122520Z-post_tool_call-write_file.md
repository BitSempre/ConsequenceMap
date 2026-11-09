# ConsequenceMap — Quality Guardian verification report

- **Generated:** 2026-11-08T12:25:20+00:00
- **Trigger:** post_tool_call:write_file
- **Verdict:** **FAIL**
- **Changed files:** 1
- **Tests executed:** 36
- **Repairs applied:** 1

## Changed files

- `consequence_map/domain/copy.py`

## Checks

| Check | Verdict | Kind | Detail |
|---|---|---|---|
| hermes-runtime-compatibility | **PASS** | — | installed (0, 22, 5) vs required >=0.22.5 |
| production-stdlib-only | **PASS** | — | PRODUCTION_DEPENDENCIES is empty and no pyproject.toml exists |
| tests:test_static_audits | **PASS** | — | 9 test(s) passed |
| tests:test_import_audit | **PASS** | — | 10 test(s) passed |
| tests:test_coverage_gaps | **FAIL** | IMPLEMENTATION | 0 failure(s), 3 error(s) |
| formatting-hygiene | **PASS** | — | no trailing whitespace or final-newline defect in the changed files |
| phase-2a-manifest-integrity | **FAIL** | IMPLEMENTATION | 1 manifest entry/entries changed |
| tests-preserved | **PASS** | — | no test file was removed |
| state-comparison | **PASS** | — | 0 file(s) differ from the pre-cycle state |

## Test runs

| Module | Verdict | Passed | Failed | Errors | Duration |
|---|---|---|---|---|---|
| test_static_audits | **PASS** | 9 | 0 | 0 | 0.816s |
| test_import_audit | **PASS** | 10 | 0 | 0 | 0.591s |
| test_coverage_gaps | **FAIL** | 14 | 0 | 3 | 0.496s |

## Repairs

| Path | Level | Kind | Applied | Description |
|---|---|---|---|---|
| `` | 1 | IMPLEMENTATION | no | module test_coverage_gaps failed; no deterministic mechanical fix was identified — Level 2, requires an investigation |

## Unresolved issues

- **FAIL** — tests:test_coverage_gaps: 0 failure(s), 3 error(s)
- **FAIL** — phase-2a-manifest-integrity: 1 manifest entry/entries changed

## Human decision required

_No — the cycle needed no human decision._
