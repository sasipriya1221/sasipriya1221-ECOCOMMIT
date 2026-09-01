from __future__ import annotations

import hmac
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256

import pytest
from pydantic import ValidationError

from ecocommit._canonical import sha256_hex
from ecocommit.exposure import TransactionBinding
from ecocommit.razorpay import (
    RazorpayOrderResult,
    RazorpayTestCredentials,
    RazorpayTestPaymentAdapter,
)
from ecocommit.razorpay_checkout import (
    RazorpayCheckoutCallback,
    RazorpayCheckoutHandoff,
    complete_test_lifecycle,
    render_checkout_html,
)


NOW = datetime(2026, 9, 1, 18, 0, tzinfo=timezone.utc)
KEY_ID = "rzp_test_x"
KEY_SECRET = "checkout-secret-not-for-output"
ORDER_ID = "order_Checkout123"
PAYMENT_ID = "pay_Checkout123"
REFUND_ID = "rfnd_Checkout123"


class FakeTransport:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, path, *, payload=None, headers=None):
        self.calls.append({"method": method, "path": path, "payload": payload, "headers": headers})
        if not self.responses:
            raise AssertionError(f"unexpected provider call: {method} {path}")
        return deepcopy(self.responses.pop(0))


def _transaction() -> TransactionBinding:
    return TransactionBinding(
        transaction_id="tx-b8-checkout",
        merchant_id="merchant-b8-checkout",
        amount_minor=100,
        currency="INR",
        contract_hash="a" * 64,
    )


def _notes(transaction: TransactionBinding) -> dict[str, str]:
    return {
        "ecocommit_transaction_digest": transaction.digest(),
        "ecocommit_contract_hash": transaction.contract_hash,
        "ecocommit_merchant_digest": sha256_hex(transaction.merchant_id),
    }


def _order_entity(transaction: TransactionBinding) -> dict:
    return {
        "id": ORDER_ID,
        "entity": "order",
        "amount": transaction.amount_minor,
        "currency": transaction.currency,
        "receipt": "ec_order_checkout",
        "status": "attempted",
        "notes": _notes(transaction),
    }


def _payment_entity(transaction: TransactionBinding, status: str) -> dict:
    return {
        "id": PAYMENT_ID,
        "entity": "payment",
        "order_id": ORDER_ID,
        "amount": transaction.amount_minor,
        "currency": transaction.currency,
        "status": status,
        "captured": status == "captured",
        "amount_captured": transaction.amount_minor if status == "captured" else 0,
        "amount_refunded": 0,
    }


def _handoff() -> RazorpayCheckoutHandoff:
    transaction = _transaction()
    order = RazorpayOrderResult(
        transaction_id=transaction.transaction_id,
        transaction_digest=transaction.digest(),
        amount_minor=transaction.amount_minor,
        currency=transaction.currency,
        order_id=ORDER_ID,
        receipt="ec_order_checkout",
        provider_status="created",
    )
    return RazorpayCheckoutHandoff.create(
        public_key_id=KEY_ID,
        transaction=transaction,
        order=order,
        created_at=NOW,
        expires_at=NOW + timedelta(minutes=30),
    )


def _callback(order_id: str = ORDER_ID) -> RazorpayCheckoutCallback:
    signature = hmac.new(
        KEY_SECRET.encode(),
        f"{order_id}|{PAYMENT_ID}".encode(),
        sha256,
    ).hexdigest()
    return RazorpayCheckoutCallback(
        razorpay_order_id=order_id,
        razorpay_payment_id=PAYMENT_ID,
        razorpay_signature=signature,
    )


def test_checkout_handoff_is_digest_bound_and_html_contains_no_secret():
    handoff = _handoff()
    rendered = render_checkout_html(handoff)

    assert handoff.handoff_sha256
    assert KEY_ID in rendered
    assert ORDER_ID in rendered
    assert KEY_SECRET not in rendered
    assert "ecocommit-razorpay-checkout-callback.json" in rendered

    tampered = handoff.model_dump(mode="json")
    tampered["transaction"]["amount_minor"] = 200
    with pytest.raises(ValidationError):
        RazorpayCheckoutHandoff.model_validate(tampered)


def test_human_callback_continues_through_capture_processed_refund_and_reconciliation():
    handoff = _handoff()
    transaction = handoff.transaction
    transport = FakeTransport(
        _order_entity(transaction),
        _payment_entity(transaction, "authorized"),
        _payment_entity(transaction, "authorized"),
        _payment_entity(transaction, "captured"),
        _payment_entity(transaction, "captured"),
        {
            "id": REFUND_ID,
            "entity": "refund",
            "amount": transaction.amount_minor,
            "currency": transaction.currency,
            "payment_id": PAYMENT_ID,
            "status": "processed",
        },
    )
    adapter = RazorpayTestPaymentAdapter(
        credentials=RazorpayTestCredentials(KEY_ID, KEY_SECRET),
        transport=transport,
    )

    result = complete_test_lifecycle(
        handoff,
        _callback(),
        adapter=adapter,
        now=NOW + timedelta(minutes=1),
        signing_secret=b"b8-test-signing-key-at-least-32-bytes",
    )

    assert result.checkpoint_b8_lifecycle_passed is True
    assert result.reserve_state == "RESERVED"
    assert result.capture_state == "CAPTURED"
    assert result.refund_state == "REFUNDED"
    assert result.commitment_stage == "COMPENSATED"
    assert result.reconciliation_in_sync is True
    assert result.webhook_verified is False
    assert result.counts_as_full_checkpoint_b is False
    assert [call["path"] for call in transport.calls] == [
        f"/orders/{ORDER_ID}",
        f"/payments/{PAYMENT_ID}",
        f"/payments/{PAYMENT_ID}",
        f"/payments/{PAYMENT_ID}/capture",
        f"/payments/{PAYMENT_ID}",
        f"/payments/{PAYMENT_ID}/refund",
    ]


def test_wrong_order_callback_and_expired_handoff_fail_before_provider_calls():
    handoff = _handoff()
    transport = FakeTransport()
    adapter = RazorpayTestPaymentAdapter(
        credentials=RazorpayTestCredentials(KEY_ID, KEY_SECRET),
        transport=transport,
    )

    with pytest.raises(ValueError, match="another order"):
        complete_test_lifecycle(
            handoff,
            _callback("order_Other123"),
            adapter=adapter,
            now=NOW,
        )
    with pytest.raises(ValueError, match="expired"):
        complete_test_lifecycle(
            handoff,
            _callback(),
            adapter=adapter,
            now=NOW + timedelta(hours=1),
        )
    assert transport.calls == []
