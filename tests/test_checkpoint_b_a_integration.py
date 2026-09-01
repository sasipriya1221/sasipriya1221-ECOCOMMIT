from datetime import datetime, timezone

from ecocommit.certificates import CertificateSigner
from ecocommit.checkpoint_a_evidence import CheckpointAEvidenceReceipt
from ecocommit.checkpoint_b_integration import (
    AtoBPolicyBridge,
    AuthorizationStatus,
    CheckpointBAuthorizer,
)
from ecocommit.checkpoint_status import GateReport, GateState
from ecocommit.contracts import (
    ClauseType,
    DecisionStatus,
    EconomicClause,
    EconomicIntentContract,
    Provenance,
    SourceSpan,
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


NOW = datetime(2026, 9, 1, 9, 0, tzinfo=timezone.utc)
SECRET = b"checkpoint-b-a-integration-key-32-bytes-minimum"


def _span(instruction: str, text: str) -> SourceSpan:
    start = instruction.index(text)
    return SourceSpan(text=text, start=start, end=start + len(text))


def clear_contract() -> EconomicIntentContract:
    instruction = "Buy widgets from merchant-1 for at most ₹50."
    return EconomicIntentContract(
        instruction=instruction,
        clauses=[
            EconomicClause(
                clause_id="product",
                clause_type=ClauseType.PRODUCT,
                normalized_value="widgets",
                source_span=_span(instruction, "widgets"),
                provenance=Provenance.EXPLICIT_USER,
                materiality=0.9,
                confidence=1.0,
            ),
            EconomicClause(
                clause_id="merchant",
                clause_type=ClauseType.COUNTERPARTY,
                normalized_value="merchant-1",
                source_span=_span(instruction, "merchant-1"),
                provenance=Provenance.EXPLICIT_USER,
                materiality=1.0,
                confidence=1.0,
            ),
            EconomicClause(
                clause_id="amount",
                clause_type=ClauseType.AMOUNT,
                normalized_value="maximum ₹50",
                source_span=_span(instruction, "₹50"),
                provenance=Provenance.EXPLICIT_USER,
                materiality=1.0,
                confidence=1.0,
            ),
        ],
    )


def _bundle(contract: EconomicIntentContract):
    transaction = TransactionBinding(
        transaction_id="tx-a-to-b",
        merchant_id="merchant-1",
        amount_minor=4_000,
        currency="INR",
        contract_hash=contract.canonical_hash(),
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
            evidence_id="auth-a-to-b",
            authority_id="user-auth",
            issuer="identity-service",
            kind=EvidenceKind.USER_AUTHORIZATION,
            subject=transaction.transaction_id,
            version=1,
            observed_at=NOW,
            claims={"approved": True},
        ),
        now=NOW,
    )
    snapshot = registry.snapshot(
        ["auth-a-to-b"],
        subject=transaction.transaction_id,
        now=NOW,
    )
    policy = ExposurePolicy(
        policy_id="a-to-b-policy",
        version=1,
        currency="INR",
        tiers=(
            ExposureTier(
                tier_id="approved",
                requirements=(
                    EvidenceRequirement(
                        kind=EvidenceKind.USER_AUTHORIZATION,
                        authority_ids={"user-auth"},
                        claims=(
                            EvidenceClaimRequirement(key="approved", expected_value=True),
                        ),
                    ),
                ),
                max_irreversible_minor=5_000,
            ),
        ),
    )
    authorizer = CheckpointBAuthorizer(
        bridge=AtoBPolicyBridge(allow_test_evidence=True),
        exposure=ExposureCalculator(policy),
        signer=CertificateSigner(
            key_id="a-to-b-key",
            secret=SECRET,
            trusted_policy=policy,
        ),
    )
    return transaction, registry, snapshot, authorizer


def test_current_a_interface_is_recomputed_and_failed_gate_releases_no_authority():
    contract = clear_contract()
    transaction, registry, snapshot, authorizer = _bundle(contract)
    failed_gate = GateReport(
        "A",
        GateState.FAILED,
        evidence="github-actions://checkpoint-a/33477953132",
    )

    result = authorizer.authorize_capture(
        contract=contract,
        checkpoint_a_gate=failed_gate,
        transaction=transaction,
        snapshot=snapshot,
        registry=registry,
        now=NOW,
    )

    assert result.status == AuthorizationStatus.BLOCKED
    assert result.admission.fidelity_report.status == DecisionStatus.VALIDATED
    assert result.admission.obligations == ()
    assert result.certificate is None
    assert result.blockers == ("CHECKPOINT_A_FAILED",)


def test_synthetic_passed_gate_proves_interface_compatibility_without_claiming_a_passed():
    contract = clear_contract()
    transaction, registry, snapshot, authorizer = _bundle(contract)
    fixture_gate = GateReport(
        "A",
        GateState.PASSED,
        evidence="test-fixture://synthetic-a-pass",
    )

    result = authorizer.authorize_capture(
        contract=contract,
        checkpoint_a_gate=fixture_gate,
        checkpoint_a_receipt=CheckpointAEvidenceReceipt.test_fixture(fixture_gate.evidence),
        transaction=transaction,
        snapshot=snapshot,
        registry=registry,
        now=NOW,
        nonce="f" * 32,
    )

    assert result.status == AuthorizationStatus.AUTHORIZED
    assert result.admission.ready is True
    assert result.certificate is not None
    assert result.certificate.transaction.contract_hash == contract.canonical_hash()


def test_transaction_cannot_swap_the_admitted_a_contract_hash():
    contract = clear_contract()
    transaction, registry, snapshot, authorizer = _bundle(contract)
    swapped = transaction.model_copy(update={"contract_hash": "0" * 64})

    result = authorizer.authorize_capture(
        contract=contract,
        checkpoint_a_gate=(gate := GateReport(
            "A",
            GateState.PASSED,
            evidence="test-fixture://synthetic-a-pass",
        )),
        checkpoint_a_receipt=CheckpointAEvidenceReceipt.test_fixture(gate.evidence),
        transaction=swapped,
        snapshot=snapshot,
        registry=registry,
        now=NOW,
    )

    assert result.status == AuthorizationStatus.BLOCKED
    assert result.certificate is None
    assert result.blockers == ("TRANSACTION_CONTRACT_HASH_MISMATCH",)


def test_bridge_rejects_materially_ambiguous_contract_even_with_fixture_gate():
    instruction = "Buy reliable widgets."
    contract = EconomicIntentContract(
        instruction=instruction,
        clauses=[
            EconomicClause(
                clause_id="condition",
                clause_type=ClauseType.CONDITION,
                normalized_value="reliable widgets",
                source_span=_span(instruction, "reliable widgets"),
                provenance=Provenance.EXPLICIT_USER,
                materiality=1.0,
                confidence=1.0,
            )
        ],
    )

    gate = GateReport(
        "A",
        GateState.PASSED,
        evidence="test-fixture://synthetic-a-pass",
    )
    admission = AtoBPolicyBridge(allow_test_evidence=True).evaluate(
        contract,
        checkpoint_a_gate=gate,
        checkpoint_a_receipt=CheckpointAEvidenceReceipt.test_fixture(gate.evidence),
    )

    assert admission.ready is False
    assert admission.fidelity_report.status == DecisionStatus.CLARIFICATION_REQUIRED
    assert admission.obligations == ()
    assert admission.blockers == ("CONTRACT_CLARIFICATION_REQUIRED",)


def test_passed_string_without_typed_receipt_releases_no_authority():
    contract = clear_contract()
    gate = GateReport("A", GateState.PASSED, evidence="github-actions://candidate-2/result")

    admission = AtoBPolicyBridge().evaluate(contract, checkpoint_a_gate=gate)

    assert admission.ready is False
    assert admission.obligations == ()
    assert admission.blockers == ("CHECKPOINT_A_EVIDENCE_UNVERIFIED",)


def test_production_bridge_refuses_explicit_test_fixture_receipt():
    contract = clear_contract()
    gate = GateReport("A", GateState.PASSED, evidence="test-fixture://synthetic-a-pass")

    admission = AtoBPolicyBridge().evaluate(
        contract,
        checkpoint_a_gate=gate,
        checkpoint_a_receipt=CheckpointAEvidenceReceipt.test_fixture(gate.evidence),
    )

    assert admission.ready is False
    assert admission.blockers == ("CHECKPOINT_A_TEST_EVIDENCE_REFUSED",)


def test_receipt_reference_must_match_gate_reference():
    contract = clear_contract()
    gate = GateReport("A", GateState.PASSED, evidence="test-fixture://expected")

    admission = AtoBPolicyBridge(allow_test_evidence=True).evaluate(
        contract,
        checkpoint_a_gate=gate,
        checkpoint_a_receipt=CheckpointAEvidenceReceipt.test_fixture("test-fixture://other"),
    )

    assert admission.ready is False
    assert admission.blockers == ("CHECKPOINT_A_EVIDENCE_REFERENCE_MISMATCH",)
