from __future__ import annotations

import hmac
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path

import pytest

from ecocommit.api import ApiRequest, CheckpointDApi
from ecocommit.audit import AppendOnlyAuditLog
from ecocommit.checkpoint_status import SafetyStatus
from ecocommit.execution import PreparedRazorpayTestOperation
from ecocommit.exposure import TransactionBinding
from ecocommit.razorpay import (
    RazorpayOrderResult,
    RazorpayWebhookVerifier,
)
from ecocommit.razorpay_checkout import RazorpayCheckoutCallback, RazorpayCheckoutHandoff
from ecocommit.service import CheckpointDService
from ecocommit.webhook import (
    BoundRazorpayWebhookProcessor,
    SQLiteWebhookEvidenceStore,
    WebhookProcessingError,
)


NOW = datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc)
WEBHOOK_SECRET = "separate-webhook-secret"
ORDER_ID = "order_Webhook123"
PAYMENT_ID = "pay_Webhook123"
REFUND_ID = "rfnd_Webhook123"
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _operation() -> PreparedRazorpayTestOperation:
    transaction = TransactionBinding(
        transaction_id="tx-b8-webhook",
        merchant_id="merchant-b8-webhook",
        amount_minor=100,
        currency="INR",
        contract_hash="a" * 64,
    )
    handoff = RazorpayCheckoutHandoff.create(
        public_key_id="rzp_test_webhook",
        transaction=transaction,
        order=RazorpayOrderResult(
            transaction_id=transaction.transaction_id,
            transaction_digest=transaction.digest(),
            amount_minor=transaction.amount_minor,
            currency=transaction.currency,
            order_id=ORDER_ID,
            receipt="ec_webhook_test",
            provider_status="created",
        ),
        created_at=NOW,
        expires_at=NOW + timedelta(minutes=30),
    )
    return PreparedRazorpayTestOperation.create(
        operation_id="prepared_webhook_123",
        handoff=handoff,
        callback=RazorpayCheckoutCallback(
            razorpay_order_id=ORDER_ID,
            razorpay_payment_id=PAYMENT_ID,
            razorpay_signature="1" * 64,
        ),
    )


def _payment(*, status="captured", **updates):
    value = {
        "id": PAYMENT_ID,
        "entity": "payment",
        "amount": 100,
        "currency": "INR",
        "status": status,
        "order_id": ORDER_ID,
        "captured": status == "captured",
    }
    value.update(updates)
    return value


def _event(event_type: str, **updates) -> bytes:
    payload = {"payment": {"entity": _payment()}}
    if event_type == "refund.processed":
        payload["refund"] = {"entity": {
            "id": REFUND_ID,
            "entity": "refund",
            "amount": 100,
            "currency": "INR",
            "payment_id": PAYMENT_ID,
            "status": "processed",
        }}
    value = {
        "entity": "event",
        "event": event_type,
        "contains": ["payment"] if event_type == "payment.captured" else ["refund", "payment"],
        "payload": payload,
    }
    value.update(updates)
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _signature(raw: bytes) -> str:
    return hmac.new(WEBHOOK_SECRET.encode("utf-8"), raw, sha256).hexdigest()


def _processor(tmp_path, *, clock=None):
    audit = AppendOnlyAuditLog(tmp_path / "webhook-audit.ndjson")
    store = SQLiteWebhookEvidenceStore(tmp_path / "webhooks.sqlite3")
    processor = BoundRazorpayWebhookProcessor(
        _operation(),
        verifier=RazorpayWebhookVerifier(WEBHOOK_SECRET),
        store=store,
        audit_log=audit,
        clock=clock or (lambda: NOW + timedelta(minutes=1)),
    )
    return processor, store, audit


def test_webhooks_are_raw_signature_verified_duplicate_safe_and_digest_bound(tmp_path):
    processor, store, audit = _processor(tmp_path)
    captured = _event("payment.captured")
    refund = _event("refund.processed")

    first = processor.ingest(
        raw_body=captured,
        signature=_signature(captured),
        event_id="event-captured-1",
    )
    duplicate = processor.ingest(
        raw_body=captured,
        signature=_signature(captured),
        event_id="event-captured-1",
    )
    second = processor.ingest(
        raw_body=refund,
        signature=_signature(refund),
        event_id="event-refund-1",
    )
    verified = store.verified_set("tx-b8-webhook")

    assert first.duplicate is False
    assert duplicate.duplicate is True
    assert second.event_type == "refund.processed"
    assert verified.captured.payment_id == PAYMENT_ID
    assert verified.refund_processed.refund_id == REFUND_ID
    assert verified.set_sha256
    assert len(audit.events()) == 3
    assert WEBHOOK_SECRET not in audit.path.read_text(encoding="utf-8")
    assert captured.decode("utf-8") not in audit.path.read_text(encoding="utf-8")


def test_webhook_redelivery_retains_first_receipt_time_and_digest(tmp_path):
    observed_now = [NOW + timedelta(minutes=1)]
    processor, store, _ = _processor(tmp_path, clock=lambda: observed_now[0])
    captured = _event("payment.captured")

    first = processor.ingest(
        raw_body=captured,
        signature=_signature(captured),
        event_id="event-redelivered-later",
    )
    observed_now[0] = NOW + timedelta(minutes=12)
    duplicate = processor.ingest(
        raw_body=captured,
        signature=_signature(captured),
        event_id="event-redelivered-later",
    )

    retained = store.records("tx-b8-webhook")
    assert duplicate.duplicate is True
    assert duplicate.record_sha256 == first.record_sha256
    assert len(retained) == 1
    assert retained[0].received_at_utc == NOW + timedelta(minutes=1)


def test_refund_and_capture_webhooks_may_arrive_out_of_order(tmp_path):
    processor, store, _ = _processor(tmp_path)
    refund = _event("refund.processed")
    capture = _event("payment.captured")

    processor.ingest(
        raw_body=refund,
        signature=_signature(refund),
        event_id="event-refund-first",
    )
    processor.ingest(
        raw_body=capture,
        signature=_signature(capture),
        event_id="event-capture-second",
    )

    assert store.verified_set("tx-b8-webhook").out_of_order_safe is True


def test_webhook_signature_binding_and_event_id_collisions_fail_closed(tmp_path):
    processor, store, audit = _processor(tmp_path)
    capture = _event("payment.captured")

    with pytest.raises(WebhookProcessingError) as bad_signature:
        processor.ingest(
            raw_body=capture,
            signature="0" * 64,
            event_id="event-bad-signature",
        )
    assert bad_signature.value.status_code == 401
    assert store.records("tx-b8-webhook") == ()

    wrong_payment = json.loads(capture)
    wrong_payment["payload"]["payment"]["entity"]["id"] = "pay_Other123"
    wrong_raw = json.dumps(
        wrong_payment,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    with pytest.raises(WebhookProcessingError) as bad_binding:
        processor.ingest(
            raw_body=wrong_raw,
            signature=_signature(wrong_raw),
            event_id="event-wrong-binding",
        )
    assert bad_binding.value.status_code == 400

    processor.ingest(
        raw_body=capture,
        signature=_signature(capture),
        event_id="event-collision",
    )
    changed = _event("payment.captured", account_id="acc_changed")
    with pytest.raises(WebhookProcessingError) as collision:
        processor.ingest(
            raw_body=changed,
            signature=_signature(changed),
            event_id="event-collision",
        )
    assert collision.value.code == "WEBHOOK_EVENT_ID_COLLISION"
    assert len(audit.events()) == 1


def test_api_preserves_raw_body_for_webhook_hmac_and_returns_redacted_ack(tmp_path):
    processor, _, audit = _processor(tmp_path)
    api = CheckpointDApi(
        CheckpointDService(SafetyStatus(), audit),
        webhook_processor=processor,
    )
    capture = _event("payment.captured")
    response = api.handle(ApiRequest(
        "POST",
        "/v1/razorpay/webhook",
        {
            "Content-Type": "application/json",
            "X-Razorpay-Signature": _signature(capture),
            "X-Razorpay-Event-Id": "event-api-capture",
        },
        capture,
    ))
    missing_signature = api.handle(ApiRequest(
        "POST",
        "/v1/razorpay/webhook",
        {"Content-Type": "application/json"},
        capture,
    ))

    assert response.status_code == 200
    assert response.body["outcome"] == "WEBHOOK_ACCEPTED"
    assert response.body["accepted"] is True
    assert response.body["real_money_moved"] is False
    assert "payload" not in response.body
    assert (missing_signature.status_code, missing_signature.body["reason"]) == (
        401,
        "WEBHOOK_SIGNATURE_OR_BODY_INVALID",
    )


def test_signed_duplicate_json_keys_are_rejected_before_binding(tmp_path):
    processor, store, _ = _processor(tmp_path)
    raw = b'{"entity":"event","entity":"event","event":"payment.captured","payload":{}}'

    with pytest.raises(WebhookProcessingError) as caught:
        processor.ingest(
            raw_body=raw,
            signature=_signature(raw),
            event_id="event-duplicate-json",
        )

    assert caught.value.status_code == 401
    assert store.records("tx-b8-webhook") == ()


def test_webhook_evidence_cli_exports_only_verified_digest_bound_set(tmp_path):
    processor, _, _ = _processor(tmp_path)
    for event_id, event_type in (
        ("event-export-capture", "payment.captured"),
        ("event-export-refund", "refund.processed"),
    ):
        raw = _event(event_type)
        processor.ingest(
            raw_body=raw,
            signature=_signature(raw),
            event_id=event_id,
        )
    output = tmp_path / "verified-webhooks.json"

    completed = subprocess.run(
        [
            sys.executable,
            str(REPOSITORY_ROOT / "scripts" / "checkpoint_b8_webhook_evidence.py"),
            "--state-db",
            str(tmp_path / "webhooks.sqlite3"),
            "--transaction-id",
            "tx-b8-webhook",
            "--output",
            str(output),
        ],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    report = json.loads(completed.stdout)
    evidence = json.loads(output.read_text(encoding="utf-8"))

    assert report["verified"] is True
    assert report["raw_webhook_bodies_retained"] is False
    assert evidence["set_sha256"] == report["webhook_set_sha256"]
    assert WEBHOOK_SECRET not in completed.stdout
    assert WEBHOOK_SECRET not in output.read_text(encoding="utf-8")
