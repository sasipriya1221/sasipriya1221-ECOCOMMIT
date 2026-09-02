from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import checkpoint_a_diagnostics
from checkpoint_a_diagnostics import diagnose
from checkpoint_a_live import _ambiguous_cases, _clear_cases, semantic_case_pass
from checkpoint_a_protocol import bind_row, build_manifest, canonical_sha256
from ecocommit.contracts import (
    EconomicClause,
    EconomicIntentContract,
    Provenance,
    SourceSpan,
)
from ecocommit.interpreter import OpenAICompatibleIntentProvider
from ecocommit.validator import FidelityValidator


def _provider() -> OpenAICompatibleIntentProvider:
    return OpenAICompatibleIntentProvider(
        "https://api.groq.com/openai/v1",
        "not-used",
        "qwen/qwen3.6-27b",
        reasoning_effort="none",
        max_completion_tokens=1024,
        use_json_schema=False,
        max_attempts=2,
        max_retry_delay=15,
    )


def _passing_row(gold, manifest):
    clauses = []
    for index, requirement in enumerate(gold.required):
        start = gold.instruction.index(requirement.source_text)
        clauses.append(
            EconomicClause(
                clause_id=f"c{index}",
                clause_type=requirement.clause_type,
                normalized_value=requirement.source_text,
                source_span=SourceSpan(
                    text=requirement.source_text,
                    start=start,
                    end=start + len(requirement.source_text),
                ),
                provenance=Provenance.EXPLICIT_USER,
                materiality=1.0,
                confidence=1.0,
                negated=bool(requirement.negated),
            )
        )
    contract = EconomicIntentContract(instruction=gold.instruction, clauses=clauses)
    passed, detail = semantic_case_pass(contract, gold, FidelityValidator())
    assert passed
    return bind_row(
        {
            "id": gold.case_id,
            "instruction": gold.instruction,
            "passed": passed,
            "detail": detail,
            "contract": contract.model_dump(mode="json"),
            "provider_trace": [
                {"attempt": 1, "candidate_sha256": "a" * 64, "outcome": "accepted"}
            ],
        },
        gold,
        manifest,
    )


def _artifact(tmp_path: Path, *, run_id: str | None = None) -> tuple[Path, dict, list]:
    frozen = _clear_cases() + _ambiguous_cases()
    manifest = build_manifest(frozen, _provider())
    if run_id is not None:
        manifest["workflow"]["run_id"] = run_id
        unsigned = {
            key: value for key, value in manifest.items() if key != "manifest_sha256"
        }
        manifest["manifest_sha256"] = canonical_sha256(unsigned)
    path = tmp_path / "attempt.json"
    path.write_text(
        json.dumps(
            {
                "evidence_schema_version": "A.EVIDENCE.2",
                "manifest": manifest,
                "cases": [_passing_row(frozen[0], manifest)],
            }
        ),
        encoding="utf-8",
    )
    return path, manifest, frozen


def test_diagnostics_recompute_rows_and_keep_missing_cases_unresolved(tmp_path):
    path, manifest, _ = _artifact(tmp_path, run_id="33590028177")

    report = diagnose(
        [path],
        expected_manifest_sha256=manifest["manifest_sha256"],
        expected_source_revision=manifest["source_revision"],
        expected_run_id="33590028177",
        run_status="completed",
        provider_condition="throttled",
    )

    assert report["status"] == "BLOCKED_NOT_PASSED"
    assert report["passed_rows"] == 1
    assert report["unresolved_case_count"] == 79
    assert (
        report["unresolved_cases_classification"]
        == "UNRESOLVED_NOT_ASSUMED_PROVIDER_DEFERRED"
    )
    assert report["retry_readiness"]["decision"] == (
        "NOT_READY_PROVIDER_BLOCKER_PERSISTS"
    )
    assert report["retry_readiness"]["retry_action_performed"] is False


def test_diagnostics_reject_conflicts_and_out_of_band_pin_mismatch(tmp_path):
    path, manifest, frozen = _artifact(tmp_path)
    conflict = tmp_path / "conflict.json"
    terminal = bind_row(
        {
            "id": frozen[0].case_id,
            "instruction": frozen[0].instruction,
            "passed": False,
            "error_kind": "candidate_contract_error",
            "error_code": "SCHEMA_INVALID_AFTER_CORRECTION",
            "error": "candidate contract invalid after bounded correction",
            "provider_trace": [],
        },
        frozen[0],
        manifest,
    )
    conflict.write_text(
        json.dumps({"manifest": manifest, "cases": [terminal]}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="conflicting terminal rows"):
        diagnose([path, conflict])
    with pytest.raises(ValueError, match="out-of-band digest pin"):
        diagnose([path], expected_manifest_sha256="0" * 64)


def test_diagnostics_reject_tampered_semantics_even_with_rehashed_row(tmp_path):
    path, manifest, _ = _artifact(tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    row = payload["cases"][0]
    row["detail"]["validator_status"] = "REJECTED"
    unsigned = {key: value for key, value in row.items() if key != "row_sha256"}
    row["row_sha256"] = canonical_sha256(unsigned)
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="semantic recomputation mismatch"):
        diagnose([path], expected_manifest_sha256=manifest["manifest_sha256"])


def test_retry_readiness_needs_completed_run_and_pinned_healthy_observation(tmp_path):
    path, manifest, _ = _artifact(tmp_path, run_id="123")
    observed = datetime(2026, 9, 2, 6, 0, tzinfo=UTC)

    active = diagnose(
        [path],
        run_status="in_progress",
        provider_condition="healthy",
        provider_health_observed_at=observed,
        provider_health_reference_sha256="a" * 64,
    )
    assert active["retry_readiness"]["decision"] == (
        "NOT_READY_CONFLICTING_ATTEMPT_ACTIVE"
    )

    cancelled = diagnose(
        [path],
        expected_manifest_sha256=manifest["manifest_sha256"],
        expected_source_revision=manifest["source_revision"],
        expected_run_id="123",
        run_status="cancelled",
        provider_condition="healthy",
        assessed_at_utc=observed + timedelta(minutes=5),
        provider_health_observed_at=observed,
        provider_health_reference_sha256="a" * 64,
    )
    assert cancelled["retry_readiness"]["decision"] == (
        "NOT_READY_RUN_NOT_COMPLETED"
    )

    unpinned = diagnose(
        [path],
        run_status="completed",
        provider_condition="healthy",
        assessed_at_utc=observed + timedelta(minutes=5),
        provider_health_observed_at=observed,
        provider_health_reference_sha256="a" * 64,
    )
    assert unpinned["retry_readiness"]["decision"] == (
        "NOT_READY_EVIDENCE_IDENTITY_UNPINNED"
    )

    ready = diagnose(
        [path],
        expected_manifest_sha256=manifest["manifest_sha256"],
        expected_source_revision=manifest["source_revision"],
        expected_run_id="123",
        run_status="completed",
        provider_condition="healthy",
        assessed_at_utc=observed + timedelta(minutes=5),
        provider_health_observed_at=observed,
        provider_health_reference_sha256="a" * 64,
    )
    assert ready["retry_readiness"]["decision"] == (
        "READY_TO_REQUEST_AUTHORIZED_RETRY"
    )
    assert ready["retry_readiness"]["eligible"] is True
    assert ready["retry_readiness"]["authorization_required"] is True
    assert ready["retry_readiness"]["retry_action_performed"] is False

    stale = diagnose(
        [path],
        expected_manifest_sha256=manifest["manifest_sha256"],
        expected_source_revision=manifest["source_revision"],
        expected_run_id="123",
        run_status="completed",
        provider_condition="healthy",
        assessed_at_utc=observed + timedelta(hours=1),
        provider_health_observed_at=observed,
        provider_health_reference_sha256="a" * 64,
    )
    assert stale["retry_readiness"]["decision"] == (
        "NOT_READY_PROVIDER_HEALTH_STALE"
    )


def test_computed_all_pass_cannot_promote_without_completed_pinned_identity(
    tmp_path,
    monkeypatch,
):
    path, manifest, _ = _artifact(tmp_path, run_id="456")
    all_pass_metrics = {
        "passed_cases": 80,
        "case_pass_rate": 1.0,
        "autonomous_coverage": 1.0,
        "selective_semantic_reliability": 1.0,
        "ambiguous_clarification_accuracy": 1.0,
    }
    monkeypatch.setattr(
        checkpoint_a_diagnostics,
        "compute_gate",
        lambda frozen, rows: (
            list(rows.values()),
            [],
            all_pass_metrics,
            True,
            True,
        ),
    )

    unpinned = diagnose([path], run_status="completed")
    assert unpinned["computed_gate_passed"] is True
    assert unpinned["gate_passed"] is False
    assert unpinned["complete_receipt_possible"] is False
    assert unpinned["status"] == "BLOCKED_NOT_PASSED"
    assert unpinned["retry_readiness"]["decision"] == (
        "NOT_READY_EVIDENCE_IDENTITY_UNPINNED"
    )

    pinned = diagnose(
        [path],
        expected_manifest_sha256=manifest["manifest_sha256"],
        expected_source_revision=manifest["source_revision"],
        expected_run_id="456",
        run_status="completed",
    )
    assert pinned["computed_gate_passed"] is True
    assert pinned["gate_passed"] is True
    assert pinned["complete_receipt_possible"] is True
    assert pinned["status"] == "PASSED"
    assert pinned["retry_readiness"]["decision"] == (
        "NO_RETRY_NEEDED_GATE_PASSED"
    )
