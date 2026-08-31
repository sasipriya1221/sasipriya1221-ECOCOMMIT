import pytest

from ecocommit.contracts import ClauseType, DecisionStatus, EconomicClause, EconomicIntentContract, Provenance
from ecocommit.validator import FidelityValidator
from helpers import span

AMBIGUOUS = [
    ("Buy around 500 units.", "around 500", 0.45),
    ("Spend roughly ₹800000.", "₹800000", 0.45),
    ("Choose a reliable supplier.", "reliable", 0.40),
    ("Use a preferred vendor if practical.", "preferred", 0.50),
    ("Deliver soon.", "soon", 0.35),
    ("Keep irreversible exposure low.", "low", 0.30),
    ("Use a strong warranty.", "strong", 0.40),
    ("Pick acceptable certification.", "acceptable", 0.40),
    ("Pay a little more for faster delivery.", "a little more", 0.35),
    ("Buy production-grade parts.", "production-grade", 0.45),
    ("Use reasonable shipping.", "reasonable", 0.40),
    ("Prefer nearby suppliers.", "nearby", 0.50),
    ("Avoid expensive insurance.", "expensive", 0.45),
    ("Keep risk minimal.", "minimal", 0.35),
    ("Buy enough reserve units.", "enough", 0.35),
    ("Use standard replacement protection.", "standard", 0.45),
    ("Choose good-quality sensors.", "good-quality", 0.40),
    ("Accept modest delay if cheaper.", "modest", 0.40),
    ("Buy near the target budget.", "target", 0.45),
    ("Prefer robust packaging.", "robust", 0.45),
    ("Keep service fees small.", "small", 0.40),
    ("Use a trustworthy logistics partner.", "trustworthy", 0.40),
    ("Choose reasonable lead time.", "reasonable", 0.40),
    ("Pay only after sufficient verification.", "sufficient", 0.35),
    ("Use acceptable substitute parts.", "acceptable", 0.40),
    ("Keep the deposit conservative.", "conservative", 0.40),
    ("Choose a mature supplier.", "mature", 0.45),
    ("Accept a small premium for quality.", "small", 0.40),
    ("Use adequate certification evidence.", "adequate", 0.40),
    ("Buy a sensible backup quantity.", "sensible", 0.40),
]


@pytest.mark.parametrize("instruction,text,confidence", AMBIGUOUS)
def test_material_ambiguity_does_not_silently_validate(instruction, text, confidence):
    clause = EconomicClause(
        clause_id="amb", clause_type=ClauseType.CONDITION, normalized_value=text,
        source_span=span(instruction, text), provenance=Provenance.EXPLICIT_USER,
        materiality=0.8, confidence=confidence,
    )
    clauses = [clause]
    if "after" in instruction.lower():
        clauses.append(EconomicClause(
            clause_id="dep", clause_type=ClauseType.DEPENDENCY, normalized_value="after condition",
            source_span=span(instruction, "after"), provenance=Provenance.EXPLICIT_USER,
            materiality=0.8, confidence=0.9, depends_on=["amb"],
        ))
    report = FidelityValidator().validate(EconomicIntentContract(instruction=instruction, clauses=clauses))
    assert report.status == DecisionStatus.CLARIFICATION_REQUIRED
