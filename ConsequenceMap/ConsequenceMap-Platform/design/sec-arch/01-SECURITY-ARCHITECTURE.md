# Security Architecture

**Status:** DESIGN. The protocol layer is implemented and tested; the
enforcement environment is not.

---

## 1. The principle

> **The agent may propose. The platform may evaluate. The authorisation
> is independent. The executor permits only what satisfies every
> verifiable condition.**

Four parties, four jobs, and no party may do another's job:

| Party | Job | May not |
|---|---|---|
| **Agent** | Propose | Authorise, evaluate, execute |
| **Core** | Canonicalise, validate, analyse | Reach the network, hold credentials, decide security |
| **Guard** | Evaluate, verify, decide, execute, record | Trust the agent's word about anything |
| **Human** | Authorise | — |
| **Executor** | Run an allowlisted operation | Run anything else |

---

## 2. The architecture

```
   ┌─ AGENT (untrusted) ──────────────────────────────────────┐
   │  Hermes runtime · user's account · session 1 ·            │
   │  computer_use can click the desktop                       │
   │                                                           │
   │   AgentSurface  (core/agent.py)                           │
   │     propose()  decide()  status()                         │
   │        three calls. that is all.                          │
   └───────────────┬───────────────────────────────────────────┘
                   │ authenticated pipe (to be implemented)
   ┌───────────────┴─ SECURITY GUARD (trusted service) ───────┐
   │  SecurityGuard  (core/guard.py)                           │
   │    six checks, fixed order, all recorded                  │
   │    ALLOW · DENY · INDETERMINATE                           │
   │                                                           │
   │  verifier ── trust anchor ── revocation list              │
   │  policy ── approval store ── audit log (hash chain)      │
   │                                                           │
   │  ExecutionEngine  (core/execution.py)                     │
   │    allowlist · transition table · no command strings      │
   └───────────────┬───────────────────────────────────────────┘
                   │ approval request (full proposal)
   ┌───────────────┴─ AUTHOR'S PHONE (independent) ──────────┐
   │  shows the real operation · biometric or PIN · signs      │
   │  key in secure hardware, never exported                   │
   └───────────────────────────────────────────────────────────┘
```

---

## 3. The six modules

| Module | Responsibility | Depends on |
|---|---|---|
| `core/canonical.py` | The one canonical form; ASCII-only, length-prefixed, domain-separated | stdlib only |
| `core/authorization.py` | The approval protocol; nine mandatory checks | `canonical`, `timeutil` |
| `core/timeutil.py` | Strict RFC 3339 UTC millisecond timestamps | stdlib only |
| `core/execution.py` | The allowlist, the transition table, the executor | `authorization` |
| `core/audit.py` | The hash-chained audit trail | `canonical`, `timeutil` |
| `core/guard.py` | The decision logic; the six checks; ALLOW/DENY/INDETERMINATE | `authorization`, `execution`, `audit` |
| `core/analysis.py` | Claim classification; forecast qualification | stdlib only |
| `core/agent.py` | The narrow surface an agent gets | `guard`, `authorization` |
| `core/deployment.py` | The deployment contract; fail-closed transport | `guard` |

**Every module is pure.** No I/O, no network, no credentials. That is
what makes them testable, and testable is what makes them trustworthy.

---

## 4. The decision

The guard's six checks, in order. The first failure decides, and the
reason names it:

| # | Check | Fails when |
|---|---|---|
| 1 | `operation_on_allowlist` | The operation is not registered. **Default deny** |
| 2 | `proposal_canonicalisable` | The proposal cannot be canonicalised — so it cannot be bound |
| 3 | `authorization_valid` | The authorization does not hold, against the guard's **own** verifier and revocation list |
| 4 | `scope_granted` | The authorization does not grant the operation's scope |
| 5 | `no_command_arguments` | An argument is named `command`, `cmd`, `shell`, `script` or `argv` |
| 6 | `state_transition_permitted` | The state machine refuses the transition |

**Three decisions, never collapsed:**

| | |
|---|---|
| `ALLOW` | Every condition held |
| `DENY` | A condition failed |
| `INDETERMINATE` | A condition could not be evaluated — **never** folded into ALLOW |

`INDETERMINATE` is the whole point. The incident audit's central finding
was that a failed verification could be rendered as a warning and the
operation could continue. This design has a name for that state and
cannot express it as an approval.

---

## 5. What the agent may do

Three calls, and nothing else:

| Call | What it does | What it may not do |
|---|---|---|
| `propose(raw)` | Turns a payload into an authorization request | Choose the operation's scope, the expiry's length, or anything off the allowlist |
| `decide(...)` | Asks the guard | Supply the decision, or the evidence for it |
| `status()` | Lists the allowlist | Learn anything about the verifier, the revocation list, the policy, or a key |

**The agent never verifies an authorization.** The guard's verifier is
not the agent's to reach. The agent's statement that "the approval was
checked" is not evidence and is not used.

---

## 6. The failure modes, and what happens in each

| Failure | Behaviour |
|---|---|
| The guard is unreachable | `GuardUnavailable` — a **refusal**. No cache, no fallback, no last-known-good |
| The authorization is forged | `DENY`, reason names the check |
| The proposal was changed | `DENY` — the hash is recomputed, not trusted |
| An old authorization is replayed against a new request | `DENY` — the nonce differs |
| The same authorization is executed twice | `DENY` — the executor's spent-authorization set; an approval is good for one execution |
| The key was revoked | `DENY` |
| The authorization expired | `DENY` |
| The operation is off the allowlist | `DENY` — default deny |
| The arguments carry a command | `DENY` |
| The policy says the operation is safe | **irrelevant** — consequence analysis is not authorisation |

**The last row is the one the mission brief singles out**, and it is
enforced structurally: the policy is not an input to the decision. The
guard consults the authorization, the scope, the allowlist and the
integrity of the proposal. A consequence analysis that says "this is
fine" has no path into the decision.

---

## 7. What is implemented

| | Status |
|---|---|
| Canonical form, hashing, binding | **IMPLEMENTED, TESTED** |
| Approval protocol (9 checks) | **IMPLEMENTED, TESTED** — 36 tests |
| Execution engine (allowlist, states, no commands) | **IMPLEMENTED, TESTED** — 18 tests |
| Guard decision logic (6 checks, 3 decisions) | **IMPLEMENTED, TESTED** — 19 tests |
| Audit trail (hash chain) | **IMPLEMENTED, TESTED** — 16 tests |
| Consequence intelligence policy | **IMPLEMENTED, TESTED** — 21 tests |
| Agent surface + Hermes adapter | **IMPLEMENTED, TESTED** — 14 tests |
| Deployment contract (fail-closed) | **IMPLEMENTED, TESTED** — 12 tests |
| Phone protocol + demonstration | **IMPLEMENTED, VERIFIED** — 11 cases, exit 0 |
| **Windows service deployment** | **NOT IMPLEMENTED** |
| **Phone applications** | **NOT IMPLEMENTED** |
| **Real signature algorithm** | **NOT IMPLEMENTED** |
| **Trusted clock** | **NOT IMPLEMENTED** |
| **Store ACLs** | **NOT IMPLEMENTED** |

**136 new tests; the package suite is 350 passing (baseline 214).**

---

## 8. The honest position

The **protocol** is done and tested. The **enforcement** is not.

Everything that makes the guard a boundary rather than a function —
the separate process, the separate identity, the store ACLs — depends on
a Windows service that does not exist, and installing one needs
authorisation this session does not have.

**The platform is not ready for production.** The threat model says so
in a table, threat by threat, and this document does not soften it.
