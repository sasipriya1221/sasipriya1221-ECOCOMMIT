from datetime import datetime, timedelta, timezone

import pytest

from ecocommit.contracts import (
    ClauseType,
    DecisionStatus,
    EconomicClause,
    EconomicIntentContract,
    Provenance,
)
from ecocommit.evidence import (
    EvidenceAuthority,
    EvidenceKind,
    EvidenceRecord,
    EvidenceRegistry,
)
from ecocommit.exposure import (
    EvidenceClaimRequirement,
    EvidenceRequirement,
    ExposureCalculator,
    ExposurePolicy,
    ExposureReason,
    ExposureTier,
    TransactionBinding,
)
from ecocommit.policy import PolicyClass, PolicyClassMapper, PolicyMappingError
from ecocommit.validator import FidelityReport


NOW = datetime(2026, 9, 1, 6, 30, tzinfo=timezone.utc)
CONTRACT_HASH = "a" * 64


def report(status: DecisionStatus = DecisionStatus.VALIDATED):
    return FidelityReport(
        status=status,
        coverage=1.0,
        faithfulness=1.0,
        selective_risk=0.0,
    )


def clause(clause_id: str, clause_type: ClauseType, *, policy_class: str | None = None):
    return EconomicClause(
        clause_id=clause_id,
        clause_type=clause_type,
        normalized_value=f"value-{clause_id}",
        provenance=Provenance.EXPLICIT_USER,
        materiality=0.9,
        confidence=0.99,
        policy_class=policy_class,
    )


def transaction(*, amount_minor: int = 4_000, currency: str = "INR", tx_id: str = "tx-1"):
    return TransactionBinding(
        transaction_id=tx_id,
        merchant_id="merchant-1",
        amount_minor=amount_minor,
        currency=currency,
        contract_hash=CONTRACT_HASH,
    )


def registry_and_records(*, malicious_claim: bool = False):
    authorities = (
        EvidenceAuthority(
            authority_id="user-auth",
            issuer="identity-service",
            permitted_kinds={EvidenceKind.USER_AUTHORIZATION},
            max_age_seconds=300,
        ),
        EvidenceAuthority(
            authority_id="kyc",
            issuer="merchant-registry",
            permitted_kinds={EvidenceKind.COUNTERPARTY_VERIFICATION},
            max_age_seconds=300,
        ),
        EvidenceAuthority(
            authority_id="untrusted-for-policy",
            issuer="other-service",
            permitted_kinds={EvidenceKind.USER_AUTHORIZATION},
            max_age_seconds=300,
        ),
    )
    registry = EvidenceRegistry(authorities)
    auth = EvidenceRecord(
        evidence_id="auth-1",
        authority_id="user-auth",
        issuer="identity-service",
        kind=EvidenceKind.USER_AUTHORIZATION,
        subject="tx-1",
        version=1,
        observed_at=NOW,
        claims={"approved": True, "max_exposure_minor": 999_999_999}
        if malicious_claim
        else {"approved": True},
    )
    merchant = EvidenceRecord(
        evidence_id="merchant-1",
        authority_id="kyc",
        issuer="merchant-registry",
        kind=EvidenceKind.COUNTERPARTY_VERIFICATION,
        subject="tx-1",
        version=1,
        observed_at=NOW,
        claims={"status": "verified"},
    )
    registry.register(auth, now=NOW)
    registry.register(merchant, now=NOW)
    return registry


def policy():
    return ExposurePolicy(
        policy_id="purchase-default",
        version=3,
        currency="INR",
        tiers=(
            ExposureTier(
                tier_id="authorized-small",
                requirements=(
                    EvidenceRequirement(
                        kind=EvidenceKind.USER_AUTHORIZATION,
                        authority_ids={"user-auth"},
                        claims=(EvidenceClaimRequirement(key="approved", expected_value=True),),
                    ),
                ),
                max_irreversible_minor=1_000,
            ),
            ExposureTier(
                tier_id="authorized-verified-merchant",
                requirements=(
                    EvidenceRequirement(
                        kind=EvidenceKind.USER_AUTHORIZATION,
                        authority_ids={"user-auth"},
                        claims=(EvidenceClaimRequirement(key="approved", expected_value=True),),
                    ),
                    EvidenceRequirement(
                        kind=EvidenceKind.COUNTERPARTY_VERIFICATION,
                        authority_ids={"kyc"},
                        claims=(EvidenceClaimRequirement(key="status", expected_value="verified"),),
                    ),
                ),
                max_irreversible_minor=5_000,
            ),
        ),
    )


def test_policy_mapper_rejects_any_contract_not_validated():
    contract = EconomicIntentContract(
        instruction="Buy two units",
        clauses=[clause("q", ClauseType.QUANTITY)],
    )
    mapper = PolicyClassMapper()

    for status in (DecisionStatus.REJECTED, DecisionStatus.CLARIFICATION_REQUIRED):
        with pytest.raises(PolicyMappingError, match="VALIDATED"):
            mapper.map_contract(contract, report(status))


def test_policy_mapper_uses_closed_deterministic_class_set():
    clauses = [clause(item.value, item) for item in ClauseType]
    contract = EconomicIntentContract(instruction="Synthetic validated fixture", clauses=clauses)

    first = PolicyClassMapper().map_contract(contract, report())
    second = PolicyClassMapper().map_contract(contract, report())

    assert first == second
    assert {item.policy_class for item in first} == set(PolicyClass)
    assert all(item.contract_hash == contract.canonical_hash() for item in first)


def test_candidate_policy_class_cannot_override_deterministic_mapping():
    contract = EconomicIntentContract(
        instruction="Spend at most 100 rupees",
        clauses=[clause("amount", ClauseType.AMOUNT, policy_class="PRODUCT_SCOPE")],
    )

    with pytest.raises(PolicyMappingError, match="deterministic class"):
        PolicyClassMapper().map_contract(contract, report())


def test_strongest_satisfied_deterministic_tier_sets_cap():
    registry = registry_and_records()
    snapshot = registry.snapshot(["auth-1", "merchant-1"], subject="tx-1", now=NOW)

    decision = ExposureCalculator(policy()).calculate(transaction(), snapshot, now=NOW)

    assert decision.allowed is True
    assert decision.reason == ExposureReason.ALLOWED
    assert decision.satisfied_tier_id == "authorized-verified-merchant"
    assert decision.max_irreversible_minor == 5_000


def test_evidence_payload_cannot_inject_or_increase_financial_authority():
    registry = registry_and_records(malicious_claim=True)
    snapshot = registry.snapshot(["auth-1"], subject="tx-1", now=NOW)

    decision = ExposureCalculator(policy()).calculate(
        transaction(amount_minor=1_001),
        snapshot,
        now=NOW,
    )

    assert decision.allowed is False
    assert decision.reason == ExposureReason.EXCEEDS_POLICY_CAP
    assert decision.max_irreversible_minor == 1_000


def test_negative_authoritative_claim_cannot_satisfy_an_exposure_tier():
    registry = registry_and_records()
    registry.register(
        EvidenceRecord(
            evidence_id="auth-denied",
            authority_id="user-auth",
            issuer="identity-service",
            kind=EvidenceKind.USER_AUTHORIZATION,
            subject="tx-1",
            version=1,
            observed_at=NOW,
            claims={"approved": False, "max_exposure_minor": 999_999_999},
        ),
        now=NOW,
    )
    snapshot = registry.snapshot(["auth-denied"], subject="tx-1", now=NOW)

    decision = ExposureCalculator(policy()).calculate(
        transaction(amount_minor=1),
        snapshot,
        now=NOW,
    )

    assert decision.allowed is False
    assert decision.reason == ExposureReason.NO_SATISFIED_TIER
    assert decision.max_irreversible_minor == 0


def test_request_amount_cannot_select_a_higher_exposure_tier():
    registry = registry_and_records()
    snapshot = registry.snapshot(["auth-1"], subject="tx-1", now=NOW)

    decision = ExposureCalculator(policy()).calculate(
        transaction(amount_minor=4_000),
        snapshot,
        now=NOW,
    )

    assert not decision.allowed
    assert decision.max_irreversible_minor == 1_000


def test_policy_rejects_evidence_from_an_unconfigured_authority():
    registry = registry_and_records()
    registry.register(
        EvidenceRecord(
            evidence_id="auth-other",
            authority_id="untrusted-for-policy",
            issuer="other-service",
            kind=EvidenceKind.USER_AUTHORIZATION,
            subject="tx-1",
            version=1,
            observed_at=NOW,
            claims={"approved": True},
        ),
        now=NOW,
    )
    snapshot = registry.snapshot(["auth-other"], subject="tx-1", now=NOW)

    decision = ExposureCalculator(policy()).calculate(
        transaction(amount_minor=1),
        snapshot,
        now=NOW,
    )

    assert not decision.allowed
    assert decision.reason == ExposureReason.NO_SATISFIED_TIER
    assert decision.max_irreversible_minor == 0


def test_transaction_subject_currency_and_freshness_fail_closed():
    registry = registry_and_records()
    snapshot = registry.snapshot(["auth-1"], subject="tx-1", now=NOW)
    calculator = ExposureCalculator(policy())

    wrong_subject = calculator.calculate(
        transaction(amount_minor=1, tx_id="tx-other"), snapshot, now=NOW
    )
    wrong_currency = calculator.calculate(
        transaction(amount_minor=1, currency="USD"), snapshot, now=NOW
    )
    expired = calculator.calculate(
        transaction(amount_minor=1), snapshot, now=NOW + timedelta(seconds=301)
    )

    assert wrong_subject.reason == ExposureReason.EVIDENCE_SUBJECT_MISMATCH
    assert wrong_currency.reason == ExposureReason.CURRENCY_NOT_PERMITTED
    assert expired.reason == ExposureReason.EVIDENCE_EXPIRED
    assert not any((wrong_subject.allowed, wrong_currency.allowed, expired.allowed))
