import pytest

from ecocommit.checkpoint_status import (
    CHECKPOINTS,
    ExecutionMode,
    GateReport,
    GateState,
    ProviderStatus,
    SafetyStatus,
)


def passed(checkpoint: str) -> GateReport:
    return GateReport(checkpoint, GateState.PASSED, evidence=f"evidence://{checkpoint}")


def test_default_status_reports_every_gate_without_accepting_anything():
    snapshot = SafetyStatus().snapshot()

    assert tuple(snapshot["checkpoint_gates"]) == CHECKPOINTS
    assert snapshot["all_checkpoint_gates_accepted"] is False
    assert snapshot["final_integration_verified"] is False
    assert snapshot["irreversible_commit_ready"] is False
    assert snapshot["safe_to_move_real_money"] is False
    assert all(not report["accepted"] for report in snapshot["checkpoint_gates"].values())


def test_gate_cannot_pass_without_evidence():
    with pytest.raises(ValueError, match="requires a non-empty evidence"):
        GateReport("A", GateState.PASSED)


def test_downstream_gate_cannot_pass_before_its_prerequisites():
    with pytest.raises(ValueError, match="checkpoint B cannot pass"):
        SafetyStatus(gates={"B": passed("B")})

    with pytest.raises(ValueError, match="checkpoint D cannot pass"):
        SafetyStatus(gates={
            "A": passed("A"),
            "B": passed("B"),
            "D": passed("D"),
        })


def test_provider_calls_cannot_be_enabled_by_mode_or_credentials_alone():
    with pytest.raises(ValueError, match="every gate and final integration"):
        SafetyStatus(
            mode=ExecutionMode.REAL_PROVIDER_TEST,
            provider_status=ProviderStatus.RAZORPAY_TEST_MODE,
            provider_credentials_verified=True,
            provider_calls_enabled=True,
        )


def test_fully_evidenced_test_mode_status_is_test_ready_but_never_real_money_ready():
    reports = {checkpoint: passed(checkpoint) for checkpoint in CHECKPOINTS}
    status = SafetyStatus(
        gates=reports,
        mode=ExecutionMode.REAL_PROVIDER_TEST,
        provider_status=ProviderStatus.RAZORPAY_TEST_MODE,
        provider_credentials_verified=True,
        provider_calls_enabled=True,
        final_integration_verified=True,
    )

    assert status.irreversible_commit_ready is True
    assert status.snapshot()["safe_to_move_real_money"] is False
