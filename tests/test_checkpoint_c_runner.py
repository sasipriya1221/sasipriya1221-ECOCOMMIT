from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from ecocommit.checkpoint_c_baselines import DynamicRiskEvidenceBaseline
from ecocommit.checkpoint_c_models import (
    BenchmarkArtifact,
    BenchmarkSplit,
    GateStatus,
    combine_input_provenance_flags,
)
from ecocommit.checkpoint_c_runner import (
    artifact_receipt,
    load_plan,
    load_suite,
    run_benchmark,
    write_artifact,
)
from test_checkpoint_c_models import make_case, make_plan, make_suite, response_set_digest


def _run(plan, suite, **overrides):
    arguments = {
        "generated_at_utc": datetime(2026, 1, 2, tzinfo=UTC),
        "code_revision": "deadbeef",
        "working_tree_dirty": False,
    }
    arguments.update(overrides)
    return run_benchmark(plan, suite, **arguments)


def test_seeded_runner_is_reproducible_and_never_claims_checkpoint_pass():
    suite = make_suite([
        make_case("c-001"),
        make_case("c-002", should_execute=False),
        make_case("c-003"),
        make_case("c-004", should_execute=False),
    ])
    plan = make_plan(suite, seed=734)
    generated_at = datetime(2026, 1, 2, tzinfo=UTC)

    first = _run(plan, suite, generated_at_utc=generated_at)
    second = _run(plan, suite, generated_at_utc=generated_at)

    assert first == second
    assert first.canonical_hash() == second.canonical_hash()
    assert first.checkpoint_c_gate_status == GateStatus.NOT_EVALUATED
    assert first.prerequisites_satisfied is False
    assert first.final_comparison_numbers_published is False
    assert first.comparison_status.value == "NOT_COMPUTED"
    assert first.provenance.live_checkpoint_a_outputs_used is False
    assert first.provenance.all_latency_data_is_simulated is True
    assert first.provenance.contains_simulated_latency is True
    assert first.provenance.synthetic_fixture_inputs_used is True
    assert first.provenance.simulated_cost_inputs_used is True
    assert first.provenance.working_tree_dirty is False
    assert first.provenance.run_complete_without_errors is True
    assert first.provenance.dependency_versions["pydantic"]
    assert first.provenance.dependency_versions["pydantic-core"]
    assert (
        first.provenance.dependency_manifest_scope
        == "ALL_INSTALLED_PYTHON_DISTRIBUTIONS"
    )
    assert len(first.case_results) == len(suite.cases) * len(plan.baselines)


def test_runner_refuses_suite_changed_after_plan_registration():
    original = make_suite([make_case("original")])
    plan = make_plan(original)
    changed = make_suite([make_case("changed")])

    with pytest.raises(ValueError, match="hash frozen"):
        _run(plan, changed)


@pytest.mark.parametrize("kind", ["plan", "suite"])
def test_benchmark_input_loader_rejects_duplicate_json_keys(tmp_path, kind):
    suite = make_suite()
    value = make_plan(suite) if kind == "plan" else suite
    payload = value.model_dump(mode="json")
    encoded = json.dumps(payload)
    first_key = next(iter(payload))
    duplicate = "{" + json.dumps(first_key) + ":" + json.dumps(payload[first_key]) + "," + encoded[1:]
    path = tmp_path / f"{kind}.json"
    path.write_text(duplicate, encoding="utf-8")

    loader = load_plan if kind == "plan" else load_suite
    with pytest.raises(ValueError, match="duplicate JSON keys"):
        loader(path)


def test_runner_and_artifact_reject_run_time_before_plan_or_suite_freeze():
    suite = make_suite()
    plan = make_plan(suite)
    too_early = datetime(2025, 12, 31, tzinfo=UTC)

    with pytest.raises(ValueError, match="cannot predate its plan"):
        _run(plan, suite, generated_at_utc=too_early)

    artifact = _run(plan, suite)
    payload = artifact.model_dump(mode="json")
    payload["provenance"]["generated_at_utc"] = too_early.isoformat()
    with pytest.raises(ValidationError, match="cannot predate its plan"):
        BenchmarkArtifact.model_validate(payload)


def test_preliminary_runner_refuses_final_held_out_cases():
    final_case = make_case("final-held-out").model_copy(
        update={"split": BenchmarkSplit.FINAL_HELD_OUT}
    )
    suite = make_suite([final_case])

    with pytest.raises(ValueError, match="cannot consume FINAL_HELD_OUT"):
        _run(make_plan(suite), suite)


def test_artifact_serialization_retains_preliminary_labels_and_provenance(tmp_path):
    suite = make_suite()
    artifact = _run(make_plan(suite), suite)
    destination = write_artifact(artifact, tmp_path / "checkpoint-c.json")
    restored = BenchmarkArtifact.model_validate_json(destination.read_text(encoding="utf-8"))
    receipt = json.loads(artifact_receipt(restored, destination))

    assert restored.notice.startswith("PRELIMINARY DEVELOPMENT EVIDENCE ONLY")
    assert restored.provenance.plan_sha256 == artifact.plan.canonical_hash()
    assert receipt["maturity"] == "PRELIMINARY_NOT_FINAL"
    assert receipt["comparison_status"] == "NOT_COMPUTED"
    assert receipt["synthetic_fixture_inputs_used"] is True
    assert receipt["simulated_cost_inputs_used"] is True
    assert receipt["run_complete_without_errors"] is True
    assert "preliminary_summaries" not in receipt
    assert "metrics" not in receipt


def test_artifact_schema_rejects_missing_baseline_case_result():
    suite = make_suite()
    artifact = _run(make_plan(suite), suite)
    payload = artifact.model_dump(mode="json")
    payload["case_results"] = payload["case_results"][:-1]

    with pytest.raises(ValidationError, match="each registered baseline/case pair"):
        BenchmarkArtifact.model_validate(payload)


def test_runner_rejects_agent_replay_that_does_not_cover_the_frozen_suite():
    suite = make_suite()
    plan = make_plan(suite)
    registration = plan.baselines[0]
    incomplete_decisions = registration.decisions[:-1]
    payload = registration.model_dump(mode="json")
    payload.update({
        "decisions": [decision.model_dump(mode="json") for decision in incomplete_decisions],
        "response_set_sha256": response_set_digest(incomplete_decisions),
    })
    incomplete_registration = type(registration).model_validate(payload)
    plan = plan.model_copy(update={
        "baselines": [incomplete_registration, *plan.baselines[1:]],
    })

    with pytest.raises(ValidationError, match="must contain every suite case"):
        _run(plan, suite)


def test_artifact_schema_rejects_tampered_provenance_hash():
    suite = make_suite()
    artifact = _run(make_plan(suite), suite)
    payload = artifact.model_dump(mode="json")
    payload["provenance"]["plan_sha256"] = "0" * 64

    with pytest.raises(ValidationError, match="provenance plan hash"):
        BenchmarkArtifact.model_validate(payload)


def test_artifact_schema_rejects_semantically_tampered_result_and_summary():
    suite = make_suite()
    artifact = _run(make_plan(suite), suite)

    result_payload = artifact.model_dump(mode="json")
    result_payload["case_results"][0]["reason_codes"] = ["TAMPERED"]
    with pytest.raises(ValidationError, match="does not match the frozen baseline"):
        BenchmarkArtifact.model_validate(result_payload)

    summary_payload = artifact.model_dump(mode="json")
    summary_payload["preliminary_summaries"][0]["preliminary_metrics"][
        "autonomous_coverage"
    ] = 0.123
    with pytest.raises(ValidationError, match="summary does not match"):
        BenchmarkArtifact.model_validate(summary_payload)


def test_runner_retains_errors_and_labels_mixed_latency(monkeypatch):
    def raise_error(self, case):
        raise RuntimeError(f"synthetic failure for {case.case_id}")

    monkeypatch.setattr(DynamicRiskEvidenceBaseline, "evaluate", raise_error)
    suite = make_suite()
    artifact = _run(make_plan(suite), suite)

    assert artifact.provenance.errored_case_count == len(suite.cases)
    assert artifact.provenance.run_complete_without_errors is False
    assert artifact.provenance.all_latency_data_is_simulated is False
    assert artifact.provenance.contains_simulated_latency is True
    assert {item.value for item in artifact.provenance.latency_provenance} == {
        "NOT_AVAILABLE",
        "SIMULATED",
    }


def test_simulated_cost_is_always_included_in_synthetic_input_summary():
    fixture_inputs_used, simulated_cost_inputs_used = combine_input_provenance_flags(
        explicit_fixture_inputs_used=False,
        simulated_cost_inputs_used=True,
    )
    assert fixture_inputs_used is True
    assert simulated_cost_inputs_used is True
