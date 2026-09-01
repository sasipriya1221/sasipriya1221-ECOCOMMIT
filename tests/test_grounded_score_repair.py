import pytest
from pydantic import ValidationError

from ecocommit.contracts import EconomicClause, EconomicIntentContract


def _grounded_explicit_clause() -> dict:
    return {
        "clause_id": "auth_01",
        "clause_type": "AUTHORIZATION",
        "normalized_value": "Buy",
        "source_span": {"text": "Buy", "start": 0, "end": 3},
        "provenance": "EXPLICIT_USER",
        "materiality": 0.9,
        "confidence": 1.0,
    }


@pytest.mark.parametrize("missing_field", ["materiality", "confidence"])
def test_grounded_explicit_clause_does_not_invent_omitted_score(missing_field):
    candidate = _grounded_explicit_clause()
    del candidate[missing_field]

    with pytest.raises(ValidationError) as caught:
        EconomicClause.model_validate(candidate)

    assert any(
        error["loc"] == (missing_field,) and error["type"] == "missing"
        for error in caught.value.errors()
    )


def test_parent_contract_requires_both_scores_even_for_an_exact_explicit_span():
    with pytest.raises(ValidationError) as caught:
        EconomicIntentContract.model_validate({
            "instruction": "Buy bearings.",
            "schema_version": "0.1",
            "clauses": [{
                key: value
                for key, value in _grounded_explicit_clause().items()
                if key not in {"materiality", "confidence"}
            }],
        })

    missing = {error["loc"] for error in caught.value.errors() if error["type"] == "missing"}
    assert missing == {("clauses", 0, "materiality"), ("clauses", 0, "confidence")}


def test_supplied_grounded_scores_are_preserved_exactly():
    clause = EconomicClause.model_validate(_grounded_explicit_clause())

    assert clause.materiality == 0.9
    assert clause.confidence == 1.0
