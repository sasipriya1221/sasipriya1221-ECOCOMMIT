import re

from ecocommit.candidate6 import SYSTEM_PROMPT
from ecocommit.candidate6_provider import COMPACT_SEMANTIC_IR_SCHEMA, GroqSemanticIRProvider


def test_candidate6_groq_payload_disables_reasoning_in_json_mode(monkeypatch):
    provider = GroqSemanticIRProvider("test-key", max_attempts=1)
    seen = {}

    def fake_request(payload, attempt):
        seen.update(payload)
        return {
            "id": "test",
            "choices": [{
                "finish_reason": "stop",
                "message": {
                    "content": '{"schema_version":"semantic-ir-v1","entities":[{"id":"E1","kind":"OBJECT","text":"cables","source":{"kind":"SPAN","quote":"cables","occurrence":1}}],"actions":[{"id":"A1","kind":"BUY","object":"E1","counterparty":null,"quantity":null,"source":{"kind":"SPAN","quote":"Buy cables","occurrence":1}}],"constraints":[],"predicates":[],"guards":[],"dependencies":[],"exceptions":[],"ambiguities":[]}'
                },
            }],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }

    monkeypatch.setattr(provider, "_request", fake_request)
    result = provider.parse_with_metadata("Buy cables")
    assert result.semantic_ir.actions[0].kind.value == "BUY"
    assert seen["reasoning_effort"] == "none"
    assert seen["response_format"] == {"type": "json_object"}
    assert seen["max_completion_tokens"] == 2048


def test_compact_schema_uses_structured_source_objects_everywhere():
    span = {"kind": "SPAN", "quote": "exact substring from instruction", "occurrence": 1}
    assert COMPACT_SEMANTIC_IR_SCHEMA["entities"][0]["source"] == span
    assert COMPACT_SEMANTIC_IR_SCHEMA["actions"][0]["source"] == span
    assert COMPACT_SEMANTIC_IR_SCHEMA["actions"][0]["quantity"]["source"] == span
    assert COMPACT_SEMANTIC_IR_SCHEMA["constraints"][0]["money"]["source"] == span
    assert COMPACT_SEMANTIC_IR_SCHEMA["predicates"][0]["source"] == span
    assert COMPACT_SEMANTIC_IR_SCHEMA["guards"][0]["source"] == span
    assert COMPACT_SEMANTIC_IR_SCHEMA["dependencies"][0]["source"] == span
    assert COMPACT_SEMANTIC_IR_SCHEMA["exceptions"][0]["source"] == span
    assert "one_of" in COMPACT_SEMANTIC_IR_SCHEMA["ambiguities"][0]["source"]


def test_default_retry_window_can_honor_long_provider_reset():
    provider = GroqSemanticIRProvider("test-key")
    assert provider.max_attempts == 3
    assert provider.max_retry_delay >= 600


def test_system_prompt_enforces_general_field_type_discipline():
    assert "Never encode money, price, fee, budget" in SYSTEM_PROMPT
    assert "Never encode a time span, renewal period" in SYSTEM_PROMPT
    assert "A concrete descriptive entity named by the instruction is not ambiguous" in SYSTEM_PROMPT
    assert 'Every Boolean expression MUST be an object with an explicit op' in SYSTEM_PROMPT
    assert "Predicate.operator MUST be one of" in SYSTEM_PROMPT


def test_system_prompt_contains_no_development_holdout_or_official_case_ids():
    assert re.search(r"\bD\d{3}\b", SYSTEM_PROMPT) is None
    assert re.search(r"\bH\d{3}\b", SYSTEM_PROMPT) is None
    assert re.search(r"\bC\d{3}\b", SYSTEM_PROMPT) is None


def test_schema_correction_reiterates_boolean_and_quantity_types(monkeypatch):
    provider = GroqSemanticIRProvider("test-key", max_attempts=2, max_schema_corrections=1)
    seen = []

    def fake_request(payload, attempt):
        seen.append(payload)
        if attempt == 1:
            return {
                "id": "bad",
                "choices": [{"finish_reason": "stop", "message": {"content": '{"schema_version":"semantic-ir-v1","entities":[{"id":"E1","kind":"OBJECT","text":"cables","source":{"kind":"SPAN","quote":"cables","occurrence":1}}],"actions":[{"id":"A1","kind":"BUY","object":"E1","counterparty":null,"quantity":{"raw_value":"4","raw_unit":null,"source":{"kind":"SPAN","quote":"4 cables","occurrence":1}},"source":{"kind":"SPAN","quote":"Buy 4 cables","occurrence":1}}],"constraints":[],"predicates":[],"guards":[],"dependencies":[],"exceptions":[],"ambiguities":[]}'}}],
                "usage": {},
            }
        return {
            "id": "good",
            "choices": [{"finish_reason": "stop", "message": {"content": '{"schema_version":"semantic-ir-v1","entities":[{"id":"E1","kind":"OBJECT","text":"cables","source":{"kind":"SPAN","quote":"cables","occurrence":1}}],"actions":[{"id":"A1","kind":"BUY","object":"E1","counterparty":null,"quantity":{"raw_value":"4","raw_unit":"cables","source":{"kind":"SPAN","quote":"4 cables","occurrence":1}},"source":{"kind":"SPAN","quote":"Buy 4 cables","occurrence":1}}],"constraints":[],"predicates":[],"guards":[],"dependencies":[],"exceptions":[],"ambiguities":[]}'}}],
            "usage": {},
        }

    monkeypatch.setattr(provider, "_request", fake_request)
    provider.parse_with_metadata("Buy 4 cables")
    correction = seen[1]["messages"][-1]["content"]
    assert "Boolean expr/when must be an object with op=ATOM|NOT|AND|OR" in correction
    assert "raw_value/raw_unit must be strings" in correction
    assert "never put money or time spans in quantity" in correction
