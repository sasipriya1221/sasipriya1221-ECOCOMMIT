from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_ID = "A-CANDIDATE-6"
ARTIFACT_NAMESPACE = "checkpoint-a-candidate-6"
SCHEMA_VERSION = "A.CANDIDATE6.PREREGISTRATION.1"
FROZEN_DATASET_SHA256 = "968be3ed3a438a3a28a3402fa65c90a45cb564ed1adad2e6e51d852e24c5bb8b"
CRITERIA = {
    "case_pass_rate_min": 0.90,
    "selective_semantic_reliability_min": 0.95,
    "autonomous_coverage_min": 0.55,
    "ambiguous_clarification_accuracy_min": 0.80,
}


def canonical_sha256(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_object(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    if not raw or len(raw) > 8 * 1024 * 1024:
        raise ValueError(f"invalid evidence size: {path}")
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"evidence must be an object: {path}")
    return value


def git_head(path: Path) -> str:
    result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=path, check=True, capture_output=True, text=True)
    head = result.stdout.strip()
    if len(head) != 40 or any(ch not in "0123456789abcdef" for ch in head):
        raise ValueError("candidate checkout does not have an exact commit SHA")
    return head


def _import_candidate(candidate_root: Path):
    source = str((candidate_root / "src").resolve())
    if source not in sys.path:
        sys.path.insert(0, source)
    from ecocommit.candidate6 import PROVIDER_POLICY  # type: ignore
    from ecocommit.candidate6_freeze import verify_freeze_receipt  # type: ignore
    return PROVIDER_POLICY, verify_freeze_receipt


def _import_frozen_dataset_tools():
    scripts = str((ROOT / "scripts").resolve())
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    from checkpoint_a_live import _ambiguous_cases, _clear_cases  # type: ignore
    from checkpoint_a_protocol import dataset_sha256  # type: ignore
    return _clear_cases, _ambiguous_cases, dataset_sha256


def evaluator_bindings(candidate_root: Path) -> dict[str, str]:
    paths = {
        "scripts/checkpoint_a_live.py": ROOT / "scripts/checkpoint_a_live.py",
        "src/ecocommit/contracts.py": candidate_root / "src/ecocommit/contracts.py",
        "src/ecocommit/validator.py": candidate_root / "src/ecocommit/validator.py",
    }
    # The historical evaluator imports the candidate checkout's contract/validator
    # modules at runtime. Require those to equal the public main copies byte-for-byte.
    for rel in ("src/ecocommit/contracts.py", "src/ecocommit/validator.py"):
        if file_sha256(candidate_root / rel) != file_sha256(ROOT / rel):
            raise ValueError(f"frozen evaluator dependency differs between candidate and main: {rel}")
    return {name: file_sha256(path) for name, path in sorted(paths.items())}


def validate_internal_evidence(candidate_root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    _, verify_freeze_receipt = _import_candidate(candidate_root)
    freeze_path = candidate_root / "evidence/candidate6-freeze-receipt.json"
    internal_path = candidate_root / "evidence/candidate6-internal-qualification-receipt.json"
    freeze = load_object(freeze_path)
    internal = load_object(internal_path)
    verify_freeze_receipt(candidate_root, freeze)

    unsigned_internal = {k: v for k, v in internal.items() if k != "receipt_sha256"}
    if internal.get("receipt_sha256") != canonical_sha256(unsigned_internal):
        raise ValueError("Candidate-6 internal qualification receipt digest mismatch")
    if not (
        internal.get("schema_version") == "C6.INTERNAL.RECEIPT.1"
        and internal.get("stage") == "holdout"
        and internal.get("candidate") == CANDIDATE_ID
        and internal.get("status") == "PASS"
        and internal.get("passed") is True
        and internal.get("official_checkpoint_a_eligibility") == "ELIGIBLE"
        and internal.get("holdout_rerun_permitted") is False
        and internal.get("post_holdout_semantic_modification_permitted") is False
    ):
        raise ValueError("Candidate-6 internal PASS receipt is required")
    return freeze, internal


def build_preregistration(candidate_root: Path) -> dict[str, Any]:
    provider_policy, _ = _import_candidate(candidate_root)
    clear_fn, ambiguous_fn, dataset_hash_fn = _import_frozen_dataset_tools()
    frozen = clear_fn() + ambiguous_fn()
    dataset_hash = dataset_hash_fn(frozen)
    if len(frozen) != 80 or dataset_hash != FROZEN_DATASET_SHA256:
        raise ValueError("historical frozen Checkpoint-A dataset changed")

    freeze, internal = validate_internal_evidence(candidate_root)
    frozen_source = freeze.get("candidate_source_revision")
    if not isinstance(frozen_source, str) or len(frozen_source) != 40:
        raise ValueError("freeze receipt lacks exact semantic source revision")

    evaluator = evaluator_bindings(candidate_root)
    runner_files = {
        "scripts/checkpoint_a_candidate6.py": ROOT / "scripts/checkpoint_a_candidate6.py",
        "scripts/checkpoint_a_candidate6_prereg.py": ROOT / "scripts/checkpoint_a_candidate6_prereg.py",
        "scripts/candidate6_official_reachability.py": ROOT / "scripts/candidate6_official_reachability.py",
        ".github/workflows/checkpoint-a-candidate6.yml": ROOT / ".github/workflows/checkpoint-a-candidate6.yml",
        ".github/workflows/candidate6-official-prereg.yml": ROOT / ".github/workflows/candidate6-official-prereg.yml",
        ".github/workflows/candidate6-provider-readiness.yml": ROOT / ".github/workflows/candidate6-provider-readiness.yml",
    }
    missing = [name for name, path in runner_files.items() if not path.exists()]
    if missing:
        raise ValueError(f"Candidate-6 official runner files missing: {missing}")

    prereg = {
        "schema_version": SCHEMA_VERSION,
        "candidate": CANDIDATE_ID,
        "artifact_namespace": ARTIFACT_NAMESPACE,
        "candidate_evidence_revision_before_preregistration": git_head(candidate_root),
        "frozen_semantic_source_revision": frozen_source,
        "freeze_receipt_sha256": freeze["freeze_receipt_sha256"],
        "internal_qualification_receipt_sha256": internal["receipt_sha256"],
        "historical_frozen_dataset": {"count": 80, "sha256": dataset_hash},
        "historical_frozen_evaluator_files": evaluator,
        "historical_frozen_evaluator_sha256": canonical_sha256(evaluator),
        "criteria": dict(CRITERIA),
        "criteria_sha256": canonical_sha256(CRITERIA),
        "provider_policy": provider_policy,
        "provider_policy_sha256": canonical_sha256(provider_policy),
        "provider_implementation_sha256": file_sha256(candidate_root / "src/ecocommit/candidate6_provider.py"),
        "semantic_parser_sha256": file_sha256(candidate_root / "src/ecocommit/candidate6.py"),
        "semantic_ir_schema_implementation_sha256": file_sha256(candidate_root / "src/ecocommit/semantic_ir.py"),
        "official_runner_files": {name: file_sha256(path) for name, path in sorted(runner_files.items())},
        "official_runner_sha256": canonical_sha256({name: file_sha256(path) for name, path in sorted(runner_files.items())}),
        "early_stop_policy": {
            "implementation": "class-aware exact optimistic joint reachability",
            "check_after_every_terminal_case_before_next_provider_call": True,
            "module_sha256": file_sha256(ROOT / "scripts/candidate6_official_reachability.py"),
        },
        "one_shot_policy": {
            "official_run_attempt": 1,
            "rerun_permitted": False,
            "resume_to_pass_permitted": False,
            "semantic_score_retry_permitted": False,
            "post_result_candidate_semantic_change_permitted": False,
            "dataset_change_permitted": False,
            "evaluator_change_permitted": False,
            "threshold_change_permitted": False,
        },
    }
    prereg["preregistration_sha256"] = canonical_sha256(prereg)
    return prereg


def verify_preregistration(candidate_root: Path, prereg: dict[str, Any]) -> None:
    unsigned = {k: v for k, v in prereg.items() if k != "preregistration_sha256"}
    if prereg.get("preregistration_sha256") != canonical_sha256(unsigned):
        raise ValueError("Candidate-6 official preregistration digest mismatch")
    expected = build_preregistration(candidate_root)
    # The candidate evidence branch advances by exactly the preregistration commit,
    # so its pre-registration revision is intentionally not recomputed after commit.
    stable_keys = set(expected) - {"candidate_evidence_revision_before_preregistration", "preregistration_sha256"}
    for key in stable_keys:
        if prereg.get(key) != expected.get(key):
            raise ValueError(f"Candidate-6 official preregistration binding mismatch: {key}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify", type=Path)
    args = parser.parse_args()
    candidate_root = args.candidate_root.resolve()
    if args.verify:
        verify_preregistration(candidate_root, load_object(args.verify.resolve()))
        print("CANDIDATE6_OFFICIAL_PREREGISTRATION_OK")
        return 0
    if not args.output:
        raise SystemExit("--output is required when not verifying")
    prereg = build_preregistration(candidate_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(prereg, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("CANDIDATE6_OFFICIAL_PREREGISTRATION", prereg["preregistration_sha256"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
