# Prototype — Phone Authorization Protocol

A runnable demonstration of the hash-bound approval protocol.

## What it is

A reference implementation of the **PC-side** half of the protocol: it
builds the canonical bytes the phone signs, and it verifies what comes
back. It imports the canonical form from `consequence_map.core.canonical`
rather than re-implementing it, so there is exactly **one** canonical
form in the system.

## What it is NOT

It is **not** a signature implementation. The demonstration signer is a
keyed hash — enough to prove that binding and tamper detection work, and
explicitly not enough to prove unforgeability. Production signing
happens in the phone's secure hardware (Android Keystore or iOS Secure
Enclave), and production verification on the PC needs a maintained
library or a reviewed pure-Python verifier.

## Running it

From the `ConsequenceMap` folder:

```
python design/mobile-auth/prototype/demo.py
```

Exit code **0** only if every negative case correctly failed. A
demonstration that passes while a tamper goes undetected is worse than
no demonstration, so the script exits non-zero if any negative case
succeeds.

If the repository is not on `PYTHONPATH`, the script finds it relative
to its own location.

## The cases it demonstrates

| # | Case | Expected |
|---|---|---|
| 1 | A correct approval | verifies |
| 2 | The proposal's action changed after approval | rejected — `AuthorizationInvalid` |
| 3 | A resource added after approval | rejected — `AuthorizationInvalid` |
| 4 | An old approval replayed against another proposal | rejected — `AuthorizationInvalid` |
| 5 | The authorization expired | rejected — `AuthorizationExpired` |
| 6 | The phone's key was revoked | rejected — `AuthorizationRevoked` |
| 7 | Non-ASCII text, unescaped | the canonical form refuses it — `CanonicalisationError` |
| 8 | Non-ASCII text, escaped | canonicalises, and the escape is stable |
| 9 | A summary that lies about the operation | **still verifies** — see below |

### Case 9 is a documented design obligation, not a bug

The consequence summary is signed, so it cannot be *changed* — but it
can be a **lie**. The cryptography cannot tell a lie from the truth.

The mitigation is presentation, and it is specified in
`../03-APPROVAL-UI-SPECIFICATION.md`: the phone must show the action
and the resource list **verbatim**, and treat the summary as
supplementary.

## The ASCII-only rule

The canonical form is ASCII-only. A proposal containing any character
above U+007E cannot be hashed until it is escaped.

**Both the phone and the PC must escape identically**, or the hashes will
not match and every approval will be rejected. `escape_for_canonical`
and `escape_tree` in `protocol.py` are that rule in one place, and they
are the reference the mobile implementation must match.

Escaping is not normalisation: `"cafe\u0301"` (NFD) and `"caf\u00e9"`
(NFC) stay distinct, because the approval must bind to the exact bytes
that were displayed and hashed.

## Files

| File | Purpose |
|---|---|
| `protocol.py` | The reference implementation: escaping, canonical payload, request building, verification |
| `demo.py` | The demonstration, with its eleven cases |

## Status

**PROTOTYPED and VERIFIED.** The protocol is implemented and the
demonstration passes with exit code 0.

**NOT IMPLEMENTED:** the mobile applications, the platform keystore
integration, the pairing transport, and a real signature algorithm.
