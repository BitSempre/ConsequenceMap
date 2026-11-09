# ConsequenceMap — Quality Guardian: final consolidated specification
## M-1 to M-4 + Step 0 + P-1 to P-4 + T-24 to T-30 + N1 safety

**Date:** 2026-11-08
**Nature:** Specification, analysis and decision preparation. **No code, test, configuration, hook, allowlist, manifest, baseline or protected artefact was modified.** The only file this task created is this document.
**Inputs:** `QUALITY-GUARDIAN-M1-M4-TECHNICAL-REMEDIATION-PLAN-20261108.md`, `QUALITY-GUARDIAN-M1-M4-FINAL-DECISION-REVIEW-20261108.md`, `QUALITY-GUARDIAN-POST-INCIDENT-SECURITY-AUDIT-20261108.md`, `QUALITY-GUARDIAN-IMPLEMENTATION-REPORT-20261108.md`, `PHASE-2A-MANIFEST.md`, `PHASE-2A-MANIFEST-ADDENDUM-A-1.md`
**Classification:** **READY WITH OPEN QUESTIONS**

---

## 1. Executive summary

*Secção 1 — Resumo executivo.*

This document is the single, consolidated specification for the remediation of the ConsequenceMap Quality Guardian. It absorbs the technical remediation plan, the final adversarial decision review, the post-incident security audit, and the implementation report into one coherent body of work, and it resolves the two documents' disagreements against the **installed source** and the **real Phase 2A manifest** rather than against each other.

**What the remediation is.** Four recommendations, M-1 to M-4, close the four findings that make the Guardian unsafe to trust with automatic repair:

| Recommendation | Closes | Substance |
|---|---|---|
| **M-1** | F-01, F-02 | the manifest check must assert over the **expected** rows, not the **found** rows |
| **M-2** | F-03, F-06 | artefact-identity validation on the write path, with a pre-write hash revalidation (TOCTOU) |
| **M-3** | F-04 | the suspension must be a **reported state**, never an uncaught exception |
| **M-4** | F-05 | the protection must be **identity-based**, not a textual prefix comparison |

**The decisive structural facts.** Two facts, both re-verified against the installed code, determine the whole shape of the work:

1. **The write surface is one function.** `quality_guardian/repair.py::write_file_text` is the only function that writes to a project source file. Every repair path reaches it. This is why the suspension works today, and why M-2 and M-3 can be implemented at one choke point rather than across the codebase.
2. **The write path is not root-aware.** `write_file_text` calls `config.auto_repair_enabled()` **without a `root` argument**, so it consults the **production** `PROJECT_ROOT` policy even when the caller is working inside an isolated temporary tree. Measured directly:

   ```
   auto_repair_enabled(<temp root>)  -> True      (the isolated tree has no policy file)
   auto_repair_enabled()             -> False     (the production tree does)
   write_file_text(...)              -> RepairSuspended
   ```

   This is not a defect of the suspension. It is a defect of the **scope of the check**, and it is the **direct cause** of the Guardian's own 29/30 result (§8.2). It is therefore **Step 0**, a prerequisite — not a by-product of M-2.

**This document corrects the two documents it consolidates.** Both prior documents are sound in their recommendations, and this document adopts their conclusions. But four of their **supporting claims** do not survive inspection of the real code and the real manifest. Each correction is recorded with its evidence in §3, and each one changes a concrete implementation instruction:

| # | Prior claim | Verified reality | Consequence |
|---|---|---|---|
| **C-1** | the current manifest regex does **not** match the four-column table, so the *current* code already excludes it | the current regex ends in `` \s*\| ``, **not** `` \|\s*$ `` — it matches **all 13** rows of the four-column table, and captures **52** rows in total | the "expected set" for M-1 is **52** entries, not 39. The 13 Desktop artefacts are legitimately protected and are already verified. P-1's scoping rule must accept **both** real entry tables |
| **C-2** | the manifest covers "32 + 4 + 10 + 19 Desktop artefacts" | the real composition is **32 + 2 + 5 + 13 = 52** | the M-9 arithmetic and the "additional files" scope must use the corrected numbers |
| **C-3** | a naive "tree minus manifest" reports "~10 legitimate files" as additional | under the three manifest-covered prefixes, the real unlisted set is **exactly 2**: the manifest itself and its addendum | the additional-files scope becomes a clean, zero-today, exemption-based rule |
| **C-4** | `repair_is_sane("A"*1000, "B"*1000)` is an escape because `"B"*1000` is a `SyntaxError` | `"B"*1000` **compiles** — it is a valid expression statement | F-03 stands, but its canonical example is wrong and is replaced with a genuinely invalid same-length candidate |

Four further corrections are recorded in §3 as well, covering the N1 literal case (C-5), the `is_protected` disagreement (C-6), the `pre_verify` nudge scope (C-7), and the `changed`-flag accounting in the N1 transformation (C-8).

**What is required to proceed.** Authorisation to implement (D-1), confirmation that the suspension holds through the whole sequence (D-2), and one owner decision that no evidence can settle (D-9, the `copy.py` divergence). Nine further decisions carry a technical recommendation that can simply be followed. Nothing in this document authorises anything; §14 lists what the owner is being asked to decide.

**This is a specification, not an implementation.** M-1 to M-4 have **not** been implemented. The automatic repair **remains suspended**. The Phase 2A manifest, the addendum A-1 and `copy.py` are **byte-identical** to their state at the start of this task, verified by SHA-256 after every step.

---

## 2. Confirmed current state

*Secção 2 — Estado atual confirmado.*

Every statement in this section was verified during this task by inspection or by a **read-only** execution. Where a number is quoted, it was measured, not inherited.

### 2.1 The suspension

| Property | Value |
|---|---|
| Policy file | `quality_guardian/state/repair-policy.json` — 462 B, SHA-256 `52f60c0afb16746a54c32a31` |
| `auto_repair` | **`false`** |
| `reason` | *"post-incident security audit 2026-11-08: automatic repair suspended pending owner decision; detection, testing and reporting remain active"* |
| `suspended_at` | `2026-11-08T12:45:00Z` |
| `suspended_by` | `post-incident security audit` |
| `reversible` | `true` |
| `reactivation_requires` | *"explicit owner authorisation"* |
| `scope` | *"automatic N1 repair only; detection, test execution, reporting and baseline recording are unaffected"* |

The suspension is in force and was **not** altered during this task.

### 2.2 The choke point

`quality_guardian/repair.py::write_file_text` — the only function that writes to a project source file:

```python
def write_file_text(path: Path, content: str) -> bool:
    # Write the file atomically. Returns True on success.
    # This is the ONLY function in the Guardian that writes to a project
    # source file, so it is the single choke point for the automatic-repair
    # capability.
    if not config.auto_repair_enabled():          # <-- no root argument
        raise RepairSuspended(
            "automatic repair is suspended by the repair policy; "
            "no file was written"
        )
    try:
        tmp = path.with_suffix(path.suffix + ".guardian-tmp")
        tmp.write_text(content, encoding="utf-8", newline="\n")
        os.replace(tmp, path)
        return True
    except OSError:
        return False
```

### 2.3 `RepairSuspended` — confirmed uncaught

`RepairSuspended` appears in exactly **two** places in the Guardian: its definition and the `raise` above. **No module catches it.**

| Caller | Current behaviour | Verified |
|---|---|---|
| `quality_guardian/hook.py` | caught by the outer `except Exception:` in `main()` — the hook returns 0 and the turn continues, **but no report is written**, because the cycle aborted before `finalize` | by inspection |
| `quality_guardian/cli.py` | **not caught** — the file contains **zero** `except` and **zero** `try` clauses; the exception propagates and the command aborts with a traceback | by inspection |
| `quality_guardian/guardian.py::_attempt_repairs` | **not caught** — the call `if not repair.write_file_text(path, fixed):` is unguarded | reproduced (traceback below) |

### 2.4 The hooks

| Property | Value |
|---|---|
| Registered | `post_tool_call` (matcher `(write_file\|patch\|execute_code\|terminal)`, timeout 120 s) and `pre_verify` (timeout 300 s) |
| Consent | both `✓ allowed` in `shell-hooks-allowlist.json` (368 B) |
| `config.yaml` | SHA-256 `85b8f48f71257a46819053d8cb74acdd019e1d439363d6c4621d962a519f9ed9` — **unchanged** |
| Allowlist | SHA-256 `0faf6e9c07b1016e6637732cf4b87c31dd5e8c02649c44285197d5de36d63bd3` — **unchanged** |
| Wrappers | `~/.hermes/agent-hooks/consequencemap-quality-guardian-post_tool_call.py` and `…-pre_verify.py` — unchanged |
| `pre_verify` directive | emitted only for `FAIL`, `NOT_VERIFIED`, `BLOCKED` — **never** for `WARNING` |

### 2.5 The Guardian's own suite — **29/30 PASS, 1 ERROR**

Measured in this task, in the isolated environment, with the production tree untouched:

```
Ran 30 tests in 7.298s
FAILED (errors=1)
```

The single error, reproduced with its full traceback:

```
ERROR: test_the_cycle_re_runs_the_tests_after_a_repair
  test_guardian.py", line 141, in test_the_cycle_re_runs_the_tests_after_a_repair
    cycle = guardian.run_cycle(trigger="g06", root=self.root)
  guardian.py", line 357, in run_cycle
    _attempt_repairs(cycle, base)
  guardian.py", line 486, in _attempt_repairs
    if not repair.write_file_text(path, fixed):
  repair.py", line 282, in write_file_text
    raise RepairSuspended(...)
quality_guardian.repair.RepairSuspended: automatic repair is suspended by the repair policy; no file was written
```

| | |
|---|---|
| Classes | **12** — `G01ChangeDetectionTest`, `G02TriggerTest`, `G03TestSelectionTest`, `G04IntentionalFailureTest`, `G05AutoRepairTest`, `G06ReRunTest`, `G07AttemptLimitTest`, `G08HumanEscalationTest`, `G09PreservationTest`, `G11CorruptionGuardTest`, `G10NoExternalDependencyTest`, `GuardianApiTest` |
| Test methods | **30** (counted by parsing the file, not estimated) |
| Skipped / expected-failure | **0** — no `@unittest.skip`, no `skipTest`, no expected-failure marker |
| Current result | **29 PASS, 1 ERROR** |
| The error | `G06ReRunTest.test_the_cycle_re_runs_the_tests_after_a_repair` |

**The failing test is not a defect in the Guardian's logic and must not be removed or weakened.** It asserts that a repair is applied; the policy forbids it. §8 specifies how it must be rewritten to test the suspension correctly.

### 2.6 The Phase 2A suite

| Scope | Result | Time |
|---|---|---|
| `unittest discover -s consequence_map` | **214/214 PASS — `OK`** | 34.1 s |
| `unittest discover -s . -p "test_*.py"` (project root) | 244 tests, **1 error** (the G06 error above) | 45.1 s |

The two suites **overlap** when discovered from the project root: 214 + 30 = 244. The Phase 2A suite alone is 214 and is green. The `copy.py` contract module `test_coverage_gaps` is included in that 214.

### 2.7 Manifest and historical integrity

Measured by hashing every entry the manifest declares, resolving each against the project root first and the Desktop second:

| | |
|---|---|
| Rows the Guardian's current regex captures | **52** — 39 from the manifest's first table, 13 from its four-column table |
| Entries that resolve to a file | **52 / 52** — none absent |
| Hash matches | **51** |
| Divergent | **1** — `consequence_map/domain/copy.py`, the known reconstruction |
| **`docs/PHASE-2A-MANIFEST.md`** | SHA-256 `a00984d7928294a0d9d8c91f…` — **byte-identical** |
| **`docs/PHASE-2A-MANIFEST-ADDENDUM-A-1.md`** | SHA-256 `2f6ebcd289c94d44afe31c6e…` — unchanged, 3 001 B |
| **`consequence_map/domain/copy.py`** | SHA-256 `765037914b353d18d904a657…` — **not touched** |
| `quality_guardian/state/last-seen.json` | SHA-256 `8c46fd54eb8385de1e515dbc…` — unchanged by this task |
| `quality_guardian/state/repair-policy.json` | SHA-256 `52f60c0afb16746a54c32a31` — unchanged |
| `.git` in the project | **does not exist** — the tree is not version-controlled |

**The single divergence is `consequence_map/domain/copy.py`.** It is a **reconstruction from its contract**, not a byte-for-byte recovery. The original manifest hash is deliberately preserved and the addendum records the divergence, which is why the check reports `WARNING` and not `FAIL`. **The reconstruction is not accepted as a baseline** by this document.

### 2.8 The functions the remediation would touch

| Function | File | Current signature | Called from |
|---|---|---|---|
| `_check_manifest_integrity` | `guardian.py` | `(root: Path, cycle=None)` | `run_cycle` — **twice**: on the no-change path and on the main path after repairs |
| `_documented_divergences` | `guardian.py` | `(root: Path)` | `_check_manifest_integrity` |
| `_check_tests_preserved` | `guardian.py` | `(before: dict, after: dict)` | `run_cycle` |
| `_attempt_repairs` | `guardian.py` | `(cycle: Cycle, root: Path)` | `run_cycle` |
| `finalize` | `guardian.py` | `(cycle: Cycle, root: Path = None)` | `hook.py`, `cli.py` |
| `apply_level1_fixes_in_project` | `repair.py` | `(path, source, project_rel=None)` | `_attempt_repairs` |
| `apply_level1_fixes` | `repair.py` | `(path, source)` | `apply_level1_fixes_in_project` |
| `repair_is_sane` | `repair.py` | `(original: str, fixed: str)` | `_attempt_repairs` |
| `write_file_text` | `repair.py` | `(path: Path, content: str)` | `_attempt_repairs` — twice: apply and revert |
| `is_manifest_protected` | `config.py` | `(rel_path: str)` | `apply_level1_fixes_in_project` |
| `is_protected` | `config.py` | `(path)` | `classify_failure` |
| `auto_repair_enabled` | `config.py` | `(root: Path = None)` | `write_file_text` (**no root**), `_attempt_repairs` (with root) |

### 2.9 The environment facts that shape the tests

| Fact | Value | Why it matters |
|---|---|---|
| Search roots | project root, then the **hard-coded** `C:\Users\Utente\Desktop` | the fallback root is not configurable; on another host it yields 13 false "missing" files. See AC-M1-7 |
| `detect.sha256_of` | returns `""` on `OSError`/`ValueError` | an unreadable file hashes to `""`, is compared against the expected hash, and is counted as **divergent** → `FAIL`. The reason is mislabelled. See §5.1 |
| `detect.tracked_files` | excludes the Guardian's own tree and `EXCLUDED_DIRS`; suffixes `.ini .txt .json .cfg .yml .toml .md .py .yaml` | the Guardian's own tree never appears in the baseline or in the "additional files" set |
| Baseline `last-seen.json` | **42** entries, **5** under `docs/`, **0** under `quality_guardian/` | three of the five `docs/` entries are not manifest entries |
| Report path | `base / "quality_guardian" / "reports"`, created with `mkdir(parents=True, exist_ok=True)` | the deterministic failure injection for T-15 (P-4) is portable: see §9 |
| `is_protected` protected set | `PROTECTED_PATH_PATTERNS` (8 files) + `PROTECTED_DIRS` (`consequence_map/tests`) | `copy.py` is **not** in it — see C-6 |
| Rollback backup | `…\hermes\cache\scratch\qg-pre-suspension-20261108-124516` — **exists** | the rollback path in §11 is real, not aspirational |

---

## 3. Corrections to the two prior documents

*Secção 3 — Correcções factuais aos dois documentos anteriores.*

The brief requires that the prior documents be treated as *evidence and proposals, not instructions*. This section records the places where their supporting claims did not survive inspection of the installed source and the real manifest. **None of the eight corrections invalidates a recommendation.** Each one changes an implementation instruction, and two of them (C-1, C-2) change the numbers the rest of the remediation is built on.

Every claim below was verified by running the real code against the real files. The commands are reproducible and read-only.

### C-1 — The manifest regex **does** match the four-column table — HIGH

**The prior claim.** The final decision review, §3.1.1: *"The current strict regex anchors on `\|\s*$` after the 64-hex hash, so it does **not** match the four-column table. But the plan proposes 'add a second regex for structurally incomplete rows — a table line that has a path and a size but no 64-hex hash'. Applied to the fourth table, a permissive three-column pattern matches **13 rows**… The result would be 13 false 'invalid entries' on the real manifest — a permanent false `FAIL`."*

**What the code actually does.** `quality_guardian/guardian.py::_check_manifest_integrity`:

```python
rows = re.findall(r"^\|\s*`([^`]+)`\s*\|\s*([\d,]+)\s*\|\s*`([0-9a-f]{64})`\s*\|", text, re.M)
```

The pattern ends with `` \s*\| `` — a trailing pipe, **not** `` \|\s*$ ``. The fourth table's rows are:

```
| `ConsequenceMap-Phase-1.6-Documents.zip` | 124,466 | `d55863b071677f8cb…` | unchanged |
```

so the regex **matches every one of them**.

**Measured.** Applying the Guardian's exact regex to the real manifest:

```
total rows captured: 52
  table 1 (L14–L54, "File | Bytes | SHA-256")            -> 39 rows
  table 4 (L87–L101, "File | Bytes | SHA-256 | Status")   -> 13 rows
rows of table 4 that match the current regex: 13 of 13
```

And every one of the 52 rows resolves to a real file: 39 inside the project, 13 on the Desktop. Hashing all 52 gives **51 matches and 1 divergence** (`consequence_map/domain/copy.py`) — which is exactly the `51/52` figure the audit reports. The audit and the code agree; the review's reading of the regex did not.

**Consequences.**

1. **The "expected set" for M-1 is 52 entries, not 39.** The 13 Desktop artefacts are *manifest-covered artefacts*, they are already being verified today, and the `51/52` headline depends on them being in the set. A parser that scoped itself to the three-column table alone would **silently drop 13 protected artefacts from the integrity check** — a regression, not a fix.
2. **P-1's underlying risk is real but its mechanism was wrong.** The danger of a file-wide *permissive* pattern — one that accepts a row with a path and a size but no hash — remains exactly as the review described: it would match all 13 four-column rows and flag them as invalid. The correction is therefore still required; only the diagnosis of *why* changes.
3. **P-1's chosen mechanism is still right, for a stronger reason.** A parser that accepts rows of **three columns or four columns where the fourth is a recognised status** and rejects anything else is immune to the false-positive problem *and* preserves the 13 Desktop entries. The review's "anchor on the column count" option (§3.1.1, second bullet) is the correct one and is adopted here.

**Specification.** §5.1 defines the parser precisely, including the exact status vocabulary observed in the real manifest.

### C-2 — The manifest's composition was mis-stated — MEDIUM

**The prior claim.** The final decision review, §3.1.2: *"The manifest covers `consequence_map/` (32), `docs/` (4), `evidence/` (10) and 19 Desktop artefacts."*

**Measured.** Counting the rows the regex captures:

| Prefix | Real count | Prior claim |
|---|---|---|
| `consequence_map/` | **32** | 32 ✔ |
| `docs/` | **2** | 4 ✘ |
| `evidence/` | **5** | 10 ✘ |
| Desktop artefacts | **13** | 19 ✘ |
| **Total** | **52** | 65 ✘ |

The prior figures sum to 65, which does not equal the manifest's own declared total of 52 — an internal inconsistency that should have been caught.

**Consequences.** Every count derived from the composition must be recomputed. In particular the M-9 arithmetic: the manifest lists **32** files under `consequence_map/`, of which **15** are under `consequence_map/tests/`, so the number of package files outside `tests/` is **32 − 15 = 17**, not 19. The brief's instruction to confirm the count against the brief's own figure ("the number previously reported was 17, not 19") is therefore **confirmed**: 17 is correct.

### C-3 — The "additional files" scope is much smaller than claimed — MEDIUM

**The prior claim.** The final decision review, §3.1.2: *"A naive 'tree minus manifest' computation reports at least **five** legitimate files as 'additional'… a naive tree-minus-manifest reports ~10 legitimate files."* The plan, §4.1, leaves the computation undefined.

**Measured.** Restricting the computation to the three prefixes the manifest actually covers (`consequence_map/`, `docs/PHASE-2A-`, `evidence/`), and walking the real tree:

```
candidates under covered prefixes, not listed in the manifest: 2
    docs/PHASE-2A-MANIFEST.md
    docs/PHASE-2A-MANIFEST-ADDENDUM-A-1.md
```

Everything else the earlier documents counted as "legitimate additional files" is either outside the covered prefixes (`docs/QUALITY-GUARDIAN-*.md`, the Guardian's own tree) or is excluded by `detect.tracked_files` (the Guardian tree, `__pycache__`, `.git`, and the other `EXCLUDED_DIRS`).

**Consequence.** The scope becomes clean and decidable: "additional" = a file under a covered prefix that the manifest does not list, **minus a declared exemption list** whose only members today are the manifest itself and the addendum A-1 — the two files that *record* the manifest and therefore cannot list their own hashes. The count is **2 today, both exempt, net 0**. The information is preserved without a false `FAIL` and without an undefined computation.

### C-4 — F-03's canonical example does not demonstrate F-03 — MEDIUM

**The prior claim.** The technical plan, §4.2: *"`repair_is_sane("A"*1000, "B"*1000)` → `True`, while `"B"*1000` is a `SyntaxError`."*

**Measured.**

```
repair_is_sane("A"*1000, "B"*1000)  -> True
compile("B"*1000, "x", "exec")      -> succeeds
```

`"B"*1000` is a valid expression statement — a name bound to nothing. It compiles. The example does not demonstrate the finding.

**What actually demonstrates it.** A same-length candidate that is genuinely invalid:

```
original   "x = 1\n"
candidate  "x = (\n"          same length (6)
compile(candidate)            -> SyntaxError: '(' was never closed
repair_is_sane(original, candidate) -> True      <-- the size gate accepts it
```

**Consequence.** F-03 stands — the size heuristic really is the only gate, and it really does accept an invalid same-length replacement. But the **test** must use a candidate that actually fails to compile, otherwise the test would pass for the wrong reason. §5.2 and T-09 specify the correct fixture, and §7 requires the candidate to be verified as non-compiling **by the test itself**, not assumed.

### C-5 — The N1 literal risk is real, but not where the review says — MEDIUM

**The prior claim.** The final decision review, §3.2.1: *"A trailing-whitespace sequence **inside a string literal** is not trailing whitespace… A file containing `TEXT = "hello   "` has its **string content** altered by the current N1 repair."*

**Measured.** `apply_level1_fixes` is line-based (`_strip_trailing_whitespace` splits on line endings and rstrips each line body):

| Input | Altered? |
|---|---|
| `T = "hello   "\n` | **No** — the whitespace is inside the quotes, not at the end of the line, so `rstrip` never reaches it |
| `T = """hello   \nworld"""\n` | **Yes** — the line `T = """hello   ` ends with whitespace, and the result is `T = """hello\nworld"""`, which **changes the string's value** |

**Consequence.** The finding is real and it is worse than a cosmetic issue: a **multi-line** string literal — a docstring, a SQL block, a template — can have its content silently altered. The example in the review does not exhibit it; a triple-quoted literal does. §6 specifies the transformation as **token-aware** and T-27 uses the triple-quoted fixture.

### C-6 — The two protections disagree in a different direction than stated — MEDIUM

**The prior claim.** The technical plan, §4.4: *"**The two protections disagree about the same file:** `ConsequenceMap/domain/copy.py` → `is_manifest_protected` `False`, `is_protected` `True`."*

**Measured.**

```
is_manifest_protected("consequence_map/domain/copy.py")  -> True
is_manifest_protected("ConsequenceMap/domain/copy.py")   -> False
is_protected(<project>/consequence_map/domain/copy.py)   -> False
```

`is_protected` returns `False` for `copy.py` because `copy.py` is in neither `PROTECTED_PATH_PATTERNS` nor `PROTECTED_DIRS`. The manifest prefix list is the **only** guard that covers it. So the disagreement is not "one says yes, the other says no about the same file" — it is that **one of the two guards does not cover `copy.py` at all**, and the one that does is the case-sensitive textual one.

**The bypass is real and was reproduced.** Using the real function against a real protected file, with a deliberately dirty payload:

```
project_rel="consequence_map/domain/copy.py"  -> not altered, notes=[]       (refused)
project_rel="ConsequenceMap/domain/copy.py"   -> ALTERED, notes=['removed trailing whitespace…']
```

The case-variant spelling passes `is_manifest_protected`, so `apply_level1_fixes_in_project` returns **modified content for a manifest-protected file**. On this host the write is blocked by the suspension — but that is the suspension, not the guard. With auto-repair enabled, this path would rewrite a protected file.

**Consequence.** M-4's requirement is unchanged and its importance is confirmed. §5.4 additionally requires that the **write-time** check, not only the pre-repair decision, is identity-based — because the pre-repair decision is exactly where the case gap lives.

### C-7 — The `pre_verify` nudge rule must be source-scoped — MEDIUM

**The prior claim.** The technical plan, §4.3, proposes excluding `REPAIR_SUSPENDED` from the nudge. The final decision review, §3.3.3, sharpens it: the exclusion must not swallow a genuine `NOT_VERIFIED` from another source.

**Verified in the source.** `quality_guardian/hook.py`:

```python
if verdict in ("FAIL", "NOT_VERIFIED", "BLOCKED"):
    directive = {"action": "continue", "message": …}
```

`NOT_VERIFIED` **does** produce a `continue` directive. `cycle.result.worst` is the only input to that decision, so under a suspension every cycle would nudge, for a condition that cannot resolve on its own — with the runtime's `max_verify_nudges` default of 3, three wasted turns per turn, each re-running the suite.

**Consequence.** Adopted, with the review's precise rule (§5.3): the nudge is suppressed **only** when every `NOT_VERIFIED`/`BLOCKED` check in the cycle is either the `repair-capability` check in the `REPAIR_SUSPENDED` state, or a check the `repair-capability` check explicitly attributes to the suspension. A suspended repair **plus** an unverifiable manifest must still nudge.

### C-8 — The N1 transformation's `changed` flag is unreliable — LOW

**Measured.**

```
_ensure_final_newline("x = 1\n")    -> ("x = 1\n",   changed=1)   # content identical
_ensure_final_newline("x = 1\n\n")  -> ("x = 1\n",   changed=1)   # a trailing blank line was removed
_ensure_final_newline("x = 1")      -> ("x = 1\n",   changed=1)
```

The flag is `1` in all three cases, including where the content is byte-identical, and it also fires when the only change is the **removal of trailing blank lines** — a change beyond "trailing whitespace" and "a missing final newline", i.e. outside the declared N-1 scope.

**Consequence.** Two effects, both addressed in §6: the "changed" accounting in the repair notes is not trustworthy as-is, and the transformation is slightly wider than its stated scope. The specification pins the transformation's exact semantics and requires the notes to report what actually changed.

### Summary of corrections

| # | Severity | Prior claim affected | Adopted correction |
|---|---|---|---|
| C-1 | HIGH | review §3.1.1 | The expected set is **52**; the parser must accept 3-column **and** 4-column-with-status rows (§5.1) |
| C-2 | MEDIUM | review §3.1.2 | Composition is **32 + 2 + 5 + 13**; M-9's count is **17** (§11) |
| C-3 | MEDIUM | review §3.1.2, plan §4.1 | "Additional" is scoped to the covered prefixes with an exemption list; net **0** today (§5.1) |
| C-4 | MEDIUM | plan §4.2 | F-03's example is replaced with a genuinely non-compiling same-length candidate (§5.2, T-09) |
| C-5 | MEDIUM | review §3.2.1 | The literal risk is real for **multi-line** literals, not single-line ones (§6, T-27) |
| C-6 | MEDIUM | plan §4.4 | `copy.py` is covered **only** by the case-sensitive textual guard; the bypass is reproduced (§5.4) |
| C-7 | MEDIUM | plan §4.3, review §3.3.3 | The nudge exclusion is **source-scoped** (§5.3) |
| C-8 | LOW | *(new — not in either document)* | The N1 `changed` flag is unreliable and the transformation slightly exceeds its scope (§6) |

---

## 4. Step 0 — root-awareness (the prerequisite)

*Secção 4 — Passo 0: root-awareness.*

**The finding, confirmed by execution.** `write_file_text` calls `config.auto_repair_enabled()` **without** a `root` argument. `config.auto_repair_enabled(root=None)` resolves to `repair_policy(None)`, which resolves to `PROJECT_ROOT`. The caller, `_attempt_repairs`, *does* pass the root. The two calls therefore consult **different policies**:

| Caller | Call | Policy consulted |
|---|---|---|
| `guardian._attempt_repairs` | `config.auto_repair_enabled(root)` | the **isolated** tree — no policy file → default `True` → proceeds |
| `repair.write_file_text` | `config.auto_repair_enabled()` | the **production** tree — `auto_repair: false` → raises `RepairSuspended` |

Measured in this task:

```
auto_repair_enabled(<temp root>)  -> True
auto_repair_enabled()             -> False
```

**Why this is Step 0 and not part of M-2.** It is the **direct cause** of the 29/30 result (§8.2), and it has a consequence far beyond one failing test: because the write path always consults the production policy, **no isolated test can express its own policy**. A test that wants "repair enabled" gets whatever the production machine says; a test that wants "repair suspended" cannot say so without mutating the production policy file. The Guardian's own suite is therefore **non-hermetic** — it depends on the host's global state.

Three of the required tests cannot be written until this is fixed: T-13 (suspension), T-18 (nudge suppression), T-24 (root isolation). Until it is fixed, **no test of the repair path can be trusted to be testing the intended behaviour rather than the machine's current policy**.

### 4.1 Requirements

| # | Requirement | Mechanism |
|---|---|---|
| **R-0.1** | The write path resolves the policy **against the root it is writing into** | `write_file_text(path, content, *, expected_hash=None, root=None)` consults `config.auto_repair_enabled(root)`; the `root` is threaded from `_attempt_repairs` |
| **R-0.2** | The resolution is **explicit, never implicit** | `root=None` must **not** silently mean "the production root" at the write site. The default must be an explicit parameter at every call site, or the function must require it. A caller that forgets `root` must fail loudly, not write to production |
| **R-0.3** | Behaviour when the root is unavailable is defined | the policy lookup fails **safe**: an unreadable or malformed policy yields `auto_repair: false` (`repair_policy` already does this) — the write is refused, never permitted by accident |
| **R-0.4** | Production and test fixtures are **fully isolated** | a test tree has no policy file → default `True` → the repair path is exercised in isolation; the production policy is never consulted and never mutated |
| **R-0.5** | The hooks keep working | `post_tool_call` and `pre_verify` call `run_cycle(..., root=…)` with the real project root; their behaviour is unchanged by Step 0 |
| **R-0.6** | **Production behaviour does not change by accident** | the production tree's policy is still `auto_repair: false`, so the production write path still refuses. Step 0 changes *which* policy is consulted, not *whether* repair is permitted in production |
| **R-0.7** | The change is provably hermetic | a new assertion proves the production policy file's hash and `last-seen.json`'s hash are **identical before and after** a full suite run |

### 4.2 Minimal change

| File | Change |
|---|---|
| `quality_guardian/repair.py` | `write_file_text` gains `root` (and, from M-2, `expected_hash`); the policy check becomes `config.auto_repair_enabled(root)` |
| `quality_guardian/guardian.py` | `_attempt_repairs` passes `root` at **both** call sites — the apply and the **revert** |
| `quality_guardian/config.py` | **no change** — `auto_repair_enabled(root)` already accepts a root |

That is the whole of Step 0. One signature, two call sites, one argument.

### 4.3 Acceptance criteria for Step 0

| ID | Criterion |
|---|---|
| **AC-0.1** | With a temporary root that has **no** policy file, `auto_repair_enabled(root)` is `True` and a write in that root is attempted. |
| **AC-0.2** | With a temporary root whose policy file sets `auto_repair: false`, the write in that root is refused as `REPAIR_SUSPENDED`. |
| **AC-0.3** | The **production** policy file and `last-seen.json` are byte-identical before and after a full run of the Guardian's suite. |
| **AC-0.4** | Two different roots can hold **opposite** policies at the same time, and each write is governed by its own root's policy. |
| **AC-0.5** | A caller that omits `root` at the write site cannot write to the production tree. |
| **AC-0.6** | The existing G06 error is gone **as a consequence of the environment**, with the test's assertions unchanged. |

### 4.4 Rollback for Step 0

Revert `repair.py` and the two call sites. The production policy remains in force throughout, so no rollback window exposes the old write path.

---

## 5. Specification — M-1 to M-4

*Secção 5 — Especificação M-1 a M-4.*

### 5.1 M-1 — the manifest check must assert over the expected rows

**Exact recommendation (audit §13.1, verbatim).** *"The manifest check must assert over the **expected** rows, not the **found** rows: any entry that cannot be resolved is `FAIL`; an empty parse is `NOT_VERIFIED`."*

**Closes:** F-01 (CRITICAL — a missing protected file produces `PASS`) and F-02 (HIGH — a malformed manifest produces `PASS`).

**Module, file, function.** `quality_guardian/guardian.py::_check_manifest_integrity` — the only function affected.

#### 5.1.1 Current behaviour, confirmed by inspection

The function parses the manifest with one regex, then loops over the rows it **found**:

```python
rows = re.findall(r"^\|\s*`([^`]+)`\s*\|\s*([\d,]+)\s*\|\s*`([0-9a-f]{64})`\s*\|", text, re.M)
checked = 0
mismatched = []
missing = 0
desktop = Path(r"C:\Users\Utente\Desktop")
for rel, _size, expected in rows:
    candidate = root / rel.replace("/", os.sep)
    if not candidate.exists():
        candidate = desktop / rel.replace("/", os.sep)
    if not candidate.exists():
        missing += 1
        continue
    actual = detect.sha256_of(candidate)
    checked += 1
    if actual != expected:
        mismatched.append(rel)
# … `missing` is consulted NOWHERE before the PASS branch:
return CheckResult(
    name="phase-2a-manifest-integrity", verdict=classify.PASS,
    detail=f"{checked} manifest entries verified, 0 mismatched",
    evidence={"checked": checked, "absent_from_disk": missing},
)
```

Two failure paths follow, both confirmed:

- **F-01 (a missing file).** `missing` is counted and never consulted. A deleted protected artefact yields `checked = 51`, `mismatched = []`, `missing = 1` → **`PASS`**.
- **F-02 (a malformed manifest).** The regex matches nothing, the loop never runs, `checked = 0` → **`PASS`** with the detail *"0 manifest entries verified, 0 mismatched"*.

A third, quieter defect: `detect.sha256_of` returns `""` when the file cannot be read. `"" != expected`, so an **unreadable** file is counted as **divergent** → `FAIL`. That verdict is defensible, but the reason is mislabelled: "cannot verify" is not "content differs". The specification distinguishes them.

#### 5.1.2 The seven states

| State | Meaning | Required verdict |
|---|---|---|
| **Expected** | a row parsed from a manifest entry table | — |
| **Found** | the row resolved to a readable file | — |
| **Missing** | the row resolved to nothing | **`FAIL`** |
| **Unreadable** | the row resolved, but the file cannot be read | **`BLOCKED`** |
| **Divergent** | the row resolved and was read, and the hash differs | `FAIL` — or `WARNING` when documented in an addendum (the current behaviour, preserved) |
| **Invalid** | a row in an entry table that is structurally malformed | **`FAIL`** (see D-4) |
| **Manifest invalid** | the manifest exists but yields no parseable entry | **`NOT_VERIFIED`** |

#### 5.1.3 The parser — the P-1 resolution

The parser is **structural and table-scoped**, not a file-wide regex. This is the correction of C-1 and the resolution of P-1.

**Rule 1 — identify the entry tables by their header.** The manifest contains five Markdown tables. Two of them are **entry tables**; three are not.

| Table | Lines | Header | Entry table? |
|---|---|---|---|
| 1 | L14–L54 | `File \| Bytes \| SHA-256` | **yes** — 39 rows |
| 2 | L62–L68 | `File \| What it holds` | no — descriptive |
| 3 | L76–L79 | `File \| Purpose` | no — descriptive |
| 4 | L87–L101 | `File \| Bytes \| SHA-256 \| Status` | **yes** — 13 rows |
| 5 | L107–L118 | `The authorisation did **not** permit \| Status` | no — scope compliance |

**Rule 2 — a row is an entry row if it has three columns, or four whose fourth column is a recognised status.** The status vocabulary observed in the real manifest is exactly two values: `unchanged` and `present`. A row with any other shape is a row of another table and is **ignored, never flagged**.

**Rule 3 — an incomplete row inside an entry table is invalid.** A row in an entry table that has a path and a size but **no** 64-hex hash, or a hash that is not 64 hex characters, is **invalid** — it is reported by name, never silently skipped. This is what closes the F-02 class completely: a corrupted manifest row cannot pass as "nothing to check".

**Rule 4 — the strict pattern stays strict.** The existing 64-hex pattern is kept for the valid rows. The permissive pattern is used **only** inside the entry tables' row ranges, and only to *detect* invalid rows.

**Rule 5 — a table-scoped parser, not a header-anchored one.** Both mechanisms are acceptable; this specification requires the **column-count** variant, because it is the one that preserves the 13 Desktop artefacts. A header-only parser that accepted exactly `File | Bytes | SHA-256` would drop table 4 entirely and silently reduce the protected set from 52 to 39 — the regression C-1 describes. The implementation may identify the entry tables by header *and* then apply the column-count rule within them; what it may not do is accept only the three-column form.

**Rule 6 — titles, separators, empty lines and escaped pipes are handled unambiguously.** A table header row, a `|---|---|` separator row, and a blank line are structural markers, never entries. A pipe escaped as `\|` inside a cell does not start a new column.

#### 5.1.4 The additional-files scope — the P-2 resolution

The corrected, decidable scope (C-3):

> **additional** = a file under one of the three manifest-covered prefixes (`consequence_map/`, `docs/PHASE-2A-`, `evidence/`) that the manifest does not list, **minus** the declared exemption list.

The exemption list is explicit and small. Measured today, the candidates are exactly two:

| Exempt path | Why |
|---|---|
| `docs/PHASE-2A-MANIFEST.md` | the manifest itself — it cannot record its own hash |
| `docs/PHASE-2A-MANIFEST-ADDENDUM-A-1.md` | the addendum records the divergence; it is not a Phase 2A deliverable |

With the exemptions applied, the additional-file count is **0 today**. The observation is still **recorded** — a count and a sample — so a future stray file under a covered prefix is visible — but it does **not** affect the verdict. That is D-3, and it is the recommendation.

**The computation must use `detect.tracked_files`-equivalent semantics** (same suffix set, same exclusions), so the Guardian's own tree and the cache directories can never appear as "additional". A naive `os.walk` over the whole tree is **not** acceptable and is the direct cause of the "~10 legitimate files" claim in the prior review.

#### 5.1.5 Minimal technical change

1. Keep the existing strict regex, but capture its result distinctly: **zero rows parsed while the manifest exists and is non-empty** → `NOT_VERIFIED` (*"the manifest yielded no parseable entries"*). This closes F-02.
2. Add the table-scoped parser of §5.1.3, producing `expected_rows` (the entry rows) and `invalid_rows` (the malformed rows inside the entry tables).
3. Resolve each expected row against the two search roots (project, then Desktop). Neither resolves → `missing`.
4. Resolve but cannot read → `unreadable`.
5. Verdict: `missing > 0` → `FAIL`; `invalid > 0` → `FAIL`; `unreadable > 0` → `BLOCKED`; no expected rows → `NOT_VERIFIED`; otherwise the existing `PASS`/`WARNING`/`FAIL` logic, unchanged.
6. `evidence` gains `expected`, `found`, `missing`, `invalid_entries`, `unreadable`, `additional`, `divergent`, and the resolved search roots.
7. The `rewritten_paths` exemption is preserved and **extended**: a file the Guardian rewrote this cycle is excluded from the divergence list **and** from the missing list.

**Compatibility.** High. `CheckResult.evidence` is free-form; `classify.NOT_VERIFIED` and `classify.BLOCKED` exist; no signature change.

**Risks introduced.** A false `FAIL` if the Desktop search root is unavailable — the current code falls back to `C:\Users\Utente\Desktop` **unconditionally**, and a host without that layout would report 13 missing files. The search roots must therefore be **explicit and reported**: when a root does not exist, the entries that depend on it are **`BLOCKED`**, not `FAIL`. Those are different facts, and the distinction is what keeps the check portable.

#### 5.1.6 Acceptance criteria — M-1

| ID | Criterion |
|---|---|
| **AC-M1-1** | With one expected file absent and every other file matching, the verdict is `FAIL` and `evidence.missing` contains that path. |
| **AC-M1-2** | With a manifest that exists, is non-empty and yields no parseable entry, the verdict is `NOT_VERIFIED` — never `PASS`, never `FAIL`. |
| **AC-M1-3** | With every expected file present and matching, the verdict is `PASS` and `evidence.found == evidence.expected == 52`. |
| **AC-M1-4** | With the **real** manifest, the parser captures **52** entries: 39 from table 1 and **13** from table 4 — none from tables 2, 3 or 5. |
| **AC-M1-5** | The **13** rows of table 4 are **not** reported as invalid entries, despite their fourth column. |
| **AC-M1-6** | A structurally incomplete row **inside an entry table** is reported as `FAIL` with `evidence.invalid_entries` naming it. |
| **AC-M1-7** | With a search root unavailable, the affected entries are `BLOCKED`, not `FAIL`. |
| **AC-M1-8** | An unreadable expected file is `BLOCKED` with `evidence.unreadable`, and is **not** counted as divergent. |
| **AC-M1-9** | With an unlisted file under a covered prefix, the verdict is unchanged and `evidence.additional` records it — after the two declared exemptions. |
| **AC-M1-10** | With the known `copy.py` divergence, the verdict remains `WARNING` — **not** `FAIL`. |
| **AC-M1-11** | The existing P03 and P08 scenarios still produce `FAIL`; P06 still produces `NOT_VERIFIED`. |

**Rollback.** Revert the single function. No data migration, no state change. The extra `evidence` keys are additive and ignored by any older reader.

---

### 5.2 M-2 — artefact-identity validation on the write path

**Exact recommendation (audit §13.1, verbatim).** *"Replace the size heuristic with artefact-identity validation: record the pre-write hash, revalidate it at the moment of the write, compile and parse the result, and require the write to differ from the original **only** by the intended transformation."*

**Closes:** F-03 (HIGH — the 50 % size rule accepts invalid content) and F-06 (MEDIUM — a TOCTOU window between verification and write).

**Module, file, function.** `quality_guardian/repair.py::write_file_text` (the choke point), plus `repair.py::repair_is_sane` and `guardian.py::_attempt_repairs` for the call site.

#### 5.2.1 Current behaviour, confirmed by inspection and by execution

```python
def repair_is_sane(original: str, fixed: str) -> bool:
    if len(original) == 0:
        return True
    return len(fixed) >= int(len(original) * config.MIN_REPAIR_SIZE_RATIO)
```

It compares **lengths only**. It never compiles the result, never parses it, and never checks that the difference is the transformation that was claimed. `write_file_text` performs **no validation at all** of the content it is handed. The pre-write hash is recorded in `_attempt_repairs` (`proposal.before_hash`) and is **never revalidated at the moment of the write**.

**The escape, measured.** (Corrected per C-4 — the prior documents' example did not demonstrate the finding.)

```
original   "x = 1\n"
candidate  "x = (\n"                      same length
compile(candidate)  -> SyntaxError: '(' was never closed
repair_is_sane(original, candidate) -> True      <-- accepted
```

A file whose *meaning* changes while its length and syntax stay valid also passes every current check.

#### 5.2.2 The four validations

Applied **in this order**, at the single write choke point:

| # | Validation | Purpose |
|---|---|---|
| **V1** | **Pre-write hash revalidation.** The hash recorded when the content was read is compared against the file's hash *at the moment of the write*. A mismatch means the file changed between decision and write → refuse. | closes F-06 |
| **V2** | **Syntactic validation.** For `.py`, the candidate must compile (`compile(content, path, "exec")`). | closes the same-size invalid-content escape |
| **V3** | **Transformation-fidelity validation.** The candidate must equal the original **after re-deriving the intended transformation from the original**. The Guardian's N-1 scope is exactly two transformations — trailing-whitespace removal and final-newline normalisation — so the candidate is re-derived by applying `apply_level1_fixes` to the *original* and compared byte-for-byte. | closes the semantic escape: a changed constant cannot survive, because re-deriving from the original produces the original's own constants |
| **V4** | **Structural validation.** For `.py`, the candidate must parse (`ast.parse`). | catches constructs that compile but are structurally wrong |

**V1 must live inside the write choke point**, not only in `_attempt_repairs`: the **revert** path also writes, and a check in the caller alone would leave it unprotected. This is the review's §3.2.2 conclusion, adopted.

**Fail-closed by default.** V1 requires the hash to travel with the write. `write_file_text` gains an optional `expected_hash`; when it is supplied, the file's current hash is compared before the temporary is written. When it is **not** supplied, the write is **refused**, because an unverified write is exactly what M-2 exists to prevent. This is a deliberate tightening.

**The percentage rule is kept, and demoted.** It is **not** deleted. It becomes one predicate among several rather than the only one. The audit's finding was that a percentage "cannot be considered an integrity guarantee"; the remedy is to stop treating it as one. `MIN_REPAIR_SIZE_RATIO` stays as a secondary guard and the specification states explicitly that it is **not** an integrity guarantee.

**The root-scope defect.** Covered by Step 0 (§4): `write_file_text(path, content, *, expected_hash=None, root=None)` consults `config.auto_repair_enabled(root)`.

#### 5.2.3 The revert exemption must be explicit in the API

The **revert** path writes the *original* content, which is **not** a transformation of the original — V3 would reject it. The exemption must therefore be **explicit in the API**, not merely described in prose: the revert must carry a distinct flag or use a distinct entry point, so that a caller cannot accidentally pass original content through the transformation path and have it refused. V1, V2 and V4 still apply to a revert.

#### 5.2.4 Minimal technical change

1. `repair.py`: add `validate_repair(original, fixed, path, expected_hash)` returning `(ok, reason)`, implementing V1–V4 in order.
2. `repair.py`: extend `write_file_text` with `expected_hash` and `root`; call `validate_repair` **before** the temporary is written; refuse with a structured result (see M-3) when validation fails.
3. `repair.py`: make the policy check root-aware (Step 0).
4. `guardian.py::_attempt_repairs`: pass `proposal.before_hash`, `root` and the revert flag at **both** call sites.
5. `config.py`: keep `MIN_REPAIR_SIZE_RATIO`; no other change.

**Compatibility.** High. `write_file_text` already returns a result the caller handles; the change is from `bool` to a structured result (M-3), and both call sites are inside `_attempt_repairs`.

**Risks introduced.**

- **False refusals.** A file that is not valid Python but is a valid project artefact would fail V2/V4. The N-1 scope is `.py` only, so the blast radius is limited — but the check must **skip** non-Python files rather than assume.
- **A file that was already invalid before the repair.** If the original does not compile, V2 on the *fixed* content also fails — correctly, since a repair cannot fix a pre-existing syntax error. The refusal reason must distinguish *"the repair produced invalid content"* from *"the original was already invalid"*, so the operator is not sent chasing the wrong thing.
- **Encoding.** `compile()` and `ast.parse()` operate on text. A file with a BOM or a non-UTF-8 encoding would fail both, though it may be valid Python. The refusal reason must say **"encoding"** in that case, not "syntax".
- **Performance.** `compile()` on every write is cheap for project-sized files.

#### 5.2.5 Acceptance criteria — M-2

| ID | Criterion |
|---|---|
| **AC-M2-1** | A candidate with invalid Python of the **same length** is refused, with a reason naming the syntax failure. The test must itself assert that the candidate does not compile (C-4). |
| **AC-M2-2** | A candidate that is valid Python but differs semantically from the original (a changed constant) is refused by V3. |
| **AC-M2-3** | A legitimate N-1 repair (trailing whitespace, final newline) is applied and recorded as before. |
| **AC-M2-4** | When the file's hash at the moment of the write differs from the recorded pre-write hash, the write is refused and the file is left byte-identical to its state at the moment of the write. |
| **AC-M2-5** | A write with no `expected_hash` supplied is refused. |
| **AC-M2-6** | The revert path restores the original content and is **not** refused by V3. |
| **AC-M2-7** | `repair_is_sane` is no longer the only guard: a same-size invalid candidate is refused even though it passes `repair_is_sane`. |
| **AC-M2-8** | A non-Python file is not subject to V2/V4. |
| **AC-M2-9** | A refusal distinguishes "the original was already invalid" from "the repair produced invalid content". |

**Rollback.** Revert `repair.py` and the two call sites. The suspension remains in force either way, so a rollback does not expose the old behaviour.

---

### 5.3 M-3 — the suspension must be a controlled state

**Exact recommendation (audit §13.1, verbatim).** *"Catch `RepairSuspended` at the call site and convert it to a reported `NOT_VERIFIED`; the cycle must always complete and always write its report."*

**Closes:** F-04 (HIGH — `RepairSuspended` propagates as an uncaught exception).

**Module, file, function.** `quality_guardian/guardian.py::_attempt_repairs` (the call site) and `quality_guardian/repair.py::write_file_text` (the raise). `quality_guardian/cli.py` needs no functional change once the cycle no longer raises.

#### 5.3.1 Current behaviour, confirmed

`RepairSuspended` is raised in `repair.py` and caught in **no** module (§2.3). The consequences:

| Caller | Current behaviour |
|---|---|
| `hook.py` | caught by the outer `except Exception:` → exit 0, the turn continues, **but no report is written** — the cycle aborted before `finalize` |
| `cli.py` | **not caught** — zero `except` clauses in the file → traceback, no report |
| `_attempt_repairs` | **not caught** → the cycle aborts |

#### 5.3.2 The six properties

| # | Property | Required mechanism |
|---|---|---|
| 1 | The repair stays blocked | the choke point still refuses the write |
| 2 | Detection keeps working | the cycle continues past the refusal |
| 3 | Tests keep running | the cycle continues to the test-execution and reporting phases |
| 4 | The final report is produced | `guardian.finalize` is always reached |
| 5 | The hooks never fail or interrupt the turn | no exception escapes `run_cycle` |
| 6 | The result identifies the state clearly | a check named `repair-capability` with an explicit `REPAIR_SUSPENDED` state |

#### 5.3.3 Minimal technical change

1. **`repair.py`:** keep `RepairSuspended` as the internal signal, but make `write_file_text` **not raise it to the caller**. The return becomes a **structured result**, not a `bool`: the current `False` conflates three outcomes — refused by policy, refused by validation, and failed to write — and F-04 exists because that conflation had nowhere to go but an exception. The reasons must be **machine-checkable and distinct**:

   | Reason prefix | Meaning |
   |---|---|
   | `REPAIR_SUSPENDED:` | the policy forbids it |
   | `VALIDATION_REFUSED:` | V1–V4 rejected the content |
   | `WRITE_FAILED:` | the filesystem refused the write |

2. **`guardian.py::_attempt_repairs`:** accept the structured result; on a policy refusal, record `proposal.error = "REPAIR_SUSPENDED: <reason>"` and add the check:

   ```python
   CheckResult(
       name="repair-capability",
       verdict=classify.NOT_VERIFIED,
       kind=classify.IMPLEMENTATION,
       detail="REPAIR_SUSPENDED — automatic repair is disabled by the repair policy; "
              "N repair(s) were proposed and none was applied",
       evidence={"policy": policy, "state": "REPAIR_SUSPENDED"},
   )
   ```

   The existing suspension branch in `_attempt_repairs` already uses this shape; M-3 **unifies** it with the exception path so there is **one** code path, not two.

3. **`guardian.py::run_cycle`:** the cycle must reach `detect.save_state` and the report regardless. Under the current code the exception prevents both.

4. **`cli.py`:** a top-level `except Exception` in `main()` that prints a diagnostic and returns a non-zero exit code is **recommended** as defence in depth, so that no future exception can abort a CLI run without a report. Two lines, and squarely within M-3's intent.

#### 5.3.4 The `pre_verify` nudge — the source-scoped rule (C-7)

Verified in the source: `NOT_VERIFIED` **does** produce a `continue` directive, and `cycle.result.worst` is the only input. Under a suspension every cycle would nudge, for a condition that never resolves on its own.

**The rule, adopted from the review and made precise:**

> The nudge is suppressed **only** when every `NOT_VERIFIED`/`BLOCKED` check in the cycle is either the `repair-capability` check in the `REPAIR_SUSPENDED` state, or a check the `repair-capability` check explicitly attributes to the suspension. A `NOT_VERIFIED` from any other source still nudges.

A cycle with a suspended repair **and** an unverifiable manifest must still nudge — the manifest problem is real and is not resolved by un-suspending anything. The exclusion must be **source-scoped**, not verdict-scoped; excluding by verdict alone turns the exclusion into a hole.

**Risks introduced.**

- **A swallowed exception hides a real fault.** Mitigated by the distinct machine-checkable reason prefixes, and by the requirement that the report carries the reason **verbatim**.
- **The nudge behaviour changes.** Mitigated by the source-scoped rule above, and by T-18, which asserts both the suppression and the non-suppression.

#### 5.3.5 Acceptance criteria — M-3

| ID | Criterion |
|---|---|
| **AC-M3-1** | With the policy suspended and a repair proposed, the cycle completes, the report is written, and no file is modified. |
| **AC-M3-2** | The report contains a `repair-capability` check whose `detail` contains `REPAIR_SUSPENDED`. |
| **AC-M3-3** | `cli.verify` under suspension exits without a traceback and writes a report. |
| **AC-M3-4** | `post_tool_call` and `pre_verify` both exit 0 with the suspension active. |
| **AC-M3-5** | `pre_verify` under suspension emits **no** `continue` directive. |
| **AC-M3-6** | `pre_verify` with a suspension **and** an independent `NOT_VERIFIED` **does** emit a `continue` directive. |
| **AC-M3-7** | The target file is byte-identical before and after the cycle. |
| **AC-M3-8** | With the policy enabled, a repair is applied exactly as before — no behaviour regression. |
| **AC-M3-9** | The three refusal reasons are distinguishable from the report text alone. |

**Rollback.** Revert the return-shape change and the call site. The suspension file remains and continues to block writes through the pre-existing raise. A rollback re-introduces F-04 — the suspension must therefore stay in force either way.

---

### 5.4 M-4 — identity-based protection

**Exact recommendation (audit §13.1, verbatim).** *"Make the protection identity-based: resolve the path, compare against the resolved set of manifest-covered files, and check the hash at the write. Close the case-sensitivity gap between `is_protected` and `is_manifest_protected`."*

**Closes:** F-05 (MEDIUM — the protection is textual, not identity-based).

**Module, file, function.** `quality_guardian/config.py::is_manifest_protected` (the textual comparison), `quality_guardian/config.py::is_protected` (the resolving comparison), and the write path (the hash check, shared with M-2).

#### 5.4.1 Current behaviour, confirmed by inspection and by execution

```python
MANIFEST_PROTECTED_PREFIXES = (
    "consequence_map/",
    "docs/PHASE-2A-",
    "evidence/",
)

def is_manifest_protected(rel_path: str) -> bool:
    rel = str(rel_path).replace("\\", "/")
    return any(rel.startswith(prefix) for prefix in MANIFEST_PROTECTED_PREFIXES)
```

A plain string prefix comparison. `is_protected` — the *other* function — resolves the path first and is therefore case-insensitive in effect for files that exist, but it covers a **different, much smaller** set: `PROTECTED_PATH_PATTERNS` (8 files) plus `PROTECTED_DIRS` (`consequence_map/tests`).

**The two guards do not agree, and the disagreement is worse than a case gap (C-6).** Measured:

```
is_manifest_protected("consequence_map/domain/copy.py")  -> True
is_manifest_protected("ConsequenceMap/domain/copy.py")   -> False
is_protected(<project>/consequence_map/domain/copy.py)   -> False
```

`copy.py` — a **manifest-covered** file — is protected by **one** guard only, and that one is the case-sensitive textual one.

**The bypass, reproduced** against the real function and a real protected file:

```
project_rel="consequence_map/domain/copy.py"  -> refused, notes=[]
project_rel="ConsequenceMap/domain/copy.py"   -> ALTERED, notes=['removed trailing whitespace…']
```

The case-variant spelling passes `is_manifest_protected`, so `apply_level1_fixes_in_project` returns **modified content for a manifest-protected file**. On this host the write is blocked by the suspension — that is the suspension, not the guard.

#### 5.4.2 Three changes, in increasing strength

| # | Change | Purpose |
|---|---|---|
| **I1** | **Resolve before comparing.** `is_manifest_protected` must resolve its input against the project root and compare the **resolved** relative path against the protected set. | closes the case-sensitivity and traversal gaps |
| **I2** | **Build the protected set from the manifest itself**, not from hard-coded prefixes: parse the manifest's entry rows (per §5.1.3 — 52 entries) and resolve each to an absolute path. The prefixes remain as a fallback for files not listed in the manifest. | the manifest is the authority on what is protected; a hard-coded list can drift from it |
| **I3** | **Check the hash at the write:** a file whose current hash equals a manifest entry's recorded hash is protected regardless of how its path was reached. | the identity anchor the recommendation asks for |

**I3 is the same mechanism as M-2's V1 and must be implemented once.** The specification requires a single function, `manifest_protection_for(path, root)`, returning a protection record — `{protected: bool, reason: str, expected_hash: str | None, resolved: Path | None}` — used by both the pre-repair decision and the write-time validation. Two implementations would hash the file twice and could disagree.

#### 5.4.3 The rename bypass — the hash clause stated unambiguously

A hash anchor alone is insufficient, and the naive form of it is wrong in **both** directions. The rule, stated so that two implementations cannot diverge:

> A file is protected when **either** its resolved path is in the manifest-covered set **or** its content hash equals the hash of a manifest entry **whose own path still resolves to a file with that same hash**. The second clause protects a protected file that was moved or renamed; the first protects everything the manifest names. A file that merely *happens* to share content with a protected file is **not** thereby protected.

The second clause's condition — *whose own path still resolves* — is what makes the rename safe. Without it, a moved protected file would lose its protection (the dangerous direction). With it, an unrelated file that coincidentally matches a protected file's hash is not over-protected (the merely-annoying direction).

**Identity, path and content are three distinct things**, and the specification keeps them distinct:

| Concept | What it is | What it protects against |
|---|---|---|
| **Logical identity** | "this is the `copy.py` deliverable" | the file being renamed, moved, or reached by an alternative path |
| **Path identity** | the resolved location on disk | case variants, `..` traversal, relative-vs-absolute spellings, separator variants |
| **Content integrity** | the hash of the bytes | the content being altered |

The protection must survive a move, a rename, a relative-to-absolute change, a separator change, a capitalisation change, and the file appearing outside its original location — while the hash and the protected identity stay attached to the correct content.

#### 5.4.4 Compatibility, risks and the collision rule

**Compatibility.** Moderate — the most invasive of the four. `is_manifest_protected(rel_path)` is called from exactly one place (`apply_level1_fixes_in_project`) and `is_protected(path)` from one place (`classify_failure`). Both signatures can be preserved as thin wrappers over the new resolution, so no caller changes.

**Risks introduced.**

- **The manifest must be readable at protection time.** If it is absent or malformed, the protected set cannot be built from it. The fallback is the prefix set — which must then be **more** protective, not less. The reason recorded is *"fallback: manifest unavailable"*.
- **Resolution can fail.** A path that does not exist cannot be resolved in the usual way; `Path.resolve()` on a non-existent path still yields an absolute path on Windows (non-strict by default). The resolution must be explicitly **non-strict** and must handle `OSError`.
- **Symlink and hard-link behaviour is NOT VERIFIED on this host** — `os.symlink` raised `OSError` (no developer-mode privilege). I2 and I3 mitigate this: a symlinked path resolves to its target, and the target's hash anchors the protection. The audit's M-14 keeps the definitive proof as future work.
- **Over-broad protection** would block legitimate repairs of ordinary files. T-22 is the counter-test.

**The collision rule.** Measured on the real manifest: no duplicate entries exist, and no entry exists in both roots — so the project-first search order is deterministic today. The rule must still be **specified**, because the state can change: if an entry existed in **both** roots with different content, the **project** copy is authoritative, and the fact that a Desktop copy exists with different content is **recorded in the evidence**, not silently ignored.

#### 5.4.5 Acceptance criteria — M-4

| ID | Criterion |
|---|---|
| **AC-M4-1** | `is_manifest_protected("ConsequenceMap/domain/copy.py")` returns `True` — the case gap is closed. |
| **AC-M4-2** | A path reaching a manifest-covered file through `..` segments is protected. |
| **AC-M4-3** | A file listed in the manifest is protected even if its path does not start with any hard-coded prefix. |
| **AC-M4-4** | A file whose current hash equals a manifest entry's recorded hash is protected at the write, regardless of path form. |
| **AC-M4-5** | A **renamed or moved** manifest-covered file remains protected (its manifest row still resolves to a file with that hash). |
| **AC-M4-6** | A file that merely shares content with a protected file, but whose manifest row does not resolve, is **not** over-protected. |
| **AC-M4-7** | With the manifest absent, the hard-coded prefixes still protect the files they name, and the reason records the fallback. |
| **AC-M4-8** | A file that is neither manifest-listed nor prefix-covered remains unprotected, so ordinary repairs are not blocked. |
| **AC-M4-9** | The existing P01, P02, P09 and P10 scenarios still block. |
| **AC-M4-10** | The **write-time** check — not only the pre-repair decision — refuses a case-variant path to a protected file. |

**Rollback.** Revert `config.py` and the shared write-time hash check. The hard-coded prefix list is retained in the current code as the fallback, so a rollback restores today's behaviour exactly.

---

## 6. N1 safety — the transformation must be semantically neutral

*Secção 6 — Segurança da transformação N1.*

**Why this is in scope.** M-2's requirement is that the write "differ from the original **only** by the intended transformation". A transformation that is not semantically neutral violates that requirement directly, so bounding it belongs in M-2. It is specified here because it needs its own reasoning.

### 6.1 What the current transformation actually does

`quality_guardian/repair.py` implements exactly two fixes:

```python
def apply_level1_fixes(path: Path, source: str) -> Tuple[str, List[str]]:
    notes = []
    result, count = _strip_trailing_whitespace(source)
    if count:
        notes.append("removed trailing whitespace on {count} line(s)")
    result, changed = _ensure_final_newline(result)
    if changed:
        notes.append("ensured a single final newline")
    return result, notes
```

**The distinction that must be drawn.** Whitespace is not one thing:

| Kind | Example | Semantically relevant? | May N1 touch it? |
|---|---|---|---|
| **Structural whitespace** | indentation, the space around `=`, the blank line between functions | no | **yes** — but only trailing, per the current scope |
| **Whitespace at end of a physical line inside a multi-line literal** | `TEXT = """hello   ` (the next line continues the string) | **yes** | **no** |
| **Whitespace inside a single-line literal** | `T = "hello   "` | **yes** | **no** |
| **Content whitespace in a data format** | CSV, YAML block scalars, `.txt` payloads, f-string templates | **yes** | **no** |
| **Whitespace in a comment** | `# TODO:  ` | no, but it is *content* | only trailing, and only in `.py` |
| **Trailing whitespace at end of a physical line, outside any literal** | `x = 1   ` | no | **yes** — this is N1's actual target |

### 6.2 The measured defect (C-5)

The transformation is **line-based**. `_strip_trailing_whitespace` splits the source into lines, rstrips each line body, and reassembles. It has no notion of tokens, so it cannot know whether a line's trailing whitespace is inside a string.

| Input | Altered? | Why |
|---|---|---|
| `x = 1   \n` | **yes** | structural trailing whitespace — N1's intended target |
| `T = "hello   "\n` | **no** | the whitespace is inside the quotes, so the line does not *end* with whitespace — `rstrip` never reaches it |
| `T = """hello   \nworld"""\n` | **yes — and the string's value changes** | the physical line `T = """hello   ` ends with whitespace, which is inside the literal |

The result in the third case is `T = """hello\nworld"""` — the literal's content is silently different. **This is the real risk**, and the prior review's single-line example did not exhibit it.

### 6.3 The requirements

| # | Requirement |
|---|---|
| **N-1** | The transformation must be **token-aware**: trailing whitespace may only be removed where the whitespace is genuinely outside a string literal. |
| **N-2** | If it cannot be **proved** that a transformation is semantically neutral, the transformation must be **blocked** or escalated to assisted review — never applied optimistically. |
| **N-3** | The transformation applies to **`.py` files only**, which is already the scope (`_find_formatting_issues` filters on `rel.endswith(".py")`). A non-`.py` file is not a candidate at all. |
| **N-4** | The `changed` accounting must be truthful: the notes must report what **actually** changed, and must not report a change when the bytes are identical (C-8). |
| **N-5** | The transformation's scope must be exactly what is declared. The current `_ensure_final_newline` also removes **trailing blank lines** beyond a single final newline — outside the declared scope. Either the scope is widened explicitly and documented, or the behaviour is narrowed. The recommendation is to **narrow** it: a missing final newline is added; existing trailing blank lines are left alone. |
| **N-6** | The transformation must be **idempotent**: applying it twice must equal applying it once, byte-for-byte. This is what makes V3's re-derivation sound. |

### 6.4 How token-awareness is achieved

The transformation should work on the **token stream**, not the raw lines:

1. Tokenise the source with `tokenize` (or `ast` + `tokenize`) to identify string literals and their spans.
2. Compute the set of line numbers that are **entirely outside** any string literal.
3. Strip trailing whitespace **only** on those lines.
4. For the final newline, operate on the end of the file only.

A token-unaware implementation that merely compares the transformed output against the original and reverts if the *parsed AST* differs would also be sound — but it is weaker: it would block legitimate repairs of files whose AST changes for unrelated reasons, and it would not detect a change *inside* a docstring that does not alter the AST's meaning. The token-aware approach is recommended.

**A weaker, acceptable alternative** — and the one this specification requires as a **minimum** — is to **refuse** the repair when the file contains any string literal whose span covers the end of a line whose trailing whitespace would be stripped. That is conservative, deterministic, and provably safe: it never alters a literal, and it declines rather than guesses. Refusing is explicitly allowed by N-2.

### 6.5 Acceptance criteria — N1

| ID | Criterion |
|---|---|
| **AC-N1-1** | A file with trailing whitespace on a line **outside** any literal is repaired as before. |
| **AC-N1-2** | A file whose only trailing whitespace is inside a **multi-line** literal is **not** modified (or is refused). |
| **AC-N1-3** | A file whose only trailing whitespace is inside a **single-line** literal is not modified. |
| **AC-N1-4** | A file with a literal containing tabs, `\n` escapes, `\t` escapes, and multi-line content is not modified by the literal region. |
| **AC-N1-5** | The transformation is idempotent: `apply(apply(x)) == apply(x)` for every fixture in the matrix. |
| **AC-N1-6** | The `changed` flag and the notes are false for a file that is already compliant. |
| **AC-N1-7** | V3 re-derivation holds: for every accepted repair, `candidate == apply_level1_fixes(original)` byte-for-byte. |

**Nothing in this section is implemented by this task.**

---

## 7. The adversarial test matrix — T-01 to T-30

*Secção 7 — Matriz de testes adversariais.*

Every test uses a **temporary copy or an artificial fixture**. **No real protected file is ever the target of a destructive test.** All fixtures are created under a `tempfile.mkdtemp()` root and removed in cleanup. The full Guardian suite writes nothing into the production tree — verified by comparing the production `last-seen.json` and policy hashes before and after a run.

Each entry states: the risk covered, the preconditions, the fixture, the simulated action, the expected result, the evidence to record, the side-effect risk, and the relation to the other tests.

### 7.1 T-01 to T-23 — the manifest and the write path

| ID | Risk covered | Preconditions | Fixture | Simulated action | Expected result | Evidence | Side-effect risk | Relates to |
|---|---|---|---|---|---|---|---|---|
| **T-01** | F-01 — a missing protected file produces `PASS` | a temp project with a 1-row manifest | the manifest's file deleted | run the manifest check | `FAIL`; `evidence.missing` names the path | the check result's `evidence` dict | none — the temp tree only | the detector for AC-M1-1 |
| **T-02** | F-01 — an altered protected file | temp project | the file's content changed | run the check | `FAIL` (undocumented) or `WARNING` (documented in an addendum) | verdict + `evidence.divergent` | none | T-01; AC-M1-10 |
| **T-03** | F-02 — an empty manifest | temp project | a manifest with a header and no rows | run the check | `NOT_VERIFIED` | verdict + `detail` | none | T-04; AC-M1-2 |
| **T-04** | F-02 — a malformed manifest | temp project | text that is not a manifest | run the check | `NOT_VERIFIED` | verdict + `detail` | none | T-03; AC-M1-2 |
| **T-05** | a duplicate manifest entry | temp project | the same path listed twice, both hashes identical | run the check | **`FAIL`**, with the duplicate named in `evidence.invalid_entries` — a duplicate is a malformed manifest, the same class as an invalid hash. `PASS` is **not** defensible: it reads as "a duplicate is acceptable" | `evidence.invalid_entries` | none | T-07; D-4 |
| **T-06** | a malicious path in a row | temp project | a row with `../escape.py` and one with an absolute path | run the check | the escaping row is rejected as invalid; the verdict is `FAIL` with `evidence.invalid_entries`; **the test asserts that no file was created outside the temp tree** | `evidence.invalid_entries` | the check is read-only by construction, but the test must assert nothing was created outside | T-07; AC-M1-6 |
| **T-07** | an invalid hash in a row | temp project | a row with a 63-character hash and one with non-hex characters | run the check | `FAIL`; `evidence.invalid_entries` names both | `evidence.invalid_entries` | none | T-05; AC-M1-6 |
| **T-08** | an unavailable search root vs a missing file | temp project | the manifest references a path under a root that **does not exist**; and separately, a row under an existing root whose file is absent | run the check | the unavailable root → **`BLOCKED`** (*"the search root is unavailable"*); the absent file under an available root → **`FAIL`**. Two different facts, two different verdicts | verdict + `detail` + `evidence` | none | T-01; AC-M1-7 |
| **T-09** | F-03 — same-size invalid content | temp file | the candidate is **verified by the test itself** to be non-compiling, and is the same length as the original (e.g. `"x = 1\n"` → `"x = (\n"`) | attempt the write | refused by V2/V4; the reason names the syntax failure; the file is byte-identical afterwards | the refusal reason naming the syntax failure | none — the refusal precedes any write | T-10, T-11; C-4; AC-M2-1 |
| **T-10** | truncation | temp file | the candidate is 10 % of the original | attempt the write | refused by the size guard **and** by V3 | the refusal reason | none | T-09 |
| **T-11** | F-03 — a semantic change | temp file | the candidate changes a constant but keeps the length and the syntax valid | attempt the write | refused by V3 — re-deriving the transformation from the original does not reproduce it | the refusal reason | none | T-09; AC-M2-2 |
| **T-12** | F-06 — TOCTOU | temp file | read the file, then modify it externally, then attempt the write with the original's hash | attempt the write | refused by V1; the externally-modified file is left untouched | the refusal reason + both hashes | none — the write is refused | T-28; AC-M2-4 |
| **T-13** | the suspension | temp project with a repairable file; **the policy file in the temp tree** sets `auto_repair: false` | run a cycle | `REPAIR_SUSPENDED`; the file is unchanged; the report is written; the cycle completes | the `repair-capability` check + the report path | none | **requires Step 0** — without root-aware policy resolution the test would consult the production policy. T-24 |
| **T-14** | an error during the repair | temp file | the write fails (injected) | attempt the write | the failure is recorded, the cycle continues, the report is written | the refusal reason + the cycle's verdict | none — the failure is on the temp tree | T-28 |
| **T-15** | an error during report production | temp project; the path `quality_guardian/reports` is occupied by a **file**, so `mkdir(parents=True, exist_ok=True)` raises `OSError` errno 17 | run a cycle | the cycle's checks are unaffected; the report failure is reported on stderr with a non-zero exit code; the **project** is untouched | the stderr diagnostic | the Guardian's own reports only | **the P-4 correction** — deterministic, portable, no ACL manipulation, no permission change. Verified: `mkdir` over an existing file raises `OSError [17]` on this host |
| **T-16** | the `post_tool_call` hook | temp project | a synthetic payload naming a file in the temp tree | run the hook entry point | exit 0; a report is written; no protected file modified | the hook's stdout/stderr + the report | none | T-17, T-18 |
| **T-17** | the `pre_verify` hook | temp project | a synthetic payload with `changed_paths` | run the hook entry point | exit 0; a report is written | the hook's stdout/stderr + the report | none | T-16, T-18 |
| **T-18** | the nudge suppression | temp project | the policy suspends repair | run the hook entry point | exit 0; **no** `continue` directive | the hook's stdout | none | T-13, T-17; **the most valuable test in the set** |
| **T-19** | an incomplete payload | no preparation | run the hook with a payload lacking `tool_input` | exit 0; no error | the hook's stderr | none | T-16 |
| **T-20** | an alternate path to a protected file | temp project | a manifest-covered file reached through `..` | attempt a write | refused | the refusal reason | none | T-21, T-23 |
| **T-21** | a case-variant path | temp project | `ConsequenceMap/domain/copy.py` | attempt a write | refused — the case gap is closed | the refusal reason | none | **the direct F-05 detector**; C-6 |
| **T-22** | over-protection | temp project | a file not in the manifest and not prefix-covered | attempt an ordinary N-1 repair | **permitted** — the protection is not over-broad | the applied repair | none | the counter-test to T-20…T-23 |
| **T-23** | a hash-matched, path-unusual file | temp project | a file with a path outside the prefixes whose hash matches a manifest row **whose row still resolves** | attempt a write | refused by the identity check | the refusal reason | none | T-20, T-25; AC-M4-4 |

### 7.2 T-24 to T-30 — the additional scenarios

The brief's own list and the review's §4.3 list diverge on the numbering of T-24 to T-30. The divergence is reconciled here by **keeping every scenario from both lists** and stating the mapping explicitly, so nothing is lost:

| Brief's list | Review's list | Final ID | Decision |
|---|---|---|---|
| T-24 root-awareness and isolation between roots | — | **T-24** | kept as the Step-0 test; it is not in the review's list because the review treated root-awareness as Step 0 rather than as a test |
| T-25 parsing of the real manifest without false positives in the fourth table | T-24 — a valid four-column table beside the entry table | **T-25** | **merged** — one test, two assertions: the real manifest parses to **52** entries, and the 13 fourth-table rows are **not** invalid entries. This covers C-1 |
| T-26 a protected file renamed or moved | T-25 | **T-26** | merged, same scenario, same assertions |
| T-27 preservation of string literals by the N-1 policy | T-26 | **T-27** | merged, with the **triple-quoted multi-line** fixture per C-5 — not the single-line fixture, which does not exhibit the defect |
| T-28 a partial write failure | T-27 — a failure between the temporary write and the rename | **T-28** | merged: the scenario covers the whole partial-write window — the temporary must not be left behind and the original must be intact |
| T-29 a failure during post-write validation | — | **T-29** | kept from the brief; the review's T-27 partly overlaps it and is folded in |
| T-30 rollback and effective content recovery | T-30 | **T-30** | merged, same scenario |
| — | T-28 — two concurrent cycles | **T-31** | **kept**, renumbered: it documents the current last-writer-wins behaviour without asserting a fix (M-6 is out of scope) |
| — | T-29 — an unreadable protected file | **T-32** | **kept**, renumbered: it distinguishes "cannot verify" from "divergent" — the refinement in §5.1.2 |
| — | — | **T-33** | **added**: the search-root-unavailable case as a **portable** scenario — the Desktop fallback root made unavailable — asserting `BLOCKED` and not `FAIL` on a host with a different layout |

**No scenario from either list is dropped.** Two are renumbered, four are merged into a single test with two assertions each, and one is added. The count moves from 23 to **33**, and the matrix grows from 23 rows to 33.

#### T-24 — root-awareness and isolation between roots

| | |
|---|---|
| **Risk covered** | the write path consults the production policy instead of the caller's root |
| **Preconditions** | two temporary roots; root A has **no** policy file, root B has a policy with `auto_repair: false` |
| **Fixture** | one repairable file in each root |
| **Simulated action** | call the write path in root A, then in root B, then in root A again |
| **Expected result** | root A's write **proceeds**; root B's write is **refused** as `REPAIR_SUSPENDED`; root A's second write **proceeds** again. The production policy is consulted **zero** times — asserted by hashing it before and after |
| **Evidence** | the three outcomes + the production policy's unchanged hash |
| **Side-effect risk** | none — both roots are temporary |
| **Relates to** | Step 0; T-13; AC-0.1…AC-0.5 |

#### T-25 — the real manifest, parsed without false positives

| | |
|---|---|
| **Risk covered** | the parser mis-scope: the 13 four-column rows flagged as invalid, or the protected set silently reduced from 52 to 39 (C-1, P-1) |
| **Preconditions** | a copy of the **real** `docs/PHASE-2A-MANIFEST.md` inside a temp tree, with the 39 project files and the 13 Desktop artefacts reproduced at the same relative locations |
| **Fixture** | the real manifest, byte-for-byte |
| **Simulated action** | run the manifest check |
| **Expected result** | the parser captures **52** entries — 39 from table 1 and **13** from table 4; `evidence.invalid_entries` is **empty**; the three non-entry tables contribute **nothing**; the verdict for the real state is `WARNING` (the known `copy.py` divergence), **not** `FAIL` |
| **Evidence** | `evidence.expected == 52`, `evidence.found == 52`, `evidence.invalid_entries == []`, `evidence.additional == 0` after exemptions |
| **Side-effect risk** | none — the copy is temporary and the real manifest is read-only |
| **Relates to** | C-1, C-2, C-3; T-01…T-08; AC-M1-3, AC-M1-4, AC-M1-5, AC-M1-9, AC-M1-10 |

**This is the test that would have caught the review's own misreading of the regex.** It must fail if the parser accepts a malformed manifest, and it must fail if the parser rejects the legitimate one.

#### T-26 — a protected file renamed or moved

| | |
|---|---|
| **Risk covered** | the rename bypass: a protected file moves out of its path and loses its protection (§5.4.3) |
| **Preconditions** | a temp project whose manifest lists a file; the file exists with a matching hash |
| **Fixture** | the manifest-covered file, renamed to a path outside every covered prefix |
| **Simulated action** | attempt a repair on the renamed file |
| **Expected result** | **refused** — the manifest row still resolves to a file with that hash, so the content is protected wherever it lives |
| **Evidence** | the refusal reason naming the hash-anchored protection |
| **Side-effect risk** | none — the temp tree only |
| **Relates to** | T-20, T-21, T-23; AC-M4-4, AC-M4-5 |

**The counter-case belongs in the same test:** an unrelated file that merely *shares* content with a protected file, whose manifest row does **not** resolve, must be **repairable** — otherwise the protection is over-broad (AC-M4-6).

#### T-27 — preservation of string literals by the N-1 policy

| | |
|---|---|
| **Risk covered** | X-1 — the transformation alters string content (C-5) |
| **Preconditions** | a temp `.py` file with trailing whitespace **inside** literals |
| **Fixture** | a single-line literal with inner spaces; a **triple-quoted multi-line** literal with trailing whitespace at the end of a physical line; a literal with `\t` and `\n` escapes; a multi-line literal with embedded quotes |
| **Simulated action** | apply the N-1 transformation |
| **Expected result** | the literal **regions are byte-identical** before and after; only whitespace genuinely outside a literal may be removed; the transformation refuses (rather than guesses) whenever neutrality cannot be proved |
| **Evidence** | the before/after bytes of each literal region |
| **Side-effect risk** | none — the temp tree only |
| **Relates to** | §6; V3; AC-N1-2, AC-N1-3, AC-N1-4, AC-N1-5 |

#### T-28 — a partial write failure

| | |
|---|---|
| **Risk covered** | a failure between the temporary write and the rename: a stray `.guardian-tmp` left behind, or a half-written original |
| **Preconditions** | a temp file; the rename step fails (injected) |
| **Fixture** | the original file with known bytes |
| **Simulated action** | attempt the write; the rename fails |
| **Expected result** | the original is **byte-identical** to its pre-write state; no `.guardian-tmp` survives; the failure is recorded with a distinct reason |
| **Evidence** | the original's hash after the failure + the absence of the temporary |
| **Side-effect risk** | none — the temp tree only; the temporary must be cleaned up by the implementation under test |
| **Relates to** | T-12, T-14; M-8 (out of scope, but the cleanup expectation is stated here) |

#### T-29 — a failure during post-write validation

| | |
|---|---|
| **Risk covered** | the write succeeds but the post-write validation fails — the file is now on disk in a state the Guardian rejects |
| **Preconditions** | a temp file; the post-write verification fails (injected) |
| **Fixture** | the original file with known bytes |
| **Simulated action** | attempt the write; the verification after the write fails |
| **Expected result** | the cycle **rolls back** to the original bytes, or reports the failure with the file's state stated explicitly — the two outcomes must not be conflated |
| **Evidence** | the final bytes of the file + the recorded reason |
| **Side-effect risk** | none — the temp tree only |
| **Relates to** | T-28, T-30; the rollback criteria of §10 |

#### T-30 — rollback and effective content recovery

| | |
|---|---|
| **Risk covered** | the revert path is untested — and it is the **only** path that restores content (`if regressed: repair.write_file_text(path, original)`) |
| **Preconditions** | a temp project; the repair is applied successfully; the subsequent test run **regresses** |
| **Fixture** | a repairable file whose repair triggers a regression |
| **Simulated action** | run a cycle; let the repair be applied, then let the tests fail |
| **Expected result** | the original content is restored **byte-for-byte**; the proposal is marked `reverted`; the revert is **not** refused by V3 (the explicit revert exemption of §5.2.3 applies); the cycle still completes and writes its report |
| **Evidence** | the file's hash before and after, the proposal's state, the report path |
| **Side-effect risk** | none — the temp tree only |
| **Relates to** | T-12, T-28, T-29; AC-M2-6; the rollback section §10 |

#### T-31 — two concurrent cycles

| | |
|---|---|
| **Risk covered** | R-6 / M-6 — concurrent cycles can interleave; `save_state` has no lock |
| **Preconditions** | two cycles against the same temp project |
| **Fixture** | one temp project |
| **Simulated action** | run two cycles concurrently |
| **Expected result** | the behaviour is **documented**, not asserted as fixed: the last writer wins, and no file is corrupted |
| **Evidence** | the two cycles' verdicts and the final file state |
| **Side-effect risk** | none — the temp tree only |
| **Relates to** | M-6, which is explicitly **out of scope**; this test documents, it does not require a fix |

#### T-32 — an unreadable protected file

| | |
|---|---|
| **Risk covered** | "cannot verify" is reported as "content differs" — `detect.sha256_of` returns `""` and the empty hash is compared against the expected one |
| **Preconditions** | a temp manifest row pointing at a file that cannot be read (injected) |
| **Fixture** | the manifest entry and the unreadable file |
| **Simulated action** | run the manifest check |
| **Expected result** | **`BLOCKED`** with the path in `evidence.unreadable` — **not** `FAIL`, and **not** counted as divergent |
| **Evidence** | the verdict + `evidence.unreadable` + `evidence.divergent` (empty) |
| **Side-effect risk** | none — the failure is injected, not provoked through ACLs |
| **Relates to** | T-08; AC-M1-8 |

#### T-33 — an unavailable search root, portably

| | |
|---|---|
| **Risk covered** | the Desktop fallback root is hard-coded; on a host with a different layout the check would report 13 files as **missing** (`FAIL`) when the truth is that the root is **unavailable** |
| **Preconditions** | the fallback root made unavailable — the configured root does not exist |
| **Fixture** | a temp manifest row under the fallback root |
| **Simulated action** | run the manifest check |
| **Expected result** | **`BLOCKED`** (*"the search root is unavailable"*), with the root named in the evidence — **not** `FAIL` |
| **Evidence** | the verdict + `detail` + the evidence's root list |
| **Side-effect risk** | none — no directory is removed; the root is *made unavailable by construction*, not by deleting anything |
| **Relates to** | T-08, T-32; AC-M1-7 |

### 7.3 Coverage of the brief's mandatory list

| Required scenario | Test | Status |
|---|---|---|
| Protected file missing | T-01 | ✔ |
| Protected file altered | T-02 | ✔ |
| Empty manifest | T-03 | ✔ |
| Malformed manifest | T-04 | ✔ |
| **Duplicate entry — unambiguous result** | **T-05** | ✔ — `FAIL`, `invalid_entries` |
| Invalid path | T-06 | ✔ |
| Invalid hash | T-07 | ✔ |
| **Search root unavailable → `BLOCKED`** | **T-08**, T-33 | ✔ |
| **Injected failure, no real permissions** | **T-15** | ✔ — P-4's correction |
| Invalid content of similar size | T-09 | ✔ — with a verified non-compiling fixture (C-4) |
| Truncated content | T-10 | ✔ |
| Semantically different content | T-11 | ✔ |
| TOCTOU | T-12 | ✔ |
| Repair during suspension | T-13 | ✔ — requires Step 0 |
| Error during the repair | T-14 | ✔ |
| Error during report production | T-15 | ✔ |
| `post_tool_call` execution | T-16 | ✔ |
| `pre_verify` execution | T-17 | ✔ |
| **Root-awareness and isolation between roots** | **T-24** | ✔ |
| **Real manifest parsed without false positives** | **T-25** | ✔ |
| **Protected file renamed or moved** | **T-26** | ✔ |
| **String literals preserved** | **T-27** | ✔ |
| **Partial write failure** | **T-28** | ✔ |
| **Failure during post-write validation** | **T-29** | ✔ |
| **Rollback and content recovery** | **T-30** | ✔ |

**Total: 33 tests. Every one uses an isolated fixture. No real protected file is ever a destructive target.**

---

## 8. G-06 and the suite's acceptance criteria

*Secção 8 — G-06 e critérios da suite.*

### 8.1 The current definition

```python
class G06ReRunTest(IsolatedProjectTestCase):
    """G6 — the tests are re-run after the repair."""

    def test_the_cycle_re_runs_the_tests_after_a_repair(self):
        target = self.root / "scratch" / "sample_copy.py"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("def add(left, right):\n    return left + right   \n", encoding="utf-8")
        cycle = guardian.run_cycle(trigger="g06", root=self.root)
        applied = [p for p in cycle.repair_outcome.proposals if p.applied]
        self.assertTrue(applied, "the mechanical repair was not applied")
        self.assertTrue(any(r.module for r in cycle.test_runs))
        self.assertGreater(len(cycle.test_runs), 1)
        self.assertFalse(target.read_text(encoding="utf-8").endswith("   \n"))

    def test_a_manifest_covered_file_is_never_rewritten(self):
        target = self.root / "consequence_map" / "sample.py"
        target.write_text("X = 1   \n", encoding="utf-8")
        before = target.read_text(encoding="utf-8")
        guardian.run_cycle(trigger="g06b", root=self.root)
        self.assertEqual(target.read_text(encoding="utf-8"), before)
```

The first test asserts that a repair **is applied**. Under the suspension it fails, because `write_file_text` raises `RepairSuspended` and nothing catches it. **That is the correct consequence of the suspension** — the test's *intent* is sound and must be preserved; what has changed is the **environment** it runs in.

### 8.2 The real cause of the 29/30 result — P-3

**Not** the suspension's logic, and **not** the test's assertion. It is a **scope error in the write path**. The chain, verified empirically in this task:

```
a) guardian._attempt_repairs → config.auto_repair_enabled(root=self.root)
   → repair_policy(<temp>) → no policy file → DEFAULT_AUTO_REPAIR = True
   → PROCEEDS to the write

b) repair.write_file_text(path, fixed) → config.auto_repair_enabled()   ← NO ROOT
   → repair_policy(PROJECT_ROOT real) → auto_repair = False
   → raises RepairSuspended
```

Measured:

```
auto_repair_enabled(<temp>)  -> True      (the isolated tree has no policy)
auto_repair_enabled()         -> False     (the production tree does)
write_file_text(...)          -> RepairSuspended
```

**The consequence is larger than one failing test.** Because the write path always consults the **production** policy, **no isolated test can express its own policy**. A test that wants "repair enabled" gets whatever the production machine says; a test that wants "repair suspended" cannot say so without mutating the production policy file. The Guardian's own suite is therefore **non-hermetic** — it depends on the host's global state. This is why Step 0 precedes everything (§4).

### 8.3 Why the test must change environmentally, not by weakening the assertion

**The two original assertions are retained verbatim:**

| Original assertion | Retained? |
|---|---|
| `assertTrue(applied, "the mechanical repair was not applied")` | ✔ |
| `assertTrue(any(r.module for r in cycle.test_runs))` | ✔ |
| `assertGreater(len(cycle.test_runs), 1)` | ✔ |
| `assertFalse(target.read_text(...).endswith("   \n"))` | ✔ |
| `assertEqual(target.read_text(...), before)` (the second method) | ✔ |

**No assertion is removed, weakened, skipped or made conditional.** The change is **environmental**: after Step 0, the test writes its own `repair-policy.json` into its own `self.root` enabling repair, instead of inheriting the machine's global state.

**This is a strict improvement in test hygiene.** The current suite's dependence on the host's global suspension state is a latent defect: with the suspension lifted, G-06 would pass for the wrong reason; with it applied, G-06 fails for the wrong reason. The per-test policy makes the suite **hermetic** — the correct property for a test suite.

### 8.4 The updated G-06

| Property | Value |
|---|---|
| Class name | `G06ReRunTest` — **kept** |
| Method count | **2 → 4** (two retained, two added) |
| Existing assertions | **all retained** — none weakened, none removed |
| New coverage | the suspension is honoured in every path |

**Retained, unchanged:**

- `test_the_cycle_re_runs_the_tests_after_a_repair` — gains the explicit per-test policy fixture; every assertion stays.
- `test_a_manifest_covered_file_is_never_rewritten` — unchanged.

**Added:**

- `test_the_suspension_blocks_the_repair_and_the_cycle_still_completes` — writes a suspending policy into `self.root`; asserts (i) the repair was **not** applied, (ii) the target file is byte-identical, (iii) the cycle produced a `repair-capability` check whose `detail` contains `REPAIR_SUSPENDED`, (iv) `cycle.result.worst` is not `PASS`, (v) the cycle's test runs were still executed — **detection and testing both operational**.
- `test_the_report_is_produced_under_suspension` — asserts `guardian.finalize(cycle, self.root)` writes a report and that the report's payload contains the `REPAIR_SUSPENDED` marker.

### 8.5 The six properties the brief requires

| # | Required property | How the updated G-06 covers it |
|---|---|---|
| 1 | The suspension blocks any repair | the new suspension test asserts no proposal was applied and the file is byte-identical |
| 2 | Detection remains operational | the same test asserts `cycle.changed_files` is non-empty |
| 3 | The report is produced | the new report test asserts the report exists and carries the marker |
| 4 | The hooks propagate no uncaught exceptions | covered by the hook tests (T-16…T-18) and by the CLI not raising |
| 5 | The suspension state is explicit | the `REPAIR_SUSPENDED` marker is asserted in both the check and the report |
| 6 | No test is weakened to obtain a pass | the two original methods keep every original assertion |

### 8.6 The suite's acceptance criteria

**A count is not an objective.** The final count is determined by the matrix actually implemented — **33** adversarial scenarios (§7) plus the existing suite — and is an **output**, not a target. A fixed number invites weakening to reach it.

| # | Criterion | Verified by |
|---|---|---|
| **AC-17** | The Phase 2A suite remains **214/214** | the Phase 2A suite run |
| **AC-18** | The Guardian's own suite passes **in full** — every test passes, with **no** test removed, skipped, weakened or marked expected-failure | the Guardian suite run |
| **AC-19** | The Phase 2A manifest, the addendum A-1 and `copy.py` are **byte-identical** to their current state | hash comparison |
| **AC-20** | The configuration and the allowlist are **unchanged** by the remediation | hash comparison |
| **AC-21** | The write path still has **exactly one** entry point for project source files | inspection |
| **AC-22** | The suspension is still in force until the owner lifts it | the policy file's content |
| **AC-23** | **No** expected-failure is introduced to hide a problem | inspection of the test files |
| **AC-24** | Every test in the T-01…T-33 matrix is **implemented** and passing | the matrix |
| **AC-25** | The Guardian's suite is **hermetic** — it produces the same result with the production policy present, absent, or altered | three runs with different production policy states, compared |
| **AC-26** | The suite writes **nothing** into the production tree | the production `last-seen.json` and policy hashes before and after |
| **AC-27** | The Guardian's own suite and the Phase 2A suite are run **separately** as well as together, and both are green | four runs (2A alone, Guardian alone, both from the root, both scoped) |

**AC-25 is the hermeticity criterion**, and it is the one that makes the whole remediation trustworthy: the suite's result must not depend on the machine's state.

---

## 9. Rollback

*Secção 9 — Rollback.*

### 9.1 Principles

1. **The suspension is the master rollback.** If anything goes wrong at any step, `auto_repair: false` stops all project-source writes immediately, whatever state the code is in.
2. **Every step is a small, revertible change.** No step introduces a data migration, a schema change or a state-format change, so every step reverts with a file restoration.
3. **The pre-remediation state is already backed up.** `…\hermes\cache\scratch\qg-pre-suspension-20261108-124516` **exists** (verified in this task) and holds the Guardian, the hooks, the allowlist and the configuration as they stood immediately after the security audit, with a per-file SHA-256 manifest in `BACKUP-SHA256.json`.
4. **The historical artefacts are never touched.** The manifest, the addendum, `copy.py` and the specification are outside every step's file list. A rollback cannot affect them.

### 9.2 The rollback procedure

| Situation | Action | Effect |
|---|---|---|
| A step's tests fail | revert that step's files | the suspension remains in force |
| The suite fails after a step | revert that step, then re-run the suite | the prior state is restored |
| A protected file is modified | **stop immediately**; set `auto_repair: false`; restore the file from the manifest's recorded hash by re-deriving it from the Phase 2A delivery; record the event | the Guardian returns to detection-only |
| The write path misbehaves in production | set `auto_repair: false` | all writes stop; detection continues |
| A wholesale rollback is needed | restore `quality_guardian/` from `qg-pre-suspension-20261108-124516`, verified against `BACKUP-SHA256.json` | the exact post-audit state |

### 9.3 The rollback of the rollback itself

The revert path — `repair.write_file_text(path, original)` — is the **only** path that restores content, and it is currently **untested**. T-30 covers it. Until T-30 passes, the rollback's own mechanism carries an unverified assumption, and that is a reason to implement T-30 **before** M-2's write-path changes, not after.

### 9.4 What is explicitly not rolled back

| Artefact | Why |
|---|---|
| `docs/PHASE-2A-MANIFEST.md` | the historical record; never modified, never restored |
| `docs/PHASE-2A-MANIFEST-ADDENDUM-A-1.md` | the truthful record of the divergence |
| `consequence_map/domain/copy.py` | the reconstruction; never modified by the remediation |
| The 51 matching manifest entries | the delivered Phase 2A state |
| `config.yaml` and the allowlist | the suspension is implemented in the Guardian, not in the Hermes configuration |

---

## 10. Residual risks

*Secção 10 — Riscos residuais.*

Re-evaluated against the real code and the real manifest. **None of these is implemented by this task.** F-07, F-08, M-7, M-8 and M-9 are re-assessed below with the corrected numbers from §3.

| Risk | Severity | Why it remains | Temporary mitigation | Needs approval? |
|---|---|---|---|---|
| **F-07** — the Telegram policy is not implemented; the Guardian is silent | MEDIUM | M-1…M-4 do not mention notification. The audit's M-5 does | the owner reviews the reports at each phase boundary | **Yes** — D-10 |
| **F-08** — `module_for_path` returns `""` for a project-relative path | LOW | not a safety defect; the runtime passes absolute paths | latent, not active | no remediation assigned |
| **R-6 / M-6** — concurrent cycles can interleave; `save_state` has no lock | MEDIUM | M-1…M-4 do not mention locking | the write is atomic; the baseline write is atomic; T-31 documents the behaviour | **Yes** — out of scope |
| **M-7** — no verifiable backup of the original before a write | MEDIUM | M-2's text does not include a backup; the audit lists it separately | the write path is fail-closed under M-2, and the suspension is in force. **The risk of not implementing it:** a power loss or a filesystem fault between the rename and the flush could leave a replaced file whose content was never durably written, and there is no separate copy of the original to restore from — recovery would depend on re-deriving the file from the Phase 2A delivery, which is only possible for the 51 manifest-covered files, **not** for ordinary project files | **Yes** — D-6 |
| **M-8** — no `flush`/`fsync`; the temporary is not validated before the rename; it is not cleaned up on failure | LOW | M-2's text covers validation of the *content*, not the durability of the write | the replacement is atomic; the temporary is in the same directory. **The risk of not implementing it:** a `.guardian-tmp` may survive a failed write and accumulate; the durability of the renamed file is not guaranteed against a power loss | **Yes** — D-6 |
| **M-9** — the absence check for the package files outside `tests/` | — | **Covered by M-1**, on the corrected arithmetic: the manifest lists **32** files under `consequence_map/`, of which **15** are under `consequence_map/tests/`, so **17** are outside `tests/`. M-1 asserting over the expected rows covers **all 52** entries — including those 17 — for absence. `_check_tests_preserved` compares `before`/`after` **within** a cycle, so it detects a test file deleted *during* a cycle but **not** one deleted *before* it; that gap is exactly what M-1 closes | — | **No** — redundant, D-7 |
| **M-11** | — | no per-cycle lock file | future | future |
| **M-12** | — | the artefact-identity model does not extend beyond the manifest | future | future |
| **M-13** | LOW now | the Guardian is not read-only by default | the **current suspension is a temporary form of exactly this** | future |
| **M-14** | LOW | symlink and hard-link behaviour is unproven on this host (`os.symlink` raised `OSError`) | M-4's I2/I3 mitigate it | future |
| **X-1** — the N1 transformation is not token-aware | MEDIUM | **Certain** — it is the current behaviour | the suspension is in force; §6 bounds it | **Yes** — within M-2 |
| **C-8** — the N1 `changed` flag is unreliable and the transformation slightly exceeds its scope | LOW | current behaviour | the suspension is in force; §6 requires truthful accounting | **Yes** — within M-2 |

**On M-7 and M-8.** The brief requires explaining the risk of **not** implementing them without automatically widening M-2's scope. That is done in the table above: both are real, both are deferred, and the residual exposure is stated plainly — the write path after M-2 has no durable backup and no `fsync`, so a power loss could leave a replaced file with unflushed content, and for ordinary project files there is no recovery path beyond re-deriving the content. **Neither is folded into M-2.** They are D-6, an explicit scope-boundary decision for the owner.

**On M-9.** The redundancy claim is now **quantitatively demonstrated**: 32 package files, 15 under `tests/`, **17** outside; M-1's expected-row assertion covers all 52 manifest entries for absence. The prior figure of 19 was wrong; the corrected figure is 17 (C-2).

---

## 11. The decision matrix — D-1 to D-10

*Secção 11 — Matriz de decisões D-1 a D-10.*

The numbering of the prior review is preserved, so the two documents remain comparable. Every recommendation is updated with the new information from §3.

| # | Original question | Recommendation | Justification | If accepted | If rejected | Authorisation |
|---|---|---|---|---|---|---|
| **D-1** | Authorise the implementation of M-1 to M-4? | **Remain pending.** No authorisation is implied by this document | this is a specification; a specification cannot authorise itself, and the task was explicitly read-only | Steps 0–6 become executable | nothing is implemented; the Guardian stays detection-only | **OWNER ONLY** |
| **D-2** | Confirm the suspension stays in force through the steps? | **Keep suspended** until every correction and test is validated | a partially-implemented write path is more dangerous than no write path | the write path is exercised only in isolated trees; the production tree is never a target | the production path stays inert, but the remediation cannot be validated end-to-end | **OWNER ONLY** |
| **D-3** | Is an unlisted file a defect or an observation? | **Observation only** — recorded, never affecting the verdict. Scoped to the three manifest-covered prefixes with the declared exemption list (the manifest itself and addendum A-1) | the manifest cannot list its own hash; the addendum records a divergence. With the exemptions, the count is **0 today** (C-3) | no false `FAIL` from the Guardian's own artefacts | the plan cannot be implemented as written; a false `FAIL` on every cycle is introduced | Technical, with owner awareness |
| **D-4** | Is a structurally incomplete manifest row `FAIL` or `NOT_VERIFIED`? | **`FAIL`**, with the row named in `evidence.invalid_entries`. **The same verdict applies to a duplicate entry** (T-05) | a malformed row is a defect **in the manifest**, not an inability to verify. `NOT_VERIFIED` would mean "the check could not run" — but the check did run and found a bad row | the manifest's own integrity is asserted, closing the F-02 class completely | a corrupt manifest row could pass as "not verifiable" | Technical |
| **D-5** | Is an unavailable search root `BLOCKED` or `FAIL`? | **`BLOCKED`**, with the root named | the two facts are different: the file is missing vs. the place to look for it is unavailable. `BLOCKED` is the existing verdict for exactly this meaning. On another host without the Desktop layout, `FAIL` would produce **13** false failures | the check is portable and honest about *why* | a missing root would be reported as a missing file — indistinguishable from a deleted artefact | Technical |
| **D-6** | Are M-7 (backup) and M-8 (fsync) deferred? | **Defer both**, and record the residual risk explicitly | M-1…M-4's texts do not mention a backup or durability. Expanding M-2's scope would violate the brief's scope discipline | the write path has no durable backup and no `fsync`; a power loss could leave a replaced file with unflushed content, and ordinary project files have no recovery path | the write path gains a verifiable backup and durable writes, at the cost of scope and complexity | **OWNER — scope boundary** |
| **D-7** | Is M-9 dropped as redundant after M-1? | **Drop M-9 as a separate change**, and record the corrected figure of **17** | **Demonstrated** (C-2): the manifest lists 32 package files, 15 under `tests/`, so 17 are outside. M-1 covers all 52 entries for absence; `_check_tests_preserved` cannot detect a file deleted *before* a cycle; M-1 can | one change covers what two would | a redundant second change, with an incorrect count, is implemented | Technical, with owner awareness |
| **D-8** | Define the suite count and the approval criterion | **Criterion:** *"every test passes, with no test removed, skipped, weakened or marked expected-failure."* The count is an **output**: **33** adversarial scenarios plus the existing suite — **not** a target | a fixed number invites weakening to reach it. The current 30 is a count of methods, verified by parsing | a criterion no implementation can game | a count becomes a proxy for quality | Technical |
| **D-9** | The `copy.py` divergence | **Keep it explicitly documented; do not touch the file and do not change the baseline** | the original bytes are not recoverable on this machine (searched: every loose file, 19 ZIPs' every member, 14 971 `state.db` messages — all by exact SHA-256). The reconstruction is functionally equivalent (17/17 contract tests, 214/214 suite) but is **not** the delivered artefact | the divergence stays visible on every cycle as a `WARNING`; the manifest keeps the original hash; the addendum remains the record | the reconstruction stays unaccepted, and the Guardian keeps reporting a known divergence | **OWNER ONLY** |
| **D-10** | The scope of the Telegram policy | **Two distinct mechanisms, explicitly separated.** **(a) Completion notification** — a task or verification ended and needs a decision, authorisation or review: one message per event, with a dedupe key so the same unchanged incident is not repeated. **(b) Operational alerting** — a *continuous* mechanism watching for critical failures: a **different** channel, a **different** trigger and an **explicit opt-in** | the audit's F-07 is about the **absence** of the policy. M-5's text spans two mechanisms with very different semantics. Conflating them would mean either spamming the owner or under-reporting a critical failure | the owner is informed of decisions and critical failures, without a continuous alert service | the Guardian stays silent; a critical failure at 3 a.m. is recorded and unnoticed | **OWNER — scope boundary** |

### 11.1 The three categories

| Category | Decisions |
|---|---|
| **Owner only** — cannot be inferred from any evidence | **D-1, D-2, D-9** |
| **Scope boundaries** — require an explicit statement of what is *not* being done | **D-6, D-10** |
| **Technical** — settle by following the recommendation; no owner judgement required | **D-3, D-4, D-5, D-7, D-8** |

**D-1, D-2 and D-9 remain pending.** Nothing in this document, and nothing in the request that produced it, constitutes approval of any of them.

---

## 12. The phased implementation plan

*Secção 12 — Plano faseado de implementação.*

**This is a plan. No step has been executed.** Each step is small, independently verifiable and independently revertible.

```
Step 0 (root-awareness) ─► Step 1 (M-1) ─► Step 2 (M-4) ─► Step 3 (M-2) ─► Step 4 (M-3) ─► Step 5 (G-06 + T-matrix) ─► Step 6 (independent validation) ─► Step 7 (OWNER ONLY)
```

### Step 0 — root-awareness (P-3)

| | |
|---|---|
| **Preconditions** | owner authorisation (D-1). The suspension in force. |
| **Files** | `quality_guardian/repair.py::write_file_text`; `quality_guardian/guardian.py::_attempt_repairs` (both call sites). `config.py` — **no change** |
| **Allowed changes** | add the `root` parameter and thread it; make the policy check root-aware; make the default explicit rather than implicit |
| **Tests** | before: the G06 error. after: the existing G06 passes **because** the isolated tree's own policy governs; plus T-24 (isolation between roots) and the hermeticity assertion of AC-0.3 |
| **Completion** | AC-0.1…AC-0.6; the production policy and `last-seen.json` unchanged by a full suite run |
| **Rollback** | revert `write_file_text` and the two call sites |
| **Authorisation** | **D-1** |
| **Risk** | a caller that omits `root` falls back to the production root — mitigated by AC-0.5, which requires the default to be explicit |

### Step 1 — M-1: the manifest check's verdict

| | |
|---|---|
| **Preconditions** | Step 0 complete |
| **Files** | `quality_guardian/guardian.py::_check_manifest_integrity` — only |
| **Allowed changes** | the seven-state accounting of §5.1.2; the **table-scoped parser** of §5.1.3; the additional-files scope of §5.1.4; the `missing → FAIL` rule; the unparseable manifest → `NOT_VERIFIED`; an unavailable root → `BLOCKED`; an unreadable file → `BLOCKED`; the `rewritten_paths` exemption extended to the missing list |
| **Tests** | before: T-01, T-03, T-04, T-08 (currently producing `PASS`). after: T-01…T-08, T-25, T-32, T-33, plus the existing P03/P06/P08 unchanged |
| **Completion** | AC-M1-1…AC-M1-11; the real manifest still yields `WARNING` for the known `copy.py` divergence |
| **Rollback** | revert the one function |
| **Authorisation** | **D-1**, plus the owner's awareness of D-3, D-4, D-5 |
| **Risk** | the P-1 false-`FAIL` if the parsing is not table-scoped; the reduction of the protected set from 52 to 39 if the parser accepts only three-column rows (C-1); noise if "additional" is unscoped (C-3) |

### Step 2 — M-4: identity-based protection

| | |
|---|---|
| **Preconditions** | Step 1 complete — the manifest's row set is now trustworthy, and it is trustworthy at **52** entries |
| **Files** | `quality_guardian/config.py` — `is_manifest_protected`, `is_protected`, a new `manifest_protection_for`; `quality_guardian/repair.py::apply_level1_fixes_in_project` |
| **Allowed changes** | resolve before comparing; build the protected set from the manifest with the prefix set as the fallback; the hash clause stated as in §5.4.3 so a **renamed** protected file stays protected; the collision rule between the two search roots recorded in the evidence; keep both public signatures as wrappers |
| **Tests** | before: T-21 (currently bypassing the guard — reproduced). after: T-20…T-23, T-26, plus P01/P02/P09/P10 unchanged |
| **Completion** | AC-M4-1…AC-M4-10 |
| **Rollback** | revert `config.py` and `apply_level1_fixes_in_project` |
| **Authorisation** | **D-1** |
| **Risk** | over-broad protection blocking legitimate repairs — mitigated by T-22 and AC-M4-8 |

### Step 3 — M-2: artefact-identity validation on the write path

| | |
|---|---|
| **Preconditions** | Step 2 complete — the hash check is shared and must be implemented **once** |
| **Files** | `quality_guardian/repair.py` — `write_file_text`, a new `validate_repair`, the transformation; `quality_guardian/guardian.py::_attempt_repairs` (both call sites) |
| **Allowed changes** | V1 hash revalidation **inside** the write choke point; V2 compile; V3 transformation fidelity; V4 parse; the **token-aware** transformation (§6); the explicit revert exemption in the API; the truthful `changed` accounting; the `expected_hash` and `root` parameters |
| **Tests** | before: T-09, T-10, T-11, T-12 (currently escaping or unsupported). after: T-09…T-14, T-27, T-28, T-30, plus P01/P02 unchanged |
| **Completion** | AC-M2-1…AC-M2-9, AC-N1-1…AC-N1-7 |
| **Rollback** | revert `repair.py` and the two call sites |
| **Authorisation** | **D-1**, plus the owner's awareness of D-6 (M-7/M-8 stay deferred) |
| **Risk** | false refusals on files that were already invalid — mitigated by the distinct refusal reason (AC-M2-9); a revert refused by V3 — mitigated by the explicit exemption; an encoding false refusal — mitigated by a distinct "encoding" reason |

### Step 4 — M-3: the suspension as a controlled state

| | |
|---|---|
| **Preconditions** | Step 3 complete — M-2 changes the write path M-3 makes safe to interrupt |
| **Files** | `quality_guardian/repair.py` — the refusal signal and the structured result; `quality_guardian/guardian.py::_attempt_repairs`, `run_cycle`; `quality_guardian/hook.py` — the nudge decision; `quality_guardian/cli.py` — a top-level guard |
| **Allowed changes** | the raise becomes a structured refusal with machine-checkable reasons; the two suspension branches unified into one; the `REPAIR_SUSPENDED` state; the **source-scoped** nudge exclusion (§5.3.4); the CLI guard |
| **Tests** | before: the current G06 error; T-13…T-19 (unsupported today). after: T-13…T-19 |
| **Completion** | AC-M3-1…AC-M3-9 |
| **Rollback** | revert the return shape and the call site; the suspension stays in force |
| **Authorisation** | **D-1**, plus D-2 |
| **Risk** | a real fault misreported as a policy refusal — mitigated by the distinct reason prefixes |

### Step 5 — the G-06 update and the full T-matrix

| | |
|---|---|
| **Preconditions** | Step 4 complete |
| **Files** | `quality_guardian/tests/test_guardian.py::G06ReRunTest`; new test modules for the T-matrix |
| **Allowed changes** | the G-06 update of §8.4; the implementation of **T-01…T-33**. **No existing test may be removed, weakened, skipped or marked expected-failure** |
| **Tests** | before: 29/30 with one error. after: every test passes, with nothing removed, skipped or weakened |
| **Completion** | AC-17…AC-27 |
| **Rollback** | revert the test files |
| **Authorisation** | **D-1**, plus D-8 (the acceptance criterion) |
| **Risk** | a test that depends on the host's global state — eliminated by Step 0 and the per-test policy; a false-positive test — eliminated by requiring each test to assert the **reason**, not merely the absence of an exception |

### Step 6 — independent final validation

| | |
|---|---|
| **Preconditions** | Step 5 complete |
| **Files** | **none** — validation only |
| **Allowed changes** | a full re-run of both suites; a hash comparison of the manifest, the addendum, `copy.py`, the configuration, the allowlist and the policy file; a re-derivation of the 52-entry matrix; a fresh read of the write path to confirm there is still exactly one entry point; a hermeticity check (AC-25) |
| **Tests** | the four runs of AC-27 |
| **Completion** | AC-1…AC-27, all of them |
| **Rollback** | not applicable |
| **Authorisation** | none — read-only |

### Step 7 — reactivation (OWNER ONLY, a separate decision)

| | |
|---|---|
| **Preconditions** | Steps 0–6 complete **and** Step 6's validation passed |
| **Files** | `quality_guardian/state/repair-policy.json` — **one field** |
| **Allowed changes** | `auto_repair: false` → `true`, with the authorisation recorded |
| **Completion** | the owner's explicit confirmation, recorded |
| **Rollback** | set `auto_repair` back to `false` |
| **Authorisation** | **OWNER ONLY — a separate decision, not a consequence of passing tests** |

**Reactivation is never a consequence of passing tests.** Step 7 requires a separate, explicit decision, recorded with the authorisation that granted it.

### 12.1 Why this order

- **Step 0 first** because the suite cannot be trusted to test the intended behaviour until it is hermetic (P-3), and because T-13, T-18 and T-24 depend on it.
- **Step 1 before Step 2** because M-4 builds the protected set from the manifest, and M-1 is what makes that set trustworthy — at the correct size of **52**.
- **Step 2 before Step 3** because they share the write-time hash check and must be implemented **once**.
- **Step 3 before Step 4** because M-2 changes the write path M-3 makes safe to interrupt.
- **Step 4 before Step 5** because the G-06 update tests M-3's behaviour.
- **Step 6 after Step 5**, and **Step 7 after Step 6**: validation first, then a separate decision.

**Could the order be different?** M-1 and M-4 are independent of each other and could be swapped; M-3 could technically precede M-2, since they are independent — but then the G-06 update would land before the write path it exercises is final, and the suite would have to be re-verified twice. The order above minimises the number of full re-verifications. One change is recommended against the brief's ordering: **T-30 (the rollback path) should be implemented early — inside Step 3 — rather than in Step 5**, because the rollback is the remediation's own safety net and is currently untested (§9.3).

---

## 13. Authorisations required

*Secção 13 — Autorizações necessárias.*

### 13.1 The single decision that unblocks everything

> **D-1 — Do you authorise the implementation of Steps 0 to 6, in that order, with the acceptance criteria of §8.6 and the scope boundaries of D-3 to D-8 as stated?**

Nothing else is needed to begin. D-3, D-4, D-5, D-7 and D-8 carry technical recommendations that can simply be followed. D-6 and D-10 need an explicit statement of what is *not* being done, but they do not block Step 0.

### 13.2 The decisions that do not block the start

| Decision | What is needed | When it is needed |
|---|---|---|
| **D-2** | confirmation that the suspension holds through Steps 0–6 | before Step 0 |
| **D-3, D-4, D-5** | awareness of the recommended verdicts — or a different instruction | before Step 1 |
| **D-6** | an explicit statement that M-7 and M-8 stay deferred, with the residual risk of §10 accepted | before Step 3 |
| **D-7** | confirmation that M-9 is dropped as redundant, with the corrected figure of 17 | before Step 1 |
| **D-8** | confirmation of the acceptance criterion — *"every test passes, with no test removed, skipped or weakened"* — rather than a count | before Step 5 |
| **D-10** | a statement of the Telegram policy's scope — completion notification, operational alerting, both, or neither | out of scope for Steps 0–6; no blocker |
| **D-9** | the `copy.py` decision — accept the reconstruction as a **known** baseline divergence with the addendum as the record, or restore the original bytes from a source outside this machine. **The original is not recoverable on this machine.** | out of scope for Steps 0–6; no blocker |

### 13.3 What is *not* being asked

This document does **not** ask for approval to:

- **implement anything** — no step has been executed;
- **lift the suspension** — that is Step 7, a separate decision;
- **modify the manifest, the addendum, `copy.py` or the baseline** — they are outside every step's file list;
- **modify the configuration, the hooks or the allowlist** — the suspension is implemented in the Guardian, not in the Hermes configuration;
- **start Phase 2B** — out of scope;
- **implement M-7, M-8 or M-5** — D-6 and D-10;
- **accept the `copy.py` reconstruction as a baseline** — D-9 remains open and this document does not accept it.

---

## 14. Integrity of the historical situation

*Secção 14 — Integridade da situação histórica.*

The following facts are preserved and were re-verified at the end of this task, after this document was written:

| Fact | State |
|---|---|
| **51 / 52 original hashes match** | preserved — the 52 rows the Guardian's regex captures were re-hashed: 51 match, 1 diverges (`copy.py`) |
| **`copy.py` is reconstructed, not recovered byte-for-byte** | preserved — the file was not touched |
| **The manifest is unchanged** | preserved — `docs/PHASE-2A-MANIFEST.md`, SHA-256 `a00984d7928294a0d9d8c91f…` |
| **Addendum A-1 is unchanged** | preserved — `docs/PHASE-2A-MANIFEST-ADDENDUM-A-1.md`, SHA-256 `2f6ebcd289c94d44afe31c6e…`, 3 001 B |
| **Automatic repair is suspended** | preserved — `auto_repair: false`, policy SHA-256 `52f60c0afb16746a54c32a31` |
| **The hooks are detection-only** | preserved — `post_tool_call` and `pre_verify` registered and allowed, neither writes |
| **The configuration and the allowlist are intact** | preserved — `config.yaml` `85b8f48f71257a46…`, allowlist `0faf6e9c07b1016e…` |
| **The baseline is unchanged** | preserved — `quality_guardian/state/last-seen.json`, SHA-256 `8c46fd54eb8385de…` |

**No code, test, configuration, hook, allowlist, manifest, baseline or protected artefact was modified by this task.** The only file created is this document.

---

## 15. Classification

# READY WITH OPEN QUESTIONS

**Why this classification.** The technical specification is complete. Every recommendation is traced to its original text in the audit; every affected function was read in the installed source; the manifest was parsed and hashed directly; the Guardian's suite was executed and its 29/30 result reproduced with its exact traceback; the Phase 2A suite was executed and confirmed at 214/214; and the eight corrections in §3 were each established by measurement, not by re-reading the prior documents. The remediation is implementable as specified, in a defined order, with a rollback at every step.

**Why not `READY FOR OWNER APPROVAL`.** The prior review's classification was `READY FOR OWNER DECISION`, and this document keeps the substance of that: **D-1, D-2 and D-9 are decisions that no evidence can settle.** D-1 asks for an authorisation. D-2 confirms a posture. D-9 concerns a historical fact — the original bytes of `copy.py` — that a search of every loose file, all 19 ZIP archives' members and 14 971 `state.db` messages has already failed to recover. Additionally, §3 introduces eight corrections to the two prior documents, and while each carries a technical recommendation, the owner should be aware that the specification it approves differs from the plan it was based on in four concrete implementation instructions.

**Why not `BLOCKED`.** Nothing prevents the work. The write surface is a single function, the dependencies are mapped, the tests are specified with their isolation and their side-effect risks, the rollback exists and is itself now covered by T-30, and every step has an owner-visible completion criterion.

**What this document is.** A specification. M-1 to M-4 have **not** been implemented. The automatic repair **remains suspended**. The Phase 2A manifest, the addendum A-1 and `copy.py` are **byte-identical** to their state at the start of this task.

---

*End of the final consolidated specification. Read-only throughout: no code, test, configuration, hook, allowlist, manifest, baseline or protected artefact was modified. The only file created is this document.*
