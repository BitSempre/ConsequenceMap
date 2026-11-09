# Residual Risks

**Status:** DESIGN.

This document lists what **cannot** be fixed, and what is being
accepted. A risk register that only lists fixed things is not a risk
register.

---

## 1. The limits of the threat model

**Out of scope:** an attacker with total administrative control of the
Windows machine. That attacker can read the trust anchor, replace the
verifier, patch the guard, rewrite the audit store, and install a
keylogger. Nothing here prevents that, and nothing here claims to.

**In scope:** the AI agent running with the user's own credentials in the
user's own interactive session, with the ability to click the desktop.

---

## 2. Risks that cannot be mitigated in this environment

These are properties of the host, not defects in the design.

### RR-A — The agent is inside the interactive session

**VERIFIED_FACT.** The Hermes agent runs in session 1 (`console`,
Active) as the same user, and `computer_use` clicks and types on the
desktop with background delivery.

**Consequence.** Any prompt on this desktop is a request, not a gate.

**Mitigation available:** the phone. **Residual:** a user-level
malware that runs in the same session has the same capability, so the
phone defends against *the agent*, not against *all local malware*.

**Accepted.** The alternative — a desktop-only design — is not a design.

### RR-B — No hardware root of trust

**VERIFIED_FACT.** TPM **1.2** (`ACPI\PNP0C31`), not 2.0. Windows Hello
not provisioned (`PreReqResult: WillNotProvision`). No CNG keys, no
smart card reader, no FIDO2 device. CNG returns `NTE_NOT_SUPPORTED` for
every asymmetric algorithm; the legacy CryptoAPI path fails with
`NTE_BAD_KEYSET`.

**Consequence.** There is no local signing or verification provider, and
no local key that cannot be read by the agent.

**Mitigation available:** the phone's secure hardware is the root of
trust. **Residual:** the chain of trust now crosses a network and a
second operating system.

**Accepted.**

### RR-C — No trusted clock

**VERIFIED_FACT.** No timestamping authority, no certificate revocation
infrastructure, no domain (WORKGROUP, not joined).

**Consequence.** Two things follow. First, the **revocation list's own
freshness** cannot be established — a revoked key is detected when the
list is consulted, but a stale list is undetectable. Second, the
`approved_at` timestamp is self-asserted by the approver, though it is
signed.

**Mitigation available:** a short validity window. **Residual:** clock
manipulation inside that window is undetectable.

**Accepted, with the window kept short.**

### RR-D — No separation of identity available today

**VERIFIED_FACT.** The agent's account `Utente` is a standard account.
The only other local accounts are disabled. `EnableLUA=1`,
`PromptOnSecureDesktop=1`, `ConsentPromptBehaviorUser=3`.

**Consequence.** The guard's service identity does not exist. Until it
does, the platform runs in-process and **provides no boundary** —
which `InProcessDeployment` declares rather than hides.

**Mitigation available:** create the service identity and the ACLs.
**Residual:** creating a service account and installing a service needs
explicit authorisation.

**Open, and it is the single largest blocker.**

### RR-E — A local standard user can tamper with the stores

**VERIFIED_FACT.** Any local malware runs as some user. The guard's
store directory would be writable by that user unless the ACLs forbid
it.

**Consequence.** The hash chain **detects** an alteration; it does not
**prevent** one that recomputes every hash.

**Mitigation available:** the ACLs. **Residual:** the detection depends
on the owner checking, and the checking is manual.

**Accepted, with the chain as evidence and the ACL as prevention.**

---

## 3. Risks accepted by design

### RR-F — The audit chain detects, it does not prevent

A wholesale rewrite with recomputed hashes is internally consistent and
will pass `verify_chain`. The chain is **evidence**; the ACL is
**prevention**.

**Accepted.** The alternative — a remote append-only log — needs a
service, and a service the agent's account cannot write to is a
deployment question, not a design one.

### RR-G — The agent can cause denial of service

It can stop the guard, or refuse to co-operate. The platform's answer
is that an unreachable guard **refuses**. Availability is traded for the
guarantee that an unreachable guard never means an approved operation.

**Accepted deliberately.** The opposite — failing open — is the defect
this whole platform exists to prevent.

### RR-H — The human's attention is a dependency

Pairing requires the human to compare a short code and six digits
across two screens. The approval UI requires the human to read the
operation. **A human who does not read is not a control.**

**Mitigation available:** make the display honest (the full operation,
never truncated) and make rejection easy. **Residual:** a determined
social engineer can still obtain a rubber-stamp approval.

**Accepted, and stated rather than engineered away.** No interface
makes a distracted human into a security control; the platform's job is
to make the *content* available to be read.

### RR-I — A compromised phone can sign

A rooted Android device with a software-only keystore, or an iOS device
with a compromised OS, can produce valid signatures.

**Mitigation available:** revocation, and detecting the keystore tier at
enrolment. **Residual:** the owner must notice and revoke.

**Accepted.**

### RR-J — The consequence analysis can be wrong

A forecast is an analysis, not a fact. The classification system keeps
`VERIFIED_FACT`, `INFERENCE` and `UNKNOWN` apart, and the aggregate
confidence is the weakest claim — but a well-classified wrong analysis
is still wrong.

**Mitigation available:** the platform never lets the analysis authorise
anything (SR-02). **Residual:** a human can be persuaded by a
confident-sounding forecast that is wrong.

**Accepted.** This is the nature of the domain, and the separation of
the analysis from the authorisation is the whole answer.

---

## 4. Open questions that need the owner

| # | Question | Why it matters |
|---|---|---|
| **Q-1** | **Which service identity?** | Blocks SR-08, SR-11, SR-12 — five requirements |
| **Q-2** | **Which PC-side signature algorithm?** | A maintained library breaks C-1; a pure-Python verifier needs independent review. **This is the same trade-off the Revision 5 analysis reached, and it recommends A2+A1** |
| **Q-3** | **How does the owner revoke a lost phone without the phone?** | The agent drives the PC, so a PC-only mechanism is suspect. A second enrolled device? A printed recovery code? |
| **Q-4** | **Should the trust anchor have a backup?** | One copy on one machine is a single point of failure — and that machine is the agent's |
| **Q-5** | **What is the maximum validity window?** | It is simultaneously the exposure window for a lost phone and the replay window for a captured authorization |
| **Q-6** | **Is a second enrolled device required?** | It solves Q-3 cleanly, at the cost of a second thing to lose |
| **Q-7** | **Who installs the Windows service, and when?** | It needs administrative authorisation and a maintenance window |

---

## 5. The summary

| | Count |
|---|---|
| Risks that **cannot** be mitigated in this environment | 5 (RR-A…RR-E) |
| Risks **accepted by design** | 5 (RR-F…RR-J) |
| Open questions for the owner | 7 |
| Requirements blocked on those answers | 5 of 16 |

**The honest summary:** the protocol layer removes the risks that
software can remove. The risks that remain are properties of the
machine and of human attention, and they are listed here rather than
designed around.
