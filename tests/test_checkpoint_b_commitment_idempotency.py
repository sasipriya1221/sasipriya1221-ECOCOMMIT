from datetime import datetime, timedelta, timezone

import pytest

from ecocommit.certificates import CertificateError, CertificateSigner, CertificateVerifier
from ecocommit.commitment import (
    CommitmentStage,
    CommitmentTransitionError,
    ProgressiveCommitmentEngine,
)
from ecocommit.evidence import EvidenceAuthority, EvidenceKind, EvidenceRecord, EvidenceRegistry
from ecocommit.exposure import (
    EvidenceRequirement,
    ExposureCalculator,
    ExposurePolicy,
    ExposureTier,
    TransactionBinding,
)
from ecocommit.idempotency import IdempotencyConflict, IdempotencyLedger, request_fingerprint
from ecocommit.payments import PaymentStateError, SimulatedPaymentAdapter


NOW = datetime(2026, 9, 1, 7, 30, tzinfo=timezone.utc)
SECRET = b"checkpoint-b-state-machine-test-key-32-bytes-minimum"


def authorization_bundle():
    tx = TransactionBinding(
        transaction_id="tx-state",
        merchant_id="merchant-state",
        amount_minor=2_000,
        currency="INR",
        contract_hash="f" * 64,
    )
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
            evidence_id="auth-state",
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
    snapshot = registry.snapshot(["auth-state"], subject=tx.transaction_id, now=NOW)
    policy = ExposurePolicy(
        policy_id="state-policy",
        version=1,
        currency="INR",
        tiers=(
            ExposureTier(
                tier_id="authorized",
                requirements=(
                    EvidenceRequirement(
                        kind=EvidenceKind.USER_AUTHORIZATION,
                        authority_ids={"user-auth"},
                    ),
                ),
                max_irreversible_minor=2_000,
            ),
        ),
    )
    decision = ExposureCalculator(policy).calculate(tx, snapshot, now=NOW)
    certificate = CertificateSigner(
        key_id="state-key",
        secret=SECRET,
        trusted_policy=policy,
    ).issue(
        transaction=tx,
        snapshot=snapshot,
        decision=decision,
        registry=registry,
        now=NOW,
        ttl_seconds=60,
        nonce="a" * 32,
    )
    verifier = CertificateVerifier({"state-key": SECRET})
    return tx, registry, certificate, verifier


def authorized_state(engine: ProgressiveCommitmentEngine, tx: TransactionBinding):
    proposed = engine.propose(tx, at=NOW)
    return engine.authorize(
        proposed,
        authorization_reference="authz-1",
        event_id="evt-authorize",
        at=NOW + timedelta(seconds=1),
    )


def test_progressive_commitment_happy_path_preserves_irreversible_boundary():
    tx, registry, certificate, verifier = authorization_bundle()
    engine = ProgressiveCommitmentEngine()
    payments = SimulatedPaymentAdapter()
    state = authorized_state(engine, tx)

    reservation = payments.reserve(tx, idempotency_key="reserve-1")
    state = engine.reserve(
        state,
        reservation_reference=reservation.provider_reference,
        reversible=True,
        event_id="evt-reserve",
        at=NOW + timedelta(seconds=2),
    )
    state = engine.allow_capture(
        state,
        certificate=certificate,
        verifier=verifier,
        registry=registry,
        event_id="evt-allow",
        at=NOW + timedelta(seconds=3),
    )
    capture = payments.capture(
        tx,
        certificate=certificate,
        verifier=verifier,
        registry=registry,
        now=NOW + timedelta(seconds=3),
        idempotency_key="capture-1",
    )
    state = engine.record_capture(
        state,
        payment_reference=capture.provider_reference,
        event_id="evt-capture",
        at=NOW + timedelta(seconds=4),
    )

    assert state.stage == CommitmentStage.CAPTURED
    assert [transition.to_stage for transition in state.transitions] == [
        CommitmentStage.AUTHORIZED,
        CommitmentStage.RESERVED,
        CommitmentStage.CAPTURE_ALLOWED,
        CommitmentStage.CAPTURED,
    ]
    assert payments.snapshot(tx.transaction_id).simulated is True


def test_commitment_cannot_skip_stages_or_use_irreversible_reservation():
    tx, registry, certificate, verifier = authorization_bundle()
    engine = ProgressiveCommitmentEngine()
    state = authorized_state(engine, tx)

    with pytest.raises(CommitmentTransitionError, match="reversible"):
        engine.reserve(
            state,
            reservation_reference="not-a-hold",
            reversible=False,
            event_id="evt-bad-reserve",
            at=NOW + timedelta(seconds=2),
        )

    with pytest.raises(CommitmentTransitionError, match="expected RESERVED"):
        engine.allow_capture(
            state,
            certificate=certificate,
            verifier=verifier,
            registry=registry,
            event_id="evt-skip",
            at=NOW + timedelta(seconds=2),
        )

    with pytest.raises(CommitmentTransitionError, match="expected CAPTURE_ALLOWED"):
        engine.record_capture(
            state,
            payment_reference="capture-without-certificate",
            event_id="evt-capture",
            at=NOW + timedelta(seconds=2),
        )


def test_capture_gate_reverifies_certificate_at_transition_time():
    tx, registry, certificate, verifier = authorization_bundle()
    engine = ProgressiveCommitmentEngine()
    state = engine.reserve(
        authorized_state(engine, tx),
        reservation_reference="sim-hold",
        reversible=True,
        event_id="evt-reserve",
        at=NOW + timedelta(seconds=2),
    )

    with pytest.raises(CertificateError, match="expired"):
        engine.allow_capture(
            state,
            certificate=certificate,
            verifier=verifier,
            registry=registry,
            event_id="evt-expired",
            at=NOW + timedelta(seconds=60),
        )


def test_transition_event_replay_is_idempotent_but_collision_fails():
    tx, _, _, _ = authorization_bundle()
    engine = ProgressiveCommitmentEngine()
    proposed = engine.propose(tx, at=NOW)
    authorized = engine.authorize(
        proposed,
        authorization_reference="authz-1",
        event_id="evt-1",
        at=NOW,
    )

    replayed = engine.authorize(
        authorized,
        authorization_reference="authz-1",
        event_id="evt-1",
        at=NOW,
    )
    assert replayed == authorized

    with pytest.raises(CommitmentTransitionError, match="reused"):
        engine.authorize(
            authorized,
            authorization_reference="different-authz",
            event_id="evt-1",
            at=NOW,
        )


def test_captured_commitment_requires_compensation_not_cancellation():
    tx, registry, certificate, verifier = authorization_bundle()
    engine = ProgressiveCommitmentEngine()
    state = authorized_state(engine, tx)
    state = engine.reserve(
        state,
        reservation_reference="hold",
        reversible=True,
        event_id="reserve",
        at=NOW + timedelta(seconds=2),
    )
    state = engine.allow_capture(
        state,
        certificate=certificate,
        verifier=verifier,
        registry=registry,
        event_id="allow",
        at=NOW + timedelta(seconds=3),
    )
    state = engine.record_capture(
        state,
        payment_reference="capture",
        event_id="capture",
        at=NOW + timedelta(seconds=4),
    )

    with pytest.raises(CommitmentTransitionError, match="cannot be cancelled"):
        engine.cancel(
            state,
            cancellation_reference="cancel",
            event_id="cancel",
            at=NOW + timedelta(seconds=5),
        )


def test_idempotency_ledger_executes_once_and_returns_defensive_copies():
    ledger = IdempotencyLedger()
    calls = 0

    def operation():
        nonlocal calls
        calls += 1
        return {"sequence": calls, "nested": {"safe": True}}

    args = dict(scope="capture:tx-1", key="key-1", fingerprint=request_fingerprint({"amount": 10}))
    first = ledger.execute(**args, operation=operation)
    first["nested"]["safe"] = False
    second = ledger.execute(**args, operation=operation)

    assert calls == 1
    assert second == {"sequence": 1, "nested": {"safe": True}}
    assert ledger.completed_count() == 1


def test_idempotency_key_collision_and_failed_operation_retry():
    ledger = IdempotencyLedger()
    ledger.execute(
        scope="reserve:tx-1",
        key="same-key",
        fingerprint=request_fingerprint({"amount": 100}),
        operation=lambda: "ok",
    )
    with pytest.raises(IdempotencyConflict, match="different request"):
        ledger.execute(
            scope="reserve:tx-1",
            key="same-key",
            fingerprint=request_fingerprint({"amount": 101}),
            operation=lambda: "must-not-run",
        )

    calls = 0

    def transient():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("transient")
        return "recovered"

    retry_args = dict(scope="refund:tx-1", key="retry", fingerprint="stable")
    with pytest.raises(RuntimeError, match="transient"):
        ledger.execute(**retry_args, operation=transient)
    assert ledger.execute(**retry_args, operation=transient) == "recovered"
    assert calls == 2


def test_simulated_adapter_is_explicit_stateful_and_transaction_bound():
    tx, registry, certificate, verifier = authorization_bundle()
    payments = SimulatedPaymentAdapter()

    with pytest.raises(TypeError, match="certificate"):
        payments.capture(tx, idempotency_key="missing-authority")

    with pytest.raises(PaymentStateError, match="cannot CAPTURE"):
        payments.capture(
            tx,
            certificate=certificate,
            verifier=verifier,
            registry=registry,
            now=NOW,
            idempotency_key="capture-too-early",
        )

    first = payments.reserve(tx, idempotency_key="reserve")
    replay = payments.reserve(tx, idempotency_key="reserve")
    assert first == replay
    assert first.simulated is True
    assert first.adapter_name == "SIMULATED_LOCAL"

    captured = payments.capture(
        tx,
        certificate=certificate,
        verifier=verifier,
        registry=registry,
        now=NOW,
        idempotency_key="capture",
    )
    assert payments.capture(
        tx,
        certificate=certificate,
        verifier=verifier,
        registry=registry,
        now=NOW + timedelta(seconds=1),
        idempotency_key="capture",
    ) == captured

    changed = tx.model_copy(update={"merchant_id": "merchant-attacker"})
    with pytest.raises(PaymentStateError, match="binding changed"):
        payments.refund(changed, idempotency_key="refund-changed")
