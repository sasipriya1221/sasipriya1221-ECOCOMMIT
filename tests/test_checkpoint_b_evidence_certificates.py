from datetime import datetime, timedelta, timezone

import pytest

from ecocommit.certificates import (
    CertificateError,
    CertificateSigner,
    CertificateVerifier,
)
from ecocommit.evidence import (
    EvidenceAuthority,
    EvidenceAuthorityError,
    EvidenceFreshnessError,
    EvidenceKind,
    EvidenceRecord,
    EvidenceRegistry,
    EvidenceSnapshotError,
    EvidenceVersionError,
)
from ecocommit.exposure import (
    EvidenceClaimRequirement,
    EvidenceRequirement,
    ExposureCalculator,
    ExposureDecision,
    ExposurePolicy,
    ExposureReason,
    ExposureTier,
    TransactionBinding,
)


NOW = datetime(2026, 9, 1, 7, 0, tzinfo=timezone.utc)
SECRET = b"checkpoint-b-local-test-signing-key-32-bytes-minimum"


def authority(*, max_age: int = 300):
    return EvidenceAuthority(
        authority_id="user-auth",
        issuer="identity-service",
        permitted_kinds={EvidenceKind.USER_AUTHORIZATION},
        max_age_seconds=max_age,
        future_skew_seconds=30,
    )


def record(
    *,
    version: int = 1,
    observed_at: datetime = NOW,
    expires_at: datetime | None = None,
    issuer: str = "identity-service",
    claims: dict | None = None,
):
    return EvidenceRecord(
        evidence_id="auth-1",
        authority_id="user-auth",
        issuer=issuer,
        kind=EvidenceKind.USER_AUTHORIZATION,
        subject="tx-1",
        version=version,
        observed_at=observed_at,
        expires_at=expires_at,
        claims=claims or {"approved": True},
    )


def exposure_policy(*, cap: int = 5_000):
    return ExposurePolicy(
        policy_id="trusted-purchase-policy",
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
                max_irreversible_minor=cap,
            ),
        ),
    )


def transaction(*, amount: int = 4_000, merchant: str = "merchant-1", contract_hash: str = "c" * 64):
    return TransactionBinding(
        transaction_id="tx-1",
        merchant_id=merchant,
        amount_minor=amount,
        currency="INR",
        contract_hash=contract_hash,
    )


def issued_bundle(*, evidence_expiry: datetime | None = None):
    registry = EvidenceRegistry([authority()])
    registry.register(record(expires_at=evidence_expiry), now=NOW)
    snapshot = registry.snapshot(["auth-1"], subject="tx-1", now=NOW)
    policy = exposure_policy()
    tx = transaction()
    decision = ExposureCalculator(policy).calculate(tx, snapshot, now=NOW)
    signer = CertificateSigner(key_id="local-key", secret=SECRET, trusted_policy=policy)
    certificate = signer.issue(
        transaction=tx,
        snapshot=snapshot,
        decision=decision,
        registry=registry,
        now=NOW,
        ttl_seconds=60,
        nonce="d" * 32,
    )
    verifier = CertificateVerifier({"local-key": SECRET})
    return registry, snapshot, policy, tx, decision, signer, certificate, verifier


def test_evidence_authority_issuer_and_kind_are_enforced():
    registry = EvidenceRegistry([authority()])

    with pytest.raises(EvidenceAuthorityError, match="issuer"):
        registry.register(record(issuer="attacker"), now=NOW)

    wrong_kind = record().model_copy(update={"kind": EvidenceKind.CERTIFICATION})
    with pytest.raises(EvidenceAuthorityError, match="not permitted"):
        registry.register(wrong_kind, now=NOW)


def test_stale_and_excessively_future_evidence_are_rejected():
    registry = EvidenceRegistry([authority(max_age=60)])

    with pytest.raises(EvidenceFreshnessError, match="stale"):
        registry.register(record(observed_at=NOW - timedelta(seconds=60)), now=NOW)
    with pytest.raises(EvidenceFreshnessError, match="future"):
        registry.register(record(observed_at=NOW + timedelta(seconds=31)), now=NOW)


def test_evidence_version_replays_conflicts_and_exact_retries():
    registry = EvidenceRegistry([authority()])
    original = registry.register(record(), now=NOW)

    assert registry.register(record(), now=NOW) == original
    with pytest.raises(EvidenceVersionError, match="conflicting"):
        registry.register(record(claims={"approved": False}), now=NOW)

    registry.register(
        record(version=2, observed_at=NOW + timedelta(seconds=1)),
        now=NOW + timedelta(seconds=1),
    )
    with pytest.raises(EvidenceVersionError, match="replayed"):
        registry.register(record(), now=NOW + timedelta(seconds=1))


def test_evidence_version_cannot_change_issuer_identity_or_move_time_backwards():
    registry = EvidenceRegistry(
        [
            authority(),
            EvidenceAuthority(
                authority_id="other-auth",
                issuer="other-issuer",
                permitted_kinds={EvidenceKind.USER_AUTHORIZATION},
                max_age_seconds=300,
            ),
        ]
    )
    registry.register(record(), now=NOW)
    takeover = record(version=2).model_copy(
        update={"authority_id": "other-auth", "issuer": "other-issuer"}
    )

    with pytest.raises(EvidenceVersionError, match="identity metadata"):
        registry.register(takeover, now=NOW)

    with pytest.raises(EvidenceVersionError, match="cannot move backwards"):
        registry.register(
            record(version=2, observed_at=NOW - timedelta(seconds=1)),
            now=NOW,
        )


def test_registered_claims_cannot_be_mutated_without_a_new_version():
    registry = EvidenceRegistry([authority()])
    returned = registry.register(record(), now=NOW)
    returned.claims["approved"] = False

    fresh = registry.get_fresh("auth-1", now=NOW)

    assert fresh.version == 1
    assert fresh.claims == {"approved": True}


def test_snapshot_rejects_wrong_subject_and_revocation():
    registry = EvidenceRegistry([authority()])
    registry.register(record(), now=NOW)

    with pytest.raises(EvidenceSnapshotError, match="subject"):
        registry.snapshot(["auth-1"], subject="tx-other", now=NOW)

    snapshot = registry.snapshot(["auth-1"], subject="tx-1", now=NOW)
    registry.revoke("auth-1", 1)
    with pytest.raises(EvidenceSnapshotError, match="revoked"):
        registry.assert_snapshot_current(snapshot, now=NOW)


def test_certificate_verifies_exact_transaction_contract_and_current_evidence():
    registry, _, _, tx, _, _, certificate, verifier = issued_bundle()

    verified = verifier.verify(
        certificate,
        expected_transaction=tx,
        expected_contract_hash=tx.contract_hash,
        registry=registry,
        now=NOW,
    )

    assert verified.certificate_id == certificate.certificate_id
    assert verified.transaction_digest == tx.digest()


def test_certificate_rejects_signature_tampering_and_transaction_substitution():
    registry, _, _, tx, _, _, certificate, verifier = issued_bundle()
    tampered = certificate.model_copy(update={"signature": "0" * 64})

    with pytest.raises(CertificateError, match="signature"):
        verifier.verify(
            tampered,
            expected_transaction=tx,
            expected_contract_hash=tx.contract_hash,
            registry=registry,
            now=NOW,
        )

    swapped_merchant = transaction(merchant="merchant-attacker")
    with pytest.raises(CertificateError, match="transaction binding"):
        verifier.verify(
            certificate,
            expected_transaction=swapped_merchant,
            expected_contract_hash=swapped_merchant.contract_hash,
            registry=registry,
            now=NOW,
        )

    with pytest.raises(CertificateError, match="contract hash"):
        verifier.verify(
            certificate,
            expected_transaction=tx,
            expected_contract_hash="e" * 64,
            registry=registry,
            now=NOW,
        )


@pytest.mark.parametrize(
    "updates",
    [
        {"transaction_id": "tx-attacker"},
        {"merchant_id": "merchant-attacker"},
        {"amount_minor": 3_999},
        {"currency": "USD"},
        {"contract_hash": "e" * 64},
    ],
)
def test_every_transaction_field_is_bound_by_the_commit_certificate(updates):
    registry, _, _, tx, _, _, certificate, verifier = issued_bundle()
    changed = tx.model_copy(update=updates)

    with pytest.raises(CertificateError, match="transaction binding"):
        verifier.verify(
            certificate,
            expected_transaction=changed,
            expected_contract_hash=changed.contract_hash,
            registry=registry,
            now=NOW,
        )


def test_signed_certificate_payload_and_nonce_tampering_are_rejected():
    registry, _, _, tx, _, _, certificate, verifier = issued_bundle()
    tampered = certificate.model_copy(update={"nonce": "e" * 32})

    with pytest.raises(CertificateError, match="certificate id"):
        verifier.verify(
            tampered,
            expected_transaction=tx,
            expected_contract_hash=tx.contract_hash,
            registry=registry,
            now=NOW,
        )


def test_superseding_evidence_version_invalidates_certificate_toctou():
    registry, _, _, tx, _, _, certificate, verifier = issued_bundle()
    later = NOW + timedelta(seconds=1)
    registry.register(record(version=2, observed_at=later, claims={"approved": False}), now=later)

    with pytest.raises(EvidenceSnapshotError, match="no longer current"):
        verifier.verify(
            certificate,
            expected_transaction=tx,
            expected_contract_hash=tx.contract_hash,
            registry=registry,
            now=later,
        )


def test_certificate_expiry_is_bounded_by_evidence_and_enforced():
    evidence_expiry = NOW + timedelta(seconds=20)
    registry, _, _, tx, _, _, certificate, verifier = issued_bundle(evidence_expiry=evidence_expiry)

    assert certificate.expires_at == evidence_expiry
    with pytest.raises(CertificateError, match="expired"):
        verifier.verify(
            certificate,
            expected_transaction=tx,
            expected_contract_hash=tx.contract_hash,
            registry=registry,
            now=evidence_expiry,
        )


def test_denied_decision_cannot_be_signed():
    registry = EvidenceRegistry([authority()])
    registry.register(record(), now=NOW)
    snapshot = registry.snapshot(["auth-1"], subject="tx-1", now=NOW)
    policy = exposure_policy(cap=5_000)
    tx = transaction(amount=5_001)
    denied = ExposureCalculator(policy).calculate(tx, snapshot, now=NOW)
    signer = CertificateSigner(key_id="local-key", secret=SECRET, trusted_policy=policy)

    assert not denied.allowed
    with pytest.raises(CertificateError, match="denied"):
        signer.issue(
            transaction=tx,
            snapshot=snapshot,
            decision=denied,
            registry=registry,
            now=NOW,
        )


def test_self_consistent_forged_inflated_decision_cannot_be_signed():
    registry = EvidenceRegistry([authority()])
    registry.register(record(), now=NOW)
    snapshot = registry.snapshot(["auth-1"], subject="tx-1", now=NOW)
    policy = exposure_policy(cap=5_000)
    tx = transaction(amount=5_001)
    trusted_denial = ExposureCalculator(policy).calculate(tx, snapshot, now=NOW)
    forged_values = trusted_denial.model_dump(exclude={"decision_hash"})
    forged_values.update(
        max_irreversible_minor=999_999_999,
        allowed=True,
        reason=ExposureReason.ALLOWED,
    )
    forged = ExposureDecision.create(**forged_values)
    signer = CertificateSigner(key_id="local-key", secret=SECRET, trusted_policy=policy)

    assert forged.allowed
    assert forged.decision_hash != trusted_denial.decision_hash
    with pytest.raises(CertificateError, match="trusted policy"):
        signer.issue(
            transaction=tx,
            snapshot=snapshot,
            decision=forged,
            registry=registry,
            now=NOW,
        )
