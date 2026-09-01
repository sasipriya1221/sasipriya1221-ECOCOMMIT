from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from ecocommit.checkpoint_c_models import BenchmarkArtifact, BenchmarkSplit, GateStatus
from ecocommit.checkpoint_c_runner import (
    artifact_receipt,
    run_benchmark,
    write_artifact,
)
from test_checkpoint_c_models import make_case, make_plan, make_suite


def test_seeded_runner_is_reproducible_and_never_claims_checkpoint_pass():
    suite = make_suite([
        make_case("c-001"),
        make_case("c-002", should_execute=False),
        make_case("c-003"),
        make_case("c-004", should_execute=False),
    ])
    plan = make_plan(suite, seed=734)
    generated_at = datetime(2026, 1, 2, tzinfo=UTC)

    first = run_benchmark(plan, suite, generated_at_utc=generated_at, code_revision="deadbeef")
    second = run_benchmark(plan, suite, generated_at_utc=generated_at, code_revision="deadbeef")

    assert first == second
    assert first.canonical_hash() == second.canonical_hash()
    assert first.checkpoint_c_gate_status == GateStatus.NOT_EVALUATED
    assert first.prerequisites_satisfied is False
    assert first.final_comparison_numbers_published is False
    assert first.comparison_status.value == "NOT_COMPUTED"
    assert first.provenance.live_checkpoint_a_outputs_used is False
    assert first.provenance.latency_data_is_simulated is True
    assert len(first.case_results) == len(suite.cases) * len(plan.baselines)


def test_runner_refuses_suite_changed_after_plan_registration():
    original = make_suite([make_case("original")])
    plan = make_plan(original)
    changed = make_suite([make_case("changed")])

    with pytest.raises(ValueError, match="hash frozen"):
        run_benchmark(plan, changed)


def test_preliminary_runner_refuses_final_held_out_cases():
    final_case = make_case("final-held-out").model_copy(
        update={"split": BenchmarkSplit.FINAL_HELD_OUT}
    )
    suite = make_suite([final_case])

    with pytest.raises(ValueError, match="cannot consume FINAL_HELD_OUT"):
        run_benchmark(make_plan(suite), suite)


def test_artifact_serialization_retains_preliminary_labels_and_provenance(tmp_path):
    suite = make_suite()
    artifact = run_benchmark(
        make_plan(suite),
        suite,
        generated_at_utc=datetime(2026, 1, 2, tzinfo=UTC),
    )
    destination = write_artifact(artifact, tmp_path / "checkpoint-c.json")
    restored = BenchmarkArtifact.model_validate_json(destination.read_text(encoding="utf-8"))
    receipt = json.loads(artifact_receipt(restored, destination))

    assert restored.notice.startswith("PRELIMINARY DEVELOPMENT EVIDENCE ONLY")
    assert restored.provenance.plan_sha256 == artifact.plan.canonical_hash()
    assert receipt["maturity"] == "PRELIMINARY_NOT_FINAL"
    assert receipt["comparison_status"] == "NOT_COMPUTED"
    assert "preliminary_summaries" not in receipt
    assert "metrics" not in receipt


def test_artifact_schema_rejects_missing_baseline_case_result():
    suite = make_suite()
    artifact = run_benchmark(
        make_plan(suite),
        suite,
        generated_at_utc=datetime(2026, 1, 2, tzinfo=UTC),
    )
    payload = artifact.model_dump(mode="json")
    payload["case_results"] = payload["case_results"][:-1]

    with pytest.raises(ValidationError, match="each registered baseline/case pair"):
        BenchmarkArtifact.model_validate(payload)


def test_artifact_schema_rejects_tampered_provenance_hash():
    suite = make_suite()
    artifact = run_benchmark(
        make_plan(suite),
        suite,
        generated_at_utc=datetime(2026, 1, 2, tzinfo=UTC),
    )
    payload = artifact.model_dump(mode="json")
    payload["provenance"]["plan_sha256"] = "0" * 64

    with pytest.raises(ValidationError, match="provenance plan hash"):
        BenchmarkArtifact.model_validate(payload)
