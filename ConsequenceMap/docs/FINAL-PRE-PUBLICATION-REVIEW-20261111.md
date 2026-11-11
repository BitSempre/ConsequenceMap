# ConsequenceMap — Final Pre-Publication Review

**Date:** 2026-11-11
**Scope:** the five prepared files, plus the plugin implementation they
describe. Read-only inspection, one verified fix, no commit, no remote, no
push, no publication.
**Classification:** NOT READY FOR PRODUCTION

---

## 1. Verdict

**The prepared files were not ready to publish.** The review found **two
pre-existing runtime defects** in the plugin adapter that the official
validator cannot see, and **one factual error** in the prepared documentation
that would have misrepresented the project to an independent evaluator.

All three are now fixed and verified. The five files are ready to commit
*after* the authorisation in §10.

| Area | Before | After |
|---|---|---|
| Plugin validation | exit 0, one rule-9 warning | exit 0, **no warning** |
| Audit sink after `register()` | inert — **nothing was ever persisted** | `RepositoryAuthorizationSink` — records persist (proved end-to-end) |
| Test suite | 733 PASS | **733 PASS** (baseline, import-only variant and fixed variant all identical) |
| Guardian full cycle | 690 PASS | **690 PASS**, verdict `PASS` (299.6 s) |
| Private Hermes imports | 1 (`hermes_cli.sqlite_util.transaction`) | **0** |
| Delivery commits | intact | intact |

## 2. Exact files to be committed

Six files. Two modified, four new.

| # | File | State | Bytes | SHA-256 |
|---|---|---|---|---|
| 1 | `README.md` | new (untracked) | 1203 | `eed21706cf62abc511d9e1f90b58ab732f40a3504b75864c08d6bde21e6c0c75` |
| 2 | `ConsequenceMap/README.md` | new (untracked) | 12 363 | `fc7067afbd023587b8ad30a391991e84aac9e40bae4ec805df136f5632449821` |
| 3 | `ConsequenceMap/docs/HERMES-GITHUB-PUBLICATION-READINESS.md` | new (untracked) | 20 119 | `29fd08a24c884cd0615f00f412a23e8640e29165b3ff08a970d132b7974ccfab` |
| 4 | `ConsequenceMap/docs/FINAL-PRE-PUBLICATION-REVIEW-20261111.md` | new (untracked) | this report | see below |
| 5 | `ConsequenceMap/plugin/__init__.py` | **modified** | — | `4124be689f356a58fd3411d8c55fd5f353816292d6bdcb8ac838c80828edb0e8` |
| 6 | `ConsequenceMap/plugin/plugin.yaml` | **modified** | — | `b43d5b455ec9a0c59a4f6cb0b3e4de15621c8dba7c6b35c71c3c68ab51e125cd` |

`ConsequenceMap/plugin/plugin.yaml` was already tracked; the four others were
not. Nothing is staged. The branch is `feature/platform-v1` at
`754cb9a36fb34c4566730c307cf9edb4af05f00b`, 60 commits, no tags, **no remote**.

> The catalog draft `consequencemap.yaml` is **not** in this list: it lives in
> the Hermes scratch, outside the Git tree. It must be copied into the
> NousResearch repository at submission time, not into this one.

### 2a. Working tree state

```
 M ConsequenceMap/plugin/__init__.py
 M ConsequenceMap/plugin/plugin.yaml
?? ConsequenceMap/README.md
?? ConsequenceMap/docs/FINAL-PRE-PUBLICATION-REVIEW-20261111.md
?? ConsequenceMap/docs/HERMES-GITHUB-PUBLICATION-READINESS.md
?? README.md
```

Nothing is staged. The four Guardian report files that the verification
cycles generated during this review were **moved to the Hermes scratch**
(`cm-review-guardian-artifacts-20261111/`) rather than deleted, and the
tracked `quality_guardian/state/last-seen.json` was restored to its HEAD
state, so the commit scope is exactly the six files above and nothing else.

Re-compute the hashes before committing.

## 3. Complete diff summary

Two tracked files changed, 7 insertions and 13 deletions in total. No test
file, no security control and no configuration was touched.

### 3.1 `ConsequenceMap/plugin/__init__.py`

```diff
@@ -63,20 +63,13 @@ def register(ctx: Any) -> None:
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
@@ -89,7 +82,7 @@ def register(ctx: Any) -> None:
             connection = db_module.connect()
             apply_migrations(connection)
             repository = Repository(connection)
-            HookState.STATE.sink = RepositoryAuthorizationSink(repository)
+            STATE.sink = RepositoryAuthorizationSink(repository)
         except Exception:
             logger.warning(
                 "ConsequenceMap: the database is unavailable; the "
```

### 3.2 `ConsequenceMap/plugin/plugin.yaml`

```diff
@@ -8,3 +8,4 @@ provides_hooks:
   - post_approval_response
   - post_tool_call
   - transform_tool_result
+requires_hermes: ">=0.22.5"
```

### 3.3 The four new documentation files

| File | Content |
|---|---|
| `README.md` | repository landing page: what it is, the `NOT READY FOR PRODUCTION` banner, install snippet, layout table |
| `ConsequenceMap/README.md` | the full public README: what it does, architecture, security model, installation, testing, development status split three ways, limitations table, responsible-use warnings |
| `ConsequenceMap/docs/HERMES-GITHUB-PUBLICATION-READINESS.md` | the full readiness report: account verification, repository existence, git state, secret scan, plugin compatibility, proposed configuration, the catalog draft, exact publication commands, blockers, the next authorisation |
| `ConsequenceMap/docs/FINAL-PRE-PUBLICATION-REVIEW-20261111.md` | this review: the two defects, the private-import assessment, the manifest compatibility analysis, the catalog assessment, the verification evidence and the outstanding risks |

## 4. Plugin validation result

**Official command, re-run on the real tree after the fix:**

```
hermes plugins validate ConsequenceMap/plugin/     →  exit code 0
```

| Check | Result |
|---|---|
| manifest — plugin.yaml parses | ✓ |
| manifest fields — name, version, description present | ✓ |
| **requires_hermes — spec '>=0.22.5' parses** | ✓ (previously "not declared") |
| loadable — entry: `__init__.py`, `desktop/plugin.js` | ✓ |
| capability probe — `register()` ran in isolation | ✓ |
| declared tools / hooks / middleware | ✓ all match the registrations |
| security scan | ✓ safe |
| no core override | ✓ |
| desktop surface | ✓ inside the plugin SDK surface |
| **private core imports (rule 9)** | **⚠ before the fix → gone after** |

The validator's own message before the fix was:
`__init__.py:71 hermes_cli.sqlite_util.transaction. Use ctx.* / documented
plugin APIs, or open an issue for the seam you need.`

## 5. Private import assessment

### 5.1 What the import was trying to do

`plugin/__init__.py` wanted to install a shared connection provider so the
plugin's writes would use the host's connection:

```python
from hermes_cli.sqlite_util import transaction as hermes_transaction
def hermes_provider(path):
    return hermes_transaction(provider=path)
db_module.set_connection_provider(hermes_provider)
```

### 5.2 Why it never worked — three independent reasons

1. **Wrong signature.** The installed Hermes 0.23.0 defines
   `transaction(conn: sqlite3.Connection, *, immediate: bool = False)`. It
   takes a **connection**, not a `provider=` keyword. Calling it as written
   raises `TypeError: transaction() got an unexpected keyword argument
   'provider'` — reproduced directly.
2. **Wrong contract.** Even with the correct signature it could not work:
   `transaction()` is a context manager that yields a connection and then
   **closes** it in its `finally` block. It cannot serve as a connection
   provider. The package's own `storage/db.py` documents this exact hazard:
   *"the host's `hermes_cli.sqlite_util.transaction()` always closes the
   connection … which would break the multi-statement seal."*
3. **Unreachable.** `db_module` is referenced on line 74 but imported on line
   85. The line raised
   `NameError: cannot access local variable 'db_module' where it is not
   associated with a value`, which the surrounding `except Exception` turned
   into a log warning.

So the private import was dead code that could never have worked, hidden
behind a broad `except Exception`.

### 5.3 A supported public alternative exists

| | |
|---|---|
| Public alternative | `plugins.plugin_storage.plugin_db` |
| Evidence it is public | it is in the validator's `_PUBLIC` set (89 entries); `_private_target("plugins.plugin_storage", "plugin_db", …)` returns *public*, while the same call for `hermes_cli.sqlite_util.transaction` returns *private* |
| Evidence it was already in use | `storage/db.py::hermes_connection_provider` uses it; it sets `row_factory=None` (rows are tuples) and `foreign_keys=True` (the composite FK is enforced) — the same guarantees the private path was meant to provide |
| Behaviour difference | none that matters: the private path never executed, so removing it is behaviour-preserving by construction, and the public path was already the one in force |

### 5.4 Why the import was replaced rather than merely warned about

The import was not just a lint warning — it **shadowed the working public
path**. Because the block ran (and failed) *before* the package's own default
provider was used, the plugin's own database provider was being replaced by a
broken one. Removing it restores the documented, public, already-tested path.

**The replacement was proven before it was applied** (§7).

### 5.5 The second defect the warning led to

Inspecting the block rather than accepting the warning uncovered a more
serious defect two lines below it.

`plugin/__init__.py:92` read:

```python
HookState.STATE.sink = RepositoryAuthorizationSink(repository)
```

`STATE` is a **module-level object** in `consequence_map/hooks.py` (line 268),
not a class attribute of `HookState`. The line raised
`AttributeError: type object 'HookState' has no attribute 'STATE'` — again
swallowed by the same `except Exception`.

**Consequence:** after `register()`, the active sink was still the **inert**
`AuthorizationSink`. The plugin loaded, created and migrated its 17 database
tables, and then recorded **nothing**. No authorization was ever persisted.
Measured on the unfixed tree:

```
sink activo apos register(): AuthorizationSink        (not RepositoryAuthorizationSink)
host_authorization rows: 0    proposal rows: 0    forecast rows: 0
```

This is the plugin's whole reason for existing: *"the authorization the human
gave has to reach the database, or the product has no record of it."* The
official validator cannot detect it — it checks the manifest, the
registrations and the import surface, but never asserts that the sink is
attached after registration.

**Both defects predate the current HEAD.** They were introduced together in
commit `2377965` and are present at `754cb9a`. Neither was caused by the
publication preparation.

## 6. Manifest compatibility — `requires_hermes: ">=0.22.5"`

### 6.1 Is the floor correct?

| Check | Result |
|---|---|
| SemVer floor, not a CalVer date | ✓ `>=0.22.5` |
| Not newer than the current release | ✓ current release is 0.23.0 |
| Bare floor, no upper bound | ✓ — the catalog's convention (43 entries use `>=0.22.5`; the largest floor used is `>=0.22.5`) |
| Evaluates correctly | ✓ `version_satisfies(">=0.22.5", …)`: rejects 0.22.4, accepts 0.22.5 / 0.22.6 / 0.23.0 / 0.24.0 / 1.0.0 |
| Parser accepts the field | ✓ `✓ requires_hermes — spec '>=0.22.5' parses` |
| Loader enforces it | ✓ `requires_hermes_error()` returns *load-blocking* when the running version does not satisfy the spec |

### 6.2 Is it in the right place?

**Yes, and now it is in both places, as the catalog requires.** Rule 14 of the
official catalog policy states:

> *"Declare the same floor in `plugin.yaml` as well, because older Hermes
> versions enforce only that one (the loader skips the plugin when it does not
> match)."*

The entry declared `>=0.22.5` but the manifest did not, so an older Hermes
would enforce **no** floor. The manifest now declares the same value.

### 6.3 Does the plugin actually need a 0.22.5 floor?

The plugin uses only documented surfaces: `ctx.register_hook`,
`ctx.register_command` (both in `PluginContext`), `plugins.plugin_storage`,
`hermes_cli.config` and `hermes_constants`. It imports **no** private Hermes
module after the fix. `>=0.22.5` is the conservative floor: it matches the
Phase 2A manifest's own stated floor and is the highest floor already in use
across the catalog, so it cannot exclude a host that would have worked.

## 7. Verification of the fix

Every change was proven in an isolated copy before it was applied to the real
tree.

| Verification | Result |
|---|---|
| Test suite, real tree, **before** any change (baseline) | 733 run, **0 failures** |
| Test suite, isolated copy, **import removed only** | 733 run, **0 failures** — behaviour-equivalent |
| Test suite, isolated copy, **both fixes** | 733 run, **0 failures** |
| Test suite, real tree, **after both fixes** | 733 run, **0 failures** |
| Official validation, isolated copy | exit 0, rule-9 warning gone |
| Official validation, real tree | exit 0, rule-9 warning gone |
| Sink after `register()`, before the fix | `AuthorizationSink` (inert) |
| Sink after `register()`, after the fix | `RepositoryAuthorizationSink`, with a live repository |
| **End-to-end write**, after the fix | 1 row in `host_authorization`, `sink.failures == 0` |
| **Guardian full cycle** (`runner.run_full_suite`) | **690 passed, 0 failed, 0 errors, verdict `PASS`**, 299.6 s |

Suite breakdown (identical in all four runs):
`consequence_map` 556 · `consequence_guard` 134 · `quality_guardian` 41 ·
`host_tests` 2 — **733 tests, 0 failures**.

### 7.1 The protected surfaces are byte-identical

| File | State vs HEAD |
|---|---|
| `consequence_map/authorization.py` | identical |
| `consequence_map/correlation.py` | identical |
| `consequence_map/paths.py` | identical |
| `consequence_guard/crypto.py` | identical |
| `consequence_guard/store.py` | identical |
| `consequence_guard/service.py` | identical |
| `quality_guardian/config.py` | identical |
| `quality_guardian/state/repair-policy.json` | identical — SHA-256 `52f60c0afb16746a54c32a31b96c53f64eaa48ff074641966ec610f5c6c3b129`, `auto_repair: false` intact |

No cryptographic, authorization, executor, nonce, replay or revocation code
was modified. DEC-16 was not touched. No ZIP or `SHA256SUMS.txt` was touched.

## 8. Catalog YAML assessment

### 8.1 The parser accepts it

Checked against the **real** Hermes 0.23.0 catalog parser
(`entry_from_mapping`), not by inspection:

| Field | Value | Check |
|---|---|---|
| `name` | `consequence-map` | no collision in the 1051 local entries |
| `repo` | `https://github.com/BitSempre/ConsequenceMap` | exactly the required URL |
| `sha` | 40 hex characters | matches `_SHA_RE` (`^[0-9a-f]{40}$`) |
| `subdir` | `ConsequenceMap` | required — the manifest is at `ConsequenceMap/plugin/` |
| `maintainer` | `BitSempre` | ✓ |
| `tier` / `category` | `community` / `desktop` | both valid; 225 entries use `desktop` |
| `requires_hermes` | `>=0.22.5` | matches the manifest |
| `platforms` | `windows` | ✓ |
| `capabilities.provides_hooks` | the 5 declared hooks | matches the manifest |
| `known_issues` | 4 entries | all accurate |

`install_identifier` resolves to
`https://github.com/BitSempre/ConsequenceMap#ConsequenceMap`.

### 8.2 The SHA pin needs to change — a defect in the previous draft

The catalog fetches **the README at the pinned SHA**. The READMEs are new and
**do not exist at the current HEAD**:

```
README.md                     -> does not exist at 754cb9a
ConsequenceMap/README.md      -> does not exist at 754cb9a
```

Pinning the pre-publication SHA would leave the catalog page with no README
to render. **The pin must be set to the 40-character SHA of the commit that
carries the READMEs and the fix** — which does not exist yet.

The draft therefore carries a `<THE NEW 40-CHAR SHA OF THE PUBLICATION
COMMIT>` placeholder, and §10 makes "read the new SHA and write it into the
YAML" an explicit step of the publication sequence. The previously reported
value `754cb9a36fb34c4566730c307cf9edb4af05f00b` was a valid 40-char SHA of a
real commit, but it was the wrong commit for this purpose.

### 8.3 The file name

The catalog convention is the plugin name in kebab-case, so the file in the
NousResearch repository is **`consequence-map.yaml`**. The mission brief wrote
`consequencemap.yaml`; the kebab form is what the catalog tooling expects.

## 9. Security and publication checks

### 9.1 Secret and sensitive-file scan

Run over the five in-scope files and over the tracked tree.

| Check | Result |
|---|---|
| Real credentials in tracked files | **none.** The only token-like strings are deliberately **truncated test fixtures** in `consequence_map/redaction/tests/test_redaction.py` (`ghp_ab…2345` — a 28-char redaction unit, not a 36/37-char valid token; `BEGIN RSA PRIVATE KEY` header with no body, used as a redaction-pattern target) |
| In-scope files: tokens, private keys, passwords, emails, chat ids | **none.** The two regex hits are the descriptive mention of that fixture and the two documented local paths in the readiness report |
| `.env`, `*.pem`, `*.key`, service credential files | none tracked |
| Windows service artifacts | `C:\ProgramData\ConsequenceMap` and the `ConsequenceMapGuardSvc` account do not exist — nothing to leak |
| `__pycache__` / `*.pyc` | present on disk, **not tracked** |
| Stale delivery ZIP + `SHA256SUMS.txt` | tracked; the archive's inner content verifies against its manifest; `SHA256SUMS.txt` records an earlier delivery. **Left untouched by rule** |
| Duplicated snapshot / old backup | 214 + 12 tracked files; history, not a leak; left in place |

**No credential, private information or temporary file will be published.** The
two local paths in the readiness report (`C:\Users\Utente\…`) are the
documented project locations — informative for a reviewer, not sensitive. They
can be removed if you prefer a path-free document.

### 9.2 The original delivery commits remain intact

| Commit | Full SHA | Subject |
|---|---|---|
| `5920406` | `59204069fda5532889d28f0154e8ce2dda678bcd` | chore(guardian): the closing verification cycle, recorded |
| `01a3b85` | `01a3b85904c7a635229d40dac037a2b802703de2` | feat(security): strengthen Quality Guardian and fail-closed policy |
| `754cb9a` | `754cb9a36fb34c4566730c307cf9edb4af05f00b` | docs(delivery): the final delivery report |

The reflog contains only those three commits — no reset, rebase, amend,
squash or rewrite. `git fsck` reports only dangling blobs (normal after a
checkout), no corruption. The tree is unchanged apart from the two modified
plugin files.

### 9.3 GitHub state, re-verified

| | |
|---|---|
| Authenticated account | `BitSempre` (confirmed via `gh api user`) |
| `BitSempre/ConsequenceMap` | **still does not exist** (404, re-checked) |
| Local remotes | **none** — no `origin`, no upstream |
| Pushed anything | **no** |

## 10. Outstanding risks

| # | Risk | Severity | Owner |
|---|---|---|---|
| 1 | The catalog `sha` pin must be updated to the publication commit's SHA; a stale pin renders no README | **high** (blocks the catalog page, not the install) | resolved by making it an explicit step in the publication sequence — the draft now carries a placeholder |
| 2 | The **Security Guard is not installed on any host**. The authorization boundary this plugin exists to provide is not active. Disclosed in the README, the YAML description and `known_issues`. | **high** (inherent, documented) | owner decision — ADR-002 has the procedure |
| 3 | Revocation of an Ed25519 key is not observed by an already-constructed verifier | medium (documented, unchanged) | owner decision |
| 4 | No public API for full audit-chain verification | medium (instrumentation gap, unchanged) | owner decision |
| 5 | The repository carries a duplicated 214-file snapshot of the tree | low (readability, not a leak) | owner decision |
| 6 | `SHA256SUMS.txt` is stale | low (archive content verifies) | needs repacking → own authorisation |
| 7 | The plugin declares `platforms: [windows]` in the catalog entry while the library itself is stdlib-only and cross-platform | low (the entry is conservative; the plugin runs on Windows) | owner decision |
| 8 | No LICENSE file in the repository | low (admission may prefer one) | owner decision |

Nothing in this list was introduced by this review.

### 10.1 The Guardian's own verdict

`quality_guardian.cli verify --full --json` returns the global verdict
**`WARNING`** and exit code 1. That is the **pre-existing, documented**
verdict: exactly one check produces it.

| Check | Verdict |
|---|---|
| `phase-2a-manifest-integrity` | **WARNING** — 3 manifest divergences, all documented in an addendum: `consequence_map/__init__.py`, `consequence_map/domain/copy.py`, `consequence_map/storage/schema.py` |
| every `tests:*` check | PASS |
| `tests-preserved` | PASS — no test file was removed |
| `state-comparison` | PASS — 0 files differ from the pre-cycle state |
| `repairs` / `repair_attempts` | `[]` / `0` — no automatic repair was attempted |

This is the same WARNING that was accepted on 2026-11-10 in
`docs/QUALITY-GUARDIAN-WARNING-ACCEPTANCE-20261110.md`. It concerns three
Phase 2A files that this review did not touch, and the acceptance document
records why it is a recorded divergence rather than a regression. The
Guardian's *test* verdict is `PASS` (690/690).

## 11. Exact next authorisation required

One decision unlocks publication:

> **Authorise:** (a) committing the six files of §2 as a **single local
> commit** on top of `754cb9a36fb34c4566730c307cf9edb4af05f00b`; (b) creating
> the public repository `BitSempre/ConsequenceMap` with the description
> *"A security and authorization layer for AI agent operations."*; (c) adding
> the `origin` remote and pushing `feature/platform-v1`.

After (a) and (c), one more mechanical step follows, which needs no new
decision: read the new 40-character SHA and write it into the catalog YAML
before submitting it.

The publication sequence, with the exact commands, is in
`ConsequenceMap/docs/HERMES-GITHUB-PUBLICATION-READINESS.md` §12.

---

### Facts vs. assumptions

**Verified:** the two defects and their root causes; the public alternative and
its status in the validator's `_PUBLIC` set; 733/733 tests across four runs;
official validation exit 0 before and after; the manifest floor's semantics and
enforcement; the catalog parser's acceptance of the YAML; the absence of
private Hermes imports after the fix; the end-to-end persistence of an
authorization; the byte-identity of every protected surface; the delivery
commits' integrity; the repository's continued absence from GitHub.

**Not yet testable:** the push itself and the catalog page's rendering — both
require the repository to exist.

**Assumptions carried forward:** that the catalog maintainers accept the
disclosure in the description, and that GitHub CI agrees with the local
validator (it should — the local validator already reports the same rule-9
finding the CI does, and it is now gone).
