# Production readiness — ConsequenceMap Security Platform v1

**Classification: `NOT READY`**

Not because the implementation is weak. Because **the trust boundary
that the whole design rests on has not been installed on this host**,
and a platform whose central claim is "the agent cannot authorise
itself" cannot claim that while the boundary is a document.

The mission's own rule: *"If a trust boundary, protected persistence,
service identity, cryptographic verification or safe recovery is
missing, the classification stays below production."* Four of those
five are present in code; the **first two need a deployment** that the
mission forbids executing.

---

## A. What was built

| Component | Lines | What it is |
|---|---|---|
| `consequence_map/core/` | 2 903 | The plugin: canonical form, the authorization protocol, the executor, the in-memory guard, the audit trail, the agent surface, the analysis layer |
| `consequence_guard/` | 2 607 | The service: Ed25519 crypto, the protocol, the policy, the authority, the durable store, the transport, the plugin client, revocation, crash recovery |
| Tests | 1 997 | 571 tests: 449 plugin, 108 guard, plus 10 mobile-protocol |
| Design | 8 new + 15 existing | The architecture, boundaries, threat model, protocol, audit, persistence, pairing, Red Team report, and the ADRs |

**31 commits** on `feature/platform-v1`. The production tree was
never touched.

### The architecture, in one sentence

`consequence_map` (the plugin, **stdlib-only**, runs where the agent
runs) may **propose**; `consequence_guard` (the service, separate
process, own identity, protected storage, uses `cryptography`) **decides
and executes**. The plugin cannot verify a signature at all, so there
is no path by which it can be talked into accepting a forged approval.

---

## B. What was demonstrated

| Property | Evidence |
|---|---|
| The agent cannot authorise itself | 8 tests: forged signature, unknown key, a request carrying its own `decision`/`allowed`, an operation outside the allowlist, a tampered proposal — **each asserts the handler was NOT called** |
| The plugin cannot bypass the guard | The request schema has no field for a decision, an approved scope, a command, a handler name or an argument |
| The approval is bound to the operation | `test_binding.py` — an approval for `file.delete` is refused for `repo.wipe` |
| The scope check is real | An approval granting `admin` when `files:write` was requested is refused |
| The signatures cover what was shown | The mobile prototype's display fields are **inside** the signed proposal; 10 protocol tests |
| A consumed authorisation cannot be reused | Durable spent set; **two real processes** race for one authorisation and exactly one wins |
| Two processes cannot execute the same authorisation | The same test |
| The audit survives a restart | Durable store; the chain and the checkpoints reopen intact |
| Tampering is detected | Immutable records, hash chain, checkpoints |
| A mandatory audit failure blocks execution | The store raises; the operation is refused |
| An interrupted operation is not falsely reported as completed | `OUTCOME_UNKNOWN`, never retried automatically |
| A lost device can be revoked without that device | A signed recovery grant, consumed atomically |
| Validity and clock skew are enforced by the service | `max_validity_seconds=600`, `clock_skew_seconds=30`, enforced at construction **and** re-checked at verification |
| The agent cannot run arbitrary commands | The handler's arguments are **derived** by the policy's argument map |
| The production tree is byte-identical | 96 files, 0 altered; the three protected files' SHA-256 unchanged |

**571 tests pass. The Guardian reports WARNING** (one pre-existing
error). The mobile prototype: 13/13, exit 0.

---

## C. What is still vulnerable

| # | Gap | Severity | Why it is not closed here |
|---|---|---|---|
| 1 | **The Windows service is not installed.** The identity, the ACLs, the pipe's client-token check are **designed and documented**, not deployed | **HIGH** | The mission forbids installing a service or altering production ACLs. The boundary is **specified, not demonstrated**. |
| 2 | **No hardware-backed recovery credential exists.** TPM 1.2, Hello not provisionable, no smart card, no FIDO2 | **HIGH** | The hardware does not exist on this host. The protocol is implemented; the credential's own security is the deployment's. |
| 3 | **The audit trail has no external anchor.** A chain rewritten consistently still verifies internally | Medium | The checkpoint mechanism exists; the anchor outside the agent's reach does not. |
| 4 | **The mobile applications do not exist.** The protocol and the reference implementation do | Medium | Building an Android and an iOS app with secure-hardware signing is beyond this environment. |
| 5 | **The handlers are untested against real side effects.** The test handlers are recorders | Medium | A handler that deletes three of four files before raising has not been exercised against a real filesystem. |
| 6 | **The startup integrity gate is not implemented** — the service should refuse to start if the chain does not verify against the last checkpoint | Medium | It needs the external anchor (gap 3). |

**Also accepted, and stated rather than hidden:**

- The phone is a single point of failure: whoever holds it holds a
  valid authority. That is why revocation exists.
- An administrator is above this design. The threat model is "a
  compromised agent", not "a compromised administrator".
- The service's private key never exists on the PC. A production
  deployment must provision it, and that is an operational decision.

---

## D. Integrity

| | |
|---|---|
| **Production original** | `C:\Users\Utente\Desktop\ConsequenceMap` — **96 files, 0 altered, 0 added, 0 removed**. `auto_repair: false`. The three protected files byte-identical. |
| **Development copy** | `C:\Users\Utente\Desktop\ConsequenceMap-Platform` — branch `feature/platform-v1`, **31 commits**, working tree clean |
| **Delivery** | `ConsequenceMap-Security-Platform-v1-20261109.zip` — 584 898 bytes, SHA-256 recorded in `SHA256SUMS.txt`, ZIP integrity verified, 218 entries |
| **Manifest** | `MANIFEST-SHA256.json` — 218 files, with a self-referencing fixed point |
| **Git history** | Verifiable in the delivery copy; no commits were made in the production tree, which has no `.git` |

---

## E. Decisions that still require the owner

These are real decisions, not technical questions I could resolve.

### E1 — Authorise the service installation *(blocks everything below staging)*

Creating `ConsequenceMapGuardSvc`, the directory tree, the ACLs and
the service registration requires **administrative rights** and
alters the machine's security configuration. The design is settled
(ADR-002); the installation is not authorised.

**Exact authorisation needed:** *"Authorise the installation of the
ConsequenceMap Security Guard service, its dedicated account and its
ACLs on this machine, for a controlled test."*

Without it, gaps 1 and 5 stay open and the platform cannot be
exercised against its own threat model.

### E2 — Choose the recovery credential *(blocks the device-loss story)*

The protocol works. The credential does not exist on this host. The
options, and what each needs:

| Option | Needs | Consequence for the user |
|---|---|---|
| A smart card | Hardware procurement | The user carries a second device |
| A FIDO2 key with the CTAP2 signing extension | Hardware procurement | The user carries a second device |
| A second device in escrow | A second phone | The user maintains two devices |
| A split recovery code (threshold shares) | Nothing | The user stores shares offline |

**Recommendation:** a split recovery code, because it needs no
procurement and works today. It is weaker than hardware, and the
weakness is recorded.

### E3 — Choose the external audit anchor

Where the checkpoint is written so the agent cannot reach it. A
write-once location, a separate machine, or a transparency log. This
needs a decision about what infrastructure is acceptable.

### E4 — The final validity window

600 seconds is a **technical default**, not a decision about the user's
risk. It is simultaneously the exposure window for a captured approval
and the time a human has to answer. It is one constant:
`MAX_VALIDITY_SECONDS`.

---

## F. Classification

## `NOT READY`

**Justification, against the mission's own criteria:**

| Criterion | Met? |
|---|---|
| 1. The agent cannot authorise itself | **Yes** — 8 tests, each asserting the handler did not run |
| 2. The plugin cannot bypass the guard | **Yes** — the schema has no field to bypass with |
| 3. The guard works with an independent identity | **No** — designed, not installed |
| 4. The agent cannot alter the protected policy | **Partly** — the code refuses; the ACL is not applied |
| 5. The signatures cover exactly what was shown | **Yes** — the display fields are inside the signed proposal |
| 6. A consumed authorisation cannot be reused after a restart | **Yes** — durable, verified |
| 7. Two concurrent processes cannot execute the same authorisation | **Yes** — two real processes, one winner |
| 8. The audit trail survives a restart | **Yes** — durable |
| 9. Tampering or truncation is detected | **Partly** — tampering yes; truncation needs the external anchor |
| 10. A mandatory audit failure prevents protected execution | **Yes** |
| 11. An interrupted operation is not falsely reported as completed | **Yes** — `OUTCOME_UNKNOWN` |
| 12. A lost device can be revoked without that device | **Yes** — the protocol; the credential is missing |
| 13. Validity and clock skew are enforced by the service | **Yes** |
| 14. The agent cannot run arbitrary commands through the service | **Yes** — the arguments are derived |
| 15. The production tree is byte-identical | **Yes** — 96 files, 0 altered |
| 16. No unresolved critical or high bypass from the Red Team | **Yes** — across eleven rounds: 39 defects found and fixed, and **eight** findings examined and rejected with the reasoning recorded |

**13 of 16 criteria are met. 3 are not, and each names a specific
missing thing: an installed service, an applied ACL, and an external
anchor.**

**The eleventh round.** Two further independent reviews ran — a
cryptography engineer and a Windows security engineer — and their
findings were checked against the code rather than accepted on
authority. Two were confirmed and fixed:

- **D-26**: the authorisation accepted an unknown field. The signed
  payload already made an added field break the signature, but a field
  the verifier ignores is authenticated-and-ignored — the exact
  pattern the platform refuses everywhere else. The authorisation now
  has a closed schema, like the IPC message already had.
- **D-27**: there was no RFC 8032 test vector. A suite that only
  checks "my signer agrees with my verifier" proves the two halves
  agree, not that either is Ed25519. The official RFC 8032 Section 7.1
  vectors now validate the implementation against an external
  reference.

Three findings were **rejected**, and the reasoning is recorded: the
interactive user must not be denied on the pipe (it would stop the
plugin from connecting); the nonce retention window must be at least
the maximum authorisation validity; and the stated transitive
dependencies (`six`, `importlib-metadata`) are not what
`cryptography` 50.0.1 actually requires.

Criterion 16 deserves a precise reading: the Red Team found no
unresolved critical or high bypass **in the logic that could be
reviewed without a deployment**. That is not the same as "there is no
bypass". The un-reviewed part is exactly the part that needs the
service installed.

**Why not `READY FOR CONTROLLED TESTING`:** that classification would
be appropriate the moment E1 is authorised. It is not appropriate now,
because a controlled test of the boundary **is** the installation.

---

## G. The next step

**One decision unblocks the rest: E1, the service installation.**

The sequence after it:

1. **Install the service** under `NT SERVICE\ConsequenceMapGuard` with
   the dedicated account and the ACLs from ADR-002.
2. **Run the three acceptance checks** as the interactive user:
   writing `policy.json` must fail with `ERROR_ACCESS_DENIED`;
   opening `guard.sqlite3` for writing must fail; connecting to the
   pipe must fail. **These three are the test that the boundary
   exists.**
3. **Exercise the real handlers** against disposable targets, including
   a handler that fails part-way — to observe `OUTCOME_UNKNOWN` in
   anger.
4. **Install the recovery credential** chosen in E2, and test the
   device-loss path end to end.
5. **Deploy the external anchor** (E3), and implement the startup
   integrity gate.
6. **Write the mobile applications** against the existing protocol.

After step 2, the classification becomes **`READY FOR CONTROLLED
TESTING`**. After steps 3–5, the remaining question is the validity
window (E4) and the operational readiness of the handlers.

**Until then, the honest statement is: the protocol is implemented and
attacked; the boundary is designed but not deployed; and the two gaps
that matter are a service install and a hardware credential.**
