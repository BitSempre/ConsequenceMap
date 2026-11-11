# ConsequenceMap

**Decision intelligence for AI agents.** ConsequenceMap forecasts the consequence
of an action *before* it happens, preserves the decision and its evidence, and
compares the forecast with what actually occurred.

> ## Status: NOT READY FOR PRODUCTION
>
> The library and the plugin are implemented and tested. The **Security Guard
> is not installed on any host** — it is a library, not a running service. The
> authorization boundary this project exists to provide is therefore **not
> active** until the Windows service, its identity and its ACLs are deployed.
> See [Current limitations](#current-limitations).

---

## What it does

An agent acting on your behalf can be wrong in a way you never see. It can
delete the wrong file, spend money twice, or write a config that breaks a
system — and report success while doing it.

ConsequenceMap makes the reasoning visible and keeps the evidence:

| Stage | What happens |
|---|---|
| **Forecast** | Before the action, classify the evidence (`VERIFIED_FACT`, `INFERENCE` or `UNKNOWN`), assess risk, confidence and reversibility, and name the alternatives. A prediction is never a guarantee. |
| **Decision** | Record what was chosen and why. The **product decision is the agent's**; the **human's authorization is the host's record**. They are stored separately and are never merged. |
| **Outcome** | After the action, record what happened and compare it with the forecast. An outcome that cannot be verified stays `NOT_VERIFIABLE`; the derived verdict is `INCONCLUSIVE`, not a clean pass. |

The comparison is the point. A system that records only what it intended
cannot tell you where it was wrong.

---

## Architecture

Three components with strictly separated authority:

```
   ┌────────────────────────┐        ┌─────────────────────────┐
   │  Hermes Agent          │        │  Security Guard          │
   │  (the plugin)          │        │  (separate service)      │
   │                        │        │                          │
   │  proposes              │        │  decides                 │
   │  observes              │ ─────► │  verifies signatures     │
   │  escalates             │        │  executes                │
   │  NEVER decides         │        │  NEVER trusts the agent  │
   │  NEVER holds a key     │        │  holds the keys          │
   └────────────────────────┘        └─────────────────────────┘
            │                                    │
            └────────── audit trail ────────────┘
                (hash-chained, checkpointed)
```

The plugin is **stdlib-only** and holds no private key. It cannot verify a
signature — which is precisely why it cannot be talked into accepting a forged
one. The Guard holds the keys, re-derives the request server-side, and
executes only allowlisted operations with arguments derived by the policy's own
argument map.

### Packages

| Package | Role |
|---|---|
| `consequence_map/` | The product: lifecycle, correlation, authorization, path containment, self-exclusion, and the storage layer. Stdlib only. |
| `consequence_guard/` | The decision boundary: Ed25519 verification, the hash-chained audit store, the closed protocol, recovery grants. |
| `quality_guardian/` | The project's own quality layer: change detection, selective test selection, and a fail-closed repair policy. |
| `plugin/` | The Hermes plugin: manifest, five hooks, a dashboard tab and a command-palette entry. |
| `host_tests/` | Tests that exercise the plugin the way the real host loads it. |

---

## Security model

### Fail-closed by construction

* **A missing, unreadable or malformed repair policy suspends the
  capability.** Only an explicit `auto_repair: true` in a readable policy file
  enables it. `DEFAULT_AUTO_REPAIR` is `False`.
* **A storage failure never lets an operation through.** The sink counts the
  failure, the operation continues (the host owns the decision), and the count
  is reported by the status command so a gap in the trail is never silent.
* **Every failure mode returns `DENY`.** Signature errors, expired
  authorizations, replays, store failures and unknown messages all refuse.

### Authorization is bound to the operation

An authorization is not a generic permission. It is bound to:

* the **operation** it approves (a mismatch is refused),
* the **proposal** it answers (the hash is recomputed, never trusted),
* the **request** (the nonce and request id must match),
* a **validity window** that is bounded by policy.

The signature covers the whole document except the signature field itself, so
any change to any field breaks it.

### Replay, expiry and single use

* The nonce set is **durable** — it survives a service restart, so a restart
  cannot reopen the replay window.
* Consumption is an **atomic** transaction: two concurrent callers, one wins.
* A consumed authorization is spent; a second attempt is refused.
* Clock-skew tolerance is applied on the expiry side only. An authorization
  that is not yet valid is refused.

### Audit integrity

The audit trail is a hash chain. Each record commits to its predecessor, and
checkpoints anchor the head. Tampering is detected — but note the honest
limitation: `audit_head()` returns the **stored** hash, so the checkpoint
comparison detects a tampered `record_hash` and not, on its own, a tampered
payload or a deleted row. Recomputing the chain detects all of them; that
verification is not exposed as a public API yet.

### Separation of authority

The plugin cannot grant authority. It proposes, observes and escalates; the
Guard decides and executes. Handlers live in the Guard's binary; the plugin
has no import path to them. The plugin never observes its own operations
(`RECUR-1` through `RECUR-9`).

---

## Installation

### Requirements

* **Hermes Agent >= 0.22.5** (tested on 0.23.0). The plugin declares
  `requires_hermes: ">=0.22.5"` in its manifest, and the loader skips the
  plugin on an older host.
* **Python 3.11+**, standard library only. No third-party runtime dependency.
* The plugin stores its own database under the Hermes plugin-data directory
  and reaches it through the public `plugins.plugin_storage` surface. It
  imports no private Hermes module.

### From a git checkout

```bash
git clone https://github.com/BitSempre/ConsequenceMap.git
cd ConsequenceMap
hermes plugins validate ConsequenceMap/plugin
hermes plugins install https://github.com/BitSempre/ConsequenceMap --ref <40-char-sha>
```

`hermes plugins validate` runs the same check the catalog CI runs. It must
pass before you install.

> **Note on layout.** The plugin manifest lives in `ConsequenceMap/plugin/`.
> The repository is a monorepo: the plugin, the product library, the guard, the
> quality layer and the delivery evidence are all in one tree. A catalog entry
> therefore points at the repository with a `subdir`.

### Running the tests

```bash
# the product
python -m unittest discover -s consequence_map/tests -t . -p "test_*.py"

# the guard
python -m unittest discover -s consequence_guard/tests -t . -p "test_*.py"

# the quality layer
python -m unittest discover -s quality_guardian/tests -t . -p "test_*.py"

# the plugin, the way the host loads it
python -m unittest discover -s host_tests -t . -p "test_*.py"
```

Current state: **745 tests pass, 0 failures**. The Guardian's full cycle runs
690 of them across both packages.

---

## Development status

### Implemented and verified

* The complete forecast → decision → outcome → comparison loop, with a durable
  SQLite store and a sealed forecast.
* The 13-state authorization machine and the escalation deadline.
* The five Hermes hooks, the dashboard API and the command-palette entry.
* Path containment with the six-step algorithm and the protected-pattern rules.
* The Security Guard library: Ed25519 verification, the hash-chained audit
  store, the closed protocol, the recovery grant flow.
* The Quality Guardian: change detection, a 37-module test-selection map
  covering both packages, a full-cycle run of 690 tests, and a fail-closed
  repair policy.

### Prototype only

* **The mobile authorization flow.** A phone-side prototype demonstrates the
  signing and binding protocol and passes 12 tests, but it is not an
  installable mobile application and is not connected to a running Guard.
* **The desktop surfaces.** The dashboard API has 4 tested routes against the
  real router, and the desktop panel is written against the host SDK. Nobody
  has watched the panel draw on a live desktop.

### Planned or incomplete

* The **Windows Security Guard service** — the design, identity and ACLs are
  documented in `security-decisions/ADR-002-WINDOWS-SERVICE-IDENTITY.md`; the
  service is not installed.
* **Revocation propagation.** A revoked Ed25519 key is not currently
  observed by a verifier that was already constructed; revocation takes effect
  for verifiers built afterwards.
* **Full audit-chain verification.** There is no public API that recomputes
  the chain.
* **DEC-16**, the grace-period constant, is still an open decision. The
  implemented 30 s is the analytical reference value, not a decision.

---

## Current limitations

| Limitation | Consequence |
|---|---|
| The Guard is a library, not a service | The authorization boundary is not enforced on any host. The plugin escalates and records; it cannot refuse. |
| Revocation does not reach an existing verifier | A key revoked while the service is running may still be accepted until the verifier is rebuilt. |
| No public chain-verification API | The checkpoint detects a tampered `record_hash`; payload tampering and row deletion need a full recomputation. |
| The repository contains a duplicated snapshot | An older copy of the tree is committed alongside the live one. It is history, not a second product. |
| `SHA256SUMS.txt` is stale | It records the hashes of an earlier delivery. The archive content itself verifies. |

---

## Responsible use and security warnings

* **This project does not protect anything until the Guard is deployed.** Treat
  any host running only the plugin as unprotected by ConsequenceMap.
* **The plugin runs with your agent's authority.** It reads the host's
  operations and writes to its own database under the Hermes plugin-data
  directory. Install it only on hosts and repositories you trust.
* **Forecasts are not guarantees.** The product deliberately refuses to record
  an unverifiable outcome as anything but `NOT_VERIFIABLE`. Do not treat a
  `VERIFIED_FACT` label as permission to skip your own review.
* **The plugin declares five hooks.** `pre_tool_call` can escalate to the
  human-approval gate; the other four observe. Review the hook list before
  enabling it.
* **Do not install this on a host where you would not accept the agent's
  actions.** The plugin makes the agent's reasoning visible; it does not make
  the agent safe.
* **Report security issues privately** to the maintainer rather than in a
  public issue.

---

## Repository layout

```
ConsequenceMap/
├── ConsequenceMap/            the project root (monorepo root of the plugin)
│   ├── consequence_map/       the product library (stdlib only)
│   ├── consequence_guard/     the decision boundary
│   ├── quality_guardian/      the project's quality layer
│   ├── plugin/                the Hermes plugin (manifest, hooks, dashboard)
│   ├── host_tests/            plugin-under-host integration tests
│   ├── demo/                  an end-to-end demonstration
│   └── docs/                  delivery reports, phase reports, decision records
├── design/                    the mobile authorization prototype
└── security-decisions/        ADRs, including the Windows service identity
```

## License

See `ConsequenceMap/docs/` for the phase reports and the full delivery
evidence.

## Acknowledgements

Built for the Nous Research Hermes Plugin ecosystem. The Hermes plugin
surface — hooks, the `ctx.register_*` APIs and the Desktop plugin SDK — is the
public extension contract this project is built on.
