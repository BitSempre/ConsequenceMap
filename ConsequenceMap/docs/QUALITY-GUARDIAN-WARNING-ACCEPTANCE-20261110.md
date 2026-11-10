# Quality Guardian — WARNING Acceptance

**Date:** 2026-11-10
**Owner:** Souza
**Scope:** the `WARNING` verdict of the Quality Guardian's final verification cycle
**Status:** ACCEPTED — with one correction applied before acceptance (see §3)

---

## 1. What was accepted

The Quality Guardian's verification cycle closed with the verdict
`WARNING`. It is accepted as the correct verdict for the delivered
state. The verdict is **not** a pass, and this document does not
present it as one.

## 2. What the WARNING is, precisely

Exactly one check produced the `WARNING`:

| Check | Verdict | Detail |
|---|---|---|
| `hermes-runtime-compatibility` | PASS | installed 0.23.0 vs required >= 0.22.5 |
| `production-stdlib-only` | PASS | `PRODUCTION_DEPENDENCIES` is empty, no `pyproject.toml` |
| `tests:test_static_audits` | PASS | 9 test(s) passed |
| `tests:test_import_audits` | PASS | 10 test(s) passed |
| `formatting-hygiene` | PASS | no trailing-whitespace or final-newline defect |
| **`phase-2a-manifest-integrity`** | **WARNING** | 3 manifest divergence(s), all documented in an addendum |
| `tests-preserved` | PASS | no test file was removed |
| `state-comparison` | PASS | 0 file(s) differ from the pre-cycle state |

The three divergences are:

- `consequence_map/__init__.py`
- `consequence_map/domain/copy.py`
- `consequence_map/storage/schema.py`

Each is named in a Phase 2A manifest addendum (`A-1`, `A-2`, `A-3`).
A divergence recorded in an addendum is, by the Guardian's own
definition, **a known and recorded state — not a new regression**. An
*undocumented* divergence is a `FAIL`; there are none.

The Guardian recorded `repairs: []`, `repair_attempts: 0` and
`unresolved: []`. No repair was proposed for application, and none was
applied.

## 3. The correction applied before acceptance

The final independent verification — run outside the Guardian's own
selective test map — found a **real regression** that the Guardian had
not detected: five failures in `consequence_map/tests/test_phase2b.py`.

The cause was a change to the hook path in `consequence_map/hooks.py`
that passed a keyword argument the correlator's `note_response()` does
not accept, raising `TypeError` on every approval response. The
Guardian did not see it because its module-to-test map covers the
Phase 2A modules; the Phase 2B modules (`hooks`, `correlation`,
`authorization`, `lifecycle`, `paths`, `self_exclusion`) are not in it,
so a change to `hooks.py` selected only the two always-on cross-cutting
audits.

That change was reverted, and the regression test that was supposed to
catch it was rewritten. The old test asserted that the **source text**
of the hook contained the word "pending" — a textual proxy that the
broken change satisfied while the runtime was broken. The replacement
asserts the **behaviour**: with two escalations in flight for the same
tool call, the hook path records no approval and counts the ambiguity.

The rewritten test was verified to have teeth by two defect injections
in isolated copies:

| Injected defect | `test_independent_review` | `test_phase2b` |
|---|---|---|
| the unsupported keyword argument | 2 errors | 5 errors |
| the EC-7 forwarding removed from `Correlator.note_response` | **1 failure** | **0 — not detected** |

The second row is the more important one: the pre-existing Phase 2B
suite does **not** cover the EC-7 ambiguity check on the hook path.
The new test does.

## 4. Why the WARNING is accepted rather than eliminated

The divergences are documented in the addenda that already exist for
them. Removing them would mean rewriting files the Phase 2A manifest
hashes — which would invalidate the delivered phase's baseline for a
cosmetic reason. The Guardian's own mechanism already draws the
distinction that matters: a recorded divergence is a `WARNING`, an
unrecorded one is a `FAIL`.

The owner authorised no new functional corrections and no cosmetic
documentation changes for the purpose of clearing the `WARNING`. None
were made.

## 5. What this acceptance does NOT authorise

- It is **not** approval for production. The Security Guard remains
  `NOT READY FOR PRODUCTION`: no service is installed, no ACL is
  applied, no external anchor exists.
- It does not lift any authorisation block. The plugin is not
  installed; the service identity certificate is not installed.
- It does not re-enable automatic repair. `auto_repair` remains
  `false`, SHA-256
  `52f60c0afb16746a54c32a31b96c53f64eaa48ff074641966ec610f5c6c3b129`
  — byte-identical to the policy in force since 2026-11-08.
- It does not change the Guardian's coverage. The module-to-test map
  still omits the Phase 2B modules, so a change to `hooks.py` alone
  will again select only the cross-cutting audits. The full-suite
  run remains the only complete check.

## 6. Evidence preserved

| Artefact | Location |
|---|---|
| Guardian reports (JSON + Markdown) | `quality_guardian/reports/` |
| Repair policy | `quality_guardian/state/repair-policy.json` |
| Recorded baseline | `quality_guardian/state/last-seen.json` |
| Independent-review suite | `consequence_map/tests/test_independent_review.py` |
| Closing report | `docs/QUALITY-GUARDIAN-CLOSING-REPORT-20261110.md` |

---

**Verdict:** `WARNING` — accepted. **Unresolved:** none.
**Production readiness:** unchanged — `NOT READY FOR PRODUCTION`.
