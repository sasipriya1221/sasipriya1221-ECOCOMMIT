from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .certificates import CertificateVerifier, CommitCertificate
from .evidence import EvidenceRegistry
from .exposure import TransactionBinding


class CommitmentTransitionError(ValueError):
    pass


class CommitmentStage(str, Enum):
    PROPOSED = "PROPOSED"
    AUTHORIZED = "AUTHORIZED"
    RESERVED = "RESERVED"
    CAPTURE_ALLOWED = "CAPTURE_ALLOWED"
    CAPTURED = "CAPTURED"
    COMPENSATION_PENDING = "COMPENSATION_PENDING"
    COMPENSATED = "COMPENSATED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


class CommitmentEvent(str, Enum):
    AUTHORIZE = "AUTHORIZE"
    RESERVE = "RESERVE"
    ALLOW_CAPTURE = "ALLOW_CAPTURE"
    CAPTURE = "CAPTURE"
    CANCEL = "CANCEL"
    BEGIN_COMPENSATION = "BEGIN_COMPENSATION"
    COMPLETE_COMPENSATION = "COMPLETE_COMPENSATION"
    FAIL = "FAIL"


def _aware(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value


class TransitionRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    event_id: str = Field(min_length=1)
    event: CommitmentEvent
    from_stage: CommitmentStage
    to_stage: CommitmentStage
    occurred_at: datetime
    reference: str = Field(min_length=1)

    @field_validator("occurred_at")
    @classmethod
    def aware_occurred_at(cls, value: datetime):
        return _aware(value, "occurred_at")


class CommitmentState(BaseModel):
    model_config = ConfigDict(frozen=True)

    transaction: TransactionBinding
    stage: CommitmentStage = CommitmentStage.PROPOSED
    proposed_at: datetime
    authorization_reference: str | None = None
    reservation_reference: str | None = None
    certificate_id: str | None = None
    payment_reference: str | None = None
    compensation_reference: str | None = None
    transitions: tuple[TransitionRecord, ...] = ()

    @field_validator("proposed_at")
    @classmethod
    def aware_proposed_at(cls, value: datetime):
        return _aware(value, "proposed_at")

    @model_validator(mode="after")
    def coherent_history(self):
        event_ids = [transition.event_id for transition in self.transitions]
        if len(event_ids) != len(set(event_ids)):
            raise ValueError("commitment event ids must be unique")
        if not self.transitions:
            if self.stage != CommitmentStage.PROPOSED:
                raise ValueError("a commitment without history must be PROPOSED")
            return self
        if self.transitions[-1].to_stage != self.stage:
            raise ValueError("last transition does not match commitment stage")
        previous_stage = CommitmentStage.PROPOSED
        previous_time = self.proposed_at
        for transition in self.transitions:
            if transition.from_stage != previous_stage:
                raise ValueError("commitment transition history is discontinuous")
            if transition.occurred_at < previous_time:
                raise ValueError("commitment transition times must be monotonic")
            previous_stage = transition.to_stage
            previous_time = transition.occurred_at
        return self


class ProgressiveCommitmentEngine:
    """Explicit irreversible boundary with no generic skip-stage operation."""

    _TERMINAL = {
        CommitmentStage.COMPENSATED,
        CommitmentStage.CANCELLED,
        CommitmentStage.FAILED,
    }

    def propose(self, transaction: TransactionBinding, *, at: datetime) -> CommitmentState:
        return CommitmentState(transaction=transaction, proposed_at=_aware(at, "at"))

    def authorize(
        self,
        state: CommitmentState,
        *,
        authorization_reference: str,
        event_id: str,
        at: datetime,
    ) -> CommitmentState:
        return self._transition(
            state,
            expected=CommitmentStage.PROPOSED,
            target=CommitmentStage.AUTHORIZED,
            event=CommitmentEvent.AUTHORIZE,
            event_id=event_id,
            reference=authorization_reference,
            at=at,
            updates={"authorization_reference": authorization_reference},
        )

    def reserve(
        self,
        state: CommitmentState,
        *,
        reservation_reference: str,
        reversible: bool,
        event_id: str,
        at: datetime,
    ) -> CommitmentState:
        if not reversible:
            raise CommitmentTransitionError("RESERVED requires a reversible payment hold")
        return self._transition(
            state,
            expected=CommitmentStage.AUTHORIZED,
            target=CommitmentStage.RESERVED,
            event=CommitmentEvent.RESERVE,
            event_id=event_id,
            reference=reservation_reference,
            at=at,
            updates={"reservation_reference": reservation_reference},
        )

    def allow_capture(
        self,
        state: CommitmentState,
        *,
        certificate: CommitCertificate,
        verifier: CertificateVerifier,
        registry: EvidenceRegistry,
        event_id: str,
        at: datetime,
    ) -> CommitmentState:
        at = _aware(at, "at")
        verified = verifier.verify(
            certificate,
            expected_transaction=state.transaction,
            expected_contract_hash=state.transaction.contract_hash,
            registry=registry,
            now=at,
        )
        return self._transition(
            state,
            expected=CommitmentStage.RESERVED,
            target=CommitmentStage.CAPTURE_ALLOWED,
            event=CommitmentEvent.ALLOW_CAPTURE,
            event_id=event_id,
            reference=verified.certificate_id,
            at=at,
            updates={"certificate_id": verified.certificate_id},
        )

    def record_capture(
        self,
        state: CommitmentState,
        *,
        payment_reference: str,
        event_id: str,
        at: datetime,
    ) -> CommitmentState:
        return self._transition(
            state,
            expected=CommitmentStage.CAPTURE_ALLOWED,
            target=CommitmentStage.CAPTURED,
            event=CommitmentEvent.CAPTURE,
            event_id=event_id,
            reference=payment_reference,
            at=at,
            updates={"payment_reference": payment_reference},
        )

    def cancel(
        self,
        state: CommitmentState,
        *,
        cancellation_reference: str,
        event_id: str,
        at: datetime,
    ) -> CommitmentState:
        if state.stage not in {
            CommitmentStage.PROPOSED,
            CommitmentStage.AUTHORIZED,
            CommitmentStage.RESERVED,
            CommitmentStage.CAPTURE_ALLOWED,
        }:
            raise CommitmentTransitionError("captured or terminal commitments cannot be cancelled")
        return self._transition(
            state,
            expected=state.stage,
            target=CommitmentStage.CANCELLED,
            event=CommitmentEvent.CANCEL,
            event_id=event_id,
            reference=cancellation_reference,
            at=at,
        )

    def begin_compensation(
        self,
        state: CommitmentState,
        *,
        reason_reference: str,
        event_id: str,
        at: datetime,
    ) -> CommitmentState:
        return self._transition(
            state,
            expected=CommitmentStage.CAPTURED,
            target=CommitmentStage.COMPENSATION_PENDING,
            event=CommitmentEvent.BEGIN_COMPENSATION,
            event_id=event_id,
            reference=reason_reference,
            at=at,
        )

    def complete_compensation(
        self,
        state: CommitmentState,
        *,
        compensation_reference: str,
        event_id: str,
        at: datetime,
    ) -> CommitmentState:
        return self._transition(
            state,
            expected=CommitmentStage.COMPENSATION_PENDING,
            target=CommitmentStage.COMPENSATED,
            event=CommitmentEvent.COMPLETE_COMPENSATION,
            event_id=event_id,
            reference=compensation_reference,
            at=at,
            updates={"compensation_reference": compensation_reference},
        )

    def fail(
        self,
        state: CommitmentState,
        *,
        failure_reference: str,
        event_id: str,
        at: datetime,
    ) -> CommitmentState:
        if state.stage in self._TERMINAL:
            raise CommitmentTransitionError("terminal commitment cannot transition to FAILED")
        return self._transition(
            state,
            expected=state.stage,
            target=CommitmentStage.FAILED,
            event=CommitmentEvent.FAIL,
            event_id=event_id,
            reference=failure_reference,
            at=at,
        )

    @staticmethod
    def _transition(
        state: CommitmentState,
        *,
        expected: CommitmentStage,
        target: CommitmentStage,
        event: CommitmentEvent,
        event_id: str,
        reference: str,
        at: datetime,
        updates: dict | None = None,
    ) -> CommitmentState:
        at = _aware(at, "at")
        if not event_id or not reference:
            raise CommitmentTransitionError("event id and reference are required")

        prior = next((item for item in state.transitions if item.event_id == event_id), None)
        if prior is not None:
            if prior.event == event and prior.to_stage == target and prior.reference == reference:
                return state
            raise CommitmentTransitionError("event id was reused with a different transition")
        if state.stage != expected:
            raise CommitmentTransitionError(
                f"cannot apply {event.value} from {state.stage.value}; expected {expected.value}"
            )
        previous_time = state.transitions[-1].occurred_at if state.transitions else state.proposed_at
        if at < previous_time:
            raise CommitmentTransitionError("transition time cannot move backwards")

        record = TransitionRecord(
            event_id=event_id,
            event=event,
            from_stage=state.stage,
            to_stage=target,
            occurred_at=at,
            reference=reference,
        )
        values = {"stage": target, "transitions": (*state.transitions, record)}
        values.update(updates or {})
        return state.model_copy(update=values, deep=True)
