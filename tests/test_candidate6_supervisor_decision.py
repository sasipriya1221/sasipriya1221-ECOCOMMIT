from scripts.candidate6_supervisor_decision import canonical_sha256, decide


def signed(**payload):
    payload = dict(payload)
    payload["receipt_sha256"] = canonical_sha256(payload)
    return payload


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
    assert decide("checkpoint_a", signed(status="FAILED")).action == "STOP"
    assert decide("checkpoint_b", signed(status="BLOCKED")).action == "STOP"


def test_missing_receipt_fails_closed():
    assert decide("development", None).reason == "MISSING_RECEIPT"


def test_invalid_hash_fails_closed():
    receipt = signed(status="PASS")
    receipt["receipt_sha256"] = "0" * 64
    assert decide("checkpoint_a", receipt).reason == "INVALID_RECEIPT_HASH"


def test_human_action_required_stops_automation():
    receipt = signed(status="PASS", human_action_required=True)
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
