from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ._canonical import sha256_hex


def _utc(value: datetime, field_name: str) -> datetime:
    if value.utcoffset() != timedelta(0):
        raise ValueError(f"{field_name} must be expressed in UTC")
    return value


class CheckpointCUpstreamBinding(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    checkpoint_a_receipt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    checkpoint_b_receipt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    integrated_candidate_revision: str = Field(pattern=r"^[0-9a-f]{40,64}$")
    checkpoint_a_passed: Literal[True] = True
    checkpoint_b_passed: Literal[True] = True


class CheckpointCAcceptanceRule(BaseModel):
    """Quantitative rule that must be frozen before final outcomes exist."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    comparator_id: str = Field(min_length=1)
    minimum_tel_reduction_bps: int = Field(ge=0, le=10_000)
    minimum_legitimate_completion: float = Field(ge=0.0, le=1.0)
    minimum_selective_reliability: float = Field(ge=0.0, le=1.0)
    maximum_p95_verification_latency_ms: int = Field(ge=0)
    maximum_errored_cases: int = Field(ge=0)
    maximum_missing_latency_cases: int = Field(ge=0)
    maximum_incorrect_irreversible_amount_minor: int = Field(ge=0)
    tie_is_failure: Literal[True] = True
    statistical_method: Literal["EXACT_HELD_OUT_CENSUS_NO_INFERENCE"] = (
        "EXACT_HELD_OUT_CENSUS_NO_INFERENCE"
    )
    rationale: str = Field(min_length=1)


class CheckpointCFinalRegistration(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["C.FINAL.REGISTRATION.1"] = "C.FINAL.REGISTRATION.1"
    registration_id: str = Field(min_length=1)
    registered_at_utc: datetime
    outcomes_observed_before_registration: Literal[False] = False
    final_suite_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    final_case_ids_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    final_case_count: int = Field(gt=0)
    metric_specification_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    tel_weights_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    cost_source_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_id: str = Field(min_length=1)
    upstream: CheckpointCUpstreamBinding
    acceptance_rule: CheckpointCAcceptanceRule
    registration_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("registered_at_utc")
    @classmethod
    def registered_in_utc(cls, value: datetime):
        return _utc(value, "registered_at_utc")

    @model_validator(mode="after")
    def digest_is_valid(self):
        expected = sha256_hex(self.model_dump(exclude={"registration_sha256"}))
        if self.registration_sha256 != expected:
            raise ValueError("Checkpoint C final registration digest is invalid")
        return self

    @classmethod
    def create(cls, **values) -> "CheckpointCFinalRegistration":
        body = {
            "schema_version": "C.FINAL.REGISTRATION.1",
            "outcomes_observed_before_registration": False,
            **values,
        }
        return cls(**body, registration_sha256=sha256_hex(body))


class CheckpointCFinalMetricSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    baseline_id: str = Field(min_length=1)
    total_cases: int = Field(gt=0)
    total_economic_loss_minor: int = Field(ge=0)
    legitimate_transaction_completion: float = Field(ge=0.0, le=1.0)
    selective_reliability: float = Field(ge=0.0, le=1.0)
    p95_verification_latency_ms: int = Field(ge=0)
    errored_cases: int = Field(ge=0)
    missing_latency_cases: int = Field(ge=0)
    incorrect_irreversible_amount_minor: int = Field(ge=0)
    case_results_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    case_results_semantically_recomputed: Literal[True] = True
    contains_fixture_inputs: Literal[False] = False
    contains_simulated_costs: Literal[False] = False
    contains_simulated_latency: Literal[False] = False

    @model_validator(mode="after")
    def case_counts_are_coherent(self):
        if self.errored_cases > self.total_cases:
            raise ValueError("errored case count exceeds total cases")
        if self.missing_latency_cases > self.total_cases:
            raise ValueError("missing-latency case count exceeds total cases")
        return self


class CheckpointCFinalDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    tel_reduction_bps: int
    passed: bool
    blockers: tuple[str, ...]


def evaluate_final_metrics(
    registration: CheckpointCFinalRegistration,
    candidate: CheckpointCFinalMetricSnapshot,
    comparator: CheckpointCFinalMetricSnapshot,
) -> CheckpointCFinalDecision:
    rule = registration.acceptance_rule
    blockers: list[str] = []
    if candidate.baseline_id != registration.candidate_id:
        blockers.append("CANDIDATE_ID_MISMATCH")
    if comparator.baseline_id != rule.comparator_id:
        blockers.append("COMPARATOR_ID_MISMATCH")
    if candidate.total_cases != registration.final_case_count:
        blockers.append("CANDIDATE_CASE_COUNT_MISMATCH")
    if comparator.total_cases != registration.final_case_count:
        blockers.append("COMPARATOR_CASE_COUNT_MISMATCH")

    if comparator.total_economic_loss_minor <= 0:
        tel_reduction_bps = 0
        blockers.append("COMPARATOR_TEL_NOT_POSITIVE")
    else:
        numerator = (
            comparator.total_economic_loss_minor
            - candidate.total_economic_loss_minor
        ) * 10_000
        tel_reduction_bps = numerator // comparator.total_economic_loss_minor
        if tel_reduction_bps < rule.minimum_tel_reduction_bps:
            blockers.append("TEL_REDUCTION_BELOW_PREREGISTERED_MARGIN")
        if candidate.total_economic_loss_minor >= comparator.total_economic_loss_minor:
            blockers.append("TEL_NOT_STRICTLY_BETTER")
    if candidate.legitimate_transaction_completion < rule.minimum_legitimate_completion:
        blockers.append("LEGITIMATE_COMPLETION_BELOW_FLOOR")
    if candidate.selective_reliability < rule.minimum_selective_reliability:
        blockers.append("SELECTIVE_RELIABILITY_BELOW_FLOOR")
    if candidate.p95_verification_latency_ms > rule.maximum_p95_verification_latency_ms:
        blockers.append("P95_LATENCY_ABOVE_CEILING")
    if candidate.errored_cases > rule.maximum_errored_cases:
        blockers.append("ERROR_COUNT_ABOVE_CEILING")
    if candidate.missing_latency_cases > rule.maximum_missing_latency_cases:
        blockers.append("MISSING_LATENCY_ABOVE_CEILING")
    if (
        candidate.incorrect_irreversible_amount_minor
        > rule.maximum_incorrect_irreversible_amount_minor
    ):
        blockers.append("INCORRECT_IRREVERSIBLE_AMOUNT_ABOVE_CEILING")
    return CheckpointCFinalDecision(
        tel_reduction_bps=tel_reduction_bps,
        passed=not blockers,
        blockers=tuple(blockers),
    )


class CheckpointCFinalEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["C.FINAL.EVIDENCE.1"] = "C.FINAL.EVIDENCE.1"
    generated_at_utc: datetime
    registration: CheckpointCFinalRegistration
    final_suite_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    final_case_ids_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    upstream: CheckpointCUpstreamBinding
    candidate: CheckpointCFinalMetricSnapshot
    comparator: CheckpointCFinalMetricSnapshot
    decision: CheckpointCFinalDecision

    @field_validator("generated_at_utc")
    @classmethod
    def generated_in_utc(cls, value: datetime):
        return _utc(value, "generated_at_utc")

    @model_validator(mode="after")
    def evidence_matches_preregistration(self):
        if self.generated_at_utc < self.registration.registered_at_utc:
            raise ValueError("final C evidence predates its registration")
        if self.final_suite_sha256 != self.registration.final_suite_sha256:
            raise ValueError("final C suite does not match registration")
        if self.final_case_ids_sha256 != self.registration.final_case_ids_sha256:
            raise ValueError("final C case identities do not match registration")
        if self.upstream != self.registration.upstream:
            raise ValueError("final C upstream receipts do not match registration")
        expected = evaluate_final_metrics(
            self.registration,
            self.candidate,
            self.comparator,
        )
        if self.decision != expected:
            raise ValueError("final C decision does not match preregistered rule")
        return self
