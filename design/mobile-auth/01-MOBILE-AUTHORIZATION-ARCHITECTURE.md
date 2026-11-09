# Mobile Authorization Architecture

**Status:** DESIGN. The protocol is implemented and demonstrated; the
mobile applications are **NOT**.

---

## 1. Why a phone, and nothing else

The whole architecture follows from one measured fact about this host:

> **The Hermes agent runs in the interactive Windows session (session 1,
> `console`, Active) as the same user, and has a `computer_use` tool that
> clicks and types on the user's desktop with background delivery.**

Everything the agent can reach on this machine, the agent can *use*. A
desktop dialog is a request, not a gate. A password prompt is not a
secret factor either — the account has `PasswordRequired=False`.

Measured and excluded as gates on this host:

| Candidate | Why not |
|---|---|
| Desktop dialog | The agent can click it |
| Windows Hello | Not provisioned (`PreReqResult: WillNotProvision`); needs TPM 2.0, this host has **1.2** |
| Smart card | No reader; `scard.exe` absent |
| FIDO2 key | No device attached |
| Password prompt | `PasswordRequired=False` |
| OS signing API | CNG returns `NTE_NOT_SUPPORTED` for every asymmetric algorithm; CryptoAPI fails too |

**The author's phone is the only independent channel.** It is a different
device, on a different operating system, holding a key the agent cannot
read and cannot invoke.

---

## 2. The two halves

```
   PC (untrusted agent's machine)              PHONE (the author's device)
   ┌──────────────────────────────┐            ┌──────────────────────────┐
   │ ConsequenceMap core          │            │ Authorizer app           │
   │  - builds the request        │            │  - shows the proposal    │
   │  - canonicalises it          │            │    IN FULL               │
   │  - computes the hash         │            │  - requires biometric    │
   │                              │  request   │    or PIN                │
   │ Guard (trusted service)      │ ─────────▶ │  - signs the canonical   │
   │  - verifies the signature    │            │    bytes                 │
   │  - decides ALLOW/DENY/       │ ◀───────── │  - returns the signature │
   │    INDETERMINATE             │  signature  │                          │
   │ Executor                      │            │ key never leaves the    │
   │  - allowlisted operation     │            │ secure hardware         │
   └──────────────────────────────┘            └──────────────────────────┘
```

**The phone signs. The PC verifies. Neither trusts the other's word.**

---

## 3. The approval request

What crosses to the phone. Every field is covered by the signature.

| Field | Purpose |
|---|---|
| `proposal` | The **full** proposal — action, resources, permissions, reversibility |
| `proposal_hash` | SHA-256 over the canonical bytes of the proposal |
| `request_id` | Identifies this request |
| `nonce` | 256-bit, unique per request — the replay defence |
| `project` | Which project |
| `operation` | Which operation |
| `affected_resources` | Exactly what is touched |
| `requested_scope` | The permissions being asked for |
| `consequence_summary` | Plain-language summary |
| `requested_by` | Who is asking |
| `expires_at` | When the request stops being valid |
| `protocol_version` | `consequencemap.authorization.v1` |

### The ASCII-only rule

The canonical form is **ASCII-only**. A proposal containing any
character above U+007E **cannot be hashed** until it is escaped.

Both sides must escape identically, or the hashes will not match and
every approval will be rejected. `escape_for_canonical` and
`escape_tree` in `prototype/protocol.py` are that rule, in one place,
and they are the reference the mobile implementation must match.

Escaping is **not** normalisation: `"cafe\u0301"` (NFD) and
`"caf\u00e9"` (NFC) stay distinct. The approval must bind to the exact
bytes that were displayed and hashed.

---

## 4. The verification chain

The PC never trusts a hash it was given. It recomputes.

```
  phone returns (proposal_hash, nonce, signature, scope, window)
                          │
                          ▼
  guard recomputes SHA-256(canonical(proposal))  ◀── NOT the hash from the phone
                          │
              equal to proposal_hash?  ── no ──▶ DENY
                          │ yes
  nonce equal to the request's nonce? ── no ──▶ DENY (replay)
                          │ yes
  scope ⊆ requested scope?              ── no ──▶ DENY
                          │ yes
  now within [valid_from, expires_at]?  ── no ──▶ DENY (expired)
                          │ yes
  key not revoked?                      ── yes──▶ DENY (revoked)
                          │ yes
  signature verifies over the canonical bytes? ── no ──▶ DENY
                          │ yes
                       ALLOW
```

**Every step is mandatory.** There is no branch that treats a missing
check as a pass.

---

## 5. Platform key storage

### Android

| Guarantee | What it gives | How to detect it |
|---|---|---|
| **StrongBox** | A dedicated Secure Element chip | `KeyInfo.getSecurityLevel() == KeyProperties.SECURITY_LEVEL_STRONGBOX`, and `isInsideSecureHardware()` |
| **TEE-backed** | TrustZone / Trusted Application | `getSecurityLevel() == SECURITY_LEVEL_TRUSTED_ENVIRONMENT`, `isInsideSecureHardware() == true` |
| **Software-only** | No hardware protection | `getSecurityLevel() == SECURITY_LEVEL_SOFTWARE`, `isInsideSecureHardware() == false` |

StrongBox must be requested explicitly (`setIsStrongBoxBacked(true)`)
and may fail — the app must fall back and then **tell the user which
guarantee it actually got**. An app that silently degrades from hardware
to software is worse than one that says so.

The key is generated with `PURPOSE_SIGN`, `setDigests(SHA256)`, and
`setUserAuthenticationRequired(true)` so the platform enforces the
biometric or PIN check **before every signing operation**. That
enforcement is in the platform, not in the app — which is the point.

### iOS

The Secure Enclave is always hardware-backed; there is no software-only
path on modern iOS. The key never leaves it and the signing operation
happens inside it.

The constraints are real and shape the design:

- **no arbitrary-data signing** — the enclave signs a digest of a
  message, not a message;
- **no export** — the key cannot leave;
- **user presence is enforced by the key's access control**, not by the
  app:
  - `biometryCurrentSet` — the signing operation fails if the enrolled
    biometry changes (a new fingerprint invalidates the key);
  - `privateKeyUsage` — the key is released only for a private-key
    operation, and the user presence requirement is attached to it.

**Can a background process sign silently? No.** The key's access control
requires user presence, and the enclave enforces it. If the passcode is
set, `kSecAccessControlDevicePasscode` is the fallback when biometry is
unavailable — but it is still a user-presence check, and it is slower
and less convenient, not less secure.

---

## 6. Pairing

See `02-PAIRING-PROTOCOL.md`.

---

## 7. What the phone displays

See `03-APPROVAL-UI-SPECIFICATION.md`.

---

## 8. Key management and recovery

See `04-KEY-MANAGEMENT.md` and `05-RECOVERY-AND-DEVICE-REPLACEMENT.md`.

---

## 9. Compatibility

See `06-COMPATIBILITY-MATRIX.md`.

---

## 10. Implementation status

| Component | Status |
|---|---|
| Canonical form, hashing, binding | **IMPLEMENTED, TESTED** |
| Approval protocol (9 checks) | **IMPLEMENTED, TESTED** — 36 tests |
| Reference protocol module | **IMPLEMENTED** — `prototype/protocol.py` |
| Demonstration, 11 cases | **IMPLEMENTED, VERIFIED** — `prototype/demo.py`, exit 0 |
| Pairing protocol | **DESIGNED** — `02-PAIRING-PROTOCOL.md` |
| Android app | **NOT IMPLEMENTED** |
| iOS app | **NOT IMPLEMENTED** |
| Platform keystore integration | **NOT IMPLEMENTED** |
| PC-side signature verification (real algorithm) | **NOT IMPLEMENTED** — see below |

### The signature-verification gap

The platform has **no working OS asymmetric signing provider** on this
host (measured). So the PC must verify an Ed25519 signature using
either:

| Option | Cost |
|---|---|
| A maintained library (`cryptography`, `PyNaCl`) | A production dependency — breaks invariant **C-1** (`dependencies.py` asserts an empty production inventory) |
| A reviewed pure-Python Ed25519 verifier | No dependency, but **requires independent cryptographic review** — the same conclusion the Revision 5 analysis reached |

**Recommendation: A2+A1** — a maintained library, with C-1 amended by
explicit decision. A hand-written verifier that has not been reviewed is
a worse risk than a declared dependency, precisely because it is the
component carrying the weight. **This decision is the owner's; it is not
made here.**
