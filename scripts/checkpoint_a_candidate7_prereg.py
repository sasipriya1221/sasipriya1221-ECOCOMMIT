"""Build/verify Candidate-7 official-A preregistration after a real qualification PASS.

This module is safe to exercise with fixtures in tests. It never calls a provider
and never treats a readiness template as a final preregistration.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_ID = "A-CANDIDATE-7"
FROZEN_SOURCE = "12d121f80a6cacd94376c6d2b7bce7dff5212eb5"
ARTIFACT_NAMESPACE = "checkpoint-a-candidate-7"
FROZEN_DATASET_SHA256 = "968be3ed3a438a3a28a3402fa65c90a45cb564ed1adad2e6e51d852e24c5bb8b"
CRITERIA = {
    "case_pass_rate_min": 0.90,
    "selective_semantic_reliability_min": 0.95,
    "autonomous_coverage_min": 0.55,
    "ambiguous_clarification_accuracy_min": 0.80,
}


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_head(path: Path) -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=path, text=True).strip()


def verify_qualification(binding: dict[str, Any], summary: dict[str, Any]) -> str:
    if not (
        binding.get("candidate") == CANDIDATE_ID
        and binding.get("candidate_sha") == FROZEN_SOURCE
        and binding.get("qualification_mode") == "candidate7-d003-d009"
        and binding.get("qualification_harness") == "scripts/candidate7_pass2_qualification.py"
        and binding.get("official_checkpoint_a_cases_used") is False
        and binding.get("holdout_opened") is False
    ):
        raise ValueError("Candidate-7 qualification source/protocol binding mismatch")
    unsigned = {k: v for k, v in binding.items() if k != "binding_sha256"}
    if binding.get("binding_sha256") != canonical_sha256(unsigned):
        raise ValueError("Candidate-7 qualification binding digest mismatch")
    cases = summary.get("cases") or {}
    if not (
        summary.get("qualification_status") == "PASS"
        and summary.get("provider_calls_recorded") == 10
        and summary.get("stopped_after_first_http_429") is False
        and all((cases.get(case) or {}).get("accepted") == 5 for case in ("D003", "D009"))
        and all((cases.get(case) or {}).get("correct_results") == 5 for case in ("D003", "D009"))
        and all((cases.get(case) or {}).get("old_failure_signature_matches") == 0 for case in ("D003", "D009"))
    ):
        raise ValueError("Candidate-7 qualification PASS evidence required")
    return canonical_sha256({"source_binding": binding, "summary": summary})


def _dataset_and_evaluator(candidate_root: Path) -> tuple[str, dict[str, str]]:
    scripts = str((ROOT / "scripts").resolve())
    source = str((candidate_root / "src").resolve())
    sys.path[:0] = [source, scripts]
    from checkpoint_a_live import _ambiguous_cases, _clear_cases  # type: ignore
    from checkpoint_a_protocol import dataset_sha256  # type: ignore
    frozen = _clear_cases() + _ambiguous_cases()
    digest = dataset_sha256(frozen)
    if len(frozen) != 80 or digest != FROZEN_DATASET_SHA256:
        raise ValueError("frozen Checkpoint-A dataset changed")
    files = {
        "scripts/checkpoint_a_live.py": ROOT / "scripts/checkpoint_a_live.py",
        "src/ecocommit/contracts.py": candidate_root / "src/ecocommit/contracts.py",
        "src/ecocommit/validator.py": candidate_root / "src/ecocommit/validator.py",
    }
    for rel in ("src/ecocommit/contracts.py", "src/ecocommit/validator.py"):
        if file_sha256(candidate_root / rel) != file_sha256(ROOT / rel):
            raise ValueError(f"frozen evaluator dependency mismatch: {rel}")
    return digest, {name: file_sha256(path) for name, path in sorted(files.items())}


def build_preregistration(candidate_root: Path, binding: dict[str, Any], summary: dict[str, Any], *, qualification_artifact: str, qualification_archive_sha256: str) -> dict[str, Any]:
    if git_head(candidate_root) != FROZEN_SOURCE:
        raise ValueError("Candidate-7 checkout is not the frozen source")
    qualification_digest = verify_qualification(binding, summary)
    if not qualification_artifact.startswith("github-actions://") or len(qualification_archive_sha256) != 64:
        raise ValueError("retained qualification artifact binding required")
    dataset, evaluator_files = _dataset_and_evaluator(candidate_root)
    components = {
        name: file_sha256(candidate_root / name)
        for name in (
            "src/ecocommit/candidate7_provider.py", "src/ecocommit/candidate7_flat.py",
            "src/ecocommit/candidate7_relation_checklist.py", "src/ecocommit/candidate7_structure.py",
            "src/ecocommit/candidate7_compile.py", "src/ecocommit/candidate7_conservation.py",
            "src/ecocommit/candidate7.py",
        )
    }
    provider = {
        "base_url": "https://api.groq.com/openai/v1", "model": "qwen/qwen3.6-27b",
        "reasoning_effort": "none", "temperature": 0, "max_completion_tokens": 1536,
        "max_attempts_per_pass": 2, "semantic_score_retry_permitted": False,
    }
    value = {
        "schema_version": "A.CANDIDATE7.PREREGISTRATION.1", "candidate": CANDIDATE_ID,
        "frozen_semantic_source_revision": FROZEN_SOURCE, "artifact_namespace": ARTIFACT_NAMESPACE,
        "qualification": {"status": "PASS", "evidence_sha256": qualification_digest, "artifact": qualification_artifact, "archive_sha256": qualification_archive_sha256},
        "frozen_dataset": {"count": 80, "sha256": dataset},
        "frozen_evaluator_files": evaluator_files, "frozen_evaluator_sha256": canonical_sha256(evaluator_files),
        "criteria": CRITERIA, "criteria_sha256": canonical_sha256(CRITERIA),
        "candidate_components": components, "candidate_components_sha256": canonical_sha256(components),
        "provider_policy": provider, "provider_policy_sha256": canonical_sha256(provider),
        "early_stop_policy": {"implementation": "class-aware exact optimistic joint reachability", "check_before_next_provider_call": True},
        "one_shot_policy": {"official_run_attempt": 1, "rerun_permitted": False, "resume_to_pass_permitted": False, "semantic_score_retry_permitted": False},
    }
    value["preregistration_sha256"] = canonical_sha256(value)
    return value
