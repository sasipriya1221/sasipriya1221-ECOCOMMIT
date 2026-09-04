from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ecocommit.interpreter import ProviderRequestError

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "candidate7_pass2_qualification.py"
SPEC = importlib.util.spec_from_file_location("candidate7_pass2_qualification", MODULE_PATH)
assert SPEC and SPEC.loader
harness = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(harness)


class FakeClock:
    def __init__(self):
        self.seconds = 0.0
        self.sleeps = []
        self.origin = datetime(2026, 9, 4, 12, 0, 0, tzinfo=timezone.utc)

    def utc_now(self):
        return self.origin + timedelta(seconds=self.seconds)

    def monotonic(self):
        return self.seconds

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.seconds += seconds


class GoodProvider:
    def _request(self, messages, attempt):
        payload = json.loads(messages[-1]["content"])
        if payload["instruction"].startswith("Pay printer"):
            parsed = {
                "action_entity_decisions": [
                    {"action":"F0001","entity":"F0002","decision":"ACTION_OBJECT","justification_span":"Pay printer"},
                    {"action":"F0001","entity":"F0004","decision":"NONE","justification_span":None},
                ],
                "relations": [
                    {"kind":"CONSTRAINT_APPLIES_TO","left":"F0003","right":"F0001","justification_span":"Pay printer exactly ₹32,500"}
                ],
            }
        else:
            parsed = {
                "action_entity_decisions": [
                    {"action":"F0001","entity":"F0002","decision":"ACTION_OBJECT","justification_span":"Order 500 envelopes"}
                ],
                "relations": [
                    {"kind":"GUARDS_ACTION","left":"F0003","right":"F0001","justification_span":"only if warehouse count below 100"}
                ],
            }
        return parsed, {"attempt": 1, "candidate_sha256": "0" * 64, "finish_reason": "stop"}


def provider_error(status=429, *, retry=0.0, headers=None):
    exc = ProviderRequestError(f"HTTP_{status}", attempts=1, transient=True)
    exc.retry_after_seconds = retry
    exc.rate_limit_headers = headers or {}
    return exc


def test_sanitized_rate_limit_metadata_preservation():
    exc = provider_error(429, retry=61.5, headers={
        "Retry-After": "61.5",
        "x-ratelimit-limit-requests": "30",
        "x-ratelimit-remaining-requests": "0",
        "x-ratelimit-reset-requests": "1m1.5s",
        "x-ratelimit-limit-tokens": "6000",
        "x-ratelimit-remaining-tokens": "0",
        "x-ratelimit-reset-tokens": "2m",
    })
    saved = harness._sanitize_provider_error(exc)
    assert saved == {
        "http_status": 429,
        "transient": True,
        "retry_after_seconds": 61.5,
        "headers": {
            "Retry-After": "61.5",
            "x-ratelimit-limit-requests": "30",
            "x-ratelimit-remaining-requests": "0",
            "x-ratelimit-reset-requests": "1m1.5s",
            "x-ratelimit-limit-tokens": "6000",
            "x-ratelimit-remaining-tokens": "0",
            "x-ratelimit-reset-tokens": "2m",
        },
    }


def test_secret_headers_are_excluded():
    exc = provider_error(headers={
        "Authorization": "Bearer NEVER_SAVE",
        "Cookie": "session=NEVER_SAVE",
        "X-Api-Key": "NEVER_SAVE",
        "x-ratelimit-remaining-requests": "0",
    })
    saved = harness._sanitize_provider_error(exc)
    text = json.dumps(saved)
    assert "NEVER_SAVE" not in text
    assert set(saved["headers"]) == {"x-ratelimit-remaining-requests"}


def test_incremental_evidence_written_before_and_after_attempt(tmp_path, monkeypatch):
    writes = []
    real_write = harness._write_evidence

    def capture(path, row):
        writes.append(dict(row))
        real_write(path, row)

    monkeypatch.setattr(harness, "_write_evidence", capture)
    row = harness.run_attempt(
        "D009", 1, tmp_path / "d009-1.json",
        provider_factory=GoodProvider,
        clock=FakeClock(),
    )
    assert writes[0]["status"] == "attempt_started"
    assert "provider_attempt_started_at_utc" in writes[0]
    assert writes[-1]["status"] == "accepted"
    assert "provider_attempt_finished_at_utc" in writes[-1]
    assert row["status"] == "accepted"


def test_sixty_second_minimum_pacing_uses_fake_clock(tmp_path):
    clock = FakeClock()
    summary = harness.run_qualification(tmp_path, provider_factory=GoodProvider, clock=clock)
    assert summary["qualification_status"] == "PASS"
    assert len(clock.sleeps) == 9
    assert all(delay == 60.0 for delay in clock.sleeps)


def test_longer_provider_directed_wait_adds_five_second_buffer(tmp_path):
    clock = FakeClock()
    calls = {"count": 0}

    class Provider:
        def _request(self, messages, attempt):
            calls["count"] += 1
            if calls["count"] == 1:
                raise provider_error(503, retry=90.0, headers={"Retry-After": "90"})
            raise provider_error(429)

    summary = harness.run_qualification(tmp_path, provider_factory=Provider, clock=clock)
    assert clock.sleeps == [95.0]
    assert summary["qualification_status"] == "INCONCLUSIVE"


def test_first_429_stops_complete_qualification_immediately(tmp_path):
    clock = FakeClock()
    calls = {"count": 0}

    class Provider:
        def _request(self, messages, attempt):
            calls["count"] += 1
            raise provider_error(429, retry=120.0, headers={
                "Retry-After": "120",
                "Authorization": "Bearer NEVER_SAVE",
            })

    summary = harness.run_qualification(tmp_path, provider_factory=Provider, clock=clock)
    assert calls["count"] == 1
    assert summary["qualification_status"] == "INCONCLUSIVE"
    assert summary["stopped_after_first_http_429"] is True
    assert summary["provider_calls_recorded"] == 1
    assert clock.sleeps == []
    saved = (tmp_path / "d003-1.json").read_text(encoding="utf-8")
    assert "NEVER_SAVE" not in saved
    assert not (tmp_path / "d003-2.json").exists()
