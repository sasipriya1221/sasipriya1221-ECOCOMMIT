from ecocommit.interpreter import OpenAICompatibleIntentProvider


def test_exception_target_is_mirrored_as_dependency_without_inventing_target():
    instruction = "Buy from an approved supplier unless another option is clearly better."
    raw = {
        "instruction": instruction,
        "schema_version": "0.1",
        "clauses": [
            {
                "clause_id": "supplier",
                "clause_type": "COUNTERPARTY",
                "normalized_value": "approved supplier",
                "source_span": {"text": "approved supplier", "start": 0, "end": 1},
                "provenance": "EXPLICIT_USER",
                "materiality": 0.9,
                "confidence": 0.95,
                "hardness": "HARD",
                "policy_class": None,
                "negated": False,
                "depends_on": [],
                "exception_to": [],
            },
            {
                "clause_id": "exception",
                "clause_type": "EXCEPTION",
                "normalized_value": "unless another option is clearly better",
                "source_span": {"text": "unless another option is clearly better", "start": 0, "end": 1},
                "provenance": "EXPLICIT_USER",
                "materiality": 0.8,
                "confidence": 0.75,
                "hardness": "SOFT",
                "policy_class": None,
                "negated": False,
                "depends_on": [],
                "exception_to": ["supplier"],
            },
        ],
    }

    repaired = OpenAICompatibleIntentProvider._repair_source_spans(raw, instruction)

    exception = next(c for c in repaired["clauses"] if c["clause_id"] == "exception")
    assert exception["exception_to"] == ["supplier"]
    assert exception["depends_on"] == ["supplier"]
