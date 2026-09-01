from __future__ import annotations

import hmac
import importlib.util
import io
import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path

import pytest

from ecocommit._canonical import sha256_hex
from ecocommit.certificates import CertificateSigner, CertificateVerifier
from ecocommit.commitment import ProgressiveCommitmentEngine
from ecocommit.evidence import EvidenceAuthority, EvidenceKind, EvidenceRecord, EvidenceRegistry
from ecocommit.exposure import (
    EvidenceClaimRequirement,
    EvidenceRequirement,
    ExposureCalculator,
    ExposurePolicy,
    ExposureTier,
    TransactionBinding,
)
from ecocommit.idempotency import IdempotencyConflict
from ecocommit.payments import PaymentState, PaymentStateError
from ecocommit.reconciliation import CompensationCoordinator
from ecocommit.razorpay import (
    RazorpayAPIError,
    RazorpayConfigurationError,
    RazorpayHTTPTransport,
    RazorpayTestCredentials,
    RazorpayTestPaymentAdapter,
    RazorpayTransportError,
    RazorpayUnsupportedOperation,
    RazorpayWebhookVerifier,
)
from ecocommit.razorpay_checkout import RazorpayCheckoutCallback


NOW = datetime(2026, 9, 1, 16, 0, tzinfo=timezone.utc)
KEY_SECRET = "test-secret-never-print"
ORDER_ID = "order_ECOCOMMIT123"
PAYMENT_ID = "pay_ECOCOMMIT123"
REFUND_ID = "rfnd_ECOCOMMIT123"
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _load_continue_script():
    path = REPOSITORY_ROOT / "scripts" / "checkpoint_b8_razorpay_continue.py"
    spec = importlib.util.spec_from_file_location("checkpoint_b8_continue", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class FakeTransport:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls: list[dict] = []

    def enqueue(self, *responses) -> None:
        self.responses.extend(responses)

    def request(self, method, path, *, payload=None, headers=None):
        call = {
            "method": method,
            "path": path,
            "payload": deepcopy(payload),
            "headers": deepcopy(headers),
        }
        self.calls.append(call)
        if not self.responses:
            raise AssertionError(f"unexpected provider call: {method} {path}")
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        if callable(response):
            response = response(call)
        return deepcopy(response)


def transaction(**updates) -> TransactionBinding:
    values = {
        "transaction_id": "tx-razorpay-b8",
        "merchant_id": "merchant-razorpay-b8",
        "amount_minor": 2_000,
        "currency": "INR",
        "contract_hash": "a" * 64,
    }
    values.update(updates)
    return TransactionBinding(**values)


def binding_notes(tx: TransactionBinding) -> dict[str, str]:
    return {
        "ecocommit_transaction_digest": tx.digest(),
        "ecocommit_contract_hash": tx.contract_hash,
        "ecocommit_merchant_digest": sha256_hex(tx.merchant_id),
    }


def order_entity(
    tx: TransactionBinding,
    *,
    order_id: str = ORDER_ID,
    receipt: str = "ec_order_test",
    status: str = "attempted",
    **updates,
) -> dict:
    values = {
        "id": order_id,
        "entity": "order",
        "amount": tx.amount_minor,
        "amount_paid": 0,
        "amount_due": tx.amount_minor,
        "currency": tx.currency,
        "receipt": receipt,
        "status": status,
        "attempts": 1 if status == "attempted" else 0,
        "notes": binding_notes(tx),
    }
    values.update(updates)
    return values


def payment_entity(
    tx: TransactionBinding,
    *,
    order_id: str = ORDER_ID,
    payment_id: str = PAYMENT_ID,
    status: str = "authorized",
    **updates,
) -> dict:
    values = {
        "id": payment_id,
        "entity": "payment",
        "amount": tx.amount_minor,
        "currency": tx.currency,
        "status": status,
        "order_id": order_id,
        "captured": status == "captured",
        "amount_captured": tx.amount_minor if status == "captured" else 0,
        "amount_refunded": 0,
    }
    values.update(updates)
    return values


def checkout_signature(order_id: str = ORDER_ID, payment_id: str = PAYMENT_ID) -> str:
    return hmac.new(
        KEY_SECRET.encode(),
        f"{order_id}|{payment_id}".encode(),
        sha256,
    ).hexdigest()


def credentials() -> RazorpayTestCredentials:
    return RazorpayTestCredentials("rzp_test_x", KEY_SECRET)


def test_live_workflows_are_manual_and_keep_credentials_in_secret_environment():
    workflow_root = REPOSITORY_ROOT / ".github" / "workflows"
    preflight = (workflow_root / "razorpay-test-preflight.yml").read_text(
        encoding="utf-8"
    )
    lifecycle = (workflow_root / "razorpay-test-lifecycle.yml").read_text(
        encoding="utf-8"
    )

    for workflow in (preflight, lifecycle):
        assert "workflow_dispatch:" in workflow
        assert "\n  push:" not in workflow
        assert "${{ secrets.RAZORPAY_KEY_ID }}" in workflow
        assert "${{ secrets.RAZORPAY_KEY_SECRET }}" in workflow
        assert "print(key_id" not in workflow
        assert "print(key_secret" not in workflow
    assert "credential_preflight_run_id" in lifecycle
    assert "RUN_TEST_MODE_ORDER" in lifecycle
    assert lifecycle.count("${{ secrets.RAZORPAY_KEY_ID }}") == 1
    assert lifecycle.count("${{ secrets.RAZORPAY_KEY_SECRET }}") == 1


def adapter(transport: FakeTransport) -> RazorpayTestPaymentAdapter:
    return RazorpayTestPaymentAdapter(credentials=credentials(), transport=transport)


def authority_bundle(tx: TransactionBinding):
    registry = EvidenceRegistry(
        [
            EvidenceAuthority(
                authority_id="user-auth",
                issuer="identity-service",
                permitted_kinds={EvidenceKind.USER_AUTHORIZATION},
                max_age_seconds=300,
            )
        ]
    )
    registry.register(
        EvidenceRecord(
            evidence_id="auth-razorpay",
            authority_id="user-auth",
            issuer="identity-service",
            kind=EvidenceKind.USER_AUTHORIZATION,
            subject=tx.transaction_id,
            version=1,
            observed_at=NOW,
            claims={"approved": True},
        ),
        now=NOW,
    )
    snapshot = registry.snapshot(["auth-razorpay"], subject=tx.transaction_id, now=NOW)
    policy = ExposurePolicy(
        policy_id="razorpay-policy",
        version=1,
        currency="INR",
        tiers=(
            ExposureTier(
                tier_id="authorized",
                requirements=(
                    EvidenceRequirement(
                        kind=EvidenceKind.USER_AUTHORIZATION,
                        authority_ids={"user-auth"},
                        claims=(
                            EvidenceClaimRequirement(key="approved", expected_value=True),
                        ),
                    ),
                ),
                max_irreversible_minor=tx.amount_minor,
            ),
        ),
    )
    decision = ExposureCalculator(policy).calculate(tx, snapshot, now=NOW)
    signing_secret = b"razorpay-certificate-test-secret-at-least-32-bytes"
    certificate = CertificateSigner(
        key_id="razorpay-certificate-key",
        secret=signing_secret,
        trusted_policy=policy,
    ).issue(
        transaction=tx,
        snapshot=snapshot,
        decision=decision,
        registry=registry,
        now=NOW,
        nonce="b" * 32,
    )
    verifier = CertificateVerifier({"razorpay-certificate-key": signing_secret})
    return registry, certificate, verifier


def capture_allowed(tx: TransactionBinding, reservation_reference: str):
    registry, certificate, verifier = authority_bundle(tx)
    engine = ProgressiveCommitmentEngine()
    state = engine.propose(tx, at=NOW)
    state = engine.authorize(
        state,
        authorization_reference="authz-razorpay",
        event_id="razorpay-authorize",
        at=NOW + timedelta(seconds=1),
    )
    state = engine.reserve(
        state,
        reservation_reference=reservation_reference,
        reversible=True,
        event_id="razorpay-reserve",
        at=NOW + timedelta(seconds=2),
    )
    state = engine.allow_capture(
        state,
        certificate=certificate,
        verifier=verifier,
        registry=registry,
        event_id="razorpay-allow-capture",
        at=NOW + timedelta(seconds=3),
    )
    return state, registry, certificate, verifier


def bound_adapter(tx: TransactionBinding | None = None):
    tx = tx or transaction()
    transport = FakeTransport(
        order_entity(tx),
        payment_entity(tx),
    )
    payments = adapter(transport)
    reservation = payments.reserve(
        tx,
        order_id=ORDER_ID,
        payment_id=PAYMENT_ID,
        checkout_signature=checkout_signature(),
        idempotency_key="bind-authorized-payment",
    )
    return tx, transport, payments, reservation


def captured_adapter():
    tx, transport, payments, reservation = bound_adapter()
    state, registry, certificate, verifier = capture_allowed(
        tx,
        reservation.provider_reference,
    )
    transport.enqueue(
        payment_entity(tx),
        payment_entity(tx, status="captured"),
    )
    result = payments.capture(
        tx,
        commitment=state,
        certificate=certificate,
        verifier=verifier,
        registry=registry,
        now=NOW + timedelta(seconds=3),
        idempotency_key="capture-authorized-payment",
    )
    return tx, transport, payments, result


def captured_compensation_bundle():
    tx, transport, payments, reservation = bound_adapter()
    capture_allowed_state, registry, certificate, verifier = capture_allowed(
        tx,
        reservation.provider_reference,
    )
    transport.enqueue(
        payment_entity(tx),
        payment_entity(tx, status="captured"),
    )
    payments.capture(
        tx,
        commitment=capture_allowed_state,
        certificate=certificate,
        verifier=verifier,
        registry=registry,
        now=NOW + timedelta(seconds=3),
        idempotency_key="capture-for-compensation",
    )
    engine = ProgressiveCommitmentEngine()
    captured_state = engine.record_capture(
        capture_allowed_state,
        payment_reference=PAYMENT_ID,
        event_id="razorpay-capture-recorded",
        at=NOW + timedelta(seconds=4),
    )
    return tx, transport, payments, engine, captured_state


def test_credentials_are_environment_only_test_mode_and_repr_is_redacted():
    creds = RazorpayTestCredentials.from_environment(
        {
            "RAZORPAY_KEY_ID": "rzp_test_from_env",
            "RAZORPAY_KEY_SECRET": KEY_SECRET,
        }
    )
    assert "rzp_test_from_env" not in repr(creds)
    assert KEY_SECRET not in repr(creds)
    with pytest.raises(RazorpayConfigurationError, match="refuses non-test"):
        RazorpayTestCredentials("rzp_live_x", KEY_SECRET)
    with pytest.raises(RazorpayConfigurationError, match="required"):
        RazorpayTestCredentials.from_environment({})


def test_http_transport_restricts_origin_and_never_exposes_credentials(monkeypatch):
    seen = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def read(self, _limit):
            return b'{"entity":"collection","count":0,"items":[]}'

    def fake_urlopen(api_request, *, timeout):
        seen["authorization"] = api_request.get_header("Authorization")
        seen["timeout"] = timeout
        return Response()

    monkeypatch.setattr("ecocommit.razorpay.request.urlopen", fake_urlopen)
    transport = RazorpayHTTPTransport(credentials(), timeout_seconds=7)
    assert transport.request("GET", "/orders?count=1")["entity"] == "collection"
    assert seen["authorization"].startswith("Basic ")
    assert KEY_SECRET not in seen["authorization"]
    assert KEY_SECRET not in repr(transport)
    assert seen["timeout"] == 7
    with pytest.raises(RazorpayConfigurationError, match="official API origin"):
        RazorpayHTTPTransport(credentials(), base_url="https://example.invalid")
    with pytest.raises(ValueError, match="origin-relative"):
        transport.request("GET", "https://example.invalid/orders")
    with pytest.raises(ValueError, match="cannot be overridden"):
        transport.request("GET", "/orders", headers={"Authorization": "Bearer attacker"})


def test_adapter_credential_preflight_is_read_only_and_schema_checked():
    valid = FakeTransport({"entity": "collection", "count": 0, "items": []})
    adapter = RazorpayTestPaymentAdapter(
        credentials=credentials(),
        transport=valid,
    )

    assert adapter.verify_credentials() is True
    assert valid.calls == [{
        "method": "GET",
        "path": "/orders?count=1",
        "payload": None,
        "headers": None,
    }]

    malformed = RazorpayTestPaymentAdapter(
        credentials=credentials(),
        transport=FakeTransport({"entity": "collection", "count": 0}),
    )
    with pytest.raises(RazorpayTransportError, match="invalid collection"):
        malformed.verify_credentials()


def test_http_error_retains_only_safe_status_and_provider_code(monkeypatch):
    body = io.BytesIO(
        json.dumps(
            {
                "error": {
                    "code": "BAD_REQUEST_ERROR",
                    "description": KEY_SECRET,
                }
            }
        ).encode()
    )

    def fail(*_args, **_kwargs):
        from urllib.error import HTTPError

        raise HTTPError("https://api.razorpay.com/v1/orders", 400, "bad", {}, body)

    monkeypatch.setattr("ecocommit.razorpay.request.urlopen", fail)
    with pytest.raises(RazorpayAPIError) as caught:
        RazorpayHTTPTransport(credentials()).request("GET", "/orders")
    assert caught.value.status_code == 400
    assert caught.value.provider_code == "BAD_REQUEST_ERROR"
    assert KEY_SECRET not in str(caught.value)


def test_order_creation_is_bound_and_idempotent_at_ecocommit_boundary():
    tx = transaction()

    def created(call):
        payload = call["payload"]
        return order_entity(
            tx,
            receipt=payload["receipt"],
            status="created",
            notes=payload["notes"],
        )

    transport = FakeTransport(
        {"entity": "collection", "count": 0, "items": []},
        created,
    )
    payments = adapter(transport)
    first = payments.create_order(tx, idempotency_key="create-order-once")
    replay = payments.create_order(tx, idempotency_key="create-order-once")
    assert first == replay
    assert first.simulated is False
    assert first.provider_status == "created"
    assert len(first.receipt) <= 40
    assert [call["method"] for call in transport.calls] == ["GET", "POST"]
    assert transport.calls[1]["payload"]["amount"] == tx.amount_minor
    assert transport.calls[1]["payload"]["currency"] == tx.currency
    assert transport.calls[1]["payload"]["notes"] == binding_notes(tx)

    changed = transaction(amount_minor=2_001)
    with pytest.raises(IdempotencyConflict):
        payments.create_order(changed, idempotency_key="create-order-once")
    with pytest.raises(PaymentStateError, match="different idempotency key"):
        payments.create_order(tx, idempotency_key="another-order-key")


def test_order_creation_recovers_exact_binding_after_ambiguous_transport_failure():
    tx = transaction()
    provider_order = {}

    def fail_after_create(call):
        provider_order.update(
            order_entity(
                tx,
                receipt=call["payload"]["receipt"],
                status="created",
                notes=call["payload"]["notes"],
            )
        )
        raise RazorpayTransportError("ambiguous")

    def recovered(_call):
        return {"entity": "collection", "count": 1, "items": [provider_order]}

    transport = FakeTransport(
        {"entity": "collection", "count": 0, "items": []},
        fail_after_create,
        recovered,
    )
    result = adapter(transport).create_order(tx, idempotency_key="ambiguous-order")
    assert result.recovered is True
    assert result.order_id == ORDER_ID


def test_fetch_order_payments_revalidates_binding_and_identifiers():
    tx = transaction()
    transport = FakeTransport(
        order_entity(tx, status="created"),
        {"entity": "collection", "count": 0, "items": []},
    )
    observed = adapter(transport).fetch_payments_for_order(tx, order_id=ORDER_ID)
    assert observed == ()
    assert [call["path"] for call in transport.calls] == [
        f"/orders/{ORDER_ID}",
        f"/orders/{ORDER_ID}/payments",
    ]


@pytest.mark.parametrize(
    "mutation, message",
    [
        ({"amount": 2_001}, "amount"),
        ({"currency": "USD"}, "currency"),
        ({"notes": {}}, "notes"),
    ],
)
def test_order_creation_rejects_provider_binding_mismatch(mutation, message):
    tx = transaction()

    def mismatched(call):
        return order_entity(
            tx,
            receipt=call["payload"]["receipt"],
            status="created",
            **mutation,
        )

    transport = FakeTransport(
        {"entity": "collection", "count": 0, "items": []},
        mismatched,
        {"entity": "collection", "count": 0, "items": []},
    )
    with pytest.raises(PaymentStateError, match=message):
        adapter(transport).create_order(tx, idempotency_key="mismatch")


def test_authorized_payment_binding_verifies_signature_provider_ids_and_replay():
    tx, transport, payments, reservation = bound_adapter()
    assert reservation.state == PaymentState.RESERVED
    assert reservation.order_id == ORDER_ID
    assert reservation.payment_id == PAYMENT_ID
    assert reservation.amount_minor == tx.amount_minor
    assert reservation.currency == tx.currency
    assert payments.snapshot(tx.transaction_id).last_reference == PAYMENT_ID
    call_count = len(transport.calls)
    assert payments.reserve(
        tx,
        order_id=ORDER_ID,
        payment_id=PAYMENT_ID,
        checkout_signature=checkout_signature(),
        idempotency_key="bind-authorized-payment",
    ) == reservation
    assert len(transport.calls) == call_count

    tampered = "0" * 64 if checkout_signature() != "0" * 64 else "1" * 64
    with pytest.raises(IdempotencyConflict):
        payments.reserve(
            tx,
            order_id=ORDER_ID,
            payment_id=PAYMENT_ID,
            checkout_signature=tampered,
            idempotency_key="bind-authorized-payment",
        )


def test_invalid_checkout_signature_fails_before_provider_calls():
    transport = FakeTransport()
    payments = adapter(transport)
    with pytest.raises(PaymentStateError, match="signature is invalid"):
        payments.reserve(
            transaction(),
            order_id=ORDER_ID,
            payment_id=PAYMENT_ID,
            checkout_signature="0" * 64,
            idempotency_key="bad-signature",
        )
    assert transport.calls == []


@pytest.mark.parametrize(
    "order, payment, message",
    [
        (None, {"order_id": "order_OTHER"}, "another order"),
        (None, {"amount": 9_999}, "amount"),
        (None, {"currency": "USD"}, "currency"),
        (None, {"status": "captured", "captured": True}, "unexpected state"),
        ({"status": "paid"}, None, "unexpected state"),
    ],
)
def test_authorized_payment_binding_rejects_provider_mismatch(order, payment, message):
    tx = transaction()
    order_values = order_entity(tx)
    payment_values = payment_entity(tx)
    order_values.update(order or {})
    payment_values.update(payment or {})
    transport = FakeTransport(order_values, payment_values)
    with pytest.raises(PaymentStateError, match=message):
        adapter(transport).reserve(
            tx,
            order_id=ORDER_ID,
            payment_id=PAYMENT_ID,
            checkout_signature=checkout_signature(),
            idempotency_key="provider-mismatch",
        )


def test_capture_executes_only_after_full_ecocommit_authority_and_replays_once():
    tx, transport, payments, reservation = bound_adapter()
    state, registry, certificate, verifier = capture_allowed(
        tx,
        reservation.provider_reference,
    )
    transport.enqueue(
        payment_entity(tx),
        payment_entity(tx, status="captured"),
    )
    result = payments.capture(
        tx,
        commitment=state,
        certificate=certificate,
        verifier=verifier,
        registry=registry,
        now=NOW + timedelta(seconds=3),
        idempotency_key="capture-once",
    )
    assert result.state == PaymentState.CAPTURED
    assert result.provider_reference == PAYMENT_ID
    assert payments.snapshot(tx.transaction_id).state == PaymentState.CAPTURED
    capture_calls = [call for call in transport.calls if call["path"].endswith("/capture")]
    assert len(capture_calls) == 1
    assert capture_calls[0]["payload"] == {"amount": 2_000, "currency": "INR"}
    assert payments.capture(
        tx,
        commitment=state,
        certificate=certificate,
        verifier=verifier,
        registry=registry,
        now=NOW + timedelta(seconds=3),
        idempotency_key="capture-once",
    ) == result
    assert len([call for call in transport.calls if call["path"].endswith("/capture")]) == 1


def test_capture_wrong_stage_fails_before_provider_capture():
    tx, transport, payments, _reservation = bound_adapter()
    registry, certificate, verifier = authority_bundle(tx)
    engine = ProgressiveCommitmentEngine()
    proposed = engine.propose(tx, at=NOW)
    authorized = engine.authorize(
        proposed,
        authorization_reference="authz",
        event_id="authorize",
        at=NOW + timedelta(seconds=1),
    )
    before = len(transport.calls)
    with pytest.raises(PaymentStateError, match="CAPTURE_ALLOWED"):
        payments.capture(
            tx,
            commitment=authorized,
            certificate=certificate,
            verifier=verifier,
            registry=registry,
            now=NOW + timedelta(seconds=2),
            idempotency_key="forbidden-capture",
        )
    assert len(transport.calls) == before


def test_capture_recovers_only_after_an_ambiguous_post():
    tx, transport, payments, reservation = bound_adapter()
    state, registry, certificate, verifier = capture_allowed(
        tx,
        reservation.provider_reference,
    )
    transport.enqueue(
        payment_entity(tx),
        RazorpayTransportError("ambiguous"),
        payment_entity(tx, status="captured"),
    )
    result = payments.capture(
        tx,
        commitment=state,
        certificate=certificate,
        verifier=verifier,
        registry=registry,
        now=NOW + timedelta(seconds=3),
        idempotency_key="capture-ambiguous",
    )
    assert result.recovered is True
    assert result.state == PaymentState.CAPTURED


def test_capture_failure_is_retryable_and_does_not_advance_local_state():
    tx, transport, payments, reservation = bound_adapter()
    state, registry, certificate, verifier = capture_allowed(
        tx,
        reservation.provider_reference,
    )
    transport.enqueue(
        payment_entity(tx),
        RazorpayAPIError(status_code=400, provider_code="BAD_REQUEST_ERROR"),
        payment_entity(tx),
    )
    with pytest.raises(RazorpayAPIError):
        payments.capture(
            tx,
            commitment=state,
            certificate=certificate,
            verifier=verifier,
            registry=registry,
            now=NOW + timedelta(seconds=3),
            idempotency_key="capture-retry",
        )
    assert payments.snapshot(tx.transaction_id).state == PaymentState.RESERVED

    transport.enqueue(
        payment_entity(tx),
        payment_entity(tx, status="captured"),
    )
    retried = payments.capture(
        tx,
        commitment=state,
        certificate=certificate,
        verifier=verifier,
        registry=registry,
        now=NOW + timedelta(seconds=3),
        idempotency_key="capture-retry",
    )
    assert retried.state == PaymentState.CAPTURED


def test_void_fails_explicitly_because_provider_has_no_void_api():
    tx, transport, payments, _reservation = bound_adapter()
    before = len(transport.calls)
    with pytest.raises(RazorpayUnsupportedOperation, match="no immediate void API"):
        payments.void(tx, idempotency_key="void-not-supported")
    assert len(transport.calls) == before
    assert payments.snapshot(tx.transaction_id).state == PaymentState.RESERVED


def test_refund_uses_provider_idempotency_and_completes_only_when_processed():
    tx, transport, payments, _capture = captured_adapter()
    transport.enqueue(
        payment_entity(tx, status="captured"),
        {
            "id": REFUND_ID,
            "entity": "refund",
            "amount": tx.amount_minor,
            "currency": tx.currency,
            "payment_id": PAYMENT_ID,
            "status": "processed",
        },
    )
    result = payments.refund(tx, idempotency_key="refund-captured-payment")
    assert result.state == PaymentState.REFUNDED
    assert result.refund_id == REFUND_ID
    refund_call = [call for call in transport.calls if call["path"].endswith("/refund")][-1]
    assert refund_call["headers"]["X-Refund-Idempotency"].startswith("ec_refund_")
    assert len(refund_call["headers"]["X-Refund-Idempotency"]) >= 10
    call_count = len(transport.calls)
    assert payments.refund(tx, idempotency_key="refund-captured-payment") == result
    assert len(transport.calls) == call_count
    with pytest.raises(IdempotencyConflict):
        payments.refund(tx, idempotency_key="different-full-refund-key")
    assert len(transport.calls) == call_count


def test_pending_refund_is_not_misreported_as_completed():
    tx, transport, payments, _capture = captured_adapter()
    transport.enqueue(
        payment_entity(tx, status="captured"),
        {
            "id": REFUND_ID,
            "entity": "refund",
            "amount": tx.amount_minor,
            "currency": tx.currency,
            "payment_id": PAYMENT_ID,
            "status": "pending",
        },
    )
    result = payments.refund(tx, idempotency_key="pending-refund")
    assert result.state == PaymentState.REFUND_PENDING
    assert payments.snapshot(tx.transaction_id).state == PaymentState.REFUND_PENDING


def test_b8_continuation_loader_rejects_duplicate_json_keys(tmp_path):
    callback = tmp_path / "callback.json"
    callback.write_text(
        '{"razorpay_order_id":"order_First123",'
        '"razorpay_order_id":"order_Second123",'
        '"razorpay_payment_id":"pay_Test123",'
        '"razorpay_signature":"' + ("0" * 64) + '"}',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="duplicate JSON keys"):
        _load_continue_script()._load(callback, RazorpayCheckoutCallback)


def test_compensation_boundary_keeps_provider_pending_refund_incomplete():
    tx, transport, payments, engine, captured_state = captured_compensation_bundle()
    transport.enqueue(
        payment_entity(tx, status="captured"),
        {
            "id": REFUND_ID,
            "entity": "refund",
            "amount": tx.amount_minor,
            "currency": tx.currency,
            "payment_id": PAYMENT_ID,
            "status": "pending",
        },
    )
    coordinator = CompensationCoordinator(engine=engine, payments=payments)
    outcome = coordinator.compensate(
        captured_state,
        reason_reference="provider-refund-required",
        idempotency_key="pending-provider-compensation",
        at=NOW + timedelta(seconds=5),
    )

    assert outcome.simulated is False
    assert outcome.succeeded is False
    assert outcome.pending is True
    assert outcome.state.stage.value == "COMPENSATION_PENDING"
    assert outcome.payment_result is not None
    assert outcome.payment_result.state == PaymentState.REFUND_PENDING
    call_count = len(transport.calls)
    transport.enqueue({
        "id": REFUND_ID,
        "entity": "refund",
        "amount": tx.amount_minor,
        "currency": tx.currency,
        "payment_id": PAYMENT_ID,
        "status": "pending",
    })

    replay = coordinator.compensate(
        outcome.state,
        reason_reference="provider-refund-required",
        idempotency_key="pending-provider-compensation",
        at=NOW + timedelta(seconds=6),
    )
    assert replay.pending is True
    assert replay.succeeded is False
    assert len(transport.calls) == call_count + 1
    assert transport.calls[-1]["path"] == f"/refunds/{REFUND_ID}"


def test_compensation_boundary_completes_only_processed_provider_refund():
    tx, transport, payments, engine, captured_state = captured_compensation_bundle()
    transport.enqueue(
        payment_entity(tx, status="captured"),
        {
            "id": REFUND_ID,
            "entity": "refund",
            "amount": tx.amount_minor,
            "currency": tx.currency,
            "payment_id": PAYMENT_ID,
            "status": "processed",
        },
    )
    outcome = CompensationCoordinator(engine=engine, payments=payments).compensate(
        captured_state,
        reason_reference="provider-refund-required",
        idempotency_key="processed-provider-compensation",
        at=NOW + timedelta(seconds=5),
    )

    assert outcome.simulated is False
    assert outcome.succeeded is True
    assert outcome.pending is False
    assert outcome.state.stage.value == "COMPENSATED"
    assert outcome.payment_result is not None
    assert outcome.payment_result.state == PaymentState.REFUNDED


def test_webhook_verifier_checks_raw_body_before_decoding_and_redacts_secret():
    raw = b'{"event":"payment.authorized","payload":{}}'
    signature = hmac.new(KEY_SECRET.encode(), raw, sha256).hexdigest()
    verifier = RazorpayWebhookVerifier(KEY_SECRET)
    assert verifier.verify_and_decode(raw, signature)["event"] == "payment.authorized"
    assert KEY_SECRET not in repr(verifier)
    with pytest.raises(PaymentStateError, match="signature is invalid"):
        verifier.verify_and_decode(raw + b" ", signature)
    with pytest.raises(RazorpayConfigurationError, match="required"):
        RazorpayWebhookVerifier.from_environment({})
