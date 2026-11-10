---
name: consequence-map
description: Use when an action may have consequences worth predicting before it runs - writing, deleting, spending, sending, committing, or changing configuration. Produces a forecast, records the decision, and compares the forecast with what actually happened.
---

# ConsequenceMap

See what happens before it happens.

## The loop

1. **Forecast** - before the action, classify the evidence, assess the
   risk, the confidence and the reversibility, and name the
   alternatives. Evidence is `VERIFIED_FACT`, `INFERENCE` or
   `UNKNOWN`; a prediction is never a guarantee.
2. **Decision** - record what was chosen and why. The product
   decision is yours; the human's authorization is the host's record.
   They are never merged.
3. **Outcome** - after the action, record what happened and compare it
   with the forecast. An outcome that cannot be verified stays
   `NOT_VERIFIABLE`. It is never presented as a confirmation.

## The rules

- **Do not block indiscriminately.** Escalate only what the
  specification escalates: a protected path, a critical or high
  severity, or an irreversible action.
- **Never claim an approval you did not observe.** If the
  authorization was not observed, the state is `UNKNOWN` or
  `APPROVAL_NOT_OBSERVED`, never `HUMAN_APPROVED`.
- **Never rewrite a forecast.** Once sealed, it is immutable. The
  comparison lives beside it.
- **Never say "guaranteed" or "ensures".** Say what was predicted,
  on what evidence, and with what confidence.
- **Mark the unknown.** What you could not determine is part of the
  answer.

## When the user asks "what will happen if I do X?"

Forecast it. Show the evidence, the risk, the confidence, the
reversibility and the alternatives. Then, after the action, compare
the forecast with what happened - and say plainly where the forecast
was wrong.
