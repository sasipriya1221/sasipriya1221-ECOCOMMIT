from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .certificates import CertificateSigner, CommitCertificate
from .checkpoint_status import GateReport, GateState
from .contracts import DecisionStatus, EconomicIntentContract
from .evidence import EvidenceRegistry, EvidenceSnapshot
from .exposure import ExposureCalculator, ExposureDecision, TransactionBinding
from .policy import PolicyClassMapper, PolicyObligation
from .validator import FidelityReport, FidelityValidator


class CheckpointBIntegrationError(ValueError):
    pass


class AuthorizationStatus(str, Enum):
    AUTHORIZED = "AUTHORIZED"
    BLOCKED = "BLOCKED"


class AtoBPolicyAdmission(BaseModel):
    """Fail-closed result of recomputing the current A contract interface.

    A caller cannot provide a bare ``VALIDATED`` enum to this boundary. The
    current ``FidelityValidator`` is run here, and no policy obligations are
    released unless the authoritative Checkpoint A gate is also accepted.
    """

    model_config = ConfigDict(frozen=True)

    ready: bool
    contract_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    checkpoint_a_state: GateState
    checkpoint_a_evidence: str | None = None
    fidelity_report: FidelityReport
    obligations: tuple[PolicyObligation, ...] = ()
    blockers: tuple[str, ...] = ()

    @model_validator(mode="after")
    def authority_is_coherent(self):
        if self.ready:
            if self.checkpoint_a_state != GateState.PASSED or not self.checkpoint_a_evidence:
                raise ValueError("ready A-to-B admission requires accepted Checkpoint A evidence")
            if self.fidelity_report.status != DecisionStatus.VALIDATED:
                raise ValueError("ready A-to-B admission requires a validated contract")
            if not self.obligations or self.blockers:
                raise ValueError("ready A-to-B admission requires obligations and no blockers")
            if any(item.contract_hash != self.contract_hash for item in self.obligations):
                raise ValueError("policy obligations do not match the admitted contract")
        elif self.obligations:
            raise ValueError("blocked A-to-B admission cannot release policy obligations")
        return self


class CheckpointBAuthorizationResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: AuthorizationStatus
    admission: AtoBPolicyAdmission
    exposure_decision: ExposureDecision | None = None
    certificate: CommitCertificate | None = None
    blockers: tuple[str, ...] = ()

    @model_validator(mode="after")
    def authorization_is_coherent(self):
        if self.status == AuthorizationStatus.AUTHORIZED:
            if not self.admission.ready:
                raise ValueError("authorization requires ready A-to-B admission")
            if self.exposure_decision is None or not self.exposure_decision.allowed:
                raise ValueError("authorization requires an allowed exposure decision")
            if self.certificate is None or self.blockers:
                raise ValueError("authorization requires a certificate and no blockers")
        elif self.certificate is not None:
            raise ValueError("blocked authorization cannot contain a commit certificate")
        return self


class AtoBPolicyBridge:
    """Integrate current A contracts/reports while keeping the A gate locked."""

    def __init__(
        self,
        *,
        validator: FidelityValidator | None = None,
        mapper: PolicyClassMapper | None = None,
    ) -> None:
        self.validator = validator or FidelityValidator()
        self.mapper = mapper or PolicyClassMapper()

    def evaluate(
        self,
        contract: EconomicIntentContract,
        *,
        checkpoint_a_gate: GateReport,
    ) -> AtoBPolicyAdmission:
        if checkpoint_a_gate.checkpoint != "A":
            raise CheckpointBIntegrationError("A-to-B admission requires a Checkpoint A gate report")

        report = self.validator.validate(contract).model_copy(deep=True)
        blockers: list[str] = []
        if not checkpoint_a_gate.accepted:
            blockers.append(f"CHECKPOINT_A_{checkpoint_a_gate.state.value}")
        if report.status != DecisionStatus.VALIDATED:
            blockers.append(f"CONTRACT_{report.status.value}")

        obligations: tuple[PolicyObligation, ...] = ()
        if not blockers:
            obligations = self.mapper.map_contract(contract, report)

        return AtoBPolicyAdmission(
            ready=not blockers,
            contract_hash=contract.canonical_hash(),
            checkpoint_a_state=checkpoint_a_gate.state,
            checkpoint_a_evidence=checkpoint_a_gate.evidence,
            fidelity_report=report,
            obligations=obligations,
            blockers=tuple(blockers),
        )


class CheckpointBAuthorizer:
    """Fail-closed integrated local path for issuing a B commit certificate."""

    def __init__(
        self,
        *,
        bridge: AtoBPolicyBridge,
        exposure: ExposureCalculator,
        signer: CertificateSigner,
    ) -> None:
        self.bridge = bridge
        self.exposure = exposure
        self.signer = signer

    def authorize_capture(
        self,
        *,
        contract: EconomicIntentContract,
        checkpoint_a_gate: GateReport,
        transaction: TransactionBinding,
        snapshot: EvidenceSnapshot,
        registry: EvidenceRegistry,
        now: datetime,
        ttl_seconds: int = 60,
        nonce: str | None = None,
    ) -> CheckpointBAuthorizationResult:
        admission = self.bridge.evaluate(contract, checkpoint_a_gate=checkpoint_a_gate)
        if not admission.ready:
            return CheckpointBAuthorizationResult(
                status=AuthorizationStatus.BLOCKED,
                admission=admission,
                blockers=admission.blockers,
            )

        if transaction.contract_hash != admission.contract_hash:
            return CheckpointBAuthorizationResult(
                status=AuthorizationStatus.BLOCKED,
                admission=admission,
                blockers=("TRANSACTION_CONTRACT_HASH_MISMATCH",),
            )

        decision = self.exposure.calculate(transaction, snapshot, now=now)
        if not decision.allowed:
            return CheckpointBAuthorizationResult(
                status=AuthorizationStatus.BLOCKED,
                admission=admission,
                exposure_decision=decision,
                blockers=(f"EXPOSURE_{decision.reason.value}",),
            )

        certificate = self.signer.issue(
            transaction=transaction,
            snapshot=snapshot,
            decision=decision,
            registry=registry,
            now=now,
            ttl_seconds=ttl_seconds,
            nonce=nonce,
        )
        return CheckpointBAuthorizationResult(
            status=AuthorizationStatus.AUTHORIZED,
            admission=admission,
            exposure_decision=decision,
            certificate=certificate,
        )
