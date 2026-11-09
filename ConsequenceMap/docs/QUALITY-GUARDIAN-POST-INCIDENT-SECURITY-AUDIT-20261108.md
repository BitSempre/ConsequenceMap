# ConsequenceMap — Quality Guardian: post-incident security and integrity audit

**Date:** 2026-11-08
**Subject:** The Quality Guardian installed on 2026-11-08, and the `copy.py` incident
**Mode:** Read-only audit. Automatic repair was **suspended** as a safety measure before any test.
**Project root:** `C:\Users\Utente\Desktop\ConsequenceMap\`

---

## 1. Executive summary

The Guardian is **structurally sound as a detector** and **not yet safe as an autonomous writer**. Three findings block a "safe for limited auto-repair" verdict:

| # | Severity | Finding | One line |
|---|---|---|---|
| **F-01** | **CRITICAL** | A missing protected file produces `PASS` | The manifest check counts only files that exist; a deleted protected file is invisible |
| **F-02** | **HIGH** | A malformed manifest produces `PASS` | A manifest with no parseable rows yields "0 entries verified, 0 mismatched" — a clean bill of health for an empty check |
| **F-03** | **HIGH** | The 50 % size rule accepts invalid content | A same-size replacement of a file with invalid Python passes the only sanity gate; there is no syntactic or structural validation on the write path |
| **F-04** | **HIGH** | `RepairSuspended` propagates as an uncaught exception | The suspension mechanism can abort a cycle mid-flight instead of degrading to a reported refusal |
| **F-05** | **MEDIUM** | The protection is textual, not identity-based | `is_manifest_protected` is case-sensitive and compares path strings, not artefact identity |
| **F-06** | **MEDIUM** | A TOCTOU window exists between verification and write | The hash is not revalidated at the moment of the write |
| **F-07** | **MEDIUM** | The Telegram policy is not implemented | The intended notification rules have no code behind them |
| **F-08** | **LOW** | `module_for_path` only accepts absolute paths | It returns `""` for a project-relative path; the runtime happens to pass absolute paths, so it is latent rather than active |

**Verdict: `SAFE FOR DETECTION ONLY`.**

The detection half of the Guardian — change detection, test selection, execution, classification, reporting — is **operational and verified**. The repair half had **one real incident** and retains **one CRITICAL** and **two HIGH** gaps that together mean a protected artefact can be silently lost or corrupted without the Guardian reporting it. Under the owner's own criterion — *do not choose `SAFE FOR LIMITED AUTO-REPAIR` if there is any uncontrolled possibility of altering protected or normative files* — that criterion is met.

**Automatic repair is therefore suspended.** Detection, testing and reporting continue unchanged.

**The `copy.py` situation:** `ORIGINAL SOURCE NOT RECOVERED — RECONSTRUCTED FILE REMAINS A KNOWN BASELINE DIVERGENCE`. The Phase 2A state is **`51/52 ORIGINAL HASHES MATCH — 1 KNOWN RECONSTRUCTED FILE`**.

---

## 2. Incident timeline

Reconstructed from the Guardian's own persistent reports, which are the primary evidence.

| Time (UTC) | Event | Evidence |
|---|---|---|
| **12:23:35** | Baseline established: 40 files hashed, the full 214-test suite passes | `20261108T122135Z-pre_verify.json` |
| **12:23:57** | **The incident.** `consequence_map/domain/copy.py` is truncated to 1 byte by a verification script. The Guardian's very next cycle detects the manifest divergence and reports **`FAIL`** | `20261108T122357Z-post_tool_call-write_file.json` — `changed: ['consequence_map/domain/copy.py']`, `phase-2a-manifest-integrity: FAIL — 1 manifest entry/entries changed` |
| 12:23:57 | The Guardian applies a repair to the **already-truncated** file. It normalises the final newline of a 1-byte file — a no-op on content, but a write to a protected artefact | same report — `repair: path='consequence_map/domain/copy.py' level=1 applied=True` |
| 12:25:20 | A second cycle confirms the divergence persists; no mechanical fix is found | `20261108T122520Z-post_tool_call-write_file.json` — `module test_coverage_gaps failed; no deterministic mechanical fix was identified` |
| 12:35:59 | Two further cycles still report `FAIL` | `20261108T123559Z-*.json` (2 reports) |
| 12:36:49 | The manifest check is **reordered** to run after the repairs, and the manifest-protection guard is added | code change; the report becomes `WARNING` |
| 12:45:16 | **This audit begins.** Full backup of the Guardian, the hooks, the allowlist and the configuration | `…\hermes\cache\scratch\qg-pre-suspension-20261108-124516` |
| 12:46 | **Automatic repair suspended** through a policy file, not by disabling the hooks | `quality_guardian/state/repair-policy.json` |
| 12:46:58 | First cycle under the suspension: **0 repairs applied**, detection, 19 tests, reporting and baseline recording all intact | `20261108T124658Z-post-incident-audit-suspension-check.json` |

### 2.1 The exact script and the exact operation

The truncation was caused by **this pattern**, in a verification script written for the audit — **not by the Guardian**:

```python
open(path, "w").write(open(path).read() + "\n")
```

Python evaluates `open(path, "w")` **first**, which truncates the file to zero length, and only then evaluates the argument `open(path).read()`, which therefore returns the empty string. The write then leaves a single newline byte.

This was confirmed by direct demonstration in an isolated temporary directory: a file containing `ORIGINAL CONTENT HERE` became `'\n'` — one byte.

**Why the read happened after the write.** The two `open()` calls are separate expressions. Python evaluates the callable and its arguments before calling `.write()`, so the outer `open(path, "w")` — the truncating one — is evaluated before the inner `open(path).read()`. The order is the opposite of what the code reads like.

### 2.2 Were there safeguards before the write?

**No.** The script read and wrote the same path with no intermediate copy, no hash check and no size check. This is precisely the class of defect the Guardian's own size-sanity rule was later designed to catch — but the rule protects the Guardian's writes, not a caller's.

### 2.3 Was the Guardian responsible?

**No.** The Guardian's own reports show it:

1. It detected the divergence on its **next cycle** and reported it as `FAIL`.
2. It repeated the detection across **four further cycles** while the divergence persisted.
3. Its repair at 12:23:57 was a **no-op on content** — it normalised the final newline of a file that was already 1 byte.

The Guardian **detected and reported** the corruption. It did not cause it. It did, however, **write to the corrupted file** — that is F-04's sibling concern, now closed by the manifest-protection guard and the suspension.

### 2.4 Protections added after the incident

| Protection | Where | Effect |
|---|---|---|
| Manifest-protected files are never rewritten | `repair.apply_level1_fixes_in_project` | A file covered by the Phase 2A manifest is reported, not repaired |
| A repair that would shrink a file below 50 % is refused | `repair.repair_is_sane` | Catches the truncation class — but **see F-03** |
| The manifest check runs **after** the repairs | `guardian.run_cycle` | Removes the transient `FAIL` caused by a legitimate repair |
| A divergence already documented in an addendum is `WARNING`, not `FAIL` | `guardian._documented_divergences` | A known historical state does not mask a new regression |
| **Automatic repair suspended** | `quality_guardian/state/repair-policy.json` | The repair half is inert; detection is unaffected |

### 2.5 Do these protections prevent a recurrence?

**Partially.** The manifest-protection guard and the suspension together make the *Guardian* unable to write to a protected artefact. The size-sanity rule catches truncation **by size**, but F-03 shows it does not catch truncation **by content substitution**. And F-06 shows the check and the write are not atomic with respect to each other.

### 2.6 Is the reconstruction correctly identified?

**Yes.** The addendum `docs/PHASE-2A-MANIFEST-ADDENDUM-A-1.md` states plainly that the file was *reconstructed from its contract*, lists both hashes, and says the manifest was deliberately not updated. It is **not** presented as a recovery. The implementation report's §8 says the same.

**Functional equivalence is not historical identity.** The reconstruction satisfies every test that governs it — `TestACData18CopyLint` 3/3, the full suite 214/214 — but it is **not** the delivered artefact and its hash differs.

### 2.7 Is there an independent source for the original bytes?

**No.** A final read-only search by exact SHA-256 across: every loose file in `C:\Users\Utente\Desktop` and the Hermes home; **every ZIP** in both locations (19 archives, every member read and hashed); and **every message in the Hermes `state.db`** (14 971 messages, both `content` and `tool_calls`, with each 1 624-byte window decoded and hashed) — found nothing.

**`ORIGINAL SOURCE NOT RECOVERED — RECONSTRUCTED FILE REMAINS A KNOWN BASELINE DIVERGENCE`**

---

## 3. `copy.py` recovery assessment

| Property | Value |
|---|---|
| Registered hash | `bd09d066c036e43a974555ad6624026e96410d359b10f00b35a7350b20f9ba5a` |
| Current hash | `765037914b353d18d904a657…` |
| Registered size | 1 624 bytes |
| Current size | 1 390 bytes |
| `TestACData18CopyLint` | **3/3 PASS** |
| `test_coverage_gaps` (the module's own suite) | **17/17 PASS** |
| Full Phase 2A suite | **214/214 PASS** |
| Documented | `docs/PHASE-2A-MANIFEST-ADDENDUM-A-1.md` — 3 001 B, SHA-256 `2f6ebcd289c9…` |

**The reconstruction was built from three independent sources**: the three assertions in `consequence_map/tests/test_coverage_gaps.py::TestACData18CopyLint`; `PRODUCT-SPECIFICATION-v1.4.md` §12.2 and §12.3; and `docs/PHASE-2A-IMPLEMENTATION-REPORT.md` §1, which fixes the module's role and line count.

**Assessment.** The behaviour is equivalent and fully tested. The **identity** is not preserved. The file is correctly and visibly marked as a reconstruction; the manifest keeps the original hash; the Guardian reports the divergence on every cycle as a `WARNING`, not as a silent success.

**This remains an owner decision.** The audit does not accept the reconstruction as a baseline and does not modify the reconstruction.

---

## 4. Protected files security audit

### 4.1 Where the protection is applied

| Checkpoint | Applied? | Location |
|---|---|---|
| Before the **write** | **YES** — the single choke point | `repair.write_file_text` (raises `RepairSuspended` when the policy forbids it) |
| Before the **repair** | **YES** | `repair.apply_level1_fixes_in_project` → `config.is_manifest_protected` |
| Before the **file replacement** | **YES** — the same choke point wraps the `os.replace` | `repair.write_file_text` |
| Before the **restore** operation | **YES** — there is no restore operation | The Guardian has no restore path; the only write to project code is `write_file_text` |
| Against **indirect** operations | **PARTIAL** — see F-05 | `config.is_manifest_protected` compares path strings |
| In **both hooks** | **YES** | Both wrappers reach `guardian.run_cycle` → `_attempt_repairs` → `write_file_text` |
| In the **CLI** | **YES** | `cli.verify` → `guardian.run_cycle` → the same path |
| In **all** execution paths | **YES** for writes; **NO** for the manifest *check* — see F-01, F-02 | — |

**The write surface is small and well-defined.** Three modules write:

| Module | What it writes | Guard |
|---|---|---|
| `repair.py` | **project source files** | the choke point — `auto_repair_enabled()` |
| `detect.py` | the baseline state file | atomic `tmp` + `os.replace`; not project source |
| `report.py` | the reports, and prunes old ones (`unlink`) | not project source |

There is exactly **one** function in the Guardian that writes to a project source file. That is a good structural property: the suspension has a single point of control.

### 4.2 The adversarial scenarios

All executed against **artificial files and temporary manifests** in isolated directories. No real protected file was used to provoke a failure.

| ID | Scenario | Expected | Actual | Result |
|---|---|---|---|---|
| **P01** | Write over a protected file | BLOCK | **BLOCK** — `RepairSuspended` raised; the file's bytes unchanged | **PASS** |
| **P02** | Repair of a protected file | BLOCK | **BLOCK** — `apply_level1_fixes_in_project` refuses; the file is reported, not rewritten | **PASS** |
| **P03** | Divergent protected hash | WARNING/BLOCK | **FAIL** — "1 undocumented manifest divergence(s)" | **PASS** |
| **P04** | Truncated protected file | BLOCK | **BLOCK** — reported as a divergence | **PASS** |
| **P05** | **Missing protected file** | BLOCK | **PASS — "0 manifest entries verified, 0 mismatched"** | **FAIL — F-01** |
| **P06** | Missing manifest | BLOCK | **BLOCK** — `NOT_VERIFIED — the Phase 2A manifest is absent` | **PASS** |
| **P07** | **Malformed manifest** | BLOCK | **PASS — "0 manifest entries verified, 0 mismatched"** | **FAIL — F-02** |
| **P08** | Tampered manifest | BLOCK | **BLOCK** — the tamper makes the real file diverge | **PASS** |
| **P09** | Alternate path to a protected file | BLOCK | **BLOCK** — a direct write is refused; the manifest check still verifies the real file | **PASS** |
| **P10** | Bypass through the CLI | BLOCK | **BLOCK** — the CLI runs the cycle but the suspension refuses every write; the file was byte-identical afterwards | **PASS** |

**8 of 10 scenarios behave as required. P05 and P07 do not.**

### 4.3 F-01 — CRITICAL — a missing protected file produces `PASS`

- **Evidence.** P05: with `pkg/mod.py` deleted, the manifest check returns `PASS — 0 manifest entries verified, 0 mismatched`. The check loop is:
  ```python
  for rel, _size, expected in rows:
      candidate = root / rel.replace("/", os.sep)
      if not candidate.exists():
          candidate = desktop / rel.replace("/", os.sep)
      if not candidate.exists():
          missing += 1
          continue          # <-- counted, then ignored
      ...
  if mismatched: ...
  return CheckResult(verdict=PASS, detail=f"{checked} manifest entries verified, 0 mismatched")
  ```
  The `missing` counter is incremented and then **never used in the verdict**. A protected file that has been deleted is reported as a clean bill of health.
- **Location.** `quality_guardian/guardian.py::_check_manifest_integrity`.
- **Consequence.** This is the exact failure the Guardian exists to prevent. A deleted protected artefact — `storage/schema.py`, `domain/records.py`, a whole test module — would pass every cycle, and the Phase 2A gate would report `PASS` while the delivered phase was incomplete. The `tests-preserved` check only covers `consequence_map/tests/`; the other 19 protected package files have **no** absence check.
- **Repeatability.** **Trivial and deterministic.** No race, no special timing. It reproduces on every cycle against the current code.
- **Recommendation.** The verdict must account for `missing`: any manifest entry that cannot be resolved is `FAIL` (or `BLOCKED` when the search path itself is unavailable), never `PASS`. Add an explicit `missing` field to the evidence and to the verdict logic.
- **Human authorisation required.** **Yes** — this changes a pass/fail criterion.

### 4.4 F-02 — HIGH — a malformed manifest produces `PASS`

- **Evidence.** P07: the manifest is replaced with `isto nao e um manifesto`. The row regex matches nothing, so `rows` is empty, `checked` is 0, `mismatched` is empty — and the check returns `PASS — 0 manifest entries verified, 0 mismatched`.
- **Location.** `quality_guardian/guardian.py::_check_manifest_integrity`.
- **Consequence.** The same class of consequence as F-01, reached by a different route: **any** corruption of the manifest that stops it parsing disables the integrity check while reporting success. A truncated file, a partial write, a bad encoding, or a malicious edit that preserves the table header but empties the body all produce the same silent `PASS`.
- **Repeatability.** **Trivial.**
- **Recommendation.** When `rows` is empty while the manifest exists, the verdict must be `FAIL` or `NOT_VERIFIED` — never `PASS`. A check that verified **nothing** has not verified anything; `NOT_VERIFIED` is the honest verdict, and it is already defined for exactly this purpose.
- **Human authorisation required.** **Yes**.

### 4.5 Path handling

| Property | Finding |
|---|---|
| Absolute vs relative paths | `config.is_protected` resolves against `PROJECT_ROOT` and handles both. `config.module_for_path` **only** accepts absolute paths — it returns `""` for a project-relative path (F-08). The runtime passes absolute paths, so this is latent, not active. |
| Windows normalisation | `is_protected` uses `Path.resolve().relative_to()`, so `\` and `/` both work. Verified: `consequence_map\storage\schema.py` → `True`. |
| Path traversal | `is_protected` resolves first, so `consequence_map/storage/../storage/schema.py` → `True`. Verified. |
| Case sensitivity | `is_protected` → `True` for `CONSEQUENCE_MAP/storage/schema.py` (fail-safe: it protects more). **`is_manifest_protected` → `False`** for `ConsequenceMap/domain/copy.py` — it is a plain string prefix comparison. See **F-05**. |
| Symlinks / junctions | **NOT VERIFIED.** `os.symlink` raised `OSError` on this host (no developer-mode privilege). The protection relies on `Path.resolve()`, which *would* follow a symlink, but the behaviour could not be demonstrated here. |
| Hard links | **NOT VERIFIED.** Not tested; the protection is path-based, so a hard link to a protected file under a different name would present a different path. |
| TOCTOU | The hash is read, the decision is made, and the file is written later, with **no revalidation** at the moment of the write. See **F-06**. |

### 4.6 F-05 — MEDIUM — the protection is textual, not identity-based

- **Evidence.** `config.is_manifest_protected` is a `str.startswith` comparison against three prefixes. `ConsequenceMap/domain/copy.py` → `False` (case-sensitive), while the sibling function `config.is_protected` resolves the path and is case-insensitive in effect. The two protections disagree about the same file.
- **Location.** `quality_guardian/config.py::is_manifest_protected` (against `MANIFEST_PROTECTED_PREFIXES`).
- **Consequence.** The manifest guard is the *narrower* of the two, and it is the one that decides whether a delivered, hashed artefact may be rewritten. A path that differs in case, or that reaches the same file through an unnormalised route, is not covered by it. The broader `is_protected` partly compensates, but the *manifest* check — the one that reports integrity — has no equivalent identity-based guard.
- **Repeatability.** Deterministic for the case variant. The hard-link and symlink variants are **NOT VERIFIED**.
- **Recommendation.** Make the protection identity-based, as the brief requires: resolve the path, compare its real location against the resolved set of manifest-covered files, and — for defence in depth — compare the **SHA-256** of the file against the manifest's recorded hash at the moment of the write, not its path.
- **Human authorisation required.** **Yes**.

### 4.7 F-06 — MEDIUM — a TOCTOU window between verification and write

- **Evidence.** In `guardian._attempt_repairs` the content is read (`repair.read_file_text`), the fixed content is computed, and `repair.write_file_text` writes it. The file's hash is **not** revalidated between the read and the write. `write_file_text` performs a `tmp` write plus `os.replace`, so the replacement itself is atomic — but atomicity of the *replacement* is not atomicity of the *decision*.
- **Location.** `quality_guardian/guardian.py::_attempt_repairs` → `quality_guardian/repair.py::write_file_text`.
- **Consequence.** Between the read and the write, the file could be changed by another process — or by the agent itself, concurrently. The Guardian would then overwrite the newer content with content derived from the older read. On Windows, a concurrent `os.replace` onto a file held open by another process can also fail, which is handled (the write returns `False`), but the content is not rechecked.
- **Repeatability.** Requires a concurrent writer. **NOT VERIFIED** under race conditions in this audit.
- **Recommendation.** Record the pre-write hash; at the moment of the write, re-hash the target and refuse if it changed. Combine with a per-file lock.
- **Human authorisation required.** **Yes**.

---

## 5. The 50 % threshold assessment

### 5.1 The implementation

`config.MIN_REPAIR_SIZE_RATIO = 0.5`; `repair.repair_is_sane(original, fixed)` returns `len(fixed) >= int(len(original) * 0.5)`. It is consulted in `guardian._attempt_repairs` before any write.

### 5.2 The adversarial cases

| Case | Original → fixed | Sane? | Assessment |
|---|---|---|---|
| 10 % reduction | 1000 → 100 | **NO** | correctly refused |
| 25 % reduction | 1000 → 250 | **NO** | correctly refused |
| 40 % reduction | 1000 → 400 | **NO** | correctly refused |
| 49 % reduction | 1000 → 490 | **NO** | correctly refused |
| **50 % reduction** | 1000 → 500 | **YES** | exactly at the threshold — accepted |
| 51 % reduction | 1000 → 510 | **YES** | accepted |
| 75 % reduction | 1000 → 750 | **YES** | accepted |
| 90 % reduction | 1000 → 900 | **YES** | accepted |
| **File reduced to zero bytes** | 1000 → 0 | **NO** | correctly refused |
| **Invalid content, same size** | 1000 → 1000 | **YES** | **F-03 — accepted** |
| **Invalid structure, larger file** | 1000 → 2000 | **YES** | **F-03 — accepted** |

### 5.3 F-03 — HIGH — the rule is a size heuristic, not an integrity guarantee

- **Evidence.** `repair_is_sane("A"*1000, "B"*1000)` returns `True`. `"B"*1000` is not valid Python (`SyntaxError` on `compile`). The rule compares **lengths only**: `len(fixed) >= int(len(original) * 0.5)`. It never compiles the result, never parses it, never checks that the change is the whitespace it claims to be.
- **Location.** `quality_guardian/repair.py::repair_is_sane`; the write path is `write_file_text`, which performs no validation of the content it is given.
- **Consequence.** Two distinct ways to corrupt a file while satisfying the rule:
  1. **Same size, different content.** Replacing a file with invalid code of identical length passes. The Guardian would write it and then run the tests — the tests would fail, so the cycle would report `FAIL` and the file would be left broken, with the repair recorded as applied.
  2. **Larger, invalid content.** An expansion passes with no constraint at all.
  A more targeted variant: a file whose *meaning* changes while its length and syntax stay valid — a single changed constant — passes every size and syntax check. The Guardian's own N1 scope is supposed to prevent this, but the *enforcement* of that scope is the absence of a validation step, not the presence of one.
- **Repeatability.** **Deterministic** for the same-size and larger cases. For the semantic variant, the N1 scope restriction is the only barrier, and it is a code-path decision rather than an artefact check.
- **Recommendation.** The percentage rule is **not** an integrity guarantee and must not be described as one. Replace the size heuristic with a set of artefact-identity checks:
  - **Pre-write hash** recorded and revalidated at the moment of the write (closes F-06).
  - **Post-write validation**: the written file must compile (`compile()` for `.py`) and must parse (`ast.parse`).
  - **A change budget**: the written content must differ from the original *only* by the specific transformation applied — i.e. the repaired file must be byte-identical to the original after the transformation is re-derived, not merely similar in size.
  - **A known-baseline comparison**: the file's hash must match the recorded baseline, or the repair must be a deliberate, recorded deviation.
  - **A verifiable backup** of the original before any write, with the backup's hash recorded in the report.
  - **Atomic write** on the same volume, with `flush` + `fsync` where appropriate, then a validated `os.replace` (the atomicity already exists; the validation does not).
  - **Rollback** on any validation failure, with the original restored and the failure reported.
- **Human authorisation required.** **Yes** — this changes the write path.

### 5.4 Windows-specific limitations

| Consideration | State |
|---|---|
| Atomic replacement | `os.replace` on the same volume is atomic on Windows for the rename itself. **Already used.** |
| `fsync` | **Not used.** The temporary file is written and closed, then renamed. On a power loss the file could be replaced with a partially-flushed one. |
| File locking | **Not used.** Two concurrent cycles can both write the same file; the last `os.replace` wins. |
| `os.replace` onto a file open by another process | Can fail with `PermissionError` on Windows. The write returns `False`, and the caller records the failure — but there is no retry and no explicit diagnostic distinguishing "locked" from "other error". |
| Path length | The Guardian's paths are well under `MAX_PATH`. **Not a concern.** |
| Case-insensitive filesystem | The default Windows filesystem is case-insensitive, so two paths differing only in case refer to the **same** file. `is_manifest_protected`'s string comparison does not model this — see F-05. |

---

## 6. Write and repair safety

### 6.1 Every write in the Guardian

| Location | Operation | Guard | Assessment |
|---|---|---|---|
| `repair.py:288` | `tmp.write_text(content, …)` | the choke point above it | **Protected** |
| `repair.py:289` | `os.replace(tmp, path)` | the same choke point | **Protected** — atomic |
| `detect.py:89` | `tmp.write_text(json…)` | none | **Acceptable** — writes the Guardian's own baseline, atomically |
| `detect.py:90` | `os.replace(tmp, path)` | none | **Acceptable** — atomic |
| `report.py:41` | `json_path.write_text(…)` | none | **Acceptable** — the Guardian's own reports |
| `report.py:42` | `md_path.write_text(…)` | none | **Acceptable** |
| `report.py:52,55` | `old.unlink()` / `sibling.unlink()` | none | **Acceptable** — prunes old reports, bounded at 100 |

### 6.2 The six questions

| # | Question | Finding |
|---|---|---|
| 1 | Does any write destroy the original before obtaining a safe copy? | **No** — within the Guardian. The Guardian reads the content first and writes a temporary file before the `os.replace`. **The incident was in a caller, not in the Guardian** — see §2.1. The Guardian cannot protect a caller from that pattern. |
| 2 | Does any write ignore the protected-file guard? | **No** for project source: one choke point, verified by P01, P02, P09 and P10. The state and report writes are outside the protected set by design. |
| 3 | Does any write update the baseline without authorisation? | **Yes, by design.** `detect.save_state` records the current hashes at the end of every cycle, including after a repair. This is what makes the next cycle's detection correct — but it means the baseline follows the repair without a separate authorisation. The repair itself is the authorised act; the baseline merely follows. **Acceptable, but worth stating.** |
| 4 | Does any write treat a divergent hash as success? | **No** — F-01 and F-02 are the exceptions, and they are in the *check*, not the write. A divergent hash is reported as `FAIL` or `WARNING`. |
| 5 | Does anything confuse functional repair with historical recovery? | **No.** The addendum explicitly separates them, and this report preserves the distinction. The reconstruction is labelled a reconstruction everywhere it appears. |
| 6 | Can a file be left partially written after an interruption? | **The replacement cannot** — `os.replace` is atomic. But the **temporary** file can be left behind if the process dies between the write and the rename. The temporary is named `<filename>.guardian-tmp` and is **not cleaned up** on failure. **LOW** — cosmetic, but it accumulates in the project tree. |

### 6.3 The atomic-write assessment

The current implementation is: temporary file in the same directory → write → close → `os.replace`. That is the correct shape. The gaps are the ones listed in §5.3: no `flush`/`fsync`, no validation of the temporary before the rename, no backup of the original, and no rollback if the post-write state is wrong.

---

## 7. N1/N2/N3 policy audit

### 7.1 Is the classification imposed in code?

**Yes.** `repair.classify_failure(kind, path)` is the single decision point, and `repair.INELIGIBLE_KINDS = frozenset({NORMATIVE, DECISION, TEST})` is a code constant — not a skill instruction and not a prompt. The skill restates the rule; it does not define it.

### 7.2 The classification matrix

| Kind | Path | Level | Correct? |
|---|---|---|---|
| `NORMATIVE` | any | **N3** | ✔ never auto-repaired |
| `DECISION` | any | **N3** | ✔ never auto-repaired |
| `TEST` | any | **N2** | ✔ a failing test is evidence, not a defect |
| `IMPLEMENTATION` | `consequence_map/storage/schema.py` | **N3** | ✔ protected surface |
| `IMPLEMENTATION` | `consequence_map/tests/test_records.py` | **N3** | ✔ test directory protected |
| `IMPLEMENTATION` | `consequence_map/domain/records.py` | **N3** | ✔ manifest-covered |
| `IMPLEMENTATION` | `docs/PHASE-2A-MANIFEST.md` | **N3** | ✔ manifest-covered |
| `IMPLEMENTATION` | `PRODUCT-SPECIFICATION-v1.4.md` | **N3** | ✔ outside the root — protected by default |
| `IMPLEMENTATION` | `ACCEPTANCE-CRITERIA-v1.4.md` | **N3** | ✔ outside the root — protected by default |

### 7.3 The seven questions

| Question | Answer |
|---|---|
| Can N1 alter a protected file? | **No** — `apply_level1_fixes_in_project` refuses manifest-covered files, and `is_protected` refuses the nine product surfaces and the test directory. Verified by P02. |
| Can N1 alter a normative document? | **No** — the specification and the criteria are outside `PROJECT_ROOT`, and `is_protected` treats anything outside as protected. |
| Can N1 alter a manifest or a reference hash? | **No** — the manifest is manifest-covered, and no code path writes a hash into the manifest. The baseline (`last-seen.json`) is the Guardian's own state and follows any repair. |
| Can N1 alter a test to make a failure disappear? | **No** — `consequence_map/tests/` is in `PROTECTED_DIRS`, and `TEST` is an ineligible kind. |
| Can a FAIL become a PASS without re-running the checks? | **No** — the reclassification to `PASS` happens only **after** `run_test_module` returns green, and the re-run is in the same code path, immediately before it. |
| Does N2 require human intervention or authorisation? | **Yes** — N2 is `LEVEL_ASSISTED`: the Guardian records the proposal and does not apply it. |
| Is N3 ever auto-repairable? | **No** — N3 is `LEVEL_HUMAN`, and no code path applies an N3 proposal. |
| Can an uncertain result be treated as authorisation to repair? | **No** — `NOT_VERIFIED` and `BLOCKED` are distinct verdicts, and neither is in the `FAIL` set that triggers a repair proposal. |

**Assessment: the N1/N2/N3 policy is correctly and enforceably implemented.** The weaknesses found are in *what counts as a safe N1 operation* (F-03), not in the level classification.

---

## 8. Hermes hooks audit

| Aspect | Finding |
|---|---|
| Write-tool matcher | `(write_file\|patch\|execute_code\|terminal)` — the runtime honours `matcher` **only** for `pre_tool_call`/`post_tool_call`, and this is a tool event. Correct. |
| Project identification | The hook resolves the written path against `PROJECT_ROOT`. Verified: a write outside the project returns in 0.37 s with **no action**. |
| Exclusion of outside paths | **Verified.** `hook._is_project_path` rejects anything outside the root. |
| Incomplete payload | **Verified.** A payload without `tool_input` exits 0 with no error. |
| Malformed payload | **Verified.** Non-JSON on stdin exits 0, no error. |
| Directory as a path | **Verified.** Exits 0, no error. |
| Hook failure | **Verified.** The wrapper catches the subprocess result and always returns 0; the Guardian's own `hook.main` wraps everything in `try/except` and returns 0. A failure can never break the agent's turn. |
| Timeouts | The wrapper uses `subprocess.run(..., timeout=240)`; the runtime's own timeout is 120 s (`post_tool_call`) and 300 s (`pre_verify`). The runtime wins. Verified: the observed durations were 0.37–2.2 s. |
| Re-entrancy | The Guardian's own tree — including `reports/` and `state/` — is excluded from change detection, so the Guardian's writes never trigger another cycle. **Verified.** |
| Concurrent executions | `detect.save_state` uses `tmp` + `os.replace` (atomic), but there is **no lock**. Two concurrent cycles can both write; the last rename wins, and one cycle's baseline can overwrite the other's. **MEDIUM.** |
| Repair loops | Bounded by `MAX_REPAIR_ATTEMPTS = 3` per cycle and by the runtime's `max_verify_nudges = 3` per turn. |
| Behaviour on protected files | **Verified** — P02 and P09: reported, never rewritten. |
| `pre_verify` return value | `{"action": "continue", "message": …}` when the worst verdict is `FAIL`, `NOT_VERIFIED` or `BLOCKED`. **`WARNING` does not produce a `continue`** — so a documented historical divergence cannot cause a nudge loop. **Verified** in the report history: the `WARNING` cycles at 12:36:49 and later produced no directive. |

### 8.1 F-04 — HIGH — `RepairSuspended` propagates as an uncaught exception

- **Evidence.** With the suspension active, `guardian._attempt_repairs` calls `repair.write_file_text`, which raises `RepairSuspended`. The exception is **not caught** in `_attempt_repairs`; it propagates through `run_cycle` and out of `cli.verify`. The Guardian's own test suite shows it directly:
  ```
  ERROR: test_the_cycle_re_runs_the_tests_after_a_repair
  File "guardian.py", line 486, in _attempt_repairs
      if not repair.write_file_text(path, fixed):
  File "repair.py", line 282, in write_file_text
      raise RepairSuspended(...)
  ```
- **Location.** `quality_guardian/guardian.py::_attempt_repairs` (the call at the write) and `quality_guardian/repair.py::write_file_text` (the raise).
- **Consequence.** The suspension currently works **only because of the outer guards**: `hook.py` wraps everything in `try/except`, and the shell wrapper returns 0 regardless. The `cli.verify` path has **no such wrapper** — the CLI exits with a traceback instead of a report. The Guardian's own suite reports 1 error. So the safety mechanism is **coincidentally** safe in the hooks and **demonstrably broken** in the CLI, and it aborts the cycle *before* the report is written — losing the very record the audit trail depends on.
- **Repeatability.** **Deterministic** whenever a repair is attempted while the policy forbids it.
- **Recommendation.** Catch `RepairSuspended` at the call site in `_attempt_repairs` and turn it into a `NOT_VERIFIED` check result — the same shape already used for the suspension check — so the cycle completes and the report is written. The CLI must never abort on a policy decision.
- **Human authorisation required.** **Yes**.

### 8.2 The Telegram policy

**F-07 — MEDIUM — the intended notification policy is not implemented.** The Guardian contains **no** notification code: no `telegram` string appears in any module, and there is no notification module. The owner's Phase F policy — notify when a task needs a decision, when blocked, when an integrity divergence is detected, when a repair is refused for safety, or when a critical failure is found; never notify per write, per test, or repeatedly for the same incident — has **no implementation and no test**.

The consequence is a **silent** guardian: it detects, classifies and writes a report, but it never tells anyone. A critical failure at 3 a.m. would be recorded and unnoticed. This is a **gap against the stated policy**, not a defect in the existing code.

Note the interaction with the suspension: F-04 means that a refusal-by-policy currently produces **no report either**, because the exception aborts the cycle. So the two findings compound.

---

## 9. Phase 2A integrity matrix

**`51/52 ORIGINAL HASHES MATCH — 1 KNOWN RECONSTRUCTED FILE`**

The 52 entries comprise 39 files inside the project and 13 artefacts on the Desktop (the Phase 1.x ZIPs and documents).

| # | Path | Reference hash | Current hash | State |
|---|---|---|---|---|
| 1 | `consequence_map/__init__.py` | `c5b92176fa8b70da…` | `c5b92176fa…` | **INTEGRO** |
| 2 | `consequence_map/config.py` | `aa4766508174f710…` | `aa47665081…` | **INTEGRO** |
| 3 | `consequence_map/dependencies.py` | `3fc11317a6411377…` | `3fc11317a6…` | **INTEGRO** |
| 4 | `consequence_map/domain/__init__.py` | `8d9cfc8d331a2718…` | `8d9cfc8d33…` | **INTEGRO** |
| 5 | `consequence_map/domain/copy.py` | `bd09d066c036e43a…` | `765037914b…` | **DIVERGENTE** |
| 6 | `consequence_map/domain/enums.py` | `8c94af37f3434514…` | `8c94af37f3…` | **INTEGRO** |
| 7 | `consequence_map/domain/records.py` | `414579aabe042fac…` | `414579aabe…` | **INTEGRO** |
| 8 | `consequence_map/domain/serialization.py` | `13f86d77215162a3…` | `13f86d7721…` | **INTEGRO** |
| 9 | `consequence_map/domain/validation.py` | `b32de602aa5fd6c3…` | `b32de602aa…` | **INTEGRO** |
| 10 | `consequence_map/redaction/__init__.py` | `97b7c152fe11326d…` | `97b7c152fe…` | **INTEGRO** |
| 11 | `consequence_map/redaction/boundary.py` | `2c31f9a3ecc508dc…` | `2c31f9a3ec…` | **INTEGRO** |
| 12 | `consequence_map/storage/__init__.py` | `2631b1f54f763dc4…` | `2631b1f54f…` | **INTEGRO** |
| 13 | `consequence_map/storage/db.py` | `38df9a61bfba2c8d…` | `38df9a61bf…` | **INTEGRO** |
| 14 | `consequence_map/storage/migrations.py` | `f2c3a01debeebb14…` | `f2c3a01deb…` | **INTEGRO** |
| 15 | `consequence_map/storage/repository.py` | `99747f7b3eae15e7…` | `99747f7b3e…` | **INTEGRO** |
| 16 | `consequence_map/storage/schema.py` | `d4b1ab95e078cf13…` | `d4b1ab95e0…` | **INTEGRO** |
| 17 | `consequence_map/storage/triggers.py` | `8e3d389470b0ff88…` | `8e3d389470…` | **INTEGRO** |
| 18 | `consequence_map/tests/__init__.py` | `64a2edfd852e8615…` | `64a2edfd85…` | **INTEGRO** |
| 19 | `consequence_map/tests/fixtures.py` | `65c6ec2ebd640131…` | `65c6ec2ebd…` | **INTEGRO** |
| 20 | `consequence_map/tests/test_coverage_gaps.py` | `1cbd85e6f7b88423…` | `1cbd85e6f7…` | **INTEGRO** |
| 21 | `consequence_map/tests/test_enums.py` | `05e44c0001895109…` | `05e44c0001…` | **INTEGRO** |
| 22 | `consequence_map/tests/test_import_audit.py` | `5fae8e8a9eb5295a…` | `5fae8e8a9e…` | **INTEGRO** |
| 23 | `consequence_map/tests/test_integration.py` | `57222fcb239818b0…` | `57222fcb23…` | **INTEGRO** |
| 24 | `consequence_map/tests/test_migrations.py` | `efafa09cbdf82298…` | `efafa09cbd…` | **INTEGRO** |
| 25 | `consequence_map/tests/test_records.py` | `6aa583dd33214677…` | `6aa583dd33…` | **INTEGRO** |
| 26 | `consequence_map/tests/test_redaction.py` | `a83e265340bfe998…` | `a83e265340…` | **INTEGRO** |
| 27 | `consequence_map/tests/test_repository.py` | `04e8784c7c3e6faf…` | `04e8784c7c…` | **INTEGRO** |
| 28 | `consequence_map/tests/test_schema.py` | `9e9dd0b4eee9f496…` | `9e9dd0b4ee…` | **INTEGRO** |
| 29 | `consequence_map/tests/test_serialization.py` | `6a68169b80e21d5a…` | `6a68169b80…` | **INTEGRO** |
| 30 | `consequence_map/tests/test_static_audits.py` | `011998b96b73d9b5…` | `011998b96b…` | **INTEGRO** |
| 31 | `consequence_map/tests/test_triggers.py` | `4ddaef60b9d0283c…` | `4ddaef60b9…` | **INTEGRO** |
| 32 | `consequence_map/tests/test_validation.py` | `210510be1b617dc7…` | `210510be1b…` | **INTEGRO** |
| 33 | `docs/PHASE-2A-CRITERIA-MATRIX.md` | `e93bc75c6f6553f4…` | `e93bc75c6f…` | **INTEGRO** |
| 34 | `docs/PHASE-2A-IMPLEMENTATION-REPORT.md` | `09345dad876630b4…` | `09345dad87…` | **INTEGRO** |
| 35 | `evidence/_runner.py` | `c012049121a1974b…` | `c012049121…` | **INTEGRO** |
| 36 | `evidence/criteria-matrix.json` | `ed8cf3bef3578413…` | `ed8cf3bef3…` | **INTEGRO** |
| 37 | `evidence/criterion-test-map.json` | `d54cb955a8489e36…` | `d54cb955a8…` | **INTEGRO** |
| 38 | `evidence/determinism-check.json` | `22a1cfe096e7a255…` | `22a1cfe096…` | **INTEGRO** |
| 39 | `evidence/test-status.json` | `fc15b759d67e45e7…` | `fc15b759d6…` | **INTEGRO** |
| 40 | `ConsequenceMap-Phase-1.6-Documents.zip` | `d55863b071677f8c…` | `d55863b071…` | **INTEGRO** |
| 41 | `ConsequenceMap-Phase-1.8-Corrections.zip` | `50ecbae74ddfae77…` | `50ecbae74d…` | **INTEGRO** |
| 42 | `ConsequenceMap-Phase-1.9-Triage-and-Phase-2A-Proposal.zip` | `a735d83cda2436f5…` | `a735d83cda…` | **INTEGRO** |
| 43 | `PHASE-1.10-INDEPENDENT-TECHNICAL-REVIEW.md` | `c58d79c610686da2…` | `c58d79c610…` | **INTEGRO** |
| 44 | `PHASE-1.10-CRITERIA-REVIEW.md` | `3a3c1e93da0b8093…` | `3a3c1e93da…` | **INTEGRO** |
| 45 | `PHASE-1.10-DECISIONS-RECOMMENDATION.md` | `aff46c98a8ff83c4…` | `aff46c98a8…` | **INTEGRO** |
| 46 | `PHASE-1.10-REVIEW-MANIFEST.md` | `9a6b9a1234b043ed…` | `9a6b9a1234…` | **INTEGRO** |
| 47 | `PHASE-1.11-PHASE-2A-PROPOSAL-v1.1.md` | `b9feb5a3ecc372b4…` | `b9feb5a3ec…` | **INTEGRO** |
| 48 | `PHASE-1.11-CORRECTIONS-REPORT.md` | `0c8d40956b4ee3f2…` | `0c8d40956b…` | **INTEGRO** |
| 49 | `PHASE-1.11-DECISIONS-REGISTER.md` | `f8a93d58d7d9eedf…` | `f8a93d58d7…` | **INTEGRO** |
| 50 | `PHASE-1.11-VALIDATION-REPORT.md` | `7c0a66b8907c6ac4…` | `7c0a66b890…` | **INTEGRO** |
| 51 | `PHASE-1.11-DIFF-REPORT.md` | `fb1859342b5403f4…` | `fb1859342b…` | **INTEGRO** |
| 52 | `PHASE-1.11-MANIFEST.md` | `339f3441037f0a2e…` | `339f344103…` | **INTEGRO** |

| Summary | Value |
|---|---|
| Entries | 52 |
| **Original hashes match** | **51** |
| Divergent | **1** — `consequence_map/domain/copy.py`, the known reconstruction |
| Absent | 0 |
| `docs/PHASE-2A-MANIFEST.md` itself | SHA-256 `a00984d7928294a0d9d8c91f…` — **byte-identical to the delivered state** |
| `docs/PHASE-2A-MANIFEST-ADDENDUM-A-1.md` | SHA-256 `2f6ebcd289c9…` — intact, 3 001 B, names both hashes |
| Phase 2A suite | **214/214 PASS** (read-only) |
| `test_coverage_gaps` (the `copy.py` contract) | **17/17 PASS** (read-only) |

**No manifest was updated. No addendum was updated. The reconstruction was not touched.**

---

## 10. Adversarial test results

### 10.1 Environment discipline

| Rule | Compliance |
|---|---|
| No destructive test against the real project tree | **Complied.** P01–P10 and the 50 % cases used artificial files and temporary manifests in isolated directories under the system temp directory. |
| No write to a file before preserving its content | **Complied.** Every write in the audit read the content first; the backups at `…\scratch\qg-pre-suspension-20261108-124516` hold the pre-suspension Guardian with per-file SHA-256. |
| No modification of `copy.py` | **Complied.** Not touched. Its hash is `765037914b353d18…`, unchanged by this audit. |
| No manifest update | **Complied.** `a00984d7928294a0d9d8c91f…` — unchanged. |
| No acceptance of the reconstruction as baseline | **Complied.** Explicitly not accepted; recorded as a divergence. |
| No Git, commits, branches, remotes | **Complied.** `.git` does not exist in the project. |
| No Phase 2B or 2C work | **Complied.** |
| No dependency, provider or plugin installation | **Complied.** |
| No paid API or service | **Complied.** |

### 10.2 The suspension, verified

| Check | Result |
|---|---|
| The suspension is in effect | `auto_repair_enabled(project) → False` |
| The choke point refuses writes | `write_file_text` raises `RepairSuspended`; the target file is byte-identical afterwards |
| A cycle still detects | ✔ changed files identified |
| A cycle still tests | ✔ 19 tests executed under the suspension |
| A cycle still reports | ✔ report written; `repair-capability` check present |
| A cycle still records the baseline | ✔ `state-comparison` check present |
| **Repairs applied** | **0** |
| It is reversible | ✔ flipping `auto_repair` to `true` re-enables it; flipping back suspends it |
| It is surgical | ✔ the Hermes `config.yaml` was **not touched** — hash `85b8f48f71257a46…` unchanged; the allowlist unchanged; the hooks still registered and still reporting |
| Detection and reporting remain operational | ✔ `hermes hooks list` still shows both as `✓ allowed` |

### 10.3 The Guardian's own suite under the suspension

**29/30 PASS, 1 ERROR** — the error is G06, and it is the **correct consequence** of the suspension: the test expects a repair to be applied, and the policy forbids it. It confirms the suspension reaches every path. The test must be adapted to enable repair explicitly **inside the isolated environment** before it can pass again — which is itself a change this audit is not authorised to make to the Guardian.

---

## 11. Root causes

| # | Root cause | Findings it produced |
|---|---|---|
| **RC-1** | **The Guardian validates the *content* it finds, never the *existence* of what it expects.** The manifest check is written as a loop over the rows it found, not as an assertion over the rows it should have found. A missing or unparseable row is therefore outside the check's frame of reference. | F-01, F-02 |
| **RC-2** | **The size heuristic was treated as an integrity guarantee.** A percentage is a proxy for "this looks like a formatting change"; it is not evidence that the artefact is still correct. | F-03 |
| **RC-3** | **The protection is expressed as path-string comparison, not as artefact identity.** Two functions protect files, they disagree, and neither is anchored to the recorded hash at the moment of the write. | F-05, F-06 |
| **RC-4** | **The suspension was introduced as a raise, not as a return value.** An exception is the wrong control-flow shape for a policy decision, and it aborted the cycle before the report was written. | F-04 |
| **RC-5** | **The notification policy was specified but never implemented.** The owner's Phase F requirement was not translated into code when the Guardian was built. | F-07 |
| **RC-6** | **The incident was caused by a caller, not by the Guardian** — the `open(path, "w").write(open(path).read())` ordering. The Guardian detected it; what was missing was a defence that would have *prevented* the caller from doing it. | the incident itself |

---

## 12. Critical risks

| # | Risk | Severity | Exploitability | Consequence if unaddressed |
|---|---|---|---|---|
| **R-1** | A protected file is deleted and the Guardian reports `PASS` | **CRITICAL** | Trivial and deterministic | The Phase 2A gate becomes meaningless: a delivered phase can be silently incomplete and every cycle will say so |
| **R-2** | The manifest is corrupted and the Guardian reports `PASS` | **HIGH** | Trivial | The integrity check is disabled while reporting success |
| **R-3** | An invalid file of the same size passes the size rule | **HIGH** | Deterministic | A protected artefact can be replaced with invalid content; the tests then fail, but the file is already broken |
| **R-4** | The suspension aborts a cycle and loses the report | **HIGH** | Deterministic | The audit trail has a hole exactly when a policy decision is taken |
| **R-5** | A case-variant or hard-link path bypasses the manifest guard | **MEDIUM** | Case variant deterministic; hard link / symlink **NOT VERIFIED** | A protected artefact is rewritten without being recognised as protected |
| **R-6** | A concurrent write between the check and the write is overwritten | **MEDIUM** | Requires concurrency; **NOT VERIFIED** under race | Silent loss of a concurrent change |
| **R-7** | The Guardian never notifies anyone | **MEDIUM** | N/A — a capability gap | A critical failure is recorded and unnoticed |

---

## 13. Recommended remediation

**Nothing in this section has been implemented.** It is a proposal for the owner's decision.

### 13.1 Indispensable — required before any reactivation of auto-repair

| # | Action | Closes | Why indispensable |
|---|---|---|---|
| **M-1** | The manifest check must assert over the **expected** rows, not the **found** rows: any entry that cannot be resolved is `FAIL`; an empty parse is `NOT_VERIFIED`. | F-01, F-02 | Without this, the integrity check can be defeated by deleting or corrupting the thing it checks |
| **M-2** | Replace the size heuristic with artefact-identity validation: record the pre-write hash, revalidate it at the moment of the write, compile and parse the result, and require the write to differ from the original **only** by the intended transformation. | F-03, F-06 | A percentage is not integrity |
| **M-3** | Catch `RepairSuspended` at the call site and convert it to a reported `NOT_VERIFIED`; the cycle must always complete and always write its report. | F-04 | A safety mechanism must never destroy the audit trail |
| **M-4** | Make the protection identity-based: resolve the path, compare against the resolved set of manifest-covered files, and check the hash at the write. Close the case-sensitivity gap between `is_protected` and `is_manifest_protected`. | F-05 | The brief requires identity, not string comparison |

### 13.2 Recommended

| # | Action | Closes |
|---|---|---|
| **M-5** | Implement the Telegram policy: notify on a human decision, a block, an integrity divergence, a safety refusal, or a critical failure; never per write or per test; suppress repeats for an unchanged incident. Add a dedupe key. | F-07 |
| **M-6** | Add a per-file lock around the check-and-write sequence, and a lock around `detect.save_state`. | R-6, concurrent cycles |
| **M-7** | Keep a verifiable backup of the original before every write: the bytes and their hash, recorded in the report, with a restore path that verifies the backup before restoring. | §5.3 |
| **M-8** | Write to a temporary file on the same volume, `flush` + `fsync`, validate the temporary, then `os.replace`; clean up the temporary on failure. | §6.2 |
| **M-9** | Add the missing-file check for the 19 protected package files that the `tests-preserved` check does not cover. | F-01 (defence in depth) |
| **M-10** | Adapt the Guardian's own G06 test to enable repair explicitly inside the isolated environment, and add a test that the suspension is honoured in every path. | §10.3 |

### 13.3 Future

| # | Action |
|---|---|
| **M-11** | A per-cycle lock file, so two concurrent Guardian cycles cannot interleave at all. |
| **M-12** | Extend the artefact-identity model beyond the manifest: a signed or hashed baseline for every protected file, with the baseline itself stored outside the project. |
| **M-13** | Run the Guardian in a **read-only mode** by default, with repair available only via an explicit, time-boxed authorisation token. |
| **M-14** | Prove the symlink and hard-link behaviour on a host where the privilege exists; the current audit could not. |

---

## 14. User decisions required

| # | Decision | Why it cannot be decided here |
|---|---|---|
| **D-1** | The `copy.py` divergence: accept the reconstruction as a **known** baseline divergence with the addendum as the record, or restore the original bytes from a source outside this machine? | **The original is not recoverable here.** Accepting the reconstruction is an owner decision; the audit does not accept it. |
| **D-2** | Approve M-1 to M-4 (the indispensable remediations) so that auto-repair can be reactivated with a defensible safety argument. | Each changes the write path or a pass/fail criterion. |
| **D-3** | Confirm that auto-repair remains **suspended** until M-1 to M-4 are implemented and verified. | The audit's recommendation, not its decision. |
| **D-4** | Approve M-5 (the Telegram policy implementation) — the intended behaviour is currently absent. | New capability. |
| **D-5** | Confirm the two hooks remain registered while repair is suspended — they are now **detection-only**, which is the intended safe state, and this is a change in behaviour from the design. | The owner should confirm that detection-only hooks are wanted. |
| **D-6** | Decide whether the Guardian's own suite must return to 30/30 (the one error is a correct consequence of the suspension). | A test-design decision. |

---

## 15. Final verdict

# SAFE FOR DETECTION ONLY

**The detection half is real, verified and operating.** Change detection is content-based and correct; test selection is derived from the package's actual import graph; execution, classification and persistent reporting all work; the hooks are robust against malformed input and cannot break a turn; the N1/N2/N3 policy is imposed in code and enforced correctly; the manifest divergence is detected and reported on every cycle; and the Phase 2A suite still passes 214/214 with the Guardian in place.

**The repair half is not.** One CRITICAL finding — a deleted protected file reported as `PASS` — and two HIGH findings — a corrupted manifest reported as `PASS`, and a same-size invalid replacement accepted by the only sanity gate — each independently defeat the property the Guardian exists to provide. The owner's criterion is explicit: *do not choose `SAFE FOR LIMITED AUTO-REPAIR` if there is any uncontrolled possibility of altering protected or normative files.* That possibility is demonstrated.

**Automatic repair is suspended.** The suspension is surgical, reversible, and implemented at the single write choke point. Detection, testing and reporting continue unchanged. The Hermes configuration was not modified.

**The `copy.py` situation is unchanged and remains visible:** `ORIGINAL SOURCE NOT RECOVERED — RECONSTRUCTED FILE REMAINS A KNOWN BASELINE DIVERGENCE`; `51/52 ORIGINAL HASHES MATCH — 1 KNOWN RECONSTRUCTED FILE`.

**The Guardian is doing its job.** It detected the incident on its next cycle, reported it four times over, and would not let it pass silently. The audit's findings are about the Guardian's *write* half and about a caller that damaged a protected file — not about the Guardian's ability to see damage. That ability is exactly what made this report possible.

**No correction has been applied to the Guardian beyond the suspension.** M-1 to M-14 are proposals awaiting the owner's decision.

---

*End of audit. Read-only throughout, except for the suspension of automatic repair, which was authorised by the brief and performed surgically with a verifiable backup.*
