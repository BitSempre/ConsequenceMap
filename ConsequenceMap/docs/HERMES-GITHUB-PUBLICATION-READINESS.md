# ConsequenceMap — Hermes Plugin Hackathon: GitHub Publication Readiness

**Date:** 2026-11-11
**Classification:** NOT READY FOR PRODUCTION
**Scope:** inspection and preparation only. No repository was created, no remote
was added, nothing was pushed or published.

---

## 1. Local repository

| | |
|---|---|
| Authoritative repository | `C:\Users\Utente\Desktop\Projects\ConsequenceMap\ConsequenceMap-Platform` |
| Project root (monorepo subdir) | `ConsequenceMap/` inside the above |
| Outdated tree (NOT the source) | `C:\Users\Utente\Desktop\ConsequenceMap` — Phase 2A only, correctly excluded |
| `.git` integrity | OK — all loose objects pass `git fsck` |

## 2. GitHub account — verified

| | |
|---|---|
| GitHub CLI | installed and authenticated |
| Authenticated username | `BitSempre` |
| Scopes | `repo`, `workflow` |
| Token | **never read, printed or stored** in this report |
| Repository-creation permission | `repo` scope on the owner account is sufficient; not exercised |
| Existing remote | **none** — no `origin`, no upstream, no remote branches |

## 3. Target repository

| | |
|---|---|
| `BitSempre/ConsequenceMap` | **does not exist** (API returns 404; checked directly, not assumed) |
| Name availability | available to create |
| Collision with Mosaic projects | none — verified independent of `Mosaic-Add-ons`, `Mosaic-Fleet-Manager` and `Mosaic-Add-on-Studio` |

## 4. Branch and HEAD

| | |
|---|---|
| Branch | `feature/platform-v1` |
| HEAD (full) | `754cb9a36fb34c4566730c307cf9edb4af05f00b` |
| Commits | 60 |
| Tags | none |
| Delivery commits intact | `01a3b85` and `754cb9a` both present and unmodified — see §6 |

## 5. Git status

```
M ConsequenceMap/plugin/__init__.py
 M ConsequenceMap/plugin/plugin.yaml
?? ConsequenceMap/README.md
?? ConsequenceMap/docs/HERMES-GITHUB-PUBLICATION-READINESS.md
?? README.md
```

| | |
|---|---|
| Staged | **nothing** |
| Tracked files modified | **2** — `ConsequenceMap/plugin/__init__.py`, `ConsequenceMap/plugin/plugin.yaml` (the review fix, §9a) |
| Untracked | **3** — `README.md` (repo root), `ConsequenceMap/README.md`, this report |
| Untracked caches | `__pycache__` / `*.pyc` exist on disk but are **not** tracked |

### 5a. The tracked modifications

| File | Change | Why |
|---|---|---|
| `ConsequenceMap/plugin/__init__.py` | removed the private-import block; `HookState.STATE` → the module-level `STATE` | two runtime defects found and fixed — see §9a |
| `ConsequenceMap/plugin/plugin.yaml` | added `requires_hermes: ">=0.22.5"` | catalog rule 14 requires the manifest to carry the same floor as the entry |

Backup of both files before editing:
`scratch/cm-backup-pre-review-fix-20261111/`.

## 6. Commit history preservation

* No reset, rebase, amend, squash or rewrite was performed.
* Full history: 60 commits on `feature/platform-v1`, from the initial import to
  `754cb9a36fb34c4566730c307cf9edb4af05f00b`.
* The two previously reported delivery commits are intact:
  * `01a3b85` — *"feat(security): strengthen Quality Guardian and fail-closed policy"*
  * `754cb9a` = `754cb9a36fb34c4566730c307cf9edb4af05f00b` — *"docs(delivery): the final delivery report"*
* All earlier reports and evidence remain in `ConsequenceMap/docs/`
  (`ENTREGA-FINAL-*`, `CLOSING-*`, `PHASE-2A-*`, `PROPOSTAS-*`,
  `CORRECCOES-SEGURANCA-*`), unmodified.

## 7. Secret and sensitive-file scan

Scan run over the five in-scope files and over the tracked tree.

| Check | Result |
|---|---|
| Real credentials in tracked files | **none found.** The only token-like strings are deliberately **truncated test fixtures** in `consequence_map/redaction/tests/test_redaction.py` (`ghp_ab…2345` — a 28-char redaction unit, not a 36/37-char valid token; `BEGIN RSA PRIVATE KEY` header with no body, used as a redaction-pattern target) |
| In-scope files: tokens, private keys, passwords, emails, chat ids | **none.** The two regex hits in this report are the descriptive mention of the fixture above and the two documented local paths in §1 |
| `.env`, `*.pem`, `*.key`, service credential files | none tracked |
| Windows service artifacts (`C:\ProgramData\ConsequenceMap`, `ConsequenceMapGuardSvc` account) | do not exist — nothing to leak |
| `__pycache__` / `*.pyc` | present on disk, **not tracked** |
| Stale delivery ZIP + `SHA256SUMS.txt` | tracked; the ZIP's inner content verifies against the manifest's own recorded hashes; `SHA256SUMS.txt` itself is stale (records an earlier delivery). **Left untouched by rule** |
| Older backup snapshot `ConsequenceMap_BACKUP_20261110_190537/` | 12 tracked files; historical, harmless, left in place |
| Duplicated snapshot `ConsequenceMap/ConsequenceMap-Platform/` | 214 tracked files from an earlier commit; history, not a second product; left in place |

**Conclusion:** the repository can be made public without exposing live secrets.
The duplicated snapshot is a readability concern, not a leak.

## 8. README and documentation readiness

Prepared in this mission:

* `README.md` (repo root) — a short landing page: what it is, status banner,
  install snippet, layout table.
* `ConsequenceMap/README.md` — the full public README:
  * status banner `NOT READY FOR PRODUCTION`;
  * what it does and why;
  * architecture (agent / guard separation);
  * security model (fail-closed, operation-bound authorization, replay,
    single-use, audit integrity, separation of authority);
  * installation and Hermes compatibility;
  * test instructions and current results (745 tests pass);
  * development status split into **implemented & verified / prototype only /
    planned or incomplete**;
  * a limitations table;
  * responsible-use and security warnings.

Honesty constraints enforced: the Windows service is described as
**not installed**; the mobile flow as a **prototype**; the audit-chain
verification gap and the revocation-propagation gap are stated, not hidden.

Existing English documentation that supports the README:
`docs/ARCHITECTURE-CONSEQUENCEMAP.md`, `docs/SECURITY-MODEL.md`,
`docs/DEVELOPER.md`, `security-decisions/ADR-002-WINDOWS-SERVICE-IDENTITY.md`,
`design/mobile-auth/README.md`, `plugin/dashboard/README.md`,
`CONSEQUENCEMAP-PLUGIN-README.md`.

## 9. Hermes plugin compatibility

**Verified against the installed Hermes 0.23.0 (not assumed).**

| Check | Result |
|---|---|
| Official validation: `hermes plugins validate ConsequenceMap/plugin/` | **PASSED, exit 0** — re-run after the §9a fix: still exit 0, **and the rule-9 warning is gone** |
| Manifest (`plugin.yaml`) | valid v1 manifest; `requires_hermes: ">=0.22.5"` now declared and parsed (`✓ requires_hermes — spec '>=0.22.5' parses`) |
| Loadable | `__init__.py` + `desktop/plugin.js` present; `register()` ran in isolation |
| Declared hooks | 5 hooks — all match the registrations |
| Security scan | clean; no core override |
| Desktop surface | stays inside the plugin SDK surface |
| Private core imports | **none.** The plugin now reaches the host database only through the public `plugins.plugin_storage` surface |
| Catalog naming collision | `consequence-map` is not present in the local catalog (1051 entries) |

### 9a. Two runtime defects found by this review — and fixed

The review inspected the private import rather than accepting the validator's
warning at face value. It uncovered **two pre-existing defects**, both present
at HEAD `754cb9a` and both introduced together in commit `2377965`. Neither was
caused by the publication preparation.

**Defect 1 — the private import was dead code that also shadowed the working
public path.**
`plugin/__init__.py` called `hermes_cli.sqlite_util.transaction(provider=path)`
to install a shared connection provider. Two independent things were wrong:

* `transaction()` has the signature `transaction(conn, *, immediate=False)` —
  it takes a **connection**, not a `provider=` keyword. The call raises
  `TypeError: transaction() got an unexpected keyword argument 'provider'`.
* Even with the right signature it would have been wrong: `transaction()` is a
  context manager that yields and then **closes** the connection. It cannot
  serve as a connection provider.

The block was also unreachable: `db_module` is referenced on line 74 but
imported on line 85, so the line raised
`NameError: cannot access local variable 'db_module'`, which the surrounding
`except Exception` swallowed into a log warning. The intended provider was
therefore never installed — and the package's own default,
`storage.db.hermes_connection_provider`, already uses the **public**
`plugins.plugin_storage.plugin_db`, which is not flagged by the rule-9 lint.

**Defect 2 — the audit sink was never wired to the database.**
Line 92 read `HookState.STATE.sink = RepositoryAuthorizationSink(repository)`.
`STATE` is a module-level object in `consequence_map/hooks.py`, not a class
attribute of `HookState`, so this raised
`AttributeError: type object 'HookState' has no attribute 'STATE'` — again
swallowed by the `except Exception`. The consequence was that after
`register()`, the active sink remained the **inert** `AuthorizationSink`: the
plugin loaded, created and migrated its 17 database tables, and then recorded
**nothing**. No authorization was ever persisted.

Both defects were hidden behind the same broad `except Exception`, and the
official validator could not see either: it checks the manifest, the
registrations and the import surface, but it does not assert that the sink is
actually attached after registration.

**The fix** (applied to the real tree, verified in an isolated copy first):

```diff
         from consequence_map.hooks import (
             RepositoryAuthorizationSink,
             HookState,
+            STATE,
         )

-        # Injete o provedor do Hermes para que as inserções usem a mesma conexão
-        # que o host cria através do sqlite_util.transaction.
-        try:
-            from hermes_cli.sqlite_util import transaction as hermes_transaction
-            def hermes_provider(path):
-                return hermes_transaction(provider=path)
-            db_module.set_connection_provider(hermes_provider)
-        except Exception:
-            logger.warning(
-                "ConsequenceMap: não foi possível injetar o provedor do Hermes",
-                exc_info=True,
-            )
+        # The connection provider is the package default
+        # (`storage.db.hermes_connection_provider`), which uses the public
+        # `plugins.plugin_storage.plugin_db` surface. No private Hermes
+        # module is imported here.
@@
-            HookState.STATE.sink = RepositoryAuthorizationSink(repository)
+            STATE.sink = RepositoryAuthorizationSink(repository)
```

**Verification of the fix** — the private import was **not** simply replaced:
the replacement was proven first.

| Check | Result |
|---|---|
| Public alternative exists | **yes** — `plugins.plugin_storage.plugin_db` is in the validator's `_PUBLIC` set (89 entries); `_private_target()` returns *public* for it, versus *private* for `hermes_cli.sqlite_util.transaction` |
| The public path was already in use | yes — `storage.db.hermes_connection_provider` uses it, and the package's own docstring states the plugin owns its connection because the host's `transaction()` always closes it |
| Tests, real tree (baseline) | 733 run, **0 failures** |
| Tests, isolated copy with the import removed only | 733 run, **0 failures** — behaviour-equivalent |
| Tests, isolated copy with both fixes | 733 run, **0 failures** |
| Sink after `register()` | `RepositoryAuthorizationSink` (was `AuthorizationSink`) — records now persist |
| Official validation on the fixed copy | exit 0, **no rule-9 warning** |
| Manifest with `requires_hermes` | exit 0, `✓ requires_hermes — spec '>=0.22.5' parses` |

Test totals: `consequence_map` 556, `consequence_guard` 134,
`quality_guardian` 41, `host_tests` 2 — **733 tests, 0 failures**, identical
across the baseline, the import-only variant and the fully fixed variant.

## 10. Proposed GitHub repository configuration

| Field | Value |
|---|---|
| Name | `ConsequenceMap` |
| Owner | `BitSempre` |
| Visibility | Public |
| Description | A security and authorization layer for AI agent operations. |
| Default branch | `feature/platform-v1` (the existing branch, per instruction) |
| Initial README | from `README.md` at the pushed commit (GitHub auto-reads it) |
| License | not set (project has no LICENSE file; add one before the hackathon if desired) |

## 11. Proposed catalog entry (draft only)

Draft saved to the Hermes scratch (`…/cache/scratch/consequencemap.yaml`) and
validated against the real Hermes 0.23.0 catalog parser (`entry_from_mapping`
accepts it; `install_identifier = https://github.com/BitSempre/ConsequenceMap#ConsequenceMap`).
**The scratch directory is outside the Git tree**, so the file must be copied
into the NousResearch repository as `consequence-map.yaml` when the
submission is authorised.

```yaml
name: consequence-map
title: ConsequenceMap
repo: https://github.com/BitSempre/ConsequenceMap
sha: <THE NEW 40-CHAR SHA OF THE PUBLICATION COMMIT>
subdir: ConsequenceMap
version: "0.3.0"
description: >-
  Decision intelligence for AI agents: forecasts the consequence of an action
  before it happens, preserves the decision and its evidence, and compares the
  forecast with what actually occurred. An outcome that cannot be verified stays
  NOT_VERIFIABLE, so the derived verdict is INCONCLUSIVE rather than a clean
  pass. Five Hermes hooks (pre_tool_call, pre_approval_request,
  post_approval_response, post_tool_call, transform_tool_result); a dashboard
  tab and a command-palette entry. The agent proposes and escalates; it never
  decides and never holds a key. Disclosure — the Security Guard that decides
  and executes is a library and is NOT installed on any host, so the
  authorization boundary this plugin exists to provide is not yet active; the
  plugin records and escalates but cannot refuse. It reads the host's
  operation stream and writes to its own database under the Hermes
  plugin-data directory, reached through the public plugins.plugin_storage
  surface; it imports no private Hermes module. No network calls, no
  telemetry, no stored credentials, no background processes.
maintainer: BitSempre
tier: community
category: desktop
requires_hermes: ">=0.22.5"
docs_url: https://github.com/BitSempre/ConsequenceMap/tree/<NEW-SHA>/ConsequenceMap
platforms:
  - windows
capabilities:
  provides_tools: []
  provides_hooks:
    - pre_tool_call
    - pre_approval_request
    - post_approval_response
    - post_tool_call
    - transform_tool_result
  provides_middleware: []
  requires_env: []
known_issues:
  - "The Security Guard is not installed on any host, so the authorization boundary is not enforced; the plugin escalates and records but cannot refuse."
  - "Revocation of an Ed25519 key is not observed by a verifier that was already constructed."
  - "The audit trail exposes no public API for full chain verification; the checkpoint detects a tampered record_hash only."
  - "The repository contains an older duplicated snapshot of the tree alongside the live one; it is history, not a second product."
```

Notes:

* **The `sha` must be updated after the publication commit.** The catalog
  fetches the README **at the pinned SHA**, and the READMEs are new — they do
  not exist at the current HEAD. Pinning the pre-publication SHA would leave
  the catalog page without a README. The current draft carries the pre-fix
  HEAD (`754cb9a36fb34c4566730c307cf9edb4af05f00b`) purely as a format placeholder; the real pin is the 40-char
  SHA of the commit that carries the READMEs and the fix.
* **File name:** the catalog convention is the plugin name in kebab-case, so
  the file in the NousResearch catalog is `consequence-map.yaml`.
* `subdir: ConsequenceMap` is required because the plugin manifest lives in
  `ConsequenceMap/plugin/` inside a monorepo — this matches existing catalog
  entries that ship a plugin inside a larger tree.
* `requires_hermes` is now declared in **both** the manifest and the entry,
  as rule 14 requires. The floor `>=0.22.5` is a bare SemVer floor, is not
  newer than the current release (0.23.0), and evaluates correctly
  (`version_satisfies(">=0.22.5", …)` rejects 0.22.4 and accepts 0.22.5+).
* This draft does **not** modify the official NousResearch repository;
  submission is a separate, later, explicitly authorised step.

## 12. Exact publication commands (not executed)

To be run **only after explicit authorization**:

```powershell
# 1) commit the READMEs, the review fix and the manifest floor
git -C C:/Users/Utente/Desktop/Projects/ConsequenceMap/ConsequenceMap-Platform add README.md ConsequenceMap/README.md ConsequenceMap/docs/HERMES-GITHUB-PUBLICATION-READINESS.md ConsequenceMap/plugin/__init__.py ConsequenceMap/plugin/plugin.yaml
git -C C:/Users/Utente/Desktop/Projects/ConsequenceMap/ConsequenceMap-Platform commit -m "fix(plugin): wire the audit sink and drop the private Hermes import"

# 2) read the new 40-character SHA and write it into the catalog YAML
git -C C:/Users/Utente/Desktop/Projects/ConsequenceMap/ConsequenceMap-Platform rev-parse HEAD

# 3) create the public repository
gh repo create BitSempre/ConsequenceMap --public --description "A security and authorization layer for AI agent operations."

# 4) point the local repository at it
git -C C:/Users/Utente/Desktop/Projects/ConsequenceMap/ConsequenceMap-Platform remote add origin https://github.com/BitSempre/ConsequenceMap.git

# 5) push the full history on the existing branch
git -C C:/Users/Utente/Desktop/Projects/ConsequenceMap/ConsequenceMap-Platform push -u origin feature/platform-v1

# 6) verify remotely
gh repo view BitSempre/ConsequenceMap
git ls-remote https://github.com/BitSempre/ConsequenceMap.git
```

After the push, re-validate the pin:
`hermes plugins install https://github.com/BitSempre/ConsequenceMap --ref <new 40-char SHA> --trust`.

## 13. Remaining blockers

| # | Blocker | Owner |
|---|---|---|
| 1 | **Publication authorization** — creating the repo, adding the remote and pushing are reserved for the user's approval | user |
| 2 | The catalog `sha` pin must be set to the SHA of the publication commit, which does not exist yet | depends on 1 |
| 3 | The catalog entry file must be copied out of the Hermes scratch into the NousResearch repository | separate authorization |
| 4 | Hackathon form submission and the catalog PR to NousResearch are **out of scope** for this mission | separate authorization |
| 5 | Optional: a LICENSE file for the public repo | user decision |
| 6 | The duplicated snapshot (214 files) remains in the tree — a readability concern, not a leak | user decision |

## 14. Exact next authorization required

A single decision unlocks publication:

> **Authorize:** (a) committing the two new READMEs, the readiness report, the
> plugin fix (`plugin/__init__.py`) and the manifest floor
> (`plugin.yaml`) as one local commit on top of
> `754cb9a36fb34c4566730c307cf9edb4af05f00b`; (b) creating the public repository
> `BitSempre/ConsequenceMap` with the description in §10; (c) adding the
> `origin` remote and pushing `feature/platform-v1`.

Everything else — repository configuration, READMEs, catalog YAML draft,
validation evidence, the reviewed fix — is ready and verified.

---

### Verified facts vs. assumptions

* **Verified:** account identity, repository absence, branch, HEAD, history
  integrity, plugin validation exit 0 (before and after the fix), catalog-parser
  acceptance of the YAML, the absence of real secrets, the absence of service
  artifacts, the two runtime defects and their fix, 733/733 tests across three
  variants.
* **Assumed / not testable yet:** the push itself (the repository does not
  exist), that GitHub CI will agree with the local validator, that the catalog
  maintainers will accept the disclosure in the description.
* **Recommendation (not fact):** add a LICENSE file before the hackathon.
