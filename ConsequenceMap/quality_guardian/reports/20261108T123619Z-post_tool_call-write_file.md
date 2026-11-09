# ConsequenceMap — Quality Guardian verification report

- **Generated:** 2026-11-08T12:36:19+00:00
- **Trigger:** post_tool_call:write_file
- **Verdict:** **FAIL**
- **Changed files:** 1
- **Tests executed:** 38
- **Repairs applied:** 1

## Changed files

- `probe_tmp.py`

## Checks

| Check | Verdict | Kind | Detail |
|---|---|---|---|
| hermes-runtime-compatibility | **PASS** | — | installed (0, 22, 5) vs required >=0.22.5 |
| production-stdlib-only | **PASS** | — | PRODUCTION_DEPENDENCIES is empty and no pyproject.toml exists |
| tests:test_static_audits | **PASS** | — | 9 test(s) passed |
| tests:test_import_audit | **PASS** | — | 10 test(s) passed |
| formatting-hygiene | **WARNING** | IMPLEMENTATION | 1 line(s) with trailing whitespace across 1 file(s) |
| repair:probe_tmp.py | **PASS** | — | the repair was applied and the tests still pass |
| phase-2a-manifest-integrity | **FAIL** | IMPLEMENTATION | 1 manifest entry/entries changed |
| tests-preserved | **PASS** | — | no test file was removed |
| state-comparison | **PASS** | — | 1 file(s) differ from the pre-cycle state |

## Test runs

| Module | Verdict | Passed | Failed | Errors | Duration |
|---|---|---|---|---|---|
| test_static_audits | **PASS** | 9 | 0 | 0 | 0.623s |
| test_import_audit | **PASS** | 10 | 0 | 0 | 0.57s |
| test_static_audits | **PASS** | 9 | 0 | 0 | 0.653s |
| test_import_audit | **PASS** | 10 | 0 | 0 | 0.632s |

## Repairs

| Path | Level | Kind | Applied | Description |
|---|---|---|---|---|
| `probe_tmp.py` | 1 | IMPLEMENTATION | yes | mechanical formatting: 1 line(s) with trailing whitespace, final-newline normalised |

## Unresolved issues

- **FAIL** — phase-2a-manifest-integrity: 1 manifest entry/entries changed

## Human decision required

_No — the cycle needed no human decision._
