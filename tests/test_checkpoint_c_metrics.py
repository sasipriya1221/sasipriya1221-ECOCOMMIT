from __future__ import annotations

from ecocommit.checkpoint_c_metrics import (
    aggregate_metrics,
    nearest_rank_percentile,
    score_case,
)
from ecocommit.checkpoint_c_models import (
    BaselineDecision,
    Decision,
    LatencyProvenance,
)
from test_checkpoint_c_models import make_case


def _decision(case_id: str, decision: Decision, latency_ms: int) -> BaselineDecision:
    return BaselineDecision(
        baseline_id="candidate",
        case_id=case_id,
        decision=decision,
        reason_codes=["UNIT_TEST"],
        verification_latency_ms=latency_ms,
        latency_provenance=LatencyProvenance.SIMULATED,
    )


def test_total_economic_loss_reliability_coverage_and_latency_are_aggregated():
    safe_executed = make_case("safe-executed", should_execute=True)
    unsafe_executed = make_case("unsafe-executed", should_execute=False)
    safe_blocked = make_case("safe-blocked", should_execute=True)
    cases = [safe_executed, unsafe_executed, safe_blocked]
    results = [
        score_case(safe_executed, _decision("safe-executed", Decision.EXECUTE, 1)),
        score_case(unsafe_executed, _decision("unsafe-executed", Decision.EXECUTE, 10)),
        score_case(safe_blocked, _decision("safe-blocked", Decision.BLOCK, 5)),
    ]

    metrics = aggregate_metrics(cases, results)
    assert metrics.autonomous_coverage == 1.0
    assert metrics.execution_coverage == 2 / 3
    assert metrics.selective_reliability == 1 / 3
    assert metrics.legitimate_transaction_completion == 0.5
    assert metrics.incorrect_irreversible_amount_minor == 2_000
    assert metrics.total_economic_loss_minor == 9_700
    assert metrics.p95_verification_latency_ms == 10
    assert metrics.latency_provenance == [LatencyProvenance.SIMULATED]


def test_always_abstain_has_undefined_reliability_and_explicit_review_loss():
    case = make_case("abstain")
    result = score_case(case, _decision("abstain", Decision.ABSTAIN, 2))
    metrics = aggregate_metrics([case], [result])

    assert result.correct_autonomous_decision is None
    assert result.economic_loss_minor == 50
    assert metrics.autonomous_coverage == 0.0
    assert metrics.selective_reliability is None
    assert metrics.total_economic_loss_minor == 50


def test_nearest_rank_p95_is_deterministic():
    assert nearest_rank_percentile([], 0.95) == 0
    assert nearest_rank_percentile(list(range(1, 101)), 0.95) == 95
