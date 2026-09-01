from __future__ import annotations

import hmac
import json
import subprocess
import sys
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path

import pytest
from pydantic import ValidationError

from ecocommit._canonical import sha256_hex
from ecocommit.commitment import SQLiteCommitmentStateStore
from ecocommit.durable import JSONResultCodec, SQLiteIdempotencyLedger, SQLiteJSONStateStore
from ecocommit.execution import (
    PreparedRazorpayTestOperation,
    RazorpayPreparedTestExecutionAdapter,
    TestExecutionError,
    TestExecutionResult,
    load_prepared_test_operation,
)
from ecocommit.exposure import TransactionBinding
from ecocommit.payments import SQLitePaymentStateStore
from ecocommit.razorpay import (
    RazorpayOrderResult,
    RazorpayPaymentResult,
    RazorpayTestCredentials,
    RazorpayTestPaymentAdapter,
)
from ecocommit.razorpay_checkout import (
    RazorpayCheckoutCallback,
    RazorpayCheckoutHandoff,
    complete_test_lifecycle,
)


NOW = datetime(2026, 9, 2, 10, 0, tzinfo=timezone.utc)
# Deliberately too short to resemble or be mistaken for an issued provider key.
KEY_ID = "rzp_test_x"
KEY_SECRET = "execution-provider-secret"
ORDER_ID = "order_Execution123"
PAYMENT_ID = "pay_Execution123"
REFUND_ID = "rfnd_Execution123"
OPERATION_ID = "prepared_execution_123"
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


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
        transaction_id="tx-d-prepared-execution",
        merchant_id="merchant-d-prepared-execution",
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


def _refund_response(transaction: TransactionBinding, status: str) -> dict[str, object]:
    return {
        "id": REFUND_ID,
        "entity": "refund",
        "amount": transaction.amount_minor,
        "currency": transaction.currency,
        "payment_id": PAYMENT_ID,
        "status": status,
    }


def _provider_responses(
    transaction: TransactionBinding,
    *,
    refund_status: str = "processed",
):
    order = {
        "id": ORDER_ID,
        "entity": "order",
        "amount": transaction.amount_minor,
        "currency": transaction.currency,
        "receipt": "ec_d_execution",
        "status": "attempted",
        "notes": _notes(transaction),
    }

    def payment(status):
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

    return (
        order,
        payment("authorized"),
        payment("authorized"),
        payment("captured"),
        payment("captured"),
        _refund_response(transaction, refund_status),
    )


def _operation() -> PreparedRazorpayTestOperation:
    transaction = _transaction()
    handoff = RazorpayCheckoutHandoff.create(
        public_key_id=KEY_ID,
        transaction=transaction,
        order=RazorpayOrderResult(
            transaction_id=transaction.transaction_id,
            transaction_digest=transaction.digest(),
            amount_minor=transaction.amount_minor,
            currency=transaction.currency,
            order_id=ORDER_ID,
            receipt="ec_d_execution",
            provider_status="created",
        ),
        created_at=NOW,
        expires_at=NOW + timedelta(minutes=30),
    )
    signature = hmac.new(
        KEY_SECRET.encode("utf-8"),
        f"{ORDER_ID}|{PAYMENT_ID}".encode("utf-8"),
        sha256,
    ).hexdigest()
    return PreparedRazorpayTestOperation.create(
        operation_id=OPERATION_ID,
        handoff=handoff,
        callback=RazorpayCheckoutCallback(
            razorpay_order_id=ORDER_ID,
            razorpay_payment_id=PAYMENT_ID,
            razorpay_signature=signature,
        ),
    )


def _ledger(path):
    return SQLiteIdempotencyLedger(
        path,
        codec=JSONResultCodec({
            "RazorpayOrderResult": RazorpayOrderResult,
            "RazorpayPaymentResult": RazorpayPaymentResult,
            "TestExecutionResult": TestExecutionResult,
        }),
    )


def test_prepared_adapter_executes_once_and_replays_across_restart(tmp_path):
    database = tmp_path / "execution-state.sqlite3"
    shared_state = SQLiteJSONStateStore(database)
    ledger = _ledger(database)
    transport = FakeTransport(*_provider_responses(_transaction()))
    payment_adapter = RazorpayTestPaymentAdapter(
        credentials=RazorpayTestCredentials(KEY_ID, KEY_SECRET),
        transport=transport,
        idempotency=ledger,
        state_store=SQLitePaymentStateStore(shared_state),
    )
    operation = _operation()
    adapter = RazorpayPreparedTestExecutionAdapter(
        {operation.operation_id: operation},
        payment_adapter=payment_adapter,
        signing_secret=b"d-test-signing-key-at-least-32-bytes",
        commitment_store=SQLiteCommitmentStateStore(shared_state),
        idempotency=ledger,
        clock=lambda: NOW + timedelta(minutes=1),
    )

    first = adapter.execute(operation_id=OPERATION_ID, correlation_id="corr-first")
    second = adapter.execute(operation_id=OPERATION_ID, correlation_id="corr-replay")
    restarted = RazorpayPreparedTestExecutionAdapter(
        {operation.operation_id: operation},
        payment_adapter=payment_adapter,
        signing_secret=b"d-test-signing-key-at-least-32-bytes",
        commitment_store=SQLiteCommitmentStateStore(database),
        idempotency=_ledger(database),
        # A completed result remains available for reconciliation after the
        # original Checkout handoff expires; no provider call is repeated.
        clock=lambda: NOW + timedelta(hours=1),
    ).execute(operation_id=OPERATION_ID, correlation_id="corr-restart")
    lifecycle_replay_transport = FakeTransport()
    lifecycle_replay = complete_test_lifecycle(
        operation.handoff,
        operation.callback,
        adapter=RazorpayTestPaymentAdapter(
            credentials=RazorpayTestCredentials(KEY_ID, KEY_SECRET),
            transport=lifecycle_replay_transport,
            idempotency=_ledger(database),
            state_store=SQLitePaymentStateStore(database),
        ),
        now=NOW + timedelta(minutes=2),
        signing_secret=b"d-test-signing-key-at-least-32-bytes",
        commitment_store=SQLiteCommitmentStateStore(database),
    )

    assert first == second == restarted
    assert first.outcome == "TEST_MODE_CAPTURED_AND_COMPENSATED"
    assert first.real_money_moved is False
    assert first.counts_as_checkpoint_d_pass is False
    assert first.lifecycle.durable_state_backend == "SQLITE_WAL_FULL_SYNC"
    assert len(transport.calls) == 6
    assert lifecycle_replay.checkpoint_b8_lifecycle_passed is True
    assert lifecycle_replay_transport.calls == []
    assert _ledger(database).integrity_check() is True


def test_unknown_or_expired_prepared_operation_never_calls_provider(tmp_path):
    operation = _operation()
    transport = FakeTransport()
    adapter = RazorpayPreparedTestExecutionAdapter(
        {operation.operation_id: operation},
        payment_adapter=RazorpayTestPaymentAdapter(
            credentials=RazorpayTestCredentials(KEY_ID, KEY_SECRET),
            transport=transport,
        ),
        signing_secret=b"d-test-signing-key-at-least-32-bytes",
        commitment_store=SQLiteCommitmentStateStore(tmp_path / "expired.sqlite3"),
        clock=lambda: NOW + timedelta(hours=1),
    )

    with pytest.raises(TestExecutionError) as unknown:
        adapter.execute(operation_id="prepared_unknown_123", correlation_id="corr")
    with pytest.raises(TestExecutionError) as expired:
        adapter.execute(operation_id=OPERATION_ID, correlation_id="corr")

    assert unknown.value.provider_call_status == "NOT_STARTED"
    assert expired.value.code == "PREPARED_OPERATION_EXPIRED"
    assert expired.value.provider_call_status == "NOT_STARTED"
    assert transport.calls == []


def test_pending_compensation_is_not_cached_as_a_terminal_execution(tmp_path):
    database = tmp_path / "pending-state.sqlite3"
    ledger = _ledger(database)
    transport = FakeTransport(*_provider_responses(
        _transaction(),
        refund_status="pending",
    ), _refund_response(_transaction(), "pending"))
    operation = _operation()
    adapter = RazorpayPreparedTestExecutionAdapter(
        {operation.operation_id: operation},
        payment_adapter=RazorpayTestPaymentAdapter(
            credentials=RazorpayTestCredentials(KEY_ID, KEY_SECRET),
            transport=transport,
            idempotency=ledger,
            state_store=SQLitePaymentStateStore(database),
        ),
        signing_secret=b"d-test-signing-key-at-least-32-bytes",
        commitment_store=SQLiteCommitmentStateStore(database),
        idempotency=ledger,
        clock=lambda: NOW + timedelta(minutes=1),
    )

    first = adapter.execute(operation_id=OPERATION_ID, correlation_id="pending-first")
    second = adapter.execute(operation_id=OPERATION_ID, correlation_id="pending-retry")

    assert first == second
    assert first.outcome == "TEST_MODE_COMPENSATION_PENDING"
    assert first.lifecycle.refund_state == "REFUND_PENDING"
    assert first.lifecycle.commitment_stage == "COMPENSATION_PENDING"
    assert len(transport.calls) == 7
    assert transport.calls[-1]["path"] == f"/refunds/{REFUND_ID}"
    # Reserve and capture are terminal. Neither a pending refund nor the overall
    # D operation is retained as completed, so later reconciliation can advance.
    assert ledger.completed_count() == 2


def test_pending_refund_reconciles_after_handoff_expiry(tmp_path):
    database = tmp_path / "pending-expired-state.sqlite3"
    ledger = _ledger(database)
    transaction = _transaction()
    transport = FakeTransport(
        *_provider_responses(transaction, refund_status="pending"),
        _refund_response(transaction, "processed"),
    )
    operation = _operation()
    observed_now = [NOW + timedelta(minutes=1)]
    adapter = RazorpayPreparedTestExecutionAdapter(
        {operation.operation_id: operation},
        payment_adapter=RazorpayTestPaymentAdapter(
            credentials=RazorpayTestCredentials(KEY_ID, KEY_SECRET),
            transport=transport,
            idempotency=ledger,
            state_store=SQLitePaymentStateStore(database),
        ),
        signing_secret=b"d-test-signing-key-at-least-32-bytes",
        commitment_store=SQLiteCommitmentStateStore(database),
        idempotency=ledger,
        clock=lambda: observed_now[0],
    )

    first = adapter.execute(operation_id=OPERATION_ID, correlation_id="pending-first")
    observed_now[0] = NOW + timedelta(minutes=31)
    completed = adapter.execute(operation_id=OPERATION_ID, correlation_id="pending-later")

    assert first.outcome == "TEST_MODE_COMPENSATION_PENDING"
    assert completed.outcome == "TEST_MODE_CAPTURED_AND_COMPENSATED"
    assert completed.lifecycle.refund_state == "REFUNDED"
    assert completed.lifecycle.commitment_stage == "COMPENSATED"
    assert transport.calls[-1]["path"] == f"/refunds/{REFUND_ID}"
    assert len(transport.calls) == 7
    assert ledger.completed_count() == 4


def test_expired_handoff_does_not_turn_a_reservation_into_fresh_capture_authority(tmp_path):
    database = tmp_path / "expired-reserved-state.sqlite3"
    ledger = _ledger(database)
    transaction = _transaction()
    provider_responses = _provider_responses(transaction)
    transport = FakeTransport(*provider_responses[:2])
    payment_adapter = RazorpayTestPaymentAdapter(
        credentials=RazorpayTestCredentials(KEY_ID, KEY_SECRET),
        transport=transport,
        idempotency=ledger,
        state_store=SQLitePaymentStateStore(database),
    )
    operation = _operation()
    payment_adapter.reserve(
        transaction,
        order_id=ORDER_ID,
        payment_id=PAYMENT_ID,
        checkout_signature=operation.callback.razorpay_signature,
        idempotency_key=f"b8-reserve-{operation.handoff.handoff_sha256[:20]}",
    )
    adapter = RazorpayPreparedTestExecutionAdapter(
        {operation.operation_id: operation},
        payment_adapter=payment_adapter,
        signing_secret=b"d-test-signing-key-at-least-32-bytes",
        commitment_store=SQLiteCommitmentStateStore(database),
        idempotency=ledger,
        clock=lambda: NOW + timedelta(minutes=31),
    )

    with pytest.raises(TestExecutionError) as expired:
        adapter.execute(operation_id=OPERATION_ID, correlation_id="expired-reserved")

    assert expired.value.code == "PREPARED_OPERATION_EXPIRED"
    assert expired.value.provider_call_status == "NOT_STARTED"
    assert len(transport.calls) == 2


def test_prepared_operation_is_strictly_digest_bound():
    payload = _operation().model_dump(mode="json")
    payload["callback"]["razorpay_payment_id"] = "pay_Tampered123"

    with pytest.raises(ValidationError):
        PreparedRazorpayTestOperation.model_validate(payload)


def test_prepared_operation_file_requires_exact_out_of_band_pin(tmp_path):
    path = tmp_path / "prepared-operation.json"
    raw = json.dumps(
        _operation().model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    path.write_bytes(raw)
    digest = sha256(raw).hexdigest()

    assert load_prepared_test_operation(
        path,
        expected_file_sha256=digest,
    ).operation_id == OPERATION_ID
    with pytest.raises(ValueError, match="digest mismatch"):
        load_prepared_test_operation(
            path,
            expected_file_sha256="0" * 64,
        )

    duplicate = raw[:-1] + b',"schema_version":"D.RAZORPAY.OPERATION.1"}'
    path.write_bytes(duplicate)
    with pytest.raises(ValueError, match="duplicate JSON keys"):
        load_prepared_test_operation(
            path,
            expected_file_sha256=sha256(duplicate).hexdigest(),
        )


def test_prepare_cli_prints_only_redacted_operation_metadata(tmp_path):
    source = _operation()
    handoff_path = tmp_path / "handoff.json"
    callback_path = tmp_path / "callback.json"
    output_path = tmp_path / "prepared.json"
    handoff_path.write_text(source.handoff.model_dump_json(), encoding="utf-8")
    callback_path.write_text(source.callback.model_dump_json(), encoding="utf-8")

    completed = subprocess.run(
        [
            sys.executable,
            str(REPOSITORY_ROOT / "scripts" / "checkpoint_d_prepare_operation.py"),
            "--handoff",
            str(handoff_path),
            "--callback",
            str(callback_path),
            "--output",
            str(output_path),
            "--operation-id",
            OPERATION_ID,
        ],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    report = json.loads(completed.stdout)

    assert report["prepared"] is True
    assert report["callback_signature_printed"] is False
    assert source.callback.razorpay_signature not in completed.stdout
    loaded = load_prepared_test_operation(
        output_path,
        expected_file_sha256=report["prepared_operation_file_sha256"],
    )
    assert loaded == source

    repeated = subprocess.run(
        [
            sys.executable,
            str(REPOSITORY_ROOT / "scripts" / "checkpoint_d_prepare_operation.py"),
            "--handoff",
            str(handoff_path),
            "--callback",
            str(callback_path),
            "--output",
            str(output_path),
            "--operation-id",
            OPERATION_ID,
        ],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert repeated.returncode != 0
    assert "refusing to overwrite" in repeated.stderr
    assert load_prepared_test_operation(
        output_path,
        expected_file_sha256=report["prepared_operation_file_sha256"],
    ) == source
