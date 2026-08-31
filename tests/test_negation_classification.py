from ecocommit.contracts import ClauseType, DecisionStatus, EconomicClause, EconomicIntentContract, Provenance
from ecocommit.validator import FidelityValidator
from helpers import span


def test_not_too_much_is_vagueness_not_unpreserved_prohibition():
    instruction = "Get a premium model if the price difference is not too much."
    clauses = [
        EconomicClause(
            clause_id="product",
            clause_type=ClauseType.PRODUCT,
            normalized_value="premium model",
            source_span=span(instruction, "premium model"),
            provenance=Provenance.EXPLICIT_USER,
            materiality=0.9,
            confidence=1.0,
        ),
        EconomicClause(
            clause_id="condition",
            clause_type=ClauseType.CONDITION,
            normalized_value="price difference is not too much",
            source_span=span(instruction, "price difference is not too much"),
            provenance=Provenance.EXPLICIT_USER,
            materiality=0.8,
            confidence=0.6,
        ),
        EconomicClause(
            clause_id="dependency",
            clause_type=ClauseType.DEPENDENCY,
            normalized_value="if the price difference is not too much",
            source_span=span(instruction, "if the price difference is not too much"),
            provenance=Provenance.EXPLICIT_USER,
            materiality=0.8,
            confidence=0.6,
            depends_on=["condition"],
        ),
    ]

    report = FidelityValidator().validate(EconomicIntentContract(instruction=instruction, clauses=clauses))

    assert report.status == DecisionStatus.CLARIFICATION_REQUIRED
    assert any(f.code == "MATERIAL_VAGUENESS" for f in report.findings)
    assert not any(f.code == "NEGATION_NOT_PRESERVED" for f in report.findings)


def test_not_recurring_remains_a_true_negation_requirement():
    instruction = "Make this a one-time purchase, not recurring."
    clauses = [
        EconomicClause(
            clause_id="auth",
            clause_type=ClauseType.AUTHORIZATION,
            normalized_value="one-time purchase",
            source_span=span(instruction, "one-time purchase"),
            provenance=Provenance.EXPLICIT_USER,
            materiality=1.0,
            confidence=1.0,
        )
    ]

    report = FidelityValidator().validate(EconomicIntentContract(instruction=instruction, clauses=clauses))

    assert report.status == DecisionStatus.REJECTED
    assert any(f.code == "NEGATION_NOT_PRESERVED" for f in report.findings)
