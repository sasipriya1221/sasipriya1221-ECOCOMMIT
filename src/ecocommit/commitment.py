from __future__ import annotations

from datetime import datetime
from enum import Enum
from pathlib import Path
from threading import RLock
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .certificates import CertificateVerifier, CommitCertificate
from .durable import DurableStateConflict, SQLiteJSONStateStore
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
    model_config = ConfigDict(frozen=True, extra="forbid")

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
    model_config = ConfigDict(frozen=True, extra="forbid")

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
            if any(
                reference is not None
                for reference in (
                    self.authorization_reference,
                    self.reservation_reference,
                    self.certificate_id,
                    self.payment_reference,
                    self.compensation_reference,
                )
            ):
                raise ValueError("a proposed commitment cannot contain transition references")
            return self
        if self.transitions[-1].to_stage != self.stage:
            raise ValueError("last transition does not match commitment stage")
        previous_stage = CommitmentStage.PROPOSED
        previous_time = self.proposed_at
        for transition in self.transitions:
            if transition.from_stage != previous_stage:
                raise ValueError("commitment transition history is discontinuous")
            if not self._transition_is_legal(transition):
                raise ValueError(
                    f"illegal commitment history transition: {transition.event.value} "
                    f"{transition.from_stage.value}->{transition.to_stage.value}"
                )
            if transition.occurred_at < previous_time:
                raise ValueError("commitment transition times must be monotonic")
            previous_stage = transition.to_stage
            previous_time = transition.occurred_at

        references = {
            CommitmentEvent.AUTHORIZE: self.authorization_reference,
            CommitmentEvent.RESERVE: self.reservation_reference,
            CommitmentEvent.ALLOW_CAPTURE: self.certificate_id,
            CommitmentEvent.CAPTURE: self.payment_reference,
            CommitmentEvent.COMPLETE_COMPENSATION: self.compensation_reference,
        }
        for event, stored_reference in references.items():
            matching = [item for item in self.transitions if item.event == event]
            if matching and stored_reference != matching[-1].reference:
                raise ValueError(f"{event.value} reference does not match commitment history")
            if not matching and stored_reference is not None:
                raise ValueError(f"{event.value} reference exists without a matching transition")
        return self

    @staticmethod
    def _transition_is_legal(transition: TransitionRecord) -> bool:
        exact = {
            CommitmentEvent.AUTHORIZE: (
                CommitmentStage.PROPOSED,
                CommitmentStage.AUTHORIZED,
            ),
            CommitmentEvent.RESERVE: (
                CommitmentStage.AUTHORIZED,
                CommitmentStage.RESERVED,
            ),
            CommitmentEvent.ALLOW_CAPTURE: (
                CommitmentStage.RESERVED,
                CommitmentStage.CAPTURE_ALLOWED,
            ),
            CommitmentEvent.CAPTURE: (
                CommitmentStage.CAPTURE_ALLOWED,
                CommitmentStage.CAPTURED,
            ),
            CommitmentEvent.BEGIN_COMPENSATION: (
                CommitmentStage.CAPTURED,
                CommitmentStage.COMPENSATION_PENDING,
            ),
            CommitmentEvent.COMPLETE_COMPENSATION: (
                CommitmentStage.COMPENSATION_PENDING,
                CommitmentStage.COMPENSATED,
            ),
        }
        if transition.event in exact:
            return (transition.from_stage, transition.to_stage) == exact[transition.event]
        if transition.event == CommitmentEvent.CANCEL:
            return (
                transition.from_stage
                in {
                    CommitmentStage.PROPOSED,
                    CommitmentStage.AUTHORIZED,
                    CommitmentStage.RESERVED,
                    CommitmentStage.CAPTURE_ALLOWED,
                }
                and transition.to_stage == CommitmentStage.CANCELLED
            )
        if transition.event == CommitmentEvent.FAIL:
            return (
                transition.from_stage
                in {
                    CommitmentStage.PROPOSED,
                    CommitmentStage.AUTHORIZED,
                    CommitmentStage.RESERVED,
                    CommitmentStage.CAPTURE_ALLOWED,
                }
                and transition.to_stage == CommitmentStage.FAILED
            )
        return False


class CommitmentStateStore(Protocol):
    def get(self, transaction_id: str) -> CommitmentState | None: ...

    def compare_and_set(
        self,
        transaction_id: str,
        *,
        expected: CommitmentState | None,
        updated: CommitmentState,
    ) -> None: ...


class InMemoryCommitmentStateStore:
    def __init__(self) -> None:
        self._values: dict[str, CommitmentState] = {}
        self._lock = RLock()

    def get(self, transaction_id: str) -> CommitmentState | None:
        with self._lock:
            value = self._values.get(transaction_id)
            return None if value is None else value.model_copy(deep=True)

    def compare_and_set(
        self,
        transaction_id: str,
        *,
        expected: CommitmentState | None,
        updated: CommitmentState,
    ) -> None:
        if updated.transaction.transaction_id != transaction_id:
            raise CommitmentTransitionError("commitment transaction id does not match")
        with self._lock:
            current = self._values.get(transaction_id)
            if current != expected:
                raise CommitmentTransitionError("commitment state changed concurrently")
            self._values[transaction_id] = updated.model_copy(deep=True)


class SQLiteCommitmentStateStore:
    """Durable CommitmentState storage with optimistic cross-process updates."""

    _NAMESPACE = "commitment-states-v1"

    def __init__(self, path_or_store: str | Path | SQLiteJSONStateStore) -> None:
        self._store = (
            path_or_store
            if isinstance(path_or_store, SQLiteJSONStateStore)
            else SQLiteJSONStateStore(path_or_store)
        )

    def get(self, transaction_id: str) -> CommitmentState | None:
        document = self._store.load(self._NAMESPACE, transaction_id)
        if document is None:
            return None
        try:
            return CommitmentState.model_validate(document.value)
        except ValueError as exc:
            raise CommitmentTransitionError("durable commitment state is invalid") from exc

    def compare_and_set(
        self,
        transaction_id: str,
        *,
        expected: CommitmentState | None,
        updated: CommitmentState,
    ) -> None:
        if updated.transaction.transaction_id != transaction_id:
            raise CommitmentTransitionError("commitment transaction id does not match")
        document = self._store.load(self._NAMESPACE, transaction_id)
        try:
            if expected is None:
                if document is not None:
                    raise CommitmentTransitionError("commitment state changed concurrently")
                self._store.create(
                    self._NAMESPACE,
                    transaction_id,
                    updated.model_dump(mode="json"),
                )
                return
            if document is None:
                raise CommitmentTransitionError("commitment state disappeared")
            current = CommitmentState.model_validate(document.value)
            if current != expected:
                raise CommitmentTransitionError("commitment state changed concurrently")
            self._store.compare_and_swap(
                self._NAMESPACE,
                transaction_id,
                expected_version=document.version,
                expected_sha256=document.payload_sha256,
                value=updated.model_dump(mode="json"),
            )
        except DurableStateConflict as exc:
            raise CommitmentTransitionError("commitment state changed concurrently") from exc


class ProgressiveCommitmentEngine:
    """Explicit irreversible boundary with no generic skip-stage operation."""

    _TERMINAL = {
        CommitmentStage.COMPENSATED,
        CommitmentStage.CANCELLED,
        CommitmentStage.FAILED,
    }

    def __init__(self, *, state_store: CommitmentStateStore | None = None) -> None:
        self._state_store = state_store

    def _persist(
        self,
        previous: CommitmentState | None,
        updated: CommitmentState,
    ) -> CommitmentState:
        if self._state_store is not None and previous != updated:
            self._state_store.compare_and_set(
                updated.transaction.transaction_id,
                expected=previous,
                updated=updated,
            )
        return updated

    def propose(self, transaction: TransactionBinding, *, at: datetime) -> CommitmentState:
        state = CommitmentState(transaction=transaction, proposed_at=_aware(at, "at"))
        return self._persist(None, state)

    def resume_or_propose(
        self,
        transaction: TransactionBinding,
        *,
        at: datetime,
    ) -> CommitmentState:
        if self._state_store is None:
            return self.propose(transaction, at=at)
        existing = self._state_store.get(transaction.transaction_id)
        if existing is None:
            return self.propose(transaction, at=at)
        if existing.transaction != transaction:
            raise CommitmentTransitionError(
                "durable commitment transaction binding changed"
            )
        return existing

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
        prior = next(
            (item for item in state.transitions if item.event_id == event_id),
            None,
        )
        if prior is not None:
            # The first application verified certificate freshness and persisted
            # the exact certificate id. Replaying that already-recorded event
            # must not turn a later clock into a mutation or a false failure.
            return self._transition(
                state,
                expected=CommitmentStage.RESERVED,
                target=CommitmentStage.CAPTURE_ALLOWED,
                event=CommitmentEvent.ALLOW_CAPTURE,
                event_id=event_id,
                reference=certificate.certificate_id,
                at=at,
                updates={"certificate_id": certificate.certificate_id},
            )
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
        if state.stage in {CommitmentStage.CAPTURED, CommitmentStage.COMPENSATION_PENDING}:
            raise CommitmentTransitionError(
                "captured funds cannot transition to FAILED; compensation must remain actionable"
            )
        return self._transition(
            state,
            expected=state.stage,
            target=CommitmentStage.FAILED,
            event=CommitmentEvent.FAIL,
            event_id=event_id,
            reference=failure_reference,
            at=at,
        )

    def _transition(
        self,
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
        values = state.model_dump(mode="python")
        values.update({"stage": target, "transitions": (*state.transitions, record)})
        values.update(updates or {})
        return self._persist(state, CommitmentState.model_validate(values))
