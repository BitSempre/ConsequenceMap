# Threat Model — ConsequenceMap Platform v1

**Status:** DESIGN. Nothing in this document is implemented unless the
implementation status says otherwise.
**Method:** STRIDE, applied to the trust boundaries in
`03-TRUST-BOUNDARIES.md`.
**Environment facts:** measured read-only on 2026-11-09 (see §5).

Every claim carries a class: **VERIFIED_FACT** (measured or read in the
code), **INFERENCE** (reasoned from verified facts), **UNKNOWN** (cannot
be determined with what is available).

---

## 1. The threat model in one paragraph

The attacker is the AI agent itself, running with the user's own Windows
credentials in the user's own interactive session, with the ability to
click on the user's desktop. The agent is not trying to break the
platform from outside — it is trying to get a destructive operation
approved without a human actually deciding. Everything below follows
from that.

---

## 2. Scope

### In scope

| | |
|---|---|
| **The agent** | Honest-but-compromised, or adversarially instructed by a prompt injection. Has the user's credentials and desktop access. |
| **A prompt injection** | Third-party content that reaches the agent's context and tries to induce an operation. |
| **A local standard user** | Another account on the machine. No administrative rights. |
| **A stolen phone** | The author's device, without the PIN or biometry. |
| **The audit store** | Tampered by anything with write access to it. |

### Out of scope, stated plainly

> **An attacker with total administrative control of the Windows machine is
> out of scope.** That attacker can read the trust anchor, replace the
> verifier, patch the guard, rewrite the audit store, and install a
> keylogger. No design in this document prevents that, and none claims to.

The boundary is **the administrative account**. Everything below is
about what a non-administrative agent can do on a machine whose owner is
present and watching.

**The owner's own account, deliberately used by the owner to authorise
an operation, is also not the adversary.** The platform's job is to
ensure that *only* such a deliberate act produces an approval.

---

## 3. Assets

| Asset | Why it matters |
|---|---|
| The ability to execute a destructive operation | The thing being protected |
| The trust anchor (public key + revocation list) | Its compromise ends every guarantee |
| The approval store | Its integrity is what "a human approved this" means |
| The audit trail | The evidence that any of the above was legitimate |
| The policy | Defines what may happen at all |
| The consequence forecast | What the human is asked to approve |

---

## 4. Threats

Severity reflects impact **and** likelihood in this environment.

### T-01 — The agent fabricates an approval

| | |
|---|---|
| **STRIDE** | Spoofing / Elevation of privilege |
| **Attacker capability** | Full — the agent writes files and runs code as the user |
| **Preconditions** | None |
| **Impact** | Arbitrary operation executed without a human |
| **Likelihood** | **High** — this is the default failure mode if the platform is naive |
| **Mitigation** | An approval is a **signature over the digest of a proposal**. Producing one requires the private key, which lives on the author's phone and is used only after the human's biometric or PIN check. The guard verifies the signature against a trust anchor the agent cannot write. |
| **Residual risk** | If the agent can reach the phone's signing operation (impossible in the design — the phone is a separate device), it can sign. |
| **Test** | `test_authorization.py::test_t04_a_forged_signature_is_rejected`, `::test_t04_a_forged_signature_from_a_different_key_is_rejected` — **PASS** |
| **Status** | Protocol implemented and tested. The signer itself is a pluggable interface; the phone implementation is **NOT implemented**. |

### T-02 — The agent replays an earlier approval

| | |
|---|---|
| **STRIDE** | Spoofing / Replay |
| **Impact** | An operation the human approved once is approved again, without a new decision |
| **Likelihood** | High without a nonce; low with one |
| **Mitigation** | Every request carries a fresh 256-bit nonce. The authorization must carry the **same** nonce. The proposal must also hash to the same value. A replay against a new request fails the nonce check. A replay against the same request is refused by the executor's **spent-authorization set**: an approval is good for **one** execution. |
| **Residual risk** | The spent set must be **durable and shared** across processes. An engine that forgets it on restart would let a captured authorization be replayed after a reboot. The validity window must also be short — it is the exposure window for a captured authorization that has not yet been spent. |
| **Test** | `test_authorization.py::test_t05_a_replayed_authorization_against_a_new_request_is_rejected`, `::test_t05_a_replayed_authorization_over_the_same_proposal_is_rejected` — **PASS** |
| **Status** | Implemented and tested. |

### T-03 — The agent modifies the proposal after approval

| | |
|---|---|
| **STRIDE** | Tampering / Elevation of privilege |
| **Impact** | The human approves "delete one report"; the agent deletes the repository |
| **Likelihood** | **High** — this is the attack the previous design missed |
| **Mitigation** | The authorization is bound to the **recomputed** canonical hash of the proposal, not to a hash carried in the request. The verifier recomputes it from the proposal itself. Any change to any field changes the hash and the authorization no longer applies. |
| **Residual risk** | None identified, provided the canonical form is unambiguous. It is: ASCII-only, length-prefixed, duplicate-key-rejecting. |
| **Test** | `test_authorization.py::test_t06_a_proposal_changed_after_approval_is_rejected`, `::test_t06_a_resource_added_after_approval_is_rejected`, `::test_t06_a_permission_widened_after_approval_is_rejected` — **PASS** |
| **Status** | Implemented and tested. |

### T-04 — The agent clicks its own consent prompt

| | |
|---|---|
| **STRIDE** | Spoofing / Elevation of privilege |
| **Impact** | A desktop confirmation is worthless: the agent produces it and clicks it |
| **Likelihood** | **Certain**, if the design relies on the desktop |
| **Measured facts** | The Hermes agent runs in **session 1 (`console`, Active)** as the same user. The `computer_use` tool (cua-driver) can **click and type on the user's desktop** with background delivery. The account has `PasswordRequired=False`, so a password prompt is not a secret factor. **Windows Hello is not provisioned** (`PreReqResult: WillNotProvision`); **TPM is 1.2, not 2.0**; no smart card, no FIDO2, no CNG keys. |
| **Mitigation** | The human-presence channel must be a device the agent cannot reach: the **author's phone**. The phone shows the real content and signs only after biometric or PIN. The desktop is used to *display* the request, never to *authorise* it. |
| **Residual risk** | The agent can still show a **fake** request on the desktop, trying to make the owner approve on the phone something else. Mitigated by the approval binding: the phone displays the proposal's own hash and the operation, and the approval only applies to exactly that proposal. The owner still has to notice a mismatch between the desktop prompt and the phone. **This is a UI-honesty risk, not a cryptographic one** — and it is why the phone UI must show the full operation, not a summary. |
| **Test** | `test_authorization.py` — the binding tests. The `computer_use` vector itself is **NOT automatically testable**: it requires a running desktop and a human to not intervene. It is covered by design review, not by a test. |
| **Status** | The protocol side is implemented. The phone side is **NOT implemented**. |

### T-05 — The agent alters the policy

| | |
|---|---|
| **STRIDE** | Tampering |
| **Impact** | The agent raises its own limits |
| **Likelihood** | High if the policy is in the agent's reach |
| **Mitigation** | The policy lives with the guard's store, which the agent's account cannot write (deployment requirement, §6). The guard records the policy version on every decision. The agent may **ask**; it may not **choose**. |
| **Residual risk** | An in-process deployment cannot enforce this — which is why `InProcessDeployment` declares `provides_boundary = False` and refuses to pretend otherwise. |
| **Test** | `test_deployment.py::test_the_in_process_deployment_admits_it_has_no_boundary` — **PASS**. The separation itself is a **deployment** property and needs a real service to test; **NOT IMPLEMENTED**. |
| **Status** | Contract implemented. Enforcement requires the Windows service — **NOT IMPLEMENTED**. |

### T-06 — The agent escalates its own privileges

| | |
|---|---|
| **STRIDE** | Elevation of privilege |
| **Impact** | The agent becomes administrator and then defeats every other control |
| **Likelihood** | Depends on the deployment |
| **Measured facts** | The Hermes agent's account `Utente` is a **standard** account (not in the Administrators group). `EnableLUA=1`, `PromptOnSecureDesktop=1`, `ConsentPromptBehaviorUser=3`. The only accounts on the machine are `Administrator`, `DefaultAccount`, `Guest` and `WDAGUtilityAccount` — all **disabled** — plus `Utente`. |
| **Mitigation** | The guard runs under a **service identity** with its own ACLs; the agent's account has no write access to the guard's store, its trust anchor or its audit store. The agent's standard account cannot touch the service's resources. |
| **Residual risk** | **UAC is not a boundary.** `ConsentPromptBehaviorAdmin=5` means an elevation prompt appears, but the agent would have to click it — and it *can* click it (`computer_use`). UAC therefore provides **no** protection against the agent. The protection must come from the service identity's ACLs, not from UAC. |
| **Test** | **NOT_TESTED** — requires the service to exist. |
| **Status** | **NOT IMPLEMENTED.** |

### T-07 — A local standard user tampers with the stores

| | |
|---|---|
| **STRIDE** | Tampering |
| **Impact** | A user-level attacker rewrites the approval store or the audit log |
| **Likelihood** | Low but non-trivial (any local malware runs as some user) |
| **Mitigation** | The stores live in a directory whose ACL grants write access only to the service identity and the Administrators group. The audit trail is a **hash chain**, so a rewrite that does not recompute every hash is **detected**. |
| **Residual risk** | A wholesale rewrite with recomputed hashes is **not** detected by the chain alone. The chain is **detection, not prevention** — the prevention is the ACL. This is stated in `core/audit.py`'s docstring rather than glossed over. |
| **Test** | `test_audit.py` — 16 tests covering altered payload, event, timestamp, removed, inserted, reordered — **PASS**. ACL enforcement: **NOT_TESTED**. |
| **Status** | Chain implemented and tested. ACLs require the service — **NOT IMPLEMENTED**. |

### T-08 — The clock is moved to defeat expiry

| | |
|---|---|
| **STRIDE** | Repudiation / Tampering |
| **Impact** | An expired approval is accepted because the machine thinks it is still valid |
| **Likelihood** | Low (requires administrative rights, which is out of scope) — but a user-level attacker may be able to set the time on some configurations |
| **Mitigation** | The guard uses a **trusted time source**, not the agent's clock. The expiration is checked twice: at request time and at execution time, and the executor re-verifies. |
| **Residual risk** | Without a trusted time source, a clock change inside the validity window cannot be detected. The honest mitigation is a **short validity window** plus the guard's own clock. |
| **Test** | `test_authorization.py::test_t08_an_expired_authorization_is_rejected`, `::test_t08_an_authorization_not_yet_valid_is_rejected` — **PASS**. A trusted time source is **NOT IMPLEMENTED**. |
| **Status** | Expiry logic implemented and tested. Trusted time — **NOT IMPLEMENTED**. |

### T-09 — The agent supplies a malformed proposal

| | |
|---|---|
| **STRIDE** | Tampering / Denial of service |
| **Impact** | A malformed proposal is accepted, or crashes the guard |
| **Likelihood** | High — the agent controls the input |
| **Mitigation** | The canonical form **rejects** duplicate keys, floats, non-ASCII text and unknown types. The authorization checks every mandatory field. The guard catches `CanonicalisationError` and refuses. The executor refuses arguments that are not a mapping and refuses any argument named `command`, `cmd`, `shell`, `script` or `argv`. |
| **Residual risk** | Resource exhaustion: a proposal with an enormous payload. **Mitigation not yet implemented** — a maximum size on the proposal is required. |
| **Test** | `test_canonicalisation` and `test_guard.py::test_t01_a_non_canonicalisable_proposal_is_denied` — **PASS**. Size limit: **NOT_TESTED**. |
| **Status** | Partially implemented. The size limit is **missing**. |

### T-10 — A module accepts an invalid state from another module

| | |
|---|---|
| **STRIDE** | Tampering |
| **Impact** | A state that should be unreachable is reached, skipping a check |
| **Likelihood** | Medium — an internal programming error is enough |
| **Mitigation** | The execution engine has an **explicit transition table**. Terminal states (`REJECTED`, `BLOCKED`, `EXECUTED`, `FAILED`, `EXPIRED`, `REVOKED`) have **no outgoing transitions**. A transition not in the table is refused. The guard checks the transition explicitly. |
| **Residual risk** | The state lives in memory in the current deployment; a crash loses it. The database layer's triggers cover the persisted records (`host_authorization_immutable_after_resolve`, `no_update`, `no_delete`). |
| **Test** | `test_execution.py::test_t22_an_undeclared_transition_is_refused`, `::test_t22_terminal_states_have_no_outgoing_transitions` — **PASS** |
| **Status** | Implemented and tested. |

### T-11 — The guard is unavailable and the agent proceeds anyway

| | |
|---|---|
| **STRIDE** | Denial of service → elevation of privilege |
| **Impact** | The agent executes because the guard could not be reached |
| **Likelihood** | High — an attacker can stop the service if it is a standard-user service |
| **Mitigation** | `GuardDeployment.decide` raises `GuardUnavailable` when the guard cannot be reached. There is **no fallback that approves**: no local cache of last-known-good decisions, no in-process substitute. The refusal is a `DENY` with a reason, not an absence. |
| **Residual risk** | The agent can **deny service** by stopping the service. That is the correct trade: availability is sacrificed for the guarantee that an unreachable guard never means an approved operation. |
| **Test** | `test_deployment.py::test_t11_an_unreachable_guard_raises_rather_than_approving`, `::test_t11_a_guard_with_no_transport_raises`, `::test_t11_the_refusal_is_a_denial_with_a_reason` — **PASS** |
| **Status** | Implemented and tested. |

### T-12 — The agent submits a proposal whose display hides the real operation

| | |
|---|---|
| **STRIDE** | Spoofing / Repudiation |
| **Impact** | The human approves a benign-looking screen while the operation does something else |
| **Likelihood** | Medium — this needs a crafted proposal, not just a malicious agent |
| **Mitigation** | The phone must display the **full** proposal — every affected resource, the requested permissions, and the consequence summary — and the approval must be bound to its hash. The hash covers the whole proposal, so a benign *display* with a different *content* cannot be approved: what the human reads must be what was hashed. |
| **Residual risk** | A proposal can be **long**, and a human may skim. The mitigation is presentation, not cryptography: the UI must not truncate without saying so, and must show a resource count. |
| **Test** | The binding tests cover the cryptographic half — **PASS**. The UI half is **NOT IMPLEMENTED**. |
| **Status** | Protocol side implemented. UI side **NOT IMPLEMENTED**. |

---

## 5. Measured environment facts

All **VERIFIED_FACT**, measured read-only on 2026-11-09.

| Fact | Value | Consequence |
|---|---|---|
| OS | Windows 11 Pro, build 22000 | — |
| Hardware | ASUS P553UJ, i5-6200U, 8 GB | — |
| Domain | WORKGROUP, not joined | No AD-based identity; no central revocation |
| TPM | **1.2** (`ACPI\PNP0C31`), driver RUNNING | Windows Hello, Passport and Platform Crypto Provider all need **2.0** |
| Windows Hello | `NgcSet: NO`, `PreReqResult: WillNotProvision`, 0 keys | No biometric or PIN gate |
| Smart card / FIDO2 / CNG keys | none / none / none | No hardware key available |
| Agent's session | **1**, `console`, Active, same user | The agent is inside the interactive session |
| `computer_use` | clicks and types on the desktop, background delivery | **Any desktop prompt is clickable by the agent** |
| `PasswordRequired` | `False` | A password prompt is not a secret factor |
| UAC | `EnableLUA=1`, `PromptOnSecureDesktop=1` | Admin prompts are on the secure desktop — but the agent does not need elevation to be dangerous |
| Accounts | only `Utente` active; the other four disabled | A single-user machine |
| OS signing providers | CNG returns `NTE_NOT_SUPPORTED` for every asymmetric algorithm; CryptoAPI `CryptAcquireContextW` returns `NTE_BAD_KEYSET` | **No OS signing provider exists here** — the phone must sign |

---

## 6. The five threats that decide the design

1. **T-04** — the agent can click the desktop. This single fact eliminates
   every desktop-based approval and makes the phone mandatory.
2. **T-01** + **T-03** — approval must be a signature over a *recomputed*
   hash. This is the difference between the previous design and this one.
3. **T-11** — an unreachable guard must refuse. Any fallback that approves
   silently removes the boundary.
4. **T-06** — UAC is not a boundary against this agent. Separation must
   come from a service identity's ACLs.
5. **T-07** — the hash chain detects rewriting but does not prevent it.
   Prevention is the ACL; the chain is the evidence.

---

## 7. What is implemented, and what is not

| Threat | Protocol / logic | Enforcement environment |
|---|---|---|
| T-01 | **Implemented, tested** | Phone signer **NOT IMPLEMENTED** |
| T-02 | **Implemented, tested** | — |
| T-03 | **Implemented, tested** | — |
| T-04 | Binding **implemented, tested** | Phone **NOT IMPLEMENTED**; desktop is unusable as a gate |
| T-05 | Contract **implemented** | Windows service **NOT IMPLEMENTED** |
| T-06 | — | Windows service **NOT IMPLEMENTED** |
| T-07 | Chain **implemented, tested** | ACLs **NOT IMPLEMENTED** |
| T-08 | Expiry **implemented, tested** | Trusted time **NOT IMPLEMENTED** |
| T-09 | Mostly **implemented, tested** | Size limit **MISSING** |
| T-10 | **Implemented, tested** | — |
| T-11 | **Implemented, tested** | — |
| T-12 | Binding **implemented** | UI **NOT IMPLEMENTED** |

**The honest summary:** the cryptographic protocol is implemented and
tested. **Every enforcement boundary that depends on the Windows service,
the phone, or a trusted clock is not.** The platform is not ready for
production, and this table is why.

---

## 8. Defects found by probing our own implementation

A threat model written by the same people who wrote the code is a
statement of intent. The four defects below were found by **writing
probes against the implementation** — attempts to break it — rather
than by reading it. They are recorded here because they are the honest
measure of how much the design documents missed.

| ID | Defect | Exploit | Fix |
|---|---|---|---|
| **D-1** | A scope given as a **string** was accepted. `set("files:write")` is nine single-character scopes, and a subset comparison could succeed on one shared character | A scope comparison could authorise something it was not asked to authorise | A scope is now rejected unless it is a list of strings — checked at construction, at verification, and at the agent surface |
| **D-2** | The canonical form had **no depth limit**. A 500-level document encoded without complaint | Resource exhaustion against the verifier; the phone has far less memory than the PC | A limit of 32 levels |
| **D-3** | `AgentRequest` coerced the scope with `list()` **before** any validation | The string became a character list before the check could see it | The type is checked before anything is coerced |
| **D-4** | The audit chain could be **truncated** and still verify — a prefix is itself a consistent chain | Records could be removed from the end of the history without detection | `verify_chain` now accepts an external anchor (`expected_head` / `expected_length`) and detects it |

**D-4 is the interesting one.** It is not a bug in the hash chain — the
chain is doing exactly what a hash chain does. It is a gap in what a
hash chain can do at all, and the fix is the anchor: the head hash,
recorded somewhere the agent cannot write. Without an anchor,
truncation is undetectable, and the documentation now says so instead of
implying coverage it does not have.

**The lesson.** Four defects in roughly 2 300 lines of new security code,
found in one probing session by an adversary working from the outside.
Reading the code did not find them; attacking it did. **Every future
change to this core should be probed the same way before it is
committed.**

Pinned by `test_regressions.py` — 15 tests, one per behaviour.

### 8.1 The second probing round

A second round of probes — 40 attempts across the canonical form, the
authorization protocol, the executor, the guard, the agent surface, the
analysis layer, the audit log and the deployment contract — found **six
more defects**, almost all of them about **input validation at the
edges**:

| ID | Defect | Exploit | Fix |
|---|---|---|---|
| **D-5** | The request's own copy of the proposal was never compared with the proposal being verified | The request could display one proposal and be verified against another | The two are compared; a mismatch is `AuthorizationInvalid` |
| **D-6** | A request or authorization could carry an **unparseable timestamp** | Accepted at construction, rejected at verification — and in between, a request the agent could hold open | Both window endpoints are parsed at construction |
| **D-7** | The agent adapter **ignored unknown fields** | A field the platform does not understand might be one it would have honoured | The schema is closed; an unknown field is refused |
| **D-8** | A **command-shaped argument** was only refused further down the chain | The request was built before anything objected | Refused at the agent's own boundary |
| **D-9** | `qualify_forecast` accepted a **dict where a list** was expected | `len(dict)` worked, and the forecast qualified | The collections must be collections |
| **D-10** | The audit log accepted an event name containing a **newline** | A crafted event could forge the appearance of two records in a log a human reads | Event names are one line, with no control characters |

**Together with the first round: ten defects in roughly 2 400 lines of
new security code, found by attacking it rather than reading it.**

**The pattern is consistent.** Nine of the ten were at an **input
boundary**, and every one of them was a case where a value was accepted
in a shape it should not have been. That is a design lesson for the
next module: *validate at the edge, and reject rather than coerce.*

Pinned by `test_regressions.py` and `test_regressions_round2.py` — 29
tests, one per behaviour.

### 8.2 The third probing round

A third round — 25 probes against the canonical form, the analysis
layer and the time parser, the areas the first two rounds did not
touch — found **two more defects**:

| ID | Defect | Exploit | Fix |
|---|---|---|---|
| **D-11** | Map **keys** were held to a different rule from map **values**. A value had to be ASCII; a key did not | The canonical form stopped being the byte sequence it promises. Worse, it opened a normalisation trap: the same key written in composed form (`é`) or decomposed form (`e` + combining accent) is two different byte strings that display the same, so **two logically identical documents could hash to two different values** | A key is now held to the same ASCII rule as a value |
| **D-12** | `qualify_forecast` only tested the confidence against `NONE`. Any other label passed through | An invented confidence label would be shown to the **human who is about to authorise the operation** | The confidence must be one the platform defines |

**D-11 is the more serious one.** The whole point of a canonical form is
that one logical document has exactly one byte representation. A key
that can be written two ways breaks that promise at the root, and the
hash stops meaning "this document" — it starts meaning "this particular
spelling of this document".

**D-12 is the more embarrassing one.** The platform's own vocabulary was
not being enforced on the field the human reads last, immediately
before deciding.

### 8.3 The fourth round: an independent reviewer, and the defect the design had documented wrongly

The fourth round was run by an **independent reviewer** working from a
logic excerpt, with no access to the repository. It confirmed D-11 (the
non-ASCII key) independently - which had already been found and fixed
in round three - and then found the defect the three earlier rounds and
the design documents had all missed.

| ID | Defect | Exploit | Fix |
|---|---|---|---|
| **D-13** | There is **no store of spent nonces**. The `AuthorizationReplay` exception fired only when two nonces *differed*, not when one was reused | A captured (request, authorization) pair verified **five times in a row** | Documented as the deliberate residual risk it was meant to be — but see D-14, which is not acceptable |
| **D-14** | The executor held **no memory of what it had already spent**. Its state machine guards transitions, but the *state is supplied by the caller* | The same approval executed the handler **three times**: "approved once, executed three times" | `ConsumedAuthorizations` — the executor marks an authorization spent before the handler runs |

**D-14 is the one that matters, and the design had it backwards.**

The threat model said:

> An authorization replayed within its validity window against the
> identical request is accepted — by design, because that is the same
> operation, approved once, still valid.

That is true of the **authorization**. It was not true of the
**execution**. "Approved once" had become "executed three times",
because the executor trusted a caller-supplied state and kept no record
of its own.

The design was self-consistent and wrong. It documented a residual risk
it had actually designed away — and missed the one it had not.

**Why the independent review found what three internal rounds did
not:** the internal rounds tested the code against its own intent. The
reviewer, having only the *description*, tested the description itself.
When the description was wrong, only the outsider could see it.

### 8.4 The tally

**Twelve defects** in roughly 2 400 lines of new security code.

| Round | Probes | Defects | Theme |
|---|---|---|---|
| 1 | 11 | 4 | Scope typing, depth, coercion order, truncatable chain |
| 2 | 40 | 6 | Input validation at the edges |
| 3 | 25 | 2 | Canonical-form invariants, vocabulary enforcement |

**Eleven of the twelve were at a boundary**, and every one was a value
accepted in a shape it should not have been. The design lesson is now
written into the code: **validate at the edge, and reject rather than
coerce.**

Pinned by `test_regressions.py`, `test_regressions_round2.py` and
`test_regressions_round3.py` — 37 tests, one per behaviour.

### 8.6 The fifth round: the prototype, which had never been probed

Four rounds had attacked the **core**. The mobile prototype — the
reference implementation the phone applications are written against —
had only ever been *run*, never *attacked*. Probing it found two
defects, one of them the worst of the sixteen.

| ID | Defect | Exploit | Fix |
|---|---|---|---|
| **D-15** | `escape_tree` escaped values but **not keys** | The canonical form refuses a non-ASCII key, so the prototype could build a tree the canonicaliser rejected — and the phone and the PC would disagree about what was approved | Keys are escaped as well as values |
| **D-16** | The fields the phone **displays** — the affected resources and the consequence summary — lived **beside** the proposal rather than **inside** it | The proposal is what gets hashed and signed. Those fields were outside the hash and outside the signature. **An attacker could change what the phone showed without invalidating the approval** | The display fields are part of the proposal, so they are hashed and signed with it |

**D-16 is the worst of the sixteen, and it is a bypass of the entire
human-in-the-loop premise.**

The human approves what they see on the phone. The phone shows the
affected resources and the consequence summary. Those two fields were
not covered by the signature. The request still verified, because the
verifier only ever looked at the proposal — so an attacker could show
the human *“deletes one report”* and have *“deletes the repository”*
approved and executed, with a valid signature on the request.

The demonstration prototype had a case for this and called it a
"DESIGN OBLIGATION, not a bug": a *lying* summary still verifies,
because a signature cannot tell a human that the summary is untrue.
That was true — but it was the wrong thing to be worried about. The
problem was not that a lie could be *signed*. It was that the
displayed field could be *changed after* it was signed.

**What the fix does and does not do.** The display fields are now
inside the proposal, so they are covered by the hash and the signature.
They cannot be altered after the human approved them. A summary that
was a lie *at the moment of approval* still verifies — no signature can
prevent that — and the mitigation remains what it always was: the
phone renders the resources and the action verbatim, and does not ask
the human to trust a summary.

**The lesson.** The core had been attacked four times and the
prototype not once. The prototype is the *reference implementation* —
the thing the mobile applications are written against. A defect there
propagates to every phone.

**Probe what ships, not just what is hardest.**

### 8.7 The sixth round: where the agent is the adversary

The sixth round attacked the places where the **agent** is the
adversary: the surface it calls, the contract the guard transport
speaks, and the policy that bounds how long an approval stays usable.

| ID | Defect | Exploit | Fix |
|---|---|---|---|
| **D-17** | The guard transport could return a decision and an `allowed` flag that **disagreed** — `decision=DENY` with `allowed=True` | Both are part of the contract, and the agent's surface reads `allowed`. A transport could hand the agent a **denial dressed as a permission** | The two must agree; a contradiction is a contract violation. The agent's surface now derives `allowed` from the decision rather than copying it |
| **D-18** | **Nothing bounded how long an approval could stay open.** The exposure window for a captured authorization was whatever the requester asked for — the agent could ask for ten years | A captured approval stayed usable for as long as the agent had asked for | `MAX_VALIDITY_SECONDS` — a **policy parameter**, enforced at construction *and* re-checked at verification |

**D-17 is a reminder that a contract is more than its schema.** Closing
the schema — refusing unexpected fields — is not enough. Two fields
that are both *accepted* can still contradict each other, and the
consumer that reads the wrong one acts on the wrong thing.

**D-18 is a decision made by absence.** The right value for the maximum
validity window is question Q-5 in the residual-risk register, and it
belongs to the project owner: it balances the exposure of a captured
approval against the time a human needs to answer. The platform cannot
wait for that answer, and it must not accept an unbounded window while
it waits. So the policy is a **parameter** with a conservative default
(3600 s), enforced in code, and changed by configuration once the
owner decides.

### 8.8 The tally

**Eighteen defects** in roughly 2 500 lines of new security code.

| Round | Probes | Defects | Theme |
|---|---|---|---|
| 1 | 11 | 4 | Scope typing, depth, coercion order, truncatable chain |
| 2 | 40 | 6 | Input validation at the edges |
| 3 | 25 | 2 | Canonical-form invariants, vocabulary enforcement |
| 4 | independent review | 2 | **Single-use enforcement — a defect the design documented wrongly** |
| 5 | 18 (prototype) | 2 | **The displayed fields were outside the signature** |
| 6 | 21 (agent boundary) | 2 | **A contract whose fields could contradict each other; an unbounded validity window** |

**Fourteen of the eighteen were at a boundary**, and every one of them
was a value accepted in a shape it should not have been. Two were
structural — the absence of a rule (single-use, a validity bound) — and
one was a rule that was written down wrongly (the replay risk).

**What the rounds have in common is the target.** Every one of them
was a place where something *enters* the platform: an input, a
transport, a document, a phone screen. The defences are not in the
middle of the system. They are at the places where the system meets
someone who is not supposed to be trusted.

### 8.9 The seventh round: the audit trail's own integrity

The seventh round attacked the **audit log** and the **analysis layer**
- the two areas the earlier rounds had touched least.

| ID | Defect | Exploit | Fix |
|---|---|---|---|
| **D-19** | An `AuditRecord` was a **mutable object**, and `append` returned the live internal object | Anyone holding that reference could rewrite a record after the fact. The chain **did** detect the rewrite — but detection is not prevention | A record is now **immutable**: read-only fields, and a deep, read-only payload snapshot |

**D-19 is a property the audit trail was supposed to have and did not.**

The whole design rests on the chain detecting tampering. It does — the
probe confirmed the rewrite is caught. But a trail whose records can be
rewritten is not a trail: it is a *suggestion that something happened*.
If the attacker can rewrite a record, they can also rewrite it
**consistently**, and then the chain verifies perfectly.

That last case is the one the chain alone cannot catch, and it is why
the fix is immutability rather than another hash. The only way to change
the history is to build a *different* history, which produces a
different chain and a different head hash — and the head hash is
recorded outside the chain.

**The payload is frozen deeply.** A snapshot that only protected the
top level would not be a snapshot: `record.payload["nested"]["key"]`
would still be writable. The payload is a read-only mapping of
read-only mappings, and mutating the caller's own dictionary after the
append does not reach into the log.

**The analysis layer produced no defect.** Its checks — the
weakest-link confidence aggregation, the closed classification
vocabulary, the refusal to present an unverified claim as a fact, the
refusal to qualify a forecast that does not state its unknowns — all
held under probing. That is worth recording too: not every module has
a hole, and saying so is part of an honest report.

### 8.10 The tally

**Nineteen defects** in roughly 2 600 lines of new security code.

| Round | Probes | Defects | Theme |
|---|---|---|---|
| 1 | 11 | 4 | Scope typing, depth, coercion order, truncatable chain |
| 2 | 40 | 6 | Input validation at the edges |
| 3 | 25 | 2 | Canonical-form invariants, vocabulary enforcement |
| 4 | independent review | 2 | **Single-use enforcement — a defect the design documented wrongly** |
| 5 | 18 (prototype) | 2 | **The displayed fields were outside the signature** |
| 6 | 21 (agent boundary) | 2 | **A contract whose fields could contradict each other; an unbounded validity window** |
| 7 | 22 (audit + analysis) | 1 | **The audit trail's records could be rewritten after the fact** |

**Fifteen of the nineteen were at a boundary**, and every one of them
was a value accepted in a shape it should not have been. Two were
structural — the absence of a rule (single-use, a validity bound) —
one was a rule written down wrongly (the replay risk), and one was a
**property claimed but not implemented** (the trail's immutability).

**Where the rounds have found defects, in order of frequency:** a
boundary that accepts a value in the wrong shape; a boundary that
accepts a value that should not be accepted at all; a rule that was
documented but not enforced; a property that was assumed rather than
built.

### 8.11 What the seventh round says about the remaining work

The audit log is now immutable **in memory**. It is not yet durable,
not yet shared across processes, and not yet anchored outside the
agent's reach. The `ConsumedAuthorizations` set has the same gap. Both
are recorded as requirements rather than shipped as a false promise:

- the spent-authorization set must be **durable and shared**, so a
  captured authorization cannot be replayed after a reboot;
- the audit trail must be **anchored** — its head hash recorded where
  the agent cannot write — so a truncation or a consistent rewrite is
  detectable from outside.

Neither is done. Both are deployment work, and both are on the list
that the blocking decisions gate.

### 8.12 The independent review, in full

The independent reviewer returned **five** findings. Each was checked
against the real code before anything was changed. **Two were real.
Three were not.** All five are recorded here, because a finding that was
tested and rejected should stay tested.

| # | Finding | Verdict |
|---|---|---|
| 1 | Non-ASCII keys are escaped rather than rejected | **Already fixed** — the excerpt the reviewer worked from predated the fix (round three) |
| 2 | The nonce check runs before the request_id check, allowing a replay | **Not a defect.** The nonce is a *binding* between an authorization and a request, not a replay detector — there is no store of seen nonces. An attacker reusing a nonce with a different request_id is refused by the request_id check that follows. The real replay defence is the executor's spent-authorization set (D-14) |
| 3 | `_as_scope` does not verify the type before casting | **Not a defect.** It rejects a string, then anything that is not a list or tuple, then every item that is not a string |
| 4 | The state machine may reach unintended states, and refusals give inadequate feedback | **Partly real, and worse than described.** The transitions are correct, but the **executor kept no audit trail at all** — so a refused execution left no trace. See D-20 |
| 5 | The expiry check does not tolerate clock skew | **Real.** The authorization is produced by the *phone* and verified by the *PC*, and they have different clocks. See D-21 |

| ID | Defect | Exploit | Fix |
|---|---|---|---|
| **D-20** | The **executor** kept no audit trail. The guard audited every decision; the executor — the thing that actually performs the operation — recorded nothing | An execution that was **refused** left no trace. The audit log's own docstring claims refusals are recorded; that was true of the guard and false of the executor | Every attempt is recorded, with the outcome and the reason. The refusals are the interesting part |
| **D-21** | No **clock-skew tolerance** between the phone and the PC | A phone whose clock is a little behind produces an authorization that looks expired to the PC — and a slightly-wrong phone looks exactly like a replay | `CLOCK_SKEW_SECONDS` — a deployment parameter, applied to the **expiry side only**. An authorization that is not yet valid is still refused: a phone saying "this is good from later" is a clock problem, not a reason to accept early |

**D-20 is a gap between a claim and the code.** The audit log's
docstring says *"Both authorised and refused operations are recorded. A
refusal that is not recorded is indistinguishable from an operation that
never happened, which is exactly the gap an attacker wants."* That
sentence was true of the guard and false of the executor. The docstring
described the intended design; the executor had not been given it.

**Why finding 2 was rejected.** The reviewer reasoned from the
excerpt, in which the nonce was described as *"the replay defence"*.
It is not. A nonce is a **binding**: it ties an authorization to one
specific request. The replay defence is the spent-authorization set,
which did not exist when the excerpt was written and does now. Reading
a description and assuming it is the design is exactly how a wrong
finding gets made — and the way to answer it is to write the probe.

### 8.13 The tally

**Twenty-one defects** in roughly 2 700 lines of new security code.

| Round | Probes | Defects | Theme |
|---|---|---|---|
| 1 | 11 | 4 | Scope typing, depth, coercion order, truncatable chain |
| 2 | 40 | 6 | Input validation at the edges |
| 3 | 25 | 2 | Canonical-form invariants, vocabulary enforcement |
| 4 | independent review | 2 | **Single-use enforcement — a defect the design documented wrongly** |
| 5 | 18 (prototype) | 2 | **The displayed fields were outside the signature** |
| 6 | 21 (agent boundary) | 2 | **A contract whose fields could contradict each other; an unbounded validity window** |
| 7 | 22 (audit + analysis) | 1 | **The audit trail's records could be rewritten after the fact** |
| 8 | independent review (full) | 2 | **The executor kept no audit trail; no clock-skew tolerance** |

**The eight rounds found twenty-one defects and rejected three
findings.** The rejected ones are as useful a record as the accepted
ones: a review is only worth running if its output is checked, and
"this was tested and it holds" is a result.
