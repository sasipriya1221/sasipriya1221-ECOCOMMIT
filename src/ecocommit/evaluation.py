from __future__ import annotations

from dataclasses import dataclass

from .contracts import DecisionStatus, EconomicIntentContract
from .validator import FidelityValidator


@dataclass
class CheckpointAMetrics:
    total: int
    autonomous: int
    correct_autonomous: int
    clarification_required: int
    rejected: int

    @property
    def autonomous_coverage(self) -> float:
        return self.autonomous / self.total if self.total else 0.0

    @property
    def selective_semantic_reliability(self) -> float:
        return self.correct_autonomous / self.autonomous if self.autonomous else 0.0


def evaluate_contracts(predicted: list[EconomicIntentContract], expected_hashes: list[str | None], validator: FidelityValidator) -> CheckpointAMetrics:
    if len(predicted) != len(expected_hashes):
        raise ValueError("predicted and expected lengths differ")
    autonomous = correct = clarify = rejected = 0
    for contract, expected_hash in zip(predicted, expected_hashes):
        report = validator.validate(contract)
        if report.status == DecisionStatus.VALIDATED:
            autonomous += 1
            if expected_hash is not None and contract.canonical_hash() == expected_hash:
                correct += 1
        elif report.status == DecisionStatus.CLARIFICATION_REQUIRED:
            clarify += 1
        else:
            rejected += 1
    return CheckpointAMetrics(len(predicted), autonomous, correct, clarify, rejected)
