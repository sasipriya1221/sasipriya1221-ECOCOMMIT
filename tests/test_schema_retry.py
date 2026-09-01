import json

import pytest
from pydantic import ValidationError

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


def _body(instruction: str, *, complete: bool) -> dict:
    clause = {
        "clause_id": "p",
        "clause_type": "PRODUCT",
        "normalized_value": "bearings",
        "source_span": {"text": "bearings", "start": 0, "end": 1},
        "provenance": "EXPLICIT_USER",
        "hardness": "HARD",
        "policy_class": None,
        "negated": False,
        "depends_on": [],
        "exception_to": [],
    }
    if complete:
        clause["materiality"] = 0.9
        clause["confidence"] = 1.0
    candidate = {
        "instruction": instruction,
        "schema_version": "0.1",
        "clauses": [clause],
    }
    return {"choices": [{"message": {"content": json.dumps(candidate)}}]}


def test_invalid_contract_candidate_gets_corrective_retry(monkeypatch):
    instruction = "Buy bearings."
    captured = []
    responses = [_body(instruction, complete=False), _body(instruction, complete=True)]

    def fake_urlopen(req, timeout):
        captured.append(json.loads(req.data.decode("utf-8")))
        return _FakeResponse(responses.pop(0))

    monkeypatch.delenv("ECOCOMMIT_LLM_REASONING_EFFORT", raising=False)
    monkeypatch.delenv("ECOCOMMIT_LLM_JSON_SCHEMA", raising=False)
    monkeypatch.delenv("ECOCOMMIT_LLM_MAX_COMPLETION_TOKENS", raising=False)
    monkeypatch.setattr("ecocommit.interpreter.request.urlopen", fake_urlopen)

    provider = OpenAICompatibleIntentProvider(
        "https://example.invalid/v1",
        "test-key",
        "model",
        max_attempts=2,
    )
    contract = provider.interpret(instruction)

    assert len(captured) == 2
    assert captured[1]["messages"][1] == captured[0]["messages"][1]
    correction = captured[1]["messages"][-1]["content"]
    assert "previous JSON candidate did not validate" in correction
    assert "materiality" in correction
    assert "confidence" in correction
    assert contract.clauses[0].materiality == 0.9
    assert contract.clauses[0].confidence == 1.0


def test_invalid_contract_candidate_is_not_fabricated_when_retry_budget_is_exhausted(monkeypatch):
    instruction = "Buy bearings."

    def fake_urlopen(req, timeout):
        return _FakeResponse(_body(instruction, complete=False))

    monkeypatch.delenv("ECOCOMMIT_LLM_REASONING_EFFORT", raising=False)
    monkeypatch.delenv("ECOCOMMIT_LLM_JSON_SCHEMA", raising=False)
    monkeypatch.delenv("ECOCOMMIT_LLM_MAX_COMPLETION_TOKENS", raising=False)
    monkeypatch.setattr("ecocommit.interpreter.request.urlopen", fake_urlopen)

    provider = OpenAICompatibleIntentProvider(
        "https://example.invalid/v1",
        "test-key",
        "model",
        max_attempts=1,
    )

    with pytest.raises(ValidationError):
        provider.interpret(instruction)
