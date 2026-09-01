from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta, timezone
from hashlib import sha256

import pytest
from pydantic import ValidationError

from ecocommit.checkpoint_c_models import (
    ArtifactMaturity,
    BenchmarkCase,
    BenchmarkPlan,
    BenchmarkSplit,
    BenchmarkSuite,
    ConservativeAbstainRegistration,
    CompensationOutcome,
    CostProvenance,
    Decision,
    DynamicRiskEvidenceRegistration,
    EconomicCostProfile,
    EconomicLossWeights,
    EvidenceObservation,
    EvidenceStatus,
    LatencyProvenance,
    MetricSpecification,
    NaiveAgentReplayRegistration,
    ObservationSourceKind,
    PromptGuardrailReplayRegistration,
    ReferenceOutcome,
    RegisteredAgentDecision,
    ReplaySourceKind,
    RiskSignal,
    ScenarioProvenance,
    ScenarioSourceKind,
    StaticRulesRegistration,
)


def digest_text(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def make_case(
    case_id: str,
    *,
    should_execute: bool = True,
    legitimate_completion_expected: bool | None = None,
    compensation_required: bool = True,
    requested_amount_minor: int = 5_000,
    policy_limit_minor: int = 10_000,
    irreversible_exposure_minor: int = 2_000,
    base_risk_bps: int = 1_000,
    evidence_status: EvidenceStatus = EvidenceStatus.VERIFIED,
    evidence_latency_ms: int = 5,
    risk_signals: list[RiskSignal] | None = None,
) -> BenchmarkCase:
    instruction = f"Synthetic procurement instruction for {case_id}."
    if legitimate_completion_expected is None:
        legitimate_completion_expected = should_execute
    return BenchmarkCase(
        case_id=case_id,
        scenario_family="unit-test-procurement",
        description=f"Synthetic test scenario {case_id}",
        instruction_text=instruction,
        instruction_sha256=digest_text(instruction),
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
            source_kind=ObservationSourceKind.SYNTHETIC_FIXTURE,
            source_reference="tests/fixtures/checkpoint_c/frozen_suite.json#/cases/0/evidence/0",
            observation_is_fixture=True,
            simulated_verification_latency_ms=evidence_latency_ms,
        )],
        risk_signals=risk_signals or [],
        reference_outcome=ReferenceOutcome(
            authorized_safe_to_execute=should_execute,
            legitimate_completion_expected=legitimate_completion_expected,
            compensation_outcome_if_unsafe_execution=(
                CompensationOutcome.SUCCEEDED
                if compensation_required
                else CompensationOutcome.NOT_REQUIRED
            ),
        ),
        costs=EconomicCostProfile(
            provenance=CostProvenance.SIMULATED,
            unsafe_execution_loss_minor=9_000,
            false_abort_loss_minor=700,
            abstention_review_loss_minor=50,
            compensation_cost_minor=400,
            basis="Synthetic unit-test values; not observed economic outcomes.",
        ),
        provenance=ScenarioProvenance(
            source_kind=ScenarioSourceKind.SYNTHETIC_SIMULATION,
            source_reference="tests/fixtures/checkpoint_c/frozen_suite.json",
            scenario_is_simulated=True,
            notes="Harness validation only; not final benchmark evidence.",
        ),
        tags=["synthetic", "unit-test"],
    )


def make_suite(cases: list[BenchmarkCase] | None = None) -> BenchmarkSuite:
    return BenchmarkSuite(
        suite_id="checkpoint-c-unit-suite",
        suite_version="1",
        description="Synthetic development-only Checkpoint C suite.",
        definitions_frozen_at_utc=datetime(2026, 1, 1, tzinfo=UTC),
        cases=cases or [make_case("c-001"), make_case("c-002", should_execute=False)],
        contains_live_checkpoint_a_outputs=False,
    )


def _agent_decisions(
    suite: BenchmarkSuite,
    *,
    label: str,
    guarded: bool,
) -> list[RegisteredAgentDecision]:
    decisions: list[RegisteredAgentDecision] = []
    for case in suite.cases:
        decision = (
            Decision.EXECUTE
            if not guarded or case.reference_outcome.authorized_safe_to_execute
            else Decision.BLOCK
        )
        output = f"Synthetic {label} fixture for {case.case_id}: {decision.value}"
        decisions.append(RegisteredAgentDecision(
            case_id=case.case_id,
            decision=decision,
            reason_codes=[f"SYNTHETIC_{label.upper()}_FIXTURE"],
            verification_latency_ms=11 if not guarded else 13,
            latency_provenance=LatencyProvenance.SIMULATED,
            source_output_text=output,
            source_output_sha256=digest_text(output),
        ))
    return decisions


def response_set_digest(decisions: list[RegisteredAgentDecision]) -> str:
    payload = json.dumps(
        [decision.model_dump(mode="json") for decision in decisions],
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return digest_text(payload)


def make_plan(suite: BenchmarkSuite, *, seed: int = 42) -> BenchmarkPlan:
    naive_decisions = _agent_decisions(suite, label="naive", guarded=False)
    guarded_decisions = _agent_decisions(suite, label="guardrail", guarded=True)
    return BenchmarkPlan(
        plan_id="checkpoint-c-unit-plan",
        plan_revision="1",
        description="Preliminary deterministic baseline unit-test plan.",
        registered_at_utc=datetime(2026, 1, 1, 0, 1, tzinfo=UTC),
        suite_id=suite.suite_id,
        suite_version=suite.suite_version,
        suite_sha256=suite.canonical_hash(),
        seed=seed,
        baselines=[
            NaiveAgentReplayRegistration(
                baseline_id="naive-agent-fixture-v1",
                model_id="synthetic-naive-agent-fixture",
                prompt_protocol_reference="tests/fixtures/checkpoint_c/naive-prompt.txt",
                prompt_protocol_sha256=digest_text("synthetic naive prompt fixture\n"),
                response_set_sha256=response_set_digest(naive_decisions),
                replay_source_kind=ReplaySourceKind.SYNTHETIC_FIXTURE,
                source_reference="tests/fixtures/checkpoint_c/frozen_plan.json#/baselines/0/decisions",
                outputs_are_synthetic_fixture=True,
                decisions=naive_decisions,
            ),
            PromptGuardrailReplayRegistration(
                baseline_id="prompt-guardrail-fixture-v1",
                model_id="synthetic-prompt-guardrail-fixture",
                prompt_protocol_reference="tests/fixtures/checkpoint_c/guarded-prompt.txt",
                prompt_protocol_sha256=digest_text("synthetic guarded prompt fixture\n"),
                guardrail_protocol_reference="tests/fixtures/checkpoint_c/guardrail.txt",
                guardrail_protocol_sha256=digest_text("synthetic prompt guardrail fixture\n"),
                response_set_sha256=response_set_digest(guarded_decisions),
                replay_source_kind=ReplaySourceKind.SYNTHETIC_FIXTURE,
                source_reference="tests/fixtures/checkpoint_c/frozen_plan.json#/baselines/1/decisions",
                outputs_are_synthetic_fixture=True,
                decisions=guarded_decisions,
            ),
            StaticRulesRegistration(
                baseline_id="static-v1",
                amount_ceiling_minor=8_000,
                blocked_signal_codes=["DENYLIST_MATCH"],
            ),
            DynamicRiskEvidenceRegistration(
                baseline_id="dynamic-v1",
                selection_rationale=(
                    "Synthetic local harness comparator exercising policy, risk, "
                    "evidence status, and freshness; strength is not a final claim."
                ),
            ),
            ConservativeAbstainRegistration(baseline_id="abstain-v1"),
        ],
        metrics=MetricSpecification(
            loss_weights=EconomicLossWeights(
                unsafe_execution_weight_bps=10_000,
                false_abort_weight_bps=5_000,
                abstention_review_weight_bps=20_000,
                compensation_cost_weight_bps=15_000,
                basis="Synthetic preliminary weights for accounting tests only.",
            )
        ),
    )


def test_suite_hash_is_stable_across_json_round_trip():
    suite = make_suite()
    restored = BenchmarkSuite.model_validate_json(suite.model_dump_json())
    assert restored.canonical_hash() == suite.canonical_hash()
    assert restored.contains_live_checkpoint_a_outputs is False
    assert restored.eligible_for_final_claims is False


def test_instruction_text_is_frozen_by_its_digest():
    payload = make_case("instruction").model_dump(mode="json")
    payload["instruction_text"] = "Changed after registration."
    with pytest.raises(ValidationError, match="instruction digest"):
        BenchmarkCase.model_validate(payload)


def test_synthetic_scenario_cannot_hide_its_simulated_status():
    with pytest.raises(ValidationError, match="explicitly labelled simulated"):
        ScenarioProvenance(
            source_kind=ScenarioSourceKind.SYNTHETIC_SIMULATION,
            source_reference="synthetic-generator-v1",
            scenario_is_simulated=False,
        )


def test_synthetic_evidence_cannot_hide_its_fixture_status():
    with pytest.raises(ValidationError, match="labelled fixture data"):
        EvidenceObservation(
            evidence_id="fixture",
            evidence_class="fixture",
            status=EvidenceStatus.VERIFIED,
            source_kind=ObservationSourceKind.SYNTHETIC_FIXTURE,
            source_reference="fixture.json",
            observation_is_fixture=False,
        )


def test_case_rejects_exposure_beyond_transaction_amount():
    with pytest.raises(ValidationError, match="irreversible exposure"):
        make_case(
            "bad-exposure",
            requested_amount_minor=1_000,
            irreversible_exposure_minor=1_001,
        )


def test_authorization_and_legitimate_completion_ground_truth_are_independent():
    outcome = ReferenceOutcome(
        authorized_safe_to_execute=False,
        legitimate_completion_expected=True,
        compensation_outcome_if_unsafe_execution=CompensationOutcome.FAILED,
    )
    assert outcome.authorized_safe_to_execute is False
    assert outcome.legitimate_completion_expected is True


def test_authorized_safe_execution_cannot_claim_completion_is_illegitimate():
    with pytest.raises(ValidationError, match="must also expect legitimate completion"):
        ReferenceOutcome(
            authorized_safe_to_execute=True,
            legitimate_completion_expected=False,
            compensation_outcome_if_unsafe_execution=CompensationOutcome.NOT_REQUIRED,
        )


def test_plan_registers_all_required_comparators_and_both_prerequisites():
    plan = make_plan(make_suite())
    assert plan.maturity == ArtifactMaturity.PRELIMINARY_NOT_FINAL
    assert plan.eligible_for_final_claims is False
    assert plan.checkpoint_a_final_pass_required is True
    assert plan.checkpoint_b_final_pass_required is True
    assert [baseline.baseline_type for baseline in plan.baselines] == [
        "NAIVE_AGENT_REPLAY",
        "PROMPT_GUARDRAIL_REPLAY",
        "STATIC_RULES",
        "DYNAMIC_DETERMINISTIC_WORKFLOW",
        "CONSERVATIVE_ABSTAIN",
    ]


def test_plan_rejects_missing_required_comparator():
    suite = make_suite()
    payload = make_plan(suite).model_dump(mode="json")
    payload["baselines"] = payload["baselines"][1:]
    with pytest.raises(ValidationError, match="exactly one naive-agent"):
        BenchmarkPlan.model_validate(payload)


def test_plan_rejects_duplicate_baseline_ids():
    suite = make_suite()
    payload = make_plan(suite).model_dump(mode="json")
    payload["baselines"][1]["baseline_id"] = payload["baselines"][0]["baseline_id"]
    with pytest.raises(ValidationError, match="baseline ids must be unique"):
        BenchmarkPlan.model_validate(payload)


def test_agent_fixture_requires_retained_output_and_matching_response_digest():
    suite = make_suite()
    payload = make_plan(suite).model_dump(mode="json")["baselines"][0]
    payload["decisions"][0]["source_output_text"] = None
    with pytest.raises(ValidationError, match="retain their fixture outputs"):
        NaiveAgentReplayRegistration.model_validate(payload)

    payload = make_plan(suite).model_dump(mode="json")["baselines"][0]
    payload["response_set_sha256"] = "0" * 64
    with pytest.raises(ValidationError, match="response-set digest"):
        NaiveAgentReplayRegistration.model_validate(payload)


def test_agent_replay_manifest_can_retain_an_explicit_error_row():
    output = "Synthetic provider failure fixture."
    decision = RegisteredAgentDecision(
        case_id="provider-error",
        decision=Decision.ERROR,
        reason_codes=["PROVIDER_ERROR"],
        verification_latency_ms=None,
        latency_provenance=LatencyProvenance.NOT_AVAILABLE,
        source_output_text=output,
        source_output_sha256=digest_text(output),
    )
    registration = NaiveAgentReplayRegistration(
        baseline_id="naive-error-fixture",
        model_id="synthetic-fixture",
        prompt_protocol_reference="fixture://prompt",
        prompt_protocol_sha256=digest_text("fixture prompt"),
        response_set_sha256=response_set_digest([decision]),
        replay_source_kind=ReplaySourceKind.SYNTHETIC_FIXTURE,
        source_reference="fixture://responses",
        outputs_are_synthetic_fixture=True,
        decisions=[decision],
    )
    assert registration.decisions[0].decision == Decision.ERROR


def test_dynamic_workflow_cannot_disable_fail_closed_evidence_behavior():
    with pytest.raises(ValidationError):
        DynamicRiskEvidenceRegistration(
            baseline_id="weak",
            selection_rationale="Invalid weak comparator.",
            block_on_required_failure=False,
        )


def test_registration_times_must_be_utc_not_merely_timezone_aware():
    suite = make_suite()
    payload = make_plan(suite).model_dump(mode="json")
    payload["registered_at_utc"] = datetime(
        2026,
        1,
        1,
        tzinfo=timezone(timedelta(hours=5, minutes=30)),
    ).isoformat()
    with pytest.raises(ValidationError, match="expressed in UTC"):
        BenchmarkPlan.model_validate(payload)
