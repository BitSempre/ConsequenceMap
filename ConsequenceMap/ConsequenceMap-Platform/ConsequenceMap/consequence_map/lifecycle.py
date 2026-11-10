"""The lifecycle: forecast -> decision -> execution -> outcome.

The domain model defines the records and the storage layer persists
them. What was missing was the link: the code that walks one operation
through the chain and keeps the four parts tied to each other.

This module is that link, and nothing more. It:

* records a proposal and seals its forecast, with the copy lint
  applied to the summary;
* records the product's decision and, separately, the host's
  authorization;
* records the execution;
* records the outcome, and the comparison with the forecast.

Three properties are load-bearing and are enforced here rather than
assumed:

1. **The forecast is immutable.** It is sealed once, and the storage
   triggers refuse any later change.
2. **The product decision and the host authorization are never
   merged.** They are two records, correlated by forecast id for
   display only.
3. **An outcome that cannot be verified stays UNVERIFIED.** The
   domain's O-1 rule forces every observation to NOT_VERIFIABLE or
   NOT_APPLICABLE, and the verdict is INCONCLUSIVE. A forecast is
   never confirmed by an observation nobody can vouch for.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Optional

from .domain import records as R
from .domain.enums import (
    COMPARISON_ORIGIN,
    COMPARISON_VERDICT,
    OBSERVED_OUTCOME,
    VERIFICATION_METHOD,
)


class LifecycleError(Exception):
    """The lifecycle could not complete the step."""


def content_digest(payload: Any) -> str:
    """A stable digest of a record's content."""
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


class Lifecycle:
    """One operation, from the proposal to the comparison.

    The repository is injected, so the same code runs against an
    in-memory database in a test and against the plugin's own database
    in production.
    """

    def __init__(self, repository) -> None:
        self.repository = repository

    # -- the forecast ---------------------------------------------------

    def record_forecast(self, forecast: R.Forecast) -> R.Forecast:
        """Persist a forecast, with the copy lint applied.

        AC-DATA-18: the forecast summary must contain no guarantee
        language. The lint is a write-path enforcement now, not an
        advisory.
        """
        from .domain.copy import CopyLintError, assert_no_guarantee_language

        try:
            assert_no_guarantee_language(forecast.summary)
        except CopyLintError as exc:
            raise LifecycleError(
                "the forecast summary may not present a prediction as a "
                "guarantee: %s" % (exc,)
            ) from exc
        self.repository.write_forecast(forecast)
        return forecast

    def seal_forecast(self, forecast_id: str) -> str:
        """Seal a forecast. After this it cannot change."""
        return self.repository.seal_forecast(forecast_id)

    # -- the decision ---------------------------------------------------

    def record_decision(
        self,
        decision: R.ProductDecision,
    ) -> R.ProductDecision:
        """Record the product's own decision.

        This is the agent's reasoning about the forecast. It is not an
        authorization, and it never becomes one.
        """
        self.repository.write_product_decision(decision)
        return decision

    def record_authorization(
        self,
        authorization: R.HostAuthorization,
    ) -> R.HostAuthorization:
        """Record what the host observed about a human's answer.

        A separate record from the product decision. The two are
        correlated for display by forecast id and are never merged.
        """
        self.repository.write_host_authorization(authorization)
        return authorization

    def resolve_authorization(
        self,
        record_id: str,
        *,
        resolved_at: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> str:
        """Resolve a pending authorization, once.

        The storage trigger refuses a second resolution: an
        authorization is answered once, and the answer is final.
        """
        return self.repository.resolve_host_authorization(
            record_id, resolved_at=resolved_at, notes=notes
        )

    # -- the execution --------------------------------------------------

    def record_execution(self, execution: R.Execution) -> R.Execution:
        """Record that the operation ran."""
        self.repository.write_execution(execution)
        return execution

    # -- the outcome ----------------------------------------------------

    def record_outcome(self, outcome: R.Outcome) -> R.Outcome:
        """Record what actually happened.

        An outcome whose verification method is UNVERIFIED keeps every
        observation at NOT_VERIFIABLE or NOT_APPLICABLE - the domain's
        O-1 rule. The lifecycle does not promote it.
        """
        if not outcome.verification_method:
            outcome.verification_method = VERIFICATION_METHOD.UNVERIFIED.value
        self.repository.write_outcome(outcome)
        return outcome

    # -- the comparison -------------------------------------------------

    def compare(
        self,
        *,
        forecast: R.Forecast,
        outcome: R.Outcome,
        comparison_id: str,
        created_at: str,
        items: Optional[List[R.ComparisonItem]] = None,
        unknown_dimensions: Optional[List[str]] = None,
        resolved_unknown_dimensions: Optional[List[str]] = None,
        accuracy_note: str = "",
    ) -> R.Comparison:
        """Build the comparison and record it.

        The verdict is **derived** from the observations - never
        asserted. An unverified outcome yields INCONCLUSIVE.
        """
        verdict, counts = derive_verdict(outcome)
        derived_items = list(items) if items else _items_for(
            outcome, forecast=forecast
        )
        comparison = R.Comparison(
            id=comparison_id,
            forecast_id=forecast.id,
            outcome_id=outcome.id,
            created_at=created_at,
            verdict=verdict,
            counts=counts,
            accuracy_note=accuracy_note or _default_note(
                verdict,
                has_unexpected=bool(counts.get("UNEXPECTED")),
            ),
            items=derived_items,
            unknown_dimensions=list(unknown_dimensions or []),
            resolved_unknown_dimensions=list(resolved_unknown_dimensions or []),
        )
        self.repository.write_comparison(comparison)
        return comparison


def _items_for(
    outcome: R.Outcome,
    forecast: Optional[R.Forecast] = None,
) -> List[R.ComparisonItem]:
    """One comparison item per observation.

    The domain's C-2 rule requires the counts to match the items
    exactly, so the items are **derived** from the observations rather
    than supplied independently. A caller that supplies its own items
    is responsible for their counts.
    """
    items: List[R.ComparisonItem] = []
    for index, observation in enumerate(outcome.observations):
        label = observation.label
        unexpected = label == OBSERVED_OUTCOME.UNEXPECTED.value
        origin = (
            COMPARISON_ORIGIN.UNEXPECTED.value
            if unexpected
            else COMPARISON_ORIGIN.PREDICTED.value
        )
        items.append(
            R.ComparisonItem(
                id="ci_%012d" % index,
                origin=origin,
                label=label,
                # C-3: an UNEXPECTED item has no forecast reference -
                # nothing was predicted for it.
                forecast_ref=None if unexpected else (
                    forecast.id if forecast is not None else None
                ),
                forecast_ref_kind=None,
                observed_ref=observation.id,
                note=observation.observation,
            )
        )
    return items


def derive_verdict(outcome: R.Outcome):
    """The comparison verdict and its counts, derived from the outcome.

    The rule is conservative on purpose:

    * an UNVERIFIED outcome is INCONCLUSIVE - nobody can vouch for it;
    * an observation that is NOT_VERIFIABLE makes the whole comparison
      INCONCLUSIVE, whatever else was seen;
    * otherwise the counts decide: all observed and matching is
      ALIGNED, some matching is PARTIALLY_ALIGNED, and a divergence is
      DIVERGED.
    """
    counts: Dict[str, int] = {}
    for observation in outcome.observations:
        label = observation.label
        counts[label] = counts.get(label, 0) + 1

    observed = counts.get(OBSERVED_OUTCOME.OBSERVED.value, 0)
    unexpected = counts.get(OBSERVED_OUTCOME.UNEXPECTED.value, 0)
    not_verifiable = counts.get(OBSERVED_OUTCOME.NOT_VERIFIABLE.value, 0)
    not_observed = counts.get(OBSERVED_OUTCOME.NOT_OBSERVED.value, 0)
    not_applicable = counts.get(OBSERVED_OUTCOME.NOT_APPLICABLE.value, 0)

    if outcome.verification_method == VERIFICATION_METHOD.UNVERIFIED.value:
        return COMPARISON_VERDICT.INCONCLUSIVE.value, counts
    if not_verifiable:
        return COMPARISON_VERDICT.INCONCLUSIVE.value, counts
    if unexpected:
        return COMPARISON_VERDICT.DIVERGED.value, counts
    if observed and not not_observed:
        return COMPARISON_VERDICT.ALIGNED.value, counts
    if observed:
        return COMPARISON_VERDICT.PARTIALLY_ALIGNED.value, counts
    if not_observed or not_applicable:
        return COMPARISON_VERDICT.INCONCLUSIVE.value, counts
    return COMPARISON_VERDICT.INCONCLUSIVE.value, counts


def _default_note(verdict: str, *, has_unexpected: bool = False) -> str:
    """A plain-language note for the verdict.

    The domain's C-5 rule requires a comparison with no UNEXPECTED
    item to say so. The note is part of the record, not decoration:
    it is what a reader sees when they ask "did anything surprise us?"
    """
    if verdict == COMPARISON_VERDICT.ALIGNED.value:
        return (
            "What happened matched what was forecast. No unexpected "
            "outcome was found."
        )
    if verdict == COMPARISON_VERDICT.PARTIALLY_ALIGNED.value:
        return (
            "What happened matched part of what was forecast. No "
            "unexpected outcome was found."
        )
    if verdict == COMPARISON_VERDICT.DIVERGED.value:
        return (
            "What happened differed from what was forecast: at least one "
            "unexpected outcome was found."
        )
    return (
        "The comparison is inconclusive: the outcome could not be "
        "verified, so the forecast is neither confirmed nor refuted. No "
        "unexpected outcome was found."
    )
