# Residual risks

Every entry names what the risk is, what it costs, and what closes it.
None of these is hidden in a footnote.

## High

### R1 — The trust boundary is specified but not deployed

The service identity (`NT SERVICE\ConsequenceMapGuard`), the protected
store's ACL, and the pipe's client-token check are written down and
specified in code, but **not installed**. The claim "the agent cannot
authorise itself" is therefore demonstrated at the **protocol** level
and **specified** at the **operating-system** level.

**Cost if unaddressed.** The agent, running as the interactive user,
could in principle open the pipe and impersonate the plugin. The
client-token check and the pipe's ACL are what stop it, and neither
has been exercised on this host.

**Closes with.** The installation (ADR-002) and the three acceptance
checks. This needs an administrator.

### R2 — No hardware-backed recovery credential

The revocation protocol works: a recovery grant, signed by a key that
is not on the phone, consumed atomically, good for one revocation. But
**this host has no credential to anchor it to**: TPM 1.2, Windows Hello
not provisionable, zero smart cards, zero FIDO2 devices, zero Passport
credentials.

**Cost if unaddressed.** The recovery key must be held somewhere. If
it is held in software on the PC, the agent can reach it, and the
agent can revoke the legitimate device — a denial of service on the
human's own approvals.

**Closes with.** A smart card, a FIDO2 key with the CTAP2 signing
extension, a second device in escrow, or a split recovery code.

## Medium

### R3 — The audit trail has no external anchor

The chain detects an inconsistent rewrite. It does **not** prevent a
consistent one: an attacker who rewrites every record *and recomputes
the hashes* produces a chain that verifies perfectly. The checkpoints
are the defence, and they are only a defence if the checkpoint itself
lives where the agent cannot write.

**Cost if unaddressed.** The agent could rewrite the history of what
it did, and the rewrite would be internally perfect.

**Closes with.** An external anchor: a write-once location, a separate
machine, or a transparency log. Then the startup integrity gate —
refuse to start if the chain does not verify against the last
checkpoint — becomes implementable.

### R4 — The mobile applications do not exist

The protocol, the canonical form, the pairing flow and the reference
implementation exist and are tested. The Android and iOS applications
that a human would actually use do not.

**Cost if unaddressed.** The human-in-the-loop path cannot be
exercised end to end.

**Closes with.** Building the two applications against the existing
protocol, with the signing operation in the platform's secure
hardware.

### R5 — The handlers are untested against real side effects

The test handlers are recorders. A handler that deletes three of four
files before raising has not been run against a real filesystem, and
the `OUTCOME_UNKNOWN` path has not been observed in anger.

**Cost if unaddressed.** The recovery classification is correct in
principle and untested in practice.

**Closes with.** An integration environment with disposable targets.

### R6 — The phone is a single point of failure

Whoever holds the phone holds a valid authority. A compromised phone
is a compromised approver.

**Cost if unaddressed.** The human's authority can be stolen whole.

**Closes with.** Short validity windows, the revocation mechanism, and
— the real answer — a second factor on the PC side that does not exist
on this host.

### R7 — The startup integrity gate is not implemented

The service should refuse to start if the audit chain does not verify
against the last checkpoint. It does not, because there is no
checkpoint to verify against.

**Closes with.** R3.

## Low

### R8 — The transport nonce set grows without bound

The nonce set is durable, so it survives a restart. It is also never
pruned, so it grows with every request the service ever answers.

**Cost if unaddressed.** Unbounded disk growth over a very long
uptime. The spent set has the same property.

**Closes with.** A retention policy, keyed on the validity window: a
nonce older than the maximum validity window cannot be replayed
anyway, because the authorisation would have expired.

### R9 — The clock is trusted to a degree

30 seconds of skew is tolerated between the PC and the phone. The
service uses its own clock; there is no external time source.

**Cost if unaddressed.** A skewed clock widens the exposure window of
a captured authorisation by up to 30 seconds, and an operator who
changes the system clock can influence it.

**Closes with.** A trusted time source (the Windows Time service
against a domain controller), and the audit already records the
observed skew when it exceeds the tolerance.

## Accepted, and out of scope

### R10 — An administrator is above this design

An administrator can change the policy, the binaries and the store. The
threat model is "a compromised agent", not "a compromised
administrator". This is the operating system's trust model, and
pretending otherwise would make the claims unfalsifiable.

### R11 — The service's private key does not exist yet

The guard's Ed25519 key pair must be provisioned at install time, from
a source the agent cannot reach. The code accepts a key from a
provider; the provisioning procedure is an operational task, and it is
written down rather than left implicit.

### R12 — A single product is not a single process

The user installs one thing. The plugin and the service are internal
components, and the service is an implementation detail of the
security guarantee. The distinction matters: "one product" and "one
privileged process" are different claims, and only the first is true.
