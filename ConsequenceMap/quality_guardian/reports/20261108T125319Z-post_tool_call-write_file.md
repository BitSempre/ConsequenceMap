# ConsequenceMap — Quality Guardian verification report

- **Generated:** 2026-11-08T12:53:19+00:00
- **Trigger:** post_tool_call:write_file
- **Verdict:** **NOT_VERIFIED**
- **Changed files:** 1
- **Tests executed:** 19
- **Repairs applied:** 1

## Changed files

- `qg_probe_ws.py`

## Checks

| Check | Verdict | Kind | Detail |
|---|---|---|---|
| hermes-runtime-compatibility | **PASS** | — | installed (0, 22, 5) vs required >=0.22.5 |
| production-stdlib-only | **PASS** | — | PRODUCTION_DEPENDENCIES is empty and no pyproject.toml exists |
| tests:test_static_audits | **PASS** | — | 9 test(s) passed |
| tests:test_import_audit | **PASS** | — | 10 test(s) passed |
| formatting-hygiene | **WARNING** | IMPLEMENTATION | 1 line(s) with trailing whitespace across 1 file(s) |
| repair-capability | **NOT_VERIFIED** | IMPLEMENTATION | automatic repair is suspended by the repair policy (post-incident security audit 2026-11-08: automatic repair suspended pending owner decision; detection, testing and reporting remain active); 1 repair(s) were proposed but not applied |
| phase-2a-manifest-integrity | **WARNING** | DOCUMENTATION | 1 manifest divergence(s), all documented in an addendum — a known, recorded state, not a new regression |
| tests-preserved | **PASS** | — | no test file was removed |
| state-comparison | **PASS** | — | 0 file(s) differ from the pre-cycle state |

## Test runs

| Module | Verdict | Passed | Failed | Errors | Duration |
|---|---|---|---|---|---|
| test_static_audits | **PASS** | 9 | 0 | 0 | 0.67s |
| test_import_audit | **PASS** | 10 | 0 | 0 | 0.61s |

## Repairs

| Path | Level | Kind | Applied | Description |
|---|---|---|---|---|
| `qg_probe_ws.py` | 1 | IMPLEMENTATION | no | mechanical formatting: 1 line(s) with trailing whitespace, final-newline normalised |

## Unresolved issues

- **NOT_VERIFIED** — repair-capability: automatic repair is suspended by the repair policy (post-incident security audit 2026-11-08: automatic repair suspended pending owner decision; detection, testing and reporting remain active); 1 repair(s) were proposed but not applied

## Human decision required

_No — the cycle needed no human decision._
