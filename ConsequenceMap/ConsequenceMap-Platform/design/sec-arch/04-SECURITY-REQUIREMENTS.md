# Security Requirements

**Status:** DESIGN.

Every requirement is numbered, states what it demands, how it is
verified, and what its current state is. **A requirement whose test
does not exist is `NOT TESTED` — not passed.**

Status values: `IMPLEMENTED` (the code exists and the test passes) ·
`NOT IMPLEMENTED` (the design exists, the code does not) ·
`NOT TESTED` (no automated verification exists).

---

## 1. The adversarial scenarios

The mission brief defines twenty-four scenarios, T01–T24. This section
maps each to the requirement that answers it and to the test that
proves it.

| ID | Scenario | Requirement | Test | Status |
|---|---|---|---|---|
| **T01** | The agent alters the security policy | SR-11 | `test_guard.py::test_t01_a_non_canonicalisable_proposal_is_denied` | **NOT IMPLEMENTED** (needs the service) |
| **T02** | The agent alters the Guard's configuration | SR-11 | — | **NOT IMPLEMENTED** |
| **T03** | The agent grants itself privileges | SR-08 | `test_guard.py::test_t03_an_authorization_without_the_scope_is_denied` | **IMPLEMENTED** (protocol); enforcement needs the service |
| **T04** | The agent fabricates an authorization | SR-03 | `test_authorization.py::test_t04_a_forged_signature_is_rejected`, `::test_t04_a_forged_signature_from_a_different_key_is_rejected` | **IMPLEMENTED** (protocol) |
| **T05** | The agent reuses an earlier signature | SR-04 | `test_authorization.py::test_t05_a_replayed_authorization_against_a_new_request_is_rejected`, `::test_t05_a_replayed_authorization_over_the_same_proposal_is_rejected`, `test_regressions_round4.py::test_the_second_execution_is_refused`, `::test_a_shared_store_survives_two_engines` | **IMPLEMENTED** |
| **T06** | The proposal changes after approval | SR-03 | `test_authorization.py::test_t06_a_proposal_changed_after_approval_is_rejected`, `::test_t06_a_resource_added_after_approval_is_rejected`, `::test_t06_a_permission_widened_after_approval_is_rejected` | **IMPLEMENTED** |
| **T07** | The hash does not match the proposal | SR-03 | `test_authorization.py::test_t07_a_mismatched_proposal_hash_is_rejected` | **IMPLEMENTED** |
| **T08** | The authorization expired | SR-05 | `test_authorization.py::test_t08_an_expired_authorization_is_rejected`, `::test_t08_an_authorization_not_yet_valid_is_rejected` | **IMPLEMENTED** (logic); trusted clock **NOT IMPLEMENTED** |
| **T09** | The authorization was revoked | SR-06 | `test_authorization.py::test_t09_a_revoked_key_is_rejected`, `test_deployment.py` | **IMPLEMENTED** (check); the list's freshness is a limitation |
| **T10** | The phone is unavailable | — | — | **NOT IMPLEMENTED** — and it must fail **closed** (SR-07) |
| **T11** | The security service is unavailable | SR-07 | `test_deployment.py::test_t11_an_unreachable_guard_raises_rather_than_approving`, `::test_t11_a_guard_with_no_transport_raises`, `::test_t11_the_refusal_is_a_denial_with_a_reason` | **IMPLEMENTED** |
| **T12** | The cryptographic verification fails | SR-03 | `test_authorization.py::test_t04_a_forged_signature_is_rejected` | **IMPLEMENTED** (logic); a **real algorithm** is **NOT IMPLEMENTED** |
| **T13** | The agent executes outside the allowlist | SR-09 | `test_execution.py::test_t13_an_unregistered_operation_is_refused`, `::test_t13_no_operation_accepts_a_command_string`, `::test_t13_arguments_must_be_a_mapping` | **IMPLEMENTED** |
| **T14** | The agent bypasses the authorisation via `computer_use` | SR-01 | — | **NOT TESTABLE AUTOMATICALLY** — needs a running desktop and a human. Covered by design review and by SR-01's phone requirement |
| **T15** | The agent alters the audit records | SR-10 | `test_audit.py` (16 tests: altered payload, event, timestamp; removed, inserted, reordered) | **IMPLEMENTED** (detection); prevention needs the ACL (SR-12) |
| **T16** | The agent's account modifies protected files | SR-12 | — | **NOT IMPLEMENTED** (needs the service) |
| **T17** | The agent's account starts or modifies privileged services | SR-12 | — | **NOT IMPLEMENTED** (needs the service) |
| **T18** | The process is interrupted mid-operation | SR-09 | `test_audit.py::test_t19_an_empty_log_verifies` | **PARTIAL** — the state machine is durable in memory only; the database triggers cover the persisted records |
| **T19** | The machine restarts during a pending authorization | SR-05 | `test_audit.py::test_a_record_can_be_reconstructed_from_its_mapping` | **PARTIAL** — expiry survives; a pending *in-memory* request does not |
| **T20** | The user loses or replaces the phone | SR-13 | — | **NOT IMPLEMENTED** — specified in `../mobile-auth/05-RECOVERY-AND-DEVICE-REPLACEMENT.md` |
| **T21** | The same request is submitted simultaneously | SR-04 | — | **NOT IMPLEMENTED** — the nonce makes each request distinct, but concurrent submission needs a store-level test |
| **T22** | A module accepts an invalid state from another module | SR-09 | `test_execution.py::test_t22_an_undeclared_transition_is_refused`, `::test_t22_terminal_states_have_no_outgoing_transitions` | **IMPLEMENTED** |
| **T23** | The agent changes the operation after receiving a valid authorisation | SR-03 | `test_execution.py::test_t23_a_changed_proposal_is_refused`, `::test_t23_an_argument_outside_the_approved_operation_is_refused` | **IMPLEMENTED** |
| **T24** | The Guard receives incomplete or malformed data | SR-12 | `test_guard.py::test_t04_a_missing_authorization_is_denied`, `test_authorization.py::test_t22_a_missing_mandatory_field_is_rejected` | **IMPLEMENTED** |

---

## 2. The requirements

### SR-01 — Human presence must come from a device the agent cannot reach

No desktop dialog, no password prompt, no local confirmation. The
authorisation is produced by the author's phone, after biometric or PIN,
with a key that never leaves the phone's secure hardware.

*Verified by:* design review against the measured environment
(TPM 1.2, Hello not provisioned, `computer_use` present).
*Status:* **NOT IMPLEMENTED** — the protocol is; the phone is not.

### SR-02 — A consequence analysis is never an authorisation

The policy is not an input to the decision. The guard consults the
authorization, the scope, the allowlist and the proposal's integrity —
never the forecast's opinion.

*Verified by:* `core/guard.py` — no policy or forecast parameter exists
in `VerificationContext` beyond `policy_version`, which is recorded, not
consulted.
*Status:* **IMPLEMENTED**.

### SR-03 — Approval must be bound to the exact proposal

The guard **recomputes** the proposal's canonical hash and compares it
with the one the authorization names. A hash carried in a request is
never trusted.

*Verified by:* `test_authorization.py` T04, T06, T07, T23.
*Status:* **IMPLEMENTED**.

### SR-04 — Each request must be unique, and nonces must not repeat

Every request carries a fresh 256-bit nonce. The authorization must
carry the same nonce. A replay against a different request fails. A replay of the **same** authorization against the same request is refused by the executor's spent-authorization set: an approval is good for one execution, and the set must be durable and shared.

*Verified by:* `test_authorization.py` T05.
*Status:* **IMPLEMENTED**.

### SR-05 — Authorizations must expire

The current time must be inside `[valid_from, expires_at]`. The
authorization may not outlive the request it answers.

*Verified by:* `test_authorization.py` T08.
*Status:* **IMPLEMENTED** (logic). A **trusted clock** is
**NOT IMPLEMENTED**.

### SR-06 — Revocation must be checked at verification time

The revocation list is consulted on every verification, not cached.

*Verified by:* `test_authorization.py` T09.
*Status:* **IMPLEMENTED** (check). The list's own freshness is
**NOT SOLVABLE** here — no timestamping authority exists (RR-15).

### SR-07 — An unreachable guard must refuse

No fallback may approve. There is no cache of last-known-good
decisions, no in-process substitute, and no "assume the last answer".

*Verified by:* `test_deployment.py` T11.
*Status:* **IMPLEMENTED**.

### SR-08 — Separation of duties

The agent's account must not be able to write the guard's stores, and
the guard must not run as the agent's account.

*Verified by:* nothing — it is a property of the deployment.
*Status:* **NOT IMPLEMENTED**. UAC is explicitly **not** this boundary:
the agent can click an elevation prompt.

### SR-09 — Default deny, and no arbitrary execution

An operation not on the allowlist does not exist. No operation accepts a
command string. The state machine's terminal states have no outgoing
transitions.

*Verified by:* `test_execution.py` T13, T22; `test_guard.py`.
*Status:* **IMPLEMENTED**.

### SR-10 — Audit records must be tamper-evident

The audit trail is a hash chain. Every decision is recorded, including
the refusals.

*Verified by:* `test_audit.py` — 16 tests.
*Status:* **IMPLEMENTED** (detection). **The chain does not prevent a
wholesale rewrite** — prevention is SR-12.

### SR-11 — The policy must not be writable by the agent

*Status:* **NOT IMPLEMENTED** — needs the service.

### SR-12 — The stores must be protected by ACLs

The trust anchor, the policy, the approval store and the audit store
must be writable only by the guard's identity.

*Status:* **NOT IMPLEMENTED** — needs the service.

### SR-13 — Recovery must not be agent-triggerable

Losing the phone must be recoverable, and the recovery must not be an
act the agent can perform. A recovered device must not inherit the lost
device's authority.

*Status:* **NOT IMPLEMENTED** — specified in
`../mobile-auth/05-RECOVERY-AND-DEVICE-REPLACEMENT.md`. **The
mechanism for revoking a lost phone without the phone is an open
decision.**

### SR-14 — Claims must carry their class

`VERIFIED_FACT`, `INFERENCE`, `UNKNOWN`. A claim that could not be
confirmed is `NOT_VERIFIABLE`. A fact without a source is rejected. The
aggregated confidence is the weakest claim.

*Verified by:* `test_analysis.py` — 21 tests.
*Status:* **IMPLEMENTED**.

### SR-15 — The canonical form must be unambiguous

ASCII-only, length-prefixed, domain-separated. Duplicate keys, floats
and non-ASCII text are rejected.

*Verified by:* `test_authorization.py::CanonicalisationTests` — 13
tests.
*Status:* **IMPLEMENTED**.

### SR-16 — Fail closed on indeterminate

A condition that cannot be evaluated yields `INDETERMINATE`, which is
not an approval.

*Verified by:* `test_guard.py::IndeterminateTests`.
*Status:* **IMPLEMENTED**.

---

## 3. The summary

| | Count |
|---|---|
| Requirements total | 16 |
| **IMPLEMENTED** | **9** |
| **PARTIAL** | 2 (SR-05's trusted clock, SR-10's prevention) |
| **NOT IMPLEMENTED** | 5 (SR-01, SR-08, SR-11, SR-12, SR-13) |

**Every NOT IMPLEMENTED requirement depends on the Windows service or
the phone.** None of them depends on the protocol, which is done.

---

## 4. Acceptance criteria for a future implementation phase

The work is technically complete when:

1. Every requirement above is `IMPLEMENTED`, with its test passing.
2. The Windows service runs under a dedicated identity, with the stores
   under ACLs, and the agent's account cannot write them.
3. The phone applications exist, on at least one Android and one iOS
   version, with the security level detected and shown to the user.
4. The PC verifies a **real** signature, with the algorithm decision
   recorded and the C-1 tension resolved by an explicit decision.
5. All twenty-four adversarial scenarios have been **executed** against
   the running system, with evidence — including T14, which needs a
   human in the loop.
6. No critical or high finding is open without a mitigation.

**Until then the classification is `NOT READY FOR PRODUCTION`.**
