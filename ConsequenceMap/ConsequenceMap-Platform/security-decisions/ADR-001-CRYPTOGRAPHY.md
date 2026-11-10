# ADR-001 — Cryptography for the ConsequenceMap Security Guard

| | |
|---|---|
| **Status** | Accepted, with the dependency change registered |
| **Date** | 2026-11-09 |
| **Decides** | D-23 — the library and the signature scheme |
| **Supersedes** | The keyed-HMAC placeholder signer |

## Context

The authorization protocol needs a signature that binds a human's
approval to an exact proposal. The previous implementation used
`blake2b` keyed with a shared secret, in the same process as the
verifier.

That proved the **protocol** — a payload is bound, tampering is
detected, a replay fails — and proved **nothing** about unforgeability,
because the agent controls the process that holds the key. An agent
that can read the secret can sign anything.

The mission requires a real signature, from a maintained library, with
the private key on a device the agent cannot reach.

### What the four concepts are, and are not

| Concept | What it proves | What it does not prove |
|---|---|---|
| **Hash** | Integrity: these bytes have not changed | Who produced them. Anyone can hash. |
| **Signature** | Authenticity *and* integrity under a key pair | That the content is **true**. That the decision was **wise**. |
| **Authorization** | That a decision was made, and by whom | That the effect was carried out |
| **Execution** | That the effect happened | — |

A signature over a proposal says: *the holder of this private key
approved exactly these bytes*. It does not say the operation is good
for the user. That judgement stays with the human.

## Decision

**Use `cryptography` (pyca/cryptography) with Ed25519.**

- Version pin: `cryptography==50.0.1`
- Licence: **Apache-2.0 OR BSD-3-Clause** — dual-licensed, so it is
  compatible with a proprietary product *and* with Apache-2.0.
- Transitive dependencies, **measured on this host**:
  `cffi>=2.0.0` (MIT-0) → `pycparser` (BSD-3-Clause). Both are the
  ABI companion of the Rust extension, not additional attack surface of
  their own. `typing-extensions>=4.13.2` is required only on Python
  below 3.11.

  **Note on a common error:** `six` and `importlib-metadata` are
  **not** dependencies of `cryptography` 50.x. They were required by
  older releases and are frequently listed by stale documentation. The
  list above was read from the installed distribution's metadata, not
  from a website.
- Python 3.14: supported by 50.0.1; verified in this environment.

### Why Ed25519

- **Deterministic signatures.** The same key over the same bytes
  produces the same signature. That makes test vectors possible and
  removes a source of nonce-management bugs — Ed25519 has no nonce
  parameter to get wrong.
- **No parameter negotiation.** The key size is fixed at 32 bytes and
  the signature at 64. There is no curve to downgrade.
- **Small keys and signatures.** A public key fits in a QR code; a
  signature is 64 bytes, which fits a phone's screen.
- **Standard.** RFC 8032. Test vectors exist and are published.

### Why `cryptography` and not PyNaCl

| | `cryptography` | PyNaCl |
|---|---|---|
| Licence | Apache-2.0 **or** BSD-3-Clause | Apache-2.0 |
| Underlying | Rust (`safe-crypto`) | libsodium (C) |
| Python support | 3.8+ including 3.14 | 3.8+ |
| Maintenance | pyca/cryptography, very high activity | pyca/pynacl, high activity |
| Test vectors | RFC 8032 exposed through the API | exposed too |
| Wheels | Windows wheels for cp3x | Windows wheels for cp3x |

`cryptography` was chosen because it is the broader library: the same
dependency can later provide the X.509 and key-management pieces the
service identity needs, without a second crypto dependency. PyNaCl is
the fallback if `cryptography` cannot be built for a target platform.

### The dependency change, registered explicitly

Constraint **C-1** required the `consequence_map` package to be
stdlib-only. That constraint is **not** broken — it is honoured, and
honoured in a way that strengthens the architecture:

```
consequence_map     the PLUGIN. Stdlib-only. It may PROPOSE.
consequence_guard   the SERVICE. Uses cryptography. It DECIDES and EXECUTES.
```

The split is the point. The plugin — the part the agent controls —
still cannot verify a real signature at all, so it cannot be talked
into accepting a forged one. The constraint that forced the split is
what makes the split legible.

**C-1 remains in force for `consequence_map`.** It is relaxed only for
`consequence_guard`, and only for `cryptography`.

### The signing rule

What is signed is the canonical bytes of the authorization document
**with exactly the field named `signature` removed**, under the
authorization domain.

The word *exactly* matters. The alternative rule — "strip the fields we
recognise" — is broken: an attacker could add an unknown field, have it
excluded from the signed payload, and the signature would still verify.
Under the rule adopted here, an added field changes the bytes that are
signed, and the signature does not verify.

The canonical form is ASCII-only, length-prefixed, domain-separated,
rejects duplicate keys, rejects floats, rejects non-ASCII, and has a
depth limit. One canonical form is used by the whole system: two would
be two sets of rules, and they would eventually disagree.

### Validation against an external reference

The implementation is validated against the **official RFC 8032
Section 7.1 test vectors** (TEST 1, TEST 2 and TEST 3), transcribed
verbatim from the RFC.

This matters for a specific reason: a test suite that only checks
"my signer agrees with my verifier" proves that the two halves agree.
It does not prove that either of them is Ed25519. The RFC vectors do
that — against a standard that was itself "double checked by Bob
Bradley using three separate implementations (one based on TweetNaCl
and two different implementations based on code from SUPERCOP)".

The vectors live in `consequence_guard/tests/test_rfc8032_vectors.py`
and cover the public-key derivation, the signature, the verification,
and the negative cases the RFC's own driver asserts.

### Algorithm agility

The algorithm is named in the document. Only algorithms on an explicit
**allowlist** are honoured. An unknown or unauthorised algorithm is
**refused outright** — not reported as a failed signature. A document
we do not understand is not a document we failed to verify, and
collapsing the two hides an attack.

### The authorisation has a closed schema

The signed payload is the document minus **exactly** the field named
`signature`. That already makes an added field break the signature.

The authorisation document is nevertheless **also** checked for
unknown fields, and refused if it has any. The reason is that the
two defences fail differently: the signature is *cryptographic*, and a
field the verifier does not understand is *authenticated but ignored* —
and a field that is ignored is a field a signer, or a bug, could add
without anyone noticing. That is exactly the pattern the rest of the
platform refuses: *a field the service does not understand might be
one it would have honoured*.

### Key handling

- Public keys: raw 32 bytes, base64url without padding — one
  canonical string form.
- Signatures: raw 64 bytes, base64url without padding.
- Private keys: never written by this codebase. Loaded from a provider
  the caller supplies — in production, the phone's secure hardware.
- `approved_by` is a **label**, never an authority. The authority is
  the signing key.

## Consequences

**Positive**

- A captured approval cannot be forged without the device's key.
- The plugin cannot verify a signature, so it cannot be the authority.
- The scheme has no parameters to misconfigure and no nonces to
  manage.

**Negative**

- `cryptography` becomes a runtime dependency of the **service**. The
  service now needs a build or a wheel for its target platform.
- A dependency the project did not have, in the component whose
  correctness matters most. This is a real cost, accepted explicitly.
- Ed25519 cannot be used with a hardware token that speaks RSA or ECDSA
  natively. If the target hardware requires it, the adapter would have
  to be ECDSA P-256 over P-256 — a different ADR.

**Neutral**

- The placeholder signer stays in the codebase for the plugin's own
  tests. It is clearly labelled as **not** a signature.

## Alternatives considered and rejected

| Alternative | Why rejected |
|---|---|
| Keep the HMAC placeholder | The key is in the agent's process. It proves protocol, not security. |
| Hand-rolled Ed25519 | Explicitly forbidden, and correctly so. Curve arithmetic is not something to write from scratch. |
| RSA-PSS | Larger keys and signatures, parameter negotiation, and a nonce to manage. |
| ECDSA P-256 | Available in hardware that Ed25519 is not; but it has a nonce, and the failure mode of a reused nonce is catastrophic. Kept as the fallback if the target hardware requires it. |
| PyNaCl | Excellent library; `cryptography` chosen for the broader surface the service identity will need. |
| `hashlib` + a home-made signature | Not a signature. |

## Open questions

- The phone's secure hardware (Android Keystore, iOS Secure Enclave)
  must perform the Ed25519 operation. Some older Android keystore
  versions do not expose Ed25519; the fallback is a hardware-backed
  ECDSA P-256 key, which would require a second ADR.
- Key rotation policy is implemented (a registry, a revocation list)
  but the **schedule** is an operational decision, not a technical one.
