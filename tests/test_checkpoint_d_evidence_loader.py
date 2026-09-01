from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path

import pytest

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
    CheckpointCFinalEvidence,
    CheckpointCFinalMetricSnapshot,
    CheckpointCFinalRegistration,
    CheckpointCUpstreamBinding,
    evaluate_final_metrics,
)
from ecocommit.checkpoint_d_evidence import (
    AuthoritativeEvidenceError,
    AuthoritativeEvidencePins,
    AuthoritativeEvidenceStatusSource,
    CheckpointDIntegrationReceipt,
    EXPECTED_EVIDENCE_REPOSITORY,
    EvidenceFilePin,
    load_authoritative_evidence,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
REVISION = "a" * 40
NOW = datetime(2026, 9, 2, tzinfo=UTC)


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


def _a_receipt(*, fixture: bool = False) -> CheckpointAEvidenceReceipt:
    values = {
        "verification_mode": "TEST_FIXTURE" if fixture else "FROZEN_AGGREGATE",
        "evidence_reference": "github://run/100/artifact/a",
        "aggregate_sha256": "1" * 64,
        "manifest_sha256": "2" * 64,
        "source_revision": REVISION,
        "candidate_version": "TEST-FIXTURE" if fixture else "A-CANDIDATE-2",
        "dataset_sha256": "0" * 64 if fixture else FROZEN_A_DATASET_SHA256,
        "total_cases": 80,
        "full_frozen_gate_run": True,
        "gate_passed": True,
        "metrics": CheckpointAMetrics(
            passed_cases=76,
            case_pass_rate=0.95,
            autonomous_coverage=0.70,
            selective_semantic_reliability=0.97,
            ambiguous_clarification_accuracy=0.90,
        ),
    }
    return CheckpointAEvidenceReceipt(**values)


def _b_receipt(a_sha: str) -> CheckpointBEvidenceReceipt:
    lifecycle = RazorpayTestLifecycleEvidence(
        order_id="order_Test123",
        payment_id="pay_Test123",
        refund_id="rfnd_Test123",
        amount_minor=100,
        captured_amount_minor=100,
        refunded_amount_minor=100,
        currency="INR",
        webhook_event_ids=("evt_capture", "evt_refund"),
        checkout_lifecycle_result_sha256="a" * 64,
        webhook_set_sha256="b" * 64,
        durability_test_manifest_sha256="c" * 64,
        state_store_backend="SQLITE_WAL_FULL_SYNC",
        audit_head_sha256="3" * 64,
    )
    return CheckpointBEvidenceReceipt.create(
        evidence_reference="github://run/101/artifact/b",
        generated_at_utc=NOW,
        source_revision=REVISION,
        checkpoint_a_receipt_sha256=a_sha,
        deterministic_safety_suite_sha256="4" * 64,
        certificate_key_reference_sha256="5" * 64,
        provider_evidence_artifact_sha256="6" * 64,
        lifecycle=lifecycle,
    )


def _c_evidence(a_sha: str, b_sha: str, *, pass_decision: bool = True):
    upstream = CheckpointCUpstreamBinding(
        checkpoint_a_receipt_sha256=a_sha,
        checkpoint_b_receipt_sha256=b_sha,
        integrated_candidate_revision=REVISION,
    )
    registration = CheckpointCFinalRegistration.create(
        registration_id="final-c-1",
        registered_at_utc=NOW,
        final_suite_sha256="7" * 64,
        final_case_ids_sha256="8" * 64,
        final_case_count=10,
        metric_specification_sha256="9" * 64,
        tel_weights_sha256="b" * 64,
        cost_source_manifest_sha256="c" * 64,
        candidate_id="ecocommit-final",
        upstream=upstream,
        acceptance_rule=CheckpointCAcceptanceRule(
            comparator_id="strongest-comparator",
            minimum_tel_reduction_bps=1_000,
            minimum_legitimate_completion=0.90,
            minimum_selective_reliability=0.95,
            maximum_p95_verification_latency_ms=500,
            maximum_errored_cases=0,
            maximum_missing_latency_cases=0,
            maximum_incorrect_irreversible_amount_minor=0,
            rationale="Frozen before the final exact census.",
        ),
    )
    candidate = CheckpointCFinalMetricSnapshot(
        baseline_id="ecocommit-final",
        total_cases=10,
        total_economic_loss_minor=80 if pass_decision else 100,
        legitimate_transaction_completion=1.0,
        selective_reliability=1.0,
        p95_verification_latency_ms=50,
        errored_cases=0,
        missing_latency_cases=0,
        incorrect_irreversible_amount_minor=0,
        case_results_sha256="d" * 64,
    )
    comparator = CheckpointCFinalMetricSnapshot(
        baseline_id="strongest-comparator",
        total_cases=10,
        total_economic_loss_minor=100,
        legitimate_transaction_completion=0.90,
        selective_reliability=0.95,
        p95_verification_latency_ms=60,
        errored_cases=0,
        missing_latency_cases=0,
        incorrect_irreversible_amount_minor=0,
        case_results_sha256="e" * 64,
    )
    decision = evaluate_final_metrics(registration, candidate, comparator)
    return CheckpointCFinalEvidence(
        generated_at_utc=NOW + timedelta(minutes=1),
        registration=registration,
        final_suite_sha256=registration.final_suite_sha256,
        final_case_ids_sha256=registration.final_case_ids_sha256,
        upstream=upstream,
        candidate=candidate,
        comparator=comparator,
        decision=decision,
    )


def _d_receipt(a_sha: str, b_sha: str, c_sha: str):
    return CheckpointDIntegrationReceipt.create(
        generated_at_utc=NOW + timedelta(minutes=2),
        source_revision=REVISION,
        checkpoint_a_receipt_sha256=a_sha,
        checkpoint_b_receipt_sha256=b_sha,
        checkpoint_c_evidence_sha256=c_sha,
        hosted_base_url="https://test.ecocommit.example",
        durable_state_backend="SQLITE_WAL_FULL_SYNC_SINGLE_HOST",
        audit_head_sha256="f" * 64,
        audit_entries=25,
        end_to_end_result_sha256="1" * 64,
        operational_test_manifest_sha256="2" * 64,
    )


def _bundle(
    tmp_path: Path,
    *,
    include_d: bool = False,
    a_fixture: bool = False,
    wrong_b_a_binding: bool = False,
    c_pass_decision: bool = True,
    repository: str = EXPECTED_EVIDENCE_REPOSITORY,
):
    root = tmp_path / "evidence"
    root.mkdir()
    a_path = root / "checkpoint-a.json"
    b_path = root / "checkpoint-b.json"
    c_path = root / "checkpoint-c.json"
    a_sha = _write_json(a_path, _a_receipt(fixture=a_fixture))
    b_sha = _write_json(
        b_path,
        _b_receipt("f" * 64 if wrong_b_a_binding else a_sha),
    )
    c_sha = _write_json(c_path, _c_evidence(a_sha, b_sha, pass_decision=c_pass_decision))
    d_pin = None
    if include_d:
        d_path = root / "checkpoint-d.json"
        d_sha = _write_json(d_path, _d_receipt(a_sha, b_sha, c_sha))
        d_pin = EvidenceFilePin(filename=d_path.name, sha256=d_sha)

    pins = AuthoritativeEvidencePins.create(
        repository=repository,
        integrated_revision=REVISION,
        checkpoint_a=EvidenceFilePin(filename=a_path.name, sha256=a_sha),
        checkpoint_b=EvidenceFilePin(filename=b_path.name, sha256=b_sha),
        checkpoint_c=EvidenceFilePin(filename=c_path.name, sha256=c_sha),
        checkpoint_d=d_pin,
    )
    pins_path = tmp_path / "pins.json"
    pins_sha = _write_json(pins_path, pins)
    return root, pins_path, pins_sha


def test_loader_accepts_only_pinned_cross_linked_passing_a_b_c_receipts(tmp_path):
    root, pins_path, pins_sha = _bundle(tmp_path)

    loaded = load_authoritative_evidence(
        root,
        pins_path,
        expected_pins_file_sha256=pins_sha,
    )
    status = loaded.safety_status()

    assert status.gates["A"].accepted is True
    assert status.gates["B"].accepted is True
    assert status.gates["C"].accepted is True
    assert status.gates["D"].state.value == "BLOCKED"
    assert status.gates["E"].state.value == "BLOCKED"
    assert status.provider_calls_enabled is False
    assert status.irreversible_commit_ready is False
    with pytest.raises(TypeError):
        loaded.file_sha256["A"] = "f" * 64


def test_optional_d_receipt_is_cross_linked_but_cannot_enable_provider_calls(tmp_path):
    root, pins_path, pins_sha = _bundle(tmp_path, include_d=True)

    status = load_authoritative_evidence(
        root,
        pins_path,
        expected_pins_file_sha256=pins_sha,
    ).safety_status()

    assert status.gates["D"].accepted is True
    assert status.gates["E"].accepted is False
    assert status.final_integration_verified is True
    assert status.provider_credentials_verified is False
    assert status.provider_calls_enabled is False


def test_status_source_can_enable_only_a_c_pinned_test_execution_after_preflight(tmp_path):
    root, pins_path, pins_sha = _bundle(tmp_path)
    source = AuthoritativeEvidenceStatusSource(
        root,
        pins_path,
        pins_sha,
        provider_credentials_verified=True,
        provider_calls_enabled=True,
    )

    status = source()
    assert status.provider_test_execution_ready is True
    assert status.gates["D"].accepted is False
    assert status.irreversible_commit_ready is False
    assert status.snapshot()["safe_to_move_real_money"] is False

    with pytest.raises(ValueError, match="credential preflight"):
        AuthoritativeEvidenceStatusSource(
            root,
            pins_path,
            pins_sha,
            provider_calls_enabled=True,
        )


@pytest.mark.parametrize(
    ("options", "message"),
    [
        ({"a_fixture": True}, "fixture evidence is forbidden"),
        ({"wrong_b_a_binding": True}, "does not bind the pinned A receipt"),
        ({"c_pass_decision": False}, "final decision did not pass"),
        ({"repository": "other/project"}, "belongs to another repository"),
    ],
)
def test_loader_rejects_non_authoritative_or_incoherent_gate_claims(
    tmp_path,
    options,
    message,
):
    root, pins_path, pins_sha = _bundle(tmp_path, **options)

    with pytest.raises(AuthoritativeEvidenceError, match=message):
        load_authoritative_evidence(
            root,
            pins_path,
            expected_pins_file_sha256=pins_sha,
        )


def test_loader_rejects_pin_or_evidence_tampering(tmp_path):
    root, pins_path, pins_sha = _bundle(tmp_path)

    with pytest.raises(AuthoritativeEvidenceError, match="pin-set file digest mismatch"):
        load_authoritative_evidence(
            root,
            pins_path,
            expected_pins_file_sha256="0" * 64,
        )

    evidence_path = root / "checkpoint-b.json"
    evidence_path.write_bytes(evidence_path.read_bytes() + b" ")
    with pytest.raises(AuthoritativeEvidenceError, match="evidence file digest mismatch"):
        load_authoritative_evidence(
            root,
            pins_path,
            expected_pins_file_sha256=pins_sha,
        )


def test_loader_rejects_duplicate_keys_even_when_outer_file_hash_is_trusted(tmp_path):
    root, pins_path, _ = _bundle(tmp_path)
    raw = pins_path.read_bytes()
    duplicate = raw[:-1] + b',"schema_version":"D.EVIDENCE.PINS.1"}'
    pins_path.write_bytes(duplicate)

    with pytest.raises(AuthoritativeEvidenceError, match="duplicate JSON key"):
        load_authoritative_evidence(
            root,
            pins_path,
            expected_pins_file_sha256=sha256(duplicate).hexdigest(),
        )


def test_receipt_schemas_reject_unknown_fields_and_incomplete_lifecycle(tmp_path):
    a_payload = _a_receipt().model_dump(mode="json")
    a_payload["caller_claim"] = "passed"
    with pytest.raises(ValueError):
        CheckpointAEvidenceReceipt.model_validate(a_payload)

    lifecycle = _b_receipt("1" * 64).lifecycle.model_dump(mode="json")
    lifecycle["refund_processed"] = False
    with pytest.raises(ValueError):
        RazorpayTestLifecycleEvidence.model_validate(lifecycle)

    metric = _c_evidence("1" * 64, "2" * 64).candidate.model_dump(mode="json")
    metric["errored_cases"] = metric["total_cases"] + 1
    with pytest.raises(ValueError, match="exceeds total cases"):
        CheckpointCFinalMetricSnapshot.model_validate(metric)


def test_status_cli_verifies_bundle_without_provider_activity(tmp_path):
    root, pins_path, pins_sha = _bundle(tmp_path)

    completed = subprocess.run(
        [
            sys.executable,
            str(REPOSITORY_ROOT / "scripts" / "checkpoint_d_evidence_status.py"),
            "--evidence-root",
            str(root),
            "--pins",
            str(pins_path),
            "--pins-sha256",
            pins_sha,
        ],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    report = json.loads(completed.stdout)

    assert report["verified"] is True
    assert report["status"]["checkpoint_gates"]["C"]["accepted"] is True
    assert report["status"]["checkpoint_gates"]["D"]["accepted"] is False
    assert report["provider_called"] is False
    assert report["money_moved"] is False


def test_status_source_revalidates_files_after_startup(tmp_path):
    root, pins_path, pins_sha = _bundle(tmp_path)
    source = AuthoritativeEvidenceStatusSource(root, pins_path, pins_sha)

    assert source().gates["C"].accepted is True
    target = root / "checkpoint-c.json"
    target.write_bytes(target.read_bytes() + b" ")

    with pytest.raises(AuthoritativeEvidenceError, match="evidence file digest mismatch"):
        source()
