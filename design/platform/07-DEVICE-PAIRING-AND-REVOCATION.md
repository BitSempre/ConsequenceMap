# Device pairing, identity and revocation

## The device's identity

A signing device has a **cryptographic identity**: an Ed25519 key pair.
The public key is the device's identity; the private key never leaves
the device's secure hardware.

`approved_by` is a **label** the human's device writes, and the
service never treats it as an authority. The authority is the key. A
label can be anything; a signature cannot be forged.

## Pairing

Pairing binds a device to a service instance. The protocol:

1. The service generates a **pairing challenge** — a fresh nonce, a
   fresh key pair, and the service's identity.
2. The device verifies the service's identity **out of band** — the
   human compares a short fingerprint shown on both. This is the one
   place where the human's eyes are the mechanism, and it is a
   *comparison*, not a *click*: the agent cannot make two fingerprints
   match.
3. The device generates its own key pair and signs the challenge.
4. The service records the device's public key, bound to the challenge
   that was signed.
5. The pairing is audited.

**The reference implementation** is in
`design/mobile-auth/prototype/protocol.py`. It has been probed: the
escaping rules, the canonical form, and the display-field binding were
all attacked, and two real defects were found and fixed.

## What the human sees, and what is signed

The phone displays the **proposal's own fields** — the action, the
resources, the permissions — and those fields are **inside the signed
proposal**.

This was a real defect, found in the eighth round: the display fields
(`affected_resources`, `consequence_summary`) lived *beside* the
proposal, so they were outside the hash and outside the signature. An
attacker could change what the phone showed without invalidating the
approval.

**The summary can still be a lie.** A signature cannot tell a human
that the summary is untrue. The mitigation is unchanged: the phone
renders the resources and the action **verbatim**, and does not ask
the human to trust a summary. That is a design obligation on the
phone application, not something cryptography can do.

## Revoking a lost device

Revocation must work **without** the lost device. The mechanism is a
**recovery grant**:

```
RecoveryGrant {
    grant_id, device_id, reason,
    issued_at, expires_at,
    recovery_key_id, signature
}
```

- The grant is signed by a **recovery key that is not on the phone**.
- It authorises **exactly one** revocation of **exactly one** device.
- It has a validity window.
- It is **consumed atomically** when used, so a replayed grant is
  refused by the same mechanism that refuses a replayed authorisation.

### The agent cannot revoke

There is no key the agent controls that the service accepts as a
recovery key, and there is no method that revokes without a verified
grant. The grant must carry the recovery key's signature.

### The gap, stated plainly

**This host has no hardware-backed credential.** TPM 1.2, Windows Hello
not provisionable, no smart cards, no FIDO2 devices, no Passport.

The module implements the **protocol and the enforcement**. The
credential's own security is whatever the deployment provides. A real
deployment needs one of:

- a smart card with a P-256 key;
- a FIDO2 security key that can sign (FIDO2's CTAP2 signing
  extension);
- a second device, held in escrow, that holds the recovery key;
- an offline recovery code, split into shares, with a threshold.

Until one of those exists, the revocation mechanism is **real but
unanchored**: the protocol works, and the thing that makes it safe is
missing.

### Revocation is durable and audited

A revocation is written to the store, so it survives a restart, and it
is audited. A revocation that leaves no trace is a revocation that can
be denied.

### Re-pairing

After a revocation, the device must be **re-paired**: a new pairing
challenge, a new key pair, and a fresh registration. The revoked key
stays revoked. A re-pairing does not resurrect the old identity.

## The key registry

One place holds the trusted keys and the revoked ones, so a key cannot
be trusted in one place and revoked in another:

| Key kind | Used for |
|---|---|
| `device` | Signing approvals |
| `recovery` | Signing recovery grants |

Revoking a recovery key stops it from signing new grants. The grant
that is already in flight is refused too, because the grant's window
and its single-use nature bound its power.
