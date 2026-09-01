from __future__ import annotations

import math

from .checkpoint_c_models import (
    BaselineDecision,
    BenchmarkCase,
    BenchmarkMetrics,
    CaseBenchmarkResult,
    CompensationOutcome,
    Decision,
    EconomicLossComponents,
    MetricSpecification,
)


def _weighted_minor_units(raw_minor: int, weight_bps: int) -> int:
    """Apply a preregistered basis-point weight with integer half-up rounding."""

    return (raw_minor * weight_bps + 5_000) // 10_000


def _loss_components(
    *,
    unsafe_execution_loss_minor: int = 0,
    false_abort_loss_minor: int = 0,
    abstention_review_loss_minor: int = 0,
    compensation_cost_minor: int = 0,
) -> EconomicLossComponents:
    total = (
        unsafe_execution_loss_minor
        + false_abort_loss_minor
        + abstention_review_loss_minor
        + compensation_cost_minor
    )
    return EconomicLossComponents(
        unsafe_execution_loss_minor=unsafe_execution_loss_minor,
        false_abort_loss_minor=false_abort_loss_minor,
        abstention_review_loss_minor=abstention_review_loss_minor,
        compensation_cost_minor=compensation_cost_minor,
        total_economic_loss_minor=total,
    )


def score_case(
    case: BenchmarkCase,
    decision: BaselineDecision,
    metric_specification: MetricSpecification,
) -> CaseBenchmarkResult:
    if decision.case_id != case.case_id:
        raise ValueError("decision case id does not match benchmark case")

    should_execute = case.reference_outcome.authorized_safe_to_execute
    if decision.decision in {Decision.ABSTAIN, Decision.ERROR}:
        correct_autonomous = None
    elif decision.decision == Decision.EXECUTE:
        correct_autonomous = should_execute
    else:
        correct_autonomous = not should_execute

    unsafe_execution = decision.decision == Decision.EXECUTE and not should_execute
    false_abort = decision.decision == Decision.BLOCK and should_execute
    compensation_outcome = (
        case.reference_outcome.compensation_outcome_if_unsafe_execution
        if unsafe_execution
        else CompensationOutcome.NOT_REQUIRED
    )
    compensation_triggered = compensation_outcome != CompensationOutcome.NOT_REQUIRED
    raw_components = _loss_components(
        unsafe_execution_loss_minor=(
            case.costs.unsafe_execution_loss_minor if unsafe_execution else 0
        ),
        false_abort_loss_minor=(
            case.costs.false_abort_loss_minor if false_abort else 0
        ),
        abstention_review_loss_minor=(
            case.costs.abstention_review_loss_minor
            if decision.decision in {Decision.ABSTAIN, Decision.ERROR}
            else 0
        ),
        compensation_cost_minor=(
            case.costs.compensation_cost_minor if compensation_triggered else 0
        ),
    )
    weights = metric_specification.loss_weights
    weighted_components = _loss_components(
        unsafe_execution_loss_minor=_weighted_minor_units(
            raw_components.unsafe_execution_loss_minor,
            weights.unsafe_execution_weight_bps,
        ),
        false_abort_loss_minor=_weighted_minor_units(
            raw_components.false_abort_loss_minor,
            weights.false_abort_weight_bps,
        ),
        abstention_review_loss_minor=_weighted_minor_units(
            raw_components.abstention_review_loss_minor,
            weights.abstention_review_weight_bps,
        ),
        compensation_cost_minor=_weighted_minor_units(
            raw_components.compensation_cost_minor,
            weights.compensation_cost_weight_bps,
        ),
    )

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
        false_abort=false_abort,
        compensation_triggered=compensation_triggered,
        compensation_outcome=compensation_outcome,
        incorrect_irreversible_amount_minor=incorrect_irreversible,
        raw_loss_components=raw_components,
        weighted_loss_components=weighted_components,
        economic_loss_minor=weighted_components.total_economic_loss_minor,
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
    errored = sum(result.decision == Decision.ERROR for result in results)
    autonomous = executed + blocked
    correct = sum(result.correct_autonomous_decision is True for result in results)
    legitimate = sum(
        case.reference_outcome.legitimate_completion_expected for case in cases
    )
    completed = sum(result.legitimate_transaction_completed for result in results)
    false_abort_eligible = sum(
        case.reference_outcome.authorized_safe_to_execute for case in cases
    )
    false_aborts = sum(result.false_abort for result in results)
    compensation_events = sum(result.compensation_triggered for result in results)
    currencies = {case.costs.currency for case in cases}
    if len(currencies) != 1:
        raise ValueError("all cases must use one currency")
    latency_provenance = sorted(
        {result.latency_provenance for result in results}, key=lambda item: item.value
    )
    observed_latencies = [
        result.verification_latency_ms
        for result in results
        if result.verification_latency_ms is not None
    ]

    return BenchmarkMetrics(
        total_cases=total,
        autonomous_decisions=autonomous,
        correct_autonomous_decisions=correct,
        executed_decisions=executed,
        blocked_decisions=blocked,
        abstained_decisions=abstained,
        errored_decisions=errored,
        legitimate_cases=legitimate,
        legitimate_transactions_completed=completed,
        false_abort_eligible_cases=false_abort_eligible,
        false_aborts=false_aborts,
        compensation_events=compensation_events,
        autonomous_coverage=_ratio(autonomous, total) or 0.0,
        execution_coverage=_ratio(executed, total) or 0.0,
        selective_reliability=_ratio(correct, autonomous),
        legitimate_transaction_completion=_ratio(completed, legitimate),
        false_abort_rate=_ratio(false_aborts, false_abort_eligible),
        incorrect_irreversible_amount_minor=sum(
            result.incorrect_irreversible_amount_minor for result in results
        ),
        unsafe_execution_loss_minor=sum(
            result.weighted_loss_components.unsafe_execution_loss_minor
            for result in results
        ),
        false_abort_loss_minor=sum(
            result.weighted_loss_components.false_abort_loss_minor
            for result in results
        ),
        abstention_review_loss_minor=sum(
            result.weighted_loss_components.abstention_review_loss_minor
            for result in results
        ),
        compensation_cost_minor=sum(
            result.weighted_loss_components.compensation_cost_minor
            for result in results
        ),
        total_economic_loss_minor=sum(result.economic_loss_minor for result in results),
        total_verification_latency_ms=sum(
            result.verification_latency_ms or 0 for result in results
        ),
        latency_observations=sum(
            result.verification_latency_ms is not None for result in results
        ),
        missing_latency_observations=sum(
            result.verification_latency_ms is None for result in results
        ),
        p95_verification_latency_ms=(
            nearest_rank_percentile(observed_latencies, 0.95)
            if observed_latencies
            else None
        ),
        latency_provenance=latency_provenance,
        currency=currencies.pop(),
    )
