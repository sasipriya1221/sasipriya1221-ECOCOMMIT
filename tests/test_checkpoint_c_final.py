from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from ecocommit.checkpoint_c_final import (
    CheckpointCAcceptanceRule,
    CheckpointCFinalEvidence,
    CheckpointCFinalMetricSnapshot,
    CheckpointCFinalRegistration,
    CheckpointCUpstreamBinding,
    evaluate_final_metrics,
)


NOW = datetime(2026, 9, 1, 19, 0, tzinfo=timezone.utc)


def _registration():
    return CheckpointCFinalRegistration.create(
        registration_id="c-final-registration",
        registered_at_utc=NOW,
        outcomes_observed_before_registration=False,
        final_execution_id="c-final-execution",
        final_execution_nonce_sha256="8" * 64,
        final_suite_sha256="a" * 64,
        final_case_ids_sha256="b" * 64,
        final_case_count=40,
        metric_specification_sha256="c" * 64,
        tel_weights_sha256="d" * 64,
        cost_source_manifest_sha256="e" * 64,
        candidate_id="ecocommit-integrated",
        candidate_execution_protocol_sha256="f" * 64,
        comparator_execution_protocol_sha256="6" * 64,
        comparator_selection_receipt_sha256="7" * 64,
        upstream=CheckpointCUpstreamBinding(
            checkpoint_a_receipt_sha256="1" * 64,
            checkpoint_b_receipt_sha256="2" * 64,
            integrated_candidate_revision="3" * 40,
        ),
        acceptance_rule=CheckpointCAcceptanceRule(
            comparator_id="dynamic-strongest",
            minimum_tel_reduction_bps=1000,
            minimum_autonomous_coverage=0.60,
            minimum_legitimate_completion=0.80,
            minimum_selective_reliability=0.95,
            maximum_p95_verification_latency_ms=500,
            maximum_errored_cases=0,
            maximum_missing_latency_cases=0,
            maximum_incorrect_irreversible_amount_minor=0,
            rationale="Frozen before outcomes: require a material loss reduction without sacrificing safety or completion.",
        ),
    )


def _metrics(baseline_id, tel):
    return CheckpointCFinalMetricSnapshot(
        baseline_id=baseline_id,
        total_cases=40,
        total_economic_loss_minor=tel,
        autonomous_coverage=0.85,
        legitimate_transaction_completion=0.90,
        selective_reliability=0.98,
        p95_verification_latency_ms=400,
        errored_cases=0,
        missing_latency_cases=0,
        incorrect_irreversible_amount_minor=0,
        case_results_sha256=("4" if baseline_id == "ecocommit-integrated" else "5") * 64,
    )


def test_preregistered_final_gate_passes_only_at_quantitative_boundaries():
    registration = _registration()
    candidate = _metrics("ecocommit-integrated", 900)
    comparator = _metrics("dynamic-strongest", 1000)

    decision = evaluate_final_metrics(registration, candidate, comparator)

    assert decision.passed is True
    assert decision.tel_reduction_bps == 1000

    below = candidate.model_copy(update={"total_economic_loss_minor": 901})
    failed = evaluate_final_metrics(registration, below, comparator)
    assert failed.passed is False
    assert "TEL_REDUCTION_BELOW_PREREGISTERED_MARGIN" in failed.blockers

    zero_margin_registration = registration.model_copy(update={
        "acceptance_rule": registration.acceptance_rule.model_copy(
            update={"minimum_tel_reduction_bps": 0}
        )
    })
    tie = evaluate_final_metrics(
        zero_margin_registration,
        _metrics("ecocommit-integrated", 1000),
        comparator,
    )
    assert tie.passed is False
    assert "TEL_NOT_STRICTLY_BETTER" in tie.blockers

    low_coverage = candidate.model_copy(update={"autonomous_coverage": 0.59})
    coverage_failure = evaluate_final_metrics(
        registration,
        low_coverage,
        comparator,
    )
    assert coverage_failure.passed is False
    assert "AUTONOMOUS_COVERAGE_BELOW_FLOOR" in coverage_failure.blockers


def test_final_evidence_recomputes_decision_and_binds_suite_upstream_and_time():
    registration = _registration()
    candidate = _metrics("ecocommit-integrated", 800)
    comparator = _metrics("dynamic-strongest", 1000)
    evidence = CheckpointCFinalEvidence(
        generated_at_utc=NOW + timedelta(minutes=1),
        registration=registration,
        final_suite_sha256=registration.final_suite_sha256,
        final_case_ids_sha256=registration.final_case_ids_sha256,
        upstream=registration.upstream,
        candidate=candidate,
        comparator=comparator,
        decision=evaluate_final_metrics(registration, candidate, comparator),
    )
    assert evidence.decision.passed is True

    payload = evidence.model_dump(mode="python")
    payload["decision"]["passed"] = False
    with pytest.raises(ValidationError, match="does not match preregistered rule"):
        CheckpointCFinalEvidence.model_validate(payload)


def test_fixture_or_simulated_final_inputs_are_structurally_refused():
    payload = _metrics("ecocommit-integrated", 800).model_dump(mode="python")
    payload["contains_fixture_inputs"] = True
    with pytest.raises(ValidationError):
        CheckpointCFinalMetricSnapshot.model_validate(payload)


def test_registration_digest_detects_post_registration_rule_changes():
    registration = _registration()
    payload = registration.model_dump(mode="python")
    changed_rule = registration.acceptance_rule.model_copy(
        update={"minimum_tel_reduction_bps": 0}
    )
    payload["acceptance_rule"] = changed_rule
    with pytest.raises(ValidationError, match="registration digest is invalid"):
        CheckpointCFinalRegistration.model_validate(payload)


def test_registration_rejects_candidate_as_its_own_comparator():
    registration = _registration()
    values = registration.model_dump(exclude={"registration_sha256"})
    values["acceptance_rule"] = registration.acceptance_rule.model_copy(
        update={"comparator_id": registration.candidate_id}
    )

    with pytest.raises(ValidationError, match="identities must be distinct"):
        CheckpointCFinalRegistration.create(**values)
