from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from ecocommit.commitment import (
    CommitmentStage,
    CommitmentState,
    CommitmentTransitionError,
    ProgressiveCommitmentEngine,
    SQLiteCommitmentStateStore,
)
from ecocommit.durable import (
    DurableStateConflict,
    DurableStateIntegrityError,
    JSONResultCodec,
    SQLiteIdempotencyLedger,
    SQLiteJSONStateStore,
)
from ecocommit.exposure import TransactionBinding
from ecocommit.idempotency import IdempotencyConflict
from ecocommit.payments import (
    PaymentSnapshot,
    PaymentState,
    PaymentStateConflict,
    SQLitePaymentStateStore,
    SimulatedPaymentAdapter,
    SimulatedPaymentResult,
)


NOW = datetime(2026, 9, 2, tzinfo=UTC)


def _transaction(identifier: str = "tx-durable") -> TransactionBinding:
    return TransactionBinding(
        transaction_id=identifier,
        merchant_id="merchant-durable",
        amount_minor=2_500,
        currency="INR",
        contract_hash="a" * 64,
    )


def test_sqlite_json_store_is_durable_and_rejects_stale_compare_and_swap(tmp_path):
    path = tmp_path / "state.sqlite3"
    first = SQLiteJSONStateStore(path)
    created = first.create("test", "one", {"value": 1})

    second = SQLiteJSONStateStore(path)
    observed = second.load("test", "one")
    assert observed == created

    updated = first.compare_and_swap(
        "test",
        "one",
        expected_version=created.version,
        expected_sha256=created.payload_sha256,
        value={"value": 2},
    )
    assert updated.version == 2
    assert second.load("test", "one").value == {"value": 2}

    with pytest.raises(DurableStateConflict, match="changed concurrently"):
        second.compare_and_swap(
            "test",
            "one",
            expected_version=observed.version,
            expected_sha256=observed.payload_sha256,
            value={"value": 3},
        )


def test_sqlite_json_store_detects_payload_tampering(tmp_path):
    path = tmp_path / "tampered.sqlite3"
    store = SQLiteJSONStateStore(path)
    store.create("test", "one", {"safe": True})

    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE state_documents SET payload_json = ? WHERE namespace = ?",
            ('{"safe":false}', "test"),
        )

    assert store.integrity_check() is False
    with pytest.raises(DurableStateIntegrityError, match="digest"):
        store.load("test", "one")


def test_sqlite_idempotency_replays_json_none_and_detects_collisions(tmp_path):
    path = tmp_path / "idempotency.sqlite3"
    calls = 0

    def operation():
        nonlocal calls
        calls += 1
        return None

    first = SQLiteIdempotencyLedger(path)
    assert first.execute(
        scope="capture:tx",
        key="same",
        fingerprint="f" * 64,
        operation=operation,
    ) is None

    second = SQLiteIdempotencyLedger(path)
    assert second.execute(
        scope="capture:tx",
        key="same",
        fingerprint="f" * 64,
        operation=lambda: pytest.fail("completed operation was re-executed"),
    ) is None
    assert calls == 1
    assert second.completed_count() == 1

    with pytest.raises(IdempotencyConflict, match="different request"):
        second.execute(
            scope="capture:tx",
            key="same",
            fingerprint="0" * 64,
            operation=lambda: None,
        )


def test_sqlite_idempotency_failed_operation_is_retryable(tmp_path):
    path = tmp_path / "retry.sqlite3"
    ledger = SQLiteIdempotencyLedger(path)
    calls = 0

    def operation():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("transient")
        return {"recovered": True}

    arguments = {
        "scope": "refund:tx",
        "key": "retry",
        "fingerprint": "a" * 64,
    }
    with pytest.raises(RuntimeError, match="transient"):
        ledger.execute(**arguments, operation=operation)
    assert ledger.execute(**arguments, operation=operation) == {"recovered": True}
    assert calls == 2


def test_sqlite_idempotency_detects_stored_result_tampering(tmp_path):
    path = tmp_path / "result-tamper.sqlite3"
    ledger = SQLiteIdempotencyLedger(path)
    ledger.execute(
        scope="reserve:tx",
        key="key",
        fingerprint="b" * 64,
        operation=lambda: {"safe": True},
    )
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE idempotency_operations SET result_json = ?",
            ('{"kind":"json","value":{"safe":false}}',),
        )

    assert ledger.integrity_check() is False
    with pytest.raises(DurableStateIntegrityError, match="digest"):
        ledger.execute(
            scope="reserve:tx",
            key="key",
            fingerprint="b" * 64,
            operation=lambda: None,
        )


def test_two_processes_share_one_sqlite_idempotency_result(tmp_path):
    path = tmp_path / "multiprocess.sqlite3"
    marker = tmp_path / "side-effect.txt"
    code = r'''
import json
import os
import sys
import time
from ecocommit.durable import SQLiteIdempotencyLedger

database, marker = sys.argv[1:]
ledger = SQLiteIdempotencyLedger(database, poll_seconds=0.01)
def operation():
    with open(marker, "ab", buffering=0) as stream:
        stream.write(b"executed\n")
        os.fsync(stream.fileno())
    time.sleep(0.25)
    return {"value": 7}
result = ledger.execute(
    scope="capture:multi",
    key="same",
    fingerprint="c" * 64,
    operation=operation,
)
print(json.dumps(result, sort_keys=True))
'''
    command = [sys.executable, "-c", code, str(path), str(marker)]
    first = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    time.sleep(0.05)
    second = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    first_out, first_err = first.communicate(timeout=10)
    second_out, second_err = second.communicate(timeout=10)

    assert (first.returncode, second.returncode) == (0, 0), first_err + second_err
    assert json.loads(first_out) == json.loads(second_out) == {"value": 7}
    assert marker.read_text(encoding="utf-8").splitlines() == ["executed"]


def test_payment_state_survives_adapter_restart_and_replays_typed_result(tmp_path):
    path = tmp_path / "payment.sqlite3"
    codec = JSONResultCodec({"SimulatedPaymentResult": SimulatedPaymentResult})
    transaction = _transaction("tx-payment-restart")
    first = SimulatedPaymentAdapter(
        idempotency=SQLiteIdempotencyLedger(path, codec=codec),
        state_store=SQLitePaymentStateStore(path),
    )
    reserved = first.reserve(transaction, idempotency_key="reserve-once")

    second = SimulatedPaymentAdapter(
        idempotency=SQLiteIdempotencyLedger(path, codec=codec),
        state_store=SQLitePaymentStateStore(path),
    )
    replayed = second.reserve(transaction, idempotency_key="reserve-once")

    assert isinstance(replayed, SimulatedPaymentResult)
    assert replayed == reserved
    assert second.snapshot(transaction.transaction_id).state == PaymentState.RESERVED


def test_payment_state_recovers_when_state_commits_before_idempotency_result(tmp_path):
    class CrashAfterOperationLedger:
        def execute(self, *, operation, **_):
            operation()
            raise RuntimeError("crash after durable state commit")

        def completed_count(self):
            return 0

    path = tmp_path / "payment-crash-window.sqlite3"
    transaction = _transaction("tx-payment-crash-window")
    state_store = SQLitePaymentStateStore(path)
    first = SimulatedPaymentAdapter(
        idempotency=CrashAfterOperationLedger(),
        state_store=state_store,
    )

    with pytest.raises(RuntimeError, match="crash after durable state commit"):
        first.reserve(transaction, idempotency_key="reserve-once")
    assert state_store.get(transaction.transaction_id).state == PaymentState.RESERVED

    codec = JSONResultCodec({"SimulatedPaymentResult": SimulatedPaymentResult})
    second = SimulatedPaymentAdapter(
        idempotency=SQLiteIdempotencyLedger(path, codec=codec),
        state_store=SQLitePaymentStateStore(path),
    )
    recovered = second.reserve(transaction, idempotency_key="reserve-once")

    assert recovered.state == PaymentState.RESERVED
    assert SQLiteIdempotencyLedger(path, codec=codec).completed_count() == 1


def test_payment_state_store_rejects_stale_cross_process_snapshot(tmp_path):
    path = tmp_path / "payment-cas.sqlite3"
    first = SQLitePaymentStateStore(path)
    second = SQLitePaymentStateStore(path)
    initial = PaymentSnapshot(
        transaction_id="tx-cas",
        state=PaymentState.RESERVED,
        amount_minor=100,
        currency="INR",
        transaction_digest="d" * 64,
        last_reference="reserve",
    )
    first.compare_and_set("tx-cas", expected=None, updated=initial)
    stale = second.get("tx-cas")
    first.compare_and_set(
        "tx-cas",
        expected=initial,
        updated=initial.model_copy(update={"state": PaymentState.CAPTURED}),
    )

    with pytest.raises(PaymentStateConflict, match="changed concurrently"):
        second.compare_and_set(
            "tx-cas",
            expected=stale,
            updated=stale.model_copy(update={"state": PaymentState.VOIDED}),
        )


def test_commitment_history_survives_restart_and_rejects_stale_transition(tmp_path):
    path = tmp_path / "commitment.sqlite3"
    transaction = _transaction("tx-commitment-restart")
    first_store = SQLiteCommitmentStateStore(path)
    first = ProgressiveCommitmentEngine(state_store=first_store)
    proposed = first.propose(transaction, at=NOW)
    authorized = first.authorize(
        proposed,
        authorization_reference="auth-1",
        event_id="authorize-1",
        at=NOW + timedelta(seconds=1),
    )

    second = ProgressiveCommitmentEngine(
        state_store=SQLiteCommitmentStateStore(path)
    )
    resumed = second.resume_or_propose(transaction, at=NOW + timedelta(seconds=2))
    assert resumed == authorized
    reserved = second.reserve(
        resumed,
        reservation_reference="reserve-1",
        reversible=True,
        event_id="reserve-1",
        at=NOW + timedelta(seconds=2),
    )
    assert reserved.stage == CommitmentStage.RESERVED

    third = ProgressiveCommitmentEngine(
        state_store=SQLiteCommitmentStateStore(path)
    )
    assert third.resume_or_propose(
        transaction,
        at=NOW + timedelta(seconds=3),
    ) == reserved

    with pytest.raises(CommitmentTransitionError, match="changed concurrently"):
        first.cancel(
            authorized,
            cancellation_reference="stale-cancel",
            event_id="cancel-stale",
            at=NOW + timedelta(seconds=3),
        )


def test_durable_payment_and_commitment_models_reject_unknown_fields():
    payment = PaymentSnapshot(
        transaction_id="tx-strict-state",
        state=PaymentState.RESERVED,
        amount_minor=100,
        currency="INR",
        transaction_digest="e" * 64,
        last_reference="reserve-strict",
    ).model_dump(mode="json")
    payment["caller_authority"] = True
    with pytest.raises(ValidationError):
        PaymentSnapshot.model_validate(payment)

    commitment = ProgressiveCommitmentEngine().propose(
        _transaction("tx-strict-commitment"),
        at=NOW,
    ).model_dump(mode="json")
    commitment["skip_to_capture"] = True
    with pytest.raises(ValidationError):
        CommitmentState.model_validate(commitment)


def test_result_codec_rejects_non_string_model_registry_key_from_storage():
    codec = JSONResultCodec({"SimulatedPaymentResult": SimulatedPaymentResult})

    with pytest.raises(DurableStateIntegrityError, match="model name"):
        codec.decode('{"kind":"pydantic","model":[],"value":{}}')
