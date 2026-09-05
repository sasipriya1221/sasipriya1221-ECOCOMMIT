from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_serializer, model_validator


FROZEN_A_DATASET_SHA256 = "968be3ed3a438a3a28a3402fa65c90a45cb564ed1adad2e6e51d852e24c5bb8b"
CANDIDATE7_FROZEN_SOURCE_REVISION = "12d121f80a6cacd94376c6d2b7bce7dff5212eb5"
CANDIDATE7_ARTIFACT_NAMESPACE = "checkpoint-a-candidate-7"
CANDIDATE7_EVALUATOR_SHA256 = "00741dbd9d84c04e22fccfbbedf9d895d8ac4e0ea711a2121b431b0cc03c564d"
CANDIDATE7_CRITERIA_SHA256 = "eb6564e3d3d4c0f0ab466eb07d2f66556b738274863e07a7274278e739a6101b"


class CheckpointAMetrics(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    passed_cases: int = Field(ge=0, le=80)
    case_pass_rate: float = Field(ge=0.0, le=1.0)
    autonomous_coverage: float = Field(ge=0.0, le=1.0)
    selective_semantic_reliability: float = Field(ge=0.0, le=1.0)
    ambiguous_clarification_accuracy: float = Field(ge=0.0, le=1.0)


class CheckpointAEvidenceReceipt(BaseModel):
    """Typed proof that an eligible frozen Checkpoint A candidate passed its real gate.

    Production receipts are emitted only by the strict aggregate verifier. The
    explicitly separate TEST_FIXTURE mode exists for local interface tests and
    is refused by the production A-to-B bridge.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["A.RECEIPT.1"] = "A.RECEIPT.1"
    verification_mode: Literal["FROZEN_AGGREGATE", "TEST_FIXTURE"]
    evidence_reference: str = Field(min_length=1)
    aggregate_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_revision: str = Field(pattern=r"^[0-9a-f]{40,64}$")
    candidate_version: str = Field(min_length=1)
    dataset_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    total_cases: int
    full_frozen_gate_run: bool
    gate_passed: bool
    metrics: CheckpointAMetrics
    candidate_source_revision: str | None = Field(default=None, pattern=r"^[0-9a-f]{40}$")
    qualification_status: Literal["PASS"] | None = None
    qualification_evidence_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    qualification_source_revision: str | None = Field(default=None, pattern=r"^[0-9a-f]{40}$")
    preregistration_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    evaluator_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    criteria_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    artifact_namespace: str | None = None
    semantic_score_retry_count: int | None = Field(default=None, ge=0)

    @model_serializer(mode="wrap")
    def omit_unset_candidate7_bindings(self, handler):
        """Keep serialized historical A receipts byte-shape compatible."""
        return {key: value for key, value in handler(self).items() if value is not None}

    @model_validator(mode="after")
    def passed_receipt_is_coherent(self):
        if self.verification_mode == "FROZEN_AGGREGATE":
            if self.candidate_version not in {"A-CANDIDATE-3", "A-CANDIDATE-4", "A-CANDIDATE-5", "A-CANDIDATE-6", "A-CANDIDATE-7"}:
                raise ValueError("production A receipt must identify an eligible frozen candidate")
            if self.dataset_sha256 != FROZEN_A_DATASET_SHA256:
                raise ValueError("production A receipt dataset digest is not frozen")
        if self.candidate_version == "A-CANDIDATE-7":
            required = (
                self.qualification_evidence_sha256,
                self.preregistration_sha256,
                self.evaluator_sha256,
                self.criteria_sha256,
            )
            if (
                self.candidate_source_revision != CANDIDATE7_FROZEN_SOURCE_REVISION
                or self.qualification_source_revision != CANDIDATE7_FROZEN_SOURCE_REVISION
                or self.qualification_status != "PASS"
                or self.artifact_namespace != CANDIDATE7_ARTIFACT_NAMESPACE
                or self.evaluator_sha256 != CANDIDATE7_EVALUATOR_SHA256
                or self.criteria_sha256 != CANDIDATE7_CRITERIA_SHA256
                or self.semantic_score_retry_count != 0
                or any(value is None for value in required)
            ):
                raise ValueError("Candidate-7 receipt lacks its frozen qualification/protocol binding")
        if self.total_cases != 80 or not self.full_frozen_gate_run or not self.gate_passed:
            raise ValueError("A receipt requires a complete passing 80-case frozen run")
        if self.metrics.passed_cases < 72:
            raise ValueError("A receipt does not meet the frozen case-pass threshold")
        expected_rate = self.metrics.passed_cases / self.total_cases
        if not math.isclose(
            self.metrics.case_pass_rate,
            expected_rate,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError("A receipt case-pass rate does not match passed cases")
        if self.metrics.case_pass_rate < 0.90:
            raise ValueError("A receipt does not meet the frozen case-pass rate")
        if self.metrics.selective_semantic_reliability < 0.95:
            raise ValueError("A receipt does not meet selective semantic reliability")
        if self.metrics.autonomous_coverage < 0.55:
            raise ValueError("A receipt does not meet autonomous coverage")
        if self.metrics.ambiguous_clarification_accuracy < 0.80:
            raise ValueError("A receipt does not meet clarification accuracy")
        return self

    @classmethod
    def test_fixture(cls, evidence_reference: str) -> "CheckpointAEvidenceReceipt":
        return cls(
            verification_mode="TEST_FIXTURE",
            evidence_reference=evidence_reference,
            aggregate_sha256="0" * 64,
            manifest_sha256="0" * 64,
            source_revision="0" * 40,
            candidate_version="TEST-FIXTURE",
            dataset_sha256="0" * 64,
            total_cases=80,
            full_frozen_gate_run=True,
            gate_passed=True,
            metrics=CheckpointAMetrics(
                passed_cases=80,
                case_pass_rate=1.0,
                autonomous_coverage=1.0,
                selective_semantic_reliability=1.0,
                ambiguous_clarification_accuracy=1.0,
            ),
        )
