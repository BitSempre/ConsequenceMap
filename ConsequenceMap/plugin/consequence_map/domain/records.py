"""Entity dataclasses and their normative validation rules.

One dataclass per entity of specification section 2, each carrying the
rules that the acceptance criteria assign to it. Validation raises
`ValidationError`; a rule is never satisfied by a silent default.

Rules implemented here:
  P-1..P-4   proposal (section 2.3)
  F-1..F-6   forecast (section 2.4)
  E-1..E-2   execution (section 2.8)
  O-1..O-2   outcome (section 2.9)
  C-1..C-6   comparison (section 2.10)
  PD-1..PD-6 product_decision (section 2.6)
  AUTH-1..   host_authorization (section 2.5)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence

from .enums import (
    ALTERNATIVE_DISPOSITION,
    AUTHORIZATION_PROVENANCE,
    AUTHORIZATION_REASON,
    AUTHORIZATION_STATE,
    AUTHORIZED_BY,
    COMPARISON_ORIGIN,
    COMPARISON_VERDICT,
    CONFIDENCE,
    EVIDENCE_CLASS,
    IMPACT_CLASS,
    OBSERVED_OUTCOME,
    PRODUCT_DECISION_STATE,
    RELATION,
    REVERSIBILITY,
    SEVERITY,
    SOURCE_KIND,
    TARGET_KIND,
    VERIFICATION_METHOD,
)
from .validation import (
    ValidationError,
    require_fields,
    validate_bool,
    validate_closed_set,
    validate_enum_field,
    validate_identifier,
    validate_timestamp,
)

#: The confidence ordering used by AC-DATA-17 (lowest confidence among
#: material claims). HIGH is the most confident.
CONFIDENCE_RANK = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}

#: The severity ordering used by F-3 (severity >= MODERATE).
SEVERITY_RANK = {"LOW": 0, "MODERATE": 1, "HIGH": 2, "CRITICAL": 3}

#: The comparison item labels that a comparison's counts may contain.
COMPARISON_COUNT_LABELS = (
    "OBSERVED",
    "NOT_OBSERVED",
    "UNEXPECTED",
    "NOT_VERIFIABLE",
    "NOT_APPLICABLE",
)

#: `forecast_ref_kind` values. `alternative` is INVALID (C-4).
FORECAST_REF_KINDS = ("evidence", "impact", "risk")


@dataclass
class Proposal:
    """A proposal: what is about to happen (specification section 2.3)."""

    id: str
    version: int
    created_at: str
    actor: str
    action: str
    operation: str
    target_kind: str
    target: Dict[str, Any]
    scope: Dict[str, Any]
    preconditions: Optional[List[str]] = None
    expected_outputs: Optional[List[str]] = None
    external_side_effects: Optional[List[str]] = None
    rollback: Optional[str] = None
    session_id: Optional[str] = None
    turn_id: Optional[str] = None
    tool_call_id: Optional[str] = None

    def validate(self) -> "Proposal":
        """Apply P-1, P-2, P-3 and P-4."""
        require_fields(
            self,
            ["id", "version", "created_at", "actor", "action", "operation",
             "target_kind", "target", "scope"],
            "proposal",
        )
        validate_identifier(self.id, "prop_", "proposal.id")
        validate_timestamp(self.created_at, "proposal.created_at")
        validate_closed_set(self.actor, ("agent", "user", "system"), "proposal.actor")
        validate_closed_set(
            self.operation,
            ("FILE_WRITE", "FILE_DELETE", "FILE_PATCH", "COMMAND",
             "DEPENDENCY_CHANGE", "CONFIG_CHANGE", "EXTERNAL_CALL", "OTHER"),
            "proposal.operation",
        )
        validate_enum_field("TARGET_KIND", self.target_kind, "proposal.target_kind")

        # P-1: scope.excluded MUST be present.
        if "excluded" not in self.scope:
            raise ValidationError("proposal.scope is missing 'excluded' (P-1)")
        if not isinstance(self.scope["excluded"], list):
            raise ValidationError("proposal.scope.excluded must be a list (P-1)")
        if not self.scope["excluded"]:
            raise ValidationError("proposal.scope.excluded must be non-empty (P-1)")
        if not isinstance(self.scope.get("included", []), list):
            raise ValidationError("proposal.scope.included must be a list")

        # P-2 / P-3: target shape per target_kind.
        if self.target_kind == "FILESYSTEM":
            paths = self.target.get("paths")
            if not isinstance(paths, list) or not paths:
                raise ValidationError(
                    "a FILESYSTEM target requires a non-empty paths list (P-2)"
                )
        # P-3: a non-FILESYSTEM target is NOT rejected for lacking a path.
        #       Nothing to enforce - the absence of 'paths' is legitimate.
        return self


@dataclass
class Evidence:
    """One evidence row (specification section 2.4)."""

    id: str
    claim: str
    classification: str
    source_kind: str
    source_ref: str
    observed_at: str
    confidence: str
    limitations: Optional[str] = None

    def validate(self) -> "Evidence":
        require_fields(
            self,
            ["id", "claim", "classification", "source_kind", "source_ref",
             "observed_at", "confidence"],
            "evidence",
        )
        validate_identifier(self.id, "ev_", "evidence.id")
        validate_enum_field("EVIDENCE_CLASS", self.classification, "evidence.classification")
        validate_enum_field("SOURCE_KIND", self.source_kind, "evidence.source_kind")
        validate_enum_field("CONFIDENCE", self.confidence, "evidence.confidence")
        validate_timestamp(self.observed_at, "evidence.observed_at")
        # AC-DATA-10: every evidence row carries a source reference. An
        # empty string is not a reference (the same reading as O-2 for an
        # observation's evidence_ref).
        if not self.source_ref:
            raise ValidationError(
                "every evidence row carries a non-empty source reference (AC-DATA-10)"
            )
        return self


@dataclass
class Impact:
    """One impact edge (specification section 2.4)."""

    id: str
    target: str
    impact_class: str
    relation: str
    classification: str
    severity_contribution: str
    confidence: str
    reason: str
    observable: bool

    def validate(self) -> "Impact":
        require_fields(
            self,
            ["id", "target", "impact_class", "relation", "classification",
             "severity_contribution", "confidence", "reason", "observable"],
            "impact",
        )
        validate_identifier(self.id, "im_", "impact.id")
        validate_enum_field("IMPACT_CLASS", self.impact_class, "impact.impact_class")
        validate_enum_field("RELATION", self.relation, "impact.relation")
        validate_enum_field("EVIDENCE_CLASS", self.classification, "impact.classification")
        validate_enum_field("SEVERITY", self.severity_contribution, "impact.severity_contribution")
        validate_enum_field("CONFIDENCE", self.confidence, "impact.confidence")
        validate_bool(self.observable, "impact.observable")

        # F-2: an INFERRED edge MUST have classification INFERENCE.
        if self.relation == "INFERRED" and self.classification != "INFERENCE":
            raise ValidationError(
                "an INFERRED edge must have classification INFERENCE (F-2)"
            )
        # F-4: an observable:false edge MUST have UNKNOWN and LOW.
        if not self.observable:
            if self.classification != "UNKNOWN":
                raise ValidationError(
                    "an observable:false edge must have classification UNKNOWN (F-4)"
                )
            if self.confidence != "LOW":
                raise ValidationError(
                    "an observable:false edge must have confidence LOW (F-4)"
                )
        return self


@dataclass
class Risk:
    """The forecast's single risk row (specification section 2.4)."""

    severity: str
    confidence: str
    reversibility: str
    reason: str
    escalation_rule: str
    requires_human_approval: bool
    dimension_caveats: List[str] = field(default_factory=list)

    def validate(self) -> "Risk":
        require_fields(
            self,
            ["severity", "confidence", "reversibility", "reason",
             "escalation_rule", "requires_human_approval"],
            "risk",
        )
        validate_enum_field("SEVERITY", self.severity, "risk.severity")
        validate_enum_field("CONFIDENCE", self.confidence, "risk.confidence")
        validate_enum_field("REVERSIBILITY", self.reversibility, "risk.reversibility")
        validate_bool(self.requires_human_approval, "risk.requires_human_approval")
        if not isinstance(self.dimension_caveats, list):
            raise ValidationError("risk.dimension_caveats must be a list")
        return self


@dataclass
class Alternative:
    """One alternative (specification section 2.4)."""

    id: str
    description: str
    expected_benefit: str
    impact_reduction: str
    tradeoffs: str
    residual_uncertainty: str
    recommended: bool

    def validate(self) -> "Alternative":
        require_fields(
            self,
            ["id", "description", "expected_benefit", "impact_reduction",
             "tradeoffs", "residual_uncertainty", "recommended"],
            "alternative",
        )
        validate_identifier(self.id, "alt_", "alternative.id")
        validate_bool(self.recommended, "alternative.recommended")
        return self


@dataclass
class Unknown:
    """One unknown dimension (specification section 2.4)."""

    id: str
    question: str
    why_it_matters: str
    evidence_that_would_resolve: str

    def validate(self) -> "Unknown":
        require_fields(
            self,
            ["id", "question", "why_it_matters", "evidence_that_would_resolve"],
            "unknown",
        )
        validate_identifier(self.id, "unk_", "unknown.id")
        return self


@dataclass
class Forecast:
    """A forecast: an immutable, pre-action prediction (section 2.4)."""

    id: str
    proposal_id: str
    proposal_version: int
    created_at: str
    generator: Dict[str, Any]
    confidence_overall: str
    summary: str
    content_hash: str
    sealed_at: Optional[str] = None
    # The five collections are ABSENT by default. AC-DATA-09 requires a
    # forecast to RECORD all of them, so an absent collection is a
    # validation error. An EMPTY collection is present but carries no
    # rows - that is what makes F-3 (severity >= MODERATE requires at
    # least one alternative) a non-vacuous rule rather than a dead one.
    evidence: Optional[List[Evidence]] = None
    impact: Optional[List[Impact]] = None
    risk: Optional[Risk] = None
    alternatives: Optional[List[Alternative]] = None
    unknowns: Optional[List[Unknown]] = None

    def validate(self) -> "Forecast":
        """Apply F-1..F-5 and AC-DATA-09, AC-DATA-10, AC-DATA-17."""
        require_fields(
            self,
            ["id", "proposal_id", "proposal_version", "created_at", "generator",
             "confidence_overall", "summary", "content_hash"],
            "forecast",
        )
        validate_identifier(self.id, "fc_", "forecast.id")
        validate_timestamp(self.created_at, "forecast.created_at")
        validate_enum_field("CONFIDENCE", self.confidence_overall, "forecast.confidence_overall")
        # AC-DATA-09: every collection must be RECORDED. "Missing" means
        # absent (None), not empty - F-3 and F-5 depend on the distinction.
        for name in ("evidence", "impact", "alternatives", "unknowns"):
            collection = getattr(self, name)
            if collection is None:
                raise ValidationError(
                    f"forecast is missing its {name} collection (AC-DATA-09)"
                )
            if not isinstance(collection, list):
                raise ValidationError(
                    f"forecast.{name} must be a list (AC-DATA-09)"
                )
        if self.risk is None:
            raise ValidationError("forecast is missing its risk (AC-DATA-09)")

        for item in self.evidence:
            item.validate()
        for item in self.impact:
            item.validate()
        self.risk.validate()
        for item in self.alternatives:
            item.validate()
        for item in self.unknowns:
            item.validate()

        # F-1: an UNKNOWN_RELATION edge requires at least one UNKNOWN evidence.
        if any(i.relation == "UNKNOWN_RELATION" for i in self.impact):
            if not any(e.classification == "UNKNOWN" for e in self.evidence):
                raise ValidationError(
                    "an UNKNOWN_RELATION edge requires at least one UNKNOWN "
                    "evidence entry (F-1)"
                )

        # F-3: severity >= MODERATE requires at least one alternative.
        if SEVERITY_RANK[self.risk.severity] >= SEVERITY_RANK["MODERATE"]:
            if not self.alternatives:
                raise ValidationError(
                    "severity >= MODERATE requires at least one alternative (F-3)"
                )

        # F-5: any observable:false edge requires non-empty dimension_caveats.
        if any(not i.observable for i in self.impact):
            if not self.risk.dimension_caveats:
                raise ValidationError(
                    "an observable:false edge requires non-empty "
                    "risk.dimension_caveats (F-5)"
                )

        # AC-DATA-17: confidence_overall == lowest confidence among material claims.
        self._validate_overall_confidence()
        return self

    def _validate_overall_confidence(self) -> None:
        material = [e.confidence for e in self.evidence] + [
            i.confidence for i in self.impact
        ]
        if not material:
            raise ValidationError(
                "confidence_overall cannot be derived: no material claims (AC-DATA-17)"
            )
        lowest = min(material, key=lambda c: CONFIDENCE_RANK[c])
        if self.confidence_overall != lowest:
            raise ValidationError(
                f"confidence_overall must be the lowest confidence among material "
                f"claims ({lowest}), got {self.confidence_overall} (AC-DATA-17)"
            )


@dataclass
class HostAuthorization:
    """Record A: what the host authorized (specification section 2.5)."""

    id: str
    forecast_id: str
    proposal_id: str
    proposal_version: int
    state: str
    provenance: str
    authorized_by: str
    observed_choice: str
    observed_via: str
    reason: str
    created_at: str
    escalation_expected: bool
    tool_call_id: Optional[str] = None
    rule_key: Optional[str] = None
    pattern_key: Optional[str] = None
    resolved_at: Optional[str] = None
    notes: Optional[str] = None
    supersedes: Optional[str] = None

    def validate(self) -> "HostAuthorization":
        """Apply AUTH-1, AUTH-1a..AUTH-1d and the state-specific rules."""
        require_fields(
            self,
            ["id", "forecast_id", "proposal_id", "proposal_version", "state",
             "provenance", "authorized_by", "observed_choice", "observed_via",
             "reason", "created_at", "escalation_expected"],
            "host_authorization",
        )
        validate_identifier(self.id, "auth_", "host_authorization.id")
        validate_enum_field("AUTHORIZATION_STATE", self.state, "host_authorization.state")
        validate_enum_field("AUTHORIZATION_PROVENANCE", self.provenance,
                            "host_authorization.provenance")
        validate_enum_field("AUTHORIZED_BY", self.authorized_by,
                            "host_authorization.authorized_by")
        validate_enum_field("AUTHORIZATION_REASON", self.reason,
                            "host_authorization.reason")
        validate_timestamp(self.created_at, "host_authorization.created_at")
        validate_bool(self.escalation_expected, "host_authorization.escalation_expected")

        # AUTH-1b: an empty tool_call_id is ABSENT, not a match.
        if not self.tool_call_id:
            self.tool_call_id = None
        if not self.rule_key:
            self.rule_key = None
        if not self.pattern_key:
            self.pattern_key = None

        if self.state == "HUMAN_APPROVED":
            if not self.escalation_expected:
                raise ValidationError(
                    "HUMAN_APPROVED requires escalation_expected = true (AUTH-1)"
                )
            if self.observed_choice not in ("once", "session", "always"):
                raise ValidationError(
                    "HUMAN_APPROVED requires an observed choice in "
                    "{once, session, always} (AUTH-1)"
                )
            # AUTH-1a / AUTH-1d: exactly ONE channel, present and matching.
            pattern_match = bool(self.pattern_key) and self._pattern_matches()
            tool_match = bool(self.tool_call_id)
            if not pattern_match and not tool_match:
                raise ValidationError(
                    "HUMAN_APPROVED requires exactly one present and matching "
                    "attribution channel: pattern_key or tool_call_id (AUTH-1d)"
                )
        if self.state == "HUMAN_REJECTED" and self.observed_choice != "deny":
            raise ValidationError(
                "HUMAN_REJECTED requires an observed choice of 'deny' (AUTH-2)"
            )
        if self.state == "APPROVAL_CANCELLED" and self.observed_choice != "cancelled":
            raise ValidationError(
                "APPROVAL_CANCELLED requires an observed choice of 'cancelled' (AUTH-4)"
            )
        if self.state == "GUARDIAN_APPROVED" and self.observed_choice != "smart_approve":
            raise ValidationError(
                "GUARDIAN_APPROVED requires an observed choice of 'smart_approve' (AUTH-13)"
            )
        if self.state == "GUARDIAN_REJECTED" and self.observed_choice != "smart_deny":
            raise ValidationError(
                "GUARDIAN_REJECTED requires an observed choice of 'smart_deny' (AUTH-14)"
            )
        if self.state == "TRANSPORT_FAILED" and self.observed_choice != "notify_failed":
            raise ValidationError(
                "TRANSPORT_FAILED requires an observed choice of 'notify_failed' (AUTH-15)"
            )
        if self.state in ("GUARDIAN_APPROVED", "GUARDIAN_REJECTED"):
            if self.authorized_by != "GUARDIAN_LLM":
                raise ValidationError(
                    "a Guardian state requires authorized_by = GUARDIAN_LLM (AUTH-11)"
                )
        if self.state == "AUTOMATICALLY_ALLOWED" and self.authorized_by == "GUARDIAN_LLM":
            raise ValidationError(
                "AUTOMATICALLY_ALLOWED excludes the Guardian (AUTH-5b)"
            )
        if self.state == "APPROVAL_NOT_REQUIRED" and self.escalation_expected:
            raise ValidationError(
                "APPROVAL_NOT_REQUIRED requires escalation_expected = false (AUTH-7)"
            )
        return self

    def _pattern_matches(self) -> bool:
        """True when pattern_key is the plugin_rule form carrying this forecast."""
        if not self.pattern_key or not self.forecast_id:
            return False
        expected_prefix = f"plugin_rule:cm:{self.forecast_id}:"
        return self.pattern_key.startswith(expected_prefix)


@dataclass
class ProductDecision:
    """Record B: ConsequenceMap's own decision (specification section 2.6)."""

    id: str
    forecast_id: str
    proposal_id: str
    proposal_version: int
    state: str
    decided_by: str
    decided_at: str
    surface: str
    scope_note: Optional[str] = None
    supersedes: Optional[str] = None

    def validate(self) -> "ProductDecision":
        """Apply PD-1..PD-6."""
        require_fields(
            self,
            ["id", "forecast_id", "proposal_id", "proposal_version", "state",
             "decided_by", "decided_at", "surface"],
            "product_decision",
        )
        validate_identifier(self.id, "pdec_", "product_decision.id")
        validate_enum_field("PRODUCT_DECISION_STATE", self.state, "product_decision.state")
        validate_closed_set(self.decided_by, ("user", "system"), "product_decision.decided_by")
        validate_closed_set(
            self.surface, ("desktop", "slash_command", "agent_tool", "none"),
            "product_decision.surface",
        )
        validate_timestamp(self.decided_at, "product_decision.decided_at")
        # PD-5: ACCEPTED requires decided_by = user.
        if self.state == "ACCEPTED" and self.decided_by != "user":
            raise ValidationError(
                "a product_decision with state ACCEPTED requires decided_by = user (PD-5)"
            )
        # PD-4: only an explicit human interaction may produce ACCEPTED/REJECTED.
        if self.state in ("ACCEPTED", "REJECTED") and self.decided_by != "user":
            raise ValidationError(
                "ACCEPTED or REJECTED requires decided_by = user (PD-4)"
            )
        return self


def execution_status_for_result(host_result: Any) -> str:
    """Map a host-reported result to an execution status (E-1).

    When the host reported NO result, the status is `UNKNOWN_STATUS` -
    an issued command is never `COMPLETED`. A reported result maps to
    `COMPLETED`.
    """
    if host_result is None:
        return "UNKNOWN_STATUS"
    return "COMPLETED"


@dataclass
class ToolCall:
    """One tool call within an execution (specification section 2.8)."""

    tool_name: str
    args_digest: str
    result_digest: str
    status: str
    duration_ms: int
    error_type: Optional[str] = None

    def validate(self) -> "ToolCall":
        require_fields(
            self,
            ["tool_name", "args_digest", "result_digest", "status", "duration_ms"],
            "tool_call",
        )
        # Section 8.2: raw arguments and results are NEVER persisted; only digests.
        for name, value in (("args_digest", self.args_digest),
                            ("result_digest", self.result_digest)):
            if not _looks_like_sha256(value):
                raise ValidationError(
                    f"{name} must be a sha256 hex digest; raw values are never "
                    f"persisted (section 8.2)"
                )
        return self


def _looks_like_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(c in "0123456789abcdef" for c in value.lower())
    )


@dataclass
class Execution:
    """An execution attempt (specification section 2.8)."""

    id: str
    forecast_id: str
    started_at: str
    status: str
    source: str
    ended_at: Optional[str] = None
    host_authorization_id: Optional[str] = None
    product_decision_id: Optional[str] = None
    trigger_tool: Optional[str] = None
    tool_call_id: Optional[str] = None
    error_type: Optional[str] = None
    tool_calls: List[ToolCall] = field(default_factory=list)

    def validate(self) -> "Execution":
        """Apply E-1 and E-2."""
        require_fields(self, ["id", "forecast_id", "started_at", "status", "source"],
                       "execution")
        validate_identifier(self.id, "exe_", "execution.id")
        validate_timestamp(self.started_at, "execution.started_at")
        validate_closed_set(
            self.status,
            ("COMPLETED", "PARTIAL", "FAILED", "BLOCKED", "UNKNOWN_STATUS"),
            "execution.status",
        )
        validate_closed_set(self.source, ("hook", "tool", "manual"), "execution.source")
        for call in self.tool_calls:
            call.validate()
        # E-2: a BLOCKED execution records the host's error_type.
        if self.status == "BLOCKED":
            if not self.error_type:
                raise ValidationError(
                    "a BLOCKED execution records the host error_type (E-2)"
                )
            if self.error_type not in ("plugin_block", "tool_error"):
                raise ValidationError(
                    "a BLOCKED execution distinguishes plugin_block from "
                    f"tool_error; got {self.error_type!r} (E-2)"
                )
        return self


@dataclass
class OutcomeObservation:
    """One observation (specification section 2.9)."""

    id: str
    target: str
    observation: str
    label: str
    evidence_source_kind: str
    evidence_ref: str
    confidence: str

    def validate(self) -> "OutcomeObservation":
        require_fields(
            self,
            ["id", "target", "observation", "label", "evidence_source_kind",
             "evidence_ref", "confidence"],
            "outcome_observation",
        )
        validate_identifier(self.id, "ob_", "outcome_observation.id")
        validate_enum_field("OBSERVED_OUTCOME", self.label, "outcome_observation.label")
        validate_enum_field("SOURCE_KIND", self.evidence_source_kind,
                            "outcome_observation.evidence_source_kind")
        validate_enum_field("CONFIDENCE", self.confidence, "outcome_observation.confidence")
        # O-2: an OBSERVED observation MUST carry a non-empty evidence_ref.
        if self.label == "OBSERVED" and not self.evidence_ref:
            raise ValidationError(
                "an OBSERVED observation must carry a non-empty evidence_ref (O-2)"
            )
        return self


@dataclass
class Outcome:
    """A verification pass (specification section 2.9)."""

    id: str
    forecast_id: str
    execution_id: str
    recorded_at: str
    recorded_by: str
    verification_method: str
    summary: str
    observations: List[OutcomeObservation] = field(default_factory=list)

    def validate(self) -> "Outcome":
        """Apply O-1 and O-2."""
        require_fields(
            self,
            ["id", "forecast_id", "execution_id", "recorded_at", "recorded_by",
             "verification_method", "summary"],
            "outcome",
        )
        validate_identifier(self.id, "out_", "outcome.id")
        validate_timestamp(self.recorded_at, "outcome.recorded_at")
        validate_enum_field("VERIFICATION_METHOD", self.verification_method,
                            "outcome.verification_method")
        for obs in self.observations:
            obs.validate()
        # O-1: UNVERIFIED forces every observation to NOT_VERIFIABLE/NOT_APPLICABLE.
        if self.verification_method == "UNVERIFIED":
            for obs in self.observations:
                if obs.label not in ("NOT_VERIFIABLE", "NOT_APPLICABLE"):
                    raise ValidationError(
                        "verification_method UNVERIFIED forces every observation "
                        f"to NOT_VERIFIABLE or NOT_APPLICABLE; got {obs.label} (O-1)"
                    )
        return self


@dataclass
class ComparisonItem:
    """One comparison item (specification section 2.10)."""

    id: str
    origin: str
    label: str
    forecast_ref: Optional[str] = None
    forecast_ref_kind: Optional[str] = None
    observed_ref: Optional[str] = None
    note: str = ""

    def validate(self) -> "ComparisonItem":
        """Apply C-3 and C-4."""
        require_fields(self, ["id", "origin", "label"], "comparison_item")
        validate_identifier(self.id, "ci_", "comparison_item.id")
        validate_enum_field("COMPARISON_ORIGIN", self.origin, "comparison_item.origin")
        validate_enum_field("OBSERVED_OUTCOME", self.label, "comparison_item.label")
        # C-4: forecast_ref_kind = alternative is invalid.
        if self.forecast_ref_kind == "alternative":
            raise ValidationError(
                "forecast_ref_kind = alternative is invalid (C-4)"
            )
        if self.forecast_ref_kind is not None:
            validate_closed_set(self.forecast_ref_kind, FORECAST_REF_KINDS,
                                "comparison_item.forecast_ref_kind")
        # C-3: origin = UNEXPECTED => forecast_ref NULL and observed_ref non-null.
        if self.origin == "UNEXPECTED":
            if self.forecast_ref is not None:
                raise ValidationError(
                    "an UNEXPECTED item has a null forecast_ref (C-3)"
                )
            if not self.observed_ref:
                raise ValidationError(
                    "an UNEXPECTED item has a non-null observed_ref (C-3)"
                )
        return self


@dataclass
class Comparison:
    """A comparison of forecast against outcome (specification section 2.10)."""

    id: str
    forecast_id: str
    outcome_id: str
    created_at: str
    verdict: str
    counts: Dict[str, int]
    accuracy_note: str
    items: List[ComparisonItem] = field(default_factory=list)
    # C-6: for each forecast UNKNOWN dimension, whether it was resolved.
    unknown_dimensions: List[str] = field(default_factory=list)
    resolved_unknown_dimensions: List[str] = field(default_factory=list)

    def validate(self) -> "Comparison":
        """Apply C-1, C-2, C-3, C-4, C-5 and C-6."""
        require_fields(
            self,
            ["id", "forecast_id", "outcome_id", "created_at", "verdict",
             "counts", "accuracy_note"],
            "comparison",
        )
        validate_identifier(self.id, "cmp_", "comparison.id")
        validate_timestamp(self.created_at, "comparison.created_at")
        validate_enum_field("COMPARISON_VERDICT", self.verdict, "comparison.verdict")
        for item in self.items:
            item.validate()

        # C-2: counts equals the per-label item counts; their sum equals the item count.
        actual = {label: 0 for label in COMPARISON_COUNT_LABELS}
        for item in self.items:
            actual[item.label] = actual.get(item.label, 0) + 1
        declared = {k: int(v) for k, v in self.counts.items()}
        for label in COMPARISON_COUNT_LABELS:
            if declared.get(label, 0) != actual[label]:
                raise ValidationError(
                    f"counts[{label}] is {declared.get(label, 0)} but the items "
                    f"contain {actual[label]} (C-2)"
                )
        if sum(declared.values()) != len(self.items):
            raise ValidationError(
                f"the sum of counts ({sum(declared.values())}) must equal the "
                f"item count ({len(self.items)}) (C-2)"
            )
        # C-6: every resolved dimension must be one of the forecast's
        # unknown dimensions, and no dimension may be resolved twice.
        for resolved in self.resolved_unknown_dimensions:
            if self.unknown_dimensions and resolved not in self.unknown_dimensions:
                raise ValidationError(
                    f"a resolved dimension must be one of the forecast's "
                    f"unknown dimensions; {resolved!r} is not (C-6)"
                )
        if len(set(self.resolved_unknown_dimensions)) != len(self.resolved_unknown_dimensions):
            raise ValidationError(
                "a dimension may not be recorded as resolved twice (C-6)"
            )
        # C-5: at least one UNEXPECTED item, or the note states none were found.
        unexpected = [i for i in self.items if i.origin == "UNEXPECTED"]
        if not unexpected and "no unexpected" not in self.accuracy_note.lower():
            raise ValidationError(
                "a comparison with no UNEXPECTED item must state so in its "
                "accuracy_note (C-5)"
            )
        return self


@dataclass
class AlternativeEvaluation:
    """An evaluation of one alternative (specification section 2.11)."""

    id: str
    forecast_id: str
    alternative_id: str
    disposition: str
    evaluated_at: str
    rationale: Optional[str] = None

    def validate(self) -> "AlternativeEvaluation":
        require_fields(
            self,
            ["id", "forecast_id", "alternative_id", "disposition", "evaluated_at"],
            "alternative_evaluation",
        )
        validate_identifier(self.id, "ae_", "alternative_evaluation.id")
        validate_enum_field("ALTERNATIVE_DISPOSITION", self.disposition,
                            "alternative_evaluation.disposition")
        validate_timestamp(self.evaluated_at, "alternative_evaluation.evaluated_at")
        return self
