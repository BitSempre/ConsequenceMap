# Recovery and Device Replacement

**Status:** DESIGN.

---

## 1. The rule

> **Recovering must never be an act the agent can perform, and a
> recovered device must never inherit the authority of the lost one.**

Both halves matter. If recovery is agent-triggerable, the agent can
enrol its own phone and authorise everything. If the new phone inherits
the old key's authority, a stolen old phone stays useful.

---

## 2. Scenarios

### 2.1 The phone is lost

**Immediately.** The owner revokes the lost key from the PC. Every
approval signed by it stops applying.

**Recovery.** The owner enrols a new phone with a **new key**. The old
key stays revoked forever — it is not "reactivated".

**The agent cannot do this.** Revocation and enrolment both require a
confirmation the agent cannot produce. This is an **open decision**: the
mechanism is not settled, because "revoke from the PC" is not safe on
its own when the agent drives the PC.

### 2.2 The phone is replaced (upgrade, loss, damage)

Same as 2.1, with one addition: the **pairing** is re-established from
scratch. The new phone gets a new key and a new channel. The old
channel key is not carried over.

### 2.3 The phone's biometric enrolment changes

On Android, `setInvalidatedByBiometricEnrollment(true)` makes the key
**unusable** — the platform refuses to sign. The user must re-enrol,
which means a **new key**, which means the old one is revoked and the
owner re-pairs.

This is intentional. A new fingerprint enrolment is exactly the event
that should invalidate the key.

### 2.4 The PC is reinstalled or replaced

The phone keeps its key. The new PC must be paired again, and the old
PC's channel dies with it. The **trust anchor survives** — the public
key lives in the phone, and the new PC re-pins it during pairing.

If the guard's store was on the PC and the PC was reinstalled, the
anchor is gone and must be re-established by pairing. **This is a
single point of failure**: the anchor has no second copy. A backup
anchor, itself protected, is an open design question.

### 2.5 The authorisation key is compromised

Revoke. Re-enrol. Treat every approval ever signed by that key as
**suspect** — the list of approvals it signed is in the audit trail, so
they can be enumerated and, if necessary, re-checked.

---

## 3. Why the new device does not inherit authority

| Property | Old phone | New phone |
|---|---|---|
| Public key | `phone-key-1` | `phone-key-2` |
| In the anchor | revoked | active |
| Approvals it signed | remain valid **until expiry**, then inert | — |
| Channel key | dead | new |

**Approvals already signed by the old phone are not retroactively
invalidated.** They were legitimate decisions, and the audit trail
should show them as such. What must not happen is the new device being
able to sign as the old one — and it cannot, because the old key is
revoked and the new key is a different key.

**The exposure window is therefore the validity period.** That is the
main reason to keep it short.

---

## 4. The recovery flow

```
  1. The owner notices the loss (phone gone, or a revocation notice).
  2. The owner revokes the old key -- through a channel the agent
     cannot drive.                          [MECHANISM NOT SETTLED]
  3. The guard writes the revocation to its own store.
  4. The owner generates a new key on the new device.
  5. Pairing runs again: QR + short code + six-digit comparison.
  6. The guard pins the new public key and removes the old one.
  7. The new channel key is established.
  8. Pending approvals signed by the old key are now inert.
```

**Step 2 is the unresolved part.** Everything else is mechanical.

---

## 5. Open questions for the owner

1. **How does the owner revoke without the phone?** A second enrolled
   device? A printed recovery code? A physical confirmation at the PC?
   This must be settled before the platform is usable, because "the
   agent can drive the PC" makes every PC-only mechanism suspect.
2. **Should the trust anchor have a backup?** A single copy on one
   machine is a single point of failure, and that machine is the one the
   agent controls.
3. **What is the maximum validity window?** It is the exposure window
   for a lost phone and the replay window for a captured authorization.
   The trade-off is real: shorter is safer but more annoying.
4. **Is a second enrolled device worth requiring?** It solves (1)
   cleanly, at the cost of a second thing to lose.

---

## 6. Implementation status

**NOT IMPLEMENTED.** No recovery, rotation or re-enrolment flow exists
in code.

The part that **is** implemented is the property that makes recovery
meaningful: a revoked key's approvals are refused at verification time,
and that is tested. The flows that produce the revocation are not.
