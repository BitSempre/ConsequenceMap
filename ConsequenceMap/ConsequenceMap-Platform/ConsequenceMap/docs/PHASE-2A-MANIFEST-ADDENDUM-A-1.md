# ConsequenceMap — Phase 2A manifest addendum A-1

**Date:** 2026-11-08
**Subject:** One reconstructed file — `consequence_map/domain/copy.py`
**Status:** Behaviour identical; the recorded hash is deliberately not overwritten.

## What happened

While installing the project-wide Quality Guardian, a bug in the
*verification script* (not in the Guardian) truncated one file before
reading it. The pattern was:

```python
open(path, "w").write(open(path).read() + "\n")
```

Python opens the file for writing first — which truncates it — and only
then evaluates the argument, so the read returned an empty string and the
write left a single newline byte. The affected file was
`consequence_map/domain/copy.py`.

The Guardian did not cause this and did not conceal it: it detected the
resulting manifest divergence on its very next cycle and reported it as
`FAIL`. A second instance of the same bug was caught by the same check.

## Recovery

The original bytes were not recoverable. They exist in no ZIP, no scratch
copy, no Hermes session transcript, no report and nowhere else on this
machine — all were searched by exact SHA-256.

The file was therefore **reconstructed from its contract**:

| Source | What it fixes |
|---|---|
| `consequence_map/tests/test_coverage_gaps.py::TestACData18CopyLint` | the three assertions that define the behaviour |
| `PRODUCT-SPECIFICATION-v1.4.md` §12.2 and §12.3 | the normative requirement and the quoting carve-out |
| `docs/PHASE-2A-IMPLEMENTATION-REPORT.md` §1 | the module's role and line count |

## State

| Property | Value |
|---|---|
| Recorded hash (Phase 2A delivery) | `bd09d066c036e43a974555ad6624026e96410d359b10f00b35a7350b20f9ba5a` |
| Current hash (reconstruction) | `765037914b353d18d904a657954b260a1f656c4ef4433052f1708f544fa55743` |
| Recorded size | 1 624 bytes |
| Current size | 1390 bytes |
| `TestACData18CopyLint` | **3/3 pass** |
| Full Phase 2A suite | **214/214 pass** |

## Why the manifest was not updated

`docs/PHASE-2A-MANIFEST.md` is the historical record of what Phase 2A
delivered. Overwriting its hash would erase the evidence of this event.
The manifest keeps the recorded hash; this addendum is the truthful
record. **51 of 52 entries are byte-identical to the delivered state**;
the one divergence is this file.

## Prevention

The Quality Guardian now refuses any repair that would shrink a file below
**50 %** of its current size (`config.MIN_REPAIR_SIZE_RATIO`). A mechanical
formatting fix never removes most of a file; a repair that would indicates
corruption rather than a formatting defect. Such a repair is reported as
`NOT_VERIFIED` and escalated to a human instead of being applied.

## Owner decision

Whether to accept the reconstruction as the new baseline, or to restore the
original bytes from another source, is an owner decision. **No decision has
been taken.** Until it is, the Guardian reports this file as a manifest
divergence on every cycle — which is the correct, honest behaviour.
