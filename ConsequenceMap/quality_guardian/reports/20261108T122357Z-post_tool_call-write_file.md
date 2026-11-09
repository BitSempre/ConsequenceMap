# ConsequenceMap — Quality Guardian verification report

- **Generated:** 2026-11-08T12:23:57+00:00
- **Trigger:** post_tool_call:write_file
- **Verdict:** **FAIL**
- **Changed files:** 1
- **Tests executed:** 72
- **Repairs applied:** 2

## Changed files

- `consequence_map/domain/copy.py`

## Checks

| Check | Verdict | Kind | Detail |
|---|---|---|---|
| hermes-runtime-compatibility | **PASS** | — | installed (0, 22, 5) vs required >=0.22.5 |
| production-stdlib-only | **PASS** | — | PRODUCTION_DEPENDENCIES is empty and no pyproject.toml exists |
| phase-2a-manifest-integrity | **FAIL** | IMPLEMENTATION | 1 manifest entry/entries changed |
| tests:test_static_audits | **PASS** | — | 9 test(s) passed |
| tests:test_import_audit | **PASS** | — | 10 test(s) passed |
| tests:test_coverage_gaps | **PASS** | — | 17 test(s) passed |
| formatting-hygiene | **WARNING** | IMPLEMENTATION | 0 line(s) with trailing whitespace across 1 file(s) |
| repair:consequence_map/domain/copy.py | **PASS** | — | the repair was applied and the tests still pass |
| tests-preserved | **PASS** | — | no test file was removed |
| state-comparison | **PASS** | — | 1 file(s) differ from the pre-cycle state |

## Test runs

| Module | Verdict | Passed | Failed | Errors | Duration |
|---|---|---|---|---|---|
| test_static_audits | **PASS** | 9 | 0 | 0 | 0.595s |
| test_import_audit | **PASS** | 10 | 0 | 0 | 0.554s |
| test_coverage_gaps | **PASS** | 17 | 0 | 0 | 0.557s |
| test_static_audits | **PASS** | 9 | 0 | 0 | 0.606s |
| test_import_audit | **PASS** | 10 | 0 | 0 | 0.565s |
| test_coverage_gaps | **PASS** | 17 | 0 | 0 | 0.544s |

## Repairs

| Path | Level | Kind | Applied | Description |
|---|---|---|---|---|
| `consequence_map/domain/copy.py` | 1 | IMPLEMENTATION | yes | mechanical formatting: 0 line(s) with trailing whitespace, final-newline normalised |
| `` | 1 | IMPLEMENTATION | no | 1 manifest entry/entries changed |

## Unresolved issues

- **FAIL** — phase-2a-manifest-integrity: 1 manifest entry/entries changed

## Human decision required

_No — the cycle needed no human decision._
