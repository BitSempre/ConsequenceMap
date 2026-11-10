# Architecture — ConsequenceMap Security Platform v1

## The claim

**Even if the agent controls the plugin, it cannot grant itself
authorisation to execute a protected operation.**

Everything below exists to make that one sentence true, and to say
precisely which parts of it are demonstrated and which are designed.

## The shape

```
┌──────────────────────────────────────────────────────────────────┐
│  THE AGENT'S SIDE — it controls all of this                       │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ consequence_map  (the PLUGIN — stdlib-only)               │  │
│  │                                                            │  │
│  │  analysis ── proposal building ── forecasts ── evidence   │  │
│  │                                                            │  │
│  │  agent.py    the surface an agent may call                │  │
│  │  canonical   the ONE canonical form                      │  │
│  │  authorization  the protocol (verify only, never decide) │  │
│  │                                                            │  │
│  │  It may PROPOSE. It may not decide, consume or execute.   │  │
│  │  It holds NO private key and CANNOT verify a signature.   │  │
│  └───────────────────────────┬────────────────────────────────┘  │
│                              │                                   │
│              named pipe, ACL-enforced, caller authenticated     │
│                              │                                   │
│  ┌───────────────────────────▼────────────────────────────────┐  │
│  │ consequence_guard  (the SERVICE — the agent cannot reach) │  │
│  │                                                            │  │
│  │  ipc.py        transport + caller authentication          │  │
│  │  protocol.py   closed schema, version, size limit         │  │
│  │  service.py    THE AUTHORITY: derive, verify, decide       │  │
│  │  crypto.py     Ed25519 — real signatures                  │  │
│  │  store.py      durable, atomic, fail-closed               │  │
│  │  recovery.py   revocation without the lost phone           │  │
│  │  recovery_after_crash.py  the honest answer                │  │
│  │                                                            │  │
│  │  Own identity. Own protected storage. Executes.            │  │
│  └────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
                              │
             ┌────────────────▼─────────────────┐
             │  THE HUMAN'S SIDE — off-PC        │
             │                                  │
             │  phone: Ed25519 key in secure    │
             │  hardware, signs the EXACT       │
             │  proposal shown on the screen    │
             └──────────────────────────────────┘
```

## The split is not a convention

The boundary is expressed in the **code structure** and in the
**dependency difference**:

| | `consequence_map` | `consequence_guard` |
|---|---|---|
| Runs | where the agent runs | where the agent cannot |
| Dependencies | **stdlib only** | `cryptography` |
| Can verify a signature | **no** | yes |
| Holds a private key | no | no (the phone holds it) |
| Decides | **no** | **yes** |
| Executes | **no** | **yes** |
| Consumes an authorisation | no | yes, atomically |

The plugin's inability to verify a signature is not a limitation
imposed on it. It is what makes it safe: an agent that controls the
plugin cannot find a path by which a forged approval is accepted,
because the code that would accept one is in the other process.

**One product, two processes.** The user installs one thing. The
plugin and the service are internal components of it, and the service
is an implementation detail of the security guarantee, not a separate
product.

## The decision path

```
plugin                      service
──────                      ───────
proposal ────────────────▶  parse (closed schema, size limit)
authorisation ───────────▶  authenticate the CALLER
                              operation in the allowlist?      ── no ─▶ DENY
                              re-derive the request
                              verify the signature            ── no ─▶ DENY
                              scope ⊆ requested?               ── no ─▶ DENY
                              operation matches the approval?  ── no ─▶ DENY
                              window valid, key not revoked?   ── no ─▶ DENY
                              audit the attempt               ── fail ─▶ DENY
                              CONSUME atomically              ── taken ─▶ DENY
                              derive the arguments
                              audit the start
                              run the handler
                              audit the outcome
◀──────────────────────────  ALLOW / DENY + reason
```

**Every arrow to DENY is a refusal with a reason.** There is no path
that converts a failure into an allowance.

## The four things that are not the same

| Concept | What it proves | What it does not prove |
|---|---|---|
| **Hash** | Integrity: these bytes have not changed | Who produced them |
| **Signature** | Authenticity *and* integrity under a key pair | That the content is **true**, or **wise** |
| **Authorisation** | That a decision was made, and by whom | That the effect happened |
| **Execution** | That the effect happened | — |

The architecture keeps these separate on purpose. The platform never
claims that a signature makes an operation good for the user.

## The plugin's surface

`agent.py` gives the agent a narrow surface: it may ask for an
operation to be considered. It cannot:

- pass a command, a shell string, or a handler name;
- pass the arguments a handler will receive (they are **derived** from
  the proposal by the policy's own argument map);
- pass a decision, an `allowed` flag, or an approved scope;
- name an operation the policy does not list;
- add a field the protocol does not define.

Every one of those is refused, and the refusals are tested.

## Where the state lives

| State | Where | Durability | Protected by |
|---|---|---|---|
| Spent authorisations | `state\guard.sqlite3` | survives a restart | filesystem ACL |
| Operation states | `state\guard.sqlite3` | survives a restart | filesystem ACL |
| Audit trail | `state\guard.sqlite3` | survives a restart | filesystem ACL + hash chain + checkpoint |
| Nonces (transport) | in memory, per service instance | **lost on restart** | — |
| Policy | `policy.json` | on disk | filesystem ACL |
| Keys | `keys\` | on disk | filesystem ACL |

The transport nonce set is the one piece of state that is not durable.
It is not the replay defence — the **spent set** is, and it is durable.
See `05-AUDIT-LOG-DESIGN.md` and `09-PERSISTENCE-AND-RECOVERY.md`.

## What the design does NOT do

Stated plainly, because a security document that only lists strengths
is not an honest one:

1. **It does not install the service.** The Windows service, its
   identity and its ACLs are **designed and documented, not installed**.
   The boundary is therefore **specified, not demonstrated** on this
   host.
2. **It does not provide a hardware-backed recovery credential.** This
   host has no TPM 2.0, no Windows Hello, no smart card, no FIDO2. The
   protocol is implemented; the credential's own security is whatever
   the deployment provides.
3. **It does not build an external audit anchor.** The checkpoint
   mechanism exists; the anchor outside the agent's reach does not.
4. **It does not make the phone's application.** The protocol and the
   reference implementation exist; the Android and iOS applications do
   not.
5. **It does not rely on the desktop for human presence.** It cannot:
   the agent can click. The human's authority is off-PC, in a signature.
