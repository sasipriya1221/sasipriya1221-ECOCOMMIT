from ecocommit.contracts import ClauseType, DecisionStatus, EconomicClause, EconomicIntentContract, Provenance, SourceSpan
from ecocommit.validator import FidelityValidator


def _span(instruction: str, text: str) -> SourceSpan:
    start = instruction.index(text)
    return SourceSpan(text=text, start=start, end=start + len(text))


def test_confidence_risk_is_normalized_not_clause_count_accumulated():
    instruction = "Buy 120 ISO-9001 valves from certified suppliers under ₹6 lakh within seven days."
    specs = [
        ("a", ClauseType.AUTHORIZATION, "Buy", 0.95, 0.97),
        ("q", ClauseType.QUANTITY, "120", 0.90, 0.98),
        ("p", ClauseType.PRODUCT, "ISO-9001 valves", 0.95, 0.96),
        ("cert", ClauseType.CERTIFICATION, "ISO-9001", 0.90, 0.97),
        ("cp", ClauseType.COUNTERPARTY, "certified suppliers", 0.85, 0.82),
        ("m", ClauseType.AMOUNT, "₹6 lakh", 0.95, 0.96),
        ("t", ClauseType.TEMPORAL, "within seven days", 0.90, 0.96),
    ]
    clauses = [
        EconomicClause(
            clause_id=clause_id,
            clause_type=clause_type,
            normalized_value=text,
            source_span=_span(instruction, text),
            provenance=Provenance.EXPLICIT_USER,
            materiality=materiality,
            confidence=confidence,
        )
        for clause_id, clause_type, text, materiality, confidence in specs
    ]

    report = FidelityValidator().validate(EconomicIntentContract(instruction=instruction, clauses=clauses))

    assert report.status == DecisionStatus.VALIDATED
    assert report.selective_risk < 0.10


def test_unless_exception_edge_counts_as_preserved_gating_dependency():
    instruction = "Buy from an approved supplier unless another option is clearly better."
    clauses = [
        EconomicClause(
            clause_id="supplier",
            clause_type=ClauseType.COUNTERPARTY,
            normalized_value="approved supplier",
            source_span=_span(instruction, "approved supplier"),
            provenance=Provenance.EXPLICIT_USER,
            materiality=0.9,
            confidence=0.95,
        ),
        EconomicClause(
            clause_id="exception",
            clause_type=ClauseType.EXCEPTION,
            normalized_value="unless another option is clearly better",
            source_span=_span(instruction, "unless another option is clearly better"),
            provenance=Provenance.EXPLICIT_USER,
            materiality=0.8,
            confidence=0.75,
            hardness="SOFT",
            exception_to=["supplier"],
        ),
    ]

    report = FidelityValidator().validate(EconomicIntentContract(instruction=instruction, clauses=clauses))

    assert report.status == DecisionStatus.CLARIFICATION_REQUIRED
    assert any(f.code == "MATERIAL_VAGUENESS" for f in report.findings)
    assert not any(f.code == "DEPENDENCY_NOT_PRESERVED" for f in report.findings)
