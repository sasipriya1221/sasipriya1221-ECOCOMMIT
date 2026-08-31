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

    This validator does not claim semantic ground truth. It proves structural facts
    that are observable from the instruction/contract pair, and sends materially
    vague or inferred meaning to clarification instead of granting authority.
    """

    NEGATION_PATTERNS = (
        r"\bnot\b", r"\bdon't\b", r"\bdo not\b", r"\bnever\b",
        r"\bexcluding\b", r"\bexcept\b", r"\breject\b",
    )
    EXCEPTION_PATTERNS = (
        r"\bunless\b", r"\bexcept\b", r"\bonly if\b",
        r"\bprovided that\b", r"\bin which case\b", r"\botherwise\b",
    )
    DEPENDENCY_PATTERNS = (
        r"\bif\b", r"\bwhen\b", r"\buntil\b", r"\bbefore\b",
        r"\bafter\b", r"\bunless\b", r"\botherwise\b",
        r"\bonly if\b", r"\bprovided that\b", r"\bin which case\b",
    )
    VAGUE_MATERIAL_PATTERNS = (
        r"\baround\b", r"\broughly\b", r"\babout\b", r"\breasonable\b",
        r"\breasonably\b", r"\breliable\b", r"\bbest\b", r"\benough\b",
        r"\bsufficient\b", r"\bsuitable\b", r"\busual\b", r"\bnormal\b",
        r"\bsensible\b", r"\bacceptable\b", r"\bfair\b", r"\bpractical\b",
        r"\bappropriate\b", r"\bstandard commercial terms\b",
        r"\bnormal approval threshold\b", r"\bnormal limit\b",
        r"\blittle more\b", r"\bnot too much\b", r"\bmaterially worse\b",
        r"\bsubstantially cheaper\b", r"\bmuch better value\b",
        r"\bunder control\b", r"\bas low as reasonably possible\b",
        r"\bminimal irreversible risk\b", r"\bunnecessary (?:financial )?exposure\b",
        r"\bexcessive irreversible risk\b", r"\bsafe staged-payment\b",
        r"\bstrong protection\b", r"\bgood warranty\b", r"\bsoon\b",
        r"\bquickly\b", r"\bbefore they are needed\b",
    )

    def __init__(self, config: ValidatorConfig | None = None):
        self.config = config or ValidatorConfig()

    @staticmethod
    def _matches_any(text: str, patterns: tuple[str, ...]) -> bool:
        return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)

    def validate(self, contract: EconomicIntentContract) -> FidelityReport:
        findings: list[ValidationFinding] = []
        material = [c for c in contract.clauses if c.materiality >= self.config.materiality_threshold]
        inferred_material = 0
        total_risk = 0.0

        for clause in material:
            grounded = (
                clause.provenance == Provenance.EXPLICIT_USER and clause.source_span is not None
                or clause.provenance in {Provenance.INCORPORATED_POLICY, Provenance.AUTHORITATIVE_EVIDENCE}
            )
            if not grounded:
                inferred_material += 1
                findings.append(ValidationFinding(
                    code="MATERIAL_INFERENCE",
                    message="Material clause is inferred rather than explicit/policy/evidence-grounded; confirmation is required before it can influence authority",
                    severity="clarify",
                    clause_id=clause.clause_id,
                ))
            total_risk += (1.0 - clause.confidence) * clause.materiality

        coverage = self._coverage(contract, findings)
        faithfulness = 1.0 if not material else max(0.0, 1.0 - inferred_material / len(material))
        self._check_negation(contract, findings)
        self._check_exception_structure(contract, findings)
        self._check_dependency_structure(contract, findings)
        self._check_material_vagueness(contract, findings)

        hard_failure = any(f.severity == "high" for f in findings)
        clarification_signal = any(f.severity == "clarify" for f in findings)

        # Missing explicit surface requirements/structure is a rejection. Inferred or
        # materially vague meaning is not silently accepted; it is escalated.
        if coverage < self.config.minimum_coverage or hard_failure:
            status = DecisionStatus.REJECTED
        elif clarification_signal or faithfulness < self.config.minimum_faithfulness or total_risk >= self.config.risk_threshold:
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
        numeric = re.findall(r"(?:₹|rs\.?\s*)?\d+(?:\.\d+)?\s*(?:lakh|lakhs|crore|%|percent)?", instruction)
        numeric = [s.strip() for s in numeric if s.strip()]
        if not numeric:
            return 1.0

        haystack = " ".join(
            [c.normalized_value.lower() for c in contract.clauses]
            + [c.source_span.text.lower() for c in contract.clauses if c.source_span]
        )
        covered = 0
        for signal in numeric:
            # Compare both the full monetary token and its core number to tolerate
            # normalization such as '₹8 lakh' -> '800000'. Exact source spans remain preferred.
            core = re.search(r"\d+(?:\.\d+)?", signal)
            core_text = core.group(0) if core else signal
            if signal in haystack or re.search(rf"(?<!\d){re.escape(core_text)}(?!\d)", haystack):
                covered += 1
            else:
                findings.append(ValidationFinding(
                    code="UNCOVERED_SIGNAL",
                    message=f"Material numeric signal not grounded by any clause: {signal}",
                    severity="high",
                ))
        return covered / len(numeric)

    def _check_negation(self, contract: EconomicIntentContract, findings: list[ValidationFinding]) -> None:
        instruction = contract.instruction
        if self._matches_any(instruction, self.NEGATION_PATTERNS) and not any(c.negated for c in contract.clauses):
            findings.append(ValidationFinding(
                code="NEGATION_NOT_PRESERVED",
                message="Instruction contains negation/prohibition but no contract clause preserves it",
                severity="high",
            ))

    def _check_exception_structure(self, contract: EconomicIntentContract, findings: list[ValidationFinding]) -> None:
        if self._matches_any(contract.instruction, self.EXCEPTION_PATTERNS) and not any(
            c.clause_type == ClauseType.EXCEPTION or c.exception_to for c in contract.clauses
        ):
            findings.append(ValidationFinding(
                code="EXCEPTION_NOT_PRESERVED",
                message="Instruction contains an exception marker but no exception structure exists",
                severity="high",
            ))

    def _check_dependency_structure(self, contract: EconomicIntentContract, findings: list[ValidationFinding]) -> None:
        # Word-boundary matching is intentional: 'if' inside 'certified' must never
        # create a fake dependency requirement.
        if self._matches_any(contract.instruction, self.DEPENDENCY_PATTERNS) and not any(
            c.clause_type == ClauseType.DEPENDENCY or c.depends_on for c in contract.clauses
        ):
            findings.append(ValidationFinding(
                code="DEPENDENCY_NOT_PRESERVED",
                message="Instruction contains a real conditional/ordering dependency but no dependency structure exists",
                severity="high",
            ))

    def _check_material_vagueness(self, contract: EconomicIntentContract, findings: list[ValidationFinding]) -> None:
        instruction = contract.instruction
        matched = [p for p in self.VAGUE_MATERIAL_PATTERNS if re.search(p, instruction, flags=re.IGNORECASE)]
        if matched:
            findings.append(ValidationFinding(
                code="MATERIAL_VAGUENESS",
                message="Instruction contains economically material open-textured language that requires clarification before autonomous financial authority",
                severity="clarify",
            ))

    def _minimum_clarification(self, contract: EconomicIntentContract, findings: list[ValidationFinding]) -> str:
        if any(f.code == "MATERIAL_VAGUENESS" for f in findings):
            return "Please replace the materially vague commercial term with an explicit amount, quantity, counterparty, timing, quality, or exposure constraint."
        low_conf = sorted(
            [c for c in contract.clauses if c.materiality >= self.config.materiality_threshold],
            key=lambda c: (c.confidence, -c.materiality),
        )
        if low_conf and low_conf[0].confidence < 0.8:
            return f"Please clarify the economically material requirement represented as '{low_conf[0].normalized_value}'."
        if any(f.code == "MATERIAL_INFERENCE" for f in findings):
            return "A financially material requirement is currently inferred rather than explicit. Please confirm it before proceeding."
        return "Please clarify the unresolved economically material condition before proceeding."
