# ConsequenceMap — Quality Guardian

The permanent quality layer for the ConsequenceMap project.

| Aspect | Value |
|---|---|
| Entry point (CLI) | `python -m quality_guardian.cli verify` |
| Hook entry point | `quality_guardian/hook.py` |
| Shell-hook wrappers | `~/.hermes/agent-hooks/consequencemap-quality-guardian-*.py` |
| Reports | `quality_guardian/reports/` (JSON + Markdown, newest 100 kept) |
| State | `quality_guardian/state/last-seen.json` |
| Dependencies | **none** — standard library only |
| Network | **never** — no provider is contacted |

## Commands

```bash
cd "C:/Users/Utente/Desktop/ConsequenceMap"

python -m quality_guardian.cli verify            # detect + verify (selective)
python -m quality_guardian.cli verify --full     # force the whole suite
python -m quality_guardian.cli verify --changed consequence_map/domain/records.py
python -m quality_guardian.cli verify --json     # machine-readable payload
python -m quality_guardian.cli status            # the recorded baseline
python -m quality_guardian.cli report            # the latest report path

python -m unittest quality_guardian.tests.test_guardian   # the Guardian's own suite
```

Exit code 0 when the worst verdict is `PASS`, 1 otherwise.

## The automatic mechanism

Two Hermes shell hooks, configured in the active profile's `config.yaml`:

| Event | When | What it does |
|---|---|---|
| `post_tool_call` | after every write tool call | verifies only if the write touched **this** project; runs the **selective** tests |
| `pre_verify` | at the end of the agent's turn | runs the full verification; returns `{"action": "continue", …}` while a hard failure remains |

Both are consented in `~/.hermes/shell-hooks-allowlist.json`. Inspect with
`hermes hooks list` and `hermes hooks doctor`; test with
`hermes hooks test post_tool_call --for-tool write_file`.

## The five verdicts

`PASS` · `FAIL` · `WARNING` · `NOT_VERIFIED` · `BLOCKED`

`NOT_VERIFIED` is never rendered as `PASS`. A module with no tests yields
`NO_TESTS_CONFIGURED`, reported as `NOT_VERIFIED`.

## The three repair levels

| Level | Scope |
|---|---|
| **1 — automatic** | trailing whitespace and final-newline normalisation only |
| **2 — assisted** | logic, integration, regression and architecture problems; the Guardian proposes, an investigator fixes |
| **3 — human only** | security model, approval system, privacy, approved architecture, destructive migrations, integrity risks, unidentified causes, the specification, the criteria, the test files |

The ineligible kinds are refused **in code**, not by configuration.

## The hard limits

Never run an unbounded repair loop (max **3** attempts per cycle). Never
delete a test to make a validation pass. Never weaken a criterion. Never
silently change a specification, a decision or an approved requirement.
Never write outside the project root. Never commit, push, publish or
submit. Never declare success without an executable test. Never apply a
repair that would shrink a file below 50 % of its size.

## The module-to-test map

`config.py` holds the map, derived from the package's real import graph. A
change to a **high-impact** module (`storage/schema.py`, `storage/triggers.py`,
`storage/migrations.py`, `storage/db.py`, `domain/enums.py`,
`domain/validation.py`) forces the full suite. Everything else runs only
the affected modules plus the two always-on cross-cutting audits.

## Files covered by the Phase 2A manifest

The Guardian **reports** a defect in a manifest-covered file but never
rewrites it: the file belongs to a delivered, hashed phase, and a change
would invalidate that baseline. A divergence already recorded in
`docs/PHASE-2A-MANIFEST-ADDENDUM-*.md` is reported as `WARNING`; an
undocumented one is a `FAIL`.
