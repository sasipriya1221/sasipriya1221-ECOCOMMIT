import json
import subprocess
import sys
from pathlib import Path

import pytest

from ecocommit.checkpoint_d_workflow import (
    CheckpointDSimulatedWorkflow,
    SimulationInputError,
    SimulationScenario,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def test_happy_path_composes_a_b_commitment_and_simulated_payment_boundaries():
    result = CheckpointDSimulatedWorkflow().run(SimulationScenario.HAPPY_PATH)

    assert result["outcome"] == "SIMULATED_CAPTURED"
    assert result["execution_mode"] == "SIMULATED_LOCAL"
    assert result["evidence_class"] == "SYNTHETIC_FIXTURE"
    assert result["counts_as_checkpoint_evidence"] is False
    assert result["final_integration_verified"] is False
    assert result["real_provider_called"] is False
    assert result["real_money_moved"] is False
    assert result["a_to_b"]["status"] == "AUTHORIZED"
    assert result["a_to_b"]["fidelity_status"] == "VALIDATED"
    assert result["a_to_b"]["obligation_count"] == 3
    assert result["final_commitment_stage"] == "CAPTURED"
    assert result["simulated_payment_state"] == "CAPTURED"
    assert result["economic_state"] == {
        "requested_minor": 4_000,
        "authorized_irreversible_minor": 5_000,
        "captured_minor": 4_000,
        "currency": "INR",
    }
    assert [row["stage"] for row in result["state_trace"]] == [
        "PROPOSED",
        "AUTHORIZED",
        "RESERVED",
        "CAPTURE_ALLOWED",
        "CAPTURED",
    ]


def test_blocked_a_fixture_releases_no_b_authority_or_payment_activity():
    result = CheckpointDSimulatedWorkflow().run("CHECKPOINT_A_BLOCKED")

    assert result["outcome"] == "SIMULATED_BLOCKED"
    assert result["checkpoint_a_fixture"] == {
        "state": "BLOCKED",
        "evidence": None,
        "synthetic": True,
    }
    assert result["a_to_b"]["status"] == "BLOCKED"
    assert result["a_to_b"]["obligation_count"] == 0
    assert result["a_to_b"]["blockers"] == ["CHECKPOINT_A_BLOCKED"]
    assert result["final_commitment_stage"] == "PROPOSED"
    assert result["simulated_payment_state"] == "NONE"
    assert result["economic_state"]["authorized_irreversible_minor"] == 0
    assert result["economic_state"]["captured_minor"] == 0


def test_injected_capture_failure_voids_hold_and_ends_failed_closed():
    result = CheckpointDSimulatedWorkflow().run("CAPTURE_FAILURE")

    assert result["outcome"] == "SIMULATED_FAILED_CLOSED"
    assert result["failure_code"] == "SIMULATED_CAPTURE_FAILURE"
    assert result["cleanup"] == "SIMULATED_HOLD_VOIDED"
    assert result["final_commitment_stage"] == "FAILED"
    assert result["simulated_payment_state"] == "VOIDED"
    assert result["economic_state"]["captured_minor"] == 0
    assert result["real_provider_called"] is False
    assert result["real_money_moved"] is False


def test_workflow_rejects_unknown_scenario_instead_of_falling_back():
    with pytest.raises(SimulationInputError, match="unknown simulation scenario"):
        CheckpointDSimulatedWorkflow().run("REAL_PROVIDER")


def test_simulation_is_reproducible_for_the_same_named_scenario():
    workflow = CheckpointDSimulatedWorkflow()

    first = workflow.run("HAPPY_PATH")
    second = workflow.run("HAPPY_PATH")

    assert first == second
    assert first["certificate_id"] == second["certificate_id"]


def test_checkpoint_d_demo_cli_emits_machine_readable_non_evidence():
    completed = subprocess.run(
        [
            sys.executable,
            str(REPOSITORY_ROOT / "scripts" / "checkpoint_d_demo.py"),
            "--scenario",
            "CAPTURE_FAILURE",
            "--compact",
        ],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    result = json.loads(completed.stdout)

    assert result["outcome"] == "SIMULATED_FAILED_CLOSED"
    assert result["counts_as_checkpoint_evidence"] is False
    assert result["execution_mode"] == "SIMULATED_LOCAL"
