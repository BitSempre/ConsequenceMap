# Threat model — ConsequenceMap Security Guard

This document covers the **guard** (the service side). The plugin-side
threat model, with the eight earlier rounds of findings, is in
`sec-arch/02-THREAT-MODEL.md`.

## The adversary

**A compromised AI agent** that controls:

- the plugin process, its files, its configuration and its skills;
- the desktop, through `computer_use` — it can click and type;
- multiple processes running concurrently;
- the ability to kill and restart services;
- the ability to fill the disk.

**Not** in scope: a compromised Windows administrator. The agent does
not have that capability, and pretending otherwise would make the
design's claims unfalsifiable.

## Assets

| Asset | Compromise means |
|---|---|
| The service's private execution authority | The agent can run protected operations |
| A signing key on the phone | The agent can forge approvals |
| The durable store | The agent can un-consume an authorisation |
| The policy | The agent can widen what is permitted |
| The audit trail | The agent can hide what it did |
| The service binaries | The agent can replace the authority |

## Threats, and what stops them

| # | Threat | STRIDE | Control | Tested? |
|---|---|---|---|---|
| T1 | The agent forges an approval | Spoofing | Ed25519 over the exact proposal; the plugin cannot verify a signature at all | **Yes** |
| T2 | The agent edits the proposal after approval | Tampering | The hash is **recomputed**; the approval is bound to the recomputed hash | **Yes** |
| T3 | The agent changes what the phone **displayed** | Tampering | The display fields are inside the signed proposal | **Yes** |
| T4 | The agent replays an approval | Replay | The spent set, atomic and durable; the transport nonce | **Yes** |
| T5 | The agent executes twice with one approval | Elevation | `ConsumedAuthorizations`: one execution, atomic across processes | **Yes** |
| T6 | The agent uses an approval for a **different operation** | Elevation | The authorisation carries its operation; the service compares | **Yes** (ninth round) |
| T7 | The agent asks for more scope than approved | Elevation | The approved scope must be a subset of the **requested** scope, carried separately | **Yes** (ninth round) |
| T8 | The agent runs an operation outside the allowlist | Elevation | The policy's allowlist; unknown operations are denied | **Yes** |
| T9 | The agent passes a command | Elevation | The protocol has no field for one; the argument map is the policy's | **Yes** |
| T10 | The agent forges the service's response | Spoofing | The plugin never decides; it asks and presents | **Yes** (in-process) |
| T11 | The agent sends `allowed=True` | Spoofing | The response schema is closed; the decision and the flag must agree | **Yes** |
| T12 | The agent races two processes | Elevation | The consumption is an `INSERT` in an immediate transaction | **Yes** — two real processes |
| T13 | The agent restarts the service to reset state | Elevation | The state is durable; a restart does not un-consume | **Yes** |
| T14 | The agent rewrites the audit trail | Repudiation | Immutable records, hash chain, checkpoints | **Partly** — the external anchor is missing |
| T15 | The agent truncates the audit trail | Repudiation | The chain needs an external head anchor | **Partly** — the mechanism exists, the anchor does not |
| T16 | The agent fills the disk | DoS / Repudiation | The audit append fails; the operation is refused | **Yes** |
| T17 | The agent locks the database | DoS | The store raises; the operation is refused | **Yes** |
| T18 | The agent kills the service mid-operation | Repudiation | The state becomes `OUTCOME_UNKNOWN`; it is never retried automatically | **Yes** |
| T19 | The agent simulates a human approval on the desktop | Spoofing | **The design does not rely on the desktop.** The authority is off-PC | **Yes** — by construction |
| T20 | The agent impersonates the service's client | Spoofing | The pipe's client token is checked against the allowlist | **Seam tested**; the Windows path is not |
| T21 | The agent writes the protected store | Tampering | The filesystem ACL | **Designed, not installed** |
| T22 | The agent replaces the service binary | Tampering | The install directory's ACL | **Designed, not installed** |
| T23 | The agent revokes the legitimate device | DoS | A revocation needs a signed recovery grant the agent cannot produce | **Yes** |
| T24 | The agent replays a recovery grant | Replay | The grant is consumed atomically | **Yes** |
| T25 | The agent exploits a clock shift | Tampering | The window is bounded; the skew tolerance is applied to the expiry side only | **Yes** |
| T26 | The agent adds a field to a signed document | Tampering | The signed payload is the document minus **exactly** the `signature` field | **Yes** |
| T27 | The agent uses an unauthorised algorithm | Spoofing | The algorithm allowlist; an unknown algorithm is refused outright | **Yes** |
| T28 | The agent exploits a malformed key or signature | DoS | The formats are checked; malformed values are refused, not retried | **Yes** |
| T29 | The agent exploits a Unicode normalisation | Tampering | The canonical form is ASCII-only; non-ASCII keys are refused | **Yes** |
| T30 | The agent convinces the service to run a proxy | Elevation | The handler is in the service binary; the arguments are derived by the policy | **Yes** |

## Residual risks

| # | Risk | Severity | Mitigation available | Status |
|---|---|---|---|---|
| R1 | The Windows service is not installed; the ACLs are untested | **High** | Install under an administrator; run the three acceptance checks | **Open** |
| R2 | No hardware-backed recovery credential exists on this host | **High** | A smart card, a FIDO2 key, or an escrow device | **Open** |
| R3 | The audit trail has no external anchor | Medium | A write-once location outside the agent's reach | **Open** |
| R4 | The transport nonce set is in memory and is lost on a restart | Low | The spent set is the replay defence and is durable | Accepted |
| R5 | The phone is a single point of failure | Medium | The recovery grant; but whoever holds the phone holds a valid authority | Accepted |
| R6 | An administrator is above the design | — | Outside the threat model | Accepted |
| R7 | The mobile applications do not exist | Medium | The protocol and the reference implementation do | **Open** |
| R8 | The service's handlers are untested against real side effects | Medium | An integration environment with disposable targets | **Open** |

## What "fail-closed" means here, concretely

Every one of these produces a **DENY with a reason**, and in every one
of them the handler does not run:

- the request is malformed, oversized, or has an unknown field;
- the version is wrong;
- the caller is not on the allowlist;
- the nonce has been seen;
- the operation is not in the allowlist;
- the signature does not verify, or the algorithm is not allowed, or
  the key is unknown or revoked;
- the proposal does not hash to the approved hash;
- the operation differs from the approved operation;
- the approved scope exceeds the requested scope, or does not cover
  the operation;
- the window is expired, not yet valid, or longer than the policy;
- the authorisation was already consumed;
- the audit trail cannot be written;
- the operation cannot be recorded;
- the authorisation cannot be consumed;
- the handler raised.

The tests assert the **last** point in every refusal case: not only
that the decision is DENY, but that the handler was not called.
