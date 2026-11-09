# ADR-002 — The identity of the Windows Security Guard

| | |
|---|---|
| **Status** | Accepted (design); **NOT INSTALLED** on this host |
| **Date** | 2026-11-09 |
| **Decides** | D-22 — the service identity |

## Context

The plugin runs where the agent runs. The agent controls that process:
it can edit the plugin's files, change its configuration, and — as
measured on this host — drive the desktop through `computer_use`.

For the guard to be an authority, it must run somewhere the agent
cannot reach. That means a separate process, with its own identity,
with its own protected storage.

### Measured facts about this host

These are measurements, not assumptions:

- Windows 11 x64. **TPM 1.2** (`ACPI\PNP0C31`),
  `PreReqResult: WillNotProvision` — Windows Hello is **not**
  available and cannot be provisioned.
- Zero CNG keys, zero smart cards, zero FIDO2 devices, zero Passport
  credentials.
- The Hermes agent runs in **session 1** (`console`, Active) as the
  same interactive user, at normal user integrity, with
  `computer_use` able to click and type.
- Therefore **a desktop confirmation is not a trust boundary**. The
  agent can click the prompt. Any design that relies on the human
  clicking something the agent can click is bypassable, and this
  architecture does not rely on it.

The human's authority comes from a **signature made by a key on a
device the agent cannot reach**, not from a click.

## Decision

The guard runs as a **Windows service under a virtual service account
name**, `NT SERVICE\ConsequenceMapGuard`, with a dedicated local
service account behind it.

### Why not LocalSystem

LocalSystem has the machine's full authority. It can write anywhere,
read other users' secrets, and impersonate anyone. The guard does not
need any of that, and a service that has it is a service whose
compromise is a machine compromise.

### Why not LocalService or NetworkService

- **LocalService** is a low-privilege identity, but it is shared by
  every LocalService process on the machine, and it has write access
  to shared resources that assume "some service" rather than "this
  service". The guard's protected store must be writable by *this*
  service and nobody else.
- **NetworkService** is LocalService plus network authentication
  credentials. The guard needs no network identity at all, and
  carrying one adds an authentication surface for no benefit.

### Why a virtual service account

`NT SERVICE\<name>` is a virtual account: the password is managed by
the SCM, it does not appear in the credential store, and it exists
only while the service exists. Paired with a dedicated local account
(`ConsequenceMapGuardSvc`) with a random, non-expiring password, it
gives:

- a **stable identity** whose SID can be written into ACLs — so the
  ACL does not depend on the account's name surviving;
- **no interactive logon** — the account cannot be used to log on,
  so the agent cannot "become" the service;
- **least privilege** — the account is granted only what the guard
  needs.

### The privileges the guard actually needs

- `Log on as a service` (`SeServiceLogonRight`).
- **Nothing else.** No "act as part of the operating system", no
  "log on locally", no "impersonate".
- The account is **denied** the "deny log on as a service" right for
  every other service, so a compromised service cannot borrow the
  guard's identity.

### The protected store layout

```
C:\ProgramData\ConsequenceMap\          ACL: SYSTEM=Full, GuardSvc=Full,
                                         Users=Read (list only),
                                         Authenticated Users=Read (list only)
  policy.json                            the operation allowlist
  keys\                                  public keys, recovery keys
  state\guard.sqlite3                    the durable store
  state\guard.sqlite3-wal                WAL
  state\guard.sqlite3-shm                shared memory index
  checkpoints\                           integrity checkpoints
  logs\                                  service logs
```

**ACL rationale**

| Path | SYSTEM | GuardSvc | Users | Everyone |
|---|---|---|---|---|
| directory | Full | Full | Read | — |
| `policy.json` | Full | Full | Read | — |
| `state\*.sqlite3` | Full | Full | **None** | **None** |
| `keys\*.pub` | Full | Full | Read | — |
| `keys\*.key` | Full | **None** | **None** | **None** |

The database is the one thing the agent must never touch: it is where
the spent authorisations live, and a write there is a way to
re-authorise itself.

The **directory** ACL denies `FILE_DELETE_CHILD` to the interactive
user, so the agent cannot replace `guard.sqlite3` by deleting it and
recreating it — the classic way to defeat a file-level ACL.

### The service configuration

To be executed during installation, **not on this host**:

```
sc.exe create ConsequenceMapGuard ^
  binPath= "C:\Program Files\ConsequenceMap\guard.exe" ^
  start= auto ^
  obj= "NT SERVICE\ConsequenceMapGuard" ^
  DisplayName= "ConsequenceMap Security Guard"
```

The binary's directory ACL must grant `Users` **read and execute**
only, and **no write** — otherwise the agent can replace the
executable.

## Threats this identity addresses

| Attack | Mechanism that stops it | Residual risk |
|---|---|---|
| Agent writes the policy | The file's ACL denies write to the interactive user; the service re-reads and re-validates the policy on every start and fails closed if it cannot be read | An administrator can still change it. That is the intended power of an administrator. |
| Agent replaces the service binary | The install directory denies write to `Users` | An administrator can still replace it |
| Agent writes the store | The database ACL denies write to `Users`, **and** the parent directory denies `FILE_DELETE_CHILD`, so the file cannot be replaced | An administrator can still write it |
| Agent impersonates the service | The service account has no interactive logon, and the pipe's client token is checked against the allowlist | An administrator can impersonate it |
| Agent forges a response | The plugin never decides; it asks the service and presents what it is told. The service's response is derived server-side | — |
| Agent calls a handler directly | Handlers live in the service binary; the plugin has no reference to them and no import path to them | An administrator can call them |
| Agent escalates through the service | The service executes only allowlisted operations, with arguments derived from the proposal by the policy's own argument map | An administrator can change the policy |
| Agent simulates a human approval on the desktop | **The design does not rely on the desktop.** The authority is a signature from a key on a separate device | A keylogger on the PC could capture a request, but not forge a signature |
| Agent kills the service to reset state | The state is **durable**. A restart does not un-consume an authorisation | The agent can stop the service, denying service — a denial of service, not a privilege gain |
| Agent races two processes | The consumption is an atomic `INSERT` in an immediate transaction | — |
| Agent fills the disk | The audit append raises; the service refuses the operation | Denial of service |

## What this design explicitly CANNOT guarantee on this host

1. **No hardware-backed human presence.** TPM 1.2 with Hello not
   provisionable means there is no second factor the agent cannot
   reach on the PC. The human's authority is therefore entirely
   **off-PC**, on the phone. That is a deliberate design, and it is
   also a single point of failure: if the phone is compromised, the
   attacker holds a valid authority.
2. **The agent runs as the same interactive user.** Anything that user
   can do, the agent can do — including starting a process that tries
   to connect to the pipe. The pipe's ACL and the client-token check
   are what stop it, and those are **untested here**, because testing
   them needs a real service install.
3. **No Smart Lock.** The TPM cannot be used to seal the store to the
   service identity.
4. **An administrator is above this design.** That is not a defect in
   the design; it is the definition of the operating system's trust
   model. The threat model is "a compromised agent, not a compromised
   administrator".

## Installation and rollback (text; NOT executed here)

**Install**

1. Create the local account `ConsequenceMapGuardSvc` with a random
   32-byte password, `Password never expires`, **deny log on locally**
   and **deny log on as a service** (the service's own right is then
   granted separately).
2. Create the directory tree and apply the ACLs above.
3. Copy the binaries to `C:\Program Files\ConsequenceMap\` and apply
   read-and-execute-only for `Users`.
4. Deploy `policy.json` and the public key material.
5. `sc.exe create` as above; start the service.
6. **Verify**: as the interactive user, attempt to write
   `policy.json` and to open `guard.sqlite3` for writing — both must
   fail with `ERROR_ACCESS_DENIED`. Attempt to connect to the pipe —
   must fail. These three checks are the acceptance test for the
   boundary.

**Rollback**

1. `sc.exe stop` then `sc.exe delete ConsequenceMapGuard`.
2. Remove the service account.
3. Remove `C:\ProgramData\ConsequenceMap\` **after taking a backup of
   the audit trail** — the trail is the evidence, and it must survive
   the uninstall.
4. Remove the install directory.
5. Verify the pipe is gone and the service is not registered.
