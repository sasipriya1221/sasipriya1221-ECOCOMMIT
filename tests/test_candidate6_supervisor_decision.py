from scripts.candidate6_supervisor_decision import canonical_sha256, decide, extract_checked_out_sha


def signed(**payload):
    payload = dict(payload)
    payload["receipt_sha256"] = canonical_sha256(payload)
    return payload


def test_checkout_provenance_parser_requires_unique_git_log_sha():
    sha = "6d04d53e62c0593c1c93124080f4a22120da6a7f"
    log = f"[command]/usr/bin/git log -1 --format=%H\n{sha}\n##[group]Removing auth\n"
    assert extract_checked_out_sha(log) == sha


def test_checkout_provenance_parser_fails_on_missing_or_conflicting_sha():
    import pytest
    with pytest.raises(ValueError):
        extract_checked_out_sha("no checkout provenance")
    with pytest.raises(ValueError):
        extract_checked_out_sha(
            "git log -1 --format=%H\n" + "1" * 40 + "\n"
            "git log -1 --format=%H\n" + "2" * 40 + "\n"
        )


def test_development_pass_advances_only_when_complete():
    receipt = signed(
        qualification_state="COMPLETE",
        passed=True,
        terminal_semantic_cases=60,
        provider_deferred_cases=0,
    )
    assert decide("development", receipt).action == "FREEZE"


def test_development_provider_incomplete_waits_without_semantic_failure():
    receipt = signed(qualification_state="PROVIDER_INCOMPLETE", passed=False)
    decision = decide("development", receipt)
    assert decision.action == "WAIT"
    assert decision.reason == "PROVIDER_INCOMPLETE"


def test_fail_and_blocked_are_fail_closed():
    assert decide("checkpoint_a", signed(stage="checkpoint_a", status="FAILED")).action == "STOP"
    assert decide("checkpoint_b", signed(stage="checkpoint_b", status="BLOCKED")).action == "STOP"


def test_missing_receipt_fails_closed():
    assert decide("development", None).reason == "MISSING_RECEIPT"


def test_unsigned_receipt_fails_closed():
    decision = decide("checkpoint_a", {"stage": "checkpoint_a", "status": "PASS"})
    assert decision.action == "STOP"
    assert decision.reason == "INVALID_RECEIPT_HASH"


def test_invalid_hash_fails_closed():
    receipt = signed(stage="checkpoint_a", status="PASS")
    receipt["receipt_sha256"] = "0" * 64
    assert decide("checkpoint_a", receipt).reason == "INVALID_RECEIPT_HASH"


def test_receipt_stage_mismatch_fails_closed():
    receipt = signed(stage="checkpoint_b", status="PASS")
    assert decide("checkpoint_a", receipt).reason == "RECEIPT_STAGE_MISMATCH"


def test_human_action_required_stops_automation():
    receipt = signed(stage="checkpoint_b", status="PASS", human_action_required=True)
    assert decide("checkpoint_b", receipt).action == "STOP_HUMAN"


def test_holdout_pass_requires_all_thresholds_and_zero_safety_errors():
    receipt = signed(
        qualification_state="COMPLETE",
        passed=True,
        terminal_semantic_cases=60,
        provider_deferred_cases=0,
        counts={
            "fail_open": 0,
            "dropped_guards": 0,
            "dropped_exceptions": 0,
            "conservation_failures": 0,
            "unknown_authorized": 0,
        },
        metrics={
            "case_pass_rate": 0.95,
            "selective_semantic_reliability": 0.97,
            "autonomous_coverage": 0.60,
            "ambiguous_clarification_accuracy": 0.90,
        },
    )
    assert decide("holdout", receipt).action == "PREREGISTER_A"


def test_holdout_provider_incomplete_stops_one_shot_progression():
    receipt = signed(qualification_state="PROVIDER_INCOMPLETE", passed=False)
    assert decide("holdout", receipt).action == "STOP"


def test_holdout_nonzero_safety_error_stops():
    receipt = signed(
        qualification_state="COMPLETE",
        passed=True,
        terminal_semantic_cases=60,
        provider_deferred_cases=0,
        counts={
            "fail_open": 1,
            "dropped_guards": 0,
            "dropped_exceptions": 0,
            "conservation_failures": 0,
            "unknown_authorized": 0,
        },
        metrics={
            "case_pass_rate": 1.0,
            "selective_semantic_reliability": 1.0,
            "autonomous_coverage": 1.0,
            "ambiguous_clarification_accuracy": 1.0,
        },
    )
    assert decide("holdout", receipt).action == "STOP"


def test_downstream_pass_receipts_are_stage_typed_and_signed():
    for stage, expected in (
        ("checkpoint_a", "ADVANCE_B"),
        ("checkpoint_b", "ADVANCE_C"),
        ("checkpoint_c", "ADVANCE_D"),
        ("checkpoint_d", "ADVANCE_E"),
        ("checkpoint_e", "COMPLETE"),
    ):
        assert decide(stage, signed(stage=stage, status="PASS")).action == expected
