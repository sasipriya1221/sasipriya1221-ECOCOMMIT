from datetime import datetime, timedelta, timezone

import pytest

from ecocommit.certificates import CertificateSigner, CertificateVerifier
from ecocommit.commitment import (
    CommitmentEvent,
    CommitmentStage,
    CommitmentState,
    ProgressiveCommitmentEngine,
    TransitionRecord,
)
from ecocommit.exposure import TransactionBinding
from ecocommit.evidence import EvidenceAuthority, EvidenceKind, EvidenceRecord, EvidenceRegistry
from ecocommit.exposure import (
    EvidenceClaimRequirement,
    EvidenceRequirement,
    ExposureCalculator,
    ExposurePolicy,
    ExposureTier,
)
from ecocommit.payments import PaymentOperation, PaymentState, SimulatedPaymentAdapter
from ecocommit.reconciliation import (
    CompensationCoordinator,
    CompensationError,
    Reconciler,
    ReconciliationSeverity,
)


NOW = datetime(2026, 9, 1, 8, 0, tzinfo=timezone.utc)
SECRET = b"checkpoint-b-compensation-test-key-32-bytes-minimum"


def transaction():
    return TransactionBinding(
        transaction_id="tx-compensate",
        merchant_id="merchant-1",
        amount_minor=2_500,
        currency="INR",
        contract_hash="b" * 64,
    )


def captured_state(tx: TransactionBinding):
    transitions = (
        TransitionRecord(
            event_id="authorize",
            event=CommitmentEvent.AUTHORIZE,
            from_stage=CommitmentStage.PROPOSED,
            to_stage=CommitmentStage.AUTHORIZED,
            occurred_at=NOW + timedelta(seconds=1),
            reference="authz",
        ),
        TransitionRecord(
            event_id="reserve",
            event=CommitmentEvent.RESERVE,
            from_stage=CommitmentStage.AUTHORIZED,
            to_stage=CommitmentStage.RESERVED,
            occurred_at=NOW + timedelta(seconds=2),
            reference="sim-hold",
        ),
        TransitionRecord(
            event_id="allow",
            event=CommitmentEvent.ALLOW_CAPTURE,
            from_stage=CommitmentStage.RESERVED,
            to_stage=CommitmentStage.CAPTURE_ALLOWED,
            occurred_at=NOW + timedelta(seconds=3),
            reference="certificate-id",
        ),
        TransitionRecord(
            event_id="capture",
            event=CommitmentEvent.CAPTURE,
            from_stage=CommitmentStage.CAPTURE_ALLOWED,
            to_stage=CommitmentStage.CAPTURED,
            occurred_at=NOW + timedelta(seconds=4),
            reference="sim-capture",
        ),
    )
    return CommitmentState(
        transaction=tx,
        stage=CommitmentStage.CAPTURED,
        proposed_at=NOW,
        authorization_reference="authz",
        reservation_reference="sim-hold",
        certificate_id="certificate-id",
        payment_reference="sim-capture",
        transitions=transitions,
    )


def captured_payment(tx: TransactionBinding):
    registry = EvidenceRegistry(
        [
            EvidenceAuthority(
                authority_id="comp-auth",
                issuer="identity-service",
                permitted_kinds={EvidenceKind.USER_AUTHORIZATION},
                max_age_seconds=300,
            )
        ]
    )
    registry.register(
        EvidenceRecord(
            evidence_id="comp-evidence",
            authority_id="comp-auth",
            issuer="identity-service",
            kind=EvidenceKind.USER_AUTHORIZATION,
            subject=tx.transaction_id,
            version=1,
            observed_at=NOW,
            claims={"approved": True},
        ),
        now=NOW,
    )
    snapshot = registry.snapshot(["comp-evidence"], subject=tx.transaction_id, now=NOW)
    policy = ExposurePolicy(
        policy_id="comp-policy",
        version=1,
        currency="INR",
        tiers=(
            ExposureTier(
                tier_id="authorized",
                requirements=(
                    EvidenceRequirement(
                        kind=EvidenceKind.USER_AUTHORIZATION,
                        authority_ids={"comp-auth"},
                        claims=(EvidenceClaimRequirement(key="approved", expected_value=True),),
                    ),
                ),
                max_irreversible_minor=tx.amount_minor,
            ),
        ),
    )
    decision = ExposureCalculator(policy).calculate(tx, snapshot, now=NOW)
    signer = CertificateSigner(key_id="comp-key", secret=SECRET, trusted_policy=policy)
    certificate = signer.issue(
        transaction=tx,
        snapshot=snapshot,
        decision=decision,
        registry=registry,
        now=NOW,
        nonce="c" * 32,
    )
    verifier = CertificateVerifier({"comp-key": SECRET})
    payments = SimulatedPaymentAdapter()
    reservation = payments.reserve(tx, idempotency_key="reserve")
    engine = ProgressiveCommitmentEngine()
    authorized = engine.authorize(
        engine.propose(tx, at=NOW),
        authorization_reference="authz",
        event_id="payment-authorize",
        at=NOW,
    )
    reserved = engine.reserve(
        authorized,
        reservation_reference=reservation.provider_reference,
        reversible=True,
        event_id="payment-reserve",
        at=NOW,
    )
    capture_allowed = engine.allow_capture(
        reserved,
        certificate=certificate,
        verifier=verifier,
        registry=registry,
        event_id="payment-allow",
        at=NOW + timedelta(seconds=1),
    )
    payments.capture(
        tx,
        commitment=capture_allowed,
        certificate=certificate,
        verifier=verifier,
        registry=registry,
        now=NOW + timedelta(seconds=1),
        idempotency_key="capture",
    )
    return payments


def test_compensation_refunds_and_journals_completion():
    tx = transaction()
    state = captured_state(tx)
    payments = captured_payment(tx)
    coordinator = CompensationCoordinator(
        engine=ProgressiveCommitmentEngine(),
        payments=payments,
    )

    outcome = coordinator.compensate(
        state,
        reason_reference="downstream-fulfilment-failed",
        idempotency_key="refund-1",
        at=NOW + timedelta(seconds=5),
    )

    assert outcome.succeeded is True
    assert outcome.simulated is True
    assert outcome.payment_result is not None and outcome.payment_result.simulated is True
    assert outcome.state.stage == CommitmentStage.COMPENSATED
    assert payments.snapshot(tx.transaction_id).state == PaymentState.REFUNDED


def test_failed_compensation_stays_pending_and_same_key_can_retry():
    tx = transaction()
    state = captured_state(tx)
    payments = captured_payment(tx)
    payments.set_failure(PaymentOperation.REFUND, enabled=True)
    coordinator = CompensationCoordinator(
        engine=ProgressiveCommitmentEngine(),
        payments=payments,
    )

    failed = coordinator.compensate(
        state,
        reason_reference="failure",
        idempotency_key="refund-retry",
        at=NOW + timedelta(seconds=5),
    )
    assert failed.succeeded is False
    assert failed.state.stage == CommitmentStage.COMPENSATION_PENDING
    assert payments.snapshot(tx.transaction_id).state == PaymentState.CAPTURED

    payments.set_failure(PaymentOperation.REFUND, enabled=False)
    recovered = coordinator.compensate(
        failed.state,
        reason_reference="failure",
        idempotency_key="refund-retry",
        at=NOW + timedelta(seconds=6),
    )
    assert recovered.succeeded is True
    assert recovered.state.stage == CommitmentStage.COMPENSATED
    assert payments.snapshot(tx.transaction_id).state == PaymentState.REFUNDED


def test_completed_compensation_cannot_issue_a_second_refund():
    tx = transaction()
    payments = captured_payment(tx)
    coordinator = CompensationCoordinator(
        engine=ProgressiveCommitmentEngine(),
        payments=payments,
    )
    completed = coordinator.compensate(
        captured_state(tx),
        reason_reference="first-recovery",
        idempotency_key="refund-first",
        at=NOW + timedelta(seconds=5),
    )

    with pytest.raises(CompensationError, match="requires CAPTURED"):
        coordinator.compensate(
            completed.state,
            reason_reference="duplicate-recovery",
            idempotency_key="refund-second",
            at=NOW + timedelta(seconds=6),
        )

    assert payments.snapshot(tx.transaction_id).state == PaymentState.REFUNDED


def test_compensation_reconciles_a_refund_completed_before_state_journaling():
    tx = transaction()
    payments = captured_payment(tx)
    refund = payments.refund(tx, idempotency_key="provider-finished-first")
    coordinator = CompensationCoordinator(
        engine=ProgressiveCommitmentEngine(),
        payments=payments,
    )

    outcome = coordinator.compensate(
        captured_state(tx),
        reason_reference="ambiguous-provider-outcome",
        idempotency_key="reconcile-refund",
        at=NOW + timedelta(seconds=5),
    )

    assert outcome.succeeded is True
    assert outcome.reconciled_existing_refund is True
    assert outcome.payment_result is None
    assert outcome.state.stage == CommitmentStage.COMPENSATED
    assert outcome.state.compensation_reference == refund.provider_reference


def test_pending_compensation_retry_cannot_change_its_recorded_reason():
    tx = transaction()
    engine = ProgressiveCommitmentEngine()
    pending = engine.begin_compensation(
        captured_state(tx),
        reason_reference="original-reason",
        event_id="begin-original",
        at=NOW + timedelta(seconds=5),
    )
    coordinator = CompensationCoordinator(
        engine=engine,
        payments=captured_payment(tx),
    )

    with pytest.raises(CompensationError, match="reason must match"):
        coordinator.compensate(
            pending,
            reason_reference="changed-reason",
            idempotency_key="retry",
            at=NOW + timedelta(seconds=6),
        )


def test_reconciliation_reports_captured_pair_in_sync():
    tx = transaction()
    state = captured_state(tx)
    payments = captured_payment(tx)

    report = Reconciler().reconcile(
        state,
        payments.snapshot(tx.transaction_id),
        now=NOW + timedelta(seconds=5),
    )

    assert report.in_sync is True
    assert report.findings == ()
    assert report.payment_simulated is True


def test_reconciliation_flags_unexpected_capture_for_compensation():
    tx = transaction()
    engine = ProgressiveCommitmentEngine()
    authorized = engine.authorize(
        engine.propose(tx, at=NOW),
        authorization_reference="authz",
        event_id="authorize",
        at=NOW,
    )
    payments = captured_payment(tx)

    report = Reconciler().reconcile(
        authorized,
        payments.snapshot(tx.transaction_id),
        now=NOW + timedelta(seconds=5),
    )

    assert report.in_sync is False
    finding = next(item for item in report.findings if item.code == "UNEXPECTED_CAPTURE")
    assert finding.severity == ReconciliationSeverity.CRITICAL
    assert finding.requires_compensation is True


def test_capture_side_effect_before_state_journal_is_reconciled_then_compensated():
    tx = transaction()
    full_state = captured_state(tx)
    stale_state = CommitmentState(
        transaction=tx,
        stage=CommitmentStage.CAPTURE_ALLOWED,
        proposed_at=full_state.proposed_at,
        authorization_reference=full_state.authorization_reference,
        reservation_reference=full_state.reservation_reference,
        certificate_id=full_state.certificate_id,
        transitions=full_state.transitions[:3],
    )
    payments = captured_payment(tx)
    coordinator = CompensationCoordinator(
        engine=ProgressiveCommitmentEngine(),
        payments=payments,
    )

    outcome = coordinator.compensate(
        stale_state,
        reason_reference="capture-journal-crash",
        idempotency_key="recover-unexpected-capture",
        at=NOW + timedelta(seconds=5),
    )

    assert outcome.succeeded is True
    assert outcome.state.stage == CommitmentStage.COMPENSATED
    assert any(
        transition.event == CommitmentEvent.CAPTURE
        and transition.event_id.endswith("reconcile-capture")
        for transition in outcome.state.transitions
    )
    assert payments.snapshot(tx.transaction_id).state == PaymentState.REFUNDED


def test_reconciliation_flags_missing_refund_and_missing_void():
    tx = transaction()
    engine = ProgressiveCommitmentEngine()
    payments = captured_payment(tx)
    captured = captured_state(tx)
    pending = engine.begin_compensation(
        captured,
        reason_reference="reason",
        event_id="begin-comp",
        at=NOW + timedelta(seconds=5),
    )
    falsely_completed = engine.complete_compensation(
        pending,
        compensation_reference="not-actually-refunded",
        event_id="complete-comp",
        at=NOW + timedelta(seconds=6),
    )

    refund_report = Reconciler().reconcile(
        falsely_completed,
        payments.snapshot(tx.transaction_id),
        now=NOW + timedelta(seconds=7),
    )
    assert any(item.code == "REFUND_MISSING" for item in refund_report.findings)

    held_payments = SimulatedPaymentAdapter()
    hold = held_payments.reserve(tx, idempotency_key="held")
    authorized = engine.authorize(
        engine.propose(tx, at=NOW),
        authorization_reference="authz",
        event_id="authz-held",
        at=NOW,
    )
    reserved = engine.reserve(
        authorized,
        reservation_reference=hold.provider_reference,
        reversible=True,
        event_id="reserve-held",
        at=NOW + timedelta(seconds=1),
    )
    cancelled = engine.cancel(
        reserved,
        cancellation_reference="cancelled-without-void",
        event_id="cancel-held",
        at=NOW + timedelta(seconds=2),
    )
    void_report = Reconciler().reconcile(
        cancelled,
        held_payments.snapshot(tx.transaction_id),
        now=NOW + timedelta(seconds=3),
    )
    assert any(item.code == "VOID_MISSING" for item in void_report.findings)
