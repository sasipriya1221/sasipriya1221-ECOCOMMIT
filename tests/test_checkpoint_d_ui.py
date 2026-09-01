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
