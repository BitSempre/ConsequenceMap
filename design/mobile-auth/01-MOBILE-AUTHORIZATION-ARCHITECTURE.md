# Human Authorization Architecture via Smartphone

## Overview
This document outlines the architecture for human authorization via a smartphone. The focus is on a secure pairing protocol, hash-bound signatures, and a verifiable prototype. The key components of this architecture include:

1. **Pairing Protocol**
2. **Signature Hash Binding**
3. **Prototype Verification**

## 1. Pairing Protocol
The pairing process between the smartphone and the PC should be secure and resistant to Man-In-The-Middle (MITM) attacks. We propose using a QR-code-based pairing mechanism that retrieves a short-lived token combined with a public-key handshake.

### Details
- **QR Code Pairing**: The smartphone generates a QR code representing a token.
- **Short-lived Token**: The token must expire quickly to prevent replay attacks.
- **Public Key Handshake**: Upon scanning the QR code, the PC should verify the public key of the smartphone.

### Entropy Argument
The QR code pairing has sufficient entropy, ensuring that brute-force attacks on the token are impractical due to:
- The complexity of the QR code representation.
- The short lifetime of the token.

## 2. Signature Hash Binding
All approval requests will carry essential data such as:
- Proposal ID
- Proposal hash
- Operation details
- Affected resources

The proposal hash is bound to the exact content of the proposal. To achieve this:
- We utilize a canonical form that ensures the information is ASCII-only.
- Any non-ASCII data must be escaped before hashing to guarantee that the hash matches on both smartphone and PC sides.

### Canonical Form
The existing canonical form must be checked for compliance with:
- No duplicate keys
- Strict JSON format

## 3. Prototype Verification
A prototype will be implemented to demonstrate the pairing and signature verification functionalities. The prototype will include testing all possible failure cases:
- Tampering with proposals
- Replay attempts
- Expired approvals
- Revoked keys and non-ASCII input failures.

### Prototype Details
The prototype will consist of:
- **`protocol.py`**: Implements the canonical protocol features.
- **`demo.py`**: Runs a series of tests to demonstrate the functionality and verify failures.

The implementation will rely on a pluggable signer interface for actual signing purposes, ensuring that a production-ready library or platform keystore is utilized.