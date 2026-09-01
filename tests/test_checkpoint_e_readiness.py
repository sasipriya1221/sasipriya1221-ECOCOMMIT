import importlib.util
import json
import subprocess
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPOSITORY_ROOT / "scripts" / "checkpoint_e_readiness.py"


def load_readiness_module():
    spec = importlib.util.spec_from_file_location("checkpoint_e_readiness", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_repository_readiness_checks_pass_locally_but_final_submission_stays_blocked():
    report = load_readiness_module().build_report(REPOSITORY_ROOT)

    assert report["schema_version"] == "E.READINESS.1"
    assert report["local_repository_checks_pass"] is True
    assert report["final_submission_ready"] is False
    assert report["truth_contract"] == {
        "local_validation_is_not_checkpoint_pass": True,
        "blocked_evidence_must_not_be_filled_with_fixtures": True,
        "simulation_is_not_provider_evidence": True,
    }
    assert "LICENSE_OWNER_DECISION_REQUIRED" in report["blockers"]
    assert all(
        marker in report["blockers"]
        for marker in load_readiness_module().EVIDENCE_MARKERS
    )


def test_readiness_cli_emits_machine_readable_blocked_report():
    completed = subprocess.run(
        [sys.executable, str(SCRIPT_PATH)],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    report = json.loads(completed.stdout)

    assert report["local_repository_checks_pass"] is True
    assert report["final_submission_ready"] is False
    assert report["license_present"] is False
    assert report["remote_url"].endswith("sasipriya1221-ECOCOMMIT.git")


def test_readiness_checker_detects_broken_relative_markdown_link(tmp_path):
    root = tmp_path.resolve()
    (root / "docs").mkdir()
    (root / "docs" / "guide.md").write_text(
        "[missing](../does-not-exist.md)\n[external](https://example.org)\n",
        encoding="utf-8",
    )
    broken = load_readiness_module()._broken_markdown_links(
        root,
        ("docs/guide.md",),
    )

    assert broken == ["docs/guide.md: missing target: ../does-not-exist.md"]


def test_submission_evidence_contains_no_final_metric_or_media_claims():
    evidence = (REPOSITORY_ROOT / "docs" / "SUBMISSION_EVIDENCE.md").read_text(
        encoding="utf-8"
    )
    normalized = " ".join(evidence.split())

    assert "No final ECOCOMMIT-versus-baseline numbers are available" in normalized
    assert "No final screenshot is retained" in normalized
    assert "No final video is recorded" in normalized
    assert "No Razorpay request was made" in normalized
