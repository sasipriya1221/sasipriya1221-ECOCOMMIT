from __future__ import annotations

import json
import secrets
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ._canonical import sha256_hex
from .certificates import CertificateSigner, CertificateVerifier
from .commitment import ProgressiveCommitmentEngine
from .evidence import EvidenceAuthority, EvidenceKind, EvidenceRecord, EvidenceRegistry
from .exposure import (
    EvidenceClaimRequirement,
    EvidenceRequirement,
    ExposureCalculator,
    ExposurePolicy,
    ExposureTier,
    TransactionBinding,
)
from .payments import PaymentState
from .razorpay import RazorpayOrderResult, RazorpayTestPaymentAdapter
from .reconciliation import CompensationCoordinator, Reconciler


def _aware(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value


class RazorpayCheckoutHandoff(BaseModel):
    """Public, digest-bound data needed for one human Test Checkout interaction."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["B8.CHECKOUT.1"] = "B8.CHECKOUT.1"
    provider_mode: Literal["RAZORPAY_TEST_MODE"] = "RAZORPAY_TEST_MODE"
    public_key_id: str = Field(pattern=r"^rzp_test_[A-Za-z0-9]+$")
    transaction: TransactionBinding
    order: RazorpayOrderResult
    created_at: datetime
    expires_at: datetime
    handoff_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("created_at", "expires_at")
    @classmethod
    def aware_times(cls, value: datetime, info):
        return _aware(value, info.field_name)

    @model_validator(mode="after")
    def binding_is_coherent(self):
        if self.expires_at <= self.created_at:
            raise ValueError("Checkout handoff expiry must follow creation")
        if self.order.transaction_id != self.transaction.transaction_id:
            raise ValueError("Checkout order transaction id does not match")
        if self.order.transaction_digest != self.transaction.digest():
            raise ValueError("Checkout order transaction digest does not match")
        if self.order.amount_minor != self.transaction.amount_minor:
            raise ValueError("Checkout order amount does not match")
        if self.order.currency != self.transaction.currency:
            raise ValueError("Checkout order currency does not match")
        expected = sha256_hex(self.model_dump(exclude={"handoff_sha256"}))
        if self.handoff_sha256 != expected:
            raise ValueError("Checkout handoff digest is invalid")
        return self

    @classmethod
    def create(cls, **values) -> "RazorpayCheckoutHandoff":
        body = {
            "schema_version": "B8.CHECKOUT.1",
            "provider_mode": "RAZORPAY_TEST_MODE",
            **values,
        }
        return cls(**body, handoff_sha256=sha256_hex(body))


class RazorpayCheckoutCallback(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    razorpay_order_id: str = Field(pattern=r"^order_[A-Za-z0-9]+$")
    razorpay_payment_id: str = Field(pattern=r"^pay_[A-Za-z0-9]+$")
    razorpay_signature: str = Field(pattern=r"^[0-9a-fA-F]{64}$")


class RazorpayLifecycleEvidence(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: Literal["B8.LIFECYCLE.1"] = "B8.LIFECYCLE.1"
    provider_mode: Literal["RAZORPAY_TEST_MODE"] = "RAZORPAY_TEST_MODE"
    simulated: Literal[False] = False
    counts_as_full_checkpoint_b: Literal[False] = False
    handoff_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    transaction_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    order_id: str = Field(pattern=r"^order_[A-Za-z0-9]+$")
    payment_id: str = Field(pattern=r"^pay_[A-Za-z0-9]+$")
    refund_id: str = Field(pattern=r"^rfnd_[A-Za-z0-9]+$")
    reserve_state: Literal["RESERVED"]
    capture_state: Literal["CAPTURED"]
    refund_state: Literal["REFUND_PENDING", "REFUNDED"]
    commitment_stage: Literal["COMPENSATION_PENDING", "COMPENSATED"]
    reconciliation_in_sync: bool
    checkpoint_b8_lifecycle_passed: bool
    checkout_signature_retained: Literal[False] = False
    certificate_signing_key_retained: Literal[False] = False
    webhook_verified: Literal[False] = False

    @model_validator(mode="after")
    def pass_requires_processed_refund_and_reconciliation(self):
        expected = (
            self.refund_state == "REFUNDED"
            and self.commitment_stage == "COMPENSATED"
            and self.reconciliation_in_sync
        )
        if self.checkpoint_b8_lifecycle_passed != expected:
            raise ValueError("B8 lifecycle pass flag is inconsistent")
        return self


def render_checkout_html(handoff: RazorpayCheckoutHandoff) -> str:
    """Render a standalone Test Checkout handoff; the secret key is never present."""
    options = {
        "key": handoff.public_key_id,
        "amount": handoff.transaction.amount_minor,
        "currency": handoff.transaction.currency,
        "name": "ECOCOMMIT Test Mode",
        "description": "Human authorization for the retained B8 Test order",
        "order_id": handoff.order.order_id,
    }
    encoded = json.dumps(options, ensure_ascii=True, separators=(",", ":")).replace("<", "\\u003c")
    return f"""<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ECOCOMMIT Razorpay Test Checkout</title>
<style>body{{font:16px system-ui;max-width:720px;margin:3rem auto;padding:0 1rem}}button{{font:inherit;padding:.8rem 1.2rem}}code{{overflow-wrap:anywhere}}.warn{{color:#8a3b00}}</style>
</head>
<body>
<h1>Razorpay Test Checkout</h1>
<p class="warn">Test Mode only. Confirm the dashboard uses manual capture before continuing.</p>
<p>Order: <code>{handoff.order.order_id}</code> · Amount: {handoff.transaction.amount_minor} {handoff.transaction.currency} minor units.</p>
<button id="checkout">Open Test Checkout</button>
<p id="status" role="status"></p>
<script src="https://checkout.razorpay.com/v1/checkout.js"></script>
<script>
const options = {encoded};
options.handler = function(response) {{
  const callback = {{
    razorpay_order_id: response.razorpay_order_id,
    razorpay_payment_id: response.razorpay_payment_id,
    razorpay_signature: response.razorpay_signature
  }};
  const blob = new Blob([JSON.stringify(callback, null, 2) + "\\n"], {{type:"application/json"}});
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = "ecocommit-razorpay-checkout-callback.json";
  link.click();
  URL.revokeObjectURL(link.href);
  document.getElementById("status").textContent = "Callback downloaded. Keep it private and run the ECOCOMMIT continuation validator.";
}};
document.getElementById("checkout").addEventListener("click", () => new Razorpay(options).open());
</script>
</body></html>
"""


def complete_test_lifecycle(
    handoff: RazorpayCheckoutHandoff,
    callback: RazorpayCheckoutCallback,
    *,
    adapter: RazorpayTestPaymentAdapter,
    now: datetime,
    signing_secret: bytes | None = None,
) -> RazorpayLifecycleEvidence:
    """Verify Checkout, capture behind a local B8 certificate, and compensate."""
    now = _aware(now, "now")
    if now > handoff.expires_at:
        raise ValueError("Checkout handoff expired")
    if callback.razorpay_order_id != handoff.order.order_id:
        raise ValueError("Checkout callback belongs to another order")

    transaction = handoff.transaction
    token = handoff.handoff_sha256[:20]
    reservation = adapter.reserve(
        transaction,
        order_id=callback.razorpay_order_id,
        payment_id=callback.razorpay_payment_id,
        checkout_signature=callback.razorpay_signature,
        idempotency_key=f"b8-reserve-{token}",
    )

    authority_id = "b8-human-checkout"
    evidence_id = f"b8-checkout-{callback.razorpay_payment_id}"
    registry = EvidenceRegistry([
        EvidenceAuthority(
            authority_id=authority_id,
            issuer="razorpay-test-checkout",
            permitted_kinds={EvidenceKind.USER_AUTHORIZATION},
            max_age_seconds=300,
        )
    ])
    registry.register(EvidenceRecord(
        evidence_id=evidence_id,
        authority_id=authority_id,
        issuer="razorpay-test-checkout",
        kind=EvidenceKind.USER_AUTHORIZATION,
        subject=transaction.transaction_id,
        version=1,
        observed_at=now,
        claims={"approved": True},
    ), now=now)
    snapshot = registry.snapshot((evidence_id,), subject=transaction.transaction_id, now=now)
    policy = ExposurePolicy(
        policy_id="b8-checkout-exact-amount",
        version=1,
        currency=transaction.currency,
        tiers=(ExposureTier(
            tier_id="human-test-checkout",
            requirements=(EvidenceRequirement(
                kind=EvidenceKind.USER_AUTHORIZATION,
                authority_ids={authority_id},
                claims=(EvidenceClaimRequirement(key="approved", expected_value=True),),
            ),),
            max_irreversible_minor=transaction.amount_minor,
        ),),
    )
    decision = ExposureCalculator(policy).calculate(transaction, snapshot, now=now)
    secret = signing_secret or secrets.token_bytes(32)
    signer = CertificateSigner(
        key_id="b8-ephemeral-test-key",
        secret=secret,
        trusted_policy=policy,
    )
    certificate = signer.issue(
        transaction=transaction,
        snapshot=snapshot,
        decision=decision,
        registry=registry,
        now=now,
        ttl_seconds=60,
    )
    verifier = CertificateVerifier({"b8-ephemeral-test-key": secret})
    engine = ProgressiveCommitmentEngine()
    state = engine.propose(transaction, at=now)
    state = engine.authorize(
        state,
        authorization_reference=callback.razorpay_payment_id,
        event_id=f"b8:{token}:authorize",
        at=now,
    )
    state = engine.reserve(
        state,
        reservation_reference=reservation.provider_reference,
        reversible=True,
        event_id=f"b8:{token}:reserve",
        at=now,
    )
    state = engine.allow_capture(
        state,
        certificate=certificate,
        verifier=verifier,
        registry=registry,
        event_id=f"b8:{token}:allow-capture",
        at=now,
    )
    capture = adapter.capture(
        transaction,
        commitment=state,
        certificate=certificate,
        verifier=verifier,
        registry=registry,
        now=now,
        idempotency_key=f"b8-capture-{token}",
    )
    state = engine.record_capture(
        state,
        payment_reference=capture.provider_reference,
        event_id=f"b8:{token}:captured",
        at=now,
    )
    compensation = CompensationCoordinator(engine=engine, payments=adapter).compensate(
        state,
        reason_reference="b8-test-lifecycle-cleanup",
        idempotency_key=f"b8-refund-{token}",
        at=now,
    )
    payment = adapter.snapshot(transaction.transaction_id)
    reconciliation = Reconciler().reconcile(compensation.state, payment, now=now)
    refund = compensation.payment_result
    if refund is None or refund.refund_id is None:
        raise ValueError("B8 lifecycle did not return a bound refund")

    return RazorpayLifecycleEvidence(
        handoff_sha256=handoff.handoff_sha256,
        transaction_digest=transaction.digest(),
        order_id=handoff.order.order_id,
        payment_id=callback.razorpay_payment_id,
        refund_id=refund.refund_id,
        reserve_state=reservation.state.value,
        capture_state=capture.state.value,
        refund_state=refund.state.value,
        commitment_stage=compensation.state.stage.value,
        reconciliation_in_sync=reconciliation.in_sync,
        checkpoint_b8_lifecycle_passed=(
            refund.state == PaymentState.REFUNDED
            and compensation.succeeded
            and reconciliation.in_sync
        ),
    )
