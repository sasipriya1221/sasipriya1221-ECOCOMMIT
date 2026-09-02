from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Literal
from urllib.parse import unquote, urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ecocommit._canonical import sha256_hex, strict_json_loads


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
MAX_REPRODUCTION_RECEIPT_BYTES = 256 * 1024
EXPECTED_REMOTE_REPOSITORY = "sasipriya1221/sasipriya1221-ECOCOMMIT"
REQUIRED_FILES = (
    ".gitattributes",
    ".github/workflows/offline-regression.yml",
    "README.md",
    "PROGRESS.md",
    "pyproject.toml",
    "requirements-dev.lock",
    "CHECKPOINT_A_RUNBOOK.md",
    "CHECKPOINT_B_VALIDATION.md",
    "CHECKPOINT_C_VALIDATION.md",
    "CHECKPOINT_D_VALIDATION.md",
    "CHECKPOINT_E_VALIDATION.md",
    "docs/ARCHITECTURE.md",
    "docs/DEMO_RUNBOOK.md",
    "docs/DEPLOYMENT_READINESS.md",
    "docs/ENGINEERING_LOG.md",
    "docs/LICENSE_DECISION.md",
    "docs/PITCH_OUTLINE.md",
    "docs/REPRODUCIBILITY.md",
    "docs/SUBMISSION_EVIDENCE.md",
    "docs/THREAT_MODEL.md",
    "deploy/ecocommit.env.example",
    "deploy/nginx.conf.template",
    "deploy/proxy-policy.inc.template",
    "deploy/wsgi.py",
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
EVIDENCE_SLOTS = (
    "CHECKPOINT_A_FINAL_METRICS",
    "CHECKPOINT_B_RAZORPAY_TEST",
    "CHECKPOINT_C_FINAL_COMPARISON",
    "CHECKPOINT_D_FINAL_INTEGRATION",
    "FINAL_SCREENSHOTS",
    "FINAL_VIDEO",
)
EVIDENCE_MARKERS = tuple(
    f"EVIDENCE:{slot} status=BLOCKED" for slot in EVIDENCE_SLOTS
)
EVIDENCE_MARKER = re.compile(
    r"<!--\s*EVIDENCE:([A-Z0-9_]+)\s+status=(BLOCKED|FAILED|PASSED)\s*-->"
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
GITHUB_SCP_REMOTE = re.compile(
    r"^git@github\.com:(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+?)(?:\.git)?/?$",
    re.IGNORECASE,
)
GITHUB_ACTIONS_EVIDENCE_REFERENCE = re.compile(
    r"^github-actions://(?P<repository>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)/"
    r"runs/[0-9]{1,20}/artifacts/[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$"
)


@dataclass(frozen=True)
class Check:
    name: str
    passed: bool
    detail: str


def _utc(value: datetime, field_name: str) -> datetime:
    if value.utcoffset() != timedelta(0):
        raise ValueError(f"{field_name} must be expressed in UTC")
    return value


class IndependentReproductionReceipt(BaseModel):
    """Strict, self-digesting independent clean-machine reproduction receipt."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["E.REPRODUCTION.2"] = "E.REPRODUCTION.2"
    source_repository: Literal[EXPECTED_REMOTE_REPOSITORY] = EXPECTED_REMOTE_REPOSITORY
    source_revision: str = Field(pattern=r"^[0-9a-f]{40}$")
    source_tree_id: str = Field(pattern=r"^[0-9a-f]{40,64}$")
    dependency_lock_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    independent_machine: Literal[True] = True
    clean_checkout: Literal[True] = True
    upstream_exact: Literal[True] = True
    machine_identity_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    verifier_identity_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    platform_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    python_version: str = Field(pattern=r"^3\.(?:11|12|13|14)\.[0-9]+(?:[-+._A-Za-z0-9]*)?$")
    started_at_utc: datetime
    completed_at_utc: datetime
    collected_tests: int = Field(gt=0, strict=True)
    passed_tests: int = Field(ge=0, strict=True)
    failed_tests: int = Field(ge=0, strict=True)
    error_tests: int = Field(ge=0, strict=True)
    readiness_checks_collected: int = Field(gt=0, strict=True)
    readiness_checks_passed: int = Field(ge=0, strict=True)
    test_report_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    dependency_check_report_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    readiness_report_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    commands_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    artifact_bundle_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_reference: str = Field(min_length=1, max_length=512)
    network_provider_calls_made: Literal[False] = False
    fixture_outputs_promoted: Literal[False] = False
    receipt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("started_at_utc", "completed_at_utc")
    @classmethod
    def timestamps_are_utc(cls, value: datetime, info):
        return _utc(value, info.field_name)

    @field_validator("evidence_reference")
    @classmethod
    def evidence_reference_is_exact(cls, value: str):
        if any(character.isspace() or ord(character) < 33 for character in value):
            raise ValueError("reproduction evidence reference contains whitespace")
        match = GITHUB_ACTIONS_EVIDENCE_REFERENCE.fullmatch(value)
        if match is None:
            raise ValueError("reproduction evidence must use an exact GitHub Actions reference")
        if match.group("repository").casefold() != EXPECTED_REMOTE_REPOSITORY.casefold():
            raise ValueError("reproduction evidence belongs to another repository")
        return value

    @model_validator(mode="after")
    def complete_run_and_digest_are_valid(self):
        if self.completed_at_utc < self.started_at_utc:
            raise ValueError("reproduction completion predates its start")
        if (
            self.passed_tests != self.collected_tests
            or self.failed_tests != 0
            or self.error_tests != 0
        ):
            raise ValueError("independent full test counts are not a complete pass")
        if self.readiness_checks_passed != self.readiness_checks_collected:
            raise ValueError("independent readiness check counts are incomplete")
        if self.machine_identity_sha256 == self.verifier_identity_sha256:
            raise ValueError("machine and verifier identities must be independently bound")
        expected = sha256_hex(self.model_dump(exclude={"receipt_sha256"}))
        if self.receipt_sha256 != expected:
            raise ValueError("independent reproduction receipt digest is invalid")
        return self

    @classmethod
    def create(cls, **values) -> "IndependentReproductionReceipt":
        body = {
            "schema_version": "E.REPRODUCTION.2",
            "source_repository": EXPECTED_REMOTE_REPOSITORY,
            "independent_machine": True,
            "clean_checkout": True,
            "upstream_exact": True,
            "network_provider_calls_made": False,
            "fixture_outputs_promoted": False,
            **values,
        }
        return cls(**body, receipt_sha256=sha256_hex(body))


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


def _evidence_slot_statuses(text: str) -> tuple[dict[str, str], list[str]]:
    discovered: dict[str, list[str]] = {}
    for name, status in EVIDENCE_MARKER.findall(text):
        discovered.setdefault(name, []).append(status)
    problems: list[str] = []
    statuses: dict[str, str] = {}
    for slot in EVIDENCE_SLOTS:
        values = discovered.get(slot, [])
        if not values:
            problems.append(f"missing:{slot}")
        elif len(values) != 1:
            problems.append(f"duplicate:{slot}")
        else:
            statuses[slot] = values[0]
    unknown = sorted(set(discovered) - set(EVIDENCE_SLOTS))
    problems.extend(f"unknown:{name}" for name in unknown)
    return statuses, problems


def _independent_reproduction_status(
    path: Path | None,
    *,
    source_revision: str,
    source_tree_id: str,
    dependency_lock_sha256: str,
) -> tuple[bool, str]:
    if path is None:
        return False, "receipt=missing"
    if path.is_symlink():
        return False, "receipt=symlink_forbidden"
    try:
        raw = path.resolve().read_bytes()
        if not raw or len(raw) > MAX_REPRODUCTION_RECEIPT_BYTES:
            return False, "receipt=invalid_size"
        payload = strict_json_loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError):
        return False, "receipt=invalid_json"
    if not isinstance(payload, dict):
        return False, "receipt=object_required"
    try:
        receipt = IndependentReproductionReceipt.model_validate(payload)
    except ValueError:
        return False, "receipt=schema_or_digest_invalid"
    mismatches = []
    if receipt.source_revision != source_revision:
        mismatches.append("source_revision")
    if receipt.source_tree_id != source_tree_id:
        mismatches.append("source_tree_id")
    if receipt.dependency_lock_sha256 != dependency_lock_sha256:
        mismatches.append("dependency_lock_sha256")
    if mismatches:
        return False, f"mismatches={mismatches}"
    return True, f"receipt_sha256={receipt.receipt_sha256}"


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


def _public_github_repository(remote_url: str | None) -> str | None:
    """Return an owner/repository identity without retaining credentials or paths."""
    if not remote_url:
        return None
    scp_match = GITHUB_SCP_REMOTE.fullmatch(remote_url)
    if scp_match:
        return f"{scp_match.group('owner')}/{scp_match.group('repo')}"

    try:
        parsed = urlsplit(remote_url)
        parsed_port = parsed.port
    except ValueError:
        return None
    allowed_transport = (
        parsed.scheme == "https" and parsed.username is None and parsed.password is None
    ) or (
        parsed.scheme == "ssh"
        and parsed.username == "git"
        and parsed.password is None
    )
    if (
        not allowed_transport
        or parsed.hostname != "github.com"
        or parsed_port is not None
        or parsed.query
        or parsed.fragment
    ):
        return None
    parts = parsed.path.strip("/").split("/")
    if len(parts) != 2:
        return None
    owner, repository = parts
    if repository.lower().endswith(".git"):
        repository = repository[:-4]
    component = re.compile(r"^[A-Za-z0-9_.-]+$")
    if not owner or not repository or not component.fullmatch(owner) or not component.fullmatch(repository):
        return None
    return f"{owner}/{repository}"


def build_report(
    root: Path = REPOSITORY_ROOT,
    *,
    independent_reproduction: Path | None = None,
) -> dict[str, object]:
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
    evidence_statuses, evidence_problems = _evidence_slot_statuses(evidence)
    checks.append(Check(
        "evidence_slot_markers",
        not evidence_problems,
        f"problems={evidence_problems}",
    ))

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
    configured_remote = _git(root, "config", "--get", "remote.origin.url", check=False) or None
    remote_repository = _public_github_repository(configured_remote)
    expected_remote = remote_repository is not None and (
        remote_repository.casefold() == EXPECTED_REMOTE_REPOSITORY.casefold()
    )
    remote_url = (
        f"https://github.com/{EXPECTED_REMOTE_REPOSITORY}.git"
        if expected_remote
        else None
    )
    revision = _git(root, "rev-parse", "HEAD")
    source_tree_id = _git(root, "rev-parse", "HEAD^{tree}")
    dependency_lock_sha256 = sha256(
        (root / "requirements-dev.lock").read_bytes()
    ).hexdigest()
    license_present = any(path in tracked_set for path in ("LICENSE", "LICENSE.md", "LICENSE.txt"))

    blockers = [
        f"EVIDENCE:{slot} status={evidence_statuses.get(slot, 'MISSING')}"
        for slot in EVIDENCE_SLOTS
        if evidence_statuses.get(slot) != "PASSED"
    ]
    if not license_present:
        blockers.append("LICENSE_OWNER_DECISION_REQUIRED")
    if not configured_remote:
        blockers.append("REMOTE_ORIGIN_NOT_CONFIGURED")
    elif remote_repository is None:
        blockers.append("REMOTE_ORIGIN_NOT_PUBLIC_GITHUB")
    elif not expected_remote:
        blockers.append("REMOTE_REPOSITORY_MISMATCH")
    if not clean:
        blockers.append("WORKING_TREE_NOT_CLEAN")
    if ahead is None:
        blockers.append("UPSTREAM_STATE_UNAVAILABLE")
    elif ahead:
        blockers.append(f"LOCAL_COMMITS_NOT_PUSHED:{ahead}")
    if behind:
        blockers.append(f"LOCAL_BRANCH_BEHIND_UPSTREAM:{behind}")
    reproduction_passed, reproduction_detail = _independent_reproduction_status(
        independent_reproduction,
        source_revision=revision,
        source_tree_id=source_tree_id,
        dependency_lock_sha256=dependency_lock_sha256,
    )
    if not reproduction_passed:
        blockers.append("INDEPENDENT_CLEAN_MACHINE_REPRODUCTION_NOT_RETAINED")

    return {
        "schema_version": "E.READINESS.1",
        "source_revision": revision,
        "source_tree_id": source_tree_id,
        "dependency_lock_sha256": dependency_lock_sha256,
        "working_tree_clean": clean,
        "remote_url": remote_url,
        "remote_origin": {
            "configured": configured_remote is not None,
            "repository": remote_repository,
            "expected_repository": EXPECTED_REMOTE_REPOSITORY,
            "verified": expected_remote,
        },
        "upstream": {"behind": behind, "ahead": ahead},
        "license_present": license_present,
        "evidence_slot_statuses": evidence_statuses,
        "independent_reproduction": {
            "verified": reproduction_passed,
            "detail": reproduction_detail,
        },
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
    parser.add_argument("--independent-reproduction", type=Path)
    parser.add_argument("--mode", choices=("local", "final"), default="local")
    args = parser.parse_args()
    report = build_report(
        args.root,
        independent_reproduction=args.independent_reproduction,
    )
    report["evaluation_mode"] = args.mode
    encoded = json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    required_pass = (
        report["final_submission_ready"]
        if args.mode == "final"
        else report["local_repository_checks_pass"]
    )
    return 0 if required_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
