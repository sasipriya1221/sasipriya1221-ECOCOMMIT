from datetime import datetime, timedelta, timezone
from threading import Event, Lock, Thread

import pytest
from pydantic import ValidationError

from ecocommit.certificates import CertificateError, CertificateSigner, CertificateVerifier
from ecocommit.commitment import (
    CommitmentEvent,
    CommitmentStage,
    CommitmentState,
    CommitmentTransitionError,
    ProgressiveCommitmentEngine,
    TransitionRecord,
)
from ecocommit.evidence import EvidenceAuthority, EvidenceKind, EvidenceRecord, EvidenceRegistry
from ecocommit.exposure import (
    EvidenceClaimRequirement,
    EvidenceRequirement,
    ExposureCalculator,
    ExposurePolicy,
    ExposureTier,
    TransactionBinding,
)
from ecocommit.idempotency import IdempotencyConflict, IdempotencyLedger, request_fingerprint
from ecocommit.payments import PaymentState, PaymentStateError, SimulatedPaymentAdapter


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
                        claims=(EvidenceClaimRequirement(key="approved", expected_value=True),),
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


def capture_allowed_state(
    tx: TransactionBinding,
    registry: EvidenceRegistry,
    certificate,
    verifier: CertificateVerifier,
    *,
    reservation_reference: str,
):
    engine = ProgressiveCommitmentEngine()
    state = engine.reserve(
        authorized_state(engine, tx),
        reservation_reference=reservation_reference,
        reversible=True,
        event_id="payment-boundary-reserve",
        at=NOW + timedelta(seconds=2),
    )
    return engine.allow_capture(
        state,
        certificate=certificate,
        verifier=verifier,
        registry=registry,
        event_id="payment-boundary-allow",
        at=NOW + timedelta(seconds=3),
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
        commitment=state,
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


def test_concurrent_identical_idempotency_calls_execute_only_once():
    ledger = IdempotencyLedger()
    entered = Event()
    release = Event()
    count_lock = Lock()
    calls = 0
    results: list[dict[str, int]] = []
    errors: list[BaseException] = []

    def operation():
        nonlocal calls
        with count_lock:
            calls += 1
        entered.set()
        assert release.wait(2)
        return {"calls": calls}

    def invoke():
        try:
            results.append(
                ledger.execute(
                    scope="capture:tx-concurrent",
                    key="same-key",
                    fingerprint=request_fingerprint({"amount": 10}),
                    operation=operation,
                )
            )
        except BaseException as exc:  # pragma: no cover - asserted below
            errors.append(exc)

    first = Thread(target=invoke)
    second = Thread(target=invoke)
    first.start()
    assert entered.wait(2)
    second.start()
    release.set()
    first.join(2)
    second.join(2)

    assert not first.is_alive() and not second.is_alive()
    assert errors == []
    assert calls == 1
    assert results == [{"calls": 1}, {"calls": 1}]


def test_simulated_adapter_is_explicit_stateful_and_transaction_bound():
    tx, registry, certificate, verifier = authorization_bundle()
    payments = SimulatedPaymentAdapter()

    with pytest.raises(TypeError, match="certificate"):
        payments.capture(tx, idempotency_key="missing-authority")

    early_commitment = capture_allowed_state(
        tx,
        registry,
        certificate,
        verifier,
        reservation_reference="hold-that-does-not-exist",
    )
    with pytest.raises(PaymentStateError, match="cannot CAPTURE"):
        payments.capture(
            tx,
            commitment=early_commitment,
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

    with pytest.raises(PaymentStateError, match="stage CAPTURE_ALLOWED"):
        payments.capture(
            tx,
            commitment=authorized_state(ProgressiveCommitmentEngine(), tx),
            certificate=certificate,
            verifier=verifier,
            registry=registry,
            now=NOW,
            idempotency_key="capture-wrong-stage",
        )

    with pytest.raises(PaymentStateError, match="reservation does not match"):
        payments.capture(
            tx,
            commitment=early_commitment,
            certificate=certificate,
            verifier=verifier,
            registry=registry,
            now=NOW,
            idempotency_key="capture-wrong-hold",
        )

    commitment = capture_allowed_state(
        tx,
        registry,
        certificate,
        verifier,
        reservation_reference=first.provider_reference,
    )

    captured = payments.capture(
        tx,
        commitment=commitment,
        certificate=certificate,
        verifier=verifier,
        registry=registry,
        now=NOW,
        idempotency_key="capture",
    )
    assert payments.capture(
        tx,
        commitment=commitment,
        certificate=certificate,
        verifier=verifier,
        registry=registry,
        now=NOW + timedelta(seconds=1),
        idempotency_key="capture",
    ) == captured

    changed = tx.model_copy(update={"merchant_id": "merchant-attacker"})
    with pytest.raises(PaymentStateError, match="binding changed"):
        payments.refund(changed, idempotency_key="refund-changed")


def test_capture_idempotency_rejects_same_id_with_tampered_signed_request():
    tx, registry, certificate, verifier = authorization_bundle()
    payments = SimulatedPaymentAdapter()
    reservation = payments.reserve(tx, idempotency_key="reserve")
    commitment = capture_allowed_state(
        tx,
        registry,
        certificate,
        verifier,
        reservation_reference=reservation.provider_reference,
    )
    payments.capture(
        tx,
        commitment=commitment,
        certificate=certificate,
        verifier=verifier,
        registry=registry,
        now=NOW,
        idempotency_key="capture",
    )
    replacement = "0" if certificate.signature[0] != "0" else "1"
    tampered = certificate.model_copy(
        update={"signature": replacement + certificate.signature[1:]}
    )

    with pytest.raises(IdempotencyConflict, match="different request"):
        payments.capture(
            tx,
            commitment=commitment,
            certificate=tampered,
            verifier=verifier,
            registry=registry,
            now=NOW + timedelta(seconds=1),
            idempotency_key="capture",
        )


def test_capture_boundary_excludes_concurrent_evidence_supersession(monkeypatch):
    tx, registry, certificate, verifier = authorization_bundle()
    payments = SimulatedPaymentAdapter()
    reservation = payments.reserve(tx, idempotency_key="reserve")
    commitment = capture_allowed_state(
        tx,
        registry,
        certificate,
        verifier,
        reservation_reference=reservation.provider_reference,
    )
    verified = Event()
    release_verifier = Event()
    update_completed = Event()
    errors: list[BaseException] = []
    original_verify = verifier.verify

    def blocking_verify(*args, **kwargs):
        result = original_verify(*args, **kwargs)
        verified.set()
        assert release_verifier.wait(2)
        return result

    monkeypatch.setattr(verifier, "verify", blocking_verify)

    def capture():
        try:
            payments.capture(
                tx,
                commitment=commitment,
                certificate=certificate,
                verifier=verifier,
                registry=registry,
                now=NOW + timedelta(seconds=1),
                idempotency_key="capture",
            )
        except BaseException as exc:  # pragma: no cover - asserted below
            errors.append(exc)

    def supersede():
        try:
            registry.register(
                EvidenceRecord(
                    evidence_id="auth-state",
                    authority_id="user-auth",
                    issuer="identity-service",
                    kind=EvidenceKind.USER_AUTHORIZATION,
                    subject=tx.transaction_id,
                    version=2,
                    observed_at=NOW + timedelta(seconds=1),
                    claims={"approved": False},
                ),
                now=NOW + timedelta(seconds=1),
            )
            update_completed.set()
        except BaseException as exc:  # pragma: no cover - asserted below
            errors.append(exc)

    capture_thread = Thread(target=capture)
    update_thread = Thread(target=supersede)
    capture_thread.start()
    assert verified.wait(2)
    update_thread.start()

    # Supersession must wait until the capture critical section has completed.
    assert update_completed.wait(0.2) is False
    release_verifier.set()
    capture_thread.join(2)
    update_thread.join(2)

    assert not capture_thread.is_alive() and not update_thread.is_alive()
    assert errors == []
    assert payments.snapshot(tx.transaction_id).state == PaymentState.CAPTURED
    assert update_completed.is_set()


def test_captured_or_compensation_pending_state_cannot_be_failed_and_stranded():
    tx, registry, certificate, verifier = authorization_bundle()
    engine = ProgressiveCommitmentEngine()
    state = engine.reserve(
        authorized_state(engine, tx),
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
    captured = engine.record_capture(
        state,
        payment_reference="capture",
        event_id="capture",
        at=NOW + timedelta(seconds=4),
    )

    with pytest.raises(CommitmentTransitionError, match="compensation must remain actionable"):
        engine.fail(
            captured,
            failure_reference="downstream-failed",
            event_id="fail-captured",
            at=NOW + timedelta(seconds=5),
        )

    pending = engine.begin_compensation(
        captured,
        reason_reference="downstream-failed",
        event_id="begin-compensation",
        at=NOW + timedelta(seconds=5),
    )
    with pytest.raises(CommitmentTransitionError, match="compensation must remain actionable"):
        engine.fail(
            pending,
            failure_reference="refund-timeout",
            event_id="fail-compensation",
            at=NOW + timedelta(seconds=6),
        )


def test_constructed_commitment_history_cannot_forge_an_illegal_state_jump():
    tx, _, _, _ = authorization_bundle()
    illegal = TransitionRecord(
        event_id="forged",
        event=CommitmentEvent.AUTHORIZE,
        from_stage=CommitmentStage.PROPOSED,
        to_stage=CommitmentStage.CAPTURED,
        occurred_at=NOW,
        reference="forged-capture",
    )

    with pytest.raises(ValidationError, match="illegal commitment history transition"):
        CommitmentState(
            transaction=tx,
            stage=CommitmentStage.CAPTURED,
            proposed_at=NOW,
            authorization_reference="forged-capture",
            payment_reference="forged-capture",
            transitions=(illegal,),
        )

    with pytest.raises(ValidationError, match="proposed commitment cannot contain"):
        CommitmentState(
            transaction=tx,
            proposed_at=NOW,
            payment_reference="forged-payment",
        )
