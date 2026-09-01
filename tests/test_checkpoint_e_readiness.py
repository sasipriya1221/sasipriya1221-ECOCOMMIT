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
    assert isinstance(report["remote_url"], str) and report["remote_url"]


def test_readiness_manifest_protects_authoritative_integration_components():
    required = set(load_readiness_module().REQUIRED_FILES)

    assert {
        "scripts/checkpoint_b8_webhook_evidence.py",
        "scripts/checkpoint_b8_webhook_server.py",
        "scripts/checkpoint_d_evidence_status.py",
        "scripts/checkpoint_d_prepare_operation.py",
        "src/ecocommit/checkpoint_b_evidence.py",
        "src/ecocommit/checkpoint_d_evidence.py",
        "src/ecocommit/durable.py",
        "src/ecocommit/execution.py",
        "src/ecocommit/webhook.py",
    } <= required


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


def test_evidence_slots_can_progress_to_passed_without_changing_checker_code():
    module = load_readiness_module()
    blocked = "\n".join(
        f"<!-- EVIDENCE:{slot} status=BLOCKED -->" for slot in module.EVIDENCE_SLOTS
    )
    passed = blocked.replace("status=BLOCKED", "status=PASSED")

    blocked_statuses, blocked_problems = module._evidence_slot_statuses(blocked)
    passed_statuses, passed_problems = module._evidence_slot_statuses(passed)

    assert not blocked_problems and set(blocked_statuses.values()) == {"BLOCKED"}
    assert not passed_problems and set(passed_statuses.values()) == {"PASSED"}


def test_independent_reproduction_receipt_is_revision_bound(tmp_path):
    module = load_readiness_module()
    revision = "a" * 40
    receipt = tmp_path / "reproduction.json"
    receipt.write_text(json.dumps({
        "schema_version": "E.REPRODUCTION.1",
        "source_revision": revision,
        "independent_machine": True,
        "clean_checkout": True,
        "full_tests_passed": True,
        "dependency_check_passed": True,
        "readiness_local_checks_passed": True,
        "artifact_sha256": "b" * 64,
    }), encoding="utf-8")

    assert module._independent_reproduction_status(
        receipt, source_revision=revision
    )[0] is True
    assert module._independent_reproduction_status(
        receipt, source_revision="c" * 40
    )[0] is False


def test_final_cli_mode_fails_while_real_evidence_is_blocked():
    completed = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--mode", "final"],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    report = json.loads(completed.stdout)

    assert completed.returncode == 1
    assert report["evaluation_mode"] == "final"
    assert report["final_submission_ready"] is False


def test_submission_evidence_contains_no_final_metric_or_media_claims():
    evidence = (REPOSITORY_ROOT / "docs" / "SUBMISSION_EVIDENCE.md").read_text(
        encoding="utf-8"
    )
    normalized = " ".join(evidence.split())

    assert "No final ECOCOMMIT-versus-baseline numbers are available" in normalized
    assert "No final screenshot is retained" in normalized
    assert "No final video is recorded" in normalized
    assert (
        "no payment authorization, capture, refund, webhook delivery, "
        "reconciliation, or settlement was executed"
    ) in normalized


def test_digest_bound_checkpoint_c_protocol_files_force_lf_checkout():
    attributes = (REPOSITORY_ROOT / ".gitattributes").read_text(encoding="utf-8")

    assert "/tests/fixtures/checkpoint_c/*.txt text eol=lf" in attributes
