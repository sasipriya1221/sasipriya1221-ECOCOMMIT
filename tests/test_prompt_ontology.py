import json

from ecocommit.interpreter import OpenAICompatibleIntentProvider


class _FakeResponse:
    def __init__(self, body: dict):
        self._payload = json.dumps(body).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self._payload


def _provider_body(instruction: str) -> dict:
    candidate = {
        "instruction": instruction,
        "schema_version": "0.1",
        "clauses": [{
            "clause_id": "t1",
            "clause_type": "TEMPORAL",
            "normalized_value": "within five days",
            "source_span": {"text": "within five days", "start": 0, "end": 1},
            "provenance": "EXPLICIT_USER",
            "materiality": 0.9,
            "confidence": 1.0,
            "hardness": "HARD",
            "policy_class": None,
            "negated": False,
            "depends_on": [],
            "exception_to": [],
        }],
    }
    return {"choices": [{"message": {"content": json.dumps(candidate)}}]}


def test_provider_prompt_disambiguates_deadlines_confidence_and_gating(monkeypatch):
    instruction = "Deliver within five days."
    captured = {}

    def fake_urlopen(req, timeout):
        captured.update(json.loads(req.data.decode("utf-8")))
        return _FakeResponse(_provider_body(instruction))

    monkeypatch.delenv("ECOCOMMIT_LLM_REASONING_EFFORT", raising=False)
    monkeypatch.delenv("ECOCOMMIT_LLM_JSON_SCHEMA", raising=False)
    monkeypatch.delenv("ECOCOMMIT_LLM_MAX_COMPLETION_TOKENS", raising=False)
    monkeypatch.setattr("ecocommit.interpreter.request.urlopen", fake_urlopen)

    provider = OpenAICompatibleIntentProvider("https://example.invalid/v1", "secret", "model")
    provider.interpret(instruction)

    system = captured["messages"][0]["content"]
    assert "'within five days'" in system
    assert "TEMPORAL, not CONDITION or DEPENDENCY" in system
    assert "confidence means certainty that this clause faithfully extracts" in system
    assert "unless/otherwise/only if/provided that/in which case" in system
    assert "preserve the gating relationship with depends_on or a DEPENDENCY clause" in system
