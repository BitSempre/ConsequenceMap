# Test results

**Run date:** 2026-11-09
**Branch:** `feature/platform-v1`
**Head:** ab1413801518
**Commits:** 29

## Totals

| Suite | Tests | Result |
|---|---|---|
| `consequence_map/tests` (the plugin) | 449 | **PASS** |
| `consequence_guard/tests` (the service) | 105 | **PASS** |
| Mobile protocol regression tests | 10 | **PASS** |
| Mobile prototype demonstration | 13 cases | **PASS**, exit 0 |
| Quality Guardian | — | `WARNING` (one pre-existing error) |

**554 tests pass.** The baseline before this mission was 449
plugin tests; the mission added 105 service tests and 10 protocol
tests.

## The tests that matter most

These are not unit tests of helpers. Each one asserts a **security
property**, and each one asserts that the **handler did not run**.

| Test | Property |
|---|---|
| `test_a_request_with_a_forged_signature_is_refused` | A forged approval does not execute |
| `test_a_request_signed_by_an_unknown_key_is_refused` | An untrusted key does not execute |
| `test_a_request_that_carries_its_own_decision_is_refused` | The plugin cannot send a decision |
| `test_a_request_for_an_operation_outside_the_allowlist_is_refused` | Default deny |
| `test_the_handler_does_not_run_on_any_refusal` | Every refusal stops the effect |
| `test_an_approval_for_another_operation_is_refused` | The approval is bound to the operation |
| `test_an_approval_granting_more_than_requested_is_refused` | The scope check is real |
| `test_two_processes_race_for_one_authorization` | **Two real processes, one winner** |
| `test_a_consumption_survives_a_restart` | Single-use is durable |
| `test_a_replayed_request_is_refused_after_a_restart` | The nonce set is durable |
| `test_a_phone_behind_by_more_than_the_tolerance_is_refused` | The clock skew tolerance is bounded |
| `test_an_added_field_is_detected` | The field-adding attack fails |
| `test_a_revoked_key_is_refused` | Revocation works |
| `test_a_signature_for_a_revoked_recovery_key_is_refused` | The recovery key can be revoked |
| `test_an_operation_that_started_is_OUTCOME_UNKNOWN` | An interrupted operation is not falsely completed |
| `test_an_unavailable_store_refuses_the_operation` | Fail-closed |

## Adversarial history

| Round | Probes | Defects found | Theme |
|---|---|---|---|
| 1 | 11 | 4 | Scope typing, depth, coercion order, truncatable chain |
| 2 | 40 | 6 | Input validation at the edges |
| 3 | 25 | 2 | Canonical-form invariants, vocabulary enforcement |
| 4 | independent review | 2 | Single-use enforcement — a defect the design documented wrongly |
| 5 | 18 (prototype) | 2 | The displayed fields were outside the signature |
| 6 | 21 (agent boundary) | 2 | A contract whose fields could contradict each other; an unbounded validity window |
| 7 | 22 (audit + analysis) | 1 | The audit trail's records could be rewritten after the fact |
| 8 | independent review | 2 | The executor kept no audit trail; no clock-skew tolerance |
| 9 | Red Team | 3 | **The operation was not bound to the signature; the scope check was vacuous; the nonce set was not durable** |

**Thirty-four defects** across nine rounds, all fixed, all pinned by
regression tests.

## Environment

| | |
|---|---|
| OS | Windows 11 x64 |
| Python | 3.14.9 |
| `cryptography` | 50.0.1 (Apache-2.0 OR BSD-3-Clause) |
| PyNaCl | 1.6.2 (present, not used) |
| Interpreter for the suites | The Hermes venv that carries `cryptography`; the base interpreter is stdlib-only, which is why the plugin suite runs on it unchanged |
| TPM | 1.2 — Windows Hello **not** provisionable |
| Smart cards / FIDO2 | none |

## Reproducing

```
# plugin - the stdlib-only interpreter is enough
set PYTHONPATH=COPY\ConsequenceMap
python -m unittest discover -s consequence_map/tests -t .

# guard - needs the cryptography-capable interpreter
set PYTHONPATH=COPY\ConsequenceMap
python -m unittest discover -s consequence_guard/tests -t .

# mobile prototype
set PYTHONPATH=COPY\ConsequenceMap;COPY\design\mobile-auth\prototype
python COPY\design\mobile-auth\prototype\demo.py
```
