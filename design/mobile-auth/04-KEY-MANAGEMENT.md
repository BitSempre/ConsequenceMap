# Key Management

**Status:** DESIGN.

---

## 1. The keys

| Key | Where | Lifetime | Purpose |
|---|---|---|---|
| **Authorisation key** (`K_auth`) | The phone's secure hardware | Long, rotates rarely | Signs approvals |
| **Channel key** | Derived; lives in both devices | Short (hours) | Encrypts the request/response channel |
| **PC key** (`K_pc`) | The PC | Long | Authenticates the PC to the phone |

Only `K_auth` matters for security. The others are conveniences that
protect the channel; the channel is never the trust anchor.

---

## 2. Generation

The authorisation key is generated **on the phone**, in the secure
hardware, and **never leaves it**.

```
Android:  KeyGenerator with KeyGenParameterSpec
          .setDigests(KeyProperties.DIGEST_SHA256)
          .setAlgorithmParameterSpec(new EcdsaParameterSpec("secp256r1"))
          .setUserAuthenticationRequired(true)   <- platform enforces presence
          .setInvalidatedByBiometricEnrollment(true)  <- new fingerprint invalidates

iOS:      SecKeyCreateRandomKey with
          kSecAttrTokenIDSecureEnclave
          + kSecAccessControl with .privateKeyUsage + .biometryCurrentSet
```

**Two rules:**

1. The private key is **never exportable**. On Android,
   `setIsStrongBoxBacked(true)` where available; on iOS, the Secure
   Enclave is not exportable by construction.
2. **User authentication is required** for every signing operation. This
   is enforced by the platform, so the app cannot skip it.

---

## 3. What the PC stores

| Item | Where | Notes |
|---|---|---|
| The public key | The guard's store (boundary 3) | Public by definition; read access is fine, write access is fatal |
| The key id | Alongside it | A stable identifier, e.g. `phone-key-1` |
| The revocation list | Alongside it | The guard's own store |

**The PC never stores anything that lets it sign.** There is no private
key on the PC at all. This is the property that makes the whole design
work: the agent shares a machine with the PC, so anything on the PC is
reachable by the agent.

---

## 4. Rotation

| When | What happens |
|---|---|
| **Scheduled** | Rotate every N months, or after a set number of approvals |
| **On suspicion** | Rotate immediately; the old key is revoked |
| **On device replacement** | New key; old key revoked |
| **On compromise** | Revoke; re-pair |

**Rotation procedure:**

1. The phone generates a new key pair.
2. The owner approves the rotation on the phone, with presence.
3. The new public key is sent to the guard over the authenticated
   channel, signed by the **old** key (proof of possession).
4. The guard verifies the old key's signature, adds the new key, and
   **revokes the old one**.
5. The revocation list is written by the guard's store.

**Step 3 is the important one.** Without proof of possession, the agent
could register its own key as the author's and authorise everything.
Rotating *to* a new key therefore requires the *old* key to sign, and
the old key is revoked in the same operation — so a rotation cannot
leave two valid keys.

---

## 5. Revocation

The revocation list lives in the guard's store and is **consulted at
verification time**, never cached beyond the request.

**VERIFIED_FACT (from the platform's implementation):** the revocation
check is part of the mandatory verification, and
`revocation_max_cache_age_seconds` is 0 — the list is not cached.

**Limitation, stated plainly:** the revocation list's own freshness
cannot be established. There is no timestamping authority and no
certificate revocation infrastructure on this host (RR-15 in the
Revision 5 risk register). A revoked key is detected **when the list is
consulted**; if the list itself is stale, that staleness is
undetectable. The mitigation is to keep the list small and to make
revocation reachable.

---

## 6. Loss and theft

| Scenario | Immediate effect | Recovery |
|---|---|---|
| Phone lost, no approvals pending | Nothing | Revoke the key; re-pair; rotate |
| Phone lost, approvals pending | Those approvals remain valid until they expire | Revoke; **do not** let the new phone "adopt" them |
| Phone stolen and unlocked | The attacker may sign | Revoke immediately — this is the reason the validity window is short |
| Phone lost while off-platform | Nothing | — |

**Revocation must be reachable without the phone.** If revoking a lost
phone required the phone, revocation would be impossible exactly when
it is most needed. The owner revokes from the PC — through a
mechanism the agent cannot perform, such as a physical confirmation.

**This is a genuine open question:** the agent can drive the PC, so
"revoke from the PC" is not by itself safe. Options, none implemented:
a second enrolled device; an offline recovery code the owner holds; or
a physical confirmation. **This decision is the owner's.**

---

## 7. Secure key handling rules

| Rule | Reason |
|---|---|
| The private key is never serialised, logged or transmitted | It cannot be leaked if it never leaves |
| The key id is derived from the public key, not chosen freely | A chosen id could collide or be confused |
| The platform's `setUserAuthenticationRequired(true)` is **never** disabled to make signing "work" | That removes the only human-presence guarantee |
| `setInvalidatedByBiometricEnrollment(true)` on Android | A newly enrolled fingerprint invalidates the key |
| The app reports the **actual** security level to the user | A silent downgrade to software-only is a lie |
| The app never offers "skip the check" | The check is the security |

---

## 8. Implementation status

**NOT IMPLEMENTED.** No key is generated, stored, rotated or revoked by
any code in this package.

What **is** implemented is the revocation *check*: the verification
protocol refuses an authorization whose key is on the revocation list,
and that is tested (`test_authorization.py::test_t09_a_revoked_key_is_rejected`
and `test_deployment.py`). The list itself, and the rotation procedure,
are not.
