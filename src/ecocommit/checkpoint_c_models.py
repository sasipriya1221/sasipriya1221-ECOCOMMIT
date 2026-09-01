from __future__ import annotations

import json
from datetime import datetime
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


class BenchmarkSplit(str, Enum):
    DEVELOPMENT = "DEVELOPMENT"
    VALIDATION = "VALIDATION"
    FINAL_HELD_OUT = "FINAL_HELD_OUT"


class Decision(str, Enum):
    EXECUTE = "EXECUTE"
    BLOCK = "BLOCK"
    ABSTAIN = "ABSTAIN"


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
    # These are deliberately named simulated: deterministic development runs must
    # never be mistaken for end-to-end verification latency measurements.
    simulated_verification_latency_ms: int = Field(default=0, ge=0)


class RiskSignal(BaseModel):
    code: str = Field(min_length=1)
    active: bool = True
    risk_weight_bps: int = Field(ge=0, le=10_000)
    source_reference: str = Field(min_length=1)


class ReferenceOutcome(BaseModel):
    authorized_safe_to_execute: bool
    legitimate_completion_expected: bool

    @model_validator(mode="after")
    def v1_uses_binary_execute_or_block_ground_truth(self):
        if self.authorized_safe_to_execute != self.legitimate_completion_expected:
            raise ValueError(
                "checkpoint-c case schema v1 requires legitimate completion exactly when execution is authorized and safe"
            )
        return self


class EconomicCostProfile(BaseModel):
    provenance: CostProvenance
    unsafe_execution_loss_minor: int = Field(ge=0)
    missed_legitimate_completion_loss_minor: int = Field(ge=0)
    abstention_review_loss_minor: int = Field(ge=0)
    currency: str = Field(default="INR", pattern=r"^[A-Z]{3}$")
    basis: str = Field(min_length=1)


class BenchmarkCase(BaseModel):
    schema_version: Literal["checkpoint-c-case.v1"] = "checkpoint-c-case.v1"
    case_id: str = Field(min_length=1)
    scenario_family: str = Field(min_length=1)
    description: str = Field(min_length=1)
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
    schema_version: Literal["checkpoint-c-suite.v1"] = "checkpoint-c-suite.v1"
    suite_id: str = Field(min_length=1)
    suite_version: str = Field(min_length=1)
    description: str = Field(min_length=1)
    cases: list[BenchmarkCase] = Field(min_length=1)
    contains_live_checkpoint_a_outputs: Literal[False] = False

    @model_validator(mode="after")
    def unique_case_ids(self):
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


class DynamicRiskEvidenceRegistration(BaseModel):
    baseline_type: Literal["DYNAMIC_RISK_EVIDENCE"] = "DYNAMIC_RISK_EVIDENCE"
    baseline_id: str = Field(min_length=1)
    execute_risk_max_bps: int = Field(default=2_500, ge=0, le=10_000)
    block_risk_min_bps: int = Field(default=7_000, ge=0, le=10_000)
    verified_evidence_credit_bps: int = Field(default=100, ge=0, le=10_000)
    failed_evidence_penalty_bps: int = Field(default=3_000, ge=0, le=10_000)
    missing_evidence_penalty_bps: int = Field(default=1_000, ge=0, le=10_000)
    stale_evidence_penalty_bps: int = Field(default=1_500, ge=0, le=10_000)
    block_on_required_failure: bool = True
    abstain_on_required_missing_or_stale: bool = True
    simulated_decision_overhead_ms: int = Field(default=2, ge=0)

    @model_validator(mode="after")
    def thresholds_do_not_overlap(self):
        if self.execute_risk_max_bps >= self.block_risk_min_bps:
            raise ValueError("execute risk maximum must be below the block risk minimum")
        return self


class ConservativeAbstainRegistration(BaseModel):
    baseline_type: Literal["CONSERVATIVE_ABSTAIN"] = "CONSERVATIVE_ABSTAIN"
    baseline_id: str = Field(min_length=1)
    simulated_decision_overhead_ms: int = Field(default=0, ge=0)


BaselineRegistration = Annotated[
    StaticRulesRegistration | DynamicRiskEvidenceRegistration | ConservativeAbstainRegistration,
    Field(discriminator="baseline_type"),
]


class MetricSpecification(BaseModel):
    schema_version: Literal["checkpoint-c-metrics.v1"] = "checkpoint-c-metrics.v1"
    selective_reliability_formula: Literal[
        "correct non-abstaining decisions / all non-abstaining decisions"
    ] = "correct non-abstaining decisions / all non-abstaining decisions"
    autonomous_coverage_formula: Literal[
        "non-abstaining decisions / all cases"
    ] = "non-abstaining decisions / all cases"
    legitimate_completion_formula: Literal[
        "executed cases where legitimate completion is expected / all cases where legitimate completion is expected"
    ] = "executed cases where legitimate completion is expected / all cases where legitimate completion is expected"
    total_economic_loss_formula: Literal[
        "unsafe execution loss + missed legitimate completion loss + abstention review loss"
    ] = "unsafe execution loss + missed legitimate completion loss + abstention review loss"
    latency_percentile_method: Literal["nearest-rank p95"] = "nearest-rank p95"
    monetary_unit: Literal["minor currency units"] = "minor currency units"


class BenchmarkPlan(BaseModel):
    schema_version: Literal["checkpoint-c-plan.v1"] = "checkpoint-c-plan.v1"
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
    metrics: MetricSpecification = Field(default_factory=MetricSpecification)
    checkpoint_a_final_pass_required: Literal[True] = True
    eligible_for_final_claims: Literal[False] = False

    @model_validator(mode="after")
    def validate_plan(self):
        if self.registered_at_utc.utcoffset() is None:
            raise ValueError("registered_at_utc must be timezone-aware")
        baseline_ids = [baseline.baseline_id for baseline in self.baselines]
        if len(baseline_ids) != len(set(baseline_ids)):
            raise ValueError("baseline ids must be unique")
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
    verification_latency_ms: int = Field(ge=0)
    latency_provenance: LatencyProvenance


class CaseBenchmarkResult(BaseModel):
    baseline_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    decision: Decision
    reason_codes: list[str] = Field(min_length=1)
    calculated_risk_bps: int | None = Field(default=None, ge=0, le=10_000)
    examined_evidence_ids: list[str] = Field(default_factory=list)
    verification_latency_ms: int = Field(ge=0)
    latency_provenance: LatencyProvenance
    correct_autonomous_decision: bool | None
    legitimate_transaction_completed: bool
    incorrect_irreversible_amount_minor: int = Field(ge=0)
    economic_loss_minor: int = Field(ge=0)
    cost_provenance: CostProvenance


class BenchmarkMetrics(BaseModel):
    total_cases: int = Field(ge=0)
    autonomous_decisions: int = Field(ge=0)
    correct_autonomous_decisions: int = Field(ge=0)
    executed_decisions: int = Field(ge=0)
    blocked_decisions: int = Field(ge=0)
    abstained_decisions: int = Field(ge=0)
    legitimate_cases: int = Field(ge=0)
    legitimate_transactions_completed: int = Field(ge=0)
    autonomous_coverage: float = Field(ge=0.0, le=1.0)
    execution_coverage: float = Field(ge=0.0, le=1.0)
    selective_reliability: float | None = Field(default=None, ge=0.0, le=1.0)
    legitimate_transaction_completion: float | None = Field(default=None, ge=0.0, le=1.0)
    incorrect_irreversible_amount_minor: int = Field(ge=0)
    total_economic_loss_minor: int = Field(ge=0)
    p95_verification_latency_ms: int = Field(ge=0)
    latency_provenance: list[LatencyProvenance] = Field(min_length=1)
    currency: str = Field(pattern=r"^[A-Z]{3}$")


class BaselinePreliminarySummary(BaseModel):
    baseline_id: str = Field(min_length=1)
    preliminary_metrics: BenchmarkMetrics


class BenchmarkRunProvenance(BaseModel):
    runner_version: Literal["checkpoint-c-runner.v1"] = "checkpoint-c-runner.v1"
    generated_at_utc: datetime
    plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    suite_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    seed: int = Field(ge=0, le=2**63 - 1)
    deterministic_case_order: list[str] = Field(min_length=1)
    code_revision: str | None = None
    python_version: str = Field(min_length=1)
    platform: str = Field(min_length=1)
    live_checkpoint_a_outputs_used: Literal[False] = False
    latency_data_is_simulated: bool

    @model_validator(mode="after")
    def generated_time_is_aware(self):
        if self.generated_at_utc.utcoffset() is None:
            raise ValueError("generated_at_utc must be timezone-aware")
        return self


class BenchmarkArtifact(BaseModel):
    schema_version: Literal["checkpoint-c-artifact.v1"] = "checkpoint-c-artifact.v1"
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

        simulated_only = all(
            result.latency_provenance == LatencyProvenance.SIMULATED
            for result in self.case_results
        )
        if self.provenance.latency_data_is_simulated != simulated_only:
            raise ValueError("artifact latency provenance summary does not match case results")
        return self

    def canonical_hash(self) -> str:
        return _canonical_sha256(self)
