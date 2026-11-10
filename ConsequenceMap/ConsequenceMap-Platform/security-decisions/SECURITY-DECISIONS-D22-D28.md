# Security decisions D-22 to D-28

One record per decision. Each states the decision, the reason, the
alternatives, and — importantly — **what remains open**. A decision
that is implemented is not the same as a decision that is complete.

Status vocabulary:

- **Implemented** — code exists and is tested.
- **Designed** — the design is settled and written; the code needs a
  deployment context this host does not have.
- **Open** — needs an owner's answer.

---

## D-22 — The identity of the Windows Security Guard

**Status: Designed.** ADR-002.

**Decision.** A Windows service under the virtual account
`NT SERVICE\ConsequenceMapGuard`, backed by a dedicated local account
`ConsequenceMapGuardSvc` with a random non-expiring password and
`Log on as a service` as its only privilege. The protected store lives
under `C:\ProgramData\ConsequenceMap\` with an ACL that denies the
interactive user write on the database, denies `FILE_DELETE_CHILD` on
the directory, and grants read-and-execute only on the binaries.

**Rejected.** LocalSystem (full machine authority), LocalService
(shared identity), NetworkService (unneeded network credential), and
an administrative account (would make the boundary meaningless).

**Open.** The service is **not installed** on this host. The ACLs, the
pipe's client-token check, and the unauthorised-access tests need a
real service install, which the mission forbids.

---

## D-23 — Cryptography and signatures

**Status: Implemented.** ADR-001.

**Decision.** Ed25519 via `cryptography==50.0.1` (Apache-2.0 OR
BSD-3-Clause). The signed payload is the canonical bytes of the
document with exactly the `signature` field removed. Algorithms are an
explicit allowlist; an unknown algorithm is refused outright.

**The dependency change, registered.** Constraint C-1 (stdlib-only)
is **kept for `consequence_map`** and relaxed only for
`consequence_guard`. The split is deliberate: the plugin the agent
controls cannot verify a real signature at all.

**Open.** Whether the target phone's secure hardware exposes Ed25519.
If not, a hardware-backed ECDSA P-256 key is the fallback and needs a
second ADR.

---

## D-24 — Revocation and recovery of a lost phone

**Status: Implemented** (protocol and enforcement). **Open** on the
credential.

**Decision.** A **recovery grant**: a document signed by a recovery key
that is not on the phone, authorising exactly one revocation of
exactly one device, with a validity window. The grant is consumed
**atomically** in the durable store, so it is good for one revocation
and a replayed grant is refused by the same mechanism that refuses a
replayed authorisation. Revocation is durable and audited. Re-pairing
requires a fresh grant.

**The agent cannot revoke.** There is no key the agent controls that
the service accepts as a recovery key, and no method that revokes
without a verified grant.

**Open.** This host has **no hardware-backed credential** to build on:
TPM 1.2, Hello not provisionable, no smart cards, no FIDO2. A real
deployment needs a credential the agent cannot reach — a smart card, a
FIDO2 key, or a second device held in escrow. The module implements
the protocol and the enforcement; the credential's own security is
whatever the deployment provides. **This is a genuine gap, not a
detail.**

---

## D-25 — Validity and clock skew

**Status: Implemented.**

**Decision.** Provisional defaults, configurable by the service:

| Parameter | Value | Meaning |
|---|---|---|
| `max_validity_seconds` | **600** | The longest an authorisation may stay open |
| `clock_skew_seconds` | **30** | The tolerated disagreement between the PC's and the phone's clocks |

The policy lives in the **service**, not in the plugin. It is enforced
**at construction and re-checked at verification**, so a document built
under a laxer policy is not honoured under a stricter one.

**The tolerance never creates an early authorisation.** It is applied
to the **expiry side only**. An authorisation that is not yet valid is
refused: a phone saying "this is good from later" is a clock problem,
not a reason to accept early.

**The agent cannot widen the window.** The policy is read by the
service from its own protected configuration.

**Open.** The values are technical defaults, not a guarantee. The
window is simultaneously the exposure window for a captured
authorisation and the time a human has to answer. An **abnormal clock
difference is recorded** — the audit records the observed skew when it
exceeds the tolerance.

---

## D-26 — Single-use and persistence

**Status: Implemented.**

**Decision.** The durable store (SQLite, WAL, `synchronous=FULL`)
holds the spent authorisations and the operation states. Consumption
is an `INSERT` inside an `BEGIN IMMEDIATE` transaction: **two processes
racing produce exactly one winner.** Verified by a test that spawns
two real processes.

The operation carries a **state**: `RECEIVED`, `VALIDATED`,
`CONSUMED`, `EXECUTION_STARTED`, `COMPLETED`, `FAILED`,
`OUTCOME_UNKNOWN`.

**Single-use is not exactly-once.** A handler may fail half-way
through, after it has already deleted three of four files. If the
process dies between `EXECUTION_STARTED` and `COMPLETED`, the effect
**may or may not have happened**, and the system says exactly that:
the state becomes `OUTCOME_UNKNOWN` and it is **never retried
automatically**. A human decides.

**Open.** The store is protected by its **filesystem ACL**, which is a
deployment property. The code guarantees atomicity, durability and
the refusal to continue when it cannot record; the ACL guarantees that
the agent cannot reach the file. Both are needed.

---

## D-27 — The audit trail

**Status: Implemented** (in memory and durably). **Open** on the
anchor.

**Decision.** The trail is append-only, hash-chained, sequentially
numbered, and records refusals, started operations, results and
failures. Records are **immutable** — read-only fields and a deep,
read-only payload snapshot — so the history cannot be rewritten in
place. The store keeps the chain and the checkpoints; a checkpoint
records the head at a moment the system knows to be correct.

**What each mechanism protects against**

| Mechanism | Adversary it stops |
|---|---|
| Hash chain | A record altered in place, a record removed from the middle, records reordered |
| Immutable records | The rewrite **after** the fact, before detection |
| Checkpoints | A chain rewritten **consistently** — it would verify internally, but not against the checkpoint |
| ACL on the store | The agent reaching the file at all |
| Durable storage | The trail surviving a restart |

**A hash chain alone does not prevent a full rewrite.** It detects
inconsistency. A chain that was rewritten consistently — with the
hashes recomputed — verifies perfectly. The defence against that is a
**checkpoint held outside the agent's reach**: an external anchor.
The code supports the checkpoint and the head anchor; **the external
anchor is not yet built**, because it needs a deployment context.

**Open.** The external anchor (a write-once location, a separate
machine, a transparency log) must be chosen and deployed.

---

## D-28 — Audit failure and fail-closed

**Status: Implemented.**

**Decision.** Every store operation raises `StoreUnavailable` on
failure. There is **no path that continues without the audit**. A
protected operation whose mandatory record cannot be guaranteed is
**refused**.

The distinction the mission asks for:

| When the failure happens | What the service does |
|---|---|
| **Before** execution | The operation is refused. Nothing ran. |
| **During** execution | The handler's exception is caught; the operation is recorded `FAILED`; the refusal is returned. |
| **After** execution, recording the result | The outcome **cannot** be recorded as `COMPLETED`. The state becomes `OUTCOME_UNKNOWN` and the effect is treated as possibly having happened. |
| The checkpoint fails | The operation continues — a checkpoint is a detection aid, not a precondition — and the failure is recorded. |

**Never is a result presented as `COMPLETED` without persisted
evidence.** The `COMPLETED` state is written in the same transaction
pattern that the audit append uses, and the state machine makes
`COMPLETED` reachable only from a successful handler return.

---

## Decisions that are not ours to make

These need the owner's answer and block the next phase:

1. **The service identity in practice** — a dedicated local account
   requires administrative rights to create. The *design* is settled;
   the *installation* needs an administrator.
2. **The recovery credential** — a smart card, a FIDO2 key, or an
   escrow device. None exists on this host.
3. **The external audit anchor** — where the checkpoint is written so
   the agent cannot reach it.
4. **The final validity window** — 600 s is a technical default, not
   a decision about the user's risk.
