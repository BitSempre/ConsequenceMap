# Pairing Protocol

**Status:** DESIGN.

---

## 1. The problem

The PC and the phone must share a secret that an attacker standing
between them cannot learn, so that a request shown on the phone is
genuinely from *this* PC, and a signature returned to the PC is
genuinely from *this* phone.

The agent is the adversary in the middle. It can see everything the PC
displays and it can write everything the PC stores. It **cannot** read
the phone's key material, and it cannot make the phone sign without the
human.

So the pairing must be authenticated against a **man-in-the-middle who
controls the PC**, which is stronger than the usual requirement.

---

## 2. The chosen scheme: QR bootstrap + public-key handshake

**Step 1 — the phone initiates.** The phone generates a key pair
(`K_phone`) in its secure hardware and shows a QR code containing:

| Field | Value |
|---|---|
| `v` | protocol version |
| `pub` | the phone's public key (32 bytes, Ed25519) |
| `n` | a fresh 256-bit nonce |
| `exp` | expiry, at most 5 minutes |

**Step 2 — the PC scans and answers.** The PC generates its own pair
(`K_pc`), and shows **on the phone** a short code:

```
   +---------------------------+
   |   4271 9035               |   <- 8 digits
   +---------------------------+
```

This is the human-verification step: the user reads the code off the
PC and types it into the phone. The code is derived from both public
keys and both nonces.

**Step 3 — both sides confirm.** Both sides compute:

```
   confirm = SHA-256("consequencemap.pairing.v1" ||
                     pub_pc || pub_phone ||
                     nonce_pc || nonce_phone ||
                     expires_at)
```

and display the first **6 digits** of `confirm` in base-10. The user
confirms they match.

**Step 4 — the channel is established.** Both sides derive:

```
   channel_key = HKDF-SHA256(
       ikm  = SHA-256(confirm_bytes),
       salt = nonce_pc || nonce_phone,
       info = "consequencemap.channel.v1")
```

Subsequent requests are encrypted with `channel_key` and signed by
`K_phone`.

---

## 3. Why the short code, and why 8 digits

### The code

The code exists to bind the human's attention to **this** exchange. The
agent could generate a code and show it on the PC — but it cannot make
the phone display the **matching** code, because the phone's display is
not under the agent's control.

The entropy argument:

| Quantity | Value | Note |
|---|---|---|
| Code length | 8 decimal digits | 10^8 ≈ 2^26.6 bits |
| Attempts before expiry | 5 minutes | |
| Rate limit | 5 attempts, then 15-minute lockout | |
| Guessing probability | ≤ 5 / 10^8 ≈ **5 × 10⁻⁸** per pairing | |
| Attempts in 5 minutes at the limit | 5 | |
| **Total probability** | **≤ 5 × 10⁻⁸** | |

That is small. But it is only the *second* line of defence — the first
is that the code is **displayed on both devices** and compared, which
turns the attack into a visual one rather than a brute-force one.

### The comparison code

`confirm` is derived from **both public keys and both nonces**. An
attacker who substitutes its own public key cannot produce the same
`confirm`, so the six digits will not match. This is the
man-in-the-middle defence, and it does not depend on the short code at
all.

### Why a QR code as well

The QR carries the phone's public key and nonce, so the user does not
have to transcribe a long value. It carries **no secret** — everything
in it is public by the time it is scanned. A QR code carrying a secret
would be a different design with different exposure; this one carries
only public material, so an attacker who photographs it learns nothing
they could not already learn.

---

## 4. What is exchanged afterwards

| Direction | Payload | Protection |
|---|---|---|
| PC → phone | The approval request (full proposal + metadata) | Encrypted with `channel_key`; integrity by AEAD |
| Phone → PC | The authorization (hash, nonce, scope, window, signature) | Encrypted with `channel_key`; plus the Ed25519 signature over the canonical bytes |

The channel encryption protects against a passive observer and against
tampering in transit. The **signature** is what protects the approval:
it is bound to the proposal's hash, so it remains verifiable even if the
channel is later replaced, and it proves the phone — not the agent —
produced it.

**The channel is not the trust anchor.** The trust anchor is the phone's
public key, pinned at pairing and stored in the guard's store. The
channel is a convenience; the anchor is the security.

---

## 5. Failure handling

| Failure | Response |
|---|---|
| The codes do not match | Abort. **Never** proceed on a partial match. |
| The QR is scanned by someone else | The short-code comparison fails — the codes will not match |
| The channel key expires | Re-pair. The old phone's key stays in the revocation list unless the owner explicitly removes it |
| The phone is replaced | The old key is **revoked**; approvals signed by it stop applying |
| The PC is reinstalled | The phone keeps its key; the new PC must be paired again, and the old PC's channel is dead |

**There is no "trust this code" button that skips the comparison.** A
pairing UI that offers to skip the visual confirmation removes the only
defence the human contributes.

---

## 6. What the agent can do to the pairing

| Attack | Outcome |
|---|---|
| Read the QR from the screen | Learns only public material — no secret |
| Photograph the QR and re-display it | Useless: the QR holds no secret |
| Replace the short code on the PC screen | The phone shows its own code; they will not match |
| Type the code into the phone itself | It can only cause a **failed** pairing, or pair with a PC the owner did not choose — which the owner sees as a code mismatch |
| Substitute the phone's public key | `confirm` changes; the six-digit comparison fails |
| Replay an old pairing exchange | The nonces are fresh; `confirm` differs |
| Use a paired channel after the phone is lost | The key is revoked at loss; the channel alone authorises nothing |

---

## 7. What is NOT covered

- **A compromised phone.** If the phone is rooted or the app is
  compromised, the attacker can sign. The platform's answer is
  revocation, not prevention.
- **A compromised PC at pairing time.** If the agent controls the PC
  *before* pairing, it can show its own public key — but the short code
  and the six-digit comparison both fail, because the phone's view of
  the exchange differs. **The owner must actually look at both screens.**
  This is the one place the design depends on human attention, and it is
  stated rather than glossed over.
- **A compromised Android device with software-only keystore.** The key
  is extractable by root. The app must show the user which guarantee
  they actually have.

---

## 8. Implementation status

**NOT IMPLEMENTED.** This is a design specification. The reference
implementation covers the *protocol* side — canonicalisation, hashing,
binding, verification — and is demonstrated in `prototype/demo.py`.
The pairing transport, the QR encoding and the phone application are
not implemented.
