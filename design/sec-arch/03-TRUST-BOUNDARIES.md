# Trust Boundaries — ConsequenceMap Platform v1

**Status:** DESIGN.

---

## 1. The four boundaries

```
    ┌──────────────────────────────────────────────────────────────┐
    │  TRUST BOUNDARY 1 — process                                 │
    │  ┌────────────────────────────────────────────────────────┐  │
    │  │  TRUST BOUNDARY 2 — OS identity                         │  │
    │  │  ┌──────────────────────────────────────────────────┐    │  │
    │  │  │  TRUST BOUNDARY 3 — store ACL                     │    │  │
    │  │  │  ┌────────────────────────────────────────────┐   │    │  │
    │  │  │  │  TRUST BOUNDARY 4 — physical               │   │    │  │
    │  │  │  │                                            │   │    │  │
    │  │  │  │      ┌──────────────────┐                   │   │    │  │
    │  │  │  │      │  AUTHOR'S PHONE  │                   │   │    │  │
    │  │  │  │      │  (independent    │                   │   │    │  │
    │  │  │  │      │   device)        │                   │   │    │  │
    │  │  │  │      └────────┬─────────┘                   │   │    │  │
    │  │  │  └───────────────┼─────────────────────────────┘   │    │  │
    │  │  │      ┌───────────┴──────────────┐                  │    │  │
    │  │  │      │   SECURITY GUARD        │                  │    │  │
    │  │  │      │   service identity       │                  │    │  │
    │  │  │      │   verifier, anchor,      │                  │    │  │
    │  │  │      │   revocation, audit      │                  │    │  │
    │  │  │      └───────────┬──────────────┘                  │    │  │
    │  │  └──────────────────┼─────────────────────────────────┘    │  │
    │  └─────────────────────┼────────────────────────────────────┘  │
    │                        │ authenticated pipe (agent → guard)   │
    │  ┌─────────────────────┴────────────────────────────────────┐  │
    │  │  AGENT (untrusted)                                       │  │
    │  │  Hermes runtime, user's account, session 1,              │  │
    │  │  computer_use can click the desktop                      │  │
    │  └──────────────────────────────────────────────────────────┘  │
    └──────────────────────────────────────────────────────────────┘
```

| # | Boundary | Separates | Enforced by | Status |
|---|---|---|---|---|
| 1 | **Process** | Agent from guard | The guard is a separate OS process | **NOT IMPLEMENTED** |
| 2 | **OS identity** | Agent's account from the guard's | A service identity with its own ACLs | **NOT IMPLEMENTED** |
| 3 | **Store ACL** | Agent's account from the guard's files | NTFS ACLs on the store directory | **NOT IMPLEMENTED** |
| 4 | **Physical** | Agent from the human | The author's phone, which the agent cannot reach | Protocol implemented; **phone NOT IMPLEMENTED** |

**Only boundary 4 is enforced by something the agent genuinely cannot
reach.** The other three are enforced by the Windows service, which does
not exist yet.

---

## 2. Why the in-process design fails

The Quality Guardian today runs as a Hermes plugin — inside the agent's
own process, with the agent's own credentials, in the agent's own
session.

**VERIFIED_FACT:** `quality_guardian/hook.py` registers `post_tool_call`
and `pre_verify` handlers; `quality_guardian/guardian.py` runs the cycle
in-process; the Guardian's own tree is excluded from change detection.

Three consequences, each independently fatal:

1. **The agent can read the Guardian's configuration.** The policy that
   says what may be repaired is a file the agent can read — and, if it is
   the agent's account that owns it, write.
2. **The agent runs with the Guardian's credentials.** Whatever the
   Guardian can write, the agent can write, because they are the same
   principal.
3. **A crash in the agent takes the Guardian with it**, and there is no
   independent record of what was decided.

This is why `core/deployment.py` exists and why `InProcessDeployment`
declares `provides_boundary = False`. A deployment that *claims* a
boundary it does not provide is worse than one that admits it has none,
because the claim changes how everything else is written.

---

## 3. Boundary 1 — process separation

**Requirement.** The guard must not be inside the agent's process.

**Shape.** A Windows service (or a service-hosted process) hosting
`consequence_map.core.guard.SecurityGuard`, reachable over a named pipe.

**What the agent may do.** Send a request over the pipe and receive a
decision.

**What the agent may not do.** Load the guard's code into its own
process, replace its transport, or observe its memory.

**The rule that matters.** The agent must not be able to supply the
answer. `GuardDeployment.decide` takes the answer from the transport and
validates it; it never falls back to a local computation.

**Status: NOT IMPLEMENTED.** Installing a service requires
authorisation this session does not have.

---

## 4. Boundary 2 — OS identity

**Requirement.** The guard must not run as the agent's account.

**Shape.** A dedicated service identity (for example
`NT SERVICE\ConsequenceMapGuard`), with:

| Property | Requirement |
|---|---|
| Logon | Service account, **not** an interactive login |
| Privilege | The **minimum** for the job — no LocalSystem, no administrator |
| Session | Session 0 (services), **not** the interactive session |
| Group membership | Only what the job needs |

**VERIFIED_FACT:** the agent's account `Utente` is a standard account.
**VERIFIED_FACT:** the other four local accounts are disabled.

**Why not LocalSystem.** LocalSystem can do everything, including
everything an administrator can do. A guard that can rewrite its own
policy, replace its own trust anchor and delete its own audit store is
not a guard. The service should have the *least* privilege that still
does its job.

**UAC is not this boundary.** **VERIFIED_FACT:** `EnableLUA=1`,
`PromptOnSecureDesktop=1`, `ConsentPromptBehaviorAdmin=5`. An elevation
prompt appears — but the agent can **click it**, because it has
`computer_use` and it runs in the interactive session. UAC therefore
protects against *other* malware and against *accidental* elevation, and
protects against **nothing** here.

**Status: NOT IMPLEMENTED.**

---

## 5. Boundary 3 — store ACL

**Requirement.** The agent's account must not be able to write the
guard's files.

**The four stores.**

| Store | Contents | If the agent can write it |
|---|---|---|
| **Trust anchor** | The author's public key, the revocation list | It can authorise itself — **the boundary is gone** |
| **Verifier / policy** | The public key material and the policy | It can widen its own limits |
| **Approval store** | The signed approvals | It can forge one — the audit trail then shows a legitimate history |
| **Audit store** | The hash-chained records | It can erase the evidence |

**Shape.** A directory, e.g. `C:\ProgramData\ConsequenceMap\guard\`, with
an ACL granting **write** only to the service identity and the
Administrators group, and **read** to the agent's account where the
agent genuinely needs to see the anchor.

**Read vs write.** Read access to the public key is fine — it is public
by definition. Write access is fatal.

**VERIFIED_FACT:** the audit trail is a hash chain
(`core/audit.py`), so a rewrite that does not recompute every hash is
**detected**. It does not prevent one that does. The chain is the
*evidence*; the ACL is the *prevention*.

**Status: NOT IMPLEMENTED.**

---

## 6. Boundary 4 — physical separation

**Requirement.** The human's approval must be produced by something the
agent cannot reach.

**VERIFIED_FACT — why nothing on this machine qualifies:**

| Candidate | Why it fails |
|---|---|
| A desktop dialog | The agent has `computer_use` and runs in the same session. It can click it. |
| A Windows Hello prompt | Not provisioned (`WillNotProvision`); needs TPM 2.0, this host has 1.2 |
| A smart card | No reader; `scard.exe` absent |
| A FIDO2 key | No device attached |
| A password prompt | `PasswordRequired=False` — not a secret factor |
| The OS signing API | CNG returns `NTE_NOT_SUPPORTED` for every asymmetric algorithm; CryptoAPI fails too |

**The only viable channel is the author's phone.**

**Shape.** The phone holds a non-exportable key (Android Keystore,
ideally hardware-backed; iOS Secure Enclave, always). It shows the
**full** proposal — every resource, the permissions, the consequence
summary — and signs the canonical bytes only after biometric or PIN.

**What crosses the boundary.** The proposal (in full), the request
metadata, and the resulting signature. Nothing else.

**What the agent receives.** The signature and the public key. It
learns nothing about the phone's key material, because there is none to
learn.

**Status: the protocol is implemented and tested**; the phone
application is **NOT IMPLEMENTED**. The design is in
`../mobile-auth/`.

---

## 7. What each component may do

| Component | May | May not |
|---|---|---|
| **Agent** | Propose an operation; request authorization; ask the guard to decide; read a decision | Verify an authorization; write any store; choose the policy; name an operation off the allowlist; declare anything approved |
| **Core** | Validate, canonicalise, decide within the protocol | Reach the network; reach the stores; hold credentials |
| **Guard** | Verify; consult its stores; decide; execute; record | Trust the agent's word about anything; answer when it cannot reach its own store |
| **Phone** | Display the proposal; sign it after human action | Sign without human action; sign a different proposal; export its key |
| **Executor** | Run an allowlisted operation under a valid authorization | Run anything else; accept a command string; trust a caller's claim that authorization was checked |

---

## 8. The trust chain, end to end

```
agent proposes ──▶ canonical bytes ──▶ SHA-256 ──▶ proposal_hash
                                                      │
                                    shown in full on the phone
                                                      │
                                          human reads it, authenticates
                                                      │
                                        phone signs the canonical bytes
                                                      │
                                         signature + proposal_hash
                                                      │
agent asks the guard ──▶ guard recomputes the hash itself  ◀── the agent's
                           recomputes from the proposal        hash is NOT
                           checks the signature                 trusted
                           checks expiry, revocation, scope
                           checks the operation is allowlisted
                           checks the arguments carry no command
                                                      │
                                              ALLOW / DENY /
                                          INDETERMINATE
                                                      │
                                        executor runs it, and
                                        re-verifies first
```

**The load-bearing property:** the agent supplies *what* is being
proposed. It does not supply *whether it was approved*. Every step
after the proposal is recomputed by something the agent does not control.

---

## 9. Open questions for the owner

1. **Service identity.** Which account? Creating one needs authorisation.
2. **Store location.** `C:\ProgramData\ConsequenceMap\guard\` — does the
   desired ACL model fit the machine's policy?
3. **Agent read access.** Should the agent be able to *read* the trust
   anchor? (It should be able to read the public key; it should not be
   able to write the directory at all.)
4. **Validity window.** How long may an approval live? This trades
   against the replay window within one valid request.
5. **Recovery.** If the phone is lost, what happens to the trust anchor
   and to approvals already signed by it?
