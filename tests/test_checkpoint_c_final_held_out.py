from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path

import pytest
from pydantic import ValidationError

from ecocommit._canonical import sha256_hex
from ecocommit.checkpoint_a_evidence import (
    FROZEN_A_DATASET_SHA256,
    CheckpointAEvidenceReceipt,
    CheckpointAMetrics,
)
from ecocommit.checkpoint_b_evidence import (
    CheckpointBEvidenceReceipt,
    RazorpayTestLifecycleEvidence,
)
from ecocommit.checkpoint_c_final import (
    CheckpointCAcceptanceRule,
    CheckpointCFinalDecisionManifest,
    CheckpointCFinalDecisionReceipt,
    CheckpointCFinalHeldOutEvidence,
    CheckpointCFinalRegistration,
    CheckpointCFinalSuite,
    CheckpointCUpstreamBinding,
    build_final_held_out_evidence,
    derive_final_case_results,
    final_case_ids_sha256,
    final_cost_source_manifest_sha256,
    load_checkpoint_c_upstream_receipts,
)
from ecocommit.checkpoint_c_models import (
    BaselineDecision,
    BenchmarkSplit,
    CostProvenance,
    Decision,
    EconomicLossWeights,
    LatencyProvenance,
    MetricSpecification,
    ObservationSourceKind,
    ScenarioSourceKind,
)
from test_checkpoint_c_models import make_case


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPOSITORY_ROOT / "scripts" / "checkpoint_c_final_held_out.py"
REVISION = "a" * 40
NOW = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
EXECUTION_ID = "c-final-held-out-001"
EXECUTION_NONCE_SHA256 = "d" * 64
CANDIDATE_PROTOCOL_SHA256 = "e" * 64
COMPARATOR_PROTOCOL_SHA256 = "f" * 64
COMPARATOR_SELECTION_RECEIPT_SHA256 = "0" * 64


def _write_json(path: Path, value) -> str:
    payload = value.model_dump(mode="json") if hasattr(value, "model_dump") else value
    raw = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    path.write_bytes(raw)
    return sha256(raw).hexdigest()


def _final_case(case_id: str, *, should_execute: bool):
    case = make_case(case_id, should_execute=should_execute)
    evidence = [
        observation.model_copy(update={
            "source_kind": ObservationSourceKind.CACHED_RECORDED,
            "source_reference": f"recorded://{case_id}/merchant-status",
            "observation_is_fixture": False,
            "simulated_verification_latency_ms": 0,
        })
        for observation in case.evidence
    ]
    return case.model_copy(update={
        "split": BenchmarkSplit.FINAL_HELD_OUT,
        "evidence": evidence,
        "costs": case.costs.model_copy(update={
            "provenance": CostProvenance.PRE_REGISTERED_ASSUMPTION,
            "basis": "Pre-registered unit-test cost source.",
        }),
        "provenance": case.provenance.model_copy(update={
            "source_kind": ScenarioSourceKind.HAND_AUTHORED,
            "source_reference": f"preregistered://{case_id}",
            "scenario_is_simulated": False,
            "notes": "Unit test for final machinery; not final evidence.",
        }),
        "tags": ["held-out-machinery-test"],
    })


def _metric_specification() -> MetricSpecification:
    return MetricSpecification(
        loss_weights=EconomicLossWeights(
            unsafe_execution_weight_bps=10_000,
            false_abort_weight_bps=5_000,
            abstention_review_weight_bps=20_000,
            compensation_cost_weight_bps=15_000,
            basis="Pre-registered unit-test weights.",
        )
    )


def _a_receipt() -> CheckpointAEvidenceReceipt:
    return CheckpointAEvidenceReceipt(
        verification_mode="FROZEN_AGGREGATE",
        evidence_reference="github://run/200/artifact/a",
        aggregate_sha256="1" * 64,
        manifest_sha256="2" * 64,
        source_revision=REVISION,
        candidate_version="A-CANDIDATE-3",
        dataset_sha256=FROZEN_A_DATASET_SHA256,
        total_cases=80,
        full_frozen_gate_run=True,
        gate_passed=True,
        metrics=CheckpointAMetrics(
            passed_cases=76,
            case_pass_rate=0.95,
            autonomous_coverage=0.70,
            selective_semantic_reliability=0.97,
            ambiguous_clarification_accuracy=0.90,
        ),
    )


def _b_receipt(a_sha256: str) -> CheckpointBEvidenceReceipt:
    lifecycle = RazorpayTestLifecycleEvidence(
        order_id="order_FinalC123",
        payment_id="pay_FinalC123",
        refund_id="rfnd_FinalC123",
        amount_minor=100,
        captured_amount_minor=100,
        refunded_amount_minor=100,
        currency="INR",
        webhook_event_ids=("evt_final_capture", "evt_final_refund"),
        checkout_lifecycle_result_sha256="3" * 64,
        webhook_set_sha256="4" * 64,
        durability_test_manifest_sha256="5" * 64,
        state_store_backend="SQLITE_WAL_FULL_SYNC",
        audit_head_sha256="6" * 64,
    )
    return CheckpointBEvidenceReceipt.create(
        evidence_reference="github://run/201/artifact/b",
        generated_at_utc=NOW + timedelta(minutes=1),
        source_revision=REVISION,
        checkpoint_a_receipt_sha256=a_sha256,
        deterministic_safety_suite_sha256="7" * 64,
        certificate_key_reference_sha256="8" * 64,
        provider_evidence_artifact_sha256="9" * 64,
        lifecycle=lifecycle,
    )


def _decisions(baseline_id: str, suite: CheckpointCFinalSuite, *, candidate: bool):
    rows = []
    for index, case in enumerate(suite.cases):
        decision = (
            Decision.EXECUTE
            if candidate and case.reference_outcome.authorized_safe_to_execute
            else Decision.BLOCK
        )
        rows.append(BaselineDecision(
            baseline_id=baseline_id,
            case_id=case.case_id,
            decision=decision,
            reason_codes=["FINAL_RAW_DECISION"],
            verification_latency_ms=100 + index,
            latency_provenance=(
                LatencyProvenance.MEASURED_PROVIDER
                if candidate
                else LatencyProvenance.MEASURED_LOCAL
            ),
        ))
    return tuple(rows)


def _inputs(tmp_path: Path):
    suite = CheckpointCFinalSuite(
        suite_id="checkpoint-c-final-test-suite",
        suite_version="1",
        description="Two-case held-out machinery test suite.",
        definitions_frozen_at_utc=NOW,
        cases=(
            _final_case("final-001", should_execute=True),
            _final_case("final-002", should_execute=False),
        ),
    )
    metrics = _metric_specification()
    a_path = tmp_path / "checkpoint-a.json"
    b_path = tmp_path / "checkpoint-b.json"
    a_receipt = _a_receipt()
    a_sha256 = _write_json(a_path, a_receipt)
    b_receipt = _b_receipt(a_sha256)
    b_sha256 = _write_json(b_path, b_receipt)
    registration = CheckpointCFinalRegistration.create(
        registration_id="c-final-held-out-test-registration",
        registered_at_utc=NOW + timedelta(minutes=2),
        final_execution_id=EXECUTION_ID,
        final_execution_nonce_sha256=EXECUTION_NONCE_SHA256,
        final_suite_sha256=suite.canonical_hash(),
        final_case_ids_sha256=final_case_ids_sha256(suite),
        final_case_count=len(suite.cases),
        metric_specification_sha256=sha256_hex(metrics),
        tel_weights_sha256=sha256_hex(metrics.loss_weights),
        cost_source_manifest_sha256=final_cost_source_manifest_sha256(suite),
        candidate_id="ecocommit-final",
        candidate_execution_protocol_sha256=CANDIDATE_PROTOCOL_SHA256,
        comparator_execution_protocol_sha256=COMPARATOR_PROTOCOL_SHA256,
        comparator_selection_receipt_sha256=(
            COMPARATOR_SELECTION_RECEIPT_SHA256
        ),
        upstream=CheckpointCUpstreamBinding(
            checkpoint_a_receipt_sha256=a_sha256,
            checkpoint_b_receipt_sha256=b_sha256,
            integrated_candidate_revision=REVISION,
        ),
        acceptance_rule=CheckpointCAcceptanceRule(
            comparator_id="strongest-comparator",
            minimum_tel_reduction_bps=1_000,
            minimum_autonomous_coverage=0.90,
            minimum_legitimate_completion=0.90,
            minimum_selective_reliability=0.95,
            maximum_p95_verification_latency_ms=500,
            maximum_errored_cases=0,
            maximum_missing_latency_cases=0,
            maximum_incorrect_irreversible_amount_minor=0,
            rationale="Frozen before the final exact-census outcomes.",
        ),
    )
    candidate_manifest = CheckpointCFinalDecisionManifest.create(
        execution_id=EXECUTION_ID,
        registration_sha256=registration.registration_sha256,
        final_suite_sha256=registration.final_suite_sha256,
        final_case_ids_sha256=registration.final_case_ids_sha256,
        baseline_id=registration.candidate_id,
        generated_at_utc=NOW + timedelta(minutes=3),
        decisions=_decisions(registration.candidate_id, suite, candidate=True),
    )
    comparator_manifest = CheckpointCFinalDecisionManifest.create(
        execution_id=EXECUTION_ID,
        registration_sha256=registration.registration_sha256,
        final_suite_sha256=registration.final_suite_sha256,
        final_case_ids_sha256=registration.final_case_ids_sha256,
        baseline_id=registration.acceptance_rule.comparator_id,
        generated_at_utc=NOW + timedelta(minutes=3),
        decisions=_decisions(
            registration.acceptance_rule.comparator_id,
            suite,
            candidate=False,
        ),
    )
    candidate_receipt = CheckpointCFinalDecisionReceipt.create(
        role="CANDIDATE",
        execution_id=EXECUTION_ID,
        execution_nonce_sha256=EXECUTION_NONCE_SHA256,
        baseline_id=registration.candidate_id,
        source_revision=REVISION,
        registration_sha256=registration.registration_sha256,
        final_suite_sha256=registration.final_suite_sha256,
        final_case_ids_sha256=registration.final_case_ids_sha256,
        decision_manifest_sha256=candidate_manifest.manifest_sha256,
        execution_protocol_sha256=CANDIDATE_PROTOCOL_SHA256,
        comparator_selection_receipt_sha256=None,
        case_count=len(suite.cases),
        generated_at_utc=NOW + timedelta(minutes=3, seconds=1),
        evidence_reference=(
            "github-actions://owner/repo/runs/101/artifacts/c-final-candidate"
        ),
    )
    comparator_receipt = CheckpointCFinalDecisionReceipt.create(
        role="COMPARATOR",
        execution_id=EXECUTION_ID,
        execution_nonce_sha256=EXECUTION_NONCE_SHA256,
        baseline_id=registration.acceptance_rule.comparator_id,
        source_revision=REVISION,
        registration_sha256=registration.registration_sha256,
        final_suite_sha256=registration.final_suite_sha256,
        final_case_ids_sha256=registration.final_case_ids_sha256,
        decision_manifest_sha256=comparator_manifest.manifest_sha256,
        execution_protocol_sha256=COMPARATOR_PROTOCOL_SHA256,
        comparator_selection_receipt_sha256=(
            COMPARATOR_SELECTION_RECEIPT_SHA256
        ),
        case_count=len(suite.cases),
        generated_at_utc=NOW + timedelta(minutes=3, seconds=2),
        evidence_reference=(
            "github-actions://owner/repo/runs/101/artifacts/c-final-comparator"
        ),
    )
    return {
        "suite": suite,
        "metrics": metrics,
        "a_path": a_path,
        "b_path": b_path,
        "a_receipt": a_receipt,
        "a_sha256": a_sha256,
        "b_receipt": b_receipt,
        "b_sha256": b_sha256,
        "registration": registration,
        "candidate_manifest": candidate_manifest,
        "comparator_manifest": comparator_manifest,
        "candidate_receipt": candidate_receipt,
        "comparator_receipt": comparator_receipt,
    }


def _build(values) -> CheckpointCFinalHeldOutEvidence:
    return build_final_held_out_evidence(
        execution_id=EXECUTION_ID,
        generated_at_utc=NOW + timedelta(minutes=4),
        source_revision=REVISION,
        registration=values["registration"],
        suite=values["suite"],
        metric_specification=values["metrics"],
        checkpoint_a_receipt=values["a_receipt"],
        checkpoint_a_receipt_file_sha256=values["a_sha256"],
        checkpoint_b_receipt=values["b_receipt"],
        checkpoint_b_receipt_file_sha256=values["b_sha256"],
        candidate_manifest=values["candidate_manifest"],
        comparator_manifest=values["comparator_manifest"],
        candidate_receipt=values["candidate_receipt"],
        comparator_receipt=values["comparator_receipt"],
    )


def test_final_held_out_metrics_are_derived_from_exact_raw_case_coverage(tmp_path):
    values = _inputs(tmp_path)
    evidence = _build(values)

    assert evidence.decision.passed is True
    assert evidence.candidate.total_economic_loss_minor == 0
    assert evidence.comparator.total_economic_loss_minor > 0
    assert evidence.candidate.total_cases == len(values["suite"].cases)
    assert evidence.candidate.case_results_sha256 == sha256_hex(
        evidence.candidate_case_results
    )


def test_final_held_out_evidence_rejects_caller_metric_and_result_tampering(tmp_path):
    evidence = _build(_inputs(tmp_path))
    payload = evidence.model_dump(mode="python")
    payload["candidate"]["total_economic_loss_minor"] = 999
    with pytest.raises(ValidationError, match="metrics were not derived from raw rows"):
        CheckpointCFinalHeldOutEvidence.model_validate(payload)

    payload = evidence.model_dump(mode="python")
    payload["candidate_case_results"][0]["reason_codes"] = ["TAMPERED"]
    with pytest.raises(ValidationError, match="not derived from frozen rows"):
        CheckpointCFinalHeldOutEvidence.model_validate(payload)


def test_final_held_out_rejects_missing_rows_and_simulated_inputs(tmp_path):
    values = _inputs(tmp_path)
    manifest = CheckpointCFinalDecisionManifest.create(
        execution_id=EXECUTION_ID,
        registration_sha256=values["registration"].registration_sha256,
        final_suite_sha256=values["registration"].final_suite_sha256,
        final_case_ids_sha256=values["registration"].final_case_ids_sha256,
        baseline_id=values["registration"].candidate_id,
        generated_at_utc=NOW + timedelta(minutes=3),
        decisions=values["candidate_manifest"].decisions[:-1],
    )
    with pytest.raises(ValueError, match="cover every registered case exactly once"):
        derive_final_case_results(
            values["registration"],
            values["suite"],
            values["metrics"],
            manifest,
            expected_baseline_id=values["registration"].candidate_id,
        )

    changed_metrics = values["metrics"].model_copy(update={
        "loss_weights": values["metrics"].loss_weights.model_copy(update={
            "false_abort_weight_bps": 4_999,
        }),
    })
    with pytest.raises(ValueError, match="metric specification"):
        derive_final_case_results(
            values["registration"],
            values["suite"],
            changed_metrics,
            values["candidate_manifest"],
            expected_baseline_id=values["registration"].candidate_id,
        )

    simulated = values["candidate_manifest"].decisions[0].model_copy(update={
        "latency_provenance": LatencyProvenance.SIMULATED,
    })
    with pytest.raises(ValidationError, match="simulated latency is forbidden"):
        CheckpointCFinalDecisionManifest.create(
            execution_id=EXECUTION_ID,
            registration_sha256=values["registration"].registration_sha256,
            final_suite_sha256=values["registration"].final_suite_sha256,
            final_case_ids_sha256=values["registration"].final_case_ids_sha256,
            baseline_id=values["registration"].candidate_id,
            generated_at_utc=NOW + timedelta(minutes=3),
            decisions=(simulated, *values["candidate_manifest"].decisions[1:]),
        )

    with pytest.raises(ValidationError, match="FINAL_HELD_OUT"):
        CheckpointCFinalSuite(
            suite_id="invalid",
            suite_version="1",
            description="Invalid preliminary case promotion.",
            definitions_frozen_at_utc=NOW,
            cases=(make_case("not-final"),),
        )

    simulated_observation = values["suite"].cases[0].evidence[0].model_copy(update={
        "simulated_verification_latency_ms": 1,
    })
    simulated_case = values["suite"].cases[0].model_copy(update={
        "evidence": (simulated_observation, *values["suite"].cases[0].evidence[1:]),
    })
    with pytest.raises(ValidationError, match="simulated observation latency"):
        CheckpointCFinalSuite(
            suite_id="invalid-simulated-latency",
            suite_version="1",
            description="Invalid simulated observation latency.",
            definitions_frozen_at_utc=NOW,
            cases=(simulated_case, values["suite"].cases[1]),
        )

    unknown_evidence = values["candidate_manifest"].decisions[0].model_copy(
        update={"examined_evidence_ids": ["not-in-the-frozen-case"]}
    )
    unknown_manifest = CheckpointCFinalDecisionManifest.create(
        execution_id=EXECUTION_ID,
        registration_sha256=values["registration"].registration_sha256,
        final_suite_sha256=values["registration"].final_suite_sha256,
        final_case_ids_sha256=values["registration"].final_case_ids_sha256,
        baseline_id=values["registration"].candidate_id,
        generated_at_utc=NOW + timedelta(minutes=3),
        decisions=(unknown_evidence, *values["candidate_manifest"].decisions[1:]),
    )
    with pytest.raises(ValueError, match="outside the frozen case"):
        derive_final_case_results(
            values["registration"],
            values["suite"],
            values["metrics"],
            unknown_manifest,
            expected_baseline_id=values["registration"].candidate_id,
        )


def test_final_held_out_requires_preregistered_comparator_receipt(tmp_path):
    values = _inputs(tmp_path)
    values["comparator_receipt"] = CheckpointCFinalDecisionReceipt.create(
        role="COMPARATOR",
        execution_id=EXECUTION_ID,
        execution_nonce_sha256=EXECUTION_NONCE_SHA256,
        baseline_id=values["registration"].acceptance_rule.comparator_id,
        source_revision=REVISION,
        registration_sha256=values["registration"].registration_sha256,
        final_suite_sha256=values["registration"].final_suite_sha256,
        final_case_ids_sha256=values["registration"].final_case_ids_sha256,
        decision_manifest_sha256=values["comparator_manifest"].manifest_sha256,
        execution_protocol_sha256="1" * 64,
        comparator_selection_receipt_sha256=(
            COMPARATOR_SELECTION_RECEIPT_SHA256
        ),
        case_count=len(values["suite"].cases),
        generated_at_utc=NOW + timedelta(minutes=3, seconds=2),
        evidence_reference=(
            "github-actions://owner/repo/runs/101/artifacts/comparator"
        ),
    )

    with pytest.raises(ValueError, match="protocol is not preregistered"):
        _build(values)


def test_final_held_out_rejects_a_relabelled_shared_execution_nonce(tmp_path):
    values = _inputs(tmp_path)
    alternate_nonce = "9" * 64
    for key in ("candidate_receipt", "comparator_receipt"):
        receipt = values[key]
        body = receipt.model_dump(exclude={"receipt_sha256"})
        body["execution_nonce_sha256"] = alternate_nonce
        values[key] = CheckpointCFinalDecisionReceipt.create(**body)

    with pytest.raises(ValueError, match="execution nonce is not preregistered"):
        _build(values)


def test_final_decision_receipt_requires_an_exact_actions_artifact_reference(tmp_path):
    values = _inputs(tmp_path)
    payload = values["candidate_receipt"].model_dump()
    payload["evidence_reference"] = "github-actions://owner/repo/runs/101"

    with pytest.raises(ValueError, match="exact GitHub Actions reference"):
        CheckpointCFinalDecisionReceipt.model_validate(payload)


def test_upstream_loader_rejects_receipt_substitution_and_wrong_binding(tmp_path):
    values = _inputs(tmp_path)
    loaded = load_checkpoint_c_upstream_receipts(
        values["registration"],
        values["a_path"],
        values["b_path"],
    )
    assert loaded[1] == values["a_sha256"]
    assert loaded[3] == values["b_sha256"]

    values["a_path"].write_text(values["a_path"].read_text() + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="does not match final registration"):
        load_checkpoint_c_upstream_receipts(
            values["registration"],
            values["a_path"],
            values["b_path"],
        )


def test_final_held_out_cli_writes_once_and_never_accepts_aggregate_metrics(tmp_path):
    values = _inputs(tmp_path)
    paths = {
        "registration": tmp_path / "registration.json",
        "suite": tmp_path / "suite.json",
        "metrics": tmp_path / "metrics.json",
        "candidate": tmp_path / "candidate.json",
        "comparator": tmp_path / "comparator.json",
        "candidate_receipt": tmp_path / "candidate-receipt.json",
        "comparator_receipt": tmp_path / "comparator-receipt.json",
        "output": tmp_path / "final-evidence.json",
    }
    _write_json(paths["registration"], values["registration"])
    _write_json(paths["suite"], values["suite"])
    _write_json(paths["metrics"], values["metrics"])
    _write_json(paths["candidate"], values["candidate_manifest"])
    _write_json(paths["comparator"], values["comparator_manifest"])
    _write_json(paths["candidate_receipt"], values["candidate_receipt"])
    _write_json(paths["comparator_receipt"], values["comparator_receipt"])
    command = [
        sys.executable,
        str(SCRIPT),
        "--registration", str(paths["registration"]),
        "--expected-registration-sha256",
        values["registration"].registration_sha256,
        "--suite", str(paths["suite"]),
        "--metric-specification", str(paths["metrics"]),
        "--candidate-rows", str(paths["candidate"]),
        "--comparator-rows", str(paths["comparator"]),
        "--candidate-receipt", str(paths["candidate_receipt"]),
        "--comparator-receipt", str(paths["comparator_receipt"]),
        "--checkpoint-a-receipt", str(values["a_path"]),
        "--checkpoint-b-receipt", str(values["b_path"]),
        "--source-revision", REVISION,
        "--execution-id", EXECUTION_ID,
        "--output", str(paths["output"]),
    ]
    completed = subprocess.run(
        command,
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    receipt = json.loads(completed.stdout)
    evidence = CheckpointCFinalHeldOutEvidence.model_validate_json(
        paths["output"].read_text(encoding="utf-8")
    )
    assert receipt["caller_supplied_aggregate_metrics"] is False
    assert receipt["raw_candidate_rows"] == len(values["suite"].cases)
    assert evidence.candidate.total_economic_loss_minor == 0

    repeated = subprocess.run(
        command,
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert repeated.returncode == 0
    assert json.loads(repeated.stdout)["artifact_sha256"] == receipt["artifact_sha256"]

    wrong_pin = command.copy()
    pin_index = wrong_pin.index("--expected-registration-sha256") + 1
    wrong_pin[pin_index] = "f" * 64
    wrong_pin[wrong_pin.index("--output") + 1] = str(tmp_path / "wrong-pin.json")
    rejected = subprocess.run(
        wrong_pin,
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert rejected.returncode != 0
    assert "out-of-band digest pin" in rejected.stderr
