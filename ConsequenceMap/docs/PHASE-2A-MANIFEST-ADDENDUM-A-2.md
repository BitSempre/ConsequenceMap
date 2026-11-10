# ConsequenceMap — Phase 2A manifest addendum A-2

**Date:** 2026-11-10
**Subject:** One file changed under Phase 2B — `consequence_map/__init__.py`.
The addendum also names `consequence_map/domain/copy.py`, whose divergence
is the one recorded in A-1 and was **not** changed under Phase 2B.
**Status:** Both changes are deliberate, minimal and behaviour-preserving for
every Phase 2A criterion. The recorded hashes are deliberately not
overwritten.

## Why this addendum exists

The Phase 2A manifest is the audit trail of a delivered phase. Its hashes
are not rewritten when a later phase legitimately changes a file: they are
left standing and the change is recorded here, so a reader can see both
what was delivered and what changed afterwards.

The Quality Guardian already treats this case correctly. A divergence
recorded in an addendum is reported as a **WARNING** — a known, recorded
state — and an unrecorded one as a **FAIL**. This addendum is what moves
the files below from the second category to the first.

## `consequence_map/__init__.py`

**Manifest hash:** `c5b92176fa8b70da9ad48ecca5d84cac5425effb71dd6e63aeae02c2f234b68d`
**Current hash:** `b0e8d5482de8d31b554d94158bf411373b52bf89137e7286908e82c68c2b6e78`
**Current size:** 542 bytes

The only change is the version string and the module docstring:

| | Phase 2A | Phase 2B |
|---|---|---|
| `__version__` | `0.2.0-phase2a` | `0.3.0-phase2b` |
| docstring | "Phase 2A: domain model and storage layer." | "Phase 2B: runtime integration." plus a paragraph naming the five new modules |

`SCHEMA_VERSION = 1` is **unchanged**: the storage schema did not change,
so the database a Phase 2A deployment already has remains valid.

No public symbol was added, removed or renamed. Every import that worked
before still works.

## `consequence_map/domain/copy.py`

**Manifest hash:** `bd09d066c036e43a974555ad6624026e96410d359b10f00b35a7350b20f9ba5a`
**Current hash:** `765037914b353d18d904a657954b260a1f656c4ef4433052f1708f544fa55743`

**This file was NOT changed under Phase 2B.** Its divergence is the one
already recorded in addendum **A-1**, which documented that the original
bytes were lost to a truncation bug in the *verification script* and were
reconstructed with identical behaviour. The current hash is the
reconstructed one, and it has been stable since A-1.

A-1 is the addendum that documents this file. This addendum names it as
well so that the Guardian's check finds the path in a single place; the
substantive record is A-1, not this one.

**What Phase 2B actually did** was call the existing lint from the write
path, in `consequence_map/lifecycle.py::Lifecycle.record_forecast`. The
lint itself was not modified: the prohibited vocabulary, the matching
rules, the case-insensitivity and the behaviour of every existing caller
are exactly as Phase 2A left them, and the Phase 2A test that exercises
the lint still passes unchanged.

## What was NOT touched

Nothing else covered by the Phase 2A manifest changed. In particular:

- `storage/schema.py`, `storage/triggers.py`, `storage/db.py` and
  `storage/migrations.py` — **byte-identical**. The 45-trigger family, the
  composite foreign keys and the journal-mode settings are untouched.
- `domain/enums.py`, `domain/validation.py`, `domain/serialization.py` —
  **byte-identical**. The eighteen enumerations, the closed sets and the
  validation rules are untouched.
- `redaction/boundary.py` — **byte-identical**.
- `domain/records.py` — **byte-identical**. The fifteen record types are
  untouched; Phase 2B added a module that *uses* them.

## The new files

The following are **new** and therefore absent from the Phase 2A manifest
by construction. They carry their own Phase 2B manifest.

| File | Purpose |
|---|---|
| `consequence_map/hooks.py` | the five hook callbacks |
| `consequence_map/correlation.py` | attribution and the eight edge cases |
| `consequence_map/authorization.py` | the thirteen-state machine |
| `consequence_map/paths.py` | path resolution and containment |
| `consequence_map/self_exclusion.py` | RECUR-1 through RECUR-9 |
| `consequence_map/lifecycle.py` | forecast to decision to execution to outcome |
