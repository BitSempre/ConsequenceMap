# ConsequenceMap — Quality Guardian: final adversarial decision review of M-1 to M-4

**Date:** 2026-11-08
**Nature:** Independent adversarial review and decision preparation. **Nothing was implemented.**
**Primary document reviewed:** `docs/QUALITY-GUARDIAN-M1-M4-TECHNICAL-REMEDIATION-PLAN-20261108.md` (68 155 B, SHA-256 `a4437b3b6285c1b36eb6b4ce…`)
**Classification:** **READY FOR OWNER DECISION**

---

## 1. Executive summary

*Secção 1 — Resumo executivo.*

The M-1 to M-4 plan is **sound, technically correct and implementable**. Every recommendation was traced back to its original text in the security audit, every affected function was read in the installed source, and every proposed test was checked for isolation and for whether it can actually detect a false `PASS`.

**The plan survives this adversarial review with four corrections of its own.** Each was found by inspecting the real code or the real manifest, not by re-reading the plan:

| # | Plan defect | Severity | Correction |
|---|---|---|---|
| **P-1** | M-1's "add a second regex for structurally incomplete rows" **would capture the wrong table**. The Phase 2A manifest contains **five** Markdown tables; the fourth has four columns (`File \| Bytes \| SHA-256 \| Status`) and **13 of its rows would match a permissive three-column pattern**. The result would be 13 false "invalid entries" on the real manifest — a permanent false `FAIL`. | **HIGH** | The incomplete-row detection must be **scoped to the manifest table**, not to the file. See §3.1 |
| **P-2** | M-1's "additional files" concept has **no defined scope**. The manifest does not list `quality_guardian/`, the Guardian's reports, the addendum, or the two Guardian reports in `docs/`. A naive "tree minus manifest" computation reports **~10 legitimate files** as additional. | **MEDIUM** | "Additional" must be defined as a **difference within a declared scope**, or dropped from the verdict entirely. See §3.1 |
| **P-3** | The plan treats the root-awareness defect as a **consequence** of M-2. It is more urgent than that: it is the **direct cause** of the 29/30 result, and it means **no isolated test can currently express a per-test policy**. | **MEDIUM** | Root-awareness must be a **precondition of Step 1**, not a by-product of Step 3. See §5.1 |
| **P-4** | The plan's T-15 ("make the reports directory unwritable") is **not portable to Windows** — ACL manipulation on a directory is unreliable for a non-elevated process, and the test would fail for environmental reasons rather than exercising the code path. | **LOW** | Use an **injected failure** instead of a filesystem permission. See §4, T-15 |

**Four substantive vulnerabilities were also found in the plan's own proposals** and are addressed below: a **hash-anchored identity check that can be bypassed by a content-preserving rename**, a **V3 fidelity check that would reject a legitimate repair of a file whose trailing whitespace appears in a string literal**, and two **missing TOCTOU/partial-write scenarios**.

**No finding invalidates a recommendation.** M-1 through M-4 remain the right corrections, in the right order, for the right reasons. The corrections above make the plan implementable without false positives against the real manifest.

**Ten decisions (D-1 to D-10) are consolidated in §6 with a technical recommendation for each.** Seven are technical and can be settled by following the recommendation; **three belong exclusively to the owner** (D-1, D-2 and D-9) and cannot be inferred from any evidence.

---

## 2. Confirmed current state

*Secção 2 — Estado atual.*

Verified by inspection and by non-destructive execution during this task.

| Property | Value |
|---|---|
| **Automatic repair** | **SUSPENDED** — `auto_repair: false` |
| Policy file | `quality_guardian/state/repair-policy.json`, 462 B, SHA-256 `52f60c0afb16746a54c32a31` |
| Reason recorded | *"post-incident security audit 2026-11-08: automatic repair suspended pending owner decision; detection, testing and reporting remain active"* |
| **Hooks** | `post_tool_call` (matcher `(write_file\|patch\|execute_code\|terminal)`, 120 s) and `pre_verify` (300 s), both `✓ allowed` |
| `config.yaml` | SHA-256 `85b8f48f71257a46819053d8…` — **unchanged** |
| Allowlist | SHA-256 `0faf6e9c07b1016e6637732c…` — **unchanged** |
| Wrappers | unchanged; both spawn `hook.py` and relay stdout/stderr |
| **Guardian suite** | **30 test methods, 12 classes — 29 PASS, 1 ERROR** |
| **Phase 2A suite** | **214/214 PASS** (read-only, 35.2 s) |
| `docs/PHASE-2A-MANIFEST.md` | SHA-256 `a00984d7928294a0d9d8c91f…` — **byte-identical** |
| `docs/PHASE-2A-MANIFEST-ADDENDUM-A-1.md` | SHA-256 `2f6ebcd289c94d44afe31c6e…` — unchanged |
| `consequence_map/domain/copy.py` | SHA-256 `765037914b353d18d904a657…` — **not touched** |
| **Manifest coverage** | **`51/52 ORIGINAL HASHES MATCH — 1 KNOWN RECONSTRUCTED FILE`** |
| `.git` in the project | **does not exist** |

**Integrity of the historical situation:** 51 of 52 original hashes match. `copy.py` is a **reconstruction from its contract, not a byte-for-byte recovery** — the original bytes are not recoverable on this machine. The manifest is unchanged, the addendum is unchanged, and the divergence is visible on every cycle. **The reconstruction is not accepted as a baseline.**

**Verification that the Guardian's suite writes nothing into the production tree:** the suite's `last-seen.json` was byte-identical before and after a full run (`8c46fd54eb8385de…`), and a scan of all 30 test methods found **zero** references to `config.PROJECT_ROOT`. The only three occurrences of the string `quality_guardian` in the test file are all prefixed with `self.root /`.

---

## 3. Adversarial review of M-1 to M-4

*Secção 3 — Revisão adversarial M-1 a M-4.*

### 3.1 M-1 — the manifest check must assert over the expected rows

**Original text, confirmed verbatim in the security audit §13.1:** *"The manifest check must assert over the **expected** rows, not the **found** rows: any entry that cannot be resolved is `FAIL`; an empty parse is `NOT_VERIFIED`."*

**Mapping confirmed:** M-1 closes **F-01 and F-02**. The plan's mapping table is correct.

**Does it resolve the vulnerability?** Yes, for the two findings it targets. The current code counts `missing` and then never consults it; the fix must make the verdict depend on it.

#### 3.1.1 P-1 — HIGH — the "incomplete row" regex would capture the wrong table

**Evidence.** The Phase 2A manifest contains **five** Markdown tables:

| Lines | Header | Rows |
|---|---|---|
| L14–L54 | `File \| Bytes \| SHA-256` | the 52 manifest entries |
| L62–L68 | `File \| What it holds` | 5 descriptive rows |
| L76–L79 | `File \| Purpose` | 2 descriptive rows |
| **L87–L101** | **`File \| Bytes \| SHA-256 \| Status`** | **13 rows** |
| L107–L118 | `The authorisation did **not** permit \| Status` | 10 rows |

The current strict regex anchors on `\|\s*$` after the 64-hex hash, so it does **not** match the four-column table. But the plan proposes *"add a second regex for structurally incomplete rows — a table line that has a path and a size but no 64-hex hash"*. Applied to the fourth table, a permissive three-column pattern matches **13 rows**:

```
ConsequenceMap-Phase-1.6-Documents.zip | d55863b071677f8cb278…
ConsequenceMap-Phase-1.8-Corrections.zip | 50ecbae74ddfae773d…
… 13 in total
```

Those 13 rows have a **fourth column** — a `Status` — so they are perfectly well-formed manifest entries with a status annotation, not invalid rows.

**Consequence.** The implementation would report 13 false "invalid entries" on the **real** manifest, producing a permanent false `FAIL` on every cycle. The remediation would introduce a new CRITICAL defect while fixing the first.

**Correction.** The incomplete-row detection must be **scoped to the manifest table**, not to the file. Two workable mechanisms:

- **Anchor on the table's header.** Parse the manifest as a sequence of tables (a header row followed by a `|---|` separator), identify the table whose header is exactly `File | Bytes | SHA-256`, and apply both the strict and the permissive patterns **only within that table's row range**.
- **Anchor on the column count.** Accept a row as a manifest entry only when it has **exactly three** columns, or exactly four **where the fourth is a recognised status vocabulary**. A row with a different shape is a row of another table and is **ignored**, not flagged.

The second is simpler and more robust; the first is more explicit. **Either is acceptable; what is not acceptable is a file-wide permissive regex.** The plan must say which.

**Additional constraint.** The plan's T-06 and T-07 introduce rows with invalid paths and invalid hashes. Under a file-wide permissive regex these would be detected; under a table-scoped one they are equally detected — **provided the test fixture's manifest has the same table structure as the real one.** The test fixtures must therefore include a **four-column table** with valid rows, so the test proves the scoping works and not merely that invalid rows are caught.

#### 3.1.2 P-2 — MEDIUM — "additional files" has no defined scope

**Evidence.** The manifest covers `consequence_map/` (32), `docs/` (4), `evidence/` (10) and 19 Desktop artefacts. It does **not** list:

- `quality_guardian/` — the Guardian's own entire tree (14 modules + tests + reports + state)
- `docs/QUALITY-GUARDIAN-IMPLEMENTATION-REPORT-20261108.md`
- `docs/QUALITY-GUARDIAN-POST-INCIDENT-SECURITY-AUDIT-20261108.md`
- `docs/PHASE-2A-MANIFEST-ADDENDUM-A-1.md`
- `docs/QUALITY-GUARDIAN-M1-M4-TECHNICAL-REMEDIATION-PLAN-20261108.md`
- `docs/QUALITY-GUARDIAN-M1-M4-FINAL-DECISION-REVIEW-20261108.md` (this document)

The tracked-file set (`detect.tracked_files`) excludes `quality_guardian/` but **includes** `docs/`. The baseline `last-seen.json` holds 42 files, including five under `docs/` — three of which are not in the manifest.

**Consequence.** A naive "tree minus manifest" computation reports at least **five legitimate files** as "additional". If that affects the verdict, the Guardian fails its own cycle. The plan correctly proposes that additional files be recorded and **not** affect the verdict — but it leaves the *computation* undefined, and an undefined computation is where the next defect will come from.

**Correction.** Either:
- **Scope it explicitly** — "additional" = a file under the three manifest-covered prefixes (`consequence_map/`, `docs/PHASE-2A-`, `evidence/`) that the manifest does not list, excluding files matching a declared exemption list; **or**
- **Drop the concept from the verdict entirely** and record only the count, without naming files.

The first is more informative; the second is safer. **Either satisfies M-1's text, which says nothing about additional files.**

#### 3.1.3 The six states the brief requires

| State | Current | Required | Achievable under the corrected plan? |
|---|---|---|---|
| **Expected** | a parsed row | a parsed row | yes |
| **Found** | `checked` counter | named set | yes |
| **Missing** | counted, **ignored** | `FAIL` | yes — the core fix |
| **Additional** | does not exist | observation only | yes, with P-2's scoping |
| **Divergent** | `FAIL`, or `WARNING` when documented | preserved | yes — unchanged |
| **Manifest invalid** | `PASS` with "0 entries" | `NOT_VERIFIED` | yes |

**Read failures.** The brief asks about *"falhas de leitura"*. The current `detect.sha256_of` returns `""` on `OSError` or `ValueError`. An empty hash is then compared against the expected hash and **counts as divergent** → `FAIL`. That is correct behaviour, but the *reason* is mislabelled: an unreadable file is not a "divergence", it is an inability to verify. The corrected plan should distinguish `unreadable` from `divergent` and report it as `BLOCKED` rather than `FAIL` — the same distinction M-1 already proposes for an unavailable search root.

#### 3.1.4 Is M-9 really redundant after M-1?

**The plan asserts it is. The assertion is correct, with one qualification.**

- The manifest lists **32** files under `consequence_map/`, of which **15** are under `consequence_map/tests/`.
- M-9 proposed checking the absence of the **19** package files *outside* `tests/` — but the arithmetic is **17** (32 − 15), not 19. M-9's own figure is off by two.
- M-1, asserting over the expected rows, covers **all 32** — including the 15 test files — for absence.
- The existing `_check_tests_preserved` compares `before`/`after` **within a cycle**, so it detects a test file deleted *during* a cycle, but **not** one deleted *before* the cycle. That gap is exactly what M-1 closes.

**Conclusion.** M-9's coverage is fully subsumed by M-1, **provided M-1 counts `missing` for every expected row**. The plan's recommendation to drop M-9 as redundant is therefore **supported by evidence** — the brief asked for that demonstration, and this is it.

**The one qualification:** M-9's *stated* figure (19) does not match the actual count (17). Any record of the decision should state the corrected number, and the reasoning above.

#### 3.1.5 Verdict on M-1

**Correct in principle; two implementation corrections required (P-1, P-2) and one refinement (unreadable vs divergent).** The core mechanism — the verdict must depend on the *expected* set — is exactly right and is the minimal change.

---

### 3.2 M-2 — artefact-identity validation on the write path

**Original text:** *"Replace the size heuristic with artefact-identity validation: record the pre-write hash, revalidate it at the moment of the write, compile and parse the result, and require the write to differ from the original **only** by the intended transformation."*

**Mapping confirmed:** M-2 closes **F-03 and F-06**. Correct.

#### 3.2.1 Is V3 (transformation fidelity) actually implementable?

**Verified empirically.** The N1 transformation is deterministic:

```
apply_level1_fixes(original) == fixed          → True
```

so V3 is expressible as `fixed == apply_level1_fixes(original)`. A semantic change is rejected:

```
original:   "def f():\n    return 1   \n"
candidate:  "def f():\n    return 2   \n"     (constant changed + trailing whitespace)
apply(original) != candidate                   → V3 REJECTS ✓
```

**V3 works.** But it has a **false-positive** case the plan does not mention:

> A trailing-whitespace sequence **inside a string literal** is not trailing whitespace. `apply_level1_fixes` operates on lines, not on tokens, so it would strip whitespace that is **part of the data**.

A file containing `TEXT = "hello   "` has its **string content** altered by the current N1 repair. V3 would *accept* that repair — because it faithfully reproduces what `apply_level1_fixes` does — and the repair would still be a **data-changing** edit.

**This is a pre-existing defect in the N1 transformation, not something M-2 introduces.** But M-2 is the natural moment to bound it, because M-2 is where the write path gains the machinery to detect it. The plan should require the transformation to be **token-aware** — that is, to strip trailing whitespace only where the whitespace is genuinely outside a string literal — or to **refuse to repair** a file whose only difference lies inside a literal.

This is **within M-2's scope**: M-2's requirement that the write *"differ from the original **only** by the intended transformation"* is precisely the property a token-unaware transformation violates. The plan's phrasing of V3 is correct; its *choice of transformation* needs tightening.

#### 3.2.2 V1 (hash revalidation) — where must it live?

The plan offers the hash check as part of the write path. **Where** matters:

| Option | Coverage | Assessment |
|---|---|---|
| **A — inside `write_file_text`** | every caller, including the **revert** path | **Correct.** The revert also writes; a check in `_attempt_repairs` alone would leave it unprotected |
| B — in `_attempt_repairs` | the apply path only | Insufficient |

**The plan's requirement that the write be fail-closed without an `expected_hash` is right.** It makes the write path refuse by default, which is the correct posture for a safety mechanism.

**One consequence the plan does not state:** the **revert** path writes the *original* content, which is **not** a transformation of the original — V3 would reject it. The plan mentions this in §4.2 (*"a revert must be exempt from the transformation-fidelity check"*) but the exemption must be **explicit in the API**, not merely in the prose: the revert must carry a distinct flag or a distinct entry point, so that a caller cannot accidentally pass original content through the transformation path and have it refused.

#### 3.2.3 V2/V4 — compile and parse

**Verified.** An invalid candidate raises `SyntaxError` on `compile`. If the **original** is already invalid, V2 on the candidate also fails — correctly, since an N1 repair cannot fix a pre-existing syntax error. The plan requires the refusal reason to distinguish the two, which is right: the operator must not be sent chasing the wrong thing.

**A subtlety the plan does not mention:** `compile()` and `ast.parse()` both operate on the *text*. A file with a **BOM** or a non-UTF-8 encoding would fail both. The N1 scope is `.py` files read as UTF-8, so the exposure is limited, but a file with a BOM is valid Python and would be refused. The refusal reason must say "encoding" rather than "syntax" in that case.

#### 3.2.4 Compatibility with protected files

**Confirmed.** `apply_level1_fixes_in_project` refuses manifest-covered files before the transformation is applied, so V1–V4 never see a protected file through that path. The write path's additional identity check (M-4) closes the remaining route.

#### 3.2.5 Verdict on M-2

**Correct and implementable.** Two refinements required: the transformation must be **token-aware** (or the repair must refuse string-literal whitespace), and the **revert exemption must be explicit in the API**. V1 must live inside the write choke point. The percentage rule must remain a secondary guard and must never be described as an integrity guarantee — the plan states this correctly.

---

### 3.3 M-3 — the suspension must be a controlled state

**Original text:** *"Catch `RepairSuspended` at the call site and convert it to a reported `NOT_VERIFIED`; the cycle must always complete and always write its report."*

**Mapping confirmed:** M-3 closes **F-04**. Correct.

#### 3.3.1 The current behaviour, verified

`RepairSuspended` is raised in `repair.py` and caught in **no** module. The consequences:

| Caller | Current behaviour |
|---|---|
| `hook.py` | caught by the outer `except Exception:` → exit 0, the turn continues, **but no report is written** because the cycle aborted before `finalize` |
| `cli.py` | **not caught** — no `except` anywhere in the file → traceback, no report |
| `_attempt_repairs` | **not caught** → the cycle aborts |

#### 3.3.2 Does the plan's conversion preserve all six properties?

| # | Property | Plan's mechanism | Assessment |
|---|---|---|---|
| 1 | The repair stays blocked | the choke point still refuses | ✔ |
| 2 | Detection keeps working | the cycle continues past the refusal | ✔ |
| 3 | Tests keep running | the cycle continues to execution and reporting | ✔ |
| 4 | The report is produced | `finalize` is reached | ✔ |
| 5 | The hooks never fail | the exception no longer escapes `run_cycle` | ✔ — and the CLI gains a top-level guard |
| 6 | The state is explicit | a `repair-capability` check carrying `REPAIR_SUSPENDED` | ✔ |

**Property 5 has a subtlety the plan gets right.** Today the hooks are safe *only because* `hook.py` has a catch-all. Under M-3 the exception is gone from the cycle entirely, so the hooks' safety no longer depends on that catch-all. The plan's addition of a CLI-level guard restores the same defence in depth on the CLI side. **Correct.**

#### 3.3.3 The `pre_verify` nudge — the plan's most important insight

**Verified in the source.** `hook.py`:

```python
if verdict in ("FAIL", "NOT_VERIFIED", "BLOCKED"):
    directive = {"action": "continue", "message": "…"}
```

`NOT_VERIFIED` **does** produce a `continue` directive. Under the suspension, every cycle's `repair-capability` check is `NOT_VERIFIED` — so **every cycle would nudge the agent to keep working**, for a condition that will never resolve on its own. With the runtime's `max_verify_nudges` default of 3, that is three wasted turns per turn, each re-running the suite.

**The plan's proposed exclusion is correct and necessary.** The `pre_verify` decision must be driven by the **substantive** verdict, with `REPAIR_SUSPENDED` reported as context rather than as a failure to fix.

**The implementation must be precise**, or the exclusion becomes a hole: excluding `REPAIR_SUSPENDED` from the nudge must **not** exclude a genuine `NOT_VERIFIED` that happens to accompany it. The correct rule is:

> The nudge is suppressed **only** when every `NOT_VERIFIED`/`BLOCKED` check in the cycle is either the `repair-capability` check in the `REPAIR_SUSPENDED` state, or a check the `repair-capability` check explicitly attributes to the suspension. A `NOT_VERIFIED` from any other source still nudges.

A cycle with a suspended repair **and** an unverifiable manifest must still nudge — the manifest problem is real and is not resolved by un-suspending anything.

#### 3.3.4 The structured-result proposal

The plan recommends replacing the `bool` return with a structured result, because the current `False` conflates three outcomes — refused by policy, refused by validation, and failed to write. **Correct.** The refusal reasons must be machine-checkable and distinct:

| Reason prefix | Meaning |
|---|---|
| `REPAIR_SUSPENDED:` | the policy forbids it |
| `VALIDATION_REFUSED:` | V1–V4 rejected the content |
| `WRITE_FAILED:` | the filesystem refused the write |

#### 3.3.5 Verdict on M-3

**Correct and complete.** The nudge exclusion is the part most likely to be missed, and the plan identifies it. The only refinement is the precision rule in §3.3.3: the exclusion must be **source-scoped**, not verdict-scoped.

---

### 3.4 M-4 — identity-based protection

**Original text:** *"Make the protection identity-based: resolve the path, compare against the resolved set of manifest-covered files, and check the hash at the write. Close the case-sensitivity gap between `is_protected` and `is_manifest_protected`."*

**Mapping confirmed:** M-4 closes **F-05**. Correct.

#### 3.4.1 The case-sensitivity gap, verified

```
is_manifest_protected('consequence_map/domain/copy.py')  → True
is_manifest_protected('ConsequenceMap/domain/copy.py')   → False
is_manifest_protected('CONSEQUENCE_MAP/domain/copy.py')  → False
```

On Windows's case-insensitive filesystem, **all three are the same file**. Two of the three spellings bypass the manifest guard. **Confirmed as a real vulnerability.**

The plan's remedy — resolve the path before comparing — is correct. **Verified empirically** that resolution normalises every variant:

| Input variant | Resolved relative path | Protected after resolution? |
|---|---|---|
| `consequence_map/domain/copy.py` | `consequence_map/domain/copy.py` | ✔ |
| `consequence_map\domain\copy.py` | `consequence_map/domain/copy.py` | ✔ |
| `consequence_map/domain/../domain/copy.py` | `consequence_map/domain/copy.py` | ✔ |
| `consequence_map/domain/./copy.py` | `consequence_map/domain/copy.py` | ✔ |
| `./consequence_map/domain/copy.py` | `consequence_map/domain/copy.py` | ✔ |

All five resolve to the same relative path and would be protected.

#### 3.4.2 A bypass the plan does not name: the rename

**The hash anchor alone is insufficient.** M-4's third clause is *"check the hash at the write"*. Consider:

1. A manifest-covered file `consequence_map/domain/copy.py` is protected by path.
2. An attacker (or a careless agent) **renames** it to `scratch/notes.py` — the content is unchanged, so the hash still matches.
3. The path no longer matches any protected prefix.
4. A repair is attempted on `scratch/notes.py`.

Does the hash anchor catch it? Only if the check asks *"does this file's hash match a manifest row **that is still at its expected path**?"* — i.e. the manifest row must also be **resolved and present**. If the implementation instead asks *"does this file's hash match **any** row in the manifest?"*, then a file with the **same content as a protected file**, but at a different path, is treated as protected. That is **over-protective**, not a bypass — it refuses a legitimate repair of an unrelated file.

The dangerous inverse is the implementation that checks the hash but **does not verify the manifest row still resolves**. Then a file that was moved out of the protected set would be unprotected — which is precisely the rename.

**The correct formulation**, which the plan should state explicitly:

> A file is protected when **either** its resolved path is in the manifest-covered set **or** its content hash equals the hash of a manifest entry **whose own path still resolves to a file with that same hash**. The second clause protects a protected file that was moved; the first protects everything the manifest names. A file that merely *happens* to share content with a protected file is **not** thereby protected — unless the intent is to be that strict, in which case it must be stated.

The practical consequence is small (the moved file is still the protected artefact), but the rule must be unambiguous, or two implementations will diverge — and M-2 and M-4 must not diverge, which is the plan's own §3.2 point.

#### 3.4.3 Collisions and ambiguity

**Verified on the real manifest.** No duplicate entries exist, and **no** entry exists in both the project tree and the Desktop — so the project-first search order is deterministic and unambiguous for the current state.

**The plan must still specify the collision rule**, because the state could change: if a manifest entry existed in **both** roots with **different** content, which is authoritative? The current code silently prefers the project. That is the right default, but it must be **recorded in the evidence**, not implicit — otherwise a divergence in the Desktop copy would be invisible.

#### 3.4.4 Does the normalisation introduce new bypasses?

**No — provided the normalisation is one-way and the check is applied to the resolved path.** The risk would be a normalisation that *strips* a protected prefix rather than resolving it. The plan's approach (resolve, then compare) does not have that shape. Two residual notes:

- **Resolution is non-strict.** `Path.resolve()` on a non-existent path still yields an absolute path; `strict=True` would raise. The plan should specify `strict=False` explicitly and handle `OSError`.
- **Symlink and hard-link behaviour is NOT VERIFIED** on this host — `os.symlink` raised `OSError` (no developer-mode privilege). M-4's resolution-and-hash approach **mitigates** the symlink case (a symlink resolves to its target, and the target's hash anchors the protection), but the definitive proof remains the audit's M-14.

#### 3.4.5 Verdict on M-4

**Correct in principle.** Two clarifications required: the hash clause must be stated so that a **renamed** protected file stays protected (and an unrelated file with coincidentally identical content is not over-protected by accident), and the **collision rule** between the two search roots must be explicit and recorded.

---

### 3.5 Cross-cutting findings on the plan as a whole

| # | Finding | Severity | Detail |
|---|---|---|---|
| **P-3** | The root-awareness defect is the **direct cause** of the 29/30 result, and it is scheduled too late | MEDIUM | See §5.1 |
| **X-1** | The N1 transformation is **not token-aware** and can alter string-literal content | MEDIUM | See §3.2.1. Pre-existing; M-2 is the moment to bound it |
| **X-2** | The plan does not require the **revert exemption** to be explicit in the API | LOW | §3.2.2 |
| **X-3** | No scenario covers a **failure between the temporary write and the rename** | LOW | §4 |
| **X-4** | No scenario covers **two concurrent cycles** | MEDIUM | §4 — the audit's M-6, correctly out of scope for M-1…M-4, but a test that merely *documents* the behaviour is cheap |

---

## 4. Audit of the 23 adversarial tests

*Secção 4 — Auditoria T-01 a T-23.*

Every test was checked individually for: the vulnerability it covers, whether the preparation is genuinely isolated, whether the expected result is unambiguous, whether it can detect a false `PASS`, and the risk of touching a real file.

**All 23 use a temporary copy or an artificial fixture. None uses a real protected file as a destructive target.** The brief's required coverage is complete:

| Required scenario | Test | Verdict |
|---|---|---|
| Protected file missing | T-01 | ✔ |
| Protected file altered | T-02 | ✔ |
| Empty manifest | T-03 | ✔ |
| Malformed manifest | T-04 | ✔ |
| Duplicate entry | T-05 | ✔ |
| Invalid path | T-06 | ✔ |
| Invalid hash | T-07 | ✔ |
| Invalid content, similar size | T-09 | ✔ |
| Truncated content | T-10 | ✔ |
| Repair during suspension | T-13 | ✔ |
| Error during the repair | T-14 | ✔ |
| Error during report production | T-15 | ✔ (with P-4) |
| `post_tool_call` execution | T-16 | ✔ |
| `pre_verify` execution | T-17 | ✔ |

### 4.1 Per-test assessment

| Test | Covers | Isolated? | Expected result unambiguous? | Can it detect a false PASS? | Real-file risk | Assessment |
|---|---|---|---|---|---|---|
| **T-01** | F-01 | ✔ temp project | ✔ `FAIL` + `evidence.missing` | ✔ **yes** — this is the F-01 detector | none | **Sound** |
| **T-02** | F-01 (divergent) | ✔ | ✔ `FAIL` / `WARNING` when documented | ✔ | none | **Sound** |
| **T-03** | F-02 | ✔ | ✔ `NOT_VERIFIED` | ✔ **yes** — a `PASS` here fails the test | none | **Sound** |
| **T-04** | F-02 | ✔ | ✔ `NOT_VERIFIED` | ✔ **yes** | none | **Sound** |
| **T-05** | duplicate entry | ✔ | ⚠ **ambiguous** | ⚠ **weak** | none | **Needs refinement** — see below |
| **T-06** | malicious path | ✔ | ✔ `FAIL` + `invalid_entries` | ✔ | none, **but the test must assert nothing was created outside the temp tree** | **Sound with an added assertion** |
| **T-07** | invalid hash | ✔ | ✔ `FAIL` + `invalid_entries` | ✔ | none | **Sound** |
| **T-08** | unavailable search root | ✔ | ⚠ **ambiguous** | ✔ | none | **Needs a precise definition** — see below |
| **T-09** | F-03 same-size invalid | ✔ | ✔ refused, reason names the syntax failure | ✔ | none — refusal precedes any write | **Sound** |
| **T-10** | truncation | ✔ | ✔ refused | ✔ | none | **Sound** |
| **T-11** | F-03 semantic change | ✔ | ✔ refused by V3 | ✔ | none | **Sound** — V3 verified to reject it |
| **T-12** | F-06 TOCTOU | ✔ | ✔ refused; the external change survives | ✔ | none | **Sound** |
| **T-13** | suspension | ⚠ **depends on P-3** | ✔ `REPAIR_SUSPENDED` | ✔ | none | **Sound once the write path is root-aware** |
| **T-14** | write failure | ✔ | ✔ recorded, cycle continues | ✔ | none | **Sound, but see P-4's alternative** |
| **T-15** | report failure | ✔ | ⚠ **not portable** | ✔ | none | **Needs correction — P-4** |
| **T-16** | `post_tool_call` | ✔ | ✔ exit 0 + report written | ✔ | none | **Sound** |
| **T-17** | `pre_verify` | ✔ | ✔ exit 0 + report written | ✔ | none | **Sound** |
| **T-18** | nudge suppression | ✔ | ✔ **no** `continue` | ✔ | none | **Sound — the most valuable test in the set** |
| **T-19** | incomplete payload | ✔ no preparation | ✔ exit 0, no error | ✔ | none | **Sound** |
| **T-20** | alternate path | ✔ | ✔ refused | ✔ | none | **Sound** |
| **T-21** | case variant | ✔ | ✔ refused | ✔ | none | **Sound — the direct F-05 detector** |
| **T-22** | unlisted file | ✔ | ✔ **permitted** | ✔ (asserts *not* over-blocked) | none | **Sound — the over-protection counter-test** |
| **T-23** | hash-matched, unusual path | ✔ | ✔ refused | ✔ | none | **Sound** |

### 4.2 The three tests that need refinement

**T-05 (duplicate entry) — ambiguous expected result.** The plan says the duplicate is *"reported, not double-counted"* and the verdict is `PASS`. But the real manifest has **no** duplicates, so a duplicate is an anomaly in the manifest — the same class as an invalid hash. Reporting it as `PASS` with a note risks it being read as "a duplicate is acceptable". **Recommendation:** the verdict should be `FAIL` (an invalid manifest entry), with the duplicate named in `evidence.invalid_entries` — consistent with T-07's treatment of an invalid hash. If the owner prefers, `NOT_VERIFIED` is the alternative; `PASS` is not defensible.

**T-08 (search root unavailable) — the scenario is undefined.** "A manifest row pointing at a path outside both roots" describes a **missing file**, not an **unavailable root**. Those are different facts with different verdicts: missing → `FAIL`; root unavailable → `BLOCKED`. **Recommendation:** the test must make the **root itself** unavailable — for example by constructing a temp project whose manifest references a path on a non-existent root — and assert `BLOCKED`. A separate assertion should cover the missing-file case as `FAIL`. The brief asks for both.

**T-15 (report production error) — not portable.** Making a directory unwritable on Windows requires ACL manipulation, which is unreliable for a non-elevated process and would fail for environmental reasons. **Recommendation (P-4):** inject the failure instead of provoking it — pass a `root` whose `quality_guardian/reports` path is occupied by a **file**, so the directory creation fails deterministically. The test then asserts that the cycle's checks are unaffected, the project is untouched, and the failure is reported on stderr with a non-zero exit code.

### 4.3 Scenarios worth adding

None is a substitute for the 23; each closes a gap the 23 leave.

| # | Scenario | Why |
|---|---|---|
| **T-24** | A manifest fixture containing a **valid four-column table** beside the entry table | Proves the P-1 scoping correction — without it, a file-wide permissive regex fails the test |
| **T-25** | A protected file **renamed** out of the protected path, then repaired | Proves the M-4 hash clause covers the rename bypass (§3.4.2) |
| **T-26** | A file whose only difference is **whitespace inside a string literal** | Proves the token-awareness requirement (§3.2.1) |
| **T-27** | A failure **between the temporary write and the rename** | The temporary must not be left behind and the original must be intact |
| **T-28** | Two cycles running concurrently against the same temp project | Documents the current last-writer-wins behaviour without asserting a fix (M-6 is out of scope) |
| **T-29** | An **unreadable** protected file (permissions or a locked handle) | Distinguishes "cannot verify" from "divergent" — the refinement in §3.1.3 |

**The brief's own list also asks about *"recuperação após falha"* — the rollback path.** The 23 do not cover it directly: **T-10** covers a refused truncation, but not a **successful** repair followed by a regression and a revert. That path exists in `_attempt_repairs` (`if regressed: repair.write_file_text(path, original)`) and it is the **only** path that restores content. **T-30** should cover it: force a regression, assert the original is restored byte-for-byte and the proposal is marked `reverted`. Under M-2, the revert must survive the V3 fidelity check — the exemption in §3.2.2.

---

## 5. G06 and the suite

*Secção 5 — Análise G06 e suite.*

### 5.1 The real cause of the 29/30 result

**Not** the suspension's logic, and **not** the test's assertion. It is a **scope error in the write path**. The chain, verified empirically:

```
a) guardian._attempt_repairs → config.auto_repair_enabled(root=self.root)
   → repair_policy(<temp>) → no policy file → DEFAULT_AUTO_REPAIR = True
   → PROCEEDS to the write

b) repair.write_file_text(path, fixed) → config.auto_repair_enabled()   ← NO ROOT
   → repair_policy(PROJECT_ROOT real) → auto_repair = False
   → raises RepairSuspended
```

Measured directly:

```
auto_repair_enabled(<temp>)  → True      (the isolated tree has no policy)
auto_repair_enabled()         → False     (the production tree does)
write_file_text(...)          → RepairSuspended
```

**The consequence is larger than one failing test.** Because the write path always consults the **production** policy, **no isolated test can express its own policy**. A test that wants "repair enabled" gets whatever the production machine says; a test that wants "repair suspended" cannot say so without mutating the production policy file. That makes the Guardian's own suite **non-hermetic** — it depends on the host's global state.

**This is finding P-3, and it is more than a by-product of M-2.** Root-awareness must be a **precondition of Step 1**, because:

- the G06 update in Step 5 depends on it;
- T-13 (suspension) depends on it;
- T-18 (nudge suppression) depends on it;
- and until it is fixed, **no test of the repair path can be trusted to be testing the intended behaviour rather than the machine's current policy**.

**Recommended:** make root-awareness an explicit, separately-testable increment at the **start of Step 1**, not inside Step 3.

### 5.2 Does the proposed G06 change fix the environment without weakening the assertions?

**Yes.** The two original assertions are **retained verbatim**:

| Original assertion | Retained? |
|---|---|
| `assertTrue(applied, "the mechanical repair was not applied")` | ✔ |
| `assertTrue(any(r.module for r in cycle.test_runs))` | ✔ |
| `assertGreater(len(cycle.test_runs), 1)` | ✔ |
| `assertFalse(target.read_text(...).endswith("   \n"))` | ✔ |
| `assertEqual(target.read_text(...), before)` (the second method) | ✔ |

**No assertion is removed, weakened, skipped or made conditional.** The change is **environmental**: the test writes a `repair-policy.json` into its own `self.root` enabling repair, instead of inheriting the machine's global state.

**This is a strict improvement in test hygiene.** The current suite's dependence on the host's global suspension state is a latent defect: with the suspension lifted, G06 would pass for the wrong reason; with it applied, G06 fails for the wrong reason. The per-test policy makes the suite **hermetic** — the correct property for a test suite.

### 5.3 Why 30 → 32, and what the two new tests are

The current suite has **30 test methods** across **12 classes** — verified by parsing `test_guardian.py`, not estimated. G06 currently has **2** methods; the proposal has **4**.

| # | New test | Asserts |
|---|---|---|
| **G06-3** | `test_the_suspension_blocks_the_repair_and_the_cycle_still_completes` | the repair was **not** applied; the target is byte-identical; `cycle.changed_files` is non-empty (**detection operational**); a `repair-capability` check exists with `REPAIR_SUSPENDED` in its detail; `cycle.result.worst` is not `PASS`; the test runs were still executed (**tests operational**) |
| **G06-4** | `test_the_report_is_produced_under_suspension` | `guardian.finalize(cycle, self.root)` writes a report; the payload carries the `REPAIR_SUSPENDED` marker (**report operational**) |

**30 + 2 = 32.** The count is derived, not asserted.

### 5.4 Do the 32 represent genuinely superior coverage?

**Yes, on four axes:** the number of assertions, the number of distinct states exercised, the hermeticity of the suite, and the coverage of the suspension path.

| Axis | 30 today | 32 proposed |
|---|---|---|
| Repair path exercised | only when the host's global policy allows it | **always**, in an isolated tree with an explicit policy |
| Suspension path exercised | **not at all** | **twice** (G06-3, G06-4) |
| Detection asserted under suspension | no | yes (G06-3) |
| Report asserted under suspension | no | yes (G06-4) |
| Host-state dependence | **yes** — the suite's result depends on the machine | **none** — every test states its own policy |

**One caveat.** The 32 figure covers the **G06 update only**. The T-matrix of §4 specifies **23** adversarial tests, of which the current suite implements a subset. Once M-1 to M-4 land and the T-matrix is implemented, the count will be **substantially higher than 32**. Any document stating "32" as the final target would be wrong by the time the work completes.

### 5.5 How to guarantee 32/32 without false positives

| Risk | Mitigation |
|---|---|
| A test that passes because the repair did **not** happen, for the wrong reason | G06-3 must assert the *reason* (`REPAIR_SUSPENDED`), not merely that no write occurred — a failed write and a refused write look the same from the filesystem |
| A test that passes because the cycle **aborted** | G06-3 must assert the cycle **completed** (the report exists, the test runs are non-empty) — an aborted cycle produces neither |
| A test that passes vacuously | Every new assertion must be on a **value** the implementation produces, not on the absence of an exception |
| The count becoming a target that invites weakening | The acceptance criterion must be phrased as *"every test passes, with no test removed or weakened"* — the count is an output, not a target |

**No test is currently ignored, skipped or marked expected-failure.** Verified: the suite has no `@unittest.skip`, no `skipTest`, and no expected-failure markers.

---

## 6. Decision matrix D-1 to D-10

*Secção 6 — Matriz D-1 a D-10.*

| # | Original question | Technical recommendation | Justification | If accepted | If rejected | Depends on | Authorisation |
|---|---|---|---|---|---|---|---|
| **D-1** | Authorise the implementation of M-1 to M-4? | **Remain pending.** No authorisation is implied by this review | The task is explicitly read-only; a specification cannot authorise itself | Steps 1–5 become executable | Nothing is implemented; the Guardian stays detection-only | — | **OWNER ONLY** |
| **D-2** | Confirm the suspension stays in force through Steps 1–5? | **Keep suspended** until every correction and test is validated | A partially-implemented write path is more dangerous than no write path | The write path is exercised only in isolated trees; the production tree is never a target | The production path stays inert, but the remediation cannot be validated end-to-end | D-1 | **OWNER ONLY** |
| **D-3** | Is an unlisted file a defect or an observation? | **Observation only** — recorded, never affecting the verdict; scope it to the manifest-covered prefixes with a declared exemption list | The manifest does not list the Guardian's own tree or its reports; a naive "tree minus manifest" reports ~5 legitimate files (P-2) | No false `FAIL` from the Guardian's own artefacts | The plan cannot be implemented as written; a false `FAIL` on every cycle is introduced | — | Technical, with owner awareness |
| **D-4** | Is a structurally incomplete manifest row `FAIL` or `NOT_VERIFIED`? | **`FAIL`**, with the row named in `evidence.invalid_entries` | A malformed row is a defect **in the manifest**, not an inability to verify. `NOT_VERIFIED` would mean "the check could not run" — but the check did run and found a bad row. The same reasoning applies to T-05's duplicate | The manifest's own integrity is asserted, closing the F-02 class completely | A corrupt manifest row could pass as "not verifiable" | — | Technical |
| **D-5** | Is an unavailable search root `BLOCKED` or `FAIL`? | **`BLOCKED`**, with the root named | The two facts are different: the file is missing vs. the place to look for it is unavailable. `BLOCKED` is the existing verdict for exactly this meaning. On another host without the Desktop layout, `FAIL` would produce 13 false failures | The check is portable and honest about *why* | A missing root would be reported as a missing file — indistinguishable from a deleted artefact | — | Technical |
| **D-6** | Are M-7 (backup) and M-8 (fsync) deferred? | **Defer both**, and record the residual risk explicitly | M-1…M-4's texts do not mention a backup or durability. Expanding M-2's scope to include them would violate the brief's scope discipline | The write path has no durable backup and no `fsync`; a power loss could leave a replaced file with unflushed content | The write path gains a verifiable backup and durable writes, at the cost of scope and complexity | — | **OWNER — scope boundary** |
| **D-7** | Is M-9 dropped as redundant after M-1? | **Drop M-9 as a separate change**, and record the corrected figure | **Demonstrated:** the manifest lists 32 package files (15 under `tests/`). M-1, asserting over the expected rows, covers all 32 for absence. M-9's own figure (19) is wrong — the true count outside `tests/` is **17**. `_check_tests_preserved` cannot detect a test file deleted *before* a cycle; M-1 can | One change covers what two would | A redundant second change, with an incorrect count, is implemented | M-1 | Technical, with owner awareness |
| **D-8** | Define the suite count and the approval criterion | **Criterion:** *"every test passes, with no test removed, skipped, or weakened."* Count: **32** for the G06 update alone, and **higher** once the T-matrix is implemented — the number is an output, not a target | A fixed number invites weakening to reach it. The current 30 is a count of methods, verified by parsing | A criterion no implementation can game | A count becomes a proxy for quality | — | Technical |
| **D-9** | The `copy.py` divergence | **Keep it explicitly documented; do not touch the file and do not change the baseline** | The original bytes are not recoverable on this machine (searched: every loose file, 19 ZIPs' every member, 14 971 `state.db` messages — all by exact SHA-256). The reconstruction is functionally equivalent (17/17 contract tests, 214/214 suite) but is **not** the delivered artefact | The divergence stays visible on every cycle as a `WARNING`; the manifest keeps the original hash; the addendum remains the record | The reconstruction stays unaccepted, and the Guardian keeps reporting a known divergence | — | **OWNER ONLY** |
| **D-10** | The scope of the Telegram policy | **Two distinct mechanisms, explicitly separated.** **(a) Notification of completion** — a task or verification ended and needs a decision, authorisation, or review: one message per event, with a dedupe key so the same unchanged incident is not repeated. **(b) Operational alerting** — a *continuous* mechanism that watches for critical failures: a **different** channel, a **different** trigger, and an explicit opt-in, because it is a monitoring service rather than a completion notice | The audit's F-07 is about the **absence of the policy**. M-5's text covers "notify on a human decision, a block, an integrity divergence, a safety refusal, or a critical failure" — which spans two mechanisms with very different semantics. Conflating them would mean either spamming the owner or under-reporting a critical failure | The owner is informed of decisions and critical failures, without a continuous alert service | The Guardian stays silent; a critical failure at 3 a.m. is recorded and unnoticed | — | **OWNER — scope boundary** |

### 6.1 Technical decisions versus owner decisions

| Category | Decisions |
|---|---|
| **Technical** — settle by following the recommendation; no owner judgement required | D-3, D-4, D-5, D-7, D-8 |
| **Scope boundaries** — require an explicit statement of what is *not* being done | D-6, D-10 |
| **Owner only** — cannot be inferred from any evidence | **D-1, D-2, D-9** |

---

## 7. Residual risks

*Secção 7 — Riscos residuais.*

| Risk | Severity | Probability | Impact | Current exposure | Temporary mitigation | Future approval needed |
|---|---|---|---|---|---|---|
| **F-07** — the Telegram policy is not implemented; the Guardian is silent | MEDIUM | **Certain** — it is absent | A critical failure is recorded and unnoticed | The report is written; nobody is told | The owner reviews the reports at each phase boundary | **Yes** — M-5 / D-10 |
| **F-08** — `module_for_path` returns `""` for a project-relative path | LOW | Low — the runtime passes absolute paths | A silent test-selection gap if a caller passes relative paths | Latent, not active | The function is called from one place, with an absolute path | No — no remediation assigned |
| **M-7** — no verifiable backup of the original before a write | MEDIUM | Low — requires an interrupted write | A lost artefact with no recovery path beyond the manifest hash | The write is atomic; the original is not preserved separately | The write path is fail-closed under M-2, and the suspension is in force | **Yes** — D-6 |
| **M-8** — no `fsync`; the temporary is not validated before the rename; not cleaned up on failure | LOW | Low — requires a power loss | A replaced file could hold unflushed content; a stray `.guardian-tmp` could accumulate | The replacement is atomic; the temporary is in the same directory | The suspension is in force | **Yes** — D-6 |
| **R-6 / M-6** — concurrent cycles can interleave; `save_state` has no lock | MEDIUM | Medium — two hooks firing together is plausible | The last writer wins; one cycle's baseline can overwrite another's | The write is atomic; the baseline write is atomic | The suspension is in force; T-28 would document the behaviour | **Yes** — M-6 |
| **M-9** — the absence check for the 17 package files | — | — | — | **Covered by M-1** | — | **No** — redundant (D-7) |
| **M-13** — the Guardian is not read-only by default | LOW now | — | — | The **current suspension is a temporary form of exactly this** | In force | Yes — future |
| **M-14** — symlink and hard-link behaviour unproven | LOW | Low | A protection bypass on an exotic path | M-4's resolution and hash anchor mitigate it | The suspension is in force | Yes — future |
| **X-1** — the N1 transformation is not token-aware | MEDIUM | **Certain** — it is the current behaviour | A repair can alter string-literal content | The Guardian's own N1 scope is only trailing whitespace and the final newline; a file with trailing whitespace inside a literal would be altered | The suspension is in force | **Yes** — within M-2's "only by the intended transformation" clause |

---

## 8. Final implementation plan

*Secção 8 — Plano de implementação.*

Seven steps, each independently verifiable and independently revertible. **This is a plan; nothing has been executed.**

```
P-3 (root-awareness) ──► Step 1 ──► Step 2 ──► Step 3 ──► Step 4 ──► Step 5 ──► Step 6
   (prerequisite)          (M-1)     (M-4)     (M-2)     (M-3)    (tests)   (validation)
                                                                   │
                                                                   └─► Step 7 (owner only)
```

### Step 0 — root-awareness (P-3) — the prerequisite

| | |
|---|---|
| **Pre-conditions** | Owner authorisation (D-1). Suspension in force. |
| **Files** | `quality_guardian/repair.py::write_file_text`; `quality_guardian/config.py::auto_repair_enabled` (already accepts `root`) |
| **Change** | `write_file_text` consults `config.auto_repair_enabled(root)`; the `root` parameter is added and threaded from `_attempt_repairs`. |
| **Tests before** | G06 errors (the current symptom) |
| **Tests after** | the existing G06 passes **because** the isolated tree's own (absent) policy governs; a new hermeticity assertion proves the production policy is not consulted |
| **Completion** | the Guardian suite is green **without** the production policy being consulted; `last-seen.json` and the production policy are unchanged by the suite |
| **Risk** | a caller that omits `root` would fall back to the production root — the default must be **explicit**, not implicit |
| **Rollback** | revert `write_file_text` |

### Step 1 — M-1: the manifest check's verdict

| | |
|---|---|
| **Pre-conditions** | Step 0 complete |
| **Files** | `quality_guardian/guardian.py::_check_manifest_integrity` only |
| **Change** | the six-state accounting (expected / found / missing / additional / divergent / invalid); the **table-scoped** parsing (P-1); the `missing` → `FAIL` rule; the unparseable manifest → `NOT_VERIFIED`; the unavailable root → `BLOCKED`; the unreadable file → `BLOCKED` |
| **Tests before** | T-01, T-03, T-04, T-08 (currently producing `PASS`) |
| **Tests after** | T-01…T-08, T-24, T-29, plus P03/P06/P08 unchanged |
| **Completion** | AC-1…AC-5; the real manifest still yields `WARNING` for the known `copy.py` divergence |
| **Risk** | the P-1 false-`FAIL` if the parsing is not table-scoped; the P-2 noise if "additional" is unscoped |
| **Rollback** | revert the one function |

### Step 2 — M-4: identity-based protection

| | |
|---|---|
| **Pre-conditions** | Step 1 complete — the manifest's row set is now trustworthy |
| **Files** | `quality_guardian/config.py` — `is_manifest_protected`, `is_protected`, a new `manifest_protection_for`; `quality_guardian/repair.py::apply_level1_fixes_in_project` |
| **Change** | resolve before comparing; build the protected set from the manifest with the prefix set as fallback; the hash clause stated so a **renamed** protected file stays protected; the collision rule between the two search roots recorded in the evidence |
| **Tests before** | T-21 (currently failing on the case variant) |
| **Tests after** | T-20, T-21, T-22, T-23, T-25, plus P01/P02/P09/P10 unchanged |
| **Completion** | AC-15, AC-16 |
| **Risk** | over-broad protection blocking legitimate repairs — T-22 is the counter-test |
| **Rollback** | revert `config.py` and `apply_level1_fixes_in_project` |

### Step 3 — M-2: artefact-identity validation

| | |
|---|---|
| **Pre-conditions** | Step 2 complete — the hash check is shared and must be implemented once |
| **Files** | `quality_guardian/repair.py` — `write_file_text`, a new `validate_repair`, the transformation; `quality_guardian/guardian.py::_attempt_repairs` (both call sites) |
| **Change** | V1 hash revalidation **inside the write choke point**; V2 compile; V3 transformation fidelity; V4 parse; the **token-aware** transformation (X-1); the explicit revert exemption in the API (X-2); the `expected_hash` and `root` parameters |
| **Tests before** | T-09, T-10, T-11, T-12 (currently escaping or unsupported) |
| **Tests after** | T-09…T-14, T-26, T-30, plus P01/P02 unchanged |
| **Completion** | AC-6…AC-10 |
| **Risk** | false refusals on files that were already invalid — the refusal reason must distinguish; a revert refused by V3 — the exemption must be explicit |
| **Rollback** | revert `repair.py` and the two call sites |

### Step 4 — M-3: the suspension as a controlled state

| | |
|---|---|
| **Pre-conditions** | Step 3 complete — M-2 changes the write path M-3 makes safe to interrupt |
| **Files** | `quality_guardian/repair.py` — the refusal signal and the structured result; `quality_guardian/guardian.py::_attempt_repairs`, `run_cycle`; `quality_guardian/hook.py` — the nudge decision; `quality_guardian/cli.py` — a top-level guard |
| **Change** | the raise becomes a structured refusal with machine-checkable reasons; the two suspension branches unified into one; the `REPAIR_SUSPENDED` state; the **source-scoped** nudge exclusion (§3.3.3); the CLI guard |
| **Tests before** | the current G06 error; T-13…T-19 (unsupported today) |
| **Tests after** | T-13…T-19 |
| **Completion** | AC-11…AC-14 |
| **Risk** | a real fault misreported as a policy refusal — mitigated by the distinct reason prefixes |
| **Rollback** | revert the return shape and the call site; the suspension stays in force |

### Step 5 — the G06 update and the full test implementation

| | |
|---|---|
| **Pre-conditions** | Step 4 complete |
| **Files** | `quality_guardian/tests/test_guardian.py::G06ReRunTest`; new test modules for the T-matrix |
| **Change** | the G06 update of §5; the T-matrix tests T-01…T-30 |
| **Tests before** | 29/30 with one error |
| **Tests after** | every test passes, with no test removed, skipped or weakened |
| **Completion** | AC-17…AC-21 |
| **Risk** | a test that depends on the host's global state — eliminated by Step 0 and the per-test policy |
| **Rollback** | revert the test files |

### Step 6 — independent final validation

| | |
|---|---|
| **Pre-conditions** | Step 5 complete |
| **Files** | **none** — validation only |
| **Change** | a full re-run of both suites; a hash comparison of the manifest, the addendum, `copy.py`, the configuration, the allowlist and the policy file; a re-derivation of the 52-file matrix; a fresh read of the write path to confirm there is still exactly one entry point |
| **Completion** | AC-17…AC-22 |
| **Risk** | none — read-only |
| **Rollback** | not applicable |

### Step 7 — reactivation (OWNER ONLY, a separate decision)

| | |
|---|---|
| **Pre-conditions** | Steps 0–6 complete **and** Step 6's validation passed |
| **Files** | `quality_guardian/state/repair-policy.json` — **one field** |
| **Change** | `auto_repair: false` → `true`, with the authorisation recorded |
| **Completion** | the owner's explicit confirmation |
| **Risk** | reactivating before validation — the sequence prevents it |
| **Rollback** | set `auto_repair` back to `false` |

**Reactivation is never a consequence of passing tests.** Step 7 requires a separate, explicit decision, recorded with the authorisation that granted it.

### 8.1 Dependencies and the recommended order

**Step 0 → Step 1 → Step 2 → Step 3 → Step 4 → Step 5 → Step 6 → Step 7.**

- **Step 0 first** because the suite cannot be trusted to test the intended behaviour until it is hermetic (P-3).
- **Step 1 before Step 2** because M-4 builds the protected set from the manifest, and M-1 is what makes that set trustworthy.
- **Step 2 before Step 3** because they share the write-time hash check and must be implemented **once**.
- **Step 3 before Step 4** because M-4 changes the write path M-3 makes safe to interrupt.
- **Step 4 before Step 5** because the G06 update tests M-3's behaviour.
- **Step 6 after Step 5** and **Step 7 after Step 6**: validation, then a separate decision.

---

## 9. Acceptance criteria

*Secção 9 — Critérios de aceitação.*

Unchanged from the plan (§7) with the four corrections of this review applied. All 22 must hold.

| Group | Criteria | Verified by |
|---|---|---|
| **Integrity of protected files** | AC-1…AC-5 — a missing protected file never yields `PASS`; an unparseable manifest never yields `PASS`; an invalid or duplicate row is detected; an unavailable root is distinguished from a missing file; the known `copy.py` divergence still yields `WARNING` | T-01…T-08, T-24, T-29 |
| **Repair safety** | AC-6…AC-10 — a same-size invalid candidate is refused; a semantic change is refused; a file changed between read and write is not overwritten; a write without a pre-write hash is refused; the revert path restores the original | T-09…T-12, T-26, T-30 |
| **The suspension as a state** | AC-11…AC-14 — it is reported, never an uncaught exception; every cycle writes its report; both hooks exit 0; `pre_verify` emits no `continue` | T-13…T-19 |
| **Identity-based protection** | AC-15…AC-16 — case, traversal and hash-anchored; a renamed protected file stays protected; ordinary files remain repairable | T-20…T-23, T-25 |
| **Preservation** | AC-17…AC-22 — the Phase 2A suite stays 214/214; the Guardian suite passes in full with nothing removed or weakened; the manifest, the addendum and `copy.py` are byte-identical; the configuration and the allowlist are unchanged; the write path still has exactly one entry point; the suspension holds until Step 7 | the suites; hash comparison; inspection |

---

## 10. Rollback

*Secção 10 — Rollback.*

**The suspension is the master rollback.** Setting `auto_repair: false` stops every project-source write immediately, whatever state the code is in.

| Situation | Action | Effect |
|---|---|---|
| A step's tests fail | revert that step's files | the suspension remains in force |
| The suite fails after a step | revert that step, re-run the suite | the prior state is restored |
| A protected file is modified | **stop immediately**; set `auto_repair: false`; restore from the manifest's recorded hash by re-deriving it from the Phase 2A delivery; record the event | the Guardian returns to detection-only |
| The write path misbehaves in production | set `auto_repair: false` | all writes stop; detection continues |
| A wholesale rollback is needed | restore `quality_guardian/` from `…\scratch\qg-pre-suspension-20261108-124516`, verified against `BACKUP-SHA256.json` | the exact post-audit state |

**Never rolled back, because never modified:** the manifest, the addendum A-1, `copy.py`, the 51 matching entries, `config.yaml`, the allowlist.

---

## 11. Final decisions pending from the owner

*Secção 11 — Decisões finais pendentes do utilizador.*

| # | Decision | Status |
|---|---|---|
| **D-1** | Authorise the implementation of Steps 0–5, in that order | **OWNER ONLY — pending** |
| **D-2** | Confirm the suspension holds through Steps 0–6, with reactivation as a separate decision at Step 7 | **OWNER ONLY — pending** |
| **D-3** | Unlisted files: observation only, scoped to the manifest-covered prefixes with a declared exemption list | Technical — recommendation stated |
| **D-4** | An incomplete or duplicate manifest row: `FAIL`, named in `evidence.invalid_entries` | Technical — recommendation stated |
| **D-5** | An unavailable search root: `BLOCKED`, with the root named | Technical — recommendation stated |
| **D-6** | M-7 (backup) and M-8 (fsync) deferred, with the residual risk recorded | **Scope boundary — owner statement needed** |
| **D-7** | M-9 dropped as redundant; the corrected figure is **17**, not 19 | Technical — recommendation stated, with the demonstration |
| **D-8** | The acceptance criterion: *"every test passes, with no test removed, skipped or weakened"*; the count is an output, not a target | Technical — recommendation stated |
| **D-9** | `copy.py`: the divergence stays explicitly documented; the file and the baseline are untouched | **OWNER ONLY — pending** |
| **D-10** | Telegram: completion-notification and operational alerting are **two separate mechanisms**, with separate triggers, channels and opt-in | **Scope boundary — owner statement needed** |

**Three further items require the owner's attention before implementation begins:**

| # | Item |
|---|---|
| **A-1** | The four plan corrections of this review — **P-1** (table-scoped manifest parsing), **P-2** (the scope of "additional"), **P-3** (root-awareness as Step 0), **P-4** (an injected rather than a provoked report failure) — must be incorporated into the plan before Step 1 |
| **A-2** | The six additional scenarios — **T-24…T-30** — should be added to the matrix. T-30 (the rollback path) is the most important: it is the only path that restores content, and it is currently untested |
| **A-3** | **X-1**, the token-awareness of the N1 transformation, must be decided within M-2. It is a pre-existing defect, and M-2's "only by the intended transformation" clause is the natural place to bound it |

---

## 12. Classification

# READY FOR OWNER DECISION

**Why this classification.** Every recommendation was traced to its original text; every affected function was read in the installed source; every proposed test was checked for isolation and for its ability to detect a false `PASS`; and the plan's own defects were found by inspecting the **real** manifest and the **real** code — not by re-reading the plan. The four corrections (P-1 to P-4) and six additional tests (T-24 to T-30) make the plan implementable without a false `FAIL` against the real manifest and without a test suite that depends on the host's global state.

**Why not `READY WITH OPEN QUESTIONS`.** There is no unresolved technical question. The three owner-only decisions (D-1, D-2, D-9) are **decisions**, not questions: D-1 asks for an authorisation, D-2 confirms a recommended posture, and D-9 concerns a historical fact that no evidence can settle. The five technical decisions carry a recommendation that can simply be followed.

**Why not `BLOCKED`.** Nothing prevents the work. The write surface is a single function, the dependencies are mapped, the tests are specified, and every step has a rollback.

**This document is a review and a decision proposal.** M-1 to M-4 have **not** been implemented. The automatic repair **remains suspended**. The Phase 2A manifest, the addendum A-1 and `copy.py` are **byte-identical** to their state at the start of this task.

---

*End of the final decision review. Read-only throughout: no code, test, configuration, hook, allowlist, manifest, baseline or protected artefact was modified.*
