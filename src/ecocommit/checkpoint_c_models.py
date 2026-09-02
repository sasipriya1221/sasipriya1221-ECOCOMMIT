from __future__ import annotations

import json
from datetime import datetime, timedelta
from enum import Enum
from hashlib import sha256
from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator


def _canonical_sha256(model: BaseModel) -> str:
    """Hash a model without relying on presentation whitespace or key order."""

    payload = json.dumps(
        model.model_dump(mode="json", exclude_none=False),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return sha256(payload.encode("utf-8")).hexdigest()


def _is_utc(value: datetime) -> bool:
    return value.utcoffset() == timedelta(0)


class BenchmarkSplit(str, Enum):
    DEVELOPMENT = "DEVELOPMENT"
    VALIDATION = "VALIDATION"
    FINAL_HELD_OUT = "FINAL_HELD_OUT"


class Decision(str, Enum):
    EXECUTE = "EXECUTE"
    BLOCK = "BLOCK"
    ABSTAIN = "ABSTAIN"
    ERROR = "ERROR"


class EvidenceStatus(str, Enum):
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"
    MISSING = "MISSING"
    STALE = "STALE"


class ScenarioSourceKind(str, Enum):
    HAND_AUTHORED = "HAND_AUTHORED"
    SYNTHETIC_SIMULATION = "SYNTHETIC_SIMULATION"
    SANITIZED_RECORDED = "SANITIZED_RECORDED"


class CostProvenance(str, Enum):
    SIMULATED = "SIMULATED"
    PRE_REGISTERED_ASSUMPTION = "PRE_REGISTERED_ASSUMPTION"
    MEASURED_HISTORICAL = "MEASURED_HISTORICAL"


class LatencyProvenance(str, Enum):
    SIMULATED = "SIMULATED"
    MEASURED_LOCAL = "MEASURED_LOCAL"
    MEASURED_PROVIDER = "MEASURED_PROVIDER"
    NOT_AVAILABLE = "NOT_AVAILABLE"


class ReplaySourceKind(str, Enum):
    SYNTHETIC_FIXTURE = "SYNTHETIC_FIXTURE"
    CACHED_PROVIDER_OUTPUT = "CACHED_PROVIDER_OUTPUT"


class ObservationSourceKind(str, Enum):
    SYNTHETIC_FIXTURE = "SYNTHETIC_FIXTURE"
    CACHED_RECORDED = "CACHED_RECORDED"
    LIVE_MEASURED = "LIVE_MEASURED"


class CompensationOutcome(str, Enum):
    NOT_REQUIRED = "NOT_REQUIRED"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


def combine_input_provenance_flags(
    *,
    explicit_fixture_inputs_used: bool,
    simulated_cost_inputs_used: bool,
) -> tuple[bool, bool]:
    """Treat simulated economic assumptions as synthetic benchmark inputs."""

    return (
        explicit_fixture_inputs_used or simulated_cost_inputs_used,
        simulated_cost_inputs_used,
    )


class ArtifactMaturity(str, Enum):
    PRELIMINARY_NOT_FINAL = "PRELIMINARY_NOT_FINAL"


class GateStatus(str, Enum):
    NOT_EVALUATED = "NOT_EVALUATED"


class ComparisonStatus(str, Enum):
    NOT_COMPUTED = "NOT_COMPUTED"


class ScenarioProvenance(BaseModel):
    source_kind: ScenarioSourceKind
    source_reference: str = Field(min_length=1)
    scenario_is_simulated: bool
    notes: str | None = None

    @model_validator(mode="after")
    def synthetic_sources_are_labelled_simulated(self):
        if self.source_kind == ScenarioSourceKind.SYNTHETIC_SIMULATION and not self.scenario_is_simulated:
            raise ValueError("synthetic scenarios must be explicitly labelled simulated")
        return self


class EvidenceObservation(BaseModel):
    evidence_id: str = Field(min_length=1)
    evidence_class: str = Field(min_length=1)
    status: EvidenceStatus
    required: bool = True
    version: str | None = None
    source_kind: ObservationSourceKind
    source_reference: str = Field(min_length=1)
    observation_is_fixture: bool
    # These are deliberately named simulated: deterministic development runs must
    # never be mistaken for end-to-end verification latency measurements.
    simulated_verification_latency_ms: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def fixture_observations_are_labelled(self):
        if (
            self.source_kind == ObservationSourceKind.SYNTHETIC_FIXTURE
            and not self.observation_is_fixture
        ):
            raise ValueError("synthetic evidence observations must be labelled fixture data")
        if (
            self.source_kind != ObservationSourceKind.SYNTHETIC_FIXTURE
            and self.observation_is_fixture
        ):
            raise ValueError("recorded/live evidence observations cannot be labelled fixture data")
        return self


class RiskSignal(BaseModel):
    code: str = Field(min_length=1)
    active: bool = True
    risk_weight_bps: int = Field(ge=0, le=10_000)
    source_reference: str = Field(min_length=1)


class ReferenceOutcome(BaseModel):
    authorized_safe_to_execute: bool
    legitimate_completion_expected: bool
    compensation_outcome_if_unsafe_execution: CompensationOutcome

    @model_validator(mode="after")
    def authorized_execution_must_be_legitimate(self):
        if self.authorized_safe_to_execute and not self.legitimate_completion_expected:
            raise ValueError(
                "authorized safe execution must also expect legitimate completion"
            )
        return self


class EconomicCostProfile(BaseModel):
    provenance: CostProvenance
    unsafe_execution_loss_minor: int = Field(ge=0)
    false_abort_loss_minor: int = Field(ge=0)
    abstention_review_loss_minor: int = Field(ge=0)
    compensation_cost_minor: int = Field(ge=0)
    currency: str = Field(default="INR", pattern=r"^[A-Z]{3}$")
    basis: str = Field(min_length=1)


class BenchmarkCase(BaseModel):
    schema_version: Literal["checkpoint-c-case.v2"] = "checkpoint-c-case.v2"
    case_id: str = Field(min_length=1)
    scenario_family: str = Field(min_length=1)
    description: str = Field(min_length=1)
    instruction_text: str = Field(min_length=1)
    instruction_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    split: BenchmarkSplit
    requested_amount_minor: int = Field(gt=0)
    irreversible_exposure_minor: int = Field(ge=0)
    policy_limit_minor: int = Field(gt=0)
    base_risk_bps: int = Field(ge=0, le=10_000)
    evidence: list[EvidenceObservation] = Field(default_factory=list)
    risk_signals: list[RiskSignal] = Field(default_factory=list)
    reference_outcome: ReferenceOutcome
    costs: EconomicCostProfile
    provenance: ScenarioProvenance
    tags: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_case_invariants(self):
        instruction_digest = sha256(self.instruction_text.encode("utf-8")).hexdigest()
        if self.instruction_sha256 != instruction_digest:
            raise ValueError("instruction digest does not match frozen instruction text")
        if self.irreversible_exposure_minor > self.requested_amount_minor:
            raise ValueError("irreversible exposure cannot exceed the requested amount")
        evidence_ids = [item.evidence_id for item in self.evidence]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("evidence ids must be unique within a case")
        signal_codes = [item.code for item in self.risk_signals]
        if len(signal_codes) != len(set(signal_codes)):
            raise ValueError("risk signal codes must be unique within a case")
        if len(self.tags) != len(set(self.tags)):
            raise ValueError("case tags must be unique")
        return self


class BenchmarkSuite(BaseModel):
    schema_version: Literal["checkpoint-c-suite.v2"] = "checkpoint-c-suite.v2"
    suite_id: str = Field(min_length=1)
    suite_version: str = Field(min_length=1)
    description: str = Field(min_length=1)
    maturity: Literal[ArtifactMaturity.PRELIMINARY_NOT_FINAL] = (
        ArtifactMaturity.PRELIMINARY_NOT_FINAL
    )
    definitions_frozen_at_utc: datetime
    eligible_for_final_claims: Literal[False] = False
    cases: list[BenchmarkCase] = Field(min_length=1)
    contains_live_checkpoint_a_outputs: Literal[False] = False

    @model_validator(mode="after")
    def unique_case_ids(self):
        if not _is_utc(self.definitions_frozen_at_utc):
            raise ValueError("definitions_frozen_at_utc must be expressed in UTC")
        case_ids = [case.case_id for case in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("benchmark case ids must be unique")
        currencies = {case.costs.currency for case in self.cases}
        if len(currencies) != 1:
            raise ValueError("all cases in one suite must use the same loss currency")
        return self

    def canonical_hash(self) -> str:
        return _canonical_sha256(self)


class StaticRulesRegistration(BaseModel):
    baseline_type: Literal["STATIC_RULES"] = "STATIC_RULES"
    baseline_id: str = Field(min_length=1)
    amount_ceiling_minor: int = Field(gt=0)
    blocked_signal_codes: list[str] = Field(default_factory=list)
    simulated_decision_overhead_ms: int = Field(default=1, ge=0)

    @model_validator(mode="after")
    def unique_blocked_signals(self):
        if len(self.blocked_signal_codes) != len(set(self.blocked_signal_codes)):
            raise ValueError("blocked static signal codes must be unique")
        return self


class RegisteredAgentDecision(BaseModel):
    case_id: str = Field(min_length=1)
    decision: Decision
    reason_codes: list[str] = Field(min_length=1)
    verification_latency_ms: int | None = Field(default=None, ge=0)
    latency_provenance: LatencyProvenance
    source_output_text: str | None = None
    source_output_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def unique_reason_codes(self):
        if len(self.reason_codes) != len(set(self.reason_codes)):
            raise ValueError("registered agent reason codes must be unique")
        if self.source_output_text is not None:
            output_digest = sha256(self.source_output_text.encode("utf-8")).hexdigest()
            if self.source_output_sha256 != output_digest:
                raise ValueError("agent source-output digest does not match retained text")
        if self.decision == Decision.ERROR:
            if (
                self.verification_latency_ms is not None
                or self.latency_provenance != LatencyProvenance.NOT_AVAILABLE
            ):
                raise ValueError("errored agent outputs must label latency unavailable")
        elif (
            self.verification_latency_ms is None
            or self.latency_provenance == LatencyProvenance.NOT_AVAILABLE
        ):
            raise ValueError("successful agent outputs must account for latency")
        return self


class AgentReplayRegistrationBase(BaseModel):
    baseline_id: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    prompt_protocol_reference: str = Field(min_length=1)
    prompt_protocol_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    response_set_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    replay_source_kind: ReplaySourceKind
    source_reference: str = Field(min_length=1)
    outputs_are_synthetic_fixture: bool
    decisions: list[RegisteredAgentDecision] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_replay_provenance_and_coverage(self):
        case_ids = [decision.case_id for decision in self.decisions]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("registered agent replay case ids must be unique")
        if self.replay_source_kind == ReplaySourceKind.SYNTHETIC_FIXTURE:
            if not self.outputs_are_synthetic_fixture:
                raise ValueError("synthetic agent replays must be explicitly labelled fixture data")
            if any(
                decision.latency_provenance
                not in {LatencyProvenance.SIMULATED, LatencyProvenance.NOT_AVAILABLE}
                for decision in self.decisions
            ):
                raise ValueError("synthetic agent replay latency must be labelled simulated")
            if any(decision.source_output_text is None for decision in self.decisions):
                raise ValueError("synthetic agent replays must retain their fixture outputs")
        elif self.outputs_are_synthetic_fixture:
            raise ValueError("cached provider outputs cannot be labelled synthetic fixture data")
        elif any(
            decision.latency_provenance
            not in {LatencyProvenance.MEASURED_PROVIDER, LatencyProvenance.NOT_AVAILABLE}
            for decision in self.decisions
        ):
            raise ValueError("cached provider replay latency must be measured provider latency")
        response_payload = json.dumps(
            [decision.model_dump(mode="json") for decision in self.decisions],
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        expected_response_set_digest = sha256(response_payload.encode("utf-8")).hexdigest()
        if self.response_set_sha256 != expected_response_set_digest:
            raise ValueError("response-set digest does not match registered agent decisions")
        return self


class NaiveAgentReplayRegistration(AgentReplayRegistrationBase):
    baseline_type: Literal["NAIVE_AGENT_REPLAY"] = "NAIVE_AGENT_REPLAY"


class PromptGuardrailReplayRegistration(AgentReplayRegistrationBase):
    baseline_type: Literal["PROMPT_GUARDRAIL_REPLAY"] = "PROMPT_GUARDRAIL_REPLAY"
    guardrail_protocol_reference: str = Field(min_length=1)
    guardrail_protocol_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class DynamicRiskEvidenceRegistration(BaseModel):
    baseline_type: Literal["DYNAMIC_DETERMINISTIC_WORKFLOW"] = (
        "DYNAMIC_DETERMINISTIC_WORKFLOW"
    )
    baseline_id: str = Field(min_length=1)
    policy_version: str = Field(default="dynamic-policy.v1", min_length=1)
    evidence_protocol_version: str = Field(default="evidence-protocol.v1", min_length=1)
    strongest_dynamic_deterministic_workflow: Literal[True] = True
    selection_rationale: str = Field(min_length=1)
    execute_risk_max_bps: int = Field(default=2_500, ge=0, le=10_000)
    block_risk_min_bps: int = Field(default=7_000, ge=0, le=10_000)
    verified_evidence_credit_bps: int = Field(default=100, ge=0, le=10_000)
    failed_evidence_penalty_bps: int = Field(default=3_000, ge=0, le=10_000)
    missing_evidence_penalty_bps: int = Field(default=1_000, ge=0, le=10_000)
    stale_evidence_penalty_bps: int = Field(default=1_500, ge=0, le=10_000)
    block_on_required_failure: Literal[True] = True
    abstain_on_required_missing_or_stale: Literal[True] = True
    simulated_decision_overhead_ms: int = Field(default=2, ge=0)

    @model_validator(mode="after")
    def thresholds_do_not_overlap(self):
        if self.execute_risk_max_bps >= self.block_risk_min_bps:
            raise ValueError("execute risk maximum must be below the block risk minimum")
        return self

    def canonical_hash(self) -> str:
        return _canonical_sha256(self)


class ConservativeAbstainRegistration(BaseModel):
    baseline_type: Literal["CONSERVATIVE_ABSTAIN"] = "CONSERVATIVE_ABSTAIN"
    baseline_id: str = Field(min_length=1)
    simulated_decision_overhead_ms: int = Field(default=0, ge=0)


BaselineRegistration = Annotated[
    NaiveAgentReplayRegistration
    | PromptGuardrailReplayRegistration
    | StaticRulesRegistration
    | DynamicRiskEvidenceRegistration
    | ConservativeAbstainRegistration,
    Field(discriminator="baseline_type"),
]


class EconomicLossWeights(BaseModel):
    schema_version: Literal["checkpoint-c-tel-weights.v1"] = (
        "checkpoint-c-tel-weights.v1"
    )
    unsafe_execution_weight_bps: int = Field(gt=0, le=100_000)
    false_abort_weight_bps: int = Field(gt=0, le=100_000)
    abstention_review_weight_bps: int = Field(gt=0, le=100_000)
    compensation_cost_weight_bps: int = Field(gt=0, le=100_000)
    basis: str = Field(min_length=1)


class MetricSpecification(BaseModel):
    schema_version: Literal["checkpoint-c-metrics.v2"] = "checkpoint-c-metrics.v2"
    selective_reliability_formula: Literal[
        "correct non-abstaining decisions / all non-abstaining decisions"
    ] = "correct non-abstaining decisions / all non-abstaining decisions"
    autonomous_coverage_formula: Literal[
        "non-abstaining decisions / all cases"
    ] = "non-abstaining decisions / all cases"
    legitimate_completion_formula: Literal[
        "executed cases where legitimate completion is expected / all cases where legitimate completion is expected"
    ] = "executed cases where legitimate completion is expected / all cases where legitimate completion is expected"
    false_abort_formula: Literal[
        "blocked cases authorized safe to execute / all cases authorized safe to execute"
    ] = (
        "blocked cases authorized safe to execute / all cases authorized safe to execute"
    )
    total_economic_loss_formula: Literal[
        "weighted unsafe execution loss + weighted false-abort loss + weighted abstention-review loss + weighted compensation cost"
    ] = (
        "weighted unsafe execution loss + weighted false-abort loss + weighted abstention-review loss + weighted compensation cost"
    )
    total_economic_loss_rounding: Literal[
        "round half up to minor units per weighted component"
    ] = "round half up to minor units per weighted component"
    error_loss_treatment: Literal[
        "charge the case abstention-review loss"
    ] = "charge the case abstention-review loss"
    error_reliability_treatment: Literal[
        "exclude from autonomous decisions and retain as an error"
    ] = "exclude from autonomous decisions and retain as an error"
    error_latency_treatment: Literal[
        "record missing latency, exclude from total and p95, and count the missing observation"
    ] = (
        "record missing latency, exclude from total and p95, and count the missing observation"
    )
    loss_weights: EconomicLossWeights
    latency_percentile_method: Literal["nearest-rank p95"] = "nearest-rank p95"
    monetary_unit: Literal["minor currency units"] = "minor currency units"


class BenchmarkPlan(BaseModel):
    schema_version: Literal["checkpoint-c-plan.v2"] = "checkpoint-c-plan.v2"
    plan_id: str = Field(min_length=1)
    plan_revision: str = Field(min_length=1)
    description: str = Field(min_length=1)
    registered_at_utc: datetime
    maturity: Literal[ArtifactMaturity.PRELIMINARY_NOT_FINAL] = ArtifactMaturity.PRELIMINARY_NOT_FINAL
    suite_id: str = Field(min_length=1)
    suite_version: str = Field(min_length=1)
    suite_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    seed: int = Field(ge=0, le=2**63 - 1)
    baselines: list[BaselineRegistration] = Field(min_length=1)
    metrics: MetricSpecification
    checkpoint_a_final_pass_required: Literal[True] = True
    checkpoint_b_final_pass_required: Literal[True] = True
    eligible_for_final_claims: Literal[False] = False

    @model_validator(mode="after")
    def validate_plan(self):
        if not _is_utc(self.registered_at_utc):
            raise ValueError("registered_at_utc must be expressed in UTC")
        baseline_ids = [baseline.baseline_id for baseline in self.baselines]
        if len(baseline_ids) != len(set(baseline_ids)):
            raise ValueError("baseline ids must be unique")
        required_types = {
            "NAIVE_AGENT_REPLAY",
            "PROMPT_GUARDRAIL_REPLAY",
            "STATIC_RULES",
            "DYNAMIC_DETERMINISTIC_WORKFLOW",
        }
        baseline_types = [baseline.baseline_type for baseline in self.baselines]
        missing = required_types.difference(baseline_types)
        duplicated = {
            baseline_type
            for baseline_type in required_types
            if baseline_types.count(baseline_type) != 1
        }
        if missing or duplicated:
            raise ValueError(
                "benchmark plan must register exactly one naive-agent replay, "
                "prompt-guardrail replay, static deterministic baseline, and "
                "strongest dynamic deterministic workflow"
            )
        return self

    def canonical_hash(self) -> str:
        return _canonical_sha256(self)


class BaselineDecision(BaseModel):
    baseline_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    decision: Decision
    reason_codes: list[str] = Field(min_length=1)
    calculated_risk_bps: int | None = Field(default=None, ge=0, le=10_000)
    examined_evidence_ids: list[str] = Field(default_factory=list)
    verification_latency_ms: int | None = Field(default=None, ge=0)
    latency_provenance: LatencyProvenance

    @model_validator(mode="after")
    def latency_value_matches_provenance(self):
        if len(self.reason_codes) != len(set(self.reason_codes)):
            raise ValueError("baseline decision reason codes must be unique")
        if len(self.examined_evidence_ids) != len(set(self.examined_evidence_ids)):
            raise ValueError("examined evidence ids must be unique")
        if self.latency_provenance == LatencyProvenance.NOT_AVAILABLE:
            if self.verification_latency_ms is not None:
                raise ValueError("unavailable latency cannot carry a numeric value")
        elif self.verification_latency_ms is None:
            raise ValueError("available latency provenance requires a numeric value")
        if self.decision == Decision.ERROR and self.latency_provenance != LatencyProvenance.NOT_AVAILABLE:
            raise ValueError("errored baseline decisions must label latency unavailable")
        if self.decision != Decision.ERROR and self.latency_provenance == LatencyProvenance.NOT_AVAILABLE:
            raise ValueError("successful baseline decisions must account for latency")
        return self


class EconomicLossComponents(BaseModel):
    unsafe_execution_loss_minor: int = Field(ge=0)
    false_abort_loss_minor: int = Field(ge=0)
    abstention_review_loss_minor: int = Field(ge=0)
    compensation_cost_minor: int = Field(ge=0)
    total_economic_loss_minor: int = Field(ge=0)

    @model_validator(mode="after")
    def total_matches_components(self):
        component_total = (
            self.unsafe_execution_loss_minor
            + self.false_abort_loss_minor
            + self.abstention_review_loss_minor
            + self.compensation_cost_minor
        )
        if self.total_economic_loss_minor != component_total:
            raise ValueError("economic loss total must equal its four components")
        return self


class CaseBenchmarkResult(BaseModel):
    baseline_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    decision: Decision
    reason_codes: list[str] = Field(min_length=1)
    calculated_risk_bps: int | None = Field(default=None, ge=0, le=10_000)
    examined_evidence_ids: list[str] = Field(default_factory=list)
    verification_latency_ms: int | None = Field(default=None, ge=0)
    latency_provenance: LatencyProvenance
    correct_autonomous_decision: bool | None
    legitimate_transaction_completed: bool
    false_abort: bool
    compensation_triggered: bool
    compensation_outcome: CompensationOutcome
    incorrect_irreversible_amount_minor: int = Field(ge=0)
    raw_loss_components: EconomicLossComponents
    weighted_loss_components: EconomicLossComponents
    economic_loss_minor: int = Field(ge=0)
    cost_provenance: CostProvenance

    @model_validator(mode="after")
    def total_matches_weighted_components(self):
        if self.economic_loss_minor != self.weighted_loss_components.total_economic_loss_minor:
            raise ValueError("case economic loss must equal weighted loss components")
        return self


class BenchmarkMetrics(BaseModel):
    total_cases: int = Field(ge=0)
    autonomous_decisions: int = Field(ge=0)
    correct_autonomous_decisions: int = Field(ge=0)
    executed_decisions: int = Field(ge=0)
    blocked_decisions: int = Field(ge=0)
    abstained_decisions: int = Field(ge=0)
    errored_decisions: int = Field(ge=0)
    legitimate_cases: int = Field(ge=0)
    legitimate_transactions_completed: int = Field(ge=0)
    false_abort_eligible_cases: int = Field(ge=0)
    false_aborts: int = Field(ge=0)
    compensation_events: int = Field(ge=0)
    autonomous_coverage: float = Field(ge=0.0, le=1.0)
    execution_coverage: float = Field(ge=0.0, le=1.0)
    selective_reliability: float | None = Field(default=None, ge=0.0, le=1.0)
    legitimate_transaction_completion: float | None = Field(default=None, ge=0.0, le=1.0)
    false_abort_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    incorrect_irreversible_amount_minor: int = Field(ge=0)
    unsafe_execution_loss_minor: int = Field(ge=0)
    false_abort_loss_minor: int = Field(ge=0)
    abstention_review_loss_minor: int = Field(ge=0)
    compensation_cost_minor: int = Field(ge=0)
    total_economic_loss_minor: int = Field(ge=0)
    total_verification_latency_ms: int = Field(ge=0)
    latency_observations: int = Field(ge=0)
    missing_latency_observations: int = Field(ge=0)
    p95_verification_latency_ms: int | None = Field(default=None, ge=0)
    latency_provenance: list[LatencyProvenance] = Field(min_length=1)
    currency: str = Field(pattern=r"^[A-Z]{3}$")

    @model_validator(mode="after")
    def total_matches_loss_components(self):
        component_total = (
            self.unsafe_execution_loss_minor
            + self.false_abort_loss_minor
            + self.abstention_review_loss_minor
            + self.compensation_cost_minor
        )
        if self.total_economic_loss_minor != component_total:
            raise ValueError("aggregate economic loss must equal its four components")
        return self


class BaselinePreliminarySummary(BaseModel):
    baseline_id: str = Field(min_length=1)
    preliminary_metrics: BenchmarkMetrics


class BenchmarkRunProvenance(BaseModel):
    runner_version: Literal["checkpoint-c-runner.v2"] = "checkpoint-c-runner.v2"
    generated_at_utc: datetime
    plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    suite_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    seed: int = Field(ge=0, le=2**63 - 1)
    deterministic_case_order: list[str] = Field(min_length=1)
    code_revision: str = Field(min_length=7)
    working_tree_dirty: bool
    python_version: str = Field(min_length=1)
    platform: str = Field(min_length=1)
    dependency_manifest_scope: Literal["ALL_INSTALLED_PYTHON_DISTRIBUTIONS"] = (
        "ALL_INSTALLED_PYTHON_DISTRIBUTIONS"
    )
    dependency_versions: dict[str, str] = Field(min_length=1)
    live_checkpoint_a_outputs_used: Literal[False] = False
    replay_source_kinds: list[ReplaySourceKind] = Field(min_length=1)
    synthetic_fixture_inputs_used: bool
    simulated_cost_inputs_used: bool
    latency_provenance: list[LatencyProvenance] = Field(min_length=1)
    all_latency_data_is_simulated: bool
    contains_simulated_latency: bool
    errored_case_count: int = Field(ge=0)
    run_complete_without_errors: bool

    @model_validator(mode="after")
    def generated_time_is_aware(self):
        if not _is_utc(self.generated_at_utc):
            raise ValueError("generated_at_utc must be expressed in UTC")
        if len(self.replay_source_kinds) != len(set(self.replay_source_kinds)):
            raise ValueError("replay source kinds must be unique")
        if len(self.latency_provenance) != len(set(self.latency_provenance)):
            raise ValueError("latency provenance values must be unique")
        required_distributions = {"ecocommit", "pydantic", "pydantic-core"}
        if not required_distributions.issubset(self.dependency_versions):
            raise ValueError("dependency manifest is missing required runtime distributions")
        if any(not version for version in self.dependency_versions.values()):
            raise ValueError("dependency manifest versions cannot be empty")
        if self.run_complete_without_errors != (self.errored_case_count == 0):
            raise ValueError("run error summary is inconsistent")
        return self


class BenchmarkArtifact(BaseModel):
    schema_version: Literal["checkpoint-c-artifact.v2"] = "checkpoint-c-artifact.v2"
    checkpoint: Literal["C"] = "C"
    maturity: Literal[ArtifactMaturity.PRELIMINARY_NOT_FINAL] = ArtifactMaturity.PRELIMINARY_NOT_FINAL
    notice: Literal[
        "PRELIMINARY DEVELOPMENT EVIDENCE ONLY; NOT A FINAL COMPARISON OR CHECKPOINT PASS"
    ] = "PRELIMINARY DEVELOPMENT EVIDENCE ONLY; NOT A FINAL COMPARISON OR CHECKPOINT PASS"
    checkpoint_c_gate_status: Literal[GateStatus.NOT_EVALUATED] = GateStatus.NOT_EVALUATED
    comparison_status: Literal[ComparisonStatus.NOT_COMPUTED] = ComparisonStatus.NOT_COMPUTED
    final_comparison_numbers_published: Literal[False] = False
    prerequisites_satisfied: Literal[False] = False
    plan: BenchmarkPlan
    suite: BenchmarkSuite
    provenance: BenchmarkRunProvenance
    preliminary_summaries: list[BaselinePreliminarySummary] = Field(min_length=1)
    case_results: list[CaseBenchmarkResult] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_artifact_integrity(self):
        suite_hash = self.suite.canonical_hash()
        plan_hash = self.plan.canonical_hash()
        if (
            self.plan.suite_id != self.suite.suite_id
            or self.plan.suite_version != self.suite.suite_version
            or self.plan.suite_sha256 != suite_hash
        ):
            raise ValueError("artifact plan and suite identity/hash do not match")
        if self.suite.definitions_frozen_at_utc > self.plan.registered_at_utc:
            raise ValueError("benchmark plan cannot predate the frozen suite definitions")
        if (
            self.provenance.generated_at_utc < self.plan.registered_at_utc
            or self.provenance.generated_at_utc < self.suite.definitions_frozen_at_utc
        ):
            raise ValueError("benchmark run cannot predate its plan or frozen suite definitions")
        if self.provenance.plan_sha256 != plan_hash:
            raise ValueError("artifact provenance plan hash does not match the embedded plan")
        if self.provenance.suite_sha256 != suite_hash:
            raise ValueError("artifact provenance suite hash does not match the embedded suite")
        if self.provenance.seed != self.plan.seed:
            raise ValueError("artifact provenance seed does not match the registered plan")

        case_ids = [case.case_id for case in self.suite.cases]
        case_order = self.provenance.deterministic_case_order
        if len(case_order) != len(set(case_order)) or set(case_order) != set(case_ids):
            raise ValueError("artifact deterministic case order must contain every suite case exactly once")

        baseline_ids = [registration.baseline_id for registration in self.plan.baselines]
        summary_ids = [summary.baseline_id for summary in self.preliminary_summaries]
        if summary_ids != baseline_ids:
            raise ValueError("artifact summaries must exactly match registered baseline order")
        if any(
            summary.preliminary_metrics.total_cases != len(case_ids)
            for summary in self.preliminary_summaries
        ):
            raise ValueError("artifact summary case counts must match the suite")

        expected_pairs = [
            (baseline_id, case_id)
            for baseline_id in baseline_ids
            for case_id in case_order
        ]
        actual_pairs = [(result.baseline_id, result.case_id) for result in self.case_results]
        if actual_pairs != expected_pairs:
            raise ValueError(
                "artifact results must contain each registered baseline/case pair exactly once in deterministic order"
            )

        latency_provenance = sorted(
            {result.latency_provenance for result in self.case_results},
            key=lambda item: item.value,
        )
        if self.provenance.latency_provenance != latency_provenance:
            raise ValueError("artifact latency provenance summary does not match case results")
        simulated_only = all(
            result.latency_provenance == LatencyProvenance.SIMULATED
            for result in self.case_results
        )
        contains_simulated = any(
            result.latency_provenance == LatencyProvenance.SIMULATED
            for result in self.case_results
        )
        if (
            self.provenance.all_latency_data_is_simulated != simulated_only
            or self.provenance.contains_simulated_latency != contains_simulated
        ):
            raise ValueError("artifact simulated-latency summary does not match case results")

        replay_registrations = [
            registration
            for registration in self.plan.baselines
            if isinstance(registration, AgentReplayRegistrationBase)
        ]
        replay_source_kinds = sorted(
            {registration.replay_source_kind for registration in replay_registrations},
            key=lambda item: item.value,
        )
        if self.provenance.replay_source_kinds != replay_source_kinds:
            raise ValueError("artifact replay source summary does not match the plan")
        simulated_cost_inputs_used = any(
            case.costs.provenance == CostProvenance.SIMULATED
            for case in self.suite.cases
        )
        explicit_fixture_inputs_used = (
            any(
                registration.outputs_are_synthetic_fixture
                for registration in replay_registrations
            )
            or any(case.provenance.scenario_is_simulated for case in self.suite.cases)
            or any(
                observation.observation_is_fixture
                for case in self.suite.cases
                for observation in case.evidence
            )
        )
        fixture_inputs_used, simulated_cost_inputs_used = combine_input_provenance_flags(
            explicit_fixture_inputs_used=explicit_fixture_inputs_used,
            simulated_cost_inputs_used=simulated_cost_inputs_used,
        )
        if self.provenance.synthetic_fixture_inputs_used != fixture_inputs_used:
            raise ValueError("artifact fixture-input summary does not match the plan")
        if self.provenance.simulated_cost_inputs_used != simulated_cost_inputs_used:
            raise ValueError("artifact simulated-cost summary does not match the suite")

        # Recompute every deterministic/replayed row and every summary from the
        # frozen plan and suite. Structural coverage alone is not enough: without
        # this check, a changed decision or loss component could still validate.
        from .checkpoint_c_baselines import build_baseline, evaluate_with_error_retention
        from .checkpoint_c_metrics import aggregate_metrics, score_case

        case_by_id = {case.case_id: case for case in self.suite.cases}
        result_index = {
            (result.baseline_id, result.case_id): result for result in self.case_results
        }
        summary_index = {
            summary.baseline_id: summary for summary in self.preliminary_summaries
        }
        for registration in self.plan.baselines:
            if isinstance(registration, AgentReplayRegistrationBase):
                replay_case_ids = {decision.case_id for decision in registration.decisions}
                if replay_case_ids != set(case_ids):
                    raise ValueError(
                        "registered agent replay must contain every suite case exactly once"
                    )
            baseline = build_baseline(registration)
            expected_results = []
            for case_id in case_order:
                case = case_by_id[case_id]
                expected = score_case(
                    case,
                    evaluate_with_error_retention(baseline, case),
                    self.plan.metrics,
                )
                if result_index[(registration.baseline_id, case_id)] != expected:
                    raise ValueError(
                        "artifact case result does not match the frozen baseline, case, and TEL specification"
                    )
                expected_results.append(expected)
            expected_metrics = aggregate_metrics(
                [case_by_id[case_id] for case_id in case_order],
                expected_results,
            )
            if summary_index[registration.baseline_id].preliminary_metrics != expected_metrics:
                raise ValueError(
                    "artifact summary does not match recomputed case results"
                )
        errored_case_count = sum(
            result.decision == Decision.ERROR for result in self.case_results
        )
        if self.provenance.errored_case_count != errored_case_count:
            raise ValueError("artifact run error summary does not match case results")
        return self

    def canonical_hash(self) -> str:
        return _canonical_sha256(self)
