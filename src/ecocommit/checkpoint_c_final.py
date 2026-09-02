from __future__ import annotations

from datetime import datetime, timedelta
from hashlib import sha256
import os
from pathlib import Path
import re
import tempfile
from typing import Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ._canonical import sha256_hex, strict_json_loads
from .checkpoint_a_evidence import CheckpointAEvidenceReceipt
from .checkpoint_b_evidence import CheckpointBEvidenceReceipt
from .checkpoint_c_metrics import aggregate_metrics, score_case
from .checkpoint_c_models import (
    BaselineDecision,
    BenchmarkCase,
    BenchmarkSplit,
    CaseBenchmarkResult,
    CostProvenance,
    LatencyProvenance,
    MetricSpecification,
)


MAX_FINAL_INPUT_BYTES = 8 * 1024 * 1024
_FinalInput = TypeVar("_FinalInput", bound=BaseModel)
_GITHUB_ACTIONS_EVIDENCE_REFERENCE = re.compile(
    r"^github-actions://[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/"
    r"runs/[0-9]{1,20}/artifacts/[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$"
)


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
    minimum_autonomous_coverage: float = Field(ge=0.0, le=1.0)
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
    candidate_execution_protocol_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    comparator_execution_protocol_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    comparator_selection_receipt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
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


class CheckpointCFinalSuite(BaseModel):
    """Real final-held-out cases frozen before either compared output exists."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["C.FINAL.SUITE.1"] = "C.FINAL.SUITE.1"
    suite_id: str = Field(min_length=1)
    suite_version: str = Field(min_length=1)
    description: str = Field(min_length=1)
    definitions_frozen_at_utc: datetime
    cases: tuple[BenchmarkCase, ...] = Field(min_length=1)
    eligible_for_final_claims: Literal[True] = True

    @field_validator("definitions_frozen_at_utc")
    @classmethod
    def frozen_in_utc(cls, value: datetime):
        return _utc(value, "definitions_frozen_at_utc")

    @model_validator(mode="after")
    def final_cases_are_real_unique_and_coherent(self):
        case_ids = [case.case_id for case in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("final held-out case ids must be unique")
        if any(case.split != BenchmarkSplit.FINAL_HELD_OUT for case in self.cases):
            raise ValueError("final suite may contain only FINAL_HELD_OUT cases")
        if any(case.provenance.scenario_is_simulated for case in self.cases):
            raise ValueError("simulated scenarios are forbidden in the final suite")
        if any(case.costs.provenance == CostProvenance.SIMULATED for case in self.cases):
            raise ValueError("simulated costs are forbidden in the final suite")
        if any(
            observation.observation_is_fixture
            for case in self.cases
            for observation in case.evidence
        ):
            raise ValueError("fixture evidence is forbidden in the final suite")
        if any(
            observation.simulated_verification_latency_ms != 0
            for case in self.cases
            for observation in case.evidence
        ):
            raise ValueError("simulated observation latency is forbidden in the final suite")
        currencies = {case.costs.currency for case in self.cases}
        if len(currencies) != 1:
            raise ValueError("all final cases must use one loss currency")
        if not any(
            case.reference_outcome.legitimate_completion_expected
            for case in self.cases
        ):
            raise ValueError("final suite must contain a legitimate-completion case")
        return self

    def canonical_hash(self) -> str:
        return sha256_hex(self)


def final_case_ids_sha256(suite: CheckpointCFinalSuite) -> str:
    """Hash final identities in their preregistered suite order."""

    return sha256_hex({"schema_version": "C.FINAL.CASE.IDS.1", "case_ids": [
        case.case_id for case in suite.cases
    ]})


def final_cost_source_manifest_sha256(suite: CheckpointCFinalSuite) -> str:
    """Bind every case's economic costs and provenance to the registration."""

    return sha256_hex({
        "schema_version": "C.FINAL.COST.SOURCES.1",
        "cases": [
            {"case_id": case.case_id, "costs": case.costs}
            for case in suite.cases
        ],
    })


class CheckpointCFinalDecisionManifest(BaseModel):
    """Raw per-case decisions bound to one frozen registration and execution."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["C.FINAL.DECISIONS.1"] = "C.FINAL.DECISIONS.1"
    execution_id: str = Field(min_length=1)
    registration_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    final_suite_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    final_case_ids_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    baseline_id: str = Field(min_length=1)
    generated_at_utc: datetime
    decisions: tuple[BaselineDecision, ...] = Field(min_length=1)
    manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("generated_at_utc")
    @classmethod
    def generated_in_utc(cls, value: datetime):
        return _utc(value, "generated_at_utc")

    @model_validator(mode="after")
    def rows_are_unique_real_and_digest_bound(self):
        case_ids = [decision.case_id for decision in self.decisions]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("final decision case ids must be unique")
        if any(decision.baseline_id != self.baseline_id for decision in self.decisions):
            raise ValueError("final decision baseline ids must match the manifest")
        if any(
            decision.latency_provenance == LatencyProvenance.SIMULATED
            for decision in self.decisions
        ):
            raise ValueError("simulated latency is forbidden in final decisions")
        expected = sha256_hex(self.model_dump(exclude={"manifest_sha256"}))
        if self.manifest_sha256 != expected:
            raise ValueError("Checkpoint C final decision manifest digest is invalid")
        return self

    @classmethod
    def create(cls, **values) -> "CheckpointCFinalDecisionManifest":
        body = {"schema_version": "C.FINAL.DECISIONS.1", **values}
        return cls(**body, manifest_sha256=sha256_hex(body))


class CheckpointCFinalDecisionReceipt(BaseModel):
    """Execution provenance for one raw decision manifest.

    The protocol and comparator-selection digests are frozen in the registration;
    this receipt cannot choose them after final outcomes are visible.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["C.FINAL.DECISION.RECEIPT.1"] = (
        "C.FINAL.DECISION.RECEIPT.1"
    )
    role: Literal["CANDIDATE", "COMPARATOR"]
    execution_id: str = Field(min_length=1)
    execution_nonce_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    run_attempt: Literal[1] = 1
    baseline_id: str = Field(min_length=1)
    source_revision: str = Field(pattern=r"^[0-9a-f]{40,64}$")
    registration_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    final_suite_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    final_case_ids_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    decision_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    execution_protocol_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    comparator_selection_receipt_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    case_count: int = Field(gt=0, strict=True)
    generated_at_utc: datetime
    evidence_reference: str = Field(min_length=1, max_length=512)
    fixture_inputs_used: Literal[False] = False
    simulated_inputs_used: Literal[False] = False
    complete_manifest_retained: Literal[True] = True
    receipt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("generated_at_utc")
    @classmethod
    def receipt_generated_in_utc(cls, value: datetime):
        return _utc(value, "generated_at_utc")

    @field_validator("evidence_reference")
    @classmethod
    def reference_is_safe(cls, value: str):
        if any(character.isspace() or ord(character) < 33 for character in value):
            raise ValueError("decision evidence reference must not contain whitespace")
        if _GITHUB_ACTIONS_EVIDENCE_REFERENCE.fullmatch(value) is None:
            raise ValueError("decision evidence must use an exact GitHub Actions reference")
        return value

    @model_validator(mode="after")
    def role_and_digest_are_coherent(self):
        if self.role == "CANDIDATE":
            if self.comparator_selection_receipt_sha256 is not None:
                raise ValueError("candidate receipt cannot carry comparator selection evidence")
        elif self.comparator_selection_receipt_sha256 is None:
            raise ValueError("comparator receipt requires selection evidence")
        expected = sha256_hex(self.model_dump(exclude={"receipt_sha256"}))
        if self.receipt_sha256 != expected:
            raise ValueError("final decision receipt digest is invalid")
        return self

    @classmethod
    def create(cls, **values) -> "CheckpointCFinalDecisionReceipt":
        body = {
            "schema_version": "C.FINAL.DECISION.RECEIPT.1",
            "run_attempt": 1,
            "fixture_inputs_used": False,
            "simulated_inputs_used": False,
            "complete_manifest_retained": True,
            "comparator_selection_receipt_sha256": None,
            **values,
        }
        return cls(**body, receipt_sha256=sha256_hex(body))


class CheckpointCFinalMetricSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    baseline_id: str = Field(min_length=1)
    total_cases: int = Field(gt=0)
    total_economic_loss_minor: int = Field(ge=0)
    autonomous_coverage: float = Field(ge=0.0, le=1.0)
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
    if candidate.autonomous_coverage < rule.minimum_autonomous_coverage:
        blockers.append("AUTONOMOUS_COVERAGE_BELOW_FLOOR")
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
    """Legacy structural contract; not the raw-row authoritative final artifact."""

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


def _read_strict_final_input(
    path: str | Path,
    model: type[_FinalInput],
) -> tuple[_FinalInput, str]:
    source = Path(path)
    if source.is_symlink():
        raise ValueError("symlinked final Checkpoint C input is forbidden")
    raw = source.resolve().read_bytes()
    if not raw or len(raw) > MAX_FINAL_INPUT_BYTES:
        raise ValueError("final Checkpoint C input file size is invalid")
    payload = strict_json_loads(raw.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("final Checkpoint C input must contain one JSON object")
    return model.model_validate(payload), sha256(raw).hexdigest()


def load_final_registration(path: str | Path) -> CheckpointCFinalRegistration:
    return _read_strict_final_input(path, CheckpointCFinalRegistration)[0]


def load_final_suite(path: str | Path) -> CheckpointCFinalSuite:
    return _read_strict_final_input(path, CheckpointCFinalSuite)[0]


def load_final_metric_specification(path: str | Path) -> MetricSpecification:
    return _read_strict_final_input(path, MetricSpecification)[0]


def load_final_decision_manifest(path: str | Path) -> CheckpointCFinalDecisionManifest:
    return _read_strict_final_input(path, CheckpointCFinalDecisionManifest)[0]


def load_final_decision_receipt(path: str | Path) -> CheckpointCFinalDecisionReceipt:
    return _read_strict_final_input(path, CheckpointCFinalDecisionReceipt)[0]


def validate_final_decision_receipt(
    registration: CheckpointCFinalRegistration,
    manifest: CheckpointCFinalDecisionManifest,
    receipt: CheckpointCFinalDecisionReceipt,
    *,
    role: Literal["CANDIDATE", "COMPARATOR"],
) -> None:
    expected_baseline_id = (
        registration.candidate_id
        if role == "CANDIDATE"
        else registration.acceptance_rule.comparator_id
    )
    expected_protocol_sha256 = (
        registration.candidate_execution_protocol_sha256
        if role == "CANDIDATE"
        else registration.comparator_execution_protocol_sha256
    )
    if receipt.role != role:
        raise ValueError("final decision receipt has the wrong execution role")
    if receipt.execution_id != manifest.execution_id:
        raise ValueError("final decision receipt belongs to another execution")
    if receipt.baseline_id != expected_baseline_id or manifest.baseline_id != expected_baseline_id:
        raise ValueError("final decision receipt baseline is not preregistered")
    if receipt.source_revision != registration.upstream.integrated_candidate_revision:
        raise ValueError("final decision receipt source revision is not preregistered")
    if receipt.registration_sha256 != registration.registration_sha256:
        raise ValueError("final decision receipt belongs to another registration")
    if receipt.final_suite_sha256 != registration.final_suite_sha256:
        raise ValueError("final decision receipt belongs to another suite")
    if receipt.final_case_ids_sha256 != registration.final_case_ids_sha256:
        raise ValueError("final decision receipt belongs to another case set")
    if receipt.decision_manifest_sha256 != manifest.manifest_sha256:
        raise ValueError("final decision receipt does not bind the retained rows")
    if receipt.execution_protocol_sha256 != expected_protocol_sha256:
        raise ValueError("final decision receipt protocol is not preregistered")
    if receipt.case_count != registration.final_case_count:
        raise ValueError("final decision receipt case count is incomplete")
    if receipt.generated_at_utc < manifest.generated_at_utc:
        raise ValueError("final decision receipt predates the retained rows")
    expected_selection = (
        None
        if role == "CANDIDATE"
        else registration.comparator_selection_receipt_sha256
    )
    if receipt.comparator_selection_receipt_sha256 != expected_selection:
        raise ValueError("comparator selection receipt is not preregistered")


def validate_checkpoint_c_upstream_receipts(
    registration: CheckpointCFinalRegistration,
    checkpoint_a: CheckpointAEvidenceReceipt,
    checkpoint_a_file_sha256: str,
    checkpoint_b: CheckpointBEvidenceReceipt,
    checkpoint_b_file_sha256: str,
) -> None:
    """Revalidate the real A -> B -> C receipt chain before final scoring."""

    expected_revision = registration.upstream.integrated_candidate_revision
    if checkpoint_a_file_sha256 != registration.upstream.checkpoint_a_receipt_sha256:
        raise ValueError("Checkpoint A receipt file does not match final registration")
    if checkpoint_b_file_sha256 != registration.upstream.checkpoint_b_receipt_sha256:
        raise ValueError("Checkpoint B receipt file does not match final registration")
    if checkpoint_a.verification_mode != "FROZEN_AGGREGATE":
        raise ValueError("Checkpoint A fixture evidence is forbidden for final C")
    if checkpoint_a.source_revision != expected_revision:
        raise ValueError("Checkpoint A receipt revision does not match final registration")
    if checkpoint_b.source_revision != expected_revision:
        raise ValueError("Checkpoint B receipt revision does not match final registration")
    if checkpoint_b.checkpoint_a_receipt_sha256 != checkpoint_a_file_sha256:
        raise ValueError("Checkpoint B receipt does not bind the supplied Checkpoint A receipt")


def load_checkpoint_c_upstream_receipts(
    registration: CheckpointCFinalRegistration,
    checkpoint_a_path: str | Path,
    checkpoint_b_path: str | Path,
) -> tuple[CheckpointAEvidenceReceipt, str, CheckpointBEvidenceReceipt, str]:
    """Load strict, nonsymlinked A/B receipts pinned by the frozen registration."""

    checkpoint_a, checkpoint_a_sha256 = _read_strict_final_input(
        checkpoint_a_path,
        CheckpointAEvidenceReceipt,
    )
    checkpoint_b, checkpoint_b_sha256 = _read_strict_final_input(
        checkpoint_b_path,
        CheckpointBEvidenceReceipt,
    )
    validate_checkpoint_c_upstream_receipts(
        registration,
        checkpoint_a,
        checkpoint_a_sha256,
        checkpoint_b,
        checkpoint_b_sha256,
    )
    return checkpoint_a, checkpoint_a_sha256, checkpoint_b, checkpoint_b_sha256


def derive_final_case_results(
    registration: CheckpointCFinalRegistration,
    suite: CheckpointCFinalSuite,
    metric_specification: MetricSpecification,
    manifest: CheckpointCFinalDecisionManifest,
    *,
    expected_baseline_id: str,
) -> tuple[CaseBenchmarkResult, ...]:
    """Score every final row from frozen cases; caller aggregates are never accepted."""

    suite_sha256 = suite.canonical_hash()
    case_ids_sha256 = final_case_ids_sha256(suite)
    if suite_sha256 != registration.final_suite_sha256:
        raise ValueError("final suite does not match its preregistration")
    if case_ids_sha256 != registration.final_case_ids_sha256:
        raise ValueError("final case identities do not match their preregistration")
    if len(suite.cases) != registration.final_case_count:
        raise ValueError("final case count does not match its preregistration")
    if suite.definitions_frozen_at_utc > registration.registered_at_utc:
        raise ValueError("final suite was frozen after its preregistration")
    if sha256_hex(metric_specification) != registration.metric_specification_sha256:
        raise ValueError("final metric specification does not match its preregistration")
    if sha256_hex(metric_specification.loss_weights) != registration.tel_weights_sha256:
        raise ValueError("final TEL weights do not match their preregistration")
    if final_cost_source_manifest_sha256(suite) != registration.cost_source_manifest_sha256:
        raise ValueError("final cost sources do not match their preregistration")
    if manifest.registration_sha256 != registration.registration_sha256:
        raise ValueError("final decision manifest belongs to another registration")
    if manifest.final_suite_sha256 != suite_sha256:
        raise ValueError("final decision manifest belongs to another suite")
    if manifest.final_case_ids_sha256 != case_ids_sha256:
        raise ValueError("final decision manifest belongs to another case set")
    if manifest.baseline_id != expected_baseline_id:
        raise ValueError("final decision manifest baseline is not preregistered")
    if manifest.generated_at_utc < registration.registered_at_utc:
        raise ValueError("final decisions predate their preregistration")

    case_ids = [case.case_id for case in suite.cases]
    decisions = {decision.case_id: decision for decision in manifest.decisions}
    if set(decisions) != set(case_ids) or len(decisions) != len(case_ids):
        raise ValueError("final decisions must cover every registered case exactly once")
    return tuple(
        score_case(case, decisions[case.case_id], metric_specification)
        for case in suite.cases
    )


def derive_final_metric_snapshot(
    suite: CheckpointCFinalSuite,
    case_results: tuple[CaseBenchmarkResult, ...],
) -> CheckpointCFinalMetricSnapshot:
    metrics = aggregate_metrics(list(suite.cases), list(case_results))
    return CheckpointCFinalMetricSnapshot(
        baseline_id=case_results[0].baseline_id,
        total_cases=metrics.total_cases,
        total_economic_loss_minor=metrics.total_economic_loss_minor,
        autonomous_coverage=metrics.autonomous_coverage,
        legitimate_transaction_completion=(
            metrics.legitimate_transaction_completion
            if metrics.legitimate_transaction_completion is not None
            else 0.0
        ),
        selective_reliability=(
            metrics.selective_reliability
            if metrics.selective_reliability is not None
            else 0.0
        ),
        p95_verification_latency_ms=metrics.p95_verification_latency_ms or 0,
        errored_cases=metrics.errored_decisions,
        missing_latency_cases=metrics.missing_latency_observations,
        incorrect_irreversible_amount_minor=(
            metrics.incorrect_irreversible_amount_minor
        ),
        case_results_sha256=sha256_hex(case_results),
    )


class CheckpointCFinalHeldOutEvidence(BaseModel):
    """Standalone final artifact whose metrics are recomputed from retained rows."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["C.FINAL.HELD_OUT.EVIDENCE.1"] = (
        "C.FINAL.HELD_OUT.EVIDENCE.1"
    )
    execution_id: str = Field(min_length=1)
    generated_at_utc: datetime
    source_revision: str = Field(pattern=r"^[0-9a-f]{40,64}$")
    registration: CheckpointCFinalRegistration
    suite: CheckpointCFinalSuite
    metric_specification: MetricSpecification
    checkpoint_a_receipt_file_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    checkpoint_b_receipt_file_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    checkpoint_a_receipt: CheckpointAEvidenceReceipt
    checkpoint_b_receipt: CheckpointBEvidenceReceipt
    candidate_manifest: CheckpointCFinalDecisionManifest
    comparator_manifest: CheckpointCFinalDecisionManifest
    candidate_receipt: CheckpointCFinalDecisionReceipt
    comparator_receipt: CheckpointCFinalDecisionReceipt
    candidate_case_results: tuple[CaseBenchmarkResult, ...] = Field(min_length=1)
    comparator_case_results: tuple[CaseBenchmarkResult, ...] = Field(min_length=1)
    candidate: CheckpointCFinalMetricSnapshot
    comparator: CheckpointCFinalMetricSnapshot
    decision: CheckpointCFinalDecision

    @field_validator("generated_at_utc")
    @classmethod
    def held_out_generated_in_utc(cls, value: datetime):
        return _utc(value, "generated_at_utc")

    @model_validator(mode="after")
    def raw_rows_and_preregistration_are_coherent(self):
        registration = self.registration
        if self.generated_at_utc < registration.registered_at_utc:
            raise ValueError("final held-out evidence predates its registration")
        if self.source_revision != registration.upstream.integrated_candidate_revision:
            raise ValueError("final held-out source revision is not preregistered")
        if self.suite.definitions_frozen_at_utc > registration.registered_at_utc:
            raise ValueError("final held-out suite was frozen after registration")
        if self.suite.canonical_hash() != registration.final_suite_sha256:
            raise ValueError("final held-out suite does not match registration")
        if final_case_ids_sha256(self.suite) != registration.final_case_ids_sha256:
            raise ValueError("final held-out case identities do not match registration")
        if len(self.suite.cases) != registration.final_case_count:
            raise ValueError("final held-out case count does not match registration")
        if sha256_hex(self.metric_specification) != registration.metric_specification_sha256:
            raise ValueError("final metric specification does not match registration")
        if (
            sha256_hex(self.metric_specification.loss_weights)
            != registration.tel_weights_sha256
        ):
            raise ValueError("final TEL weights do not match registration")
        if (
            final_cost_source_manifest_sha256(self.suite)
            != registration.cost_source_manifest_sha256
        ):
            raise ValueError("final cost sources do not match registration")
        validate_checkpoint_c_upstream_receipts(
            registration,
            self.checkpoint_a_receipt,
            self.checkpoint_a_receipt_file_sha256,
            self.checkpoint_b_receipt,
            self.checkpoint_b_receipt_file_sha256,
        )
        if (
            self.candidate_manifest.execution_id != self.execution_id
            or self.comparator_manifest.execution_id != self.execution_id
        ):
            raise ValueError("candidate and comparator rows must share the execution id")
        if self.candidate_receipt.execution_nonce_sha256 != (
            self.comparator_receipt.execution_nonce_sha256
        ):
            raise ValueError("candidate and comparator receipts do not share one execution")
        validate_final_decision_receipt(
            registration,
            self.candidate_manifest,
            self.candidate_receipt,
            role="CANDIDATE",
        )
        validate_final_decision_receipt(
            registration,
            self.comparator_manifest,
            self.comparator_receipt,
            role="COMPARATOR",
        )
        if (
            self.generated_at_utc < self.candidate_manifest.generated_at_utc
            or self.generated_at_utc < self.comparator_manifest.generated_at_utc
            or self.generated_at_utc < self.candidate_receipt.generated_at_utc
            or self.generated_at_utc < self.comparator_receipt.generated_at_utc
        ):
            raise ValueError("final evidence predates retained decision rows")

        expected_candidate_results = derive_final_case_results(
            registration,
            self.suite,
            self.metric_specification,
            self.candidate_manifest,
            expected_baseline_id=registration.candidate_id,
        )
        expected_comparator_results = derive_final_case_results(
            registration,
            self.suite,
            self.metric_specification,
            self.comparator_manifest,
            expected_baseline_id=registration.acceptance_rule.comparator_id,
        )
        if self.candidate_case_results != expected_candidate_results:
            raise ValueError("candidate case results were not derived from frozen rows")
        if self.comparator_case_results != expected_comparator_results:
            raise ValueError("comparator case results were not derived from frozen rows")
        expected_candidate = derive_final_metric_snapshot(
            self.suite,
            expected_candidate_results,
        )
        expected_comparator = derive_final_metric_snapshot(
            self.suite,
            expected_comparator_results,
        )
        if self.candidate != expected_candidate:
            raise ValueError("candidate final metrics were not derived from raw rows")
        if self.comparator != expected_comparator:
            raise ValueError("comparator final metrics were not derived from raw rows")
        expected_decision = evaluate_final_metrics(
            registration,
            expected_candidate,
            expected_comparator,
        )
        if self.decision != expected_decision:
            raise ValueError("final held-out decision does not match derived metrics")
        return self


def build_final_held_out_evidence(
    *,
    execution_id: str,
    generated_at_utc: datetime,
    source_revision: str,
    registration: CheckpointCFinalRegistration,
    suite: CheckpointCFinalSuite,
    metric_specification: MetricSpecification,
    checkpoint_a_receipt: CheckpointAEvidenceReceipt,
    checkpoint_a_receipt_file_sha256: str,
    checkpoint_b_receipt: CheckpointBEvidenceReceipt,
    checkpoint_b_receipt_file_sha256: str,
    candidate_manifest: CheckpointCFinalDecisionManifest,
    comparator_manifest: CheckpointCFinalDecisionManifest,
    candidate_receipt: CheckpointCFinalDecisionReceipt,
    comparator_receipt: CheckpointCFinalDecisionReceipt,
) -> CheckpointCFinalHeldOutEvidence:
    """Build final evidence exclusively from strict preregistered inputs and rows."""

    candidate_results = derive_final_case_results(
        registration,
        suite,
        metric_specification,
        candidate_manifest,
        expected_baseline_id=registration.candidate_id,
    )
    comparator_results = derive_final_case_results(
        registration,
        suite,
        metric_specification,
        comparator_manifest,
        expected_baseline_id=registration.acceptance_rule.comparator_id,
    )
    candidate = derive_final_metric_snapshot(suite, candidate_results)
    comparator = derive_final_metric_snapshot(suite, comparator_results)
    return CheckpointCFinalHeldOutEvidence(
        execution_id=execution_id,
        generated_at_utc=generated_at_utc,
        source_revision=source_revision,
        registration=registration,
        suite=suite,
        metric_specification=metric_specification,
        checkpoint_a_receipt_file_sha256=checkpoint_a_receipt_file_sha256,
        checkpoint_b_receipt_file_sha256=checkpoint_b_receipt_file_sha256,
        checkpoint_a_receipt=checkpoint_a_receipt,
        checkpoint_b_receipt=checkpoint_b_receipt,
        candidate_manifest=candidate_manifest,
        comparator_manifest=comparator_manifest,
        candidate_receipt=candidate_receipt,
        comparator_receipt=comparator_receipt,
        candidate_case_results=candidate_results,
        comparator_case_results=comparator_results,
        candidate=candidate,
        comparator=comparator,
        decision=evaluate_final_metrics(registration, candidate, comparator),
    )


def write_final_held_out_evidence(
    evidence: CheckpointCFinalHeldOutEvidence,
    path: str | Path,
) -> tuple[Path, str]:
    """Write once so a prior authoritative output is never silently replaced."""

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.parent.is_symlink() or destination.is_symlink():
        raise ValueError("final held-out evidence path must not use symlinks")
    encoded = evidence.model_dump_json(indent=2, exclude_none=False) + "\n"
    raw = encoded.encode("utf-8")
    if destination.exists():
        if destination.read_bytes() != raw:
            raise FileExistsError("final held-out evidence conflicts with prior output")
        return destination, sha256(raw).hexdigest()
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        suffix=".tmp",
        dir=destination.parent,
    )
    try:
        os.chmod(temporary_name, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        descriptor = -1
        try:
            os.link(temporary_name, destination)
        except FileExistsError:
            if destination.is_symlink() or destination.read_bytes() != raw:
                raise FileExistsError(
                    "final held-out evidence conflicts with prior output"
                ) from None
    finally:
        if descriptor != -1:
            os.close(descriptor)
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
    return destination, sha256(raw).hexdigest()
