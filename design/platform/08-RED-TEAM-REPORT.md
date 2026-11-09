# Red Team report

## Method

The Red Team was **not** me. Two independent reviews ran against the
guard's specification, with no repository access, reasoning only from
the described implementation — one as a general adversarial review and
one as a targeted attack on eight named areas.

**Every finding was checked against the real code before anything was
changed.** Two were confirmed and fixed; the rest were either
theoretical, already fixed, or wrong.

## Confirmed findings, and their fixes

### D-22 — The operation was not bound to the signature

**Severity: CRITICAL.**

The service derived the request from the authorisation, and the derived
request's `operation` field was set to the operation the **plugin**
asked for. The proposal hash was recomputed and checked, the scope was
checked — but the **operation**, which is the thing the human
approved, was never among the checks.

The probe: an approval signed for `file.delete` was presented for
`repo.wipe`. Both need the scope `files:write`. The service answered
**ALLOW** and the handler ran.

**Fix.** The authorisation now carries the operation it was made for,
and the service refuses an approval whose operation differs from the
one being requested.

### D-23 — The scope check was vacuous

**Severity: HIGH.**

The derived request's `requested_scope` was the authorisation's **own**
`approved_scope`. So `verify_authorization`'s "approved is a subset of
requested" compared a set with itself. It could not detect an
approval that grants more than the operation needs.

**Fix.** The requested scope now travels in the message, separately
from the approval, and the approval must be a subset of **that**.

### D-24 — The transport nonce set was not durable

**Severity: HIGH.**

The nonce set was in memory, so it was lost on a service restart — and
an agent can restart a service.

**What it was and was not.** It was **not** an open door: the **spent
set** is durable and already refuses a replayed *authorisation*. The
nonce set refuses a replayed *request*, which is a different thing. The
in-memory set was a weaker defence than it should have been.

**Fix.** The nonce set is durable, in the same store and the same
atomic pattern as the spent set. The refusal is fail-closed: if the
nonce cannot be recorded, the request is refused before any
authorisation logic is reached.

## Findings examined and not confirmed

| Finding | Why it was not confirmed |
|---|---|
| "The scope check is vacuous" (second review) | It was vacuous **before** D-23. After the fix, step 6 compares against the message's requested scope, which is the plugin's claim — and the approval must be a subset of it. The second review was reasoning from the specification as given, which already included the fix. |
| "A consistent rewrite of the audit chain is undetected" | **True and already known.** It is residual risk R3: the checkpoint mechanism exists, the external anchor does not. Not a new finding. |
| "The exception handling is insufficient" | Every failure path was traced. Each one produces a DENY with a reason, and the tests assert that the **handler was not called** in each refusal case. |
| "Undefined behaviour in the recovery" | The recovery function has no handler access at all. It classifies and records; it cannot retry because it cannot execute. |

## What the review could not test

Stated so the report is not read as more than it is:

1. **The Windows service path.** The client-token check, the pipe's
   ACL, the service's own identity — none of it can be exercised
   without installing a service, which the mission forbids.
2. **Real side effects.** The handlers in the tests are recorders.
   A handler that deletes three of four files before raising has not
   been exercised against a real filesystem.
3. **The mobile applications.** They do not exist. The protocol and
   the reference implementation do.

## The verdict

**No unresolved critical or high bypass in the logic that was
reviewable.** The two confirmed critical/high defects are fixed, and
the highest-risk remaining items — the un-installed service, the absent
hardware credential, the missing external anchor — are **deployment**
gaps, stated as such in the readiness report rather than presented as
implemented.

That is not the same as "the platform is safe". It is: *the parts that
could be attacked without a deployment have been attacked, and the
parts that need a deployment are named.*
