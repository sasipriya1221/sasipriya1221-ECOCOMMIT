import importlib.util
import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest


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
    assert "LICENSE_OWNER_DECISION_REQUIRED" not in report["blockers"]
    assert report["license_present"] is True
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
    assert report["license_present"] is True
    remote = report["remote_origin"]
    assert remote["configured"] is True
    assert remote["expected_repository"] == "sasipriya1221/sasipriya1221-ECOCOMMIT"
    if remote["verified"]:
        assert remote["repository"].casefold() == remote["expected_repository"].casefold()
        assert report["remote_url"] == (
            "https://github.com/sasipriya1221/sasipriya1221-ECOCOMMIT.git"
        )
    else:
        assert report["remote_url"] is None
        assert any(blocker.startswith("REMOTE_") for blocker in report["blockers"])


@pytest.mark.parametrize(
    "remote_url",
    [
        "https://github.com/sasipriya1221/sasipriya1221-ECOCOMMIT.git",
        "https://github.com/sasipriya1221/sasipriya1221-ECOCOMMIT",
        "git@github.com:sasipriya1221/sasipriya1221-ECOCOMMIT.git",
        "ssh://git@github.com/sasipriya1221/sasipriya1221-ECOCOMMIT.git",
    ],
)
def test_readiness_normalizes_supported_public_github_origins(remote_url):
    assert load_readiness_module()._public_github_repository(remote_url) == (
        "sasipriya1221/sasipriya1221-ECOCOMMIT"
    )


@pytest.mark.parametrize(
    "remote_url",
    [
        r"C:\workspace\ECOCOMMIT",
        "/tmp/ECOCOMMIT",
        "file:///tmp/ECOCOMMIT",
        "http://github.com/sasipriya1221/sasipriya1221-ECOCOMMIT.git",
        "https://token@github.com/sasipriya1221/sasipriya1221-ECOCOMMIT.git",
        "https://github.example/sasipriya1221/sasipriya1221-ECOCOMMIT.git",
        "https://github.com:not-a-port/sasipriya1221/sasipriya1221-ECOCOMMIT.git",
        "https://github.com/sasipriya1221/sasipriya1221-ECOCOMMIT.git?token=secret",
        "https://github.com/sasipriya1221/too/many/parts.git",
    ],
)
def test_readiness_rejects_nonpublic_or_credential_bearing_origins(remote_url):
    assert load_readiness_module()._public_github_repository(remote_url) is None


def test_readiness_manifest_protects_authoritative_integration_components():
    required = set(load_readiness_module().REQUIRED_FILES)

    assert {
        ".github/workflows/offline-regression.yml",
        "deploy/ecocommit.env.example",
        "deploy/nginx.conf.template",
        "deploy/proxy-policy.inc.template",
        "deploy/wsgi.py",
        "docs/DEPLOYMENT_READINESS.md",
        "docs/LICENSE_DECISION.md",
        "scripts/checkpoint_a_diagnostics.py",
        "scripts/checkpoint_b8_finalize.py",
        "scripts/checkpoint_b8_webhook_evidence.py",
        "scripts/checkpoint_b8_webhook_server.py",
        "scripts/checkpoint_c_final_held_out.py",
        "scripts/checkpoint_d_evidence_status.py",
        "scripts/checkpoint_d_prepare_operation.py",
        "scripts/checkpoint_e_readiness.py",
        "src/ecocommit/checkpoint_b_evidence.py",
        "src/ecocommit/checkpoint_c_final.py",
        "src/ecocommit/checkpoint_d_evidence.py",
        "src/ecocommit/deployment.py",
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
    source_tree_id = "b" * 40
    dependency_lock_sha256 = "c" * 64
    receipt = tmp_path / "reproduction.json"
    value = module.IndependentReproductionReceipt.create(
        source_revision=revision,
        source_tree_id=source_tree_id,
        dependency_lock_sha256=dependency_lock_sha256,
        machine_identity_sha256="d" * 64,
        verifier_identity_sha256="e" * 64,
        platform_sha256="f" * 64,
        python_version="3.11.10",
        started_at_utc=datetime(2026, 9, 2, 5, 0, tzinfo=UTC),
        completed_at_utc=datetime(2026, 9, 2, 5, 10, tzinfo=UTC),
        collected_tests=450,
        passed_tests=450,
        failed_tests=0,
        error_tests=0,
        readiness_checks_collected=10,
        readiness_checks_passed=10,
        test_report_sha256="1" * 64,
        dependency_check_report_sha256="2" * 64,
        readiness_report_sha256="3" * 64,
        commands_manifest_sha256="4" * 64,
        artifact_bundle_sha256="5" * 64,
        evidence_reference=(
            "github-actions://sasipriya1221/sasipriya1221-ECOCOMMIT/"
            "runs/1/artifacts/independent-reproduction"
        ),
    )
    receipt.write_text(value.model_dump_json(), encoding="utf-8")

    assert module._independent_reproduction_status(
        receipt,
        source_revision=revision,
        source_tree_id=source_tree_id,
        dependency_lock_sha256=dependency_lock_sha256,
    )[0] is True
    assert module._independent_reproduction_status(
        receipt,
        source_revision="f" * 40,
        source_tree_id=source_tree_id,
        dependency_lock_sha256=dependency_lock_sha256,
    )[0] is False

    tampered = json.loads(receipt.read_text(encoding="utf-8"))
    tampered["passed_tests"] -= 1
    receipt.write_text(json.dumps(tampered), encoding="utf-8")
    assert module._independent_reproduction_status(
        receipt,
        source_revision=revision,
        source_tree_id=source_tree_id,
        dependency_lock_sha256=dependency_lock_sha256,
    ) == (False, "receipt=schema_or_digest_invalid")


def test_independent_reproduction_receipt_rejects_inexact_or_wrong_repo_reference():
    module = load_readiness_module()
    common = {
        "source_revision": "a" * 40,
        "source_tree_id": "b" * 40,
        "dependency_lock_sha256": "c" * 64,
        "machine_identity_sha256": "d" * 64,
        "verifier_identity_sha256": "e" * 64,
        "platform_sha256": "f" * 64,
        "python_version": "3.11.10",
        "started_at_utc": datetime(2026, 9, 2, 5, 0, tzinfo=UTC),
        "completed_at_utc": datetime(2026, 9, 2, 5, 10, tzinfo=UTC),
        "collected_tests": 450,
        "passed_tests": 450,
        "failed_tests": 0,
        "error_tests": 0,
        "readiness_checks_collected": 10,
        "readiness_checks_passed": 10,
        "test_report_sha256": "1" * 64,
        "dependency_check_report_sha256": "2" * 64,
        "readiness_report_sha256": "3" * 64,
        "commands_manifest_sha256": "4" * 64,
        "artifact_bundle_sha256": "5" * 64,
    }

    with pytest.raises(ValueError, match="exact GitHub Actions reference"):
        module.IndependentReproductionReceipt.create(
            **common,
            evidence_reference="github-actions://owner/repo/runs/1",
        )
    with pytest.raises(ValueError, match="another repository"):
        module.IndependentReproductionReceipt.create(
            **common,
            evidence_reference=(
                "github-actions://someone/else/runs/1/artifacts/reproduction"
            ),
        )


@pytest.mark.parametrize("raw", [
    '{"schema_version":"E.REPRODUCTION.2","schema_version":"E.REPRODUCTION.2"}',
    '{"schema_version":"E.REPRODUCTION.2","score":NaN}',
    '[]',
])
def test_independent_reproduction_receipt_requires_strict_object_json(tmp_path, raw):
    receipt = tmp_path / "reproduction.json"
    receipt.write_text(raw, encoding="utf-8")

    verified, detail = load_readiness_module()._independent_reproduction_status(
        receipt,
        source_revision="a" * 40,
        source_tree_id="b" * 40,
        dependency_lock_sha256="c" * 64,
    )

    assert verified is False
    assert detail in {"receipt=invalid_json", "receipt=object_required"}


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


def test_checkpoint_e_report_distinguishes_order_boundary_from_payment_lifecycle():
    report = (REPOSITORY_ROOT / "CHECKPOINT_E_VALIDATION.md").read_text(
        encoding="utf-8"
    )
    normalized = " ".join(report.split())

    assert (
        "retained prior evidence proves Razorpay Test authentication and order "
        "creation only"
    ) in normalized
    assert (
        "No genuine Checkout authorization, capture, refund, webhook lifecycle, "
        "or reconciliation result is claimed"
    ) in normalized
    assert "No Razorpay credential, request, Test Mode transaction" not in normalized
    assert "passed 392/392 tests" in normalized


def test_byte_digest_bound_inputs_force_lf_checkout():
    attributes = (REPOSITORY_ROOT / ".gitattributes").read_text(encoding="utf-8")

    assert "/tests/fixtures/checkpoint_c/*.txt text eol=lf" in attributes
    assert "/requirements-dev.lock text eol=lf" in attributes
