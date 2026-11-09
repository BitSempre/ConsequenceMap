# Persistence and recovery

## The store

SQLite, with `journal_mode=WAL` and `synchronous=FULL`.

`synchronous=FULL` is the expensive setting: it makes a commit durable
rather than merely handing it to the operating system. For a store
that decides whether a protected operation may proceed, the cost is
the point.

### The schema

| Table | Holds |
|---|---|
| `spent_authorizations` | The consumed authorisations: the spent key, the authorisation id, the nonce, the request id, the operation id, when, by whom |
| `operations` | The operation states, with the request, the authorisation, the operation, the proposal hash and the timestamps |
| `audit_log` | The chained trail |
| `audit_checkpoints` | The integrity checkpoints |
| `guard_meta` | The schema version |

## Atomic consumption

The atomic step is the `INSERT` of the spent key, inside a
`BEGIN IMMEDIATE` transaction:

```sql
BEGIN IMMEDIATE;
  SELECT spent_key FROM spent_authorizations WHERE spent_key = ?;
  -- absent: INSERT ... ; present: return "already consumed"
COMMIT;
```

`IMMEDIATE` takes the write lock at the start. Two writers cannot both
read and then both write: the second one either sees the row or loses
the insert. With a **deferred** transaction the second writer would
fail at `COMMIT` with "database is locked" — a different failure, and a
worse one, because it does not say *which* authorisation was taken.

**Verified with two real processes.** The test spawns two Python
processes that race for the same authorisation and asserts exactly one
wins. A thread-level test would have proved nothing: the GIL would
serialise the threads and the test would pass for the wrong reason.

## The operation states

```
RECEIVED ──▶ VALIDATED ──▶ CONSUMED ──▶ EXECUTION_STARTED ──┬──▶ COMPLETED
                                                            └──▶ FAILED
```

and, from a crash:

```
EXECUTION_STARTED ──(process dies)──▶ OUTCOME_UNKNOWN
```

### Why `OUTCOME_UNKNOWN` exists

A handler may fail **half-way through** — it may have deleted three of
four files before raising. If the process dies between
`EXECUTION_STARTED` and `COMPLETED`, the effect **may or may not have
happened**.

Three wrong answers are available, and all three are tempting:

1. **Assume it did not happen** → a retry applies the effect twice.
   "Delete one report" becomes "delete two".
2. **Assume it did happen** → a failed operation is reported as a
   success, and the human is told something untrue.
3. **Retry automatically** → the same as (1), without a human in the
   loop.

The only defensible answer is `OUTCOME_UNKNOWN`: the effect may or may
not have happened, the system says so, and **it is never retried
automatically**. A human decides, and the decision is audited.

## Recovery

On startup, `recover_operations` classifies every operation left in a
non-terminal state:

| Found in | Becomes | Why |
|---|---|---|
| `RECEIVED`, `VALIDATED` | `FAILED` | Nothing ran. The authorisation was not spent, so it may be proposed again. |
| `CONSUMED` | `FAILED` | The authorisation was spent but the handler did not start. The effect did not happen — and a **new** authorisation is needed, because the old one is spent. |
| `EXECUTION_STARTED` | `OUTCOME_UNKNOWN` | The effect may or may not have happened. A human checks. |

**The recovery function has no handler access at all.** That is how
the "never retried automatically" guarantee is structural rather than
a promise: it is not that the function chooses not to retry — it
*cannot*.

The classification is audited.

## Fail-closed

Every store operation raises `StoreUnavailable` on failure. There is
no path that continues without the record.

| Failure | Result |
|---|---|
| The store cannot be opened | `StoreUnavailable` |
| The directory cannot be created | `StoreUnavailable` |
| The database is locked | `StoreUnavailable` after the timeout |
| The disk is full | `StoreUnavailable` on the write |

And in the service: **an operation whose audit record cannot be
guaranteed is refused.**

## What is not yet done

- **The external anchor.** The checkpoint mechanism exists; the
  anchor outside the agent's reach does not.
- **The startup integrity gate.** The service should refuse to start
  if the chain does not verify against the last checkpoint. That needs
  the anchor.
- **The durable store's ACL.** The code guarantees atomicity and
  durability; the filesystem ACL guarantees the agent cannot reach the
  file. The ACL is a deployment property and is **not installed here**.
