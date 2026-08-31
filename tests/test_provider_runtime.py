import io
import json
from urllib import error

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
            "clause_id": "p",
            "clause_type": "PRODUCT",
            "normalized_value": "bearings",
            "source_span": {"text": "bearings", "start": 0, "end": 1},
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


def test_runtime_reasoning_effort_is_sent_when_configured(monkeypatch):
    instruction = "Buy bearings."
    captured = {}

    def fake_urlopen(req, timeout):
        captured.update(json.loads(req.data.decode("utf-8")))
        return _FakeResponse(_provider_body(instruction))

    monkeypatch.setenv("ECOCOMMIT_LLM_REASONING_EFFORT", "low")
    monkeypatch.setattr("ecocommit.interpreter.request.urlopen", fake_urlopen)

    provider = OpenAICompatibleIntentProvider("https://example.invalid/v1", "secret", "model")
    contract = provider.interpret(instruction)

    assert captured["reasoning_effort"] == "low"
    assert contract.clauses[0].source_span.text == "bearings"


def test_http_429_respects_retry_after_with_hard_ceiling(monkeypatch):
    instruction = "Buy bearings."
    calls = 0
    sleeps = []

    def fake_urlopen(req, timeout):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise error.HTTPError(
                req.full_url,
                429,
                "Too Many Requests",
                {"Retry-After": "61"},
                io.BytesIO(b'{"error":{"message":"rate limited"}}'),
            )
        return _FakeResponse(_provider_body(instruction))

    monkeypatch.delenv("ECOCOMMIT_LLM_REASONING_EFFORT", raising=False)
    monkeypatch.setattr("ecocommit.interpreter.request.urlopen", fake_urlopen)
    monkeypatch.setattr("ecocommit.interpreter.time.sleep", sleeps.append)

    provider = OpenAICompatibleIntentProvider(
        "https://example.invalid/v1",
        "secret",
        "model",
        max_attempts=2,
        max_retry_delay=65,
    )
    provider.interpret(instruction)

    assert calls == 2
    assert sleeps == [61.0]


def test_transport_error_is_retried(monkeypatch):
    instruction = "Buy bearings."
    calls = 0
    sleeps = []

    def fake_urlopen(req, timeout):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise error.URLError("temporary network failure")
        return _FakeResponse(_provider_body(instruction))

    monkeypatch.delenv("ECOCOMMIT_LLM_REASONING_EFFORT", raising=False)
    monkeypatch.setattr("ecocommit.interpreter.request.urlopen", fake_urlopen)
    monkeypatch.setattr("ecocommit.interpreter.time.sleep", sleeps.append)

    provider = OpenAICompatibleIntentProvider(
        "https://example.invalid/v1",
        "secret",
        "model",
        max_attempts=2,
    )
    provider.interpret(instruction)

    assert calls == 2
    assert sleeps == [1.0]
