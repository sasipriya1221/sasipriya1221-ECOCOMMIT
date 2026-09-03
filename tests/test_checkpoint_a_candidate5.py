from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import checkpoint_a_candidate5 as candidate5
from checkpoint_a_live import _ambiguous_cases, _clear_cases, _evaluate_one
from checkpoint_a_protocol import bind_row, build_manifest, canonical_sha256
from ecocommit.interpreter import CandidateContractError
from ecocommit.validator import FidelityValidator
from test_checkpoint_a_candidate4 import _FakeResponse, _body


@pytest.mark.parametrize("invalid_count", [0, 1, 2, 3])
def test_uniform_2048_budget_and_bounded_correction_terminality(monkeypatch, invalid_count):
    requests = []
    def respond(req, timeout):
        requests.append(json.loads(req.data))
        assert timeout == 60
        return _FakeResponse(_body("Buy bearings.", complete=len(requests) > invalid_count))
    monkeypatch.setattr("ecocommit.interpreter.request.urlopen", respond)
    provider = candidate5.candidate_provider("fixture-only")
    if invalid_count == 3:
        with pytest.raises(CandidateContractError):
            provider.interpret_with_metadata("Buy bearings.")
    else:
        provider.interpret_with_metadata("Buy bearings.")
    assert len(requests) == min(invalid_count + 1, 3)
    assert all(r["max_completion_tokens"] == 2048 for r in requests)
    assert all(r["model"] == "qwen/qwen3.6-27b" for r in requests)
    assert all(r["reasoning_effort"] == "none" and r["response_format"] == {"type": "json_object"} for r in requests)


def test_first_schema_valid_semantic_failure_is_terminal(monkeypatch):
    calls = []
    gold = _clear_cases()[0]
    def respond(req, timeout):
        calls.append(req)
        return _FakeResponse(_body(gold.instruction, complete=True))
    monkeypatch.setattr("ecocommit.interpreter.request.urlopen", respond)
    row = _evaluate_one(gold, candidate5.candidate_provider("fixture-only"), FidelityValidator())
    assert row["passed"] is False
    assert row["provider_trace"][-1]["outcome"] == "accepted"
    assert len(calls) == 1


def test_preregistration_binds_budget_runner_and_namespace(tmp_path):
    manifest = build_manifest(_clear_cases() + _ambiguous_cases(), candidate5.candidate_provider("fixture-only"))
    registration = {"frozen_manifest": manifest, "artifact_namespace": candidate5.NAMESPACE}
    registration["preregistration_sha256"] = canonical_sha256(registration)
    path = tmp_path / "registration.json"
    candidate5.write_json(path, registration)
    assert candidate5.verify_registration(manifest, path) == registration
    for field, value in [("max_completion_tokens", 1024), ("max_attempts", 4), ("max_schema_corrections", 3), ("request_timeout_seconds", 30)]:
        altered = deepcopy(manifest)
        altered["provider"][field] = value
        with pytest.raises(ValueError, match="configuration/source"):
            candidate5.verify_registration(altered, path)
    for field, value in [("candidate_version", "A-CANDIDATE-4"), ("runner_sha256", "0" * 64)]:
        altered = deepcopy(manifest)
        altered[field] = value
        with pytest.raises(ValueError):
            candidate5.verify_registration(altered, path)
    registration["artifact_namespace"] = "checkpoint-a-candidate-4"
    registration["preregistration_sha256"] = canonical_sha256({k: v for k, v in registration.items() if k != "preregistration_sha256"})
    candidate5.write_json(path, registration)
    with pytest.raises(ValueError, match="namespace"):
        candidate5.verify_registration(manifest, path)


@pytest.mark.parametrize("kind,count,criterion", [
    ("terminal", 9, "case_pass_rate_min"),
    ("validated_wrong", 5, "selective_semantic_reliability_min"),
    ("nonvalidated", 37, "autonomous_coverage_min"),
    ("ambiguous_wrong", 7, "ambiguous_clarification_accuracy_min"),
])
def test_optimistic_math_stops_at_frozen_boundary(kind, count, criterion):
    frozen = _clear_cases() + _ambiguous_cases()
    selected = _ambiguous_cases() if kind == "ambiguous_wrong" else frozen
    status = "VALIDATED" if kind == "validated_wrong" else "REJECTED"
    rows = {g.case_id: {"passed": kind == "nonvalidated", "detail": {"validator_status": status}} for g in selected[:count]}
    before = dict(list(rows.items())[:-1])
    assert criterion not in candidate5.impossible_thresholds(frozen, before)
    assert criterion in candidate5.impossible_thresholds(frozen, rows)


def test_serial_run_stops_before_tenth_case_after_nine_terminal_failures(monkeypatch, tmp_path):
    for key, value in {"GITHUB_RUN_ATTEMPT": "1", "GITHUB_RUN_ID": "1", "GITHUB_SHA": "c" * 40, "GITHUB_REPOSITORY": "fixture/repo", "ECOCOMMIT_LLM_API_KEY": "fixture-only"}.items():
        monkeypatch.setenv(key, value)
    frozen = _clear_cases() + _ambiguous_cases()
    manifest = build_manifest(frozen, candidate5.candidate_provider("fixture-only"))
    monkeypatch.setattr(candidate5, "verify_registration", lambda m: {"fixture": True})
    monkeypatch.setattr(candidate5, "verify_health", lambda r, m: None)
    calls = []
    def run(args, **kwargs):
        calls.append(args)
        if args[1].endswith("checkpoint_a_shard.py"):
            index = int(args[args.index("--start") + 1])
            assert index < 9
            gold = frozen[index]
            row = bind_row({"id": gold.case_id, "instruction": gold.instruction, "passed": False, "error_kind": "candidate_contract_error"}, gold, manifest)
            candidate5.write_json(Path(args[args.index("--output") + 1]), {"manifest": manifest, "cases": [row]})
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        assert args[1].endswith("checkpoint_a_aggregate.py")
        return SimpleNamespace(returncode=2, stdout="", stderr="")
    monkeypatch.setattr(candidate5.subprocess, "run", run)
    health = tmp_path / "health.json"
    health.write_text("{}")
    out = tmp_path / "fresh"
    monkeypatch.setattr(sys, "argv", ["candidate5", "--output-dir", str(out), "--health-receipt", str(health)])
    assert candidate5.main() == 2
    assert len(calls) == 10
    decision = json.loads((out / "decision.json").read_text())
    assert decision["status"] == "FAILED" and decision["terminal_case_count"] == 9
    assert decision["typed_a_receipt_present"] is False
    assert all("--resume" not in args for args in calls)


def test_candidate5_manual_workflow_and_receipt_compatibility():
    from ecocommit.checkpoint_a_evidence import CheckpointAEvidenceReceipt, FROZEN_A_DATASET_SHA256
    workflow = (candidate5.ROOT / ".github/workflows/checkpoint-a-live.yml").read_text()
    assert "workflow_dispatch:" in workflow and "push:" not in workflow
    assert "ECOCOMMIT_LLM_MAX_COMPLETION_TOKENS: '2048'" in workflow
    assert "ECOCOMMIT_LLM_CASE_MAX_ATTEMPTS: '3'" in workflow
    assert "ECOCOMMIT_LLM_MAX_SCHEMA_CORRECTIONS: '2'" in workflow
    assert "timeout-minutes: 360" in workflow and candidate5.CASE_WALL_TIMEOUT_SECONDS == 240
    fixture = CheckpointAEvidenceReceipt.test_fixture("fixture-only").model_dump()
    fixture.update(verification_mode="FROZEN_AGGREGATE", candidate_version="A-CANDIDATE-5", dataset_sha256=FROZEN_A_DATASET_SHA256)
    assert CheckpointAEvidenceReceipt.model_validate(fixture).candidate_version == "A-CANDIDATE-5"
