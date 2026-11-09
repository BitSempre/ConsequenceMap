"""Consequence Intelligence: the analysis that precedes execution.

This module does the thinking, and it does it in a way that survives
contact with reality.

The three rules it enforces
---------------------------
1. **Forecast and outcome stay separate.** A forecast is immutable once
   sealed. An outcome is a separate record that references it. Nothing
   here ever writes an observation into a forecast, and nothing here
   treats an outcome as something the forecast predicted.
2. **Every claim carries its class.** ``VERIFIED_FACT`` means the claim
   was checked against a source. ``INFERENCE`` means it was reasoned from
   other claims. ``UNKNOWN`` means nobody knows. A result that could not
   be confirmed is ``NOT_VERIFIABLE``, which is not ``VERIFIED_FACT``.
3. **A forecast is not a promise.** Nothing in this module reports a
   forecast as a guarantee, and a comparison never turns a partial match
   into a success.

Why the classification matters
-------------------------------
The failure this prevents is specific: an agent writes a plausible
analysis, the analysis is treated as a fact, the fact is used to justify
an operation, and the operation turns out to have been based on nothing.
Keeping the class attached to the claim all the way to the authorization
is what stops that chain.

Where it fits
-------------
The forecast layer already exists in ``domain/records.py`` (Forecast,
Evidence, Impact, Risk, Alternative, Unknown) and
``domain/serialization.py`` (canonical form, content hash). This module
adds the **policy** on top: what a claim may be used for, and how a
forecast is qualified for presentation to a human who is about to approve
an operation.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping, Optional, Sequence, Tuple

__all__ = [
    "CLASS_VERIFIED_FACT",
    "CLASS_INFERENCE",
    "CLASS_UNKNOWN",
    "CLASS_NOT_VERIFIABLE",
    "CLAIM_CLASSES",
    "CONFIDENCE_RANK",
    "confidence_rank",
    "QualificationError",
    "ForecastNotQualified",
    "classify_claim",
    "confidence_rank",
    "aggregate_confidence",
    "qualify_forecast",
    "comparison_verdict",
    "COMPARISON_VERDICTS",
]

CLASS_VERIFIED_FACT = "VERIFIED_FACT"
CLASS_INFERENCE = "INFERENCE"
CLASS_UNKNOWN = "UNKNOWN"
CLASS_NOT_VERIFIABLE = "NOT_VERIFIABLE"

#: Every class a claim may carry.
CLAIM_CLASSES: Tuple[str, ...] = (
    CLASS_VERIFIED_FACT,
    CLASS_INFERENCE,
    CLASS_UNKNOWN,
    CLASS_NOT_VERIFIABLE,
)

#: The confidence levels, from strongest to weakest.
CONFIDENCE_RANK: Mapping[str, int] = {
    "HIGH": 3,
    "MEDIUM": 2,
    "LOW": 1,
    "NONE": 0,
}


class QualificationError(ValueError):
    """Raised when a value violates the analysis contract."""


class ForecastNotQualified(QualificationError):
    """The forecast may not be presented for approval."""


def classify_claim(
    classification: str,
    *,
    source_kind: Optional[str] = None,
    verified: Optional[bool] = None,
) -> str:
    """Normalise and validate a claim's classification.

    ``verified=False`` downgrades a claim to ``NOT_VERIFIABLE``: a result
    that could not be confirmed must never be presented as a fact, and
    this is where that rule is enforced rather than assumed.
    """
    if classification not in CLAIM_CLASSES:
        raise QualificationError(
            "unknown classification %r; expected one of %s"
            % (classification, ", ".join(CLAIM_CLASSES))
        )
    if verified is False and classification in (
        CLASS_VERIFIED_FACT,
        CLASS_INFERENCE,
    ):
        return CLASS_NOT_VERIFIABLE
    if classification == CLASS_VERIFIED_FACT and verified is None:
        # A fact with no source is not a fact.
        if not source_kind:
            raise QualificationError(
                "a VERIFIED_FACT claim needs a source_kind"
            )
    return classification


def confidence_rank(confidence: str) -> int:
    """Return the rank of a confidence level; unknown levels rank lowest."""
    return CONFIDENCE_RANK.get(confidence, -1)


def aggregate_confidence(confidences: Sequence[str]) -> str:
    """Aggregate the confidence of a set of claims.

    The aggregate is the **weakest** claim, not the average. A forecast
    built on one unverified claim is not as confident as its other claims
    suggest, and averaging would hide that.
    """
    if not confidences:
        return "NONE"
    ranks = [confidence_rank(c) for c in confidences]
    known = [r for r in ranks if r >= 0]
    if not known:
        return "NONE"
    weakest = min(known)
    for level, rank in sorted(CONFIDENCE_RANK.items(), key=lambda kv: kv[1]):
        if rank == weakest:
            return level
    return "NONE"


def comparison_verdict(
    *,
    matched: int,
    total: int,
    unknown_dimensions: int = 0,
) -> str:
    """Classify a forecast-versus-outcome comparison.

    The rules are deliberately conservative:

    - a comparison with **no** dimensions is ``NOT_EVALUABLE`` - there is
      nothing to compare, and that is not a pass;
    - a comparison with **unknown** dimensions is ``PARTIAL`` - the
      forecast was not fully borne out, and saying otherwise would be the
      false reassurance this module exists to prevent;
    - a partial match is ``PARTIAL``, never ``MATCHED``.
    """
    if total <= 0:
        return "NOT_EVALUABLE"
    if unknown_dimensions > 0:
        return "PARTIAL"
    if matched <= 0:
        return "CONTRADICTED"
    if matched < total:
        return "PARTIAL"
    return "MATCHED"


#: The verdicts a comparison may carry.
COMPARISON_VERDICTS: Tuple[str, ...] = (
    "MATCHED",
    "PARTIAL",
    "CONTRADICTED",
    "NOT_EVALUABLE",
)


def qualify_forecast(
    forecast: Mapping[str, Any],
    *,
    require_explicit_unknowns: bool = True,
) -> Mapping[str, Any]:
    """Decide whether a forecast may be presented for approval.

    A forecast qualifies when it:

    - carries a content hash (it is sealed and identifiable);
    - has a summary;
    - records its unknowns explicitly - a forecast that does not say what
      it does not know is asking the human to approve a blank;
    - does not present an unverified claim as a fact;
    - states its confidence, and that confidence is not ``NONE`` when the
      forecast claims to support an operation.

    The result names what failed, so a refusal is actionable rather than
    a shrug.
    """
    problems = []

    if not forecast.get("content_hash"):
        problems.append("the forecast is not sealed: it has no content hash")
    if not forecast.get("summary"):
        problems.append("the forecast has no summary")

    unknowns = forecast.get("unknowns") or ()
    if require_explicit_unknowns and not unknowns:
        problems.append(
            "the forecast records no unknowns: the human would be approving "
            "a blank"
        )

    evidence = forecast.get("evidence") or ()
    for item in evidence:
        classification = item.get("classification")
        if classification == CLASS_VERIFIED_FACT and not item.get("source_kind"):
            problems.append(
                "an evidence item is marked VERIFIED_FACT without a source"
            )
        if classification not in CLAIM_CLASSES:
            problems.append(
                "an evidence item has the unknown classification %r"
                % (classification,)
            )

    confidence = forecast.get("confidence_overall")
    if not confidence:
        problems.append("the forecast states no overall confidence")

    risks = forecast.get("risk") or {}
    if risks.get("requires_human_approval") and confidence == "NONE":
        problems.append(
            "the forecast requires human approval but states no confidence"
        )

    if problems:
        raise ForecastNotQualified(
            "the forecast is not fit for approval: " + "; ".join(problems)
        )

    return {
        "qualified": True,
        "content_hash": forecast["content_hash"],
        "confidence_overall": confidence,
        "unknown_count": len(unknowns),
        "evidence_count": len(evidence),
    }
