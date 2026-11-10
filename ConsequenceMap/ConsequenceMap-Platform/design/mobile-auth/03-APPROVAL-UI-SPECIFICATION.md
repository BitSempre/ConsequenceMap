# Approval UI Specification

**Status:** DESIGN.

---

## 1. The rule the whole specification exists to enforce

> **The human must see the real operation, not a summary of it.**

A generic "Approve this request?" dialog is not a human decision. It is
a rubber stamp with a delay. The interface exists so that a person can
read what will happen and decide whether they want it to happen.

---

## 2. What must be on the screen

Every field below is shown **verbatim** from the signed request. The app
does not paraphrase, does not shorten, and does not reorder.

### 2.1 Identity — always visible

| Element | Rule |
|---|---|
| Project | Plain text, from the request |
| Requesting agent | From the request |
| Request id | Short, but selectable and copyable |
| **Proposal hash** | Full 64 hex characters, selectable. The human can compare it with the PC |
| Protocol version | From the request |

The hash is not decoration. It is the value the human's signature will
be bound to, and showing it in full is what lets a person check two
devices against each other.

### 2.2 The operation — the substance

| Element | Rule |
|---|---|
| **Action** | Shown in full. Never truncated. Never abbreviated |
| **Affected resources** | **Every one**, as a list, each item selectable |
| **Requested permissions** | Each permission named individually |
| Reversibility | Explicit: yes / no / partially |
| Consequence summary | Shown, **but never as the only description** |

### 2.3 Time and scope

| Element | Rule |
|---|---|
| Expires at | Absolute time, plus a live countdown |
| Requested scope | Every scope item |

---

## 3. The truncation and hiding attacks

This is the part that makes the difference between a real decision and a
rubber stamp.

### 3.1 Content hidden below the fold

**Attack.** The proposal names 200 resources. The app shows the first
three, and the rest are below the scroll. The human scrolls past, or
does not scroll, and approves.

**Requirement.** The app **must** state the total count, and must show
it **before** the approval button is reachable:

```
  This operation affects 200 files.
  [ Show all ]        <- must be tapped, or the button stays disabled
```

The approval button is **disabled** until the human has either viewed
the full list or explicitly dismissed it with an action that is recorded
in the signed request.

### 3.2 Content hidden by an ellipsis

**Attack.** The action string is 400 characters; the app shows 40
followed by "…".

**Requirement.** **No ellipsis on the action, the resource list, or the
permissions.** If the content does not fit, the screen scrolls. A
truncated field is a field the human has not read.

If the platform ever needs a hard cap, it belongs on the **producer**
side — the request is rejected for being too long — not on the display
side. A cap that silently truncates is a cap that hides.

### 3.3 The summary lies

**Attack.** The proposal's real action is "delete the repository"; the
consequence summary says "Deletes one harmless file." The summary is
signed, so it cannot be changed — but it can be a lie.

**Requirement.** The summary is **supplementary**. The action and the
resource list are authoritative and are always shown in full. The
summary is labelled as the requester's own description, not as the
platform's characterisation.

The demonstration in `prototype/demo.py` §7 documents this explicitly: a
lying summary **still verifies**, because the cryptography cannot tell a
lie from a truth. The mitigation is presentation, and it belongs in the
specification rather than in a test.

### 3.4 The wrong screen

**Attack.** A crafted proposal carries a string that renders as a
different operation — for example, a resource name containing a newline
followed by a word that looks like the platform's own decision banner.

**Requirement.** All strings are rendered as **plain text**, never as
markup, never with a renderer that interprets them. No HTML, no
Markdown, no rich text. A newline in a resource name is shown as a
newline, visually distinct, not swallowed.

### 3.5 The tapjacking / decoy screen

**Attack.** The PC shows a different QR code, or a fake prompt, at the
moment the human is looking at the phone.

**Requirement.** The phone shows the **hash**. The human can compare it
with the PC. The app must make that comparison easy: the hash is shown
in full, selectable, and grouped in readable blocks.

---

## 4. The approval action

| Requirement | Why |
|---|---|
| Biometric or PIN, **always** — no "approve" button alone | The signature must require user presence; the platform enforces it |
| The signing operation is triggered by the human's action | Not on page load, not on a timer |
| The human may **reject** without any ceremony | A rejection must be as easy as an approval, or people approve reflexively |
| The decision is **recorded either way** | A refusal that leaves no trace is invisible to the owner |
| The app states which key signed and at what security level | Hardware-backed or software-only |

### Rejection is a first-class outcome

The UI must make rejection **fast and unsurprising**. If rejecting is
hard, the approval becomes the path of least resistance, and the human
presence becomes theatre. The platform records refusals with the same
rigour as approvals.

---

## 5. Accessibility and honesty

| Requirement | Why |
|---|---|
| Every field readable by a screen reader | An unreadable field is an unapproved field |
| Text resizable to 200% | "It was too small to read" is not consent |
| No time limit shorter than the expiry | A forced decision is not a decision |
| Works one-handed | The rejection path must be reachable |
| No dark patterns | A dark pattern converts a decision into a reflex |

---

## 6. States the screen must distinguish

| State | Screen |
|---|---|
| No pending request | "Nothing to approve" — never a stale request |
| A request arrived | The full operation, hash, expiry, countdown |
| Expired | "This request expired" with the expiry time; approve disabled |
| Already answered | "You already approved this request" — the request id, and **no** second approval |
| Key revoked | "This device's key was revoked" — approve disabled |
| Wrong channel | "This request came from a different computer" — approve disabled |
| Wrong hash | "This request does not match what is being signed" — approve disabled |

**A rejected request is never silently retried.** If the human declines,
the request is closed and a new one requires a new proposal.

---

## 7. What the human cannot see

| Hidden | Why |
|---|---|
| The internal policy | It would let the human approve "in the abstract"; the scope shown IS the policy |
| The verifier's internals | Irrelevant to the decision |
| The revocation list | Not actionable by the human |
| Other pending requests | One at a time — a queue invites reflexive approval |

---

## 8. Implementation status

**NOT IMPLEMENTED.** The specification above is complete enough to
implement against; the phone applications are not written.

The part that **is** implemented is the cryptographic binding, which is
what makes the display trustworthy: what the human reads is what was
hashed, and what was hashed is what the signature covers. See
`prototype/demo.py`.
