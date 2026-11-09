# Trust boundaries

## The boundaries, and what each one is for

| # | Boundary | Between | Enforced by | Demonstrated? |
|---|---|---|---|---|
| B1 | The plugin's surface | the agent / the platform | `agent.py`: closed schema, no commands, no decisions, no handler arguments | **Yes** — tested |
| B2 | The service's protocol | the plugin / the service | `protocol.py`: closed schema, version, size limit, fresh nonce | **Yes** — tested |
| B3 | The service's decision | the plugin / the authority | `service.py`: the decision is derived, never read from the request | **Yes** — tested |
| B4 | The cryptographic verification | the plugin / the phone's key | `crypto.py`: the plugin cannot verify a signature at all | **Yes** — tested |
| B5 | The caller's identity | any process / the service | `ipc.py`: the pipe's client token is checked against the allowlist | **Seam tested**; the Windows path is not |
| B6 | The service's storage | the agent / the state | the filesystem ACL on `C:\ProgramData\ConsequenceMap\` | **Designed, not installed** |
| B7 | The service's binaries | the agent / the code | the install directory's ACL: read and execute only | **Designed, not installed** |
| B8 | The human's authority | the agent / the human | a signature from a key on a device the agent cannot reach | **Yes** — tested with real Ed25519 |
| B9 | The desktop | the agent / the human | **nothing** — and nothing is asked of it | The desktop is explicitly **not** a boundary |

## B9: the boundary that does not exist, and is not needed

The agent runs in session 1 as the same interactive user, with
`computer_use` able to click and type. `credwiz.exe` is present.

**Any design in which the human's approval is a click is bypassable
here**, and this design is not that design. The human's authority is a
**signature made by a key on a separate device**. The agent can
control every pixel of the desktop and cannot produce that signature.

This is why there is no "the user must confirm" step anywhere in the
execution path. A confirmation the agent can click is not a
confirmation.

## B1 — the plugin's surface

The agent may call the plugin. What it may send:

| Field | Who controls it | Constraint |
|---|---|---|
| `tool` | agent | must be an operation in the policy's allowlist |
| `arguments` | agent | **command-shaped names refused at the boundary** |
| `proposal` | agent | the thing to be approved; hashed and signed as-is |
| `project` | agent | informational |
| `scope` | agent | the scope **requested**, not the scope **granted** |
| `actor` | agent | informational — **never an authority** |
| `expires_at` | agent | bounded by the service's policy |
| `summary` | agent | informational |

What it may **not** send: a decision, an `allowed` flag, an approved
scope, a handler name, a command, a script, or an unknown field.

`actor` deserves a note. The agent sets it, so it is worthless as an
identity. The authority is the **signing key**; `approved_by` is a
**label** the human's device writes, and the service never treats it
as an authority.

## B2 — the protocol

A request is a canonical document with a **closed schema**.

| Rule | Why |
|---|---|
| The version is checked | A message for another version is refused, not best-effort interpreted |
| Unknown fields are refused | A field the service does not understand might be one it would have honoured |
| The size limit applies to the **bytes**, before parsing | A large message cannot make the service do work |
| Every request carries a fresh nonce | A request replayed at the transport layer is refused before the authorisation is even considered |
| The response schema is closed too | A response with an unexpected field is a contradiction |

## B3 — the decision

The service derives the decision from four things it controls: the
**policy**, the **cryptographic verification**, the **durable state**,
and its own **clock**.

There is no code path in which a decision is read from a request. The
request has no such field, so there is nothing to lie about.

`INDETERMINATE` is never converted to `ALLOW`. An unverifiable
condition is a refusal.

## B4 — the cryptographic boundary

The plugin is **stdlib-only** and cannot verify an Ed25519 signature.
It does not hold a private key, and it cannot be given one.

This is the cleanest boundary in the system, because it is enforced by
**an import that is not there**. There is no check to bypass, no
configuration to get wrong, and no code path in the plugin that could
be talked into accepting a forged approval.

## B5 — the caller's identity

The pipe's **name** proves nothing. Anything that can open the pipe
can send a message through it. So the service authenticates the
**caller**:

1. read the client's token from the pipe;
2. read the caller's SID;
3. compare it against the policy's allowlist;
4. reject an unlisted caller **before the message is read**.

The Windows implementation (`WindowsPipeClientAuthenticator`) is
written as the specification of what the production path must do. It
**cannot be exercised on this host**, because it needs a real service
install. The seam around it is tested: the reference authenticator
lets the tests prove that an unlisted caller is refused, and that the
refusal happens before the message is read.

## B6 — the storage

The database is where the spent authorisations live. A write there is
a way to re-authorise oneself, so it is the one file the agent must
never reach.

The ACL denies the interactive user write **and** denies
`FILE_DELETE_CHILD` on the directory. The second part is what stops
the classic bypass of deleting the file and recreating it.

**Designed, not installed.** The ACL is a deployment property; the
code guarantees the atomicity and the durability.

## B8 — the human's authority

The phone signs the **exact bytes** the human saw. The mobile
prototype's display fields are **inside** the signed proposal — a
defect found in the eighth round, where an attacker could change what
the phone showed without invalidating the approval.

Revocation works **without** the lost phone: a recovery grant, signed
by a key that is not on the phone, consumed atomically so it is good
for one revocation.

**The gap:** this host has no hardware-backed credential. The
protocol is implemented; the credential's security is the
deployment's.

## The boundaries that are NOT here

Stated so nobody assumes them:

1. **The plugin is not trusted.** The service treats everything it
   receives as a claim.
2. **The administrator is not trusted by this design.** An
   administrator can change the policy, the binaries and the store.
   That is the operating system's trust model, and the threat model
   is "a compromised agent", not "a compromised administrator".
3. **The phone is trusted.** Whoever holds the phone holds a valid
   authority. That is why revocation exists, and why the recovery
   credential matters.
4. **The clock is trusted, to a degree.** 30 seconds of skew is
   tolerated. Beyond that, an authorisation is refused.
