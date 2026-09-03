from __future__ import annotations

import json
from pathlib import Path

from ecocommit.checkpoint_a_evidence import CheckpointAEvidenceReceipt, CheckpointAMetrics, FROZEN_A_DATASET_SHA256
from ecocommit.interpreter import OpenAICompatibleIntentProvider


class _FakeResponse:
    def __init__(self, body: dict):
        self._payload = json.dumps(body).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self, size=-1):
        return self._payload if size < 0 else self._payload[:size]


def _body(instruction: str, *, complete: bool) -> dict:
    clause = {
        "clause_id": "p",
        "clause_type": "PRODUCT",
        "normalized_value": "bearings",
        "source_span": {"text": "bearings", "start": 4, "end": 12},
        "provenance": "EXPLICIT_USER",
        "materiality": 0.9,
        "confidence": 1.0,
        "hardness": "HARD",
        "policy_class": None,
        "negated": False,
        "depends_on": [],
        "exception_to": [],
    }
    if not complete:
        clause.pop("confidence")
    candidate = {
        "instruction": instruction,
        "schema_version": "0.1",
        "clauses": [clause],
    }
    return {
        "id": "req_candidate4",
        "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(candidate)}}],
    }


def test_candidate4_allows_two_schema_corrections_but_accepts_first_valid_candidate(monkeypatch):
    instruction = "Buy bearings."
    responses = iter([
        _FakeResponse(_body(instruction, complete=False)),
        _FakeResponse(_body(instruction, complete=False)),
        _FakeResponse(_body(instruction, complete=True)),
    ])
    requests = []

    def fake_urlopen(req, timeout):
        requests.append(json.loads(req.data.decode("utf-8")))
        return next(responses)

    monkeypatch.setattr("ecocommit.interpreter.request.urlopen", fake_urlopen)
    provider = OpenAICompatibleIntentProvider(
        "https://example.invalid/v1",
        "secret",
        "model",
        allowed_hosts={"example.invalid"},
        max_attempts=3,
        max_schema_corrections=2,
    )

    result = provider.interpret_with_metadata(instruction)

    assert len(requests) == 3
    assert [item["outcome"] for item in result.provider_trace] == [
        "schema_invalid",
        "schema_invalid",
        "accepted",
    ]
    assert all(len(payload["messages"]) == 3 for payload in requests[1:])


def test_candidate4_historical_preregistration_remains_unchanged():
    from hashlib import sha256
    root = Path(__file__).resolve().parents[1]
    historical = root / "evidence/checkpoint-a-candidate-4-preregistration.json"
    retirement = json.loads((root / "evidence/checkpoint-a-candidate-4-retirement.json").read_text())
    assert sha256(historical.read_bytes()).hexdigest() == retirement["historical_preregistration_sha256"]
    assert retirement["status"] == "PREREGISTERED / SUPERSEDED / NEVER RUN"


def test_candidate4_production_receipt_keeps_frozen_gate():
    receipt = CheckpointAEvidenceReceipt(
        verification_mode="FROZEN_AGGREGATE",
        evidence_reference="github-actions://owner/repo/runs/1/candidate-4",
        aggregate_sha256="a" * 64,
        manifest_sha256="b" * 64,
        source_revision="c" * 40,
        candidate_version="A-CANDIDATE-4",
        dataset_sha256=FROZEN_A_DATASET_SHA256,
        total_cases=80,
        full_frozen_gate_run=True,
        gate_passed=True,
        metrics=CheckpointAMetrics(
            passed_cases=72,
            case_pass_rate=0.90,
            autonomous_coverage=0.55,
            selective_semantic_reliability=0.95,
            ambiguous_clarification_accuracy=0.80,
        ),
    )

    assert receipt.candidate_version == "A-CANDIDATE-4"
