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
            nearby = "\n".join(lines[index + 1:index + 5])
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

    assert credentialed == ["checkpoint-a-live.yml", "provider-preflight.yml", "razorpay-test-preflight.yml"]


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
        "checkpoint-a-live.yml",
        "checkpoint-a-qwen-smoke.yml",
        "checkpoint-a-smoke.yml",
        "groq-preflight.yml",
        "provider-preflight.yml",
        "razorpay-test-lifecycle.yml",
        "razorpay-test-preflight.yml",
    ]


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
        matches = [
            index
            for index, line in enumerate(lines)
            if line.startswith(f"{distribution}==")
        ]
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
