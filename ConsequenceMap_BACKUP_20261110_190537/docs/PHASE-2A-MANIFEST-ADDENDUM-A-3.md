

---

# ConsequenceMap — Phase 2A manifest addendum A-3

**Date:** 2026-11-10
**Subject:** `consequence_map/storage/schema.py` — five foreign keys added.
**Status:** A deliberate, minimal change to the DDL. The recorded hash
is deliberately not overwritten.

## Why this addendum exists

The same mechanism as A-1 and A-2: the Phase 2A manifest is the audit
trail of a delivered phase, and a later phase that legitimately changes a
file records the change rather than rewriting the hash.

## `consequence_map/storage/schema.py`

**Manifest hash:** `d4b1ab95e078cf13f9a2fee1b6793259b2338d0c46e893c345186b55bad22962`
**Current hash:** `6c742810101f37e9b560192ac662338dba8a3f966a467d114d577e702455635b`
**Current size:** 11670 bytes

### What changed

Five tables had **no foreign keys at all**. A row could name a forecast
that did not exist, an execution that did not exist, an outcome that did
not exist.

That is the chain the product is built on. A forecast is sealed; a
decision is made about it; an authorisation is recorded for it; the
execution runs against it; the outcome is observed for it; and the
comparison puts the two side by side. If any of those references may
dangle, the chain can be broken in the middle and the product will report
a comparison between things that were never related.

The `forecast` table has had a composite foreign key to the proposal
since Phase 2A. The other five had none. They now have them:

| Table | Foreign keys added |
|---|---|
| `host_authorization` | `forecast(id)`, `proposal(id, version)` |
| `product_decision` | `forecast(id)`, `proposal(id, version)` |
| `execution` | `forecast(id)`, `host_authorization(id)`, `product_decision(id)` |
| `outcome` | `forecast(id)`, `execution(id)` |
| `comparison` | `forecast(id)`, `outcome(id)` |

The composite key on the proposal is the same one `forecast` uses, so a
decision cannot name a different version of the proposal than the
forecast it belongs to.

### What did not change

- **The 17 tables.** No table was added, removed or renamed.
- **Every column.** No column was added, removed, renamed or retyped.
- **The column order.** `COLUMN_ORDER` is unchanged, so the tuple-row
  addressing the repository uses is unaffected.
- **The trigger family.** `storage/triggers.py` is byte-identical; the
  45 triggers are untouched.
- **The journal and durability settings.** `storage/db.py` is
  byte-identical: WAL, `synchronous=FULL`, `foreign_keys=ON`.

### The proof came first

Five tests recorded an orphaned row and watched it accepted. They failed
before the change and pass after it. A sixth test records the whole chain
and confirms the normal path still works.

The foreign keys caught one of the Phase 2B tests, which recorded an
outcome naming an execution that never ran. The test was wrong, not the
constraint.

### The scope limit this change does not remove

Foreign keys enforce **referential** integrity. They do not make a
`host_authorization` mean that a human actually approved: that is the
correlation's job, and the correlation attributes an observation to a
forecast only when the pattern key or the tool call id matches. A row
that points at a real forecast can still be a row nobody answered — which
is why `PENDING`, `UNKNOWN` and `APPROVAL_NOT_OBSERVED` exist, and why
only `HUMAN_APPROVED` and `GUARDIAN_APPROVED` authorize anything.
