from ecocommit.candidate7 import run_candidate7
from ecocommit.candidate7_provider import Candidate7SchemaError, PASS1_SYSTEM_PROMPT, PASS2_SYSTEM_PROMPT


def test_pass1_action_must_preserve_source_verb_verbatim():
    assert "ACTION fact" in PASS1_SYSTEM_PROMPT
    assert "own explicit action/domain verb verbatim" in PASS1_SYSTEM_PROMPT
    assert "Never replace, normalize, synonymize, infer, or substitute" in PASS1_SYSTEM_PROMPT


def test_pass2_empty_relations_are_first_class():
    assert '{"relations":[]}' in PASS2_SYSTEM_PROMPT
    assert "equally valid" in PASS2_SYSTEM_PROMPT
    assert "Do not invent a relation" in PASS2_SYSTEM_PROMPT


def test_candidate7_schema_error_preserves_provider_trace():
    trace = [
        {"stage": "relations", "attempt": 1, "outcome": "schema_invalid"},
        {"stage": "relations", "attempt": 2, "outcome": "schema_invalid"},
    ]

    class Provider:
        def parse_with_metadata(self, instruction: str):
            raise Candidate7SchemaError("relations", [{"location": "relations.0", "code": "invalid"}], trace)

    result = run_candidate7("Pay the invoice.", Provider())
    assert result.status == "REJECTED"
    assert result.error_code == "candidate7 relations remained schema-invalid"
    assert result.provider_trace == tuple(trace)
