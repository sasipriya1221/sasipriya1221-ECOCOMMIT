from __future__ import annotations

from email.message import Message
from urllib import error

import pytest

import ecocommit.candidate7_provider as provider_mod
from ecocommit.candidate7_provider import GroqCandidate7Provider
from ecocommit.interpreter import ProviderRequestError


def test_candidate7_provider_paces_all_requests(monkeypatch):
    provider = GroqCandidate7Provider("test-key", min_request_interval_seconds=3.0)
    times = iter([10.0, 11.0, 13.0])
    sleeps: list[float] = []
    monkeypatch.setattr(provider_mod.time, "monotonic", lambda: next(times))
    monkeypatch.setattr(provider_mod.time, "sleep", sleeps.append)

    provider._pace_request()
    provider._pace_request()

    assert sleeps == [2.0]
    assert provider._last_request_started == 13.0


def test_candidate7_429_preserves_rate_limit_headers(monkeypatch):
    headers = Message()
    headers["x-ratelimit-limit-requests"] = "1000"
    headers["x-ratelimit-remaining-requests"] = "0"
    headers["x-ratelimit-reset-requests"] = "42s"
    headers["x-ratelimit-limit-tokens"] = "8000"
    headers["x-ratelimit-remaining-tokens"] = "0"
    headers["x-ratelimit-reset-tokens"] = "3.5s"
    headers["retry-after"] = "4"

    def fail(*args, **kwargs):
        raise error.HTTPError("https://api.groq.com/openai/v1/chat/completions", 429, "rate limited", headers, None)

    monkeypatch.setattr(provider_mod.request, "urlopen", fail)
    provider = GroqCandidate7Provider("test-key", min_request_interval_seconds=0)

    with pytest.raises(ProviderRequestError) as captured:
        provider._request([{"role": "user", "content": "ping"}], 1)

    exc = captured.value
    assert exc.code == "HTTP_429"
    assert exc.retry_after_seconds == 4.0
    assert exc.rate_limit_headers == {
        "x-ratelimit-limit-requests": "1000",
        "x-ratelimit-remaining-requests": "0",
        "x-ratelimit-reset-requests": "42s",
        "x-ratelimit-limit-tokens": "8000",
        "x-ratelimit-remaining-tokens": "0",
        "x-ratelimit-reset-tokens": "3.5s",
        "retry-after": "4",
    }


def test_candidate7_trace_includes_429_headers(monkeypatch):
    provider = GroqCandidate7Provider("test-key", max_attempts_per_pass=1, min_request_interval_seconds=0)
    exc = ProviderRequestError("HTTP_429", attempts=1, transient=True)
    exc.rate_limit_headers = {
        "x-ratelimit-remaining-requests": "0",
        "x-ratelimit-reset-requests": "10s",
        "retry-after": "10",
    }

    def fail(*args, **kwargs):
        raise exc

    monkeypatch.setattr(provider, "_request", fail)
    with pytest.raises(ProviderRequestError) as captured:
        provider._run_stage("facts", [{"role": "user", "content": "x"}], lambda value: value)

    assert captured.value.provider_trace == [{
        "stage": "facts",
        "attempt": 1,
        "outcome": "provider_error",
        "code": "HTTP_429",
        "transient": True,
        "rate_limit_headers": {
            "x-ratelimit-remaining-requests": "0",
            "x-ratelimit-reset-requests": "10s",
            "retry-after": "10",
        },
    }]
