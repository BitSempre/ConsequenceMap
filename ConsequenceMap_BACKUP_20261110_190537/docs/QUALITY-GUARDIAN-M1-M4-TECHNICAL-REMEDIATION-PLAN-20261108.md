# ConsequenceMap — Quality Guardian: technical remediation plan for M-1 to M-4

**Date:** 2026-11-08
**Nature:** Specification and analysis only. **No code, test, configuration, hook, manifest or baseline was modified.**
**Input:** `docs/QUALITY-GUARDIAN-POST-INCIDENT-SECURITY-AUDIT-20261108.md`
**Classification:** **READY WITH OPEN QUESTIONS**

---

## 1. Executive summary

*Secção 1 — Resumo executivo.*

This document specifies the technical remediation of the four **indispensable** recommendations M-1 to M-4 from the post-incident security audit. It is an analysis and a specification: nothing described here has been implemented, and the automatic repair remains suspended.

The four recommendations do **not** map one-to-one onto F-01 to F-04. The real mapping, read from the audit's §13.1 "Closes" column and confirmed against the audit's own §4 and §5 text, is:

| Recommendation | Closes | Findings |
|---|---|---|
| **M-1** | F-01, F-02 | the manifest check must assert over the **expected** rows |
| **M-2** | F-03, F-06 | replace the size heuristic with artefact-identity validation |
| **M-3** | F-04 | `RepairSuspended` must be a reported state, not an uncaught exception |
| **M-4** | F-05 | the protection must be identity-based, not textual |

**F-07 and F-08 are outside the scope of M-1 to M-4** and are recorded in §10 without being folded into the specification.

Two cross-cutting facts emerged from the inspection and shape the whole plan:

1. **The write surface is a single function.** `repair.write_file_text` is the only function in the Guardian that writes to a project source file. Every repair path reaches it. This is why the suspension works today, and it is why M-2 and M-3 can be implemented at one choke point rather than across the codebase.
2. **The write path is not root-aware.** `write_file_text` calls `config.auto_repair_enabled()` **without a `root` argument**, so it always consults the **production** `PROJECT_ROOT` policy — never the isolated root a test is working in. The consequence is visible today: the G06 test in the isolated environment raises `RepairSuspended` even though the isolated tree has no policy file. This is not a defect of the suspension — it is a defect of the **scope of the check**, and M-2/M-3 must address it or the Guardian's own test suite can never exercise the repair path.

**Dependencies.** M-1 and M-4 are independent of each other. M-2 depends on M-4 (the pre-write hash comparison is the identity check). M-3 is independent of all three but must land **after** M-2, because M-2 changes the write path that M-3 makes safe to interrupt. The recommended order is **M-1 → M-4 → M-2 → M-3**, with the G06 update landing with M-2.

**What is needed to proceed:** authorisation to implement, plus five decisions listed in §11.

---

## 2. Confirmed current state

*Secção 2 — Estado atual confirmado.*

Every statement in this section was verified by inspection or by a non-destructive execution during this task.

### 2.1 The suspension

| Property | Value |
|---|---|
| Policy file | `quality_guardian/state/repair-policy.json` — 462 B, SHA-256 `52f60c0afb16746a54c32a31` |
| `auto_repair` | **`false`** |
| `reason` | *"post-incident security audit 2026-11-08: automatic repair suspended pending owner decision; detection, testing and reporting remain active"* |
| `suspended_at` | `2026-11-08T12:45:00Z` |
| `reversible` | `true` |
| `reactivation_requires` | *"explicit owner authorisation"* |
| Scope | *"automatic N1 repair only; detection, test execution, reporting and baseline recording are unaffected"* |

The suspension is in force and was **not** altered during this task.

### 2.2 The choke point

`quality_guardian/repair.py::write_file_text` — the only function that writes to a project source file:

```python
def write_file_text(path: Path, content: str) -> bool:
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

A full grep of the Guardian's modules finds `RepairSuspended` in exactly **two** places: its definition and its `raise`. **No module catches it.**

| Caller | Behaviour |
|---|---|
| `quality_guardian/hook.py` | caught by the outer `except Exception:` in `main()` — the hook returns 0 and the agent's turn continues |
| `quality_guardian/cli.py` | **not caught** — the CLI has no `except` at all; the exception propagates and the command aborts with a traceback |
| `quality_guardian/guardian.py::_attempt_repairs` | **not caught** — the call to `write_file_text` is unguarded |

### 2.4 The hooks

| Property | Value |
|---|---|
| Registered | `post_tool_call` (matcher `(write_file\|patch\|execute_code\|terminal)`, timeout 120 s) and `pre_verify` (timeout 300 s) |
| Consent | both `✓ allowed` in `shell-hooks-allowlist.json` |
| `config.yaml` SHA-256 | `85b8f48f71257a46819053d8cb74acdd019e1d439363d6c4621d962a519f9ed9` — **unchanged** |
| Allowlist SHA-256 | `0faf6e9c07b1016e6637732c…` — **unchanged** |
| Wrappers | `~/.hermes/agent-hooks/consequencemap-quality-guardian-{post_tool_call,pre_verify}.py` — unchanged |
| Robustness | verified against an incomplete payload, a non-JSON payload and a directory path: all exit 0 with no error |
| `pre_verify` directive | emitted only for `FAIL`, `NOT_VERIFIED`, `BLOCKED` — **never** for `WARNING` |

### 2.5 The Guardian's test suite — **29/30 PASS, 1 ERROR**

| | |
|---|---|
| Classes | 12 (`G01`…`G11` plus `GuardianApiTest`) |
| Test methods | **30** |
| Current result | **29 PASS, 1 ERROR** |
| The error | `G06ReRunTest.test_the_cycle_re_runs_the_tests_after_a_repair` |
| Cause | the suspension is active, so `write_file_text` raises `RepairSuspended`, which `_attempt_repairs` does not catch — **F-04, observed in the test suite** |
| Note | this is the *correct* consequence of the suspension. The test asserts that a repair is applied; the policy forbids it. |

**The failing test is not a defect in the Guardian's logic and must not be removed or weakened.** §6 specifies how it should be rewritten to test the suspension correctly.

### 2.6 Which tests write, and where

Every write in the Guardian's own suite targets `self.root` — a `tempfile.mkdtemp()` directory removed by `addCleanup`. **No test references `config.PROJECT_ROOT`; the suite contains zero references to the production tree.** The grep of every `write_text` / `mkdir` / `unlink` in `test_guardian.py` and `isolated.py` confirms each targets either `self.root` or a path under it.

The one write outside the isolated roots is `G02TriggerTest.test_post_tool_call_ignores_a_write_outside_the_project`, which writes a file into the system temp directory and removes it in `addCleanup`.

**No existing test writes to, repairs, truncates or modifies a protected file.** The suite is safe to run — and it was run during this task.

### 2.7 The Phase 2A suite

**214/214 PASS** (read-only execution, 33.3 s). `test_coverage_gaps` — the module that carries the `copy.py` contract — is **17/17 PASS**.

### 2.8 Manifest and historical integrity

| Artefact | SHA-256 | State |
|---|---|---|
| `docs/PHASE-2A-MANIFEST.md` | `a00984d7928294a0d9d8c91f…` | **byte-identical to the delivered state** |
| `docs/PHASE-2A-MANIFEST-ADDENDUM-A-1.md` | `2f6ebcd289c9…` | intact, 3 001 B |
| `consequence_map/domain/copy.py` | `765037914b353d18d904a657…` | **not touched by this task** |
| **Manifest coverage** | — | **`51/52 ORIGINAL HASHES MATCH — 1 KNOWN RECONSTRUCTED FILE`** |

The single divergence is `consequence_map/domain/copy.py`. It is a **reconstruction from its contract**, not a byte-for-byte recovery. The original manifest hash is deliberately preserved and the addendum records the divergence. **The reconstruction is not accepted as a baseline** and nothing in this document changes that.

### 2.9 The functions M-1 to M-4 would touch

| Function | File | Current signature | Called from |
|---|---|---|---|
| `_check_manifest_integrity` | `guardian.py` | `(root: Path, cycle=None)` | `run_cycle` (twice: the no-change path and the main path) |
| `_documented_divergences` | `guardian.py` | `(root: Path)` | `_check_manifest_integrity` |
| `_check_tests_preserved` | `guardian.py` | `(before: dict, after: dict)` | `run_cycle` |
| `_attempt_repairs` | `guardian.py` | `(cycle: Cycle, root: Path)` | `run_cycle` |
| `apply_level1_fixes_in_project` | `repair.py` | `(path, source, project_rel=None)` | `_attempt_repairs` |
| `repair_is_sane` | `repair.py` | `(original: str, fixed: str)` | `_attempt_repairs` |
| `write_file_text` | `repair.py` | `(path: Path, content: str)` | `_attempt_repairs` (twice: apply and revert) |
| `is_manifest_protected` | `config.py` | `(rel_path: str)` | `apply_level1_fixes_in_project` |
| `is_protected` | `config.py` | `(path)` | `repair.classify_failure` |
| `auto_repair_enabled` | `config.py` | `(root: Path = None)` | `write_file_text` (**no root**), `_attempt_repairs` (with root) |

---

## 3. The exact text and mapping of M-1 to M-4

*Secção 3 — Texto e mapeamento exatos de M-1 a M-4.*

### 3.1 The audit's §13.1, verbatim

| # | Action | Closes | Why indispensable |
|---|---|---|---|
| **M-1** | The manifest check must assert over the **expected** rows, not the **found** rows: any entry that cannot be resolved is `FAIL`; an empty parse is `NOT_VERIFIED`. | F-01, F-02 | Without this, the integrity check can be defeated by deleting or corrupting the thing it checks |
| **M-2** | Replace the size heuristic with artefact-identity validation: record the pre-write hash, revalidate it at the moment of the write, compile and parse the result, and require the write to differ from the original **only** by the intended transformation. | F-03, F-06 | A percentage is not integrity |
| **M-3** | Catch `RepairSuspended` at the call site and convert it to a reported `NOT_VERIFIED`; the cycle must always complete and always write its report. | F-04 | A safety mechanism must never destroy the audit trail |
| **M-4** | Make the protection identity-based: resolve the path, compare against the resolved set of manifest-covered files, and check the hash at the write. Close the case-sensitivity gap between `is_protected` and `is_manifest_protected`. | F-05 | The brief requires identity, not string comparison |

### 3.2 The real mapping — and the assumption this task was warned about

The task brief warned: *"Não assumas que correspondem automaticamente a F-01, F-02, F-03 e F-04."* The warning is correct. The actual mapping is:

| Recommendation | Closes | Does **not** close | Note |
|---|---|---|---|
| **M-1** | **F-01, F-02** | F-03, F-04, F-05 | M-1 is about the **check**, not the write |
| **M-2** | **F-03, F-06** | F-01, F-02, F-04, F-05 | M-2 absorbs **F-06 (TOCTOU)** — the pre-write hash revalidation is part of it |
| **M-3** | **F-04** | F-01, F-02, F-03, F-05, F-06 | M-3 is about the **control flow** of the refusal |
| **M-4** | **F-05** | F-01, F-02, F-03, F-04, F-06 | M-4 also requires "check the hash at the write" — which overlaps M-2's "revalidate it at the moment of the write" |

**Two consequences of the real mapping:**

- **M-1 does not touch the write path.** It changes a verdict. The CRITICAL finding F-01 is a *reporting* defect, not a *writing* defect.
- **M-2 and M-4 overlap on the hash check at the write.** M-2 says "revalidate it at the moment of the write"; M-4 says "check the hash at the write". These are the same mechanism, serving two purposes: M-2's is a TOCTOU guard, M-4's is an identity guard. **They must be implemented as one function, not two**, or the write path will hash the file twice and the two guards can disagree.

### 3.3 Scope discipline

| In scope (M-1 to M-4) | Out of scope |
|---|---|
| The manifest check's verdict logic | **F-07** — the Telegram policy (audit M-5, §13.2) |
| The write path's validation | **F-08** — `module_for_path` accepting only absolute paths (audit, §4.5) |
| The protection's basis | **M-6** — locking (audit §13.2) |
| The suspension's control flow | **M-7** — verifiable backup (audit §13.2) |
| | **M-8** — `fsync` and temporary validation (audit §13.2) |
| | **M-9** — the extra absence check for the 19 package files (audit §13.2) |
| | **M-10** — the G06 adaptation (audit §13.2) — **but see §6**, where the G06 update is required *as a consequence* of M-2 and M-3 and is therefore specified here |
| | **M-11 to M-14** — future |

**On M-10.** The audit places the G06 adaptation in the "Recommended" tier. But the current G06 test **fails because of F-04**, and M-2 and M-3 change exactly the code path it exercises. Leaving it untouched would mean shipping M-2 and M-3 with a failing suite. The G06 update is therefore specified in §6 as a **necessary consequence of M-2/M-3**, not as an independent recommendation. It must not be executed before M-3, or the test would assert a behaviour that M-3 has not yet introduced.

---

## 4. Technical analysis per recommendation

*Secção 4 — Análise técnica por recomendação.*

### 4.1 M-1 — assert over the expected rows

**Finding addressed.** F-01 (CRITICAL, a missing protected file produces `PASS`) and F-02 (HIGH, a malformed manifest produces `PASS`).

**Exact recommendation.** *"The manifest check must assert over the **expected** rows, not the **found** rows: any entry that cannot be resolved is `FAIL`; an empty parse is `NOT_VERIFIED`."*

**Module, file, function.** `quality_guardian/guardian.py::_check_manifest_integrity` — the only function affected.

**Current behaviour, confirmed by inspection.** The function parses the manifest with a regex into `rows`, then loops over `rows` — that is, over the rows it **found**. A row that resolves to no file increments `missing` and `continue`s. The `missing` counter appears **only** in the `PASS` branch's `evidence` dict:

```python
for rel, _size, expected in rows:
    candidate = root / rel.replace("/", os.sep)
    if not candidate.exists():
        candidate = desktop / rel.replace("/", os.sep)
    if not candidate.exists():
        missing += 1
        continue
    ...
if mismatched:
    ...
return CheckResult(
    name="phase-2a-manifest-integrity", verdict=classify.PASS,
    detail=f"{checked} manifest entries verified, 0 mismatched",
    evidence={"checked": checked, "absent_from_disk": missing},
)
```

Two distinct failure paths follow:

- **F-01 (missing file).** `missing` is counted but never consulted. A deleted protected artefact yields `checked = 51`, `mismatched = []`, `missing = 1` → `PASS`.
- **F-02 (malformed manifest).** The regex matches nothing, so `rows = []`, the loop never runs, `checked = 0`, `missing = 0`, `mismatched = []` → `PASS` with *"0 manifest entries verified, 0 mismatched"*.

**Intended behaviour.** The check must distinguish six states, as the brief requires:

| State | Meaning | Required verdict |
|---|---|---|
| **Expected** | a row parsed from the manifest | — |
| **Found** | the row resolved to a readable file | — |
| **Missing** | the row resolved to nothing | `FAIL` |
| **Additional** | a file in the tree that the manifest does not list | **not specified by M-1** — see §4.1.4 |
| **Divergent** | the row resolved and the hash differs | `FAIL` (or `WARNING` when documented in an addendum — the current behaviour, preserved) |
| **Manifest invalid** | the manifest exists but yields no parseable rows | `NOT_VERIFIED` |

**Minimal technical change.** One function, no signature change, no new dependency:

1. Keep the existing regex, but capture the parse result distinctly: `rows` empty **while the manifest exists and is non-empty** → `NOT_VERIFIED` (*"the manifest yielded no parseable entries"*). This distinguishes F-02 from the legitimate case of an empty manifest, which should also be `NOT_VERIFIED`.
2. Add a second regex for **structurally incomplete rows** — a table line that has a path and a size but no 64-hex hash, or a hash that is not 64 hex characters — and report them as a distinct `invalid_entries` count. A malformed row must not be silently skipped by the strict regex. *Note: the strict regex currently requires the exact shape, so an incomplete row is invisible; this is the same class of defect as F-02 and is within M-1's "expected rows" wording.*
3. Resolve each expected row against the two search roots (project, then Desktop). If neither resolves → `missing += 1` and record the path.
4. Change the final verdict: `missing > 0` → `FAIL` with the missing paths in `evidence`; `invalid_entries > 0` → `FAIL`; `rows` empty → `NOT_VERIFIED`; otherwise the existing `PASS`/`WARNING`/`FAIL` logic, unchanged.
5. The `evidence` dict gains `expected`, `found`, `missing`, `invalid_entries`, `additional`, `divergent` — so the report states exactly what was checked, not only that nothing disagreed.

**Compatibility with the current design.** High. `CheckResult` already carries an arbitrary `evidence` dict. The `classify` module already defines `NOT_VERIFIED`. The caller passes `cycle` for the `rewritten_paths` exemption and that exemption is preserved untouched — a file the Guardian rewrote this cycle is still excluded from the divergence list, and it must also be excluded from the missing list.

**Additional files.** The brief asks the specification to distinguish "ficheiros adicionais". M-1's text is about *expected* rows and does not mention additional files. **Adding an additional-file check would widen M-1's scope.** The specification therefore **records** additional files as an observation in the `evidence` dict only — a count and a sample — and **does not** make them affect the verdict. A decision on whether an unlisted file is a defect belongs to the owner (§11, D-4).

**Risks introduced.** A false `FAIL` if the Desktop search root is unavailable — the current code falls back to `C:\Users\Utente\Desktop` unconditionally, and a machine without that layout would report 13 missing files. The specification requires the search roots to be **explicit and reported**: when a root does not exist, the entry is `BLOCKED` (*"the search root is unavailable"*) rather than `FAIL` (*"the file is missing"*), because those are different facts. This distinction also protects the 13 Desktop-resident entries from a false `FAIL` on another host.

**Tests.** §5 rows T-01 to T-08.

**Objective acceptance criteria.**

| ID | Criterion |
|---|---|
| AC-M1-1 | With one expected file absent and every other file matching, the check's verdict is `FAIL` and `evidence.missing` contains that path. |
| AC-M1-2 | With a manifest that exists, is non-empty and yields no parseable row, the verdict is `NOT_VERIFIED` — never `PASS`, never `FAIL`. |
| AC-M1-3 | With every expected file present and matching, the verdict is `PASS` and `evidence.found == evidence.expected`. |
| AC-M1-4 | With an unlisted file present in the tree, the verdict is unchanged from AC-M1-3, and `evidence.additional` records it. |
| AC-M1-5 | With a structurally incomplete row (missing or malformed hash), the verdict is `FAIL` and `evidence.invalid_entries` records it. |
| AC-M1-6 | With a documented divergence (the addendum case), the verdict remains `WARNING` — the existing behaviour is preserved. |
| AC-M1-7 | With a search root unavailable, the affected entries are `BLOCKED`, not `FAIL`. |
| AC-M1-8 | The existing P03 and P08 scenarios still produce `FAIL`; P06 still produces `NOT_VERIFIED`. |
| AC-M1-9 | The real Phase 2A manifest, with the known `copy.py` divergence, still yields `WARNING` — **not** `FAIL`. |

**Rollback.** Revert the single function. No data migration, no state change. The `evidence` dict's extra keys are additive and ignored by any older reader.

---

### 4.2 M-2 — artefact-identity validation on the write path

**Finding addressed.** F-03 (HIGH, the 50 % size rule accepts invalid content) and F-06 (MEDIUM, a TOCTOU window between verification and write).

**Exact recommendation.** *"Replace the size heuristic with artefact-identity validation: record the pre-write hash, revalidate it at the moment of the write, compile and parse the result, and require the write to differ from the original **only** by the intended transformation."*

**Module, file, function.** `quality_guardian/repair.py::write_file_text` (the choke point), plus `repair.py::repair_is_sane` and `guardian.py::_attempt_repairs` for the call site.

**Current behaviour, confirmed by inspection.**

```python
def repair_is_sane(original: str, fixed: str) -> bool:
    if len(original) == 0:
        return True
    return len(fixed) >= int(len(original) * config.MIN_REPAIR_SIZE_RATIO)
```

It compares **lengths only**. It never compiles the result, never parses it, and never checks that the difference is the transformation that was claimed. `write_file_text` performs no validation of the content it is handed. The pre-write hash is recorded in `_attempt_repairs` (`proposal.before_hash`) but is **never revalidated at the moment of the write**.

Two concrete escapes, both verified in the audit:

- `repair_is_sane("A"*1000, "B"*1000)` → `True`, while `"B"*1000` is a `SyntaxError`.
- A file whose *meaning* changes while its length and syntax stay valid — a single changed constant — passes every size and syntax check.

**Intended behaviour.** Four validations, in this order, at the single write choke point:

| # | Validation | Purpose |
|---|---|---|
| **V1** | **Pre-write hash revalidation.** The hash recorded when the content was read is compared against the file's hash *at the moment of the write*. A mismatch means the file changed between the decision and the write → refuse. | closes F-06 |
| **V2** | **Syntactic validation.** For `.py`, the candidate content must compile (`compile(content, path, "exec")`). | closes the same-size invalid-content escape |
| **V3** | **Transformation-fidelity validation.** The candidate must equal the original **after re-deriving the intended transformation from the original**. The Guardian's N1 scope is exactly two transformations — trailing-whitespace removal and final-newline normalisation — so the candidate is re-derived by applying `apply_level1_fixes` to the *original* and compared byte-for-byte. | closes the semantic escape: a changed constant cannot survive, because re-deriving from the original produces the original's own constants |
| **V4** | **Structural validation.** For `.py`, the candidate must parse (`ast.parse`). | catches constructs that compile but are structurally wrong |

V1 requires the hash to travel with the write. The minimal change is to give `write_file_text` an optional `expected_hash` parameter; when supplied, the file's current hash is compared before the temporary is written. When it is not supplied — the current call sites — the write is refused, because an unverified write is exactly what M-2 exists to prevent. **This is a deliberate tightening: the write path becomes fail-closed by default.**

**Intended behaviour of the size rule.** It is **not** deleted — it becomes one predicate among several rather than the only one. The audit's finding was that a percentage "cannot be considered an integrity guarantee"; the remedy is to stop treating it as one. A file that shrinks by 60 % still fails V1–V4 regardless of the ratio, so the ratio's operational value is low; but removing it outright would change behaviour for a case (a legitimately truncated file) that the current rule refuses and that no other rule covers. **The specification keeps `MIN_REPAIR_SIZE_RATIO` as a secondary guard** and states explicitly that it is **not** an integrity guarantee.

**The root-scope defect.** `write_file_text` calls `config.auto_repair_enabled()` with **no root**, so it consults the production policy even when the caller is working in an isolated tree. M-2 must make the write path root-aware: `write_file_text(path, content, *, expected_hash=None, root=None)`, consulting `config.auto_repair_enabled(root)`. Without this, the Guardian's own suite can never exercise the repair path, and the G06 update in §6 would be untestable.

**Minimal technical change.**

1. `repair.py`: add a `validate_repair(original, fixed, path, expected_hash)` function returning `(ok, reason)`, implementing V1–V4 in order.
2. `repair.py`: extend `write_file_text` with `expected_hash` and `root`; call `validate_repair` before the temporary is written; refuse with a `False` return (not an exception — see M-3) when validation fails.
3. `repair.py`: make `auto_repair_enabled` root-aware at the call site.
4. `guardian.py::_attempt_repairs`: pass `proposal.before_hash` and `root` at both call sites — the apply and the **revert**.
5. `config.py`: keep `MIN_REPAIR_SIZE_RATIO`; add the compile/parse helpers' configuration only if needed.

**Compatibility with the current design.** High. `write_file_text` already returns `bool`; the caller already handles `False` (`if not repair.write_file_text(path, fixed): proposal.error = …; continue`). The **revert** path already calls `write_file_text(path, original)` — under M-2 that call would need an `expected_hash` too, or it would be refused. This is a real subtlety: **a revert must be exempt from the transformation-fidelity check** (V3), because the revert's content is the *original*, not a transformation of it. V1, V2 and V4 still apply to a revert.

**Risks introduced.**

- **False refusals.** A file that is not valid Python but is a valid project artefact would fail V2/V4. The Guardian's N1 scope is `.py` only (`_find_formatting_issues` filters on `rel.endswith(".py")`), so the blast radius is limited to Python files — but the check must skip non-Python files rather than assume.
- **A file that was already invalid before the repair.** If the original does not compile, V2 on the *fixed* content will also fail — correctly, since the repair cannot fix a pre-existing syntax error. The refusal reason must distinguish "the repair produced invalid content" from "the original was already invalid", so the operator is not sent chasing the wrong thing. The specification requires the reason to name which.
- **Performance.** `compile()` on every write is cheap for project-sized files. Acceptable.

**Tests.** §5 rows T-09 to T-14.

**Objective acceptance criteria.**

| ID | Criterion |
|---|---|
| AC-M2-1 | A candidate with invalid Python of the same length is refused, with a reason naming the syntax failure. |
| AC-M2-2 | A candidate that is valid Python but differs semantically from the original (a changed constant) is refused by V3 — re-deriving the transformation from the original does not reproduce it. |
| AC-M2-3 | A legitimate N1 repair (trailing whitespace, final newline) is applied and recorded as before. |
| AC-M2-4 | When the file's hash at the moment of the write differs from the recorded pre-write hash, the write is refused and the file is left byte-identical to its state at the moment of the write. |
| AC-M2-5 | A write with no `expected_hash` supplied is refused. |
| AC-M2-6 | The revert path restores the original content and is not refused by V3. |
| AC-M2-7 | `repair_is_sane` is no longer the only guard: a same-size invalid candidate is refused even though it passes `repair_is_sane`. |
| AC-M2-8 | A non-Python file is not subject to V2/V4. |

**Rollback.** Revert `repair.py` and the two call sites in `guardian.py`. The write path returns to its current shape. The suspension remains in force either way, so a rollback does not expose the old behaviour.

---

### 4.3 M-3 — the suspension must be a reported state

**Finding addressed.** F-04 (HIGH, `RepairSuspended` propagates as an uncaught exception).

**Exact recommendation.** *"Catch `RepairSuspended` at the call site and convert it to a reported `NOT_VERIFIED`; the cycle must always complete and always write its report."*

**Module, file, function.** `quality_guardian/guardian.py::_attempt_repairs` (the call site) and `quality_guardian/repair.py::write_file_text` (the raise). `quality_guardian/cli.py` needs no change if the cycle no longer raises.

**Current behaviour, confirmed by inspection.** `RepairSuspended` is raised in `repair.py` and caught in **no** module. The `hook.py` outer `except Exception:` is what keeps the hooks alive; `cli.py` has no `except` at all. The G06 test fails with the exception propagating out of `run_cycle`.

**Intended behaviour.** The suspension is a **controlled state**, not an error. Six properties, from the brief:

| # | Property | Required mechanism |
|---|---|---|
| 1 | The repair stays blocked | the choke point still refuses the write |
| 2 | Detection keeps working | the cycle continues past the refusal |
| 3 | Tests keep running | the cycle continues to the test-execution and reporting phases |
| 4 | The final report is produced | `guardian.finalize` is always reached |
| 5 | The hooks never fail or interrupt the turn | no exception escapes `run_cycle` |
| 6 | The result identifies the state clearly | a check named `repair-capability` with an explicit `REPAIR_SUSPENDED` state |

**Minimal technical change.**

1. **`repair.py`:** keep `RepairSuspended` as the signal, but make `write_file_text` **not** raise it. Two options:
   - **(a) return `False`** and record the reason. Minimal, but `False` is already the signal for "the file could not be written", so the reason would be lost.
   - **(b) return a structured result** — a small dataclass or a `(ok, reason)` tuple.
   **The specification recommends (b)**: a distinct return shape preserves the reason, which is exactly what property 6 requires. The current `bool` return conflates three different outcomes — refused by policy, refused by validation, and failed to write — and the audit's F-04 exists because that conflation had nowhere to go but an exception.
2. **`guardian.py::_attempt_repairs`:** accept the structured result; on a policy refusal, record `proposal.error = "REPAIR_SUSPENDED: <reason>"` and add a check:
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
   The existing suspension check (added during the security audit) already uses this shape; M-3 unifies it with the exception path so there is **one** code path, not two.
3. **`guardian.py::run_cycle`:** the cycle must reach `detect.save_state` and the report regardless. Under the current code the exception prevents both. With the refusal converted to a check result, the existing flow is restored.
4. **`cli.py`:** no functional change required, but a top-level `except Exception` in `main()` that prints a diagnostic and returns a non-zero exit code is **recommended** as defence in depth, so that no future exception can abort a CLI run without a report. This is within M-3's intent (*"the cycle must always complete and always write its report"*) and is a two-line change.

**Compatibility with the current design.** High. `classify.NOT_VERIFIED` exists; `CheckResult.evidence` is free-form; the `_attempt_repairs` function already has a suspension branch to unify with. The only signature change is `write_file_text`'s return type — the two call sites are both in `_attempt_repairs`, and the audit's §4.1 confirms there is exactly one other writer.

**Risks introduced.**

- **A swallowed exception hides a real fault.** If the structured result is not produced correctly, a genuine write failure could be reported as a policy refusal. Mitigation: the reason strings are distinct and machine-checkable (`REPAIR_SUSPENDED:` vs `WRITE_FAILED:` vs `VALIDATION_REFUSED:`), and the specification requires the report to carry the reason verbatim.
- **The `pre_verify` nudge behaviour changes.** A `NOT_VERIFIED` verdict **does** currently produce `{"action": "continue"}`. Under the suspension, every cycle would therefore nudge the agent to keep working — for a condition that will not resolve on its own. **This is a real behavioural risk that M-3 must address.** The specification requires the `repair-capability` check to be **excluded from the `pre_verify` nudge decision** when its state is `REPAIR_SUSPENDED`, so a deliberately suspended Guardian does not trap the agent in a nudge loop. The `pre_verify` decision must remain driven by the *substantive* verdict, with the suspension reported as context rather than as a failure to fix.

**Tests.** §5 rows T-15 to T-19.

**Objective acceptance criteria.**

| ID | Criterion |
|---|---|
| AC-M3-1 | With the policy suspended and a repair proposed, the cycle completes, the report is written, and no file is modified. |
| AC-M3-2 | The report contains a `repair-capability` check whose `detail` contains `REPAIR_SUSPENDED`. |
| AC-M3-3 | `cli.verify` under suspension exits without a traceback and writes a report. |
| AC-M3-4 | `post_tool_call` and `pre_verify` both exit 0 with the suspension active. |
| AC-M3-5 | `pre_verify` under suspension emits **no** `continue` directive. |
| AC-M3-6 | The target file is byte-identical before and after the cycle. |
| AC-M3-7 | With the policy enabled, a repair is applied exactly as before — no behaviour regression. |

**Rollback.** Revert the return-shape change and the call site. The suspension file remains and continues to block writes through the pre-existing raise. Note that a rollback re-introduces F-04; the suspension must therefore stay in force either way.

---

### 4.4 M-4 — identity-based protection

**Finding addressed.** F-05 (MEDIUM, the protection is textual, not identity-based).

**Exact recommendation.** *"Make the protection identity-based: resolve the path, compare against the resolved set of manifest-covered files, and check the hash at the write. Close the case-sensitivity gap between `is_protected` and `is_manifest_protected`."*

**Module, file, function.** `quality_guardian/config.py::is_manifest_protected` (the textual comparison), `quality_guardian/config.py::is_protected` (the resolving comparison), and the write path (the hash check, shared with M-2).

**Current behaviour, confirmed by inspection.**

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

A plain string prefix comparison. `is_protected` — the *other* function — resolves the path first and is therefore case-insensitive in effect and traversal-safe. **The two protections disagree about the same file:** `ConsequenceMap/domain/copy.py` → `is_manifest_protected` `False`, `is_protected` `True`.

**Intended behaviour.** Three changes, in increasing strength:

| # | Change | Purpose |
|---|---|---|
| **I1** | Resolve the path before comparing. `is_manifest_protected` must resolve its input against `PROJECT_ROOT` and compare the **resolved** relative path against the protected set. | closes the case-sensitivity and traversal gaps |
| **I2** | Build the protected set from the **manifest itself** rather than from hard-coded prefixes: parse the manifest's rows and resolve each to an absolute path. The prefixes remain as a fallback for files not listed in the manifest. | the manifest is the authority on what is protected; a hard-coded prefix list can drift from it |
| **I3** | Check the **hash** at the write: a file whose current hash equals the manifest's recorded hash is protected regardless of how its path was reached. | the identity anchor the brief asks for — "based on the identity and integrity of the artefact, not only on a textual comparison of the path" |

I3 is the same mechanism as M-2's V1 and **must be implemented once**. The specification requires a single function, `manifest_protection_for(path, root)`, returning a protection record — `{protected: bool, reason: str, expected_hash: str | None, resolved: Path | None}` — used by both the pre-repair decision and the write-time validation.

**Compatibility with the current design.** Moderate — this is the most invasive of the four. `is_manifest_protected(rel_path)` is called from exactly one place (`apply_level1_fixes_in_project`), and `is_protected(path)` from one place (`classify_failure`). Both signatures can be preserved as thin wrappers over the new resolution, so no caller changes.

**Risks introduced.**

- **The manifest must be readable at protection time.** If the manifest is absent or malformed, the protection set cannot be built from it. The fallback is the hard-coded prefixes — which must then be **more** protective, not less. The specification requires: when the manifest is unavailable, the prefix set is used **and** the reason recorded as *"fallback: manifest unavailable"*.
- **Resolution can fail.** A path that does not exist cannot be resolved in the usual way; `Path.resolve()` on a non-existent path still yields an absolute path on Windows (strict=False by default). The specification requires the resolution to be non-strict and to handle `OSError`.
- **Symlink and hard-link behaviour is NOT VERIFIED** in this environment — `os.symlink` raised `OSError`. I2 and I3 mitigate this: a symlinked path resolves to its target, and the target's hash anchors the protection. The audit's M-14 keeps the definitive proof as future work.

**Tests.** §5 rows T-20 to T-23.

**Objective acceptance criteria.**

| ID | Criterion |
|---|---|
| AC-M4-1 | `is_manifest_protected("ConsequenceMap/domain/copy.py")` returns `True` — the case-sensitivity gap is closed. |
| AC-M4-2 | A path reaching a manifest-covered file through `..` segments is protected. |
| AC-M4-3 | A file listed in the manifest is protected even if its path does not start with any hard-coded prefix. |
| AC-M4-4 | A file whose current hash equals the manifest's recorded hash is protected at the write, regardless of path form. |
| AC-M4-5 | With the manifest absent, the hard-coded prefixes still protect the files they name, and the reason records the fallback. |
| AC-M4-6 | A file that is neither manifest-listed nor prefix-covered remains unprotected, so ordinary repairs are not blocked. |
| AC-M4-7 | The existing P01, P02, P09 and P10 scenarios still block. |

**Rollback.** Revert `config.py` and the shared write-time hash check. The hard-coded prefix list is retained in the current code as the fallback, so a rollback restores today's behaviour exactly.

---

## 5. Adversarial test matrix

*Secção 5 — Matriz de testes adversariais.*

Every test uses a **temporary copy** or an artificial fixture. No real protected file is ever a target of a destructive test.

| ID | Scenario | Isolated preparation | Simulated action | Expected result | Evidence to record | Side-effect risk |
|---|---|---|---|---|---|---|
| **T-01** | Protected file missing | temp project with a 1-row manifest; delete the file | run the manifest check | `FAIL`; `evidence.missing` names the path | the check result's `evidence` dict | none — the temp tree only |
| **T-02** | Protected file altered | temp project; change the file's content | run the check | `FAIL` (undocumented) or `WARNING` (documented in an addendum) | verdict + `evidence.undocumented` | none |
| **T-03** | Empty manifest | temp project; write a manifest with a header and no rows | run the check | `NOT_VERIFIED` | verdict + `detail` | none |
| **T-04** | Malformed manifest | temp project; write text that is not a manifest | run the check | `NOT_VERIFIED` | verdict + `detail` | none |
| **T-05** | Duplicate entry | temp project; the same path listed twice, both hashes identical | run the check | `PASS`; `evidence.expected == evidence.found`; the duplicate is reported, not double-counted | `evidence` dict | none |
| **T-06** | Invalid path in a row | temp project; a row with `../escape.py` and one with an absolute path | run the check | the escaping row is rejected as invalid; the verdict is `FAIL` with `evidence.invalid_entries` | `evidence.invalid_entries` | **must not write outside the temp tree** — the check is read-only by construction, but the test must assert no file was created outside |
| **T-07** | Invalid hash in a row | temp project; a row with a 63-character hash and one with non-hex characters | run the check | `FAIL`; `evidence.invalid_entries` names both | `evidence.invalid_entries` | none |
| **T-08** | Search root unavailable | temp project; a manifest row pointing at a path outside both roots | run the check | `BLOCKED` (*"the search root is unavailable"*), not `FAIL` | verdict + `detail` | none |
| **T-09** | Invalid content, similar size | temp file; candidate content is invalid Python of the same length | attempt the write | refused by V2/V4; the file is byte-identical afterwards | the refusal reason naming the syntax failure | none — the refusal precedes any write |
| **T-10** | Truncated content | temp file; candidate is 10 % of the original | attempt the write | refused by the size guard **and** by V3 | the refusal reason | none |
| **T-11** | Semantically different, same length and valid syntax | temp file; candidate changes a constant | attempt the write | refused by V3 — re-deriving the transformation from the original does not reproduce it | the refusal reason | none |
| **T-12** | File changed between read and write | temp file; read it, then modify it externally, then attempt the write with the original's hash | attempt the write | refused by V1; the externally-modified file is left untouched | the refusal reason + both hashes | none — the write is refused |
| **T-13** | Repair attempted during suspension | temp project with an artificial repairable file; the policy file in the **temp** tree sets `auto_repair: false` | run a cycle | `REPAIR_SUSPENDED`; the file is unchanged; the report is written | the `repair-capability` check + the report path | none — this test requires the root-aware policy resolution of M-2 |
| **T-14** | Error during the repair | temp file; make the write fail (e.g. a read-only directory) | attempt the write | the failure is recorded, the cycle continues, the report is written | the refusal reason + the cycle's verdict | none — the failure is on the temp tree |
| **T-15** | Error during report production | temp project; make the reports directory unwritable | run a cycle | the cycle's checks are unaffected; the report failure is reported on stderr and the exit code is non-zero; the **project** is untouched | the stderr diagnostic | the Guardian's own reports only |
| **T-16** | `post_tool_call` execution | temp project; a synthetic payload naming a file in the temp tree | run the hook entry point | exit 0; a report is written; no protected file modified | the hook's stdout/stderr + the report | none |
| **T-17** | `pre_verify` execution | temp project; a synthetic payload with `changed_paths` | run the hook entry point | exit 0; a report is written | the hook's stdout/stderr + the report | none |
| **T-18** | `pre_verify` under suspension | temp project; the policy suspends repair | run the hook entry point | exit 0; **no** `continue` directive | the hook's stdout | none |
| **T-19** | `post_tool_call` with an incomplete payload | no preparation | run the hook with a payload lacking `tool_input` | exit 0; no error | the hook's stderr | none |
| **T-20** | Alternate path to a protected file | temp project; a manifest-covered file reached through `..` | attempt a write | refused | the refusal reason | none |
| **T-21** | Case-variant path | temp project; `ConsequenceMap/domain/copy.py` | attempt a write | refused — the case gap is closed | the refusal reason | none |
| **T-22** | Unlisted file | temp project; a file not in the manifest and not prefix-covered | attempt an ordinary N1 repair | **permitted** — the protection is not over-broad | the applied repair | none |
| **T-23** | Hash-matched, path-unusual | temp project; a file with a path outside the prefixes whose hash matches a manifest row | attempt a write | refused by the identity check | the refusal reason | none |

**Coverage of the brief's required list.** Every scenario the brief names is present: missing protected file (T-01), altered protected file (T-02), empty manifest (T-03), malformed manifest (T-04), duplicate entry (T-05), invalid path (T-06), invalid hash (T-07), invalid content of similar size (T-09), truncated content (T-10), repair during suspension (T-13), error during the repair (T-14), error during report production (T-15), `post_tool_call` execution (T-16), `pre_verify` execution (T-17).

**T-13 depends on the root-aware policy resolution** specified in §4.2. Without it, the test would consult the production policy and could not express a per-test suspension — the exact limitation that makes the current G06 fail.

---

## 6. The G06 update

*Secção 6 — Proposta de atualização G06.*

### 6.1 The current definition

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

The first test asserts that a repair **is applied**. Under the suspension it fails, because `write_file_text` raises `RepairSuspended` and nothing catches it.

### 6.2 Why the test must change rather than the assertion

The test's *intent* — "the tests are re-run after the repair" — is sound and must be preserved. What has changed is the **environment** the test runs in: the policy now suspends repair globally, and the write path does not consult the test's isolated root.

**The correct fix is environmental, not a weakened assertion:**

1. **Root-aware policy resolution (M-2).** `write_file_text` consults `config.auto_repair_enabled(root)`. The isolated tree then has its own policy — and by default, **no policy file**, which means the default (`auto_repair: true`) applies to the isolated tree.
2. **An explicit, per-test policy.** The test writes a `repair-policy.json` into its own `self.root` enabling repair, so the intent is expressed in the fixture rather than inherited from the machine's global state.
3. **A separate suspension test.** A new test writes a policy with `auto_repair: false` into its own root and asserts the suspension behaviour.

This makes the suite **independent of the host's global suspension state** — which is a genuine improvement in test hygiene, not a relaxation.

### 6.3 The proposed G06

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

- `test_the_suspension_blocks_the_repair_and_the_cycle_still_completes` — writes a suspending policy into `self.root`; asserts (i) the repair was **not** applied, (ii) the target file is byte-identical, (iii) the cycle produced a `repair-capability` check whose `detail` contains `REPAIR_SUSPENDED`, (iv) `cycle.result.worst` is not `PASS`, (v) the cycle's test runs were still executed.
- `test_the_report_is_produced_under_suspension` — asserts `guardian.finalize(cycle, self.root)` writes a report and that the report's payload contains the `REPAIR_SUSPENDED` marker.

### 6.4 The six properties the brief requires

| # | Required property | How G06 (updated) covers it |
|---|---|---|
| 1 | The suspension blocks any repair | the new suspension test asserts no proposal was applied and the file is byte-identical |
| 2 | Detection remains operational | the same test asserts `cycle.changed_files` is non-empty |
| 3 | The report is produced | the new report test asserts the report exists and carries the marker |
| 4 | The hooks propagate no uncaught exceptions | covered by the hook tests (T-16…T-18) and by the CLI not raising |
| 5 | The suspension state is explicit | the `REPAIR_SUSPENDED` marker is asserted in both the check and the report |
| 6 | No test is weakened to obtain a pass | the two original methods keep every original assertion; the count grows from 30 to **32** |

### 6.5 The future acceptance target

**30/30 is no longer the correct target.** The inspection shows the suite currently holds **30** test methods across **12** classes. After the G06 update it holds **32**. The honest target is therefore:

> **`32/32 PASS`**, with the Guardian's own suite exercising both the repair-enabled path (in an isolated tree with an explicit enabling policy) and the repair-suspended path.

The number 32 is derived from the current suite's structure plus the two additions specified above. If the implementation of M-1 to M-4 adds further tests — which the specification's own matrix implies, T-01…T-23 are not all currently implemented — the count will be higher. **The target is "every test passes, with no test removed or weakened", and the count is whatever the implementation produces.** The specific number 32 is stated for planning only.

---

## 7. Acceptance criteria for the whole remediation

*Secção 7 — Critérios de aceitação.*

The remediation is complete when **all** of the following hold:

| ID | Criterion | Verified by |
|---|---|---|
| **AC-1** | A missing protected file never yields a `PASS` verdict | T-01, AC-M1-1 |
| **AC-2** | A manifest that yields no parseable entry never yields a `PASS` verdict | T-03, T-04, AC-M1-2 |
| **AC-3** | An invalid or duplicate manifest row is detected and reported | T-05, T-06, T-07, AC-M1-5 |
| **AC-4** | An unavailable search root is distinguished from a missing file | T-08, AC-M1-7 |
| **AC-5** | The known `copy.py` divergence still yields `WARNING`, not `FAIL` | AC-M1-9 |
| **AC-6** | A same-size invalid candidate is refused before any write | T-09, AC-M2-1 |
| **AC-7** | A semantically different but valid candidate is refused | T-11, AC-M2-2 |
| **AC-8** | A file changed between read and write is not overwritten | T-12, AC-M2-4 |
| **AC-9** | A write without a pre-write hash is refused | AC-M2-5 |
| **AC-10** | The revert path restores the original and is not refused by the fidelity check | AC-M2-6 |
| **AC-11** | The suspension is a reported state, never an uncaught exception | T-13, T-15, AC-M3-1, AC-M3-3 |
| **AC-12** | Every cycle writes its report, under every condition | T-14, T-15, AC-M3-1 |
| **AC-13** | `post_tool_call` and `pre_verify` exit 0 under the suspension | T-16, T-17, T-18, AC-M3-4 |
| **AC-14** | `pre_verify` emits no `continue` under the suspension | T-18, AC-M3-5 |
| **AC-15** | The protection is identity-based: case, traversal and hash-anchored | T-20, T-21, T-23, AC-M4-1…AC-M4-4 |
| **AC-16** | Ordinary, unprotected files remain repairable | T-22, AC-M4-6 |
| **AC-17** | The Phase 2A suite remains 214/214 | the Phase 2A suite run |
| **AC-18** | The Guardian's own suite passes in full, with no test removed or weakened | the Guardian suite run |
| **AC-19** | The Phase 2A manifest, the addendum A-1 and `copy.py` are byte-identical to their current state | hash comparison |
| **AC-20** | The configuration and the allowlist are unchanged by the remediation | hash comparison |
| **AC-21** | The write path still has exactly one entry point for project source files | inspection |
| **AC-22** | The suspension is still in force until the owner lifts it | the policy file's content |

---

## 8. Implementation sequence

*Secção 8 — Sequência de implementação.*

Each step is small, independently verifiable and independently revertible. **This is a plan; no step has been executed.**

### Step 1 — M-1: the manifest check's verdict

| | |
|---|---|
| **Pre-conditions** | Owner authorisation to implement M-1. The suspension in force. |
| **Files** | `quality_guardian/guardian.py` — `_check_manifest_integrity` only |
| **Changes** | Add the expected/found/missing/invalid/additional/divergent accounting; the `NOT_VERIFIED` verdict for an unparseable manifest; `BLOCKED` for an unavailable search root; the missing-file `FAIL`. |
| **Tests before** | T-03, T-04 (currently failing as `PASS`), T-08 |
| **Tests after** | T-01, T-02, T-03, T-04, T-05, T-06, T-07, T-08, plus the existing P03/P06/P08 |
| **Completion** | AC-1…AC-5; the real manifest still yields `WARNING` |
| **Risk** | a false `FAIL` on a host with a different Desktop layout — mitigated by AC-4's `BLOCKED` distinction |
| **Rollback** | revert the one function |

### Step 2 — M-4: identity-based protection

| | |
|---|---|
| **Pre-conditions** | Step 1 complete; the manifest's row set is trustworthy (M-1 makes it so) |
| **Files** | `quality_guardian/config.py` — `is_manifest_protected`, `is_protected`, a new `manifest_protection_for`; `quality_guardian/repair.py` — `apply_level1_fixes_in_project` |
| **Changes** | Resolve before comparing; build the protected set from the manifest with the prefix set as fallback; close the case gap; keep both public signatures as wrappers |
| **Tests before** | T-20, T-21, T-23 (currently failing on the case variant) |
| **Tests after** | T-20, T-21, T-22, T-23, plus P01/P02/P09/P10 |
| **Completion** | AC-15, AC-16 |
| **Risk** | over-broad protection blocking legitimate repairs — mitigated by AC-16 |
| **Rollback** | revert `config.py` and `apply_level1_fixes_in_project` |

### Step 3 — M-2: artefact-identity validation on the write path

| | |
|---|---|
| **Pre-conditions** | Step 2 complete (the hash check is shared) |
| **Files** | `quality_guardian/repair.py` — `write_file_text`, a new `validate_repair`, `repair_is_sane`; `quality_guardian/guardian.py` — `_attempt_repairs` (two call sites) |
| **Changes** | V1 hash revalidation, V2 compile, V3 transformation fidelity, V4 parse; root-aware policy resolution; the structured write result; the `expected_hash` parameter; the revert exemption |
| **Tests before** | T-09, T-10, T-11, T-12 (currently escaping or unsupported) |
| **Tests after** | T-09…T-14, plus the existing P01/P02 |
| **Completion** | AC-6…AC-10 |
| **Risk** | false refusals on files that were already invalid — mitigated by the distinct refusal reason; a revert refused by V3 — mitigated by the explicit exemption |
| **Rollback** | revert `repair.py` and the two call sites |

### Step 4 — M-3: the suspension as a controlled state

| | |
|---|---|
| **Pre-conditions** | Step 3 complete — M-2 changes the write path M-3 makes safe to interrupt |
| **Files** | `quality_guardian/repair.py` — the `RepairSuspended` signal and the write result; `quality_guardian/guardian.py` — `_attempt_repairs`, `run_cycle`, the `pre_verify` nudge decision in `hook.py`; `quality_guardian/cli.py` — a top-level guard |
| **Changes** | Convert the raise into a structured refusal; unify the two suspension branches into one; add the `REPAIR_SUSPENDED` state; exclude it from the `pre_verify` nudge; a CLI-level guard |
| **Tests before** | the current G06 error; T-13…T-19 (currently unsupported) |
| **Tests after** | T-13…T-19 |
| **Completion** | AC-11…AC-14 |
| **Risk** | a real fault misreported as a policy refusal — mitigated by the distinct machine-checkable reason strings |
| **Rollback** | revert the return shape and the call site; the suspension file remains in force |

### Step 5 — G06 update and the full verification

| | |
|---|---|
| **Pre-conditions** | Step 4 complete |
| **Files** | `quality_guardian/tests/test_guardian.py` — `G06ReRunTest` only; new test modules for the T-matrix as needed |
| **Changes** | The G06 update specified in §6; the new adversarial tests T-01…T-23 |
| **Tests before** | 29/30 with one error |
| **Tests after** | the full suite passes with no test removed or weakened |
| **Completion** | AC-17, AC-18, AC-19, AC-20, AC-21 |
| **Risk** | a test that depends on the host's global suspension state — eliminated by the per-test policy fixture |
| **Rollback** | revert the test file |

### Step 6 — reactivation decision (owner only)

| | |
|---|---|
| **Pre-conditions** | Steps 1–5 complete and verified |
| **Files** | `quality_guardian/state/repair-policy.json` — **one field** |
| **Changes** | `auto_repair: false` → `true`, with the authorisation recorded |
| **Completion** | AC-22; the owner confirms in writing |
| **Risk** | reactivating before the verification is complete — the sequence prevents it |
| **Rollback** | set `auto_repair` back to `false` |

### 8.1 Dependencies and the recommended order

```
M-1  ─────────────► (independent)
 │
 └─► enables trustworthy manifest rows ──► M-4
                                          │
                                          └─► supplies the hash anchor ──► M-2
                                                                        │
                                                                        └─► changes the write path ──► M-3
                                                                                        │
                                                                                        └─► G06 update + full verification
```

**Recommended order: M-1 → M-4 → M-2 → M-3 → G06.** M-1 first because it makes the manifest a trustworthy authority, which M-4 then relies on. M-4 before M-2 because they share the write-time hash check and must be implemented once. M-3 last among the recommendations because it makes safe the write path that M-2 changes.

**M-3 could be implemented before M-2** — they are technically independent — but then the G06 update would land before the write path it exercises is final, and the suite would have to be re-verified twice.

---

## 9. Rollback plan

*Secção 9 — Plano de rollback.*

### 9.1 Principles

1. **The suspension is the master rollback.** If anything goes wrong at any step, setting `auto_repair: false` stops all project-source writes immediately, regardless of the state of the code.
2. **Every step is a small, revertible change.** No step introduces a data migration, a schema change or a state format change, so every step reverts with a file restoration.
3. **The pre-remediation state is already backed up.** `…\hermes\cache\scratch\qg-pre-suspension-20261108-124516` holds the Guardian, the hooks, the allowlist and the configuration as they stood immediately after the security audit, with a per-file SHA-256 manifest in `BACKUP-SHA256.json`.
4. **The historical artefacts are not touched at all.** The manifest, the addendum, `copy.py` and the specification are outside every step's file list. A rollback cannot affect them.

### 9.2 The rollback procedure

| Situation | Action | Effect |
|---|---|---|
| A step's tests fail | revert that step's files | the suspension remains in force |
| The suite fails after a step | revert that step, then re-run the suite | the prior state is restored |
| A protected file is modified | **stop immediately**; set `auto_repair: false`; restore the file from the manifest's recorded hash by re-deriving it from the Phase 2A delivery; record the event | the Guardian returns to detection-only |
| The write path misbehaves in production | set `auto_repair: false` | all writes stop; detection continues |
| A rollback is needed wholesale | restore `quality_guardian/` from `qg-pre-suspension-20261108-124516`, verified against `BACKUP-SHA256.json` | the exact post-audit state |

### 9.3 What is explicitly not rolled back

| Artefact | Why |
|---|---|
| `docs/PHASE-2A-MANIFEST.md` | the historical record; never modified, never restored |
| `docs/PHASE-2A-MANIFEST-ADDENDUM-A-1.md` | the truthful record of the divergence |
| `consequence_map/domain/copy.py` | the reconstruction; never modified by the remediation |
| The 51 matching manifest entries | the delivered Phase 2A state |
| `config.yaml` and the allowlist | the suspension is implemented in the Guardian, not in the Hermes configuration |

---

## 10. Risks outside the scope of M-1 to M-4

*Secção 10 — Riscos fora do âmbito.*

Recorded separately, **not** folded into the specification, and **not** to be implemented without the owner's approval.

| # | Risk | Severity | Why it is out of scope | Where it is addressed |
|---|---|---|---|---|
| **F-07** | The Telegram notification policy is not implemented — the Guardian is silent | MEDIUM | M-1…M-4 do not mention notification | audit **M-5**, §13.2 |
| **F-08** | `module_for_path` returns `""` for a project-relative path | LOW | not a safety defect; the runtime passes absolute paths | audit §4.5; no remediation assigned |
| **R-6** | Concurrent cycles can interleave; `save_state` has no lock | MEDIUM | M-1…M-4 do not mention locking | audit **M-6** |
| **M-7** | No verifiable backup of the original before a write | — | M-2's text does not include a backup; the audit's §5.3 lists it under the wider set | audit **M-7** |
| **M-8** | No `flush`/`fsync`; the temporary file is not validated before the rename; it is not cleaned up on failure | LOW | M-2's text covers validation of the *content*, not the durability of the write | audit **M-8** |
| **M-9** | The absence check covers only `consequence_map/tests/`; the other 19 protected package files have no absence check | — | M-1 addresses the manifest check, which covers all 52 entries — so M-9 becomes largely redundant once M-1 lands. It should be re-evaluated after M-1 rather than implemented separately | audit **M-9** |
| **M-11** | No per-cycle lock file | — | future | audit **M-11** |
| **M-12** | The artefact-identity model does not extend beyond the manifest | — | future | audit **M-12** |
| **M-13** | The Guardian is not read-only by default | — | future; note that the current suspension is a *temporary* form of exactly this | audit **M-13** |
| **M-14** | The symlink and hard-link behaviour is unproven on this host | — | future; M-4's I2/I3 mitigate it | audit **M-14** |

**A note on M-9.** M-9 and M-1 overlap: M-1 makes the manifest check assert over the expected rows, which covers all 52 entries including the 19 package files M-9 proposes to check separately. **Implementing M-9 after M-1 would be redundant.** The specification recommends re-evaluating M-9 once M-1 has landed, rather than implementing it as a separate change.

---

## 11. Decisions requiring the user's authorisation

*Secção 11 — Decisões que exigem autorização do utilizador.*

| # | Decision | Why it cannot be decided here |
|---|---|---|
| **D-1** | Authorise the implementation of M-1 to M-4, in the order M-1 → M-4 → M-2 → M-3, with the G06 update in Step 5. | This document is a specification; the task is explicitly read-only. |
| **D-2** | Confirm that the **suspension stays in force** through Steps 1–5, and that reactivation is a separate, explicit decision at Step 6. | The audit's recommendation, not the audit's decision. |
| **D-3** | Decide whether an **unlisted file** in the project tree is a defect (affecting the verdict) or an observation (recorded only). M-1's text does not say. | This changes a pass/fail criterion. The specification proposes recording it only. |
| **D-4** | Decide whether a **structurally incomplete manifest row** is `FAIL` or `NOT_VERIFIED`. The specification proposes `FAIL` — a malformed row is a defect in the manifest — but M-1's text says only *"any entry that cannot be resolved is FAIL"*. | The distinction is between a corrupt manifest and an unresolvable file. |
| **D-5** | Decide whether the **search-root unavailability** verdict should be `BLOCKED` or `FAIL`. The specification proposes `BLOCKED`. | Both are defensible; `BLOCKED` is the honest one. |
| **D-6** | Confirm that **M-7 and M-8 are deferred**, so the write path after M-2 has no durable backup and no `fsync`. The specification notes this as a residual risk rather than silently expanding M-2's scope. | Expanding M-2's scope without approval would violate the brief. |
| **D-7** | Confirm whether **M-9 is dropped as redundant** once M-1 asserts over the expected rows. | M-9's value depends on M-1's outcome. |
| **D-8** | Confirm the **acceptance target** for the Guardian's suite: "every test passes, with no test removed or weakened", with the count whatever the implementation produces (32 by the specification's plan). | The current count is 30; the target must not be a fixed number that invites weakening. |

**Also carried forward, unchanged from the security audit and not decided here:**

| # | Decision |
|---|---|
| **D-9** | The `copy.py` divergence: accept the reconstruction as a **known** baseline divergence with the addendum as the record, or restore the original bytes from a source outside this machine. **The original is not recoverable here.** The reconstruction is **not** accepted as a baseline by this document. |
| **D-10** | Whether to implement the Telegram policy (audit M-5 / F-07). |

---

## 12. Classification

# READY WITH OPEN QUESTIONS

**Why not `READY FOR REVIEW`.** The technical specification is complete: the mapping of M-1 to M-4 is established from the audit's own text, the current behaviour of every affected function is confirmed by inspection, the minimal change for each is specified with its risks and rollback, the adversarial test matrix covers every scenario the brief names, and the G06 update is defined without weakening a single assertion. But **eight decisions** (D-1 to D-8) require the owner's judgement — most consequentially D-3, D-4 and D-5, each of which changes a pass/fail criterion — and D-9, the `copy.py` divergence, remains open from the previous audit.

**Why not `BLOCKED`.** Nothing prevents the work. The implementation is well understood, the dependencies are mapped, the write surface is a single function, and every step has a rollback. The open items are decisions, not unknowns.

**This document is a specification, not an implementation.** M-1 to M-4 have **not** been implemented. The automatic repair **remains suspended**. The Phase 2A manifest, the addendum A-1 and `copy.py` are **byte-identical** to their state at the start of this task.

---

*End of the technical remediation plan. Specification only — no code, test, configuration, hook, manifest, baseline or protected artefact was modified.*
