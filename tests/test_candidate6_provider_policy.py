from ecocommit.candidate6_provider import GroqSemanticIRProvider


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
