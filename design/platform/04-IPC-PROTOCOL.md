# The protocol between the plugin and the Security Guard

## The shape

A request travels over a **named pipe**. The plugin opens it, writes
one request, reads one response, closes it.

```
plugin                          service
  │  CreateFile(\\.\pipe\ConsequenceMapGuard)
  │  ──── request bytes ────▶  authenticate the caller
  │                            parse (closed schema, size limit)
  │                            decide
  │  ◀─── response bytes ───  {decision, reason, operation_id, state}
```

## Why a named pipe

| Property | Why it matters here |
|---|---|
| Local only | A pipe has no port and no network binding. A loopback socket is reachable from another machine unless the firewall stops it. |
| Kernel-mediated | The ACL is checked by the kernel on every connection, not by the application. |
| Attributable | The service can ask the kernel who connected. |
| No listening socket | Nothing is exposed to the network stack at all. |

## The request schema

```json
{
  "message_type": "execution.request",
  "protocol_version": "consequencemap.guard.ipc.v1",
  "nonce": "a fresh 256-bit value",
  "operation_id": "file.delete",
  "proposal": { "...the operation to approve..." },
  "authorization": { "...signed by the phone..." },
  "requested_scope": ["files:write"],
  "issued_at": "2026-11-09T18:00:00.000Z"
}
```

**The schema is closed.** A field that is not listed is refused.

**There is no field for a decision.** Not `allowed`, not `decision`,
not `approved`. The service derives the answer; a field the plugin can
set is a field the plugin can lie about.

**There is no field for arguments, a handler name, or a command.** The
operation is named by its identifier, and the service looks that
identifier up in its own allowlist. The arguments are **derived** from
the proposal by the policy's argument map.

## The response schema

```json
{
  "message_type": "execution.response",
  "protocol_version": "consequencemap.guard.ipc.v1",
  "decision": "ALLOW",
  "reason": "the operation completed",
  "operation_id": "file.delete",
  "state": "COMPLETED"
}
```

`decision` is `ALLOW`, `DENY` or `INDETERMINATE`. **`INDETERMINATE` is
never converted to `ALLOW`.**

## The rules

| Rule | Consequence |
|---|---|
| The version is checked | A message for another version is refused |
| Unknown fields are refused | A field the service does not understand might be one it would have honoured |
| The size limit applies to the bytes, before parsing | A large message cannot make the service do work |
| A fresh nonce per request | A transport-level replay is refused before the authorisation is considered |
| The caller is authenticated | An unlisted caller is refused before the message is read |
| The response schema is closed | A response with an unexpected field is a contradiction |

## The client's contract

The plugin's client has **no fallback**. If the pipe is unreachable,
the operation does not happen and the plugin is told why.

That is deliberate and it is the load-bearing part: the agent controls
the plugin, so **any capability the plugin can exercise without the
service is a capability the agent has**. A local fallback would be
exactly the hole the architecture exists to close.

## The Windows path, and what is untested

The production transport uses `CreateFile` on the pipe, a
length-prefixed frame, and a per-request deadline. The service obtains
the client's token and compares the SID against the allowlist.

**None of that can be exercised on this host** — it needs a real
service install, which the mission forbids. The seam around it is
tested; the Windows path is written as the specification of what the
production implementation must do.
