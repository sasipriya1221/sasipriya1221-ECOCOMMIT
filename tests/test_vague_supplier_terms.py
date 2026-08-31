from ecocommit.contracts import ClauseType, DecisionStatus, EconomicClause, EconomicIntentContract, Provenance
from ecocommit.validator import FidelityValidator
from helpers import span


def test_good_and_trustworthy_supplier_terms_require_clarification():
    instruction = "Use Vendor A if the deal is good; otherwise choose someone trustworthy."
    clauses = [
        EconomicClause(
            clause_id="vendor",
            clause_type=ClauseType.COUNTERPARTY,
            normalized_value="Vendor A",
            source_span=span(instruction, "Vendor A"),
            provenance=Provenance.EXPLICIT_USER,
            materiality=0.9,
            confidence=1.0,
        ),
        EconomicClause(
            clause_id="condition",
            clause_type=ClauseType.CONDITION,
            normalized_value="deal is good",
            source_span=span(instruction, "deal is good"),
            provenance=Provenance.EXPLICIT_USER,
            materiality=0.8,
            confidence=1.0,
        ),
        EconomicClause(
            clause_id="dependency",
            clause_type=ClauseType.DEPENDENCY,
            normalized_value="if the deal is good",
            source_span=span(instruction, "if the deal is good"),
            provenance=Provenance.EXPLICIT_USER,
            materiality=0.8,
            confidence=1.0,
            depends_on=["condition"],
        ),
        EconomicClause(
            clause_id="fallback",
            clause_type=ClauseType.EXCEPTION,
            normalized_value="otherwise choose someone trustworthy",
            source_span=span(instruction, "otherwise choose someone trustworthy"),
            provenance=Provenance.EXPLICIT_USER,
            materiality=0.8,
            confidence=1.0,
            exception_to=["vendor"],
        ),
    ]

    report = FidelityValidator().validate(EconomicIntentContract(instruction=instruction, clauses=clauses))

    assert report.status == DecisionStatus.CLARIFICATION_REQUIRED
    assert any(f.code == "MATERIAL_VAGUENESS" for f in report.findings)


def test_clearly_better_alternative_requires_clarification_even_with_structure_preserved():
    instruction = "Buy from an approved supplier unless another option is clearly better."
    clauses = [
        EconomicClause(
            clause_id="approved",
            clause_type=ClauseType.COUNTERPARTY,
            normalized_value="approved supplier",
            source_span=span(instruction, "approved supplier"),
            provenance=Provenance.EXPLICIT_USER,
            materiality=0.9,
            confidence=1.0,
        ),
        EconomicClause(
            clause_id="alternative",
            clause_type=ClauseType.CONDITION,
            normalized_value="another option is clearly better",
            source_span=span(instruction, "another option is clearly better"),
            provenance=Provenance.EXPLICIT_USER,
            materiality=0.8,
            confidence=1.0,
        ),
        EconomicClause(
            clause_id="exception",
            clause_type=ClauseType.EXCEPTION,
            normalized_value="unless another option is clearly better",
            source_span=span(instruction, "unless another option is clearly better"),
            provenance=Provenance.EXPLICIT_USER,
            materiality=0.8,
            confidence=1.0,
            exception_to=["approved"],
            depends_on=["alternative"],
        ),
    ]

    report = FidelityValidator().validate(EconomicIntentContract(instruction=instruction, clauses=clauses))

    assert report.status == DecisionStatus.CLARIFICATION_REQUIRED
    assert any(f.code == "MATERIAL_VAGUENESS" for f in report.findings)
