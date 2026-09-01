from __future__ import annotations

import json
import platform as platform_module
import random
from datetime import UTC, datetime
from pathlib import Path

from .checkpoint_c_baselines import build_baseline
from .checkpoint_c_metrics import aggregate_metrics, score_case
from .checkpoint_c_models import (
    ArtifactMaturity,
    BaselinePreliminarySummary,
    BenchmarkArtifact,
    BenchmarkPlan,
    BenchmarkRunProvenance,
    BenchmarkSplit,
    BenchmarkSuite,
    LatencyProvenance,
)


def run_benchmark(
    plan: BenchmarkPlan,
    suite: BenchmarkSuite,
    *,
    generated_at_utc: datetime | None = None,
    code_revision: str | None = None,
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
    if generated_at.utcoffset() is None:
        raise ValueError("generated_at_utc must be timezone-aware")

    ordered_cases = list(suite.cases)
    random.Random(plan.seed).shuffle(ordered_cases)
    case_order = [case.case_id for case in ordered_cases]

    all_results = []
    summaries = []
    for registration in plan.baselines:
        baseline = build_baseline(registration)
        results = [score_case(case, baseline.evaluate(case)) for case in ordered_cases]
        all_results.extend(results)
        summaries.append(BaselinePreliminarySummary(
            baseline_id=baseline.baseline_id,
            preliminary_metrics=aggregate_metrics(ordered_cases, results),
        ))

    simulated_only = all(
        result.latency_provenance == LatencyProvenance.SIMULATED for result in all_results
    )
    provenance = BenchmarkRunProvenance(
        generated_at_utc=generated_at,
        plan_sha256=plan.canonical_hash(),
        suite_sha256=suite_hash,
        seed=plan.seed,
        deterministic_case_order=case_order,
        code_revision=code_revision,
        python_version=platform_module.python_version(),
        platform=platform_module.platform(),
        live_checkpoint_a_outputs_used=False,
        latency_data_is_simulated=simulated_only,
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
        },
        indent=2,
    )
