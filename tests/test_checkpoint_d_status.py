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
    with pytest.raises(ValueError, match="requires a non-empty evidence"):
        GateReport("A", GateState.PASSED, evidence="   ")


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
    with pytest.raises(ValueError, match="prerequisite checkpoints A-C"):
        SafetyStatus(
            mode=ExecutionMode.REAL_PROVIDER_TEST,
            provider_status=ProviderStatus.RAZORPAY_TEST_MODE,
            provider_credentials_verified=True,
            provider_calls_enabled=True,
        )


def test_passing_a_through_c_can_authorize_test_execution_that_will_produce_d():
    reports = {checkpoint: passed(checkpoint) for checkpoint in ("A", "B", "C")}
    reports["D"] = GateReport(
        "D",
        GateState.IN_PROGRESS,
        detail="hosted Test Mode integration run has not produced D evidence yet",
    )
    status = SafetyStatus(
        gates=reports,
        mode=ExecutionMode.REAL_PROVIDER_TEST,
        provider_status=ProviderStatus.RAZORPAY_TEST_MODE,
        provider_credentials_verified=True,
        provider_calls_enabled=True,
    )

    snapshot = status.snapshot()
    assert status.provider_prerequisite_gates_accepted is True
    assert status.provider_test_execution_ready is True
    assert status.execution_gates_accepted is False
    assert status.irreversible_commit_ready is False
    assert snapshot["provider_execution_blockers"] == []
    assert snapshot["safe_to_move_real_money"] is False


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


def test_checkpoint_e_packaging_does_not_deadlock_verified_a_through_d_execution():
    reports = {
        checkpoint: passed(checkpoint)
        for checkpoint in ("A", "B", "C", "D")
    }
    reports["E"] = GateReport(
        "E",
        GateState.BLOCKED,
        detail="submission bundle is assembled after D",
    )
    status = SafetyStatus(
        gates=reports,
        mode=ExecutionMode.REAL_PROVIDER_TEST,
        provider_status=ProviderStatus.RAZORPAY_TEST_MODE,
        provider_credentials_verified=True,
        provider_calls_enabled=True,
        final_integration_verified=True,
    )

    snapshot = status.snapshot()
    assert status.execution_gates_accepted is True
    assert status.all_gates_accepted is False
    assert status.irreversible_commit_ready is True
    assert snapshot["execution_checkpoint_gates_accepted"] is True
    assert snapshot["submission_checkpoint_e_accepted"] is False
    assert snapshot["safe_to_move_real_money"] is False


def test_status_takes_an_immutable_snapshot_of_the_supplied_gate_mapping():
    supplied = {"A": GateReport("A", GateState.BLOCKED, detail="live gate incomplete")}
    status = SafetyStatus(gates=supplied)
    supplied["A"] = passed("A")

    assert status.gates["A"].state == GateState.BLOCKED
    with pytest.raises(TypeError):
        status.gates["A"] = passed("A")


def test_d_can_be_locally_blocked_without_being_mislabeled_failed_or_passed():
    status = SafetyStatus(
        gates={
            "A": GateReport("A", GateState.IN_PROGRESS, detail="frozen live evaluation"),
            "B": GateReport("B", GateState.BLOCKED, detail="requires A"),
            "C": GateReport("C", GateState.BLOCKED, detail="requires A and B"),
            "D": GateReport("D", GateState.BLOCKED, detail="locally validated only"),
            "E": GateReport("E", GateState.IN_PROGRESS, detail="local validation"),
        }
    )

    snapshot = status.snapshot()
    assert snapshot["checkpoint_gates"]["D"]["state"] == "BLOCKED"
    assert snapshot["checkpoint_gates"]["D"]["accepted"] is False
    assert "CHECKPOINT_D_NOT_ACCEPTED" in snapshot["blockers"]
