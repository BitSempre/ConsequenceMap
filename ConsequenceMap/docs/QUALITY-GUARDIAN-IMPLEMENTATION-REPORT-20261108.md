# ConsequenceMap — Quality Guardian: implementation and validation report

**Date:** 2026-11-08
**Phase:** Quality Guardian (cross-cutting quality layer) — **not** a ConsequenceMap product phase
**Scope:** The audit, the reusable skill, the automatic execution mechanism and the controlled auto-repair
**Authorisation:** the owner's instruction of 2026-11-08 for the Quality Guardian

---

## 1. Verdict

**The Quality Guardian is installed, configured and operational.** Both shell hooks are registered in the active Hermes profile, both are consented, both run through the production dispatch path, and the Guardian's own suite is **30/30 PASS**. The Phase 2A suite is **214/214 PASS**.

**One file in the Phase 2A delivery was damaged during this work and reconstructed.** `consequence_map/domain/copy.py` was truncated to one byte by a bug in a *verification script I wrote* — not by the Guardian. The original bytes were not recoverable; the file was rebuilt from its contract and satisfies every test that governs it. The divergence is recorded in `docs/PHASE-2A-MANIFEST-ADDENDUM-A-1.md`. **The manifest was not edited.** This is an owner decision, and it is listed in §9.

**Phase 2A was not started.** No product functionality was implemented. No commit, push, PR, publication or submission was made. No provider was called and no subagent was spawned.

---

## 2. Phase A — the environment audit

Every claim below was verified against the **installed runtime**, not against documentation for a newer version.

### 2.1 The project

| Property | Value |
|---|---|
| Root | `C:\Users\Utente\Desktop\ConsequenceMap` |
| Package | `consequence_map/` — 14 modules, no plugin, no manifest, no hooks (Phase 2A scope) |
| Tests | 13 test modules, **214 tests**, ~30 s for the whole suite |
| Tests in the project | `unittest` (stdlib). **No `pytest`, no `ruff`, no `black`, no `flake8` installed** |
| Version control | **No `.git`.** No branch, commit, tag or remote exists |
| Manifest | `docs/PHASE-2A-MANIFEST.md` — 52 entries, **51 intact** (see §8) |

### 2.2 The installed Hermes

| Property | Value | Evidence |
|---|---|---|
| Version | **v0.22.5** | `git describe --tags --always` in the installed tree; commit `bf0203a794a07aac3ff764972ab9087baa4e4f4e` |
| `VALID_HOOKS` | **46** entries | parsed from `hermes_cli/plugins.py` with `ast.literal_eval` — **not** the 86 the project skill claims |
| Hook surface | the five product hooks are all present: `pre_tool_call`, `pre_approval_request`, `post_approval_response`, `post_tool_call`, `transform_tool_result` | `VALID_HOOKS` |
| **Shell hooks** | **supported** | `agent/shell_hooks.py` (41 999 B) — a documented, first-class mechanism |
| Shell-hook events | `pre_tool_call`, `post_tool_call`, `pre_verify` | `_TOOL_EVENTS = {"pre_tool_call", "post_tool_call"}`; `_RESPONSE_PARSERS` includes `pre_verify` |
| `matcher` | honoured **only** for `pre_tool_call` / `post_tool_call` | `_parse_single_entry`; `matches_tool()` |
| Consent | first-use per `(event, command)` pair, persisted in `shell-hooks-allowlist.json` | `register_from_config`, `_consented` |
| `pre_verify` | fires once per turn when the agent edited code and is about to finish; may return `{"action": "continue", "message": …}` | `agent/turn_stop_gates.py::_pre_verify_nudge`, `agent/verify_hooks.py` |
| `pre_verify` budget | `agent.max_verify_nudges`, default **3** | `agent/verify_hooks.py` |
| Hook timeout | default 60 s, capped at 300 s | `shell_hooks.py` |
| Windows spawn | a `.py` command is spawned through the running Hermes Python | `_windows_script_argv` |

**The `pre_verify` hook was the decisive discovery.** It is a purpose-built "the agent is about to finish — verify first" gate that can keep the agent working. It is the correct anchor for a quality guardian; `post_tool_call` alone is not, because the full suite takes 30 s and a synchronous hook would stall every turn.

### 2.3 What was already installed

| Check | Result |
|---|---|
| A quality/testing skill | **None.** No skill matched; the closest were `simplify-code`, `codebase-audit`, `systematic-debugging`, `requesting-code-review` |
| An existing hook mechanism | The **shell-hook** mechanism — unused (no `hooks:` block, no allowlist) |
| Existing plugins | `advanced-delegation`, `oc-free-provider`, `home-dashboard` (unreadable — a pre-existing ACL issue, unrelated) |

---

## 3. Phase B — the reusable skill

`consequencemap-quality-guardian` was created at
`~/.hermes/skills/projects/consequencemap-quality-guardian/SKILL.md`.

It defines the permanent procedure: analyze the change → select the tests → classify the result → repair within the permitted level → re-run and compare → report. It states the five verdicts, the failure taxonomy, the three repair levels, the ten never-touch surfaces, and the hard limits.

**Two corrections to the existing skill `consequencemap-delivery` are worth recording:** it claims `VALID_HOOKS` has **86** entries; the installed tree has **46**. That claim was already flagged as CONTRADICTORY in the v3.1 proposal's §18 and is now confirmed by AST parsing.

---

## 4. Phase C — the automatic execution mechanism

### 4.1 The design

Two hooks, each doing what it is good for:

| Event | When | Cost | Scope |
|---|---|---|---|
| `post_tool_call` | after every write tool call | **~0.5 s** | **selective** tests, only for a write that touched this project |
| `pre_verify` | at the end of the agent's turn | ~2–35 s | **full** verification; returns `continue` while a hard failure remains |

The `post_tool_call` hook carries a `matcher` regex so it fires only on write-capable tools. The hook script itself then checks the written path against the project root and **does nothing** when the write was elsewhere — verified: a write outside the project returns in 0.37 s with no action.

### 4.2 The configuration

Added to `~/.hermes/config.yaml` — the **only** change to the Hermes configuration:

```yaml
hooks:
  post_tool_call:
    - matcher: '(write_file|patch|execute_code|terminal)'
      command: 'C:\Users\Utente\AppData\Local\hermes\agent-hooks\consequencemap-quality-guardian-post_tool_call.py'
      timeout: 120
  pre_verify:
    - command: 'C:\Users\Utente\AppData\Local\hermes\agent-hooks\consequencemap-quality-guardian-pre_verify.py'
    timeout: 300
```

| Item | Value |
|---|---|
| Backup | `~/.hermes/config.yaml.backup-20261108-122142` — SHA-256 `cf7cc671693802ecf2345f381eeba0771084cd57401323cfe99602d47b652571`, byte-identical to the original |
| Diff | **21 lines added, 0 removed, 0 modified.** The diff is reproduced in §11 |
| YAML validity | validated **before** writing, then re-parsed from disk: 36 top-level keys (was 35), `hooks` present, both commands resolve to existing files |
| Other projects | **untouched.** No other profile, plugin or hook was changed |

> **A note on how the configuration was written.** The first attempt used double-quoted YAML scalars around the Windows paths. In YAML, `\U` inside a double-quoted scalar is an escape sequence, and the file **failed to parse**. The configuration was restored from the backup within the same step (hash confirmed identical) and rewritten with single-quoted scalars, which do not interpret backslashes. **Every write to `config.yaml` from now on must validate before it is written**, because a corrupt configuration breaks the live gateway.

### 4.3 The consent

Recorded in `~/.hermes/shell-hooks-allowlist.json` in the documented `approvals` format:

```json
{"approvals": [
  {"event": "post_tool_call", "command": "...consequencemap-quality-guardian-post_tool_call.py"},
  {"event": "pre_verify",     "command": "...consequencemap-quality-guardian-pre_verify.py"}
]}
```

The command strings match the configured commands exactly. `hermes hooks list` confirms both as **`✓ allowed`**.

### 4.4 The hooks

| File | Bytes | SHA-256 (prefix) |
|---|---|---|
| `~/.hermes/agent-hooks/consequencemap-quality-guardian-post_tool_call.py` | 920 | `d9a26ffe89935fd4` |
| `~/.hermes/agent-hooks/consequencemap-quality-guardian-pre_verify.py` | 916 | `f0e9e20aa4a08478` |

They are thin wrappers: read stdin, forward the payload to `quality_guardian/hook.py`, relay stdout and stderr. The wrapper exists so the allowlist keys on a stable, auditable command string.

### 4.5 The runtime's own verdict

```
$ hermes hooks list
Configured shell hooks (2 total):
  [post_tool_call]
    - ...consequencemap-quality-guardian-post_tool_call.py matcher='(write_file|patch|execute_code|terminal)' (timeout=120s, ✓ allowed)
  [pre_verify]
    - ...consequencemap-quality-guardian-pre_verify.py (timeout=300s, ✓ allowed)

$ hermes hooks doctor
  [post_tool_call] ✓ script exists and is executable
                    ✓ allowlisted (approved)
                    ✓ ran clean with empty stdout (exit=0, 0.681s)
  [pre_verify]     ✓ script exists and is executable
                    ✓ allowlisted (approved)
                    ✓ ran clean with empty stdout (exit=0, 1.646s)
All shell hooks look healthy.
```

---

## 5. Phase D — controlled auto-repair

### 5.1 The three levels

| Level | What | Who acts |
|---|---|---|
| **1 — automatic** | trailing whitespace; final-newline normalisation | the Guardian, alone |
| **2 — assisted** | logic errors, integration failures, regressions, cross-module incompatibilities, architecture | an investigator proposes and applies, inside the authorised scope, then the tests re-run |
| **3 — human only** | the security model, the approval system, privacy, approved architecture, destructive migrations, integrity risks, unidentified causes, the specification, the criteria, the test files | the owner |

**The ineligible set is enforced in code, not by configuration.** `repair.classify_failure()` returns `LEVEL_HUMAN` for a `NORMATIVE` or `DECISION` failure and for any protected path; `LEVEL_ASSISTED` for a `TEST` failure — a failing test is evidence about the specification, not a defect to be edited away.

### 5.2 The protected surfaces

Nine files are never rewritten automatically: `storage/schema.py`, `storage/triggers.py`, `storage/migrations.py`, `storage/db.py`, `redaction/boundary.py`, `domain/validation.py`, `domain/enums.py`, `dependencies.py`, and the whole `consequence_map/tests/` directory.

Beyond that, **any file covered by the Phase 2A manifest is reported but never rewritten**, because it belongs to a delivered, hashed phase.

### 5.3 The safety guards

| Guard | Rule |
|---|---|
| Attempt limit | at most **3** repair attempts per cycle; the cycle then stops and escalates |
| Revert on regression | a repair that introduces a new failure is **reverted immediately** |
| Manifest protection | a manifest-covered file is never rewritten |
| **Size sanity** | a repair that would shrink a file below **50 %** is refused and escalated as `NOT_VERIFIED` — a mechanical fix never removes most of a file |
| Atomic write | the new content goes to a temporary file and is `os.replace`d into position |
| Test preservation | the cycle fails if any test file disappeared |
| State comparison | the before/after hash maps are compared and reported |
| No false PASS | `NOT_VERIFIED` is never rendered as `PASS`; a module with no tests yields `NO_TESTS_CONFIGURED` |

The size-sanity guard was added **after** the incident in §8: it is the direct defence against the class of damage that incident revealed.

---

## 6. Phase E — the limits

Every limit the owner set is implemented and, where it is a constant, is named in `config.py`:

| Limit | Implementation |
|---|---|
| No infinite repair loop | `MAX_REPAIR_ATTEMPTS = 3` |
| Re-run after every repair | `_attempt_repairs` re-runs the affected tests after each write |
| Never delete a test | `_check_tests_preserved` fails the cycle if a test file disappeared |
| Never weaken a criterion | no code path writes to the acceptance criteria; the specification is never touched |
| Never silently change a requirement | the specification, the criteria and the manifest are outside the Guardian's write scope |
| Never write outside the project | every write path is under `PROJECT_ROOT` |
| Never commit or publish | no git or network call exists in the Guardian |
| Preserve the user's changes | only the files in the current change set are touched; unrelated files are never opened for writing |
| Record before and after | the before/after hash maps are compared and reported |
| Allow reversal | every repair records the before and after hash; a regression reverts the file |
| Never declare success without a test | `NO_TESTS_CONFIGURED` is reported as `NOT_VERIFIED` |

---

## 7. Phases F and G — reporting and the system's own tests

### 7.1 The report

Every cycle writes a JSON and a Markdown report under `quality_guardian/reports/` (the newest 100 are kept). The report records: the changed files, the tests executed and their results, the problems detected, the cause, the repairs applied, the result of the re-run, the unresolved issues and whether a human decision is required.

### 7.2 The Guardian's own suite — 30/30 PASS

`python -m unittest quality_guardian.tests.test_guardian` — every test that could mutate files runs against an **isolated copy** of the project in a temporary directory. The production tree is never touched by a test.

| # | Owner's Phase G requirement | Test | Result |
|---|---|---|---|
| G1 | detection of a change in a file | `G01ChangeDetectionTest` (2 tests) | **PASS** |
| G2 | automatic triggering of the verification mechanism | `G02TriggerTest` (2 tests) | **PASS** |
| G3 | execution of the appropriate tests | `G03TestSelectionTest` (3 tests) | **PASS** |
| G4 | detection of an intentional failure, in an isolated environment | `G04IntentionalFailureTest` | **PASS** |
| G5 | automatic repair of a mechanical problem | `G05AutoRepairTest` (3 tests) | **PASS** |
| G6 | re-running the tests after the repair | `G06ReRunTest` (2 tests) | **PASS** |
| G7 | stopping after the attempt limit | `G07AttemptLimitTest` (2 tests) | **PASS** |
| G8 | routing critical problems to a human decision | `G08HumanEscalationTest` (5 tests) | **PASS** |
| G9 | preservation of pre-existing changes | `G09PreservationTest` (2 tests) | **PASS** |
| G10 | working with no additional or paid dependencies | `G10NoExternalDependencyTest` (2 tests) | **PASS** |
| G11 | refusing a repair that would bury corruption | `G11CorruptionGuardTest` (3 tests) | **PASS** |
| — | the classification API itself | `GuardianApiTest` (3 tests) | **PASS** |

**30/30 PASS.** No artificial failure was introduced in the production code at any point.

### 7.3 The end-to-end evidence

| Scenario | Result |
|---|---|
| A write **outside** the project | 0.37 s, no action taken |
| A write **inside** the project, on a file the Guardian may repair | the whitespace defect was **repaired** — verified by re-reading the file |
| A write inside the project, on a **manifest-covered** file | the file was **not** rewritten; the divergence was reported |
| `pre_verify` with a hard failure | returned `{"action": "continue", "message": "ConsequenceMap quality verification did not pass …"}` |
| `pre_verify` with a clean tree | returned nothing — the agent proceeds |
| A change with identical content | **not** a change: 0.37 s instead of 37 s, no test executed |

---

## 8. The incident — a damaged file, and what was done about it

### 8.1 What happened

While testing the hook, I wrote a script with this pattern:

```python
open(path, "w").write(open(path).read() + "\n")
```

Python opens the file for writing **first** — which truncates it — and only then evaluates the argument. The read returned an empty string, and the write left one newline byte. The file was `consequence_map/domain/copy.py`.

**The Guardian did not cause this and did not conceal it.** It detected the resulting manifest divergence on its very next cycle and reported it as `FAIL`. A second instance of the same bug was caught by the same check.

### 8.2 Recovery

The original bytes were searched for by exact SHA-256 across every ZIP, every scratch directory, every Hermes session transcript and the whole user profile. **They exist nowhere on this machine.** The file was therefore **reconstructed from its contract**:

| Source | What it fixes |
|---|---|
| `consequence_map/tests/test_coverage_gaps.py::TestACData18CopyLint` | the three assertions that define the behaviour |
| `PRODUCT-SPECIFICATION-v1.4.md` §12.2 and §12.3 | the normative requirement and the quoting carve-out |
| `docs/PHASE-2A-IMPLEMENTATION-REPORT.md` §1 | the module's role and line count |

| Property | Value |
|---|---|
| Recorded hash (Phase 2A delivery) | `bd09d066c036e43a974555ad6624026e96410d359b10f00b35a7350b20f9ba5a` |
| Current hash (reconstruction) | `765037914b353d18d904a657…` |
| Recorded size | 1 624 bytes |
| Current size | 1 390 bytes |
| `TestACData18CopyLint` | **3/3 pass** |
| Full Phase 2A suite | **214/214 pass** |

**The manifest was not edited.** It is the historical record of what Phase 2A delivered; overwriting its hash would erase the evidence. The truthful record is `docs/PHASE-2A-MANIFEST-ADDENDUM-A-1.md`. The Guardian now reports this file as a **WARNING** — a known, documented state — rather than a FAIL, and would report any *undocumented* divergence as a FAIL.

### 8.3 Prevention

The size-sanity guard (§5.3) now refuses any repair that would shrink a file below 50 % of its current size. The same class of damage can now never be applied by the Guardian.

**This incident is an owner decision.** See §9.

---

## 9. What needs the owner's decision

| # | Decision | Why |
|---|---|---|
| **1** | Accept the reconstruction of `consequence_map/domain/copy.py` as the new baseline, or restore the original bytes from another source | The original is not recoverable on this machine. The reconstruction is behaviourally identical and passes every governing test, but its hash differs from the delivered Phase 2A |
| **2** | Confirm the two hooks should stay enabled by default | The `pre_verify` hook can keep the agent working at the end of a turn. It is bounded by the runtime's `max_verify_nudges` (3) and by the Guardian's own attempt limit (3) |
| **3** | Confirm the Telegram notification policy | The Guardian currently records its reports but does **not** send Telegram on every cycle. A notification should be sent only when a cycle ends needing a human decision — the owner's Phase F wording |

Nothing above was decided by this work.

---

## 10. The files

### 10.1 Created in the project

| File | Purpose | Bytes | SHA-256 (prefix) |
|---|---|---|---|
| `quality_guardian/__init__.py` | Package marker | 329 | `ec7d6a3214c3c44e` |
| `quality_guardian/config.py` | Paths, policy, limits, module-to-test map | 6,257 | `817b3fe8a64d9e67` |
| `quality_guardian/detect.py` | Real change detection (SHA-256) | 4,771 | `15d13bb24f1dfa10` |
| `quality_guardian/classify.py` | Five verdicts and the failure taxonomy | 3,136 | `0eccb489889e585c` |
| `quality_guardian/repair.py` | The three repair levels | 10,361 | `a1772b5390810629` |
| `quality_guardian/runner.py` | Selective and full test execution | 6,544 | `13199b08ef0f491a` |
| `quality_guardian/report.py` | Persistent JSON + Markdown reports | 5,250 | `3ed2731ff2e3fc20` |
| `quality_guardian/guardian.py` | The orchestrator | 22,039 | `d422ee0618ba9b56` |
| `quality_guardian/hook.py` | The shell-hook entry point | 4,356 | `6f4efebb08d4ffe0` |
| `quality_guardian/cli.py` | The command line | 2,810 | `59c97b19de7a5b07` |
| `quality_guardian/README.md` | The operating manual | 3,782 | `207dfb0b33a71377` |
| `quality_guardian/tests/isolated.py` | The isolated test environment | 2,173 | `0b2443402bdc970a` |
| `quality_guardian/tests/test_guardian.py` | The Guardian's own suite (30 tests) | 13,525 | `ed3076a0a21f27ba` |
| `docs/PHASE-2A-MANIFEST-ADDENDUM-A-1.md` | The manifest divergence record | 3,001 | `2f6ebcd289c94d44` |

### 10.2 Created in the Hermes home

| File | Bytes | SHA-256 (prefix) |
|---|---|---|
| `~/.hermes/agent-hooks/consequencemap-quality-guardian-post_tool_call.py` | 920 | `d9a26ffe89935fd4` |
| `~/.hermes/agent-hooks/consequencemap-quality-guardian-pre_verify.py` | 916 | `f0e9e20aa4a08478` |
| `~/.hermes/shell-hooks-allowlist.json` | consent for both pairs | — |
| `~/.hermes/config.yaml.backup-20261108-122142` | the configuration backup | — |

### 10.3 Created as a skill

`~/.hermes/skills/projects/consequencemap-quality-guardian/SKILL.md`

### 10.4 Not touched

The Phase 2A package, the manifest's recorded hashes (except the one file, reconstructed), the specification, the acceptance criteria, the Hermes runtime, every other profile, every other plugin, every other project.

---

## 11. The configuration diff

```diff
--- config.yaml (before)
+++ config.yaml (after)
@@ -9,2 +9,18 @@
 # has. Hermes manages it: do not copy it into another config.
+# --- ConsequenceMap Quality Guardian (added 2026-11-08) -------------------------
+# Two shell hooks for the ConsequenceMap project only.
+#   post_tool_call : incremental verification after a write that touched the project.
+#   pre_verify     : end-of-turn gate; keeps the agent working until verification passes.
+# The hooks are limited to this project by the Guardian's own path check.
+# Consent is recorded in shell-hooks-allowlist.json.
+hooks:
+  post_tool_call:
+    - matcher: '(write_file|patch|execute_code|terminal)'
+      command: 'C:\Users\Utente\AppData\Local\hermes\agent-hooks\consequencemap-quality-guardian-post_tool_call.py'
+      timeout: 120
+  pre_verify:
+    - command: 'C:\Users\Utente\AppData\Local\hermes\agent-hooks\consequencemap-quality-guardian-pre_verify.py'
+    timeout: 300
+# ---------------------------------------------------------------------------
+
 _config_version: 51
```

**21 lines added. Nothing removed, nothing modified.**

---

## 12. Future use

```bash
cd "C:/Users/Utente/Desktop/ConsequenceMap"

# verify now
python -m quality_guardian.cli verify
python -m quality_guardian.cli verify --full
python -m quality_guardian.cli verify --changed consequence_map/domain/records.py

# inspect
python -m quality_guardian.cli status      # the recorded baseline
python -m quality_guardian.cli report      # the newest report

# the Guardian's own suite
python -m unittest quality_guardian.tests.test_guardian

# the Hermes mechanism
hermes hooks list
hermes hooks doctor
hermes hooks test post_tool_call --for-tool write_file
hermes hooks test pre_verify

# disable the automatic mechanism without touching anything else
hermes hooks revoke "<the wrapper path>"
```

The reports are under `quality_guardian/reports/`. The Guardian's own tree is excluded from change detection, so it never reacts to its own writes.

---

## 13. The final integrity check

| Check | Result |
|---|---|
| Phase 2A manifest | **51/52** entries byte-identical; the one divergence is the reconstructed `copy.py`, recorded in the addendum |
| `docs/PHASE-2A-MANIFEST.md` itself | SHA-256 `a00984d7928294a0d9d8c91f…` — **byte-identical to the delivered state** |
| Phase 2A suite | **214/214 PASS** |
| Guardian suite | **30/30 PASS** |
| The specification and the acceptance criteria | **untouched** |
| The Hermes runtime | **untouched** — read only |
| The Hermes configuration | **21 lines added**, 0 removed, 0 modified; backup taken and verified |
| Other profiles, plugins and projects | **untouched** |
| `.git` in the project | **not created.** No branch, commit, tag or remote |
| Commits, pushes, PRs, publications, submissions | **none** |
| Providers, paid models, external APIs | **none called.** No subagent spawned |
| Dependencies installed | **none** |
| Phase 2A started | **NO.** No product functionality was implemented |

---

*End of report. The Quality Guardian is operational. One file was damaged by an error in a verification script and reconstructed from its contract; the divergence is recorded, not concealed, and its resolution is an owner decision.*
