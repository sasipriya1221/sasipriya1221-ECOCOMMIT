from __future__ import annotations

import json
import platform as platform_module
import random
from datetime import UTC, datetime, timedelta
from importlib.metadata import distributions
from pathlib import Path

from .checkpoint_c_baselines import build_baseline, evaluate_with_error_retention
from .checkpoint_c_metrics import aggregate_metrics, score_case
from .checkpoint_c_models import (
    ArtifactMaturity,
    BaselinePreliminarySummary,
    BenchmarkArtifact,
    BenchmarkPlan,
    BenchmarkRunProvenance,
    BenchmarkSplit,
    BenchmarkSuite,
    CostProvenance,
    Decision,
    LatencyProvenance,
    NaiveAgentReplayRegistration,
    PromptGuardrailReplayRegistration,
    combine_input_provenance_flags,
)


def _dependency_versions() -> dict[str, str]:
    """Return every installed Python distribution as a stable name/version map."""

    discovered: dict[str, set[str]] = {}
    for distribution in distributions():
        raw_name = distribution.metadata.get("Name")
        if not raw_name:
            continue
        normalized_name = raw_name.strip().lower().replace("_", "-")
        discovered.setdefault(normalized_name, set()).add(distribution.version)
    return {
        name: ",".join(sorted(versions))
        for name, versions in sorted(discovered.items())
    }


def run_benchmark(
    plan: BenchmarkPlan,
    suite: BenchmarkSuite,
    *,
    generated_at_utc: datetime | None = None,
    code_revision: str,
    working_tree_dirty: bool,
) -> BenchmarkArtifact:
    """Run only registered deterministic baselines; never evaluate Checkpoint A output."""

    suite_hash = suite.canonical_hash()
    if plan.suite_id != suite.suite_id or plan.suite_version != suite.suite_version:
        raise ValueError("benchmark plan targets a different suite id or version")
    if plan.suite_sha256 != suite_hash:
        raise ValueError("suite content does not match the hash frozen in the benchmark plan")
    if suite.contains_live_checkpoint_a_outputs:
        raise ValueError("Checkpoint C preliminary runner cannot consume live Checkpoint A outputs")
    if any(case.split == BenchmarkSplit.FINAL_HELD_OUT for case in suite.cases):
        raise ValueError(
            "Checkpoint C preliminary runner cannot consume FINAL_HELD_OUT cases"
        )

    generated_at = generated_at_utc or datetime.now(UTC)
    if generated_at.utcoffset() != timedelta(0):
        raise ValueError("generated_at_utc must be expressed in UTC")
    if plan.registered_at_utc < suite.definitions_frozen_at_utc:
        raise ValueError("benchmark plan cannot predate the frozen suite definitions")
    if (
        generated_at < plan.registered_at_utc
        or generated_at < suite.definitions_frozen_at_utc
    ):
        raise ValueError("benchmark run cannot predate its plan or frozen suite definitions")

    ordered_cases = list(suite.cases)
    random.Random(plan.seed).shuffle(ordered_cases)
    case_order = [case.case_id for case in ordered_cases]

    all_results = []
    summaries = []
    for registration in plan.baselines:
        baseline = build_baseline(registration)
        results = [
            score_case(
                case,
                evaluate_with_error_retention(baseline, case),
                plan.metrics,
            )
            for case in ordered_cases
        ]
        all_results.extend(results)
        summaries.append(BaselinePreliminarySummary(
            baseline_id=baseline.baseline_id,
            preliminary_metrics=aggregate_metrics(ordered_cases, results),
        ))

    latency_provenance = sorted(
        {result.latency_provenance for result in all_results},
        key=lambda item: item.value,
    )
    simulated_only = all(
        result.latency_provenance == LatencyProvenance.SIMULATED for result in all_results
    )
    contains_simulated = any(
        result.latency_provenance == LatencyProvenance.SIMULATED
        for result in all_results
    )
    replay_registrations = [
        registration
        for registration in plan.baselines
        if isinstance(
            registration,
            (NaiveAgentReplayRegistration, PromptGuardrailReplayRegistration),
        )
    ]
    replay_source_kinds = sorted(
        {registration.replay_source_kind for registration in replay_registrations},
        key=lambda item: item.value,
    )
    simulated_cost_inputs_used = any(
        case.costs.provenance == CostProvenance.SIMULATED for case in suite.cases
    )
    explicit_fixture_inputs_used = (
        any(registration.outputs_are_synthetic_fixture for registration in replay_registrations)
        or any(case.provenance.scenario_is_simulated for case in suite.cases)
        or any(
            observation.observation_is_fixture
            for case in suite.cases
            for observation in case.evidence
        )
    )
    fixture_inputs_used, simulated_cost_inputs_used = combine_input_provenance_flags(
        explicit_fixture_inputs_used=explicit_fixture_inputs_used,
        simulated_cost_inputs_used=simulated_cost_inputs_used,
    )
    errored_case_count = sum(
        result.decision == Decision.ERROR for result in all_results
    )
    provenance = BenchmarkRunProvenance(
        generated_at_utc=generated_at,
        plan_sha256=plan.canonical_hash(),
        suite_sha256=suite_hash,
        seed=plan.seed,
        deterministic_case_order=case_order,
        code_revision=code_revision,
        working_tree_dirty=working_tree_dirty,
        python_version=platform_module.python_version(),
        platform=platform_module.platform(),
        dependency_versions=_dependency_versions(),
        live_checkpoint_a_outputs_used=False,
        replay_source_kinds=replay_source_kinds,
        synthetic_fixture_inputs_used=fixture_inputs_used,
        simulated_cost_inputs_used=simulated_cost_inputs_used,
        latency_provenance=latency_provenance,
        all_latency_data_is_simulated=simulated_only,
        contains_simulated_latency=contains_simulated,
        errored_case_count=errored_case_count,
        run_complete_without_errors=errored_case_count == 0,
    )
    return BenchmarkArtifact(
        maturity=ArtifactMaturity.PRELIMINARY_NOT_FINAL,
        plan=plan,
        suite=suite,
        provenance=provenance,
        preliminary_summaries=summaries,
        case_results=all_results,
    )


def write_artifact(artifact: BenchmarkArtifact, path: str | Path) -> Path:
    """Serialize a validated artifact atomically with its warning fields intact."""

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.tmp")
    temporary.write_text(
        artifact.model_dump_json(indent=2, exclude_none=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(destination)
    return destination


def load_plan(path: str | Path) -> BenchmarkPlan:
    return BenchmarkPlan.model_validate_json(Path(path).read_text(encoding="utf-8"))


def load_suite(path: str | Path) -> BenchmarkSuite:
    return BenchmarkSuite.model_validate_json(Path(path).read_text(encoding="utf-8"))


def artifact_receipt(artifact: BenchmarkArtifact, path: str | Path) -> str:
    """Return a structural receipt without printing preliminary comparison numbers."""

    return json.dumps(
        {
            "artifact": str(Path(path)),
            "artifact_sha256": artifact.canonical_hash(),
            "maturity": artifact.maturity.value,
            "checkpoint_c_gate_status": artifact.checkpoint_c_gate_status.value,
            "comparison_status": artifact.comparison_status.value,
            "case_count": len(artifact.suite.cases),
            "baseline_count": len(artifact.preliminary_summaries),
            "final_comparison_numbers_published": artifact.final_comparison_numbers_published,
            "synthetic_fixture_inputs_used": artifact.provenance.synthetic_fixture_inputs_used,
            "simulated_cost_inputs_used": artifact.provenance.simulated_cost_inputs_used,
            "contains_simulated_latency": artifact.provenance.contains_simulated_latency,
            "errored_case_count": artifact.provenance.errored_case_count,
            "run_complete_without_errors": artifact.provenance.run_complete_without_errors,
        },
        indent=2,
    )
