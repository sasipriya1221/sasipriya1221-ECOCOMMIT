from __future__ import annotations

from datetime import datetime, timedelta, timezone
from enum import Enum

from .certificates import CertificateSigner, CertificateVerifier
from .checkpoint_a_evidence import CheckpointAEvidenceReceipt
from .checkpoint_b_integration import (
    AtoBPolicyBridge,
    AuthorizationStatus,
    CheckpointBAuthorizer,
)
from .checkpoint_status import GateReport, GateState
from .commitment import CommitmentStage, ProgressiveCommitmentEngine
from .contracts import (
    ClauseType,
    EconomicClause,
    EconomicIntentContract,
    Provenance,
    SourceSpan,
)
from .evidence import EvidenceAuthority, EvidenceKind, EvidenceRecord, EvidenceRegistry
from .exposure import (
    EvidenceClaimRequirement,
    EvidenceRequirement,
    ExposureCalculator,
    ExposurePolicy,
    ExposureTier,
    TransactionBinding,
)
from .payments import (
    PaymentOperation,
    PaymentState,
    SimulatedPaymentAdapter,
    SimulatedPaymentFailure,
)


SIMULATION_TIME = datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc)
_SIMULATION_KEY = b"checkpoint-d-simulation-key-32-bytes-minimum"


class SimulationInputError(ValueError):
    pass


class SimulationScenario(str, Enum):
    HAPPY_PATH = "HAPPY_PATH"
    CHECKPOINT_A_BLOCKED = "CHECKPOINT_A_BLOCKED"
    CAPTURE_FAILURE = "CAPTURE_FAILURE"


def _span(instruction: str, text: str) -> SourceSpan:
    start = instruction.index(text)
    return SourceSpan(text=text, start=start, end=start + len(text))


def _synthetic_contract() -> EconomicIntentContract:
    instruction = "Buy widgets from merchant-1 for at most ₹50."
    return EconomicIntentContract(
        instruction=instruction,
        clauses=(
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
        ),
    )


def _trace(stage: CommitmentStage, *, reversible: bool, detail: str) -> dict[str, object]:
    return {
        "stage": stage.value,
        "reversible": reversible,
        "detail": detail,
    }


class CheckpointDSimulatedWorkflow:
    """Deterministic local A/B/D compatibility exercise with no real authority.

    The workflow uses a checked-in synthetic contract, synthetic Checkpoint A gate
    evidence, a local HMAC key, and ``SIMULATED_LOCAL`` payments. It can prove that
    the component interfaces compose and that failure paths clean up a reversible
    hold. It can never prove that Checkpoint A, B, or D passed.
    """

    def run(self, scenario: str | SimulationScenario) -> dict[str, object]:
        try:
            selected = (
                scenario
                if isinstance(scenario, SimulationScenario)
                else SimulationScenario(str(scenario).strip().upper())
            )
        except ValueError as exc:
            allowed = ", ".join(item.value for item in SimulationScenario)
            raise SimulationInputError(
                f"unknown simulation scenario; expected one of: {allowed}"
            ) from exc

        contract = _synthetic_contract()
        transaction = TransactionBinding(
            transaction_id=f"d-sim-{selected.value.lower()}",
            merchant_id="merchant-1",
            amount_minor=4_000,
            currency="INR",
            contract_hash=contract.canonical_hash(),
        )
        registry = EvidenceRegistry(
            (
                EvidenceAuthority(
                    authority_id="d-synthetic-user-auth",
                    issuer="synthetic-identity-fixture",
                    permitted_kinds={EvidenceKind.USER_AUTHORIZATION},
                    max_age_seconds=300,
                ),
            )
        )
        registry.register(
            EvidenceRecord(
                evidence_id="d-synthetic-approval",
                authority_id="d-synthetic-user-auth",
                issuer="synthetic-identity-fixture",
                kind=EvidenceKind.USER_AUTHORIZATION,
                subject=transaction.transaction_id,
                version=1,
                observed_at=SIMULATION_TIME,
                claims={"approved": True},
            ),
            now=SIMULATION_TIME,
        )
        snapshot = registry.snapshot(
            ("d-synthetic-approval",),
            subject=transaction.transaction_id,
            now=SIMULATION_TIME,
        )
        policy = ExposurePolicy(
            policy_id="d-synthetic-policy",
            version=1,
            currency="INR",
            tiers=(
                ExposureTier(
                    tier_id="synthetic-user-approved",
                    requirements=(
                        EvidenceRequirement(
                            kind=EvidenceKind.USER_AUTHORIZATION,
                            authority_ids={"d-synthetic-user-auth"},
                            claims=(
                                EvidenceClaimRequirement(
                                    key="approved",
                                    expected_value=True,
                                ),
                            ),
                        ),
                    ),
                    max_irreversible_minor=5_000,
                ),
            ),
        )
        signer = CertificateSigner(
            key_id="d-synthetic-local-key",
            secret=_SIMULATION_KEY,
            trusted_policy=policy,
        )
        authorizer = CheckpointBAuthorizer(
            bridge=AtoBPolicyBridge(allow_test_evidence=True),
            exposure=ExposureCalculator(policy),
            signer=signer,
        )
        gate = GateReport(
            "A",
            (
                GateState.BLOCKED
                if selected == SimulationScenario.CHECKPOINT_A_BLOCKED
                else GateState.PASSED
            ),
            evidence=(
                None
                if selected == SimulationScenario.CHECKPOINT_A_BLOCKED
                else "test-fixture://checkpoint-d/synthetic-a-pass"
            ),
            detail="SYNTHETIC_FIXTURE_ONLY",
        )
        authorization = authorizer.authorize_capture(
            contract=contract,
            checkpoint_a_gate=gate,
            checkpoint_a_receipt=(
                CheckpointAEvidenceReceipt.test_fixture(gate.evidence)
                if gate.accepted and gate.evidence is not None
                else None
            ),
            transaction=transaction,
            snapshot=snapshot,
            registry=registry,
            now=SIMULATION_TIME,
            nonce="d" * 32,
        )

        engine = ProgressiveCommitmentEngine()
        state = engine.propose(transaction, at=SIMULATION_TIME)
        trace = [
            _trace(
                state.stage,
                reversible=True,
                detail="Synthetic proposal created; no payment activity",
            )
        ]
        payments = SimulatedPaymentAdapter()

        base: dict[str, object] = {
            "schema_version": "D.SIMULATION.1",
            "scenario": selected.value,
            "execution_mode": "SIMULATED_LOCAL",
            "evidence_class": "SYNTHETIC_FIXTURE",
            "counts_as_checkpoint_evidence": False,
            "final_integration_verified": False,
            "real_provider_called": False,
            "real_money_moved": False,
            "transaction": {
                "transaction_id": transaction.transaction_id,
                "merchant_id": transaction.merchant_id,
                "amount_minor": transaction.amount_minor,
                "currency": transaction.currency,
                "contract_hash": transaction.contract_hash,
            },
            "checkpoint_a_fixture": {
                "state": gate.state.value,
                "evidence": gate.evidence,
                "synthetic": True,
            },
            "a_to_b": {
                "status": authorization.status.value,
                "fidelity_status": authorization.admission.fidelity_report.status.value,
                "obligation_count": len(authorization.admission.obligations),
                "blockers": list(authorization.blockers),
            },
        }

        if authorization.status != AuthorizationStatus.AUTHORIZED:
            return {
                **base,
                "outcome": "SIMULATED_BLOCKED",
                "final_commitment_stage": state.stage.value,
                "simulated_payment_state": PaymentState.NONE.value,
                "economic_state": {
                    "requested_minor": transaction.amount_minor,
                    "authorized_irreversible_minor": 0,
                    "captured_minor": 0,
                    "currency": transaction.currency,
                },
                "state_trace": trace,
            }

        certificate = authorization.certificate
        decision = authorization.exposure_decision
        if certificate is None or decision is None:  # defensive coherence check
            raise RuntimeError("authorized synthetic workflow lacks deterministic authority")
        verifier = CertificateVerifier({"d-synthetic-local-key": _SIMULATION_KEY})

        state = engine.authorize(
            state,
            authorization_reference=certificate.certificate_id,
            event_id="d-sim-authorize",
            at=SIMULATION_TIME,
        )
        trace.append(
            _trace(
                state.stage,
                reversible=True,
                detail="Synthetic A-to-B admission and exposure decision authorized",
            )
        )
        reservation = payments.reserve(transaction, idempotency_key="d-sim-reserve")
        state = engine.reserve(
            state,
            reservation_reference=reservation.provider_reference,
            reversible=True,
            event_id="d-sim-reserve",
            at=SIMULATION_TIME + timedelta(seconds=1),
        )
        trace.append(
            _trace(
                state.stage,
                reversible=True,
                detail="SIMULATED_LOCAL reversible hold recorded",
            )
        )
        state = engine.allow_capture(
            state,
            certificate=certificate,
            verifier=verifier,
            registry=registry,
            event_id="d-sim-allow-capture",
            at=SIMULATION_TIME + timedelta(seconds=2),
        )
        trace.append(
            _trace(
                state.stage,
                reversible=True,
                detail="Certificate reverified; simulated capture boundary unlocked",
            )
        )

        if selected == SimulationScenario.CAPTURE_FAILURE:
            payments.set_failure(PaymentOperation.CAPTURE, enabled=True)
            try:
                payments.capture(
                    transaction,
                    commitment=state,
                    certificate=certificate,
                    verifier=verifier,
                    registry=registry,
                    now=SIMULATION_TIME + timedelta(seconds=3),
                    idempotency_key="d-sim-capture",
                )
            except SimulatedPaymentFailure:
                voided = payments.void(transaction, idempotency_key="d-sim-void")
                state = engine.fail(
                    state,
                    failure_reference="SIMULATED_CAPTURE_FAILURE_HOLD_VOIDED",
                    event_id="d-sim-fail",
                    at=SIMULATION_TIME + timedelta(seconds=4),
                )
                trace.append(
                    _trace(
                        state.stage,
                        reversible=True,
                        detail="Injected capture failure; simulated hold voided",
                    )
                )
                return {
                    **base,
                    "outcome": "SIMULATED_FAILED_CLOSED",
                    "failure_code": "SIMULATED_CAPTURE_FAILURE",
                    "cleanup": "SIMULATED_HOLD_VOIDED",
                    "final_commitment_stage": state.stage.value,
                    "simulated_payment_state": voided.state.value,
                    "economic_state": {
                        "requested_minor": transaction.amount_minor,
                        "authorized_irreversible_minor": decision.max_irreversible_minor,
                        "captured_minor": 0,
                        "currency": transaction.currency,
                    },
                    "state_trace": trace,
                }
            raise RuntimeError("injected simulation failure did not fail")

        captured = payments.capture(
            transaction,
            commitment=state,
            certificate=certificate,
            verifier=verifier,
            registry=registry,
            now=SIMULATION_TIME + timedelta(seconds=3),
            idempotency_key="d-sim-capture",
        )
        state = engine.record_capture(
            state,
            payment_reference=captured.provider_reference,
            event_id="d-sim-capture",
            at=SIMULATION_TIME + timedelta(seconds=3),
        )
        trace.append(
            _trace(
                state.stage,
                reversible=False,
                detail="SIMULATED_LOCAL capture recorded; no real money moved",
            )
        )
        return {
            **base,
            "outcome": "SIMULATED_CAPTURED",
            "final_commitment_stage": state.stage.value,
            "simulated_payment_state": captured.state.value,
            "certificate_id": certificate.certificate_id,
            "economic_state": {
                "requested_minor": transaction.amount_minor,
                "authorized_irreversible_minor": decision.max_irreversible_minor,
                "captured_minor": transaction.amount_minor,
                "currency": transaction.currency,
            },
            "state_trace": trace,
        }
