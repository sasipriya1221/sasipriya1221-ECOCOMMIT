from __future__ import annotations

from datetime import datetime
from enum import Enum
from threading import RLock
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ._canonical import sha256_hex
from .certificates import CertificateVerifier, CommitCertificate
from .evidence import EvidenceRegistry
from .exposure import TransactionBinding
from .idempotency import IdempotencyLedger, request_fingerprint


class PaymentStateError(RuntimeError):
    pass


class SimulatedPaymentFailure(RuntimeError):
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
    REFUNDED = "REFUNDED"


class SimulatedPaymentResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    simulated: Literal[True] = True
    adapter_name: Literal["SIMULATED_LOCAL"] = "SIMULATED_LOCAL"
    transaction_id: str
    operation: PaymentOperation
    state: PaymentState
    amount_minor: int = Field(gt=0)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    provider_reference: str = Field(pattern=r"^sim_[0-9a-f]{24}$")


class PaymentSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    simulated: Literal[True] = True
    adapter_name: Literal["SIMULATED_LOCAL"] = "SIMULATED_LOCAL"
    transaction_id: str
    state: PaymentState
    amount_minor: int | None = Field(default=None, gt=0)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    transaction_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    last_reference: str | None = None


class SimulatedPaymentAdapter:
    """Explicit local simulator. It does not claim Razorpay/API execution."""

    is_simulation: Literal[True] = True
    adapter_name: Literal["SIMULATED_LOCAL"] = "SIMULATED_LOCAL"

    def __init__(self, *, idempotency: IdempotencyLedger | None = None):
        self._idempotency = idempotency or IdempotencyLedger()
        self._payments: dict[str, PaymentSnapshot] = {}
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
            return self._payments.get(
                transaction_id,
                PaymentSnapshot(transaction_id=transaction_id, state=PaymentState.NONE),
            ).model_copy(deep=True)

    def _execute(
        self,
        operation: PaymentOperation,
        transaction: TransactionBinding,
        idempotency_key: str,
        *,
        certificate: CommitCertificate | None = None,
        verifier: CertificateVerifier | None = None,
        registry: EvidenceRegistry | None = None,
        now: datetime | None = None,
    ) -> SimulatedPaymentResult:
        fingerprint = request_fingerprint(
            {
                "operation": operation.value,
                "transaction": transaction,
                "certificate_id": certificate.certificate_id if certificate else None,
            }
        )

        def perform() -> SimulatedPaymentResult:
            with self._lock:
                if operation in self._fail_operations:
                    raise SimulatedPaymentFailure(
                        f"injected SIMULATED_LOCAL failure for {operation.value}"
                    )
                if operation == PaymentOperation.CAPTURE:
                    if certificate is None or verifier is None or registry is None or now is None:
                        raise PaymentStateError("CAPTURE requires a transaction-bound commit certificate")
                    verifier.verify(
                        certificate,
                        expected_transaction=transaction,
                        expected_contract_hash=transaction.contract_hash,
                        registry=registry,
                        now=now,
                    )
                current = self._payments.get(
                    transaction.transaction_id,
                    PaymentSnapshot(transaction_id=transaction.transaction_id, state=PaymentState.NONE),
                )
                self._assert_transaction_unchanged(current, transaction)
                expected, target = {
                    PaymentOperation.RESERVE: (PaymentState.NONE, PaymentState.RESERVED),
                    PaymentOperation.CAPTURE: (PaymentState.RESERVED, PaymentState.CAPTURED),
                    PaymentOperation.VOID: (PaymentState.RESERVED, PaymentState.VOIDED),
                    PaymentOperation.REFUND: (PaymentState.CAPTURED, PaymentState.REFUNDED),
                }[operation]
                if current.state != expected:
                    raise PaymentStateError(
                        f"cannot {operation.value} simulated payment from {current.state.value}"
                    )
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
                self._payments[transaction.transaction_id] = PaymentSnapshot(
                    transaction_id=transaction.transaction_id,
                    state=target,
                    amount_minor=transaction.amount_minor,
                    currency=transaction.currency,
                    transaction_digest=transaction.digest(),
                    last_reference=reference,
                )
                return result

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
