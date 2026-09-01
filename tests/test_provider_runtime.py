import io
import json
from urllib import error

import pytest

from ecocommit.interpreter import (
    CandidateContractError,
    OpenAICompatibleIntentProvider,
    ProviderRequestError,
)


class _FakeResponse:
    def __init__(self, body: dict):
        self._payload = json.dumps(body).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self, size=-1):
        return self._payload if size < 0 else self._payload[:size]


class _RawResponse:
    def __init__(self, payload: bytes):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self, size=-1):
        return self._payload if size < 0 else self._payload[:size]


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
    return {
        "id": "req_test",
        "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(candidate)}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
    }


def _provider(instruction: str, **kwargs):
    return OpenAICompatibleIntentProvider(
        "https://example.invalid/v1",
        "secret",
        "model",
        allowed_hosts={"example.invalid"},
        **kwargs,
    )


def test_runtime_reasoning_effort_is_sent_when_configured(monkeypatch):
    instruction = "Buy bearings."
    captured = {}

    def fake_urlopen(req, timeout):
        captured.update(json.loads(req.data.decode("utf-8")))
        return _FakeResponse(_provider_body(instruction))

    monkeypatch.setenv("ECOCOMMIT_LLM_REASONING_EFFORT", "low")
    monkeypatch.delenv("ECOCOMMIT_LLM_JSON_SCHEMA", raising=False)
    monkeypatch.delenv("ECOCOMMIT_LLM_MAX_COMPLETION_TOKENS", raising=False)
    monkeypatch.setattr("ecocommit.interpreter.request.urlopen", fake_urlopen)

    provider = _provider(instruction)
    contract = provider.interpret(instruction)

    assert captured["reasoning_effort"] == "low"
    assert contract.clauses[0].source_span.text == "bearings"


def test_strict_schema_and_completion_budget_are_sent_when_enabled(monkeypatch):
    instruction = "Buy bearings."
    captured = {}

    def fake_urlopen(req, timeout):
        captured.update(json.loads(req.data.decode("utf-8")))
        return _FakeResponse(_provider_body(instruction))

    monkeypatch.setenv("ECOCOMMIT_LLM_JSON_SCHEMA", "true")
    monkeypatch.setenv("ECOCOMMIT_LLM_MAX_COMPLETION_TOKENS", "2048")
    monkeypatch.delenv("ECOCOMMIT_LLM_REASONING_EFFORT", raising=False)
    monkeypatch.setattr("ecocommit.interpreter.request.urlopen", fake_urlopen)

    provider = _provider(instruction)
    provider.interpret(instruction)

    assert captured["max_completion_tokens"] == 2048
    assert captured["response_format"]["type"] == "json_schema"
    assert captured["response_format"]["json_schema"]["strict"] is True
    assert captured["response_format"]["json_schema"]["schema"]["additionalProperties"] is False
    user_payload = json.loads(captured["messages"][1]["content"])
    assert user_payload == {"instruction": instruction}


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
    monkeypatch.delenv("ECOCOMMIT_LLM_JSON_SCHEMA", raising=False)
    monkeypatch.delenv("ECOCOMMIT_LLM_MAX_COMPLETION_TOKENS", raising=False)
    monkeypatch.setattr("ecocommit.interpreter.request.urlopen", fake_urlopen)
    monkeypatch.setattr("ecocommit.interpreter.time.sleep", sleeps.append)

    provider = _provider(
        instruction,
        max_attempts=2,
        max_retry_delay=65,
    )
    result = provider.interpret_with_metadata(instruction)

    assert calls == 2
    assert sleeps == [61.0]
    assert [item["outcome"] for item in result.provider_trace] == [
        "provider_error",
        "accepted",
    ]
    assert result.provider_trace[0] == {
        "attempt": 1,
        "outcome": "provider_error",
        "code": "HTTP_429",
        "transient": True,
    }


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
    monkeypatch.delenv("ECOCOMMIT_LLM_JSON_SCHEMA", raising=False)
    monkeypatch.delenv("ECOCOMMIT_LLM_MAX_COMPLETION_TOKENS", raising=False)
    monkeypatch.setattr("ecocommit.interpreter.request.urlopen", fake_urlopen)
    monkeypatch.setattr("ecocommit.interpreter.time.sleep", sleeps.append)

    provider = _provider(
        instruction,
        max_attempts=2,
    )
    result = provider.interpret_with_metadata(instruction)

    assert calls == 2
    assert sleeps == [1.0]
    assert [item["outcome"] for item in result.provider_trace] == [
        "provider_error",
        "accepted",
    ]
    assert result.provider_trace[0]["code"] == "TRANSPORT_ERROR"
    assert result.provider_trace[0]["transient"] is True


def test_schema_invalid_candidate_gets_one_bounded_correction(monkeypatch):
    instruction = "Buy bearings from Vendor A."
    malformed = _provider_body(instruction)
    raw = json.loads(malformed["choices"][0]["message"]["content"])
    raw["clauses"].append({
        "clause_id": "auth_01",
        "clause_type": "AUTHORIZATION",
        "normalized_value": "Buy",
        "source_span": {"text": "Buy", "start": 0, "end": 3},
        "provenance": "EXPLICIT_USER",
    })
    malformed["choices"][0]["message"]["content"] = json.dumps(raw)
    valid = _provider_body(instruction)
    requests = []
    responses = iter([_FakeResponse(malformed), _FakeResponse(valid)])

    def fake_urlopen(req, timeout):
        requests.append(json.loads(req.data.decode("utf-8")))
        return next(responses)

    monkeypatch.setattr("ecocommit.interpreter.request.urlopen", fake_urlopen)
    result = _provider(instruction, max_attempts=2).interpret_with_metadata(instruction)

    assert len(requests) == 2
    correction = requests[1]["messages"][-1]["content"]
    assert "clauses.1.materiality (missing)" in correction
    assert "clauses.1.confidence (missing)" in correction
    assert [item["outcome"] for item in result.provider_trace] == ["schema_invalid", "accepted"]
    assert result.provider_trace[0]["candidate_sha256"]
    assert result.provider_trace[1]["finish_reason"] == "stop"
    assert result.provider_trace[1]["usage"]["total_tokens"] == 30


def test_missing_top_level_clauses_is_corrected_without_inventing_locally(monkeypatch):
    instruction = "Purchase parts with reasonable protection."
    malformed = {
        "id": "req_bad",
        "choices": [{"finish_reason": "stop", "message": {"content": json.dumps({
            "instruction": instruction,
            "schema_version": "0.1",
        })}}],
    }
    responses = iter([_FakeResponse(malformed), _FakeResponse(_provider_body(instruction))])
    monkeypatch.setattr("ecocommit.interpreter.request.urlopen", lambda req, timeout: next(responses))

    result = _provider(instruction, max_attempts=2).interpret_with_metadata(instruction)

    assert result.provider_trace[0]["issues"] == [{"location": "clauses", "code": "missing"}]
    assert result.provider_trace[1]["outcome"] == "accepted"


@pytest.mark.parametrize(
    ("original", "replacement", "expected_code"),
    [
        (
            '"confidence": 1.0',
            '"confidence": 0.25, "confidence": 1.0',
            "duplicate_json_key",
        ),
        ('"materiality": 0.9', '"materiality": NaN', "non_finite_number"),
        (
            '"normalized_value": "bearings"',
            '"normalized_value": "\\ud800"',
            "invalid_json_value",
        ),
    ],
)
def test_non_strict_candidate_json_requires_bounded_model_correction(
    original,
    replacement,
    expected_code,
    monkeypatch,
):
    instruction = "Buy bearings."
    malformed = _provider_body(instruction)
    content = malformed["choices"][0]["message"]["content"]
    malformed["choices"][0]["message"]["content"] = content.replace(
        original,
        replacement,
        1,
    )
    responses = iter([_FakeResponse(malformed), _FakeResponse(_provider_body(instruction))])
    monkeypatch.setattr(
        "ecocommit.interpreter.request.urlopen",
        lambda req, timeout: next(responses),
    )

    result = _provider(instruction, max_attempts=2).interpret_with_metadata(instruction)

    assert result.provider_trace[0]["issues"] == [{
        "location": "root",
        "code": expected_code,
    }]
    assert result.provider_trace[1]["outcome"] == "accepted"


def test_duplicate_provider_envelope_keys_are_malformed_not_candidate_evidence(monkeypatch):
    instruction = "Buy bearings."
    encoded = json.dumps(_provider_body(instruction))
    duplicate = encoded.replace('"choices":', '"choices": [], "choices":', 1)
    monkeypatch.setattr(
        "ecocommit.interpreter.request.urlopen",
        lambda req, timeout: _RawResponse(duplicate.encode("utf-8")),
    )

    with pytest.raises(ProviderRequestError) as caught:
        _provider(instruction, max_attempts=1).interpret(instruction)

    assert caught.value.code == "MALFORMED_RESPONSE"
    assert caught.value.provider_trace[-1]["outcome"] == "provider_error"


@pytest.mark.parametrize("missing_field", [
    "materiality",
    "confidence",
    "source_span",
    "hardness",
    "policy_class",
    "negated",
    "depends_on",
    "exception_to",
])
def test_model_default_fields_must_still_be_explicit(missing_field, monkeypatch):
    instruction = "Buy bearings."
    malformed = _provider_body(instruction)
    raw = json.loads(malformed["choices"][0]["message"]["content"])
    del raw["clauses"][0][missing_field]
    malformed["choices"][0]["message"]["content"] = json.dumps(raw)
    responses = iter([_FakeResponse(malformed), _FakeResponse(_provider_body(instruction))])
    monkeypatch.setattr("ecocommit.interpreter.request.urlopen", lambda req, timeout: next(responses))

    result = _provider(instruction, max_attempts=3).interpret_with_metadata(instruction)

    assert result.provider_trace[0]["issues"] == [{
        "location": f"clauses.0.{missing_field}",
        "code": "missing",
    }]
    assert result.provider_trace[1]["outcome"] == "accepted"


def test_only_one_schema_correction_is_attempted_even_with_larger_retry_budget(monkeypatch):
    instruction = "Buy bearings."
    malformed = _provider_body(instruction)
    raw = json.loads(malformed["choices"][0]["message"]["content"])
    del raw["clauses"][0]["confidence"]
    malformed["choices"][0]["message"]["content"] = json.dumps(raw)
    calls = 0

    def fake_urlopen(req, timeout):
        nonlocal calls
        calls += 1
        return _FakeResponse(malformed)

    monkeypatch.setattr("ecocommit.interpreter.request.urlopen", fake_urlopen)

    with pytest.raises(CandidateContractError) as caught:
        _provider(instruction, max_attempts=5).interpret(instruction)

    assert calls == 2
    assert len(caught.value.provider_trace) == 2
    assert caught.value.correction_attempted is True


def test_retry_budget_exhaustion_before_first_schema_failure_is_not_called_corrected(
    monkeypatch,
):
    instruction = "Buy bearings."
    malformed = _provider_body(instruction)
    raw = json.loads(malformed["choices"][0]["message"]["content"])
    del raw["clauses"][0]["confidence"]
    malformed["choices"][0]["message"]["content"] = json.dumps(raw)
    calls = 0

    def fake_urlopen(req, timeout):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise error.URLError("temporary")
        return _FakeResponse(malformed)

    monkeypatch.setattr("ecocommit.interpreter.request.urlopen", fake_urlopen)
    monkeypatch.setattr("ecocommit.interpreter.time.sleep", lambda delay: None)

    with pytest.raises(CandidateContractError) as caught:
        _provider(instruction, max_attempts=2).interpret(instruction)

    assert calls == 2
    assert caught.value.correction_attempted is False
    assert [item["outcome"] for item in caught.value.provider_trace] == [
        "provider_error",
        "schema_invalid",
    ]


def test_original_instruction_mismatch_requires_model_correction(monkeypatch):
    instruction = "Buy bearings."
    malformed = _provider_body(instruction)
    raw = json.loads(malformed["choices"][0]["message"]["content"])
    raw["instruction"] = "Buy a different product."
    malformed["choices"][0]["message"]["content"] = json.dumps(raw)
    responses = iter([_FakeResponse(malformed), _FakeResponse(_provider_body(instruction))])
    monkeypatch.setattr("ecocommit.interpreter.request.urlopen", lambda req, timeout: next(responses))

    result = _provider(instruction, max_attempts=2).interpret_with_metadata(instruction)

    assert result.provider_trace[0]["issues"] == [{
        "location": "instruction",
        "code": "original_mismatch",
    }]


def test_repeated_schema_failure_is_terminal_and_redacted(monkeypatch):
    instruction = "Buy bearings."
    sensitive = "private-provider-content"
    malformed = {
        "id": "req_bad",
        "choices": [{"finish_reason": "length", "message": {"content": json.dumps({
            "instruction": instruction,
            "schema_version": "0.1",
            "debug": sensitive,
        })}}],
    }
    monkeypatch.setattr("ecocommit.interpreter.request.urlopen", lambda req, timeout: _FakeResponse(malformed))

    with pytest.raises(CandidateContractError) as caught:
        _provider(instruction, max_attempts=2).interpret(instruction)

    assert sensitive not in str(caught.value)
    assert len(caught.value.provider_trace) == 2
    assert all(item["finish_reason"] == "length" for item in caught.value.provider_trace)
    assert all("candidate_sha256" in item for item in caught.value.provider_trace)


@pytest.mark.parametrize("url", [
    "http://api.groq.com/openai/v1",
    "https://user:secret@api.groq.com/openai/v1",
    "https://api.groq.com/openai/v1?redirect=evil",
    "https://api.groq.com/openai/v1#fragment",
    "https://attacker.example/v1",
])
def test_provider_url_rejects_credential_exfiltration_surfaces(url):
    with pytest.raises(ValueError):
        OpenAICompatibleIntentProvider(url, "secret", "model")


def test_provider_redirect_is_terminal_and_authorization_is_not_redirectable(
    monkeypatch,
):
    instruction = "Buy bearings."
    seen = {}

    class RedirectedResponse(_FakeResponse):
        def geturl(self):
            return "https://attacker.example/chat/completions"

    def fake_urlopen(req, timeout):
        seen["authorization"] = req.get_header("Authorization")
        seen["redirectable_authorization"] = req.headers.get("Authorization")
        return RedirectedResponse(_provider_body(instruction))

    monkeypatch.setattr("ecocommit.interpreter.request.urlopen", fake_urlopen)

    with pytest.raises(ProviderRequestError) as caught:
        _provider(instruction, max_attempts=3).interpret(instruction)

    assert caught.value.code == "REDIRECT_REJECTED"
    assert caught.value.transient is False
    assert caught.value.attempts == 1
    assert caught.value.provider_trace == ({
        "attempt": 1,
        "outcome": "provider_error",
        "code": "REDIRECT_REJECTED",
        "transient": False,
    },)
    assert seen["authorization"] == "Bearer secret"
    assert seen["redirectable_authorization"] is None


def test_oversized_success_response_is_rejected_without_retaining_body(monkeypatch):
    instruction = "Buy bearings."
    sensitive = "sensitive" * 100
    monkeypatch.setattr(
        "ecocommit.interpreter.request.urlopen",
        lambda req, timeout: _FakeResponse({"oversized": sensitive}),
    )

    with pytest.raises(ProviderRequestError) as caught:
        _provider(instruction, max_attempts=1, max_response_bytes=32).interpret(instruction)

    assert caught.value.code == "RESPONSE_TOO_LARGE"
    assert sensitive not in str(caught.value)


def test_http_error_body_is_not_retained(monkeypatch):
    instruction = "Buy bearings."
    sensitive = b'{"error":{"message":"account-private-detail"}}'

    def fake_urlopen(req, timeout):
        raise error.HTTPError(req.full_url, 400, "Bad Request", {}, io.BytesIO(sensitive))

    monkeypatch.setattr("ecocommit.interpreter.request.urlopen", fake_urlopen)

    with pytest.raises(ProviderRequestError) as caught:
        _provider(instruction, max_attempts=1).interpret(instruction)

    assert caught.value.code == "HTTP_400"
    assert "account-private-detail" not in str(caught.value)


def test_schema_failure_then_provider_deferral_retains_both_facts(monkeypatch):
    instruction = "Buy bearings."
    malformed = _provider_body(instruction)
    raw = json.loads(malformed["choices"][0]["message"]["content"])
    del raw["clauses"][0]["confidence"]
    malformed["choices"][0]["message"]["content"] = json.dumps(raw)
    calls = 0

    def fake_urlopen(req, timeout):
        nonlocal calls
        calls += 1
        if calls == 1:
            return _FakeResponse(malformed)
        raise error.HTTPError(req.full_url, 429, "Too Many Requests", {}, io.BytesIO(b"private"))

    monkeypatch.setattr("ecocommit.interpreter.request.urlopen", fake_urlopen)

    with pytest.raises(ProviderRequestError) as caught:
        _provider(instruction, max_attempts=2).interpret(instruction)

    assert caught.value.transient is True
    assert [item["outcome"] for item in caught.value.provider_trace] == [
        "schema_invalid",
        "provider_error",
    ]


def test_schema_correction_retains_intermediate_provider_retry_chronology(monkeypatch):
    instruction = "Buy bearings."
    malformed = _provider_body(instruction)
    raw = json.loads(malformed["choices"][0]["message"]["content"])
    del raw["clauses"][0]["confidence"]
    malformed["choices"][0]["message"]["content"] = json.dumps(raw)
    calls = 0

    def fake_urlopen(req, timeout):
        nonlocal calls
        calls += 1
        if calls == 1:
            return _FakeResponse(malformed)
        if calls == 2:
            raise error.HTTPError(
                req.full_url,
                503,
                "Service Unavailable",
                {},
                io.BytesIO(b"private"),
            )
        return _FakeResponse(_provider_body(instruction))

    sleeps = []
    monkeypatch.setattr("ecocommit.interpreter.request.urlopen", fake_urlopen)
    monkeypatch.setattr("ecocommit.interpreter.time.sleep", sleeps.append)

    result = _provider(instruction, max_attempts=3).interpret_with_metadata(instruction)

    assert calls == 3
    assert sleeps == [2.0]
    assert [item["outcome"] for item in result.provider_trace] == [
        "schema_invalid",
        "provider_error",
        "accepted",
    ]
    assert [item["attempt"] for item in result.provider_trace] == [1, 2, 3]
    assert result.provider_trace[1]["code"] == "HTTP_503"
    assert result.provider_trace[1]["transient"] is True
