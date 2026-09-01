from __future__ import annotations

from datetime import datetime
from enum import Enum
from threading import RLock
from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ._canonical import sha256_hex
from .certificates import CertificateVerifier, CommitCertificate
from .commitment import CommitmentStage, CommitmentState
from .durable import DurableStateConflict, SQLiteJSONStateStore
from .evidence import EvidenceRegistry
from .exposure import TransactionBinding
from .idempotency import IdempotencyBackend, IdempotencyLedger, request_fingerprint


class PaymentStateError(RuntimeError):
    pass


class PaymentStateConflict(PaymentStateError):
    pass


class PaymentProviderError(RuntimeError):
    """A safe operational provider/adapter failure at the payment boundary."""


class SimulatedPaymentFailure(PaymentProviderError):
    pass


class PaymentOperation(str, Enum):
    RESERVE = "RESERVE"
    CAPTURE = "CAPTURE"
    VOID = "VOID"
    REFUND = "REFUND"


class PaymentState(str, Enum):
    NONE = "NONE"
    RESERVED = "RESERVED"
    CAPTURED = "CAPTURED"
    VOIDED = "VOIDED"
    REFUND_PENDING = "REFUND_PENDING"
    REFUNDED = "REFUNDED"


class PaymentResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    simulated: bool
    adapter_name: Literal["SIMULATED_LOCAL", "RAZORPAY_TEST_MODE"]
    transaction_id: str
    operation: PaymentOperation
    state: PaymentState
    amount_minor: int = Field(gt=0)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    provider_reference: str = Field(min_length=1)


class SimulatedPaymentResult(PaymentResult):
    model_config = ConfigDict(frozen=True, extra="forbid")

    simulated: Literal[True] = True
    adapter_name: Literal["SIMULATED_LOCAL"] = "SIMULATED_LOCAL"
    provider_reference: str = Field(pattern=r"^sim_[0-9a-f]{24}$")


class PaymentSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    simulated: bool = True
    adapter_name: Literal["SIMULATED_LOCAL", "RAZORPAY_TEST_MODE"] = "SIMULATED_LOCAL"
    transaction_id: str
    state: PaymentState
    amount_minor: int | None = Field(default=None, gt=0)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    transaction_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    last_reference: str | None = None
    order_id: str | None = Field(default=None, pattern=r"^order_[A-Za-z0-9]+$")
    payment_id: str | None = Field(default=None, pattern=r"^pay_[A-Za-z0-9]+$")
    refund_id: str | None = Field(default=None, pattern=r"^rfnd_[A-Za-z0-9]+$")

    @model_validator(mode="after")
    def coherent_adapter_identity(self):
        if self.simulated != (self.adapter_name == "SIMULATED_LOCAL"):
            raise ValueError("payment simulation flag and adapter name disagree")
        if self.adapter_name == "RAZORPAY_TEST_MODE" and self.state != PaymentState.NONE:
            if self.order_id is None or self.payment_id is None:
                raise ValueError("Razorpay payment activity requires order and payment identifiers")
        return self


class PaymentStateStore(Protocol):
    def get(self, transaction_id: str) -> PaymentSnapshot | None: ...

    def compare_and_set(
        self,
        transaction_id: str,
        *,
        expected: PaymentSnapshot | None,
        updated: PaymentSnapshot,
    ) -> None: ...


class InMemoryPaymentStateStore:
    def __init__(self) -> None:
        self._values: dict[str, PaymentSnapshot] = {}
        self._lock = RLock()

    def get(self, transaction_id: str) -> PaymentSnapshot | None:
        with self._lock:
            value = self._values.get(transaction_id)
            return None if value is None else value.model_copy(deep=True)

    def compare_and_set(
        self,
        transaction_id: str,
        *,
        expected: PaymentSnapshot | None,
        updated: PaymentSnapshot,
    ) -> None:
        if updated.transaction_id != transaction_id:
            raise PaymentStateConflict("payment state transaction id does not match")
        with self._lock:
            current = self._values.get(transaction_id)
            if current != expected:
                raise PaymentStateConflict("payment state changed concurrently")
            self._values[transaction_id] = updated.model_copy(deep=True)


class SQLitePaymentStateStore:
    """Durable PaymentSnapshot storage with optimistic cross-process updates."""

    _NAMESPACE = "payment-snapshots-v1"

    def __init__(
        self,
        path_or_store: str | Path | SQLiteJSONStateStore,
    ) -> None:
        self._store = (
            path_or_store
            if isinstance(path_or_store, SQLiteJSONStateStore)
            else SQLiteJSONStateStore(path_or_store)
        )

    def get(self, transaction_id: str) -> PaymentSnapshot | None:
        document = self._store.load(self._NAMESPACE, transaction_id)
        if document is None:
            return None
        try:
            return PaymentSnapshot.model_validate(document.value)
        except ValueError as exc:
            raise PaymentStateError("durable payment state is invalid") from exc

    def compare_and_set(
        self,
        transaction_id: str,
        *,
        expected: PaymentSnapshot | None,
        updated: PaymentSnapshot,
    ) -> None:
        if updated.transaction_id != transaction_id:
            raise PaymentStateConflict("payment state transaction id does not match")
        document = self._store.load(self._NAMESPACE, transaction_id)
        try:
            if expected is None:
                if document is not None:
                    raise PaymentStateConflict("payment state changed concurrently")
                self._store.create(
                    self._NAMESPACE,
                    transaction_id,
                    updated.model_dump(mode="json"),
                )
                return
            if document is None:
                raise PaymentStateConflict("payment state disappeared")
            current = PaymentSnapshot.model_validate(document.value)
            if current != expected:
                raise PaymentStateConflict("payment state changed concurrently")
            self._store.compare_and_swap(
                self._NAMESPACE,
                transaction_id,
                expected_version=document.version,
                expected_sha256=document.payload_sha256,
                value=updated.model_dump(mode="json"),
            )
        except DurableStateConflict as exc:
            raise PaymentStateConflict("payment state changed concurrently") from exc


class SimulatedPaymentAdapter:
    """Explicit local simulator. It does not claim Razorpay/API execution."""

    is_simulation: Literal[True] = True
    adapter_name: Literal["SIMULATED_LOCAL"] = "SIMULATED_LOCAL"

    def __init__(
        self,
        *,
        idempotency: IdempotencyBackend | None = None,
        state_store: PaymentStateStore | None = None,
    ):
        self._idempotency = idempotency or IdempotencyLedger()
        self._state_store = state_store or InMemoryPaymentStateStore()
        self._fail_operations: set[PaymentOperation] = set()
        self._lock = RLock()

    def set_failure(self, operation: PaymentOperation, *, enabled: bool) -> None:
        with self._lock:
            if enabled:
                self._fail_operations.add(operation)
            else:
                self._fail_operations.discard(operation)

    def reserve(self, transaction: TransactionBinding, *, idempotency_key: str) -> SimulatedPaymentResult:
        return self._execute(PaymentOperation.RESERVE, transaction, idempotency_key)

    def capture(
        self,
        transaction: TransactionBinding,
        *,
        commitment: CommitmentState,
        certificate: CommitCertificate,
        verifier: CertificateVerifier,
        registry: EvidenceRegistry,
        now: datetime,
        idempotency_key: str,
    ) -> SimulatedPaymentResult:
        return self._execute(
            PaymentOperation.CAPTURE,
            transaction,
            idempotency_key,
            commitment=commitment,
            certificate=certificate,
            verifier=verifier,
            registry=registry,
            now=now,
        )

    def void(self, transaction: TransactionBinding, *, idempotency_key: str) -> SimulatedPaymentResult:
        return self._execute(PaymentOperation.VOID, transaction, idempotency_key)

    def refund(self, transaction: TransactionBinding, *, idempotency_key: str) -> SimulatedPaymentResult:
        return self._execute(PaymentOperation.REFUND, transaction, idempotency_key)

    def snapshot(self, transaction_id: str) -> PaymentSnapshot:
        with self._lock:
            current = self._state_store.get(transaction_id)
            return (
                current
                if current is not None
                else PaymentSnapshot(transaction_id=transaction_id, state=PaymentState.NONE)
            ).model_copy(deep=True)

    def _execute(
        self,
        operation: PaymentOperation,
        transaction: TransactionBinding,
        idempotency_key: str,
        *,
        commitment: CommitmentState | None = None,
        certificate: CommitCertificate | None = None,
        verifier: CertificateVerifier | None = None,
        registry: EvidenceRegistry | None = None,
        now: datetime | None = None,
    ) -> SimulatedPaymentResult:
        fingerprint = request_fingerprint(
            {
                "operation": operation.value,
                "transaction": transaction,
                "commitment": commitment,
                # The complete signed request is part of idempotency identity.
                # A tampered signature with the same certificate id must collide,
                # not replay an earlier successful result.
                "certificate": certificate,
            }
        )

        def perform_locked() -> SimulatedPaymentResult:
            with self._lock:
                if operation in self._fail_operations:
                    raise SimulatedPaymentFailure(
                        f"injected SIMULATED_LOCAL failure for {operation.value}"
                    )
                if operation == PaymentOperation.CAPTURE:
                    if (
                        commitment is None
                        or certificate is None
                        or verifier is None
                        or registry is None
                        or now is None
                    ):
                        raise PaymentStateError(
                            "CAPTURE requires CAPTURE_ALLOWED commitment and commit certificate"
                        )
                    current = self._state_store.get(transaction.transaction_id)
                    self._assert_capture_authority(
                        commitment,
                        transaction=transaction,
                        certificate=certificate,
                        current=(
                            current
                            if current is not None
                            else PaymentSnapshot(
                                transaction_id=transaction.transaction_id,
                                state=PaymentState.NONE,
                            )
                        ),
                    )
                    verifier.verify(
                        certificate,
                        expected_transaction=transaction,
                        expected_contract_hash=transaction.contract_hash,
                        registry=registry,
                        now=now,
                    )
                stored_current = self._state_store.get(transaction.transaction_id)
                current = stored_current or PaymentSnapshot(
                    transaction_id=transaction.transaction_id,
                    state=PaymentState.NONE,
                )
                self._assert_transaction_unchanged(current, transaction)
                expected, target = {
                    PaymentOperation.RESERVE: (PaymentState.NONE, PaymentState.RESERVED),
                    PaymentOperation.CAPTURE: (PaymentState.RESERVED, PaymentState.CAPTURED),
                    PaymentOperation.VOID: (PaymentState.RESERVED, PaymentState.VOIDED),
                    PaymentOperation.REFUND: (PaymentState.CAPTURED, PaymentState.REFUNDED),
                }[operation]
                reference = "sim_" + sha256_hex(
                    {
                        "operation": operation.value,
                        "transaction": transaction,
                        "idempotency_key": idempotency_key,
                    }
                )[:24]
                result = SimulatedPaymentResult(
                    transaction_id=transaction.transaction_id,
                    operation=operation,
                    state=target,
                    amount_minor=transaction.amount_minor,
                    currency=transaction.currency,
                    provider_reference=reference,
                )
                if current.state == target and current.last_reference == reference:
                    # The durable state mutation may have committed immediately
                    # before a crash prevented the idempotency row from being
                    # marked complete. Reconstruct only the exact deterministic
                    # result for the same request identity.
                    return result
                if current.state != expected:
                    raise PaymentStateError(
                        f"cannot {operation.value} simulated payment from {current.state.value}"
                    )
                updated = PaymentSnapshot(
                    transaction_id=transaction.transaction_id,
                    state=target,
                    amount_minor=transaction.amount_minor,
                    currency=transaction.currency,
                    transaction_digest=transaction.digest(),
                    last_reference=reference,
                )
                self._state_store.compare_and_set(
                    transaction.transaction_id,
                    expected=stored_current,
                    updated=updated,
                )
                return result

        def perform() -> SimulatedPaymentResult:
            if operation != PaymentOperation.CAPTURE:
                return perform_locked()
            if (
                commitment is None
                or certificate is None
                or verifier is None
                or registry is None
                or now is None
            ):
                raise PaymentStateError(
                    "CAPTURE requires CAPTURE_ALLOWED commitment and commit certificate"
                )

            # Hold the evidence registry version lock from the final freshness
            # check through the simulated irreversible mutation. A concurrent
            # revoke/superseding version can land immediately after capture, but
            # never between verification and that boundary.
            with registry.hold_snapshot_current(certificate.evidence_snapshot, now=now):
                return perform_locked()

        return self._idempotency.execute(
            scope=f"SIMULATED_LOCAL:{transaction.transaction_id}:{operation.value}",
            key=idempotency_key,
            fingerprint=fingerprint,
            operation=perform,
        )

    @staticmethod
    def _assert_transaction_unchanged(
        current: PaymentSnapshot,
        transaction: TransactionBinding,
    ) -> None:
        if current.state == PaymentState.NONE:
            return
        if current.transaction_digest != transaction.digest():
            raise PaymentStateError("transaction binding changed after payment activity")

    @staticmethod
    def _assert_capture_authority(
        commitment: CommitmentState,
        *,
        transaction: TransactionBinding,
        certificate: CommitCertificate,
        current: PaymentSnapshot,
    ) -> None:
        if commitment.stage != CommitmentStage.CAPTURE_ALLOWED:
            raise PaymentStateError("CAPTURE requires commitment stage CAPTURE_ALLOWED")
        if commitment.transaction != transaction:
            raise PaymentStateError("commitment transaction binding does not match capture")
        if commitment.certificate_id != certificate.certificate_id:
            raise PaymentStateError("commitment certificate does not match capture certificate")
        if current.state == PaymentState.RESERVED and (
            not commitment.reservation_reference
            or commitment.reservation_reference != current.last_reference
        ):
            raise PaymentStateError("commitment reservation does not match the payment hold")
