from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from ecocommit.checkpoint_c_models import (
    ArtifactMaturity,
    BenchmarkCase,
    BenchmarkPlan,
    BenchmarkSplit,
    BenchmarkSuite,
    ConservativeAbstainRegistration,
    CostProvenance,
    DynamicRiskEvidenceRegistration,
    EconomicCostProfile,
    EvidenceObservation,
    EvidenceStatus,
    ReferenceOutcome,
    RiskSignal,
    ScenarioProvenance,
    ScenarioSourceKind,
    StaticRulesRegistration,
)


def make_case(
    case_id: str,
    *,
    should_execute: bool = True,
    requested_amount_minor: int = 5_000,
    policy_limit_minor: int = 10_000,
    irreversible_exposure_minor: int = 2_000,
    base_risk_bps: int = 1_000,
    evidence_status: EvidenceStatus = EvidenceStatus.VERIFIED,
    evidence_latency_ms: int = 5,
    risk_signals: list[RiskSignal] | None = None,
) -> BenchmarkCase:
    return BenchmarkCase(
        case_id=case_id,
        scenario_family="unit-test-procurement",
        description=f"Synthetic test scenario {case_id}",
        split=BenchmarkSplit.DEVELOPMENT,
        requested_amount_minor=requested_amount_minor,
        irreversible_exposure_minor=irreversible_exposure_minor,
        policy_limit_minor=policy_limit_minor,
        base_risk_bps=base_risk_bps,
        evidence=[EvidenceObservation(
            evidence_id="merchant-status",
            evidence_class="merchant_registry",
            status=evidence_status,
            required=True,
            version="fixture-v1",
            simulated_verification_latency_ms=evidence_latency_ms,
        )],
        risk_signals=risk_signals or [],
        reference_outcome=ReferenceOutcome(
            authorized_safe_to_execute=should_execute,
            legitimate_completion_expected=should_execute,
        ),
        costs=EconomicCostProfile(
            provenance=CostProvenance.SIMULATED,
            unsafe_execution_loss_minor=9_000,
            missed_legitimate_completion_loss_minor=700,
            abstention_review_loss_minor=50,
            basis="Synthetic unit-test values; not observed economic outcomes.",
        ),
        provenance=ScenarioProvenance(
            source_kind=ScenarioSourceKind.SYNTHETIC_SIMULATION,
            source_reference="tests/test_checkpoint_c_models.py",
            scenario_is_simulated=True,
        ),
        tags=["synthetic", "unit-test"],
    )


def make_suite(cases: list[BenchmarkCase] | None = None) -> BenchmarkSuite:
    return BenchmarkSuite(
        suite_id="checkpoint-c-unit-suite",
        suite_version="1",
        description="Synthetic development-only Checkpoint C suite.",
        cases=cases or [make_case("c-001"), make_case("c-002", should_execute=False)],
        contains_live_checkpoint_a_outputs=False,
    )


def make_plan(suite: BenchmarkSuite, *, seed: int = 42) -> BenchmarkPlan:
    return BenchmarkPlan(
        plan_id="checkpoint-c-unit-plan",
        plan_revision="1",
        description="Preliminary deterministic baseline unit-test plan.",
        registered_at_utc=datetime(2026, 1, 1, tzinfo=UTC),
        suite_id=suite.suite_id,
        suite_version=suite.suite_version,
        suite_sha256=suite.canonical_hash(),
        seed=seed,
        baselines=[
            StaticRulesRegistration(
                baseline_id="static-v1",
                amount_ceiling_minor=8_000,
                blocked_signal_codes=["DENYLIST_MATCH"],
            ),
            DynamicRiskEvidenceRegistration(baseline_id="dynamic-v1"),
            ConservativeAbstainRegistration(baseline_id="abstain-v1"),
        ],
    )


def test_suite_hash_is_stable_across_json_round_trip():
    suite = make_suite()
    restored = BenchmarkSuite.model_validate_json(suite.model_dump_json())
    assert restored.canonical_hash() == suite.canonical_hash()
    assert restored.contains_live_checkpoint_a_outputs is False


def test_synthetic_scenario_cannot_hide_its_simulated_status():
    with pytest.raises(ValidationError, match="explicitly labelled simulated"):
        ScenarioProvenance(
            source_kind=ScenarioSourceKind.SYNTHETIC_SIMULATION,
            source_reference="synthetic-generator-v1",
            scenario_is_simulated=False,
        )


def test_case_rejects_exposure_beyond_transaction_amount():
    with pytest.raises(ValidationError, match="irreversible exposure"):
        make_case(
            "bad-exposure",
            requested_amount_minor=1_000,
            irreversible_exposure_minor=1_001,
        )


def test_reference_outcome_requires_binary_v1_ground_truth():
    with pytest.raises(ValidationError, match="requires legitimate completion"):
        ReferenceOutcome(
            authorized_safe_to_execute=False,
            legitimate_completion_expected=True,
        )


def test_plan_records_all_three_baselines_and_is_never_final():
    plan = make_plan(make_suite())
    assert plan.maturity == ArtifactMaturity.PRELIMINARY_NOT_FINAL
    assert plan.eligible_for_final_claims is False
    assert plan.checkpoint_a_final_pass_required is True
    assert [baseline.baseline_type for baseline in plan.baselines] == [
        "STATIC_RULES",
        "DYNAMIC_RISK_EVIDENCE",
        "CONSERVATIVE_ABSTAIN",
    ]


def test_plan_rejects_duplicate_baseline_ids():
    suite = make_suite()
    with pytest.raises(ValidationError, match="baseline ids must be unique"):
        BenchmarkPlan(
            plan_id="duplicate-plan",
            plan_revision="1",
            description="Invalid duplicate baseline registration.",
            registered_at_utc=datetime(2026, 1, 1, tzinfo=UTC),
            suite_id=suite.suite_id,
            suite_version=suite.suite_version,
            suite_sha256=suite.canonical_hash(),
            seed=1,
            baselines=[
                StaticRulesRegistration(baseline_id="same", amount_ceiling_minor=10_000),
                ConservativeAbstainRegistration(baseline_id="same"),
            ],
        )
