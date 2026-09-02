from __future__ import annotations

import importlib.util
import json
import sys
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path

import pytest

from ecocommit.audit import AppendOnlyAuditLog
from ecocommit.checkpoint_a_evidence import (
    FROZEN_A_DATASET_SHA256,
    CheckpointAEvidenceReceipt,
    CheckpointAMetrics,
)
from ecocommit.checkpoint_b_evidence import CheckpointBEvidenceReceipt
from ecocommit.exposure import TransactionBinding
from ecocommit.github_actions import verify_razorpay_preflight_run
from ecocommit.razorpay import RazorpayOrderResult
from ecocommit.razorpay_checkout import (
    RazorpayCheckoutHandoff,
    RazorpayLifecycleEvidence,
)
from ecocommit.webhook import (
    RazorpayWebhookRecord,
    VerifiedRazorpayWebhookSet,
)


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "checkpoint_b8_finalize.py"
SPEC = importlib.util.spec_from_file_location("checkpoint_b8_finalize", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
FINALIZER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = FINALIZER
SPEC.loader.exec_module(FINALIZER)

REVISION = "a" * 40
REPOSITORY = "sasipriya1221/sasipriya1221-ECOCOMMIT"
PREFLIGHT_RUN_ID = 33535533432
ORDER_RUN_ID = 33535533557
FINALIZATION_RUN_ID = 33535533999
NOW = datetime(2026, 9, 2, 12, 0, tzinfo=UTC)
ORDER_ID = "order_B8Final123"
PAYMENT_ID = "pay_B8Final123"
REFUND_ID = "rfnd_B8Final123"
PUBLIC_KEY_ID = "rzp_test_B8Key"
PROVIDER_ACCOUNT_BINDING_SHA256 = sha256(PUBLIC_KEY_ID.encode("utf-8")).hexdigest()
MANUAL_CAPTURE_SCREENSHOT_SHA256 = "9" * 64
WEBHOOK_CONFIGURATION_SCREENSHOT_SHA256 = "c" * 64
WEBHOOK_ENDPOINT_SHA256 = "d" * 64
VERIFIER_IDENTITY_SHA256 = "e" * 64


def _write_json(path: Path, value) -> bytes:
    payload = value.model_dump(mode="json") if hasattr(value, "model_dump") else value
    raw = (
        json.dumps(
            payload,
            sort_keys=True,
            indent=2,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return raw


def _transaction() -> TransactionBinding:
    return TransactionBinding(
        transaction_id=f"tx-b8-{ORDER_RUN_ID}-1",
        merchant_id="razorpay-test-mode-boundary",
        amount_minor=100,
        currency="INR",
        contract_hash="b" * 64,
    )


def _preflight_receipt():
    return verify_razorpay_preflight_run(
        {
            "id": PREFLIGHT_RUN_ID,
            "run_attempt": 1,
            "event": "workflow_dispatch",
            "status": "completed",
            "conclusion": "success",
            "head_sha": REVISION,
            "path": ".github/workflows/razorpay-test-preflight.yml@main",
            "repository": {"full_name": REPOSITORY},
            "head_repository": {"full_name": REPOSITORY},
        },
        repository=REPOSITORY,
        run_id=PREFLIGHT_RUN_ID,
        expected_sha=REVISION,
    )


def _a_receipt() -> CheckpointAEvidenceReceipt:
    return CheckpointAEvidenceReceipt(
        verification_mode="FROZEN_AGGREGATE",
        evidence_reference="github://run/400/artifact/checkpoint-a",
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


def _webhook_record(event_type: str, *, received_at: datetime):
    transaction = _transaction()
    return RazorpayWebhookRecord.create(
        event_id=(
            "evt_b8_capture_final"
            if event_type == "payment.captured"
            else "evt_b8_refund_final"
        ),
        event_type=event_type,
        received_at_utc=received_at,
        raw_body_sha256=("3" if event_type == "payment.captured" else "4") * 64,
        transaction_id=transaction.transaction_id,
        transaction_digest=transaction.digest(),
        order_id=ORDER_ID,
        payment_id=PAYMENT_ID,
        refund_id=None if event_type == "payment.captured" else REFUND_ID,
        amount_minor=100,
        currency="INR",
    )


def _bundle(tmp_path: Path):
    transaction = _transaction()
    provider_order = RazorpayOrderResult(
        transaction_id=transaction.transaction_id,
        transaction_digest=transaction.digest(),
        amount_minor=100,
        currency="INR",
        order_id=ORDER_ID,
        receipt="ec_b8_final_receipt",
        provider_status="created",
    )
    handoff = RazorpayCheckoutHandoff.create(
        public_key_id=PUBLIC_KEY_ID,
        transaction=transaction,
        order=provider_order,
        created_at=NOW,
        expires_at=NOW + timedelta(hours=24),
    )
    preflight = _preflight_receipt()
    order_evidence = {
        "schema_version": "B8.1",
        "checkpoint": "B8_RAZORPAY_TEST_MODE",
        "generated_at": NOW.isoformat(),
        "provider": "RAZORPAY",
        "provider_mode": "TEST",
        "credentials": {
            "injected_from_environment": True,
            "test_prefix_validated": True,
            "key_id_retained": False,
            "key_secret_retained": False,
        },
        "github": {
            "run_id": str(ORDER_RUN_ID),
            "run_attempt": "1",
            "sha": REVISION,
            "ref_name": "main",
            "credential_preflight_run_id": str(PREFLIGHT_RUN_ID),
        },
        "authentication": {
            "credential_preflight_run_reference_present": True,
            "credential_preflight_run_verified": True,
            "preflight_response_body_retained": False,
            "credentialed_order_api_succeeded": True,
            "preflight_verification_source": "GITHUB_ACTIONS_API",
            "preflight_reference_receipt_sha256": preflight["receipt_sha256"],
            "preflight_source_revision": REVISION,
        },
        "provider_calls": [
            {"method": "GET", "path": "/orders?receipt=ec_b8_final_receipt&count=100"},
            {"method": "POST", "path": "/orders"},
            {"method": "GET", "path": f"/orders/{ORDER_ID}"},
            {"method": "GET", "path": f"/orders/{ORDER_ID}"},
            {"method": "GET", "path": f"/orders/{ORDER_ID}/payments"},
        ],
        "transaction": {
            "transaction_id": transaction.transaction_id,
            "transaction_digest": transaction.digest(),
            "merchant_id": transaction.merchant_id,
            "amount_minor": transaction.amount_minor,
            "currency": transaction.currency,
            "contract_hash": transaction.contract_hash,
        },
        "order": {
            "executed": True,
            "order_id": provider_order.order_id,
            "receipt": provider_order.receipt,
            "provider_status": provider_order.provider_status,
            "amount_minor": provider_order.amount_minor,
            "currency": provider_order.currency,
            "transaction_digest": provider_order.transaction_digest,
            "provider_response_recovered": provider_order.recovered,
        },
        "checkout_handoff": {
            "generated": True,
            "schema_version": handoff.schema_version,
            "handoff_sha256": handoff.handoff_sha256,
            "expires_at": handoff.expires_at.isoformat(),
            "public_key_id_retained_only_in_handoff": True,
            "secret_key_retained": False,
        },
        "idempotency": {
            "validated": True,
            "identical_replay_returned_same_order": True,
            "provider_create_order_post_count": 1,
            "idempotency_key_retained": False,
        },
        "payments_for_order": {
            "executed": True,
            "count": 0,
            "payment_ids": [],
            "statuses": [],
        },
        "authorization": {"executed": False, "reason": "Checkout callback required"},
        "capture": {"executed": False, "reason": "No authorized payment"},
        "refund": {"executed": False, "reason": "No captured payment"},
        "settlement": {"executed": False, "reason": "Test order is not settlement"},
        "checkpoint_b8_passed": False,
        "status": "ORDER_API_VALIDATED_PAYMENT_LIFECYCLE_BLOCKED",
        "external_blocker": {
            "code": "RAZORPAY_CHECKOUT_AUTHORIZATION_REQUIRED",
            "boundary": "RAZORPAY_PRODUCT_API",
            "detail": "A genuine Test Checkout callback is required.",
        },
    }
    lifecycle = RazorpayLifecycleEvidence(
        handoff_sha256=handoff.handoff_sha256,
        transaction_digest=transaction.digest(),
        order_id=ORDER_ID,
        payment_id=PAYMENT_ID,
        refund_id=REFUND_ID,
        reserve_state="RESERVED",
        capture_state="CAPTURED",
        refund_state="REFUNDED",
        commitment_stage="COMPENSATED",
        reconciliation_in_sync=True,
        checkpoint_b8_lifecycle_passed=True,
        durable_state_backend="SQLITE_WAL_FULL_SYNC",
    )
    captured = _webhook_record("payment.captured", received_at=NOW + timedelta(minutes=1))
    refunded = _webhook_record("refund.processed", received_at=NOW + timedelta(minutes=2))
    webhooks = VerifiedRazorpayWebhookSet.create(
        transaction_id=transaction.transaction_id,
        transaction_digest=transaction.digest(),
        captured=captured,
        refund_processed=refunded,
    )

    paths = {
        "preflight_path": tmp_path / "preflight.json",
        "order_evidence_path": tmp_path / "order.json",
        "handoff_path": tmp_path / "handoff.json",
        "lifecycle_path": tmp_path / "lifecycle.json",
        "webhook_evidence_path": tmp_path / "webhooks.json",
        "checkpoint_a_receipt_path": tmp_path / "checkpoint-a.json",
        "deterministic_safety_manifest_path": tmp_path / "safety.json",
        "durability_manifest_path": tmp_path / "durability.json",
        "certificate_key_reference_path": tmp_path / "certificate-key.json",
        "manual_capture_attestation_path": tmp_path / "manual-capture.json",
        "webhook_configuration_attestation_path": (
            tmp_path / "webhook-configuration.json"
        ),
        "audit_path": tmp_path / "audit.ndjson",
        "evidence_reference": (
            f"github-actions://{REPOSITORY}/runs/{FINALIZATION_RUN_ID}/artifacts/"
            f"checkpoint-b8-final-{FINALIZATION_RUN_ID}"
        ),
        "provider_manifest_output": tmp_path / "provider-manifest.json",
        "receipt_output": tmp_path / "checkpoint-b.json",
    }
    _write_json(paths["preflight_path"], preflight)
    _write_json(paths["order_evidence_path"], order_evidence)
    _write_json(paths["handoff_path"], handoff)
    _write_json(paths["lifecycle_path"], lifecycle)
    _write_json(paths["webhook_evidence_path"], webhooks)
    _write_json(paths["checkpoint_a_receipt_path"], _a_receipt())
    _write_json(paths["deterministic_safety_manifest_path"], {
        "schema_version": "B8.DETERMINISTIC_SAFETY.1",
        "source_revision": REVISION,
        "collected_tests": 115,
        "passed_tests": 115,
        "failed_tests": 0,
        "error_tests": 0,
        "covered_groups": sorted(FINALIZER.REQUIRED_SAFETY_GROUPS),
        "report_sha256": "5" * 64,
    })
    _write_json(paths["durability_manifest_path"], {
        "schema_version": "B8.DURABILITY_TESTS.1",
        "source_revision": REVISION,
        "state_store_backend": "SQLITE_WAL_FULL_SYNC",
        "completed_scenarios": sorted(FINALIZER.REQUIRED_DURABILITY_SCENARIOS),
        "failed_scenarios": [],
        "report_sha256": "6" * 64,
    })
    _write_json(paths["certificate_key_reference_path"], {
        "schema_version": "B8.CERTIFICATE_KEY_REFERENCE.1",
        "source_revision": REVISION,
        "boundary": "ENVIRONMENT_ONLY_HMAC_TEST_BOUNDARY",
        "key_reference_sha256": "7" * 64,
        "minimum_secret_bytes": 32,
        "retained_material_fields": [],
    })
    _write_json(paths["manual_capture_attestation_path"], {
        "schema_version": "B8.MANUAL_CAPTURE_CONFIGURATION.1",
        "source_revision": REVISION,
        "provider_account_binding_sha256": PROVIDER_ACCOUNT_BINDING_SHA256,
        "provider_mode": "TEST",
        "capture_mode": "MANUAL",
        "manual_capture_timeout_seconds": 259200,
        "capture_timeout_action": "NORMAL_REFUND",
        "observed_at_utc": (NOW - timedelta(minutes=5)).isoformat(),
        "observation_artifact_kind": "RAZORPAY_TEST_DASHBOARD_SCREENSHOT",
        "observation_artifact_sha256": MANUAL_CAPTURE_SCREENSHOT_SHA256,
        "verifier_identity_sha256": VERIFIER_IDENTITY_SHA256,
        "verification_reference_sha256": "f" * 64,
    })
    _write_json(paths["webhook_configuration_attestation_path"], {
        "schema_version": "B8.WEBHOOK_CONFIGURATION.1",
        "source_revision": REVISION,
        "provider_account_binding_sha256": PROVIDER_ACCOUNT_BINDING_SHA256,
        "provider_mode": "TEST",
        "endpoint_scheme": "HTTPS",
        "endpoint_sha256": WEBHOOK_ENDPOINT_SHA256,
        "enabled_state": "ENABLED",
        "enabled_events": ["payment.captured", "refund.processed"],
        "observed_at_utc": (NOW - timedelta(minutes=4)).isoformat(),
        "observation_artifact_kind": "RAZORPAY_TEST_DASHBOARD_SCREENSHOT",
        "observation_artifact_sha256": WEBHOOK_CONFIGURATION_SCREENSHOT_SHA256,
        "verifier_identity_sha256": VERIFIER_IDENTITY_SHA256,
        "verification_reference_sha256": "0" * 64,
    })

    audit = AppendOnlyAuditLog(paths["audit_path"])
    for record in (captured, refunded):
        audit.append(
            "razorpay.webhook.verified",
            f"audit-{record.event_type}",
            {
                "record_sha256": record.record_sha256,
                "signature_verified": True,
                "binding_verified": True,
            },
        )
    return paths


def test_finalizer_derives_cross_linked_receipt_without_pass_inputs(tmp_path):
    paths = _bundle(tmp_path)

    receipt = FINALIZER.finalize_b8(**paths, generated_at=NOW + timedelta(minutes=3))

    retained = CheckpointBEvidenceReceipt.model_validate(
        json.loads(paths["receipt_output"].read_text(encoding="utf-8"))
    )
    provider_manifest = json.loads(
        paths["provider_manifest_output"].read_text(encoding="utf-8")
    )
    lifecycle_raw = paths["lifecycle_path"].read_bytes()
    a_raw = paths["checkpoint_a_receipt_path"].read_bytes()

    assert receipt == retained
    assert retained.source_revision == REVISION
    assert retained.evidence_reference == paths["evidence_reference"]
    assert retained.lifecycle.order_id == ORDER_ID
    assert retained.lifecycle.payment_id == PAYMENT_ID
    assert retained.lifecycle.refund_id == REFUND_ID
    assert retained.lifecycle.amount_minor == 100
    assert retained.lifecycle.currency == "INR"
    assert retained.lifecycle.checkout_lifecycle_result_sha256 == sha256(
        lifecycle_raw
    ).hexdigest()
    assert retained.checkpoint_a_receipt_sha256 == sha256(a_raw).hexdigest()
    assert retained.provider_evidence_artifact_sha256 == sha256(
        paths["provider_manifest_output"].read_bytes()
    ).hexdigest()
    assert provider_manifest["transaction_digest"] == _transaction().digest()
    assert provider_manifest["evidence_reference"] == paths["evidence_reference"]
    assert provider_manifest["retention_run_id"] == FINALIZATION_RUN_ID
    assert provider_manifest["artifact_file_sha256"]["webhook_evidence"] == sha256(
        paths["webhook_evidence_path"].read_bytes()
    ).hexdigest()
    external_configuration = provider_manifest["external_configuration"]
    assert (
        external_configuration["provider_account_binding_sha256"]
        == PROVIDER_ACCOUNT_BINDING_SHA256
    )
    assert external_configuration["manual_capture"] == {
        "capture_mode": "MANUAL",
        "manual_capture_timeout_seconds": 259200,
        "capture_timeout_action": "NORMAL_REFUND",
        "observation_artifact_kind": "RAZORPAY_TEST_DASHBOARD_SCREENSHOT",
        "observation_artifact_sha256": MANUAL_CAPTURE_SCREENSHOT_SHA256,
        "observed_at_utc": (NOW - timedelta(minutes=5)).isoformat(),
        "provider_mode": "TEST",
        "source_revision": REVISION,
        "verification_reference_sha256": "f" * 64,
        "verifier_identity_sha256": VERIFIER_IDENTITY_SHA256,
    }
    assert external_configuration["webhook"]["endpoint_scheme"] == "HTTPS"
    assert external_configuration["webhook"]["endpoint_sha256"] == (
        WEBHOOK_ENDPOINT_SHA256
    )
    assert external_configuration["webhook"]["enabled_events"] == [
        "payment.captured",
        "refund.processed",
    ]
    assert provider_manifest["artifact_file_sha256"][
        "manual_capture_configuration_attestation"
    ] == sha256(paths["manual_capture_attestation_path"].read_bytes()).hexdigest()
    assert provider_manifest["artifact_file_sha256"][
        "webhook_configuration_attestation"
    ] == sha256(
        paths["webhook_configuration_attestation_path"].read_bytes()
    ).hexdigest()
    assert retained.gate_passed is True
    assert retained.provider_test_mode is True
    assert retained.real_money_moved is False


def test_finalizer_rejects_cross_artifact_payment_mismatch_before_writing(tmp_path):
    paths = _bundle(tmp_path)
    lifecycle = json.loads(paths["lifecycle_path"].read_text(encoding="utf-8"))
    lifecycle["payment_id"] = "pay_AnotherValid123"
    _write_json(paths["lifecycle_path"], lifecycle)

    with pytest.raises(FINALIZER.B8FinalizationError, match="webhook set"):
        FINALIZER.finalize_b8(**paths, generated_at=NOW)

    assert not paths["provider_manifest_output"].exists()
    assert not paths["receipt_output"].exists()


def test_finalizer_rejects_incomplete_test_counts_without_pass_boolean(tmp_path):
    paths = _bundle(tmp_path)
    safety = json.loads(
        paths["deterministic_safety_manifest_path"].read_text(encoding="utf-8")
    )
    safety["passed_tests"] -= 1
    safety["failed_tests"] = 1
    _write_json(paths["deterministic_safety_manifest_path"], safety)

    with pytest.raises(FINALIZER.B8FinalizationError, match="safety manifest"):
        FINALIZER.finalize_b8(**paths, generated_at=NOW)

    assert not paths["provider_manifest_output"].exists()
    assert not paths["receipt_output"].exists()


def test_finalizer_rejects_duplicate_json_keys_before_writing(tmp_path):
    paths = _bundle(tmp_path)
    raw = paths["order_evidence_path"].read_bytes()
    paths["order_evidence_path"].write_bytes(
        raw.rstrip()[:-1] + b',"status":"ORDER_API_VALIDATED_PAYMENT_LIFECYCLE_BLOCKED"}'
    )

    with pytest.raises(FINALIZER.B8FinalizationError, match="strict UTF-8 JSON"):
        FINALIZER.finalize_b8(**paths, generated_at=NOW)

    assert not paths["provider_manifest_output"].exists()
    assert not paths["receipt_output"].exists()


def test_finalizer_requires_manual_capture_dashboard_attestation(tmp_path):
    paths = _bundle(tmp_path)
    paths["manual_capture_attestation_path"] = tmp_path / "missing-manual.json"

    with pytest.raises(
        FINALIZER.B8FinalizationError,
        match="manual-capture configuration attestation is unavailable",
    ):
        FINALIZER.finalize_b8(**paths, generated_at=NOW + timedelta(minutes=3))

    assert not paths["provider_manifest_output"].exists()
    assert not paths["receipt_output"].exists()


def test_finalizer_requires_webhook_dashboard_attestation(tmp_path):
    paths = _bundle(tmp_path)
    paths["webhook_configuration_attestation_path"] = (
        tmp_path / "missing-webhook-configuration.json"
    )

    with pytest.raises(
        FINALIZER.B8FinalizationError,
        match="webhook configuration attestation is unavailable",
    ):
        FINALIZER.finalize_b8(**paths, generated_at=NOW + timedelta(minutes=3))

    assert not paths["provider_manifest_output"].exists()
    assert not paths["receipt_output"].exists()


def test_finalizer_rejects_dashboard_attestation_for_another_revision(tmp_path):
    paths = _bundle(tmp_path)
    manual = json.loads(
        paths["manual_capture_attestation_path"].read_text(encoding="utf-8")
    )
    manual["source_revision"] = "b" * 40
    _write_json(paths["manual_capture_attestation_path"], manual)

    with pytest.raises(
        FINALIZER.B8FinalizationError,
        match="manual-capture configuration attestation source revision",
    ):
        FINALIZER.finalize_b8(**paths, generated_at=NOW + timedelta(minutes=3))

    assert not paths["provider_manifest_output"].exists()
    assert not paths["receipt_output"].exists()


def test_finalizer_rejects_dashboard_attestations_for_different_accounts(tmp_path):
    paths = _bundle(tmp_path)
    webhook = json.loads(
        paths["webhook_configuration_attestation_path"].read_text(encoding="utf-8")
    )
    webhook["provider_account_binding_sha256"] = "1" * 64
    _write_json(paths["webhook_configuration_attestation_path"], webhook)

    with pytest.raises(
        FINALIZER.B8FinalizationError,
        match="bind different provider accounts",
    ):
        FINALIZER.finalize_b8(**paths, generated_at=NOW + timedelta(minutes=3))

    assert not paths["provider_manifest_output"].exists()
    assert not paths["receipt_output"].exists()


def test_finalizer_rejects_matching_attestations_for_another_test_account(tmp_path):
    paths = _bundle(tmp_path)
    for key in (
        "manual_capture_attestation_path",
        "webhook_configuration_attestation_path",
    ):
        attestation = json.loads(paths[key].read_text(encoding="utf-8"))
        attestation["provider_account_binding_sha256"] = "1" * 64
        _write_json(paths[key], attestation)

    with pytest.raises(
        FINALIZER.B8FinalizationError,
        match="does not match the Checkout Test account",
    ):
        FINALIZER.finalize_b8(**paths, generated_at=NOW + timedelta(minutes=3))

    assert not paths["provider_manifest_output"].exists()
    assert not paths["receipt_output"].exists()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("provider_mode", "LIVE"),
        ("capture_mode", "AUTO"),
        ("manual_capture_timeout_seconds", 0),
        ("manual_capture_timeout_seconds", 86400),
        ("capture_timeout_action", "AUTO_REFUND"),
    ],
)
def test_finalizer_rejects_invalid_manual_capture_configuration(
    tmp_path,
    field,
    value,
):
    paths = _bundle(tmp_path)
    manual = json.loads(
        paths["manual_capture_attestation_path"].read_text(encoding="utf-8")
    )
    manual[field] = value
    _write_json(paths["manual_capture_attestation_path"], manual)

    with pytest.raises(
        FINALIZER.B8FinalizationError,
        match="manual-capture configuration attestation schema or digest is invalid",
    ):
        FINALIZER.finalize_b8(**paths, generated_at=NOW + timedelta(minutes=3))

    assert not paths["provider_manifest_output"].exists()
    assert not paths["receipt_output"].exists()


@pytest.mark.parametrize(
    "enabled_events",
    [
        ["payment.captured"],
        ["payment.captured", "refund.processed", "payment.captured"],
        ["refund.processed", "payment.captured"],
    ],
)
def test_finalizer_rejects_inexact_dashboard_webhook_events(
    tmp_path,
    enabled_events,
):
    paths = _bundle(tmp_path)
    webhook = json.loads(
        paths["webhook_configuration_attestation_path"].read_text(encoding="utf-8")
    )
    webhook["enabled_events"] = enabled_events
    _write_json(paths["webhook_configuration_attestation_path"], webhook)

    with pytest.raises(
        FINALIZER.B8FinalizationError,
        match="webhook configuration attestation schema or digest is invalid",
    ):
        FINALIZER.finalize_b8(**paths, generated_at=NOW + timedelta(minutes=3))

    assert not paths["provider_manifest_output"].exists()
    assert not paths["receipt_output"].exists()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("provider_mode", "LIVE"),
        ("endpoint_scheme", "HTTP"),
        ("enabled_state", "DISABLED"),
    ],
)
def test_finalizer_rejects_insecure_or_inactive_webhook_configuration(
    tmp_path,
    field,
    value,
):
    paths = _bundle(tmp_path)
    webhook = json.loads(
        paths["webhook_configuration_attestation_path"].read_text(encoding="utf-8")
    )
    webhook[field] = value
    _write_json(paths["webhook_configuration_attestation_path"], webhook)

    with pytest.raises(
        FINALIZER.B8FinalizationError,
        match="webhook configuration attestation schema or digest is invalid",
    ):
        FINALIZER.finalize_b8(**paths, generated_at=NOW + timedelta(minutes=3))

    assert not paths["provider_manifest_output"].exists()
    assert not paths["receipt_output"].exists()


def test_finalizer_rejects_raw_or_secret_bearing_webhook_url_field(tmp_path):
    paths = _bundle(tmp_path)
    webhook = json.loads(
        paths["webhook_configuration_attestation_path"].read_text(encoding="utf-8")
    )
    webhook["endpoint_url"] = (
        "https://example.test/v1/razorpay/webhook?credential=must-not-be-retained"
    )
    _write_json(paths["webhook_configuration_attestation_path"], webhook)

    with pytest.raises(
        FINALIZER.B8FinalizationError,
        match="webhook configuration attestation schema or digest is invalid",
    ):
        FINALIZER.finalize_b8(**paths, generated_at=NOW + timedelta(minutes=3))

    assert not paths["provider_manifest_output"].exists()
    assert not paths["receipt_output"].exists()


def test_finalizer_rejects_webhook_configuration_observed_after_delivery(tmp_path):
    paths = _bundle(tmp_path)
    webhook = json.loads(
        paths["webhook_configuration_attestation_path"].read_text(encoding="utf-8")
    )
    webhook["observed_at_utc"] = (NOW + timedelta(minutes=2)).isoformat()
    _write_json(paths["webhook_configuration_attestation_path"], webhook)

    with pytest.raises(
        FINALIZER.B8FinalizationError,
        match="was not observed before webhook delivery",
    ):
        FINALIZER.finalize_b8(**paths, generated_at=NOW + timedelta(minutes=3))

    assert not paths["provider_manifest_output"].exists()
    assert not paths["receipt_output"].exists()


def test_finalizer_rejects_manual_capture_observed_after_capture(tmp_path):
    paths = _bundle(tmp_path)
    manual = json.loads(
        paths["manual_capture_attestation_path"].read_text(encoding="utf-8")
    )
    manual["observed_at_utc"] = (NOW + timedelta(minutes=2)).isoformat()
    _write_json(paths["manual_capture_attestation_path"], manual)

    with pytest.raises(
        FINALIZER.B8FinalizationError,
        match="was not observed before capture",
    ):
        FINALIZER.finalize_b8(**paths, generated_at=NOW + timedelta(minutes=3))

    assert not paths["provider_manifest_output"].exists()
    assert not paths["receipt_output"].exists()


def test_finalizer_rejects_false_retention_reference_and_handoff_expiry(tmp_path):
    paths = _bundle(tmp_path)
    paths["evidence_reference"] = (
        "github-actions://different-owner/different-repo/runs/1/artifacts/b8"
    )
    with pytest.raises(FINALIZER.B8FinalizationError, match="same repository"):
        FINALIZER.finalize_b8(**paths, generated_at=NOW + timedelta(minutes=3))

    paths = _bundle(tmp_path / "expiry")
    order = json.loads(paths["order_evidence_path"].read_text(encoding="utf-8"))
    order["checkout_handoff"]["expires_at"] = (
        NOW + timedelta(hours=23)
    ).isoformat()
    _write_json(paths["order_evidence_path"], order)
    with pytest.raises(FINALIZER.B8FinalizationError, match="expiry does not match"):
        FINALIZER.finalize_b8(**paths, generated_at=NOW + timedelta(minutes=3))


def test_finalizer_recovers_exactly_after_interrupted_two_file_publication(
    tmp_path,
    monkeypatch,
):
    paths = _bundle(tmp_path)
    generated_at = NOW + timedelta(minutes=3)
    write_or_verify = FINALIZER._write_or_verify

    def interrupt_receipt(path, raw, label):
        if label == "Checkpoint B receipt output":
            raise FINALIZER.B8FinalizationError("simulated publication interruption")
        return write_or_verify(path, raw, label)

    monkeypatch.setattr(FINALIZER, "_write_or_verify", interrupt_receipt)
    with pytest.raises(FINALIZER.B8FinalizationError, match="interruption"):
        FINALIZER.finalize_b8(**paths, generated_at=generated_at)
    assert paths["provider_manifest_output"].exists()
    assert not paths["receipt_output"].exists()

    monkeypatch.setattr(FINALIZER, "_write_or_verify", write_or_verify)
    recovered = FINALIZER.finalize_b8(**paths, generated_at=generated_at)
    replayed = FINALIZER.finalize_b8(**paths, generated_at=generated_at)

    assert recovered == replayed
    assert CheckpointBEvidenceReceipt.model_validate_json(
        paths["receipt_output"].read_text(encoding="utf-8")
    ) == recovered
