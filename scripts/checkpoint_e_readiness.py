from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import unquote


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
REQUIRED_FILES = (
    ".gitattributes",
    "README.md",
    "PROGRESS.md",
    "pyproject.toml",
    "requirements-dev.lock",
    "CHECKPOINT_A_RUNBOOK.md",
    "CHECKPOINT_B_VALIDATION.md",
    "CHECKPOINT_C_VALIDATION.md",
    "CHECKPOINT_D_VALIDATION.md",
    "docs/ARCHITECTURE.md",
    "docs/DEMO_RUNBOOK.md",
    "docs/ENGINEERING_LOG.md",
    "docs/PITCH_OUTLINE.md",
    "docs/REPRODUCIBILITY.md",
    "docs/SUBMISSION_EVIDENCE.md",
    "docs/THREAT_MODEL.md",
)
README_HEADINGS = (
    "## Why ECOCOMMIT",
    "## Architecture",
    "## Checkpoint truth",
    "## Quick start",
    "## Local safety-console demo",
    "## Evidence and reports",
    "## Submission evidence status",
    "## Safety and limitations",
    "## License",
)
EVIDENCE_MARKERS = (
    "EVIDENCE:CHECKPOINT_A_FINAL_METRICS status=BLOCKED",
    "EVIDENCE:CHECKPOINT_B_RAZORPAY_TEST status=BLOCKED",
    "EVIDENCE:CHECKPOINT_C_FINAL_COMPARISON status=BLOCKED",
    "EVIDENCE:CHECKPOINT_D_FINAL_INTEGRATION status=BLOCKED",
    "EVIDENCE:FINAL_SCREENSHOTS status=BLOCKED",
    "EVIDENCE:FINAL_VIDEO status=BLOCKED",
)
TRANSIENT_PREFIXES = (
    ".pytest_cache/",
    ".test-tmp",
    ".venv/",
    "artifacts/",
    "build/",
    "dist/",
)
SECRET_PATTERNS = (
    re.compile(r"gsk_[A-Za-z0-9]{20,}"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"rzp_(?:test|live)_[A-Za-z0-9]{8,}"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
)
ABSOLUTE_LOCAL_PATH = re.compile(
    r"(?:[A-Za-z]:[\\/](?:Users|Documents)[\\/]|/Users/|/home/)",
    re.IGNORECASE,
)
MARKDOWN_LINK = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")


@dataclass(frozen=True)
class Check:
    name: str
    passed: bool
    detail: str


def _git(root: Path, *arguments: str, check: bool = True) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=root,
        check=check,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _tracked_files(root: Path) -> tuple[str, ...]:
    output = _git(root, "ls-files")
    return tuple(line.replace("\\", "/") for line in output.splitlines() if line)


def _read_text(root: Path, relative_path: str) -> str | None:
    try:
        return (root / relative_path).read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None


def _broken_markdown_links(root: Path, tracked: tuple[str, ...]) -> list[str]:
    broken: list[str] = []
    for relative_path in tracked:
        if not relative_path.lower().endswith(".md"):
            continue
        text = _read_text(root, relative_path)
        if text is None:
            continue
        for match in MARKDOWN_LINK.finditer(text):
            raw_target = match.group(1).strip().strip("<>").split(maxsplit=1)[0]
            if not raw_target or raw_target.startswith(("#", "http://", "https://", "mailto:")):
                continue
            target_without_fragment = unquote(raw_target.split("#", 1)[0].split("?", 1)[0])
            resolved = (root / Path(relative_path).parent / target_without_fragment).resolve()
            try:
                resolved.relative_to(root.resolve())
            except ValueError:
                broken.append(f"{relative_path}: link escapes repository: {raw_target}")
                continue
            if not resolved.exists():
                broken.append(f"{relative_path}: missing target: {raw_target}")
    return broken


def _sensitive_matches(root: Path, tracked: tuple[str, ...]) -> list[str]:
    matches: list[str] = []
    for relative_path in tracked:
        text = _read_text(root, relative_path)
        if text is None:
            continue
        if any(pattern.search(text) for pattern in SECRET_PATTERNS):
            matches.append(relative_path)
    return matches


def _markdown_absolute_paths(root: Path, tracked: tuple[str, ...]) -> list[str]:
    matches: list[str] = []
    for relative_path in tracked:
        if not relative_path.lower().endswith(".md"):
            continue
        text = _read_text(root, relative_path)
        if text is not None and ABSOLUTE_LOCAL_PATH.search(text):
            matches.append(relative_path)
    return matches


def _upstream_counts(root: Path) -> tuple[int | None, int | None]:
    completed = subprocess.run(
        ["git", "rev-list", "--left-right", "--count", "@{upstream}...HEAD"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        return None, None
    behind, ahead = completed.stdout.split()
    return int(behind), int(ahead)


def build_report(root: Path = REPOSITORY_ROOT) -> dict[str, object]:
    root = root.resolve()
    tracked = _tracked_files(root)
    tracked_set = set(tracked)
    checks: list[Check] = []

    missing = sorted(set(REQUIRED_FILES) - tracked_set)
    checks.append(Check("required_public_files", not missing, f"missing={missing}"))

    readme = _read_text(root, "README.md") or ""
    missing_headings = [heading for heading in README_HEADINGS if heading not in readme]
    checks.append(Check("readme_structure", not missing_headings, f"missing={missing_headings}"))

    evidence = _read_text(root, "docs/SUBMISSION_EVIDENCE.md") or ""
    missing_markers = [marker for marker in EVIDENCE_MARKERS if marker not in evidence]
    checks.append(Check("blocked_evidence_markers", not missing_markers, f"missing={missing_markers}"))

    broken_links = _broken_markdown_links(root, tracked)
    checks.append(Check("local_markdown_links", not broken_links, f"broken={broken_links}"))

    absolute_paths = _markdown_absolute_paths(root, tracked)
    checks.append(Check("portable_markdown_paths", not absolute_paths, f"files={absolute_paths}"))

    transient = sorted(
        path for path in tracked if path.startswith(TRANSIENT_PREFIXES) or path.endswith(".pyc")
    )
    checks.append(Check("no_tracked_transient_outputs", not transient, f"files={transient}"))

    sensitive = _sensitive_matches(root, tracked)
    checks.append(Check("current_tree_secret_markers", not sensitive, f"files={sensitive}"))

    progress = _read_text(root, "PROGRESS.md") or ""
    truth_terms = ("BUILT", "LOCALLY VALIDATED", "BLOCKED", "PASSED", "NOT PASSED")
    absent_truth_terms = [term for term in truth_terms if term not in progress]
    checks.append(
        Check(
            "checkpoint_truth_vocabulary",
            not absent_truth_terms,
            f"missing={absent_truth_terms}",
        )
    )

    local_validation_pass = all(item.passed for item in checks)
    status_output = _git(root, "status", "--porcelain=v1")
    clean = not bool(status_output)
    behind, ahead = _upstream_counts(root)
    remote_url = _git(root, "config", "--get", "remote.origin.url", check=False) or None
    revision = _git(root, "rev-parse", "HEAD")
    license_present = any(path in tracked_set for path in ("LICENSE", "LICENSE.md", "LICENSE.txt"))

    blockers = list(EVIDENCE_MARKERS)
    if not license_present:
        blockers.append("LICENSE_OWNER_DECISION_REQUIRED")
    if not remote_url:
        blockers.append("REMOTE_ORIGIN_NOT_CONFIGURED")
    if not clean:
        blockers.append("WORKING_TREE_NOT_CLEAN")
    if ahead is None:
        blockers.append("UPSTREAM_STATE_UNAVAILABLE")
    elif ahead:
        blockers.append(f"LOCAL_COMMITS_NOT_PUSHED:{ahead}")
    if behind:
        blockers.append(f"LOCAL_BRANCH_BEHIND_UPSTREAM:{behind}")
    blockers.append("INDEPENDENT_CLEAN_MACHINE_REPRODUCTION_NOT_RETAINED")

    return {
        "schema_version": "E.READINESS.1",
        "source_revision": revision,
        "working_tree_clean": clean,
        "remote_url": remote_url,
        "upstream": {"behind": behind, "ahead": ahead},
        "license_present": license_present,
        "checks": [asdict(item) for item in checks],
        "local_repository_checks_pass": local_validation_pass,
        "final_submission_ready": local_validation_pass and not blockers,
        "blockers": blockers,
        "truth_contract": {
            "local_validation_is_not_checkpoint_pass": True,
            "blocked_evidence_must_not_be_filled_with_fixtures": True,
            "simulation_is_not_provider_evidence": True,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate local Checkpoint E repository/submission structure."
    )
    parser.add_argument("--root", type=Path, default=REPOSITORY_ROOT)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = build_report(args.root)
    encoded = json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    return 0 if report["local_repository_checks_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
