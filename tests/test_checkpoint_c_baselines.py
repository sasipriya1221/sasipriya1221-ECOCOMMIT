from __future__ import annotations

from ecocommit.checkpoint_c_baselines import (
    ConservativeAbstainBaseline,
    DynamicRiskEvidenceBaseline,
    StaticRulesBaseline,
)
from ecocommit.checkpoint_c_models import (
    ConservativeAbstainRegistration,
    Decision,
    DynamicRiskEvidenceRegistration,
    EvidenceStatus,
    LatencyProvenance,
    RiskSignal,
    StaticRulesRegistration,
)
from test_checkpoint_c_models import make_case


def test_static_rules_use_only_pre_registered_ceiling_and_signal_codes():
    baseline = StaticRulesBaseline(StaticRulesRegistration(
        baseline_id="static",
        amount_ceiling_minor=8_000,
        blocked_signal_codes=["DENYLIST_MATCH"],
        simulated_decision_overhead_ms=3,
    ))
    missing_evidence = make_case("low", evidence_status=EvidenceStatus.MISSING)
    too_large = make_case("large", requested_amount_minor=9_000)
    denied = make_case(
        "denied",
        risk_signals=[RiskSignal(
            code="DENYLIST_MATCH",
            risk_weight_bps=10_000,
            source_reference="synthetic unit test",
        )],
    )

    allowed = baseline.evaluate(missing_evidence)
    assert allowed.decision == Decision.EXECUTE
    assert allowed.examined_evidence_ids == []
    assert allowed.verification_latency_ms == 3
    assert baseline.evaluate(too_large).decision == Decision.BLOCK
    assert baseline.evaluate(denied).decision == Decision.BLOCK


def test_dynamic_baseline_executes_only_with_policy_evidence_and_low_risk():
    baseline = DynamicRiskEvidenceBaseline(DynamicRiskEvidenceRegistration(
        baseline_id="dynamic",
        simulated_decision_overhead_ms=2,
    ))
    decision = baseline.evaluate(make_case(
        "allowed",
        base_risk_bps=1_000,
        evidence_status=EvidenceStatus.VERIFIED,
        evidence_latency_ms=7,
    ))

    assert decision.decision == Decision.EXECUTE
    assert decision.calculated_risk_bps == 900
    assert decision.examined_evidence_ids == ["merchant-status"]
    assert decision.verification_latency_ms == 9
    assert decision.latency_provenance == LatencyProvenance.SIMULATED


def test_dynamic_baseline_blocks_failed_evidence_and_policy_breach():
    baseline = DynamicRiskEvidenceBaseline(
        DynamicRiskEvidenceRegistration(baseline_id="dynamic")
    )
    failed = baseline.evaluate(make_case("failed", evidence_status=EvidenceStatus.FAILED))
    policy_breach = baseline.evaluate(make_case(
        "over-policy",
        requested_amount_minor=11_000,
        irreversible_exposure_minor=2_000,
        policy_limit_minor=10_000,
    ))

    assert failed.decision == Decision.BLOCK
    assert failed.reason_codes == ["REQUIRED_EVIDENCE_FAILED"]
    assert policy_breach.decision == Decision.BLOCK
    assert policy_breach.reason_codes == ["CASE_POLICY_LIMIT_EXCEEDED"]
    assert policy_breach.examined_evidence_ids == []


def test_dynamic_baseline_abstains_for_stale_evidence_or_review_band():
    baseline = DynamicRiskEvidenceBaseline(
        DynamicRiskEvidenceRegistration(baseline_id="dynamic")
    )
    stale = baseline.evaluate(make_case("stale", evidence_status=EvidenceStatus.STALE))
    review_band = baseline.evaluate(make_case(
        "review",
        base_risk_bps=4_000,
        evidence_status=EvidenceStatus.VERIFIED,
    ))

    assert stale.decision == Decision.ABSTAIN
    assert stale.reason_codes == ["REQUIRED_EVIDENCE_INCOMPLETE"]
    assert review_band.decision == Decision.ABSTAIN
    assert review_band.reason_codes == ["DYNAMIC_RISK_REVIEW_BAND"]


def test_dynamic_baseline_blocks_at_registered_risk_threshold():
    baseline = DynamicRiskEvidenceBaseline(
        DynamicRiskEvidenceRegistration(baseline_id="dynamic")
    )
    high_risk = baseline.evaluate(make_case(
        "high-risk",
        base_risk_bps=2_000,
        risk_signals=[RiskSignal(
            code="UNUSUAL_DESTINATION",
            risk_weight_bps=6_000,
            source_reference="synthetic unit test",
        )],
    ))
    assert high_risk.decision == Decision.BLOCK
    assert high_risk.reason_codes == ["DYNAMIC_RISK_BLOCK_THRESHOLD"]


def test_conservative_baseline_is_an_explicit_zero_coverage_control():
    baseline = ConservativeAbstainBaseline(ConservativeAbstainRegistration(
        baseline_id="conservative",
        simulated_decision_overhead_ms=1,
    ))
    decision = baseline.evaluate(make_case("any"))
    assert decision.decision == Decision.ABSTAIN
    assert decision.reason_codes == ["CONSERVATIVE_ALWAYS_ABSTAIN"]
    assert decision.verification_latency_ms == 1
