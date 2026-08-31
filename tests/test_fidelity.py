from ecocommit.contracts import ClauseType, DecisionStatus, EconomicClause, EconomicIntentContract, Provenance
from ecocommit.validator import FidelityValidator
from helpers import span


def test_negation_omission_is_rejected():
    instruction = "Do not buy refurbished servers under ₹900000."
    clauses = [EconomicClause(
        clause_id="amount", clause_type=ClauseType.AMOUNT, normalized_value="max ₹900000",
        source_span=span(instruction, "₹900000"), provenance=Provenance.EXPLICIT_USER,
        materiality=1.0, confidence=1.0,
    )]
    report = FidelityValidator().validate(EconomicIntentContract(instruction=instruction, clauses=clauses))
    assert report.status == DecisionStatus.REJECTED
    assert any(f.code == "NEGATION_NOT_PRESERVED" for f in report.findings)


def test_exception_omission_is_rejected():
    instruction = "Do not pay more than 20% before quality inspection unless Vendor A provides the approved guarantee."
    clauses = [EconomicClause(
        clause_id="exposure", clause_type=ClauseType.REVERSIBILITY, normalized_value="max 20% before quality inspection",
        source_span=span(instruction, "20%"), provenance=Provenance.EXPLICIT_USER,
        materiality=1.0, confidence=1.0, negated=True,
    )]
    report = FidelityValidator().validate(EconomicIntentContract(instruction=instruction, clauses=clauses))
    assert report.status == DecisionStatus.REJECTED
    assert any(f.code == "EXCEPTION_NOT_PRESERVED" for f in report.findings)


def test_material_low_confidence_requires_clarification():
    instruction = "Buy a reliable laptop under ₹70000."
    clauses = [
        EconomicClause(
            clause_id="amount", clause_type=ClauseType.AMOUNT, normalized_value="max ₹70000",
            source_span=span(instruction, "₹70000"), provenance=Provenance.EXPLICIT_USER,
            materiality=1.0, confidence=1.0,
        ),
        EconomicClause(
            clause_id="reliable", clause_type=ClauseType.CONDITION, normalized_value="reliable",
            source_span=span(instruction, "reliable"), provenance=Provenance.EXPLICIT_USER,
            materiality=0.8, confidence=0.45,
        ),
    ]
    report = FidelityValidator().validate(EconomicIntentContract(instruction=instruction, clauses=clauses))
    assert report.status == DecisionStatus.CLARIFICATION_REQUIRED
    assert report.clarification_question


def test_clear_grounded_contract_validates():
    instruction = "Buy 500 parts under ₹800000."
    clauses = [
        EconomicClause(
            clause_id="qty", clause_type=ClauseType.QUANTITY, normalized_value="500",
            source_span=span(instruction, "500"), provenance=Provenance.EXPLICIT_USER,
            materiality=0.9, confidence=1.0,
        ),
        EconomicClause(
            clause_id="amount", clause_type=ClauseType.AMOUNT, normalized_value="max ₹800000",
            source_span=span(instruction, "₹800000"), provenance=Provenance.EXPLICIT_USER,
            materiality=1.0, confidence=1.0,
        ),
    ]
    report = FidelityValidator().validate(EconomicIntentContract(instruction=instruction, clauses=clauses))
    assert report.status == DecisionStatus.VALIDATED
