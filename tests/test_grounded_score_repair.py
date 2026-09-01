import pytest
from pydantic import ValidationError

from ecocommit.contracts import EconomicClause, EconomicIntentContract


def test_grounded_explicit_clause_recovers_omitted_scores():
    instruction = "Buy bearings."
    contract = EconomicIntentContract.model_validate({
        "instruction": instruction,
        "schema_version": "0.1",
        "clauses": [{
            "clause_id": "auth_01",
            "clause_type": "AUTHORIZATION",
            "normalized_value": "Buy",
            "source_span": {"text": "Buy", "start": 0, "end": 3},
            "provenance": "EXPLICIT_USER",
        }],
    })

    clause = contract.clauses[0]
    assert clause.materiality == 1.0
    assert clause.confidence == 1.0


def test_ungrounded_or_inferred_clause_does_not_recover_omitted_scores():
    with pytest.raises(ValidationError):
        EconomicClause.model_validate({
            "clause_id": "inferred_01",
            "clause_type": "CONDITION",
            "normalized_value": "reasonable terms",
            "source_span": None,
            "provenance": "INFERENCE",
            "hardness": "SOFT",
        })


def test_parent_contract_still_rejects_false_explicit_span_after_score_repair():
    with pytest.raises(ValidationError):
        EconomicIntentContract.model_validate({
            "instruction": "Buy bearings.",
            "schema_version": "0.1",
            "clauses": [{
                "clause_id": "auth_01",
                "clause_type": "AUTHORIZATION",
                "normalized_value": "Purchase",
                "source_span": {"text": "Purchase", "start": 0, "end": 8},
                "provenance": "EXPLICIT_USER",
            }],
        })
