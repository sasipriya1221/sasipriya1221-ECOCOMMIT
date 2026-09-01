from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Mapping


CHECKPOINTS = ("A", "B", "C", "D", "E")
PROVIDER_PREREQUISITE_CHECKPOINTS = ("A", "B", "C")
EXECUTION_CHECKPOINTS = ("A", "B", "C", "D")
CHECKPOINT_PREREQUISITES: Mapping[str, tuple[str, ...]] = MappingProxyType({
    "A": (),
    "B": ("A",),
    "C": ("A", "B"),
    "D": ("A", "B", "C"),
    "E": ("A", "B", "C", "D"),
})


class GateState(str, Enum):
    NOT_EVALUATED = "NOT_EVALUATED"
    IN_PROGRESS = "IN_PROGRESS"
    PASSED = "PASSED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"


class ExecutionMode(str, Enum):
    SIMULATED = "SIMULATED"
    REAL_PROVIDER_TEST = "REAL_PROVIDER_TEST"


class ProviderStatus(str, Enum):
    NOT_CONFIGURED = "NOT_CONFIGURED"
    SIMULATED = "SIMULATED"
    RAZORPAY_TEST_MODE = "RAZORPAY_TEST_MODE"


@dataclass(frozen=True)
class GateReport:
    checkpoint: str
    state: GateState = GateState.NOT_EVALUATED
    evidence: str | None = None
    detail: str | None = None

    def __post_init__(self) -> None:
        if self.checkpoint not in CHECKPOINTS:
            raise ValueError(f"unknown checkpoint: {self.checkpoint}")
        if self.state == GateState.PASSED and not (self.evidence and self.evidence.strip()):
            raise ValueError("a passed checkpoint requires a non-empty evidence reference")

    @property
    def accepted(self) -> bool:
        return self.state == GateState.PASSED and bool(self.evidence and self.evidence.strip())

    def as_dict(self) -> dict[str, object]:
        return {
            "checkpoint": self.checkpoint,
            "state": self.state.value,
            "accepted": self.accepted,
            "evidence": self.evidence,
            "detail": self.detail,
            "prerequisites": list(CHECKPOINT_PREREQUISITES[self.checkpoint]),
        }

@dataclass(frozen=True)
class SafetyStatus:
    """Truthful status for the scaffold, separate from ordinary process liveness.

    Gate reports are supplied by integration code. The scaffold does not infer a
    pass from a healthy process, a caller assertion, or the presence of an output.
    """

    gates: Mapping[str, GateReport] = field(default_factory=dict)
    mode: ExecutionMode = ExecutionMode.SIMULATED
    provider_status: ProviderStatus = ProviderStatus.SIMULATED
    provider_credentials_verified: bool = False
    provider_calls_enabled: bool = False
    final_integration_verified: bool = False

    def __post_init__(self) -> None:
        normalized: dict[str, GateReport] = {}
        unknown = set(self.gates) - set(CHECKPOINTS)
        if unknown:
            raise ValueError(f"unknown checkpoint reports: {sorted(unknown)}")

        for checkpoint in CHECKPOINTS:
            report = self.gates.get(checkpoint, GateReport(checkpoint))
            if report.checkpoint != checkpoint:
                raise ValueError(
                    f"gate key {checkpoint!r} does not match report {report.checkpoint!r}"
                )
            normalized[checkpoint] = report

        for checkpoint, report in normalized.items():
            if not report.accepted:
                continue
            missing = [
                prerequisite
                for prerequisite in CHECKPOINT_PREREQUISITES[checkpoint]
                if not normalized[prerequisite].accepted
            ]
            if missing:
                raise ValueError(
                    f"checkpoint {checkpoint} cannot pass before prerequisites {missing}"
                )

        provider_prerequisites_accepted = all(
            normalized[checkpoint].accepted
            for checkpoint in PROVIDER_PREREQUISITE_CHECKPOINTS
        )
        execution_accepted = all(
            normalized[checkpoint].accepted for checkpoint in EXECUTION_CHECKPOINTS
        )
        if self.final_integration_verified and not execution_accepted:
            raise ValueError(
                "final integration cannot be verified before execution checkpoints A-D pass"
            )

        if self.provider_credentials_verified and self.provider_status != ProviderStatus.RAZORPAY_TEST_MODE:
            raise ValueError("provider credentials may only be verified for Razorpay Test Mode")

        if self.provider_calls_enabled:
            if self.mode != ExecutionMode.REAL_PROVIDER_TEST:
                raise ValueError("provider calls require REAL_PROVIDER_TEST mode")
            if self.provider_status != ProviderStatus.RAZORPAY_TEST_MODE:
                raise ValueError("provider calls require explicit Razorpay Test Mode status")
            if not self.provider_credentials_verified:
                raise ValueError("provider calls require verified Test Mode credentials")
            if not provider_prerequisites_accepted:
                raise ValueError(
                    "provider calls require prerequisite checkpoints A-C to pass"
                )

        object.__setattr__(self, "gates", MappingProxyType(normalized))

    @property
    def all_gates_accepted(self) -> bool:
        return all(report.accepted for report in self.gates.values())

    @property
    def execution_gates_accepted(self) -> bool:
        return all(self.gates[name].accepted for name in EXECUTION_CHECKPOINTS)

    @property
    def provider_prerequisite_gates_accepted(self) -> bool:
        return all(
            self.gates[name].accepted
            for name in PROVIDER_PREREQUISITE_CHECKPOINTS
        )

    @property
    def provider_test_execution_ready(self) -> bool:
        """Whether a configured adapter may perform a compensated Test Mode run.

        D is the evidence produced by that integrated run, so requiring D here
        would make the D gate impossible to satisfy. This never authorizes real
        money; the provider and mode checks remain Test Mode only.
        """

        return (
            self.provider_prerequisite_gates_accepted
            and self.mode == ExecutionMode.REAL_PROVIDER_TEST
            and self.provider_status == ProviderStatus.RAZORPAY_TEST_MODE
            and self.provider_credentials_verified
            and self.provider_calls_enabled
        )

    @property
    def irreversible_commit_ready(self) -> bool:
        return (
            self.execution_gates_accepted
            and self.final_integration_verified
            and self.provider_test_execution_ready
        )

    def provider_execution_blockers(self) -> list[str]:
        blockers = [
            f"CHECKPOINT_{name}_NOT_ACCEPTED"
            for name in PROVIDER_PREREQUISITE_CHECKPOINTS
            if not self.gates[name].accepted
        ]
        if self.mode != ExecutionMode.REAL_PROVIDER_TEST:
            blockers.append("REAL_PROVIDER_TEST_MODE_NOT_SELECTED")
        if self.provider_status != ProviderStatus.RAZORPAY_TEST_MODE:
            blockers.append("RAZORPAY_TEST_MODE_NOT_CONFIGURED")
        if not self.provider_credentials_verified:
            blockers.append("TEST_MODE_CREDENTIALS_NOT_VERIFIED")
        if not self.provider_calls_enabled:
            blockers.append("PROVIDER_CALLS_DISABLED")
        return blockers

    def blockers(self) -> list[str]:
        blockers = [
            f"CHECKPOINT_{name}_NOT_ACCEPTED"
            for name, report in self.gates.items()
            if not report.accepted
        ]
        if not self.final_integration_verified:
            blockers.append("FINAL_INTEGRATION_NOT_VERIFIED")
        if self.mode != ExecutionMode.REAL_PROVIDER_TEST:
            blockers.append("REAL_PROVIDER_TEST_MODE_NOT_SELECTED")
        if self.provider_status != ProviderStatus.RAZORPAY_TEST_MODE:
            blockers.append("RAZORPAY_TEST_MODE_NOT_CONFIGURED")
        if not self.provider_credentials_verified:
            blockers.append("TEST_MODE_CREDENTIALS_NOT_VERIFIED")
        if not self.provider_calls_enabled:
            blockers.append("PROVIDER_CALLS_DISABLED")
        return blockers

    def snapshot(self) -> dict[str, object]:
        return {
            "mode": self.mode.value,
            "simulation": self.mode == ExecutionMode.SIMULATED,
            "provider": {
                "status": self.provider_status.value,
                "credentials_verified": self.provider_credentials_verified,
                "calls_enabled": self.provider_calls_enabled,
            },
            "checkpoint_gates": {
                name: report.as_dict() for name, report in self.gates.items()
            },
            "all_checkpoint_gates_accepted": self.all_gates_accepted,
            "provider_prerequisite_gates_accepted": (
                self.provider_prerequisite_gates_accepted
            ),
            "execution_checkpoint_gates_accepted": self.execution_gates_accepted,
            "submission_checkpoint_e_accepted": self.gates["E"].accepted,
            "provider_test_execution_ready": self.provider_test_execution_ready,
            "provider_execution_blockers": self.provider_execution_blockers(),
            "final_integration_verified": self.final_integration_verified,
            "irreversible_commit_ready": self.irreversible_commit_ready,
            "safe_to_move_real_money": False,
            "blockers": self.blockers(),
            "status_contract": {
                "health_means_liveness_only": True,
                "caller_claims_do_not_change_gate_state": True,
                "acceptance_requires_recorded_gate_evidence": True,
            },
        }
