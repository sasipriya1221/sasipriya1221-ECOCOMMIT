from __future__ import annotations

import re
from dataclasses import dataclass

from pydantic import BaseModel, Field

from .contracts import ClauseType, DecisionStatus, EconomicIntentContract, Provenance


class ValidationFinding(BaseModel):
    code: str
    message: str
    severity: str
    clause_id: str | None = None


class FidelityReport(BaseModel):
    status: DecisionStatus
    coverage: float = Field(ge=0.0, le=1.0)
    faithfulness: float = Field(ge=0.0, le=1.0)
    selective_risk: float = Field(ge=0.0)
    findings: list[ValidationFinding] = Field(default_factory=list)
    clarification_question: str | None = None


@dataclass(frozen=True)
class ValidatorConfig:
    materiality_threshold: float = 0.55
    risk_threshold: float = 0.28
    minimum_coverage: float = 0.90
    minimum_faithfulness: float = 0.95


class FidelityValidator:
    """Deterministic structural guardrail around a probabilistic candidate contract.

    This is deliberately not claimed as semantic ground truth. It detects structural
    failures we can prove from provenance/source spans and decides when ambiguity is
    material enough to require clarification.
    """

    NEGATION_MARKERS = ("not", "don't", "do not", "never", "excluding", "except")
    EXCEPTION_MARKERS = ("unless", "except", "only if", "provided that")
    DEPENDENCY_MARKERS = ("if", "when", "until", "before", "after", "unless")

    def __init__(self, config: ValidatorConfig | None = None):
        self.config = config or ValidatorConfig()

    def validate(self, contract: EconomicIntentContract) -> FidelityReport:
        findings: list[ValidationFinding] = []
        material = [c for c in contract.clauses if c.materiality >= self.config.materiality_threshold]
        invented = 0
        total_risk = 0.0

        for clause in material:
            if not (
                clause.provenance == Provenance.EXPLICIT_USER and clause.source_span is not None
                or clause.provenance in {Provenance.INCORPORATED_POLICY, Provenance.AUTHORITATIVE_EVIDENCE}
            ):
                invented += 1
                findings.append(ValidationFinding(
                    code="MATERIAL_INFERENCE",
                    message="Material clause is based on inference rather than explicit/policy/evidence provenance",
                    severity="high",
                    clause_id=clause.clause_id,
                ))
            total_risk += (1.0 - clause.confidence) * clause.materiality

        coverage = self._coverage(contract, findings)
        faithfulness = 1.0 if not material else max(0.0, 1.0 - invented / len(material))
        self._check_negation(contract, findings)
        self._check_exception_structure(contract, findings)
        self._check_dependency_structure(contract, findings)

        structural_high = any(f.severity == "high" for f in findings)
        if coverage < self.config.minimum_coverage or faithfulness < self.config.minimum_faithfulness:
            status = DecisionStatus.REJECTED
        elif structural_high or total_risk >= self.config.risk_threshold:
            status = DecisionStatus.CLARIFICATION_REQUIRED
        else:
            status = DecisionStatus.VALIDATED

        question = self._minimum_clarification(contract, findings) if status == DecisionStatus.CLARIFICATION_REQUIRED else None
        return FidelityReport(
            status=status,
            coverage=coverage,
            faithfulness=faithfulness,
            selective_risk=round(total_risk, 4),
            findings=findings,
            clarification_question=question,
        )

    def _coverage(self, contract: EconomicIntentContract, findings: list[ValidationFinding]) -> float:
        instruction = contract.instruction.lower()
        signals: list[str] = []
        signals += re.findall(r"(?:₹|rs\.?\s*)?\d+(?:\.\d+)?\s*(?:lakh|lakhs|crore|%|percent)?", instruction)
        for marker in self.NEGATION_MARKERS + self.EXCEPTION_MARKERS:
            if marker in instruction:
                signals.append(marker)
        for marker in ("before", "after", "within", "by ", "until"):
            if marker in instruction:
                signals.append(marker.strip())
        signals = [s.strip() for s in signals if s.strip()]
        if not signals:
            return 1.0

        spans = " ".join(c.source_span.text.lower() for c in contract.clauses if c.source_span)
        covered = 0
        for signal in signals:
            if signal in spans:
                covered += 1
            else:
                findings.append(ValidationFinding(
                    code="UNCOVERED_SIGNAL",
                    message=f"Material surface signal not grounded by any clause: {signal}",
                    severity="high",
                ))
        return covered / len(signals)

    def _check_negation(self, contract: EconomicIntentContract, findings: list[ValidationFinding]) -> None:
        instruction = contract.instruction.lower()
        if any(m in instruction for m in self.NEGATION_MARKERS) and not any(c.negated for c in contract.clauses):
            findings.append(ValidationFinding(
                code="NEGATION_NOT_PRESERVED",
                message="Instruction contains negation but no contract clause preserves it",
                severity="high",
            ))

    def _check_exception_structure(self, contract: EconomicIntentContract, findings: list[ValidationFinding]) -> None:
        instruction = contract.instruction.lower()
        if any(m in instruction for m in self.EXCEPTION_MARKERS) and not any(c.clause_type == ClauseType.EXCEPTION or c.exception_to for c in contract.clauses):
            findings.append(ValidationFinding(
                code="EXCEPTION_NOT_PRESERVED",
                message="Instruction contains an exception marker but no exception structure exists",
                severity="high",
            ))

    def _check_dependency_structure(self, contract: EconomicIntentContract, findings: list[ValidationFinding]) -> None:
        instruction = contract.instruction.lower()
        if any(m in instruction for m in self.DEPENDENCY_MARKERS) and not any(c.clause_type == ClauseType.DEPENDENCY or c.depends_on for c in contract.clauses):
            findings.append(ValidationFinding(
                code="DEPENDENCY_NOT_PRESERVED",
                message="Instruction appears conditional/temporal but no dependency structure exists",
                severity="high",
            ))

    def _minimum_clarification(self, contract: EconomicIntentContract, findings: list[ValidationFinding]) -> str:
        low_conf = sorted(
            [c for c in contract.clauses if c.materiality >= self.config.materiality_threshold],
            key=lambda c: (c.confidence, -c.materiality),
        )
        if low_conf and low_conf[0].confidence < 0.8:
            return f"Please clarify the economically material requirement represented as '{low_conf[0].normalized_value}'."
        if any(f.code == "MATERIAL_INFERENCE" for f in findings):
            return "A financially material requirement is currently inferred rather than explicit. Please confirm it before proceeding."
        return "Please clarify the unresolved economically material condition before proceeding."
