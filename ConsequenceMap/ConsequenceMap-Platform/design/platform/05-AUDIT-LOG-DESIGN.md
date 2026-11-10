# The audit trail

## What it records

| Event | When |
|---|---|
| `guard.request.accepted` | The service accepted a request and is about to consume the authorisation |
| `guard.operation.completed` | The handler returned successfully |
| `guard.operation.failed` | The handler raised |
| `guard.operation.blocked` | The handler blocked |
| `guard.registry.revoked` | A device was revoked |
| `guard.recovery.classified` | A crash left an operation in a non-terminal state, and recovery classified it |

**Refusals are recorded too**, and they are the interesting part: a
refusal that leaves no trace is indistinguishable from an operation
that never happened.

## The chain

Each record carries:

- a **sequence number**, contiguous from zero;
- the **previous record's hash**;
- its **own hash**, over its sequence, event, payload and timestamp.

A record that is altered, removed or reordered breaks the chain.

## Immutability

A written record is **immutable**: read-only fields, and a deep,
read-only payload snapshot. Mutating the caller's own dictionary after
the append does not reach into the log, and
`record.payload["nested"]["key"] = x` raises.

This is the difference between *detecting* a rewrite and *preventing*
one. The chain detects inconsistency; immutability means the only way
to change the history is to build a different history — which produces
a different chain and a different head.

## What each mechanism protects against

This matters, because a hash chain is often over-claimed:

| Mechanism | Stops | Does not stop |
|---|---|---|
| The hash chain | A record altered in place, removed from the middle, or reordered | A **consistent** rewrite, with the hashes recomputed |
| Immutable records | The rewrite after the fact, before detection | A rewrite that produces a new, valid chain |
| Checkpoints | A consistent rewrite — it verifies internally, but not against the checkpoint | A rewrite that also updates the checkpoint |
| The ACL on the store | The agent reaching the file at all | An administrator |
| Durable storage | The trail surviving a restart | — |

**A hash chain alone does not prevent a full rewrite.** It detects
inconsistency. The defence against a consistent rewrite is an
**external anchor**: the head hash, recorded where the agent cannot
write. The mechanism exists — `write_checkpoint`, and the
`expected_head` parameter on the chain verification — but **the anchor
itself is not built**, because it needs a deployment context.

That is listed as residual risk **R3**, not quietly omitted.

## Failure modes

| When the failure happens | What happens |
|---|---|
| **Before** execution | The operation is refused. Nothing ran. |
| **During** execution | The handler's exception is caught; the operation is recorded `FAILED`. |
| **After** execution, recording the result | The outcome **cannot** be recorded as `COMPLETED`. The state becomes `OUTCOME_UNKNOWN`, and the effect is treated as possibly having happened. |
| The checkpoint fails | The operation continues — a checkpoint is a detection aid, not a precondition — and the failure is recorded. |

**A result is never presented as `COMPLETED` without persisted
evidence.**

## Verifying after a restart

The trail is in the durable store, so it survives a restart. On
startup the service should:

1. read the chain and verify it;
2. compare the head against the last checkpoint;
3. classify any operation left in a non-terminal state (see
   `09-PERSISTENCE-AND-RECOVERY.md`);
4. **refuse to start** if the chain does not verify against the
   checkpoint.

Step 4 is not implemented yet, because there is no external anchor to
compare against. It is written down rather than left implied.
