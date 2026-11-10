# ConsequenceMap — Closing Report

**Date:** 2026-11-10
**Branch:** `feature/platform-v1` · **HEAD:** `c1f4e2c` · 56 commits
**Scope:** the closing verification of the Phase 2B delivery and the six
independent-review decisions (F1–F6)

---

## 1. The verdict, stated without euphemism

| | |
|---|---|
| **Guardian verdict** | **WARNING** — accepted, 0 FAIL, 0 unresolved |
| **Independent verification** | **PASS** — 716 tests, 0 failures |
| **Automatic repair** | **suspended** (`auto_repair: false`), unchanged |
| **Production readiness** | **NOT READY FOR PRODUCTION** — unchanged |

The `WARNING` is the Guardian's verdict on the *Phase 2A manifest*: three
files that the delivered manifest hashes have since changed, each named
in an addendum. It is a recorded state, not a regression. Its grounds
are in `QUALITY-GUARDIAN-WARNING-ACCEPTANCE-20261110.md`.

The independent verification is stronger than the Guardian's own cycle,
and it is where the one real defect of this session was found. Both
verdicts are reported; neither is presented as the other.

## 2. What the independent verification found

Running the suites directly — outside the Guardian's selective test
map — produced **5 failures** in `consequence_map/tests/test_phase2b.py`:

```
TypeError: Correlator.note_response() got an unexpected keyword
argument 'pending_forecasts'
```

The hook path passed a keyword the correlator does not accept, so
every approval response raised. The Guardian had reported `WARNING`
without seeing it, because its module-to-test map covers the Phase 2A
modules and not the Phase 2B ones; a change to `hooks.py` selected only
the two always-on cross-cutting audits (19 tests).

**Root cause.** Two changes had been made to the EC-7 fix: one in
`consequence_map/correlation.py` — where `note_response()` already
forwards `pending_forecasts` to `attribute()`, and the check lives —
and one in `consequence_map/hooks.py`, which passed the argument again
from the outside, through a signature that does not accept it.

**The correction.** The `hooks.py` change was reverted; the correlator
was left untouched. The EC-7 check was always reachable on the hook
path — the second change added nothing but the exception.

**The test.** The regression test was asserting that the *source text*
of the hook contained the word "pending". A textual proxy the broken
change satisfied while the runtime was broken. It was replaced by a
behavioural assertion: two escalations in flight for the same tool call
must record no approval, and the ambiguity must be counted. A companion
test asserts the converse — an unambiguous answer is still recorded.

## 3. The test that now has teeth

Two defect injections into isolated copies, each run against the
suites:

| Injected defect | `test_independent_review` | `test_phase2b` |
|---|---|---|
| unsupported keyword argument in `hooks.py` | 2 errors | 5 errors |
| EC-7 forwarding removed from `note_response()` | **1 failure** | **0 — not detected** |

The second row is the finding that matters. The Phase 2B suite has
**no coverage** of the EC-7 ambiguity check on the hook path. A test
that passed while the code was broken is not evidence; the new test
fails when the check is removed.

The same principle is why the Guardian's own `phase-2a-manifest-integrity`
check was left alone: it distinguishes a recorded divergence
(`WARNING`) from an unrecorded one (`FAIL`), and the injection corpus
for it was verified before it was trusted.

## 4. Final verification — every suite, run directly

| Suite | Tests | Result |
|---|---|---|
| `consequence_map/tests` | 549 | **PASS** |
| `consequence_guard/tests` | 134 | **PASS** |
| `host_tests` | 2 | **PASS** |
| `quality_guardian/tests` | 30 | 29 PASS, **1 error** — see below |
| `design/mobile-auth/prototype` | 13 | **PASS** |
| `demo/consequence_map_demo.py` | — | exit 0 |
| **Total** | **716 + demo** | **715 PASS, 1 error** |

### The one error, and why it is not a regression

`quality_guardian.tests.test_guardian.G06ReRunTest.test_the_cycle_re_runs_the_tests_after_a_repair`
raises `RepairSuspended: automatic repair is suspended by the repair
policy`.

The test asserts that the Guardian applies a mechanical repair. The
policy says it must not. The Guardian's repair policy has been
suspended since 2026-11-08, so this test has failed at every commit
since — including the baseline `HEAD` (`c1f4e2c`), verified by
extracting the commit to a clean directory and running it there.

This is the guard working as intended: the `write_file_text()` choke
point refuses the write, and the refusal surfaces as a failure rather
than as a silent success. The test asserts the behaviour that the
policy deliberately disables. It is a conflict between the test and the
policy, not a defect in either — and resolving it means choosing one
of them, which is the owner's decision.

## 5. The six independent-review decisions

Each was checked against the code rather than accepted on authority.

| | Finding | Outcome |
|---|---|---|
| **F1** | the transform hook | **Rejected** — returning `None` *is* the specified behaviour (RECUR-8). The reviewer inverted the rule. A test now pins it, including that the payload is unchanged in content *and* identity. |
| **F2** | the sink was inert | **Confirmed and fixed** — the default sink recorded nothing, so the human's answer never reached the database. The sink now writes through the lifecycle, and the record carries the forecast's own `proposal_id` and `proposal_version`, so the composite foreign key holds. |
| **F3** | the ambiguity check never ran | **Confirmed and fixed** — and the fix was then shown to be misplaced. The check lives in `Correlator.note_response()`, which already forwards the pending forecasts; the hook did not need to, and doing so broke it. The test is now behavioural. |
| **F4** | a rule could be chosen by the caller | **Confirmed and fixed** — a pattern key naming a pending forecast with a *different* rule is refused, and the refusal is counted as an orphan. |
| **F5** | the tool fate | **Rejected** — `AUTOMATICALLY_ALLOWED` authorizes nothing: `is_approval` is False for it. |
| **F6** | the accuracy note was injectable | **Confirmed and fixed** — the note is derived from the observations. `Lifecycle.compare` no longer accepts an `accuracy_note` parameter, so a caller cannot supply it. |

## 6. What changed, and what did not

Three files differ from `HEAD`:

| File | Change |
|---|---|
| `consequence_map/authorization.py` | `AuthorizationRecord` carries `observed_choice`, so the sink records what the human actually chose instead of the pattern key. |
| `consequence_map/hooks.py` | the sink derives `observed_choice` from the record and stamps `created_at` with `now_timestamp()`; the invalid `pending_forecasts` argument is gone. |
| `consequence_map/tests/test_independent_review.py` | the F3 test rewritten as a behavioural proof, plus its converse. Two column indices corrected to the schema's real `COLUMN_ORDER`. |

Line endings were normalised to LF in `authorization.py` (the file had
CRLF; every other file in the package uses LF).

**Unchanged, byte-identical:** the storage layer, the schema, the
triggers, the migrations, the enumerations, the validation rules, the
redaction boundary and `dependencies.py`. `auto_repair` remains
`false`. The Phase 2A manifest hashes of those files still hold.

## 7. The limitations that remain

Stated plainly, because a closing report that hides them is worth
nothing.

1. **The Guardian cannot see the Phase 2B modules.** Its
   module-to-test map covers 13 of the 33 test modules and none of the
   Phase 2B modules. A change to `hooks.py` alone selects only the
   cross-cutting audits. This is exactly how the regression in §2
   reached a `WARNING` verdict unchallenged. The fix is mechanical —
   the map is derivable from the real import graph — but it changes
   what the Guardian selects, so it is a decision, not a correction.

2. **The plugin is not installed.** It is built, and the host's own
   manifest parser accepts it, but installing it changes the global
   Hermes configuration, which requires authorisation.

3. **The Desktop surfaces have not been rendered.** The frontend is
   written against the host's plugin SDK and the backend's four routes
   are tested against the real FastAPI router. Nobody watched the panel
   draw.

4. **The Security Guard is a library, not a service.** Ed25519
   validated against the RFC 8032 vectors, atomic authorisation
   consumption, hash-chained audit, closed protocol — and no service
   installed, no ACL applied, no external anchor. `NOT READY FOR
   PRODUCTION`.

5. **Human presence is not demonstrable on this host.** TPM 1.2 (the
   Windows Hello does not provision), no smart cards, no FIDO2, and
   the agent runs in the interactive session with the ability to click.
   A desktop prompt is not a security boundary.

6. **Path containment is a statement about the analysis, not the
   write.** The path, resolved at the moment of analysis, was inside
   the authorised root. The window between the check and the host's
   write is not closed and is not claimed to be.

7. **DEC-16 is still OPEN.** The grace period is a default (30 s),
   not a decision. The owner deferred the value on 2026-11-07.

8. **The Guardian's own suite has one failing test** — the G06 repair
   test, in conflict with the repair policy (§4). It has failed at
   every commit since the suspension.

## 8. The decisions that remain the owner's

| # | Decision | Why it is not the agent's |
|---|---|---|
| 1 | Extend the Guardian's module-to-test map to the Phase 2B modules | It changes what the Guardian verifies. The derivation is mechanical and available; the policy choice is not. |
| 2 | Resolve the G06 conflict: amend the test, or amend the policy | One of the two must give. The policy was set by the post-incident security audit of 2026-11-08. |
| 3 | Install the plugin certificate and the Windows service identity | Neither can be installed on this host without human interaction. |
| 4 | DEC-16 — the grace-period constant | Deferred by the owner on 2026-11-07. |

## 9. Artefacts

| Artefact | SHA-256 / location |
|---|---|
| `consequence_map/hooks.py` | `76ca18b0cb08f72100503bdde0e335f265c81bf11531fb25180b5f9b0630530e` |
| `consequence_map/authorization.py` | `a8127bc1a7f7f5b123eefba3be8d6f02649e8949e8b9aa8eb8a569b91459f8db` |
| `consequence_map/tests/test_independent_review.py` | `de4487c5fd39c71a1feaef936f1debe137725fab9a9a27afea1a71291b7f0e99` |
| `consequence_map/correlation.py` | `87220b2f67d02618f924a4bd84a1cac474cce14e2293bb4d80a6557f0f54c41c` |
| `quality_guardian/state/repair-policy.json` | `52f60c0afb16746a54c32a31b96c53f64eaa48ff074641966ec610f5c6c3b129` |
| Guardian reports | `quality_guardian/reports/` (JSON + Markdown, every cycle) |
| WARNING acceptance | `docs/QUALITY-GUARDIAN-WARNING-ACCEPTANCE-20261110.md` |

---

**Closing position:** the delivery is verified, the `WARNING` is
accepted on stated grounds, the repair policy is unchanged, and the
production-readiness classification is unchanged.
