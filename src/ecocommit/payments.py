from __future__ import annotations

from datetime import datetime
from enum import Enum
from threading import RLock
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ._canonical import sha256_hex
from .certificates import CertificateVerifier, CommitCertificate
from .commitment import CommitmentStage, CommitmentState
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
    REFUND_PENDING = "REFUND_PENDING"
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
                    self._assert_capture_authority(
                        commitment,
                        transaction=transaction,
                        certificate=certificate,
                        current=self._payments.get(
                            transaction.transaction_id,
                            PaymentSnapshot(
                                transaction_id=transaction.transaction_id,
                                state=PaymentState.NONE,
                            ),
                        ),
                    )
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
