from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

from .commitment import (
    CommitmentEvent,
    CommitmentStage,
    CommitmentState,
    ProgressiveCommitmentEngine,
)
from .payments import (
    PaymentSnapshot,
    PaymentState,
    PaymentStateError,
    SimulatedPaymentAdapter,
    SimulatedPaymentFailure,
    SimulatedPaymentResult,
)


class CompensationError(ValueError):
    pass


class ReconciliationSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class ReconciliationFinding(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str
    severity: ReconciliationSeverity
    message: str
    requires_compensation: bool = False


class ReconciliationReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    transaction_id: str
    checked_at: datetime
    commitment_stage: CommitmentStage
    payment_state: PaymentState
    in_sync: bool
    findings: tuple[ReconciliationFinding, ...]
    payment_simulated: bool

    @field_validator("checked_at")
    @classmethod
    def aware_checked_at(cls, value: datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("checked_at must be timezone-aware")
        return value


class Reconciler:
    def reconcile(
        self,
        commitment: CommitmentState,
        payment: PaymentSnapshot,
        *,
        now: datetime,
    ) -> ReconciliationReport:
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("now must be timezone-aware")
        findings: list[ReconciliationFinding] = []

        if payment.transaction_id != commitment.transaction.transaction_id:
            findings.append(self._critical("TRANSACTION_ID_MISMATCH", "payment belongs to another transaction"))
        if payment.state != PaymentState.NONE and payment.transaction_digest != commitment.transaction.digest():
            findings.append(self._critical("TRANSACTION_BINDING_MISMATCH", "payment binding changed after activity"))

        expected = self._expected_states(commitment)
        if payment.state not in expected:
            findings.append(self._state_finding(commitment.stage, payment.state))

        return ReconciliationReport(
            transaction_id=commitment.transaction.transaction_id,
            checked_at=now,
            commitment_stage=commitment.stage,
            payment_state=payment.state,
            in_sync=not findings,
            findings=tuple(findings),
            payment_simulated=payment.simulated,
        )

    @staticmethod
    def _expected_states(commitment: CommitmentState) -> set[PaymentState]:
        stage = commitment.stage
        if stage in {CommitmentStage.PROPOSED, CommitmentStage.AUTHORIZED}:
            return {PaymentState.NONE}
        if stage in {CommitmentStage.RESERVED, CommitmentStage.CAPTURE_ALLOWED}:
            return {PaymentState.RESERVED}
        if stage == CommitmentStage.CAPTURED:
            return {PaymentState.CAPTURED}
        if stage == CommitmentStage.COMPENSATION_PENDING:
            # A refund can succeed just before its state transition is journaled.
            return {
                PaymentState.CAPTURED,
                PaymentState.REFUND_PENDING,
                PaymentState.REFUNDED,
            }
        if stage == CommitmentStage.COMPENSATED:
            return {PaymentState.REFUNDED}
        if stage == CommitmentStage.CANCELLED:
            cancelled_from = commitment.transitions[-1].from_stage
            if cancelled_from in {CommitmentStage.RESERVED, CommitmentStage.CAPTURE_ALLOWED}:
                return {PaymentState.VOIDED}
            return {PaymentState.NONE}
        # FAILED is intentionally conservative: held funds require cleanup and
        # captured funds require compensation, handled as findings below.
        return {PaymentState.NONE, PaymentState.VOIDED, PaymentState.REFUNDED}

    def _state_finding(
        self,
        stage: CommitmentStage,
        payment_state: PaymentState,
    ) -> ReconciliationFinding:
        if stage == CommitmentStage.COMPENSATED and payment_state != PaymentState.REFUNDED:
            return self._critical("REFUND_MISSING", "commitment says compensated but payment is not refunded")
        if stage == CommitmentStage.CAPTURED:
            return self._critical("CAPTURE_MISSING", f"commitment says CAPTURED but payment is {payment_state.value}")
        if payment_state == PaymentState.CAPTURED:
            return self._critical(
                "UNEXPECTED_CAPTURE",
                f"payment is CAPTURED while commitment is {stage.value}",
                compensate=True,
            )
        if payment_state == PaymentState.REFUND_PENDING:
            return ReconciliationFinding(
                code="REFUND_PENDING",
                severity=ReconciliationSeverity.WARNING,
                message="provider accepted the refund but has not confirmed completion",
            )
        if stage in {CommitmentStage.RESERVED, CommitmentStage.CAPTURE_ALLOWED}:
            return ReconciliationFinding(
                code="RESERVATION_STATE_MISMATCH",
                severity=ReconciliationSeverity.WARNING,
                message=f"expected a reversible reservation, found {payment_state.value}",
            )
        if stage == CommitmentStage.CANCELLED and payment_state == PaymentState.RESERVED:
            return ReconciliationFinding(
                code="VOID_MISSING",
                severity=ReconciliationSeverity.WARNING,
                message="cancelled commitment still has a reserved payment",
            )
        if stage == CommitmentStage.FAILED and payment_state == PaymentState.RESERVED:
            return ReconciliationFinding(
                code="FAILED_RESERVATION_NEEDS_VOID",
                severity=ReconciliationSeverity.WARNING,
                message="failed commitment still has a reserved payment",
            )
        return ReconciliationFinding(
            code="PAYMENT_STATE_MISMATCH",
            severity=ReconciliationSeverity.WARNING,
            message=f"payment state {payment_state.value} does not match commitment {stage.value}",
        )

    @staticmethod
    def _critical(code: str, message: str, *, compensate: bool = False) -> ReconciliationFinding:
        return ReconciliationFinding(
            code=code,
            severity=ReconciliationSeverity.CRITICAL,
            message=message,
            requires_compensation=compensate,
        )


class CompensationOutcome(BaseModel):
    model_config = ConfigDict(frozen=True)

    simulated: Literal[True] = True
    succeeded: bool
    state: CommitmentState
    payment_result: SimulatedPaymentResult | None = None
    error: str | None = None
    reconciled_existing_refund: bool = False


class CompensationCoordinator:
    """Retry-safe full-refund compensation against the explicit simulator."""

    def __init__(
        self,
        *,
        engine: ProgressiveCommitmentEngine,
        payments: SimulatedPaymentAdapter,
    ):
        self.engine = engine
        self.payments = payments

    def compensate(
        self,
        state: CommitmentState,
        *,
        reason_reference: str,
        idempotency_key: str,
        at: datetime,
    ) -> CompensationOutcome:
        payment = self.payments.snapshot(state.transaction.transaction_id)
        if state.stage == CommitmentStage.CAPTURE_ALLOWED:
            if (
                payment.state != PaymentState.CAPTURED
                or payment.transaction_digest != state.transaction.digest()
                or not payment.last_reference
            ):
                raise CompensationError(
                    "CAPTURE_ALLOWED compensation requires a reconciled captured payment"
                )
            state = self.engine.record_capture(
                state,
                payment_reference=payment.last_reference,
                event_id=f"compensation:{idempotency_key}:reconcile-capture",
                at=at,
            )

        if state.stage == CommitmentStage.CAPTURED:
            pending = self.engine.begin_compensation(
                state,
                reason_reference=reason_reference,
                event_id=f"compensation:{idempotency_key}:begin",
                at=at,
            )
        elif state.stage == CommitmentStage.COMPENSATION_PENDING:
            pending = state
            begin = next(
                (
                    transition
                    for transition in reversed(state.transitions)
                    if transition.event == CommitmentEvent.BEGIN_COMPENSATION
                ),
                None,
            )
            if begin is None or begin.reference != reason_reference:
                raise CompensationError(
                    "compensation retry reason must match the pending compensation"
                )
        else:
            raise CompensationError("compensation requires CAPTURED or COMPENSATION_PENDING state")

        payment = self.payments.snapshot(pending.transaction.transaction_id)
        if payment.state == PaymentState.REFUNDED:
            if (
                payment.transaction_digest != pending.transaction.digest()
                or not payment.last_reference
            ):
                raise CompensationError(
                    "existing refund cannot be reconciled to the pending transaction"
                )
            completed = self.engine.complete_compensation(
                pending,
                compensation_reference=payment.last_reference,
                event_id=f"compensation:{idempotency_key}:complete",
                at=at,
            )
            return CompensationOutcome(
                succeeded=True,
                state=completed,
                reconciled_existing_refund=True,
            )

        try:
            result = self.payments.refund(
                pending.transaction,
                idempotency_key=idempotency_key,
            )
        except (SimulatedPaymentFailure, PaymentStateError) as exc:
            return CompensationOutcome(
                succeeded=False,
                state=pending,
                error=str(exc),
            )

        completed = self.engine.complete_compensation(
            pending,
            compensation_reference=result.provider_reference,
            event_id=f"compensation:{idempotency_key}:complete",
            at=at,
        )
        return CompensationOutcome(
            succeeded=True,
            state=completed,
            payment_result=result,
        )
