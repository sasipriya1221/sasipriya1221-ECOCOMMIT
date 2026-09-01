from pathlib import Path


UI_DIR = Path(__file__).resolve().parents[1] / "ui"


def test_ui_defaults_to_unverified_and_never_presents_a_real_commit_control():
    html = (UI_DIR / "index.html").read_text(encoding="utf-8")
    script = (UI_DIR / "app.js").read_text(encoding="utf-8")

    assert "MODE UNVERIFIED — EXECUTION DISABLED" in html
    assert "Real money movement" in html
    assert "Disabled" in html
    assert "SIMULATION ONLY" in html
    assert "/v1/commit/simulate" in script
    assert 'fetch("/v1/commit",' not in script


def test_ui_has_distinct_simulated_and_real_test_mode_labels():
    script = (UI_DIR / "app.js").read_text(encoding="utf-8")

    assert "SIMULATION MODE — NO PROVIDER CALLS · NO MONEY MOVEMENT" in script
    assert "REAL INTEGRATION TEST MODE — RAZORPAY TEST MODE ONLY · NO REAL MONEY" in script
    assert "no acceptance inferred" in script


def test_ui_renders_economic_state_and_explicit_failure_feedback():
    html = (UI_DIR / "index.html").read_text(encoding="utf-8")
    script = (UI_DIR / "app.js").read_text(encoding="utf-8")

    assert "Progressive commitment trace" in html
    assert 'id="requested-exposure"' in html
    assert 'id="authorized-exposure"' in html
    assert 'id="captured-exposure"' in html
    assert 'id="workflow-alert"' in html
    assert 'role="alert"' in html
    assert "CHECKPOINT_A_BLOCKED" in html
    assert "CAPTURE_FAILURE" in html
    assert "renderWorkflow" in script
    assert "Simulation stopped safely" in script
    assert "correlation" in script
    assert "Service returned an unreadable response" in script
    assert "correlation unavailable" in script


def test_status_failure_resets_stale_gate_acceptance_in_the_ui():
    script = (UI_DIR / "app.js").read_text(encoding="utf-8")

    assert "function clearGateCards" in script
    assert 'card.dataset.accepted = "false"' in script
    assert "renderStatusUnavailable" in script
    assert "DISABLED (OUT OF SCOPE)" in script
