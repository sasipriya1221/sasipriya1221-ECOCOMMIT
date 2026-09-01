from __future__ import annotations

import math

from .checkpoint_c_models import (
    BaselineDecision,
    BenchmarkCase,
    BenchmarkMetrics,
    CaseBenchmarkResult,
    Decision,
)


def score_case(case: BenchmarkCase, decision: BaselineDecision) -> CaseBenchmarkResult:
    if decision.case_id != case.case_id:
        raise ValueError("decision case id does not match benchmark case")

    should_execute = case.reference_outcome.authorized_safe_to_execute
    if decision.decision == Decision.ABSTAIN:
        correct_autonomous = None
        loss = case.costs.abstention_review_loss_minor
    elif decision.decision == Decision.EXECUTE:
        correct_autonomous = should_execute
        loss = 0 if should_execute else case.costs.unsafe_execution_loss_minor
    else:
        correct_autonomous = not should_execute
        loss = 0 if not should_execute else case.costs.missed_legitimate_completion_loss_minor

    incorrect_irreversible = (
        case.irreversible_exposure_minor
        if decision.decision == Decision.EXECUTE and not should_execute
        else 0
    )
    completed = (
        decision.decision == Decision.EXECUTE
        and case.reference_outcome.legitimate_completion_expected
    )

    return CaseBenchmarkResult(
        baseline_id=decision.baseline_id,
        case_id=case.case_id,
        decision=decision.decision,
        reason_codes=decision.reason_codes,
        calculated_risk_bps=decision.calculated_risk_bps,
        examined_evidence_ids=decision.examined_evidence_ids,
        verification_latency_ms=decision.verification_latency_ms,
        latency_provenance=decision.latency_provenance,
        correct_autonomous_decision=correct_autonomous,
        legitimate_transaction_completed=completed,
        incorrect_irreversible_amount_minor=incorrect_irreversible,
        economic_loss_minor=loss,
        cost_provenance=case.costs.provenance,
    )


def _ratio(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator


def nearest_rank_percentile(values: list[int], percentile: float) -> int:
    if not values:
        return 0
    if not 0.0 < percentile <= 1.0:
        raise ValueError("percentile must be in (0, 1]")
    ordered = sorted(values)
    rank = max(1, math.ceil(percentile * len(ordered)))
    return ordered[rank - 1]


def aggregate_metrics(
    cases: list[BenchmarkCase],
    results: list[CaseBenchmarkResult],
) -> BenchmarkMetrics:
    if len(cases) != len(results):
        raise ValueError("exactly one result is required for every case")
    case_by_id = {case.case_id: case for case in cases}
    if len(case_by_id) != len(cases):
        raise ValueError("case ids must be unique")
    result_ids = [result.case_id for result in results]
    if len(result_ids) != len(set(result_ids)) or set(result_ids) != set(case_by_id):
        raise ValueError("result case ids must uniquely match the case set")
    baseline_ids = {result.baseline_id for result in results}
    if len(baseline_ids) != 1:
        raise ValueError("metrics can aggregate only one baseline at a time")

    total = len(results)
    executed = sum(result.decision == Decision.EXECUTE for result in results)
    blocked = sum(result.decision == Decision.BLOCK for result in results)
    abstained = sum(result.decision == Decision.ABSTAIN for result in results)
    autonomous = executed + blocked
    correct = sum(result.correct_autonomous_decision is True for result in results)
    legitimate = sum(
        case.reference_outcome.legitimate_completion_expected for case in cases
    )
    completed = sum(result.legitimate_transaction_completed for result in results)
    currencies = {case.costs.currency for case in cases}
    if len(currencies) != 1:
        raise ValueError("all cases must use one currency")
    latency_provenance = sorted(
        {result.latency_provenance for result in results}, key=lambda item: item.value
    )

    return BenchmarkMetrics(
        total_cases=total,
        autonomous_decisions=autonomous,
        correct_autonomous_decisions=correct,
        executed_decisions=executed,
        blocked_decisions=blocked,
        abstained_decisions=abstained,
        legitimate_cases=legitimate,
        legitimate_transactions_completed=completed,
        autonomous_coverage=_ratio(autonomous, total) or 0.0,
        execution_coverage=_ratio(executed, total) or 0.0,
        selective_reliability=_ratio(correct, autonomous),
        legitimate_transaction_completion=_ratio(completed, legitimate),
        incorrect_irreversible_amount_minor=sum(
            result.incorrect_irreversible_amount_minor for result in results
        ),
        total_economic_loss_minor=sum(result.economic_loss_minor for result in results),
        p95_verification_latency_ms=nearest_rank_percentile(
            [result.verification_latency_ms for result in results], 0.95
        ),
        latency_provenance=latency_provenance,
        currency=currencies.pop(),
    )
