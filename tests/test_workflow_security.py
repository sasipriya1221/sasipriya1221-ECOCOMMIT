from __future__ import annotations

import re
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


def test_offline_regression_covers_runtime_ui_workflows_and_static_checks():
    workflow = (WORKFLOWS / "offline-regression.yml").read_text(encoding="utf-8")

    assert workflow.count("- '.github/workflows/**'") == 2
    assert workflow.count("- 'ui/**'") == 2
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
