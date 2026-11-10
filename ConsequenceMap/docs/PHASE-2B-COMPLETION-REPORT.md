# ConsequenceMap — Phase 2B Completion Report

**Date:** 2026-11-10
**Phase:** 2B — Runtime integration, the product loop, and the demonstration
**Supersedes:** nothing. Phase 2A remains the record of the domain model and
the storage layer; see `PHASE-2A-MANIFEST.md` and addendum A-2.

---

## 1. What Phase 2A left, and what Phase 2B adds

Phase 2A delivered the **model** and the **storage**: fifteen record types,
eighteen enumerations, seventeen tables, a forty-five-trigger family that
makes a sealed forecast immutable, and 214 tests.

What it did not deliver was the **loop**. The repository had writers for
every record and no code that walked one operation through them. A
forecast could be stored, a decision could be stored, an outcome could be
stored — and nothing held them together, and nothing derived the
comparison that is the product's whole point.

Phase 2B adds that, and the runtime that makes it a plugin.

| Module | Lines | What it does |
|---|---|---|
| `consequence_map/lifecycle.py` | 299 | Forecast → decision → execution → outcome → comparison |
| `consequence_map/correlation.py` | 355 | Attribution, the eight edge cases, duplicate and orphan counters |
| `consequence_map/authorization.py` | 359 | The thirteen-state machine and the escalation deadline |
| `consequence_map/paths.py` | 211 | The six-step containment algorithm and the protected patterns |
| `consequence_map/self_exclusion.py` | 103 | RECUR-1 through RECUR-9 |
| `consequence_map/hooks.py` | 260 | The five callbacks and the command palette entry |

And the plugin itself:

```
plugin/
  plugin.yaml              the manifest the host parses
  __init__.py              the entry point: register(ctx)
  dashboard/
    manifest.json          the tab declaration
    plugin_api.py          the backend: four routes, a FastAPI router
    dist/index.js          the three Desktop surfaces
    dist/style.css
  desktop/plugin.js        the compact desktop panel
  skills/consequence-map/SKILL.md
```

---

## 2. The lifecycle

The link the repository did not have. It does five things and nothing
else:

1. `record_forecast` — persists a forecast **with the copy lint applied**.
   A summary containing guarantee language is refused at the write path.
2. `record_decision` — persists the product's own decision.
3. `record_authorization` — persists what the host observed about a
   human's answer. **A separate record.** The two are correlated for
   display by forecast id and are never merged.
4. `record_execution` — persists that the operation ran.
5. `compare` — builds the comparison and persists it.

Three properties are enforced rather than assumed:

| Property | How it is enforced |
|---|---|
| The forecast is immutable | The storage triggers refuse a second write; the lifecycle adds nothing |
| The decision and the authorization are never merged | Two tables, two write methods, one correlation key |
| An unverifiable outcome stays unverifiable | The domain's O-1 rule forces every observation to NOT_VERIFIABLE; the derived verdict is INCONCLUSIVE |

### The verdict is derived, never asserted

`derive_verdict` reads the observations and computes:

| Observations | Verdict |
|---|---|
| The outcome is UNVERIFIED | INCONCLUSIVE |
| Any observation is NOT_VERIFIABLE | INCONCLUSIVE |
| Any observation is UNEXPECTED | DIVERGED |
| All observed, none not-observed | ALIGNED |
| Some observed, some not | PARTIALLY_ALIGNED |
| None observed | INCONCLUSIVE |

The domain's C-2 rule requires the comparison's counts to match its items
exactly, so the items are **derived from the observations** rather than
supplied independently. The domain's C-5 rule requires a comparison with
no UNEXPECTED item to say so in its accuracy note, so the note states it
in words rather than leaving the reader to infer it.

---

## 3. The runtime

### The five hooks

| Hook | Kind | May it change the host's decision? |
|---|---|---|
| `pre_tool_call` | Directive | **Yes** — the plugin's one intervention point |
| `pre_approval_request` | Observer | No |
| `post_approval_response` | Observer | No |
| `post_tool_call` | Observer | No |
| `transform_tool_result` | Transform | Yes — **and this plugin never uses it** |

`transform_tool_result` is registered because it is one of the five
declared hooks, and it is registered **strictly as a declaration**: its
callback returns `None` on every invocation and never mutates the
`result` payload it receives — neither by returning a replacement nor by
mutating the object in place. The host passes the live object by
reference, so returning `None` alone does not demonstrate compliance.
The test asserts the payload is unchanged in content and identity.

### Correlation

The chain is `forecast_id → proposal_version → rule_key → tool_call_id →
approval_request → approval_response → post_tool_call → outcome`.

The plugin supplies `cm:<forecast_id>:<rule>` and **never** includes the
host's `plugin_rule:` prefix; the host adds it. An observation is
attributed to a forecast only if every condition holds, and any failure
means `UNKNOWN` or `APPROVAL_NOT_OBSERVED` — never `HUMAN_APPROVED`.

The eight edge cases are implemented and tested: EC-1 (an empty
`tool_call_id` is ABSENT, not a match), EC-2 (an orphan belongs to
nobody), EC-3 (the first observation wins; the duplicate is ignored **and
counted**), EC-4 (out-of-order events), EC-5 (a crash loses the pending
escalation, reconciled as `APPROVAL_NOT_OBSERVED`), EC-6 (a tool that ran
with no approval observed is `AUTOMATICALLY_ALLOWED`), EC-7 (an ambiguous
match is never an approval), EC-8 (another plugin's approval is never
attributed).

### The thirteen states

The domain already defines them. The machine derives one from an
observation, and the absence of an observation is itself an observation —
the weaker state.

The confusions the specification names as high-risk are pinned by tests:
a timeout is not a refusal (and has no author), a cancelled prompt is
not a refusal, and the Guardian's verdict is never recorded as the
human.

---

## 4. The demonstration

`demo/consequence_map_demo.py` runs one operation through the whole
product loop against a real temporary SQLite database — the real schema,
the real triggers, the real immutability rule — and prints what a
reviewer would see.

It ends by attempting to rewrite the sealed forecast. The write is
refused with an `IntegrityError`, and the script prints that the stored
forecast is unchanged.

It also says plainly what it does **not** exercise: the Hermes host
integration. The five hooks, the command palette and the three Desktop
surfaces are covered by the test suite, not by that script.

---

## 5. The tests

| Suite | Count | Result |
|---|---|---|
| `consequence_map/tests` | 515 | PASS |
| `host_tests` | 2 | PASS |
| `consequence_guard/tests` | 134 | PASS |
| Mobile prototype | 12 | PASS |
| Mobile prototype demo | 13 checks | exit 0 |
| **Total** | **676** | **all green** |

The Phase 2A suite was 214. It is 515 now: 301 new tests across four new test files, none of
the original ones changed.

Two audits held throughout, and they caught real problems:

- **The third-party import audit.** It refused `logging`, `time`,
  `importlib.util`, `subprocess` and a `hermes_constants` import. The
  modules were rewritten to use only what the allowlist permits — the
  home is injected rather than read, the time comes from `datetime`, and
  the logger is gone.
- **The environment audit.** It refuses the literal `os.environ` anywhere
  in the package — including in a docstring that mentioned it. The
  docstring was reworded.

Neither audit was widened. The allowlist was not relaxed to make the new
code fit; the new code was made to fit the allowlist.

### The host is exercised, not assumed

`host_tests/test_host_manifest.py` imports the **real** Hermes manifest
parser and checks that it accepts the plugin's manifest with its five
hooks. It is skipped, never reported as a pass, when the runtime is
absent.

`consequence_map/tests/test_host_load.py` executes the plugin's entry
point the way the host's loader reaches a directory plugin, and checks
that the five hooks and the command are registered.

---

## 6. What is NOT claimed

- **The plugin is not installed.** It is built, and the host's own parser
  accepts it, but it has not been installed into `~/.hermes/plugins/`.
  The mission forbids changing the global Hermes configuration without
  authorisation.
- **The Desktop surfaces have not been rendered in the Hermes Desktop
  window.** The frontend is written against the host's plugin SDK and
  the backend's four routes are tested against the real FastAPI router,
  but nobody has watched the panel draw.
- **The escalation deadline is a default, not a decision.** The machine
  implements mechanism M-1 (the host's wait plus a grace period) with a
  30-second grace. DEC-16 is still OPEN and belongs to the owner.
- **Path containment is not a guarantee about the write.** The path,
  *resolved at the moment of analysis*, was inside the authorized root.
  The window between the check and the host's write is not closed and is
  not claimed to be.
- **The security platform is still `NOT READY FOR PRODUCTION`.** No
  service is installed, no ACL is applied, no external anchor exists.
  Phase 2B does not change that.

---

## 7. The Phase 2A divergence

One file covered by the Phase 2A manifest changed: `consequence_map/__init__.py`,
for the version string and the module docstring. `SCHEMA_VERSION` is
unchanged, so an existing Phase 2A database remains valid.

Addendum **A-2** records the change and names the file, which is the
mechanism the Quality Guardian already implements: a divergence recorded
in an addendum is a WARNING — a known, recorded state — and an
unrecorded one is a FAIL. The Guardian reports **WARNING, 0 FAIL**.

`auto_repair` remains `false`. The storage layer, the schema, the
triggers, the enumerations, the validation rules and the redaction
boundary are all byte-identical to Phase 2A.
