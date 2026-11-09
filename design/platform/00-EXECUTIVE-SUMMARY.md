# Executive summary — ConsequenceMap Security Platform v1

## The mission's central claim, and its status

> **Even if the agent controls the plugin, it cannot grant itself
> authorisation to execute a protected operation.**

**The code that makes this true is written, tested and attacked. The
boundary it depends on is designed but not deployed.**

That sentence is the honest summary, and the rest of this document is
its detail.

## What was built

A **Security Guard**: a privileged service, in its own process, with
its own identity and its own protected storage, that is the only
authority able to execute a protected operation.

The boundary is expressed in the **code structure**, not only in the
documents:

| | `consequence_map` — the plugin | `consequence_guard` — the service |
|---|---|---|
| Runs | where the agent runs | where the agent cannot |
| Dependencies | **stdlib only** | `cryptography` |
| Can verify a signature | **no** | yes |
| Decides | **no** | **yes** |
| Executes | **no** | **yes** |

The plugin's inability to verify a signature is not a limitation
imposed on it. **It is what makes it safe.** The code that would
accept a forged approval is in the other process, and the agent
cannot reach it.

- **557 tests pass** (449 plugin, 108 service, plus 10 mobile-protocol).
- **34 defects** found and fixed across nine adversarial rounds, three
  of them by independent reviewers.
- The production tree was **never touched**: 96 files, 0 altered.

## The three findings that mattered most

| | Defect | Why it mattered |
|---|---|---|
| **1** | The mobile prototype displayed fields that were **outside** the signed content | The human approves what they see, and what they saw was protected by nothing. An attacker could change the phone's screen without invalidating the approval. |
| **2** | The **operation was not bound to the signature** | Every individual check was correct — the hash, the scope, the window — and the thing the human actually approved was never among them. An approval for `file.delete` executed `repo.wipe`. |
| **3** | The executor had **no memory of what it had spent** | One approval, three executions. The design had documented this as an acceptable residual risk, and it was not. |

The third is the one worth remembering. The threat model said, in
writing, that a replayed authorisation within its validity window was
"accepted by design, because that is the same operation, approved once,
still valid". That was true of the **authorisation** and false of the
**execution**. *Reading your own design tells you what you intended; it
does not tell you what you built.*

## What is not done

| | Gap | Why |
|---|---|---|
| 1 | The Windows service is **not installed** — the identity, the ACLs and the pipe's client-token check are designed and documented | Installing a service or altering production ACLs is outside the mission's authorisation |
| 2 | **No hardware-backed recovery credential** — TPM 1.2, Hello not provisionable, no smart card, no FIDO2 | The hardware does not exist on this host |
| 3 | The audit trail has **no external anchor** | Needs a deployment decision |
| 4 | The **mobile applications do not exist** | The protocol and the reference implementation do |

Gaps 1 and 2 are the two that matter, and both are named rather than
implied.

## The decision that unblocks the rest

**Authorising the service installation** — one administrative action,
with the ACLs and the account already specified in ADR-002, and three
acceptance checks that prove the boundary exists:

1. writing `policy.json` as the interactive user must fail with
   `ERROR_ACCESS_DENIED`;
2. opening `guard.sqlite3` for writing must fail;
3. connecting to the pipe must fail.

After that, the classification becomes **`READY FOR CONTROLLED
TESTING`**.

## Classification

## `NOT READY`

**13 of the mission's 16 acceptance criteria are met.** The three
that are not each name a specific missing thing: an installed service,
an applied ACL, and an external anchor.

Not because the implementation is weak — because a platform whose
central claim is "the agent cannot authorise itself" cannot claim that
while the boundary is a document.

The full reasoning, per criterion, is in `09-PRODUCTION-READINESS.md`.

## Where everything is

| | |
|---|---|
| The code | `C:\Users\Utente\Desktop\ConsequenceMap-Platform` — branch `feature/platform-v1`, 31 commits |
| The documents | `design/platform/` — 10 documents |
| The decisions | `security-decisions/` — ADR-001 (cryptography), ADR-002 (the service identity), and D-22…D-28 |
| The delivery | `ConsequenceMap-Security-Platform-v1-20261109.zip` — SHA-256 `81ce968d4f1cc37314cab9394b31d466a570aee6ccb1cb504137e81da563637e` |
| The manifest | `MANIFEST-SHA256.json` — 218 files, with a self-referencing fixed point |
