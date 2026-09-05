from __future__ import annotations

import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"


def test_all_third_party_workflow_actions_are_commit_pinned():
    unpinned = []
    for path in sorted(WORKFLOWS.glob("*.yml")):
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            match = re.search(r"\buses:\s*([^\s#]+)", line)
            if match and not re.fullmatch(r"[^@\s]+@[0-9a-f]{40}", match.group(1)):
                unpinned.append(f"{path.name}:{line_number}:{match.group(1)}")
    assert unpinned == []


def test_checkout_never_persists_repository_credentials():
    for path in sorted(WORKFLOWS.glob("*.yml")):
        lines = path.read_text(encoding="utf-8").splitlines()
        for index, line in enumerate(lines):
            if "uses: actions/checkout@" not in line:
                continue
            nearby = "\n".join(lines[index + 1:index + 7])
            assert "persist-credentials: false" in nearby, path.name


def test_secrets_are_step_scoped_and_provider_bodies_are_not_printed():
    for path in sorted(WORKFLOWS.glob("*.yml")):
        text = path.read_text(encoding="utf-8")
        assert not re.search(
            r"(?m)^    env:\s*$\n(?:^      [^\n]*$\n)*^      [^\n]*secrets\.",
            text,
        ), path.name
        assert "print(body" not in text
        assert "print(raw" not in text
        if "python -m pip install" in text:
            assert "--require-hashes -r requirements-dev.lock" in text
            assert "--no-deps --no-build-isolation -e ." in text


def test_inline_credentialed_http_preflights_do_not_forward_auth_on_redirects():
    credentialed = []
    for path in sorted(WORKFLOWS.glob("*.yml")):
        text = path.read_text(encoding="utf-8")
        if '"Authorization"' not in text and "'Authorization'" not in text:
            continue
        credentialed.append(path.name)
        assert ".add_unredirected_header(" in text, path.name
        assert ".geturl()" in text, path.name
        assert ".full_url" in text, path.name
    assert credentialed == [
        "candidate6-freeze.yml",
        "candidate6-holdout-decision.yml",
        "candidate6-official-prereg.yml",
        "candidate6-provider-readiness.yml",
        "candidate6-supervisor-kick.yml",
        "candidate6-supervisor.yml",
        "checkpoint-a-candidate6.yml",
        "checkpoint-a-live.yml",
        "provider-preflight.yml",
        "razorpay-test-preflight.yml",
    ]


def test_secret_bearing_workflows_require_explicit_manual_dispatch():
    credentialed = []
    for path in sorted(WORKFLOWS.glob("*.yml")):
        text = path.read_text(encoding="utf-8")
        if "secrets." not in text:
            continue
        credentialed.append(path.name)
        trigger_block = text.split("\njobs:", 1)[0]
        assert re.search(r"(?m)^  workflow_dispatch:\s*$", trigger_block), path.name
        assert not re.search(r"(?m)^  (?:push|pull_request(?:_target)?):", trigger_block), path.name
    assert credentialed == [
        "candidate6-development-dispatch.yml",
        "candidate6-holdout-dispatch.yml",
        "candidate6-provider-readiness.yml",
        "candidate7-development-dispatch.yml",
        "candidate7-diagnostic-d003-incremental.yml",
        "candidate7-diagnostic-pass1-incremental.yml",
        "candidate7-diagnostic-sweep.yml",
        "candidate7-provider-readiness.yml",
        "candidate7-rate-limit-diagnostic.yml",
        "checkpoint-a-candidate6.yml",
        "checkpoint-a-candidate7.yml",
        "checkpoint-a-live.yml",
        "checkpoint-a-qwen-smoke.yml",
        "checkpoint-a-smoke.yml",
        "groq-preflight.yml",
        "provider-preflight.yml",
        "razorpay-test-lifecycle.yml",
        "razorpay-test-preflight.yml",
    ]


def test_candidate7_development_dispatch_is_manual_hard_bound_and_secret_scoped():
    workflow = (WORKFLOWS / "candidate7-development-dispatch.yml").read_text(encoding="utf-8")
    trigger_block = workflow.split("\nconcurrency:", 1)[0]
    assert re.search(r"(?m)^  workflow_dispatch:\s*$", trigger_block)
    assert not re.search(r"(?m)^  (?:push|pull_request(?:_target)?):", trigger_block)
    frozen_sha = "12d121f80a6cacd94376c6d2b7bce7dff5212eb5"
    assert "source_sha" not in trigger_block
    assert f"ref: {frozen_sha}" in workflow
    assert f'expected = "{frozen_sha}"' in workflow
    assert "persist-credentials: false" in workflow
    assert "ECOCOMMIT_LLM_API_KEY: ${{ secrets.ECOCOMMIT_GROQ_API_KEY }}" in workflow
    assert "python -m pytest" in workflow
    assert "python scripts/candidate7_pass2_qualification.py self-check" in workflow
    assert "python scripts/candidate7_pass2_qualification.py qualify --directory artifacts/candidate7-pass2-qualification" in workflow
    assert "candidate7_qualify.py" not in workflow
    assert '"qualification_mode": "candidate7-d003-d009"' in workflow
    assert "official_checkpoint_a_cases_used" in workflow
    assert "holdout_opened" in workflow


def test_candidate7_request_bridge_is_secretless_exact_source_and_duplicate_safe():
    workflow = (WORKFLOWS / "candidate7-development-request.yml").read_text(encoding="utf-8")
    trigger_block = workflow.split("\nconcurrency:", 1)[0]
    assert re.search(r"(?m)^  push:\s*$", trigger_block)
    assert "evidence/candidate7-development-request.json" in trigger_block
    assert "secrets." not in workflow
    assert "actions: write" in workflow
    assert "candidate7-structural-semantic-fix" in workflow
    assert "duplicate Candidate-7 development dispatch for this exact source refused" in workflow
    assert "gh workflow run candidate7-development-dispatch.yml" in workflow
    assert "-f source_sha=" not in workflow
    assert '"candidate7-d003-d009"' in workflow
    assert '"scripts/candidate7_pass2_qualification.py"' in workflow
    assert "persist-credentials: false" in workflow


def test_candidate6_freeze_workflow_is_manual_secretless_and_single_purpose():
    workflow = (WORKFLOWS / "candidate6-freeze.yml").read_text(encoding="utf-8")
    trigger_block = workflow.split("\nconcurrency:", 1)[0]
    assert re.search(r"(?m)^  workflow_dispatch:\s*$", trigger_block)
    assert "secrets." not in workflow
    assert "ECOCOMMIT_LLM_API_KEY" not in workflow
    assert "RAZORPAY" not in workflow
    assert "candidate6-holdout-dispatch.yml/dispatches" not in workflow
    assert "Freeze Gate" in workflow
    assert "candidate6-freeze-receipt.json" in workflow


def test_candidate6_holdout_decision_is_secretless_mechanical_and_non_provider():
    workflow = (WORKFLOWS / "candidate6-holdout-decision.yml").read_text(encoding="utf-8")
    trigger_block = workflow.split("\nconcurrency:", 1)[0]
    assert re.search(r"(?m)^  workflow_dispatch:\s*$", trigger_block)
    assert "secrets." not in workflow
    assert "ECOCOMMIT_LLM_API_KEY" not in workflow
    assert "RAZORPAY" not in workflow
    assert "case_pass_rate" in workflow
    assert "0.95" in workflow and "0.97" in workflow and "0.60" in workflow and "0.90" in workflow
    assert "holdout_rerun_permitted': False" in workflow
    assert "post_holdout_semantic_modification_permitted': False" in workflow


def test_candidate6_supervisor_is_minimal_scheduled_fail_closed_and_duplicate_safe():
    workflow = (WORKFLOWS / "candidate6-supervisor.yml").read_text(encoding="utf-8")
    trigger_block = workflow.split("\nconcurrency:", 1)[0]
    assert re.search(r"(?m)^  workflow_dispatch:\s*$", trigger_block)
    assert re.search(r"(?m)^  schedule:\s*$", trigger_block)
    assert "candidate6-fail-closed-supervisor" in workflow
    assert "cancel-in-progress: false" in workflow
    assert "secrets." not in workflow
    assert "ECOCOMMIT_LLM_API_KEY" not in workflow
    assert "RAZORPAY" not in workflow
    assert "freeze workflow already has history; automatic duplicate dispatch refused" in workflow
    assert "holdout dispatcher already has history; duplicate dispatch refused" in workflow
    assert "holdout decision workflow already has history; duplicate decision refused" in workflow
    assert "STOP_HOLDOUT_RERUN_DETECTED" in workflow
    assert "STOP_INTERNAL_FAILED" in workflow
    assert "candidate6_supervisor_decision" in workflow


def test_candidate6_supervisor_handoff_is_event_driven_secretless_and_narrow():
    workflow = (WORKFLOWS / "candidate6-supervisor-kick.yml").read_text(encoding="utf-8")
    trigger_block = workflow.split("\nconcurrency:", 1)[0]
    assert re.search(r"(?m)^  workflow_run:\s*$", trigger_block)
    for name in (
        "Candidate 6 - Development Qualification (Dispatcher)",
        "Candidate 6 - Freeze Gate",
        "Candidate 6 - Internal Holdout Qualification (Dispatcher)",
        "Candidate 6 - Holdout Decision Receipt",
    ):
        assert name in trigger_block
    assert "types: [completed]" in trigger_block
    assert "candidate6-supervisor.yml/dispatches" in workflow
    assert "secrets." not in workflow
    assert "ECOCOMMIT_LLM_API_KEY" not in workflow
    assert "RAZORPAY" not in workflow


def test_offline_regression_covers_every_change_and_static_checks():
    workflow = (WORKFLOWS / "offline-regression.yml").read_text(encoding="utf-8")
    trigger_block = workflow.split("\nconcurrency:", 1)[0]
    assert "paths:" not in trigger_block
    assert "paths-ignore:" not in trigger_block
    assert re.search(r"(?m)^  push:\s*$", trigger_block)
    assert re.search(r"(?m)^  pull_request:\s*$", trigger_block)
    assert "python -m compileall -q src scripts tests" in workflow
    assert "node --check ui/app.js" in workflow
    assert "git diff --check" in workflow


def test_hash_lock_includes_build_backend_for_a_fresh_venv():
    lock = (ROOT / "requirements-dev.lock").read_text(encoding="utf-8")
    lines = lock.splitlines()
    for distribution in ("setuptools", "wheel"):
        matches = [index for index, line in enumerate(lines) if line.startswith(f"{distribution}==")]
        assert len(matches) == 1, distribution
        index = matches[0]
        assert lines[index].endswith(" \\")
        assert re.fullmatch(r"  --hash=sha256:[0-9a-f]{64}", lines[index + 1])


def test_checkout_callback_is_ignored_and_runbook_moves_it_to_private_artifacts():
    callback = "ecocommit-razorpay-checkout-callback.json"
    ignored = subprocess.run(
        ["git", "check-ignore", "--quiet", "--no-index", callback],
        cwd=ROOT,
        check=False,
    )
    runbook = (ROOT / "docs" / "REPRODUCIBILITY.md").read_text(encoding="utf-8")
    assert ignored.returncode == 0
    assert f"Move-Item -LiteralPath {callback}" in runbook
    assert runbook.count(f"artifacts\\private\\{callback}") == 3
