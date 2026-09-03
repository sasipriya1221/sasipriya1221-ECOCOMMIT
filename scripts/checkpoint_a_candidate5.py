"""One fresh Candidate 5 run; stop between cases on a proved frozen-gate failure."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from checkpoint_a_constants import CANDIDATE_VERSION, CRITERIA
from checkpoint_a_live import _ambiguous_cases, _clear_cases
from checkpoint_a_protocol import (
    ROOT, build_manifest, canonical_sha256, load_evidence_object, verify_manifest, verify_row,
)
from ecocommit.interpreter import OpenAICompatibleIntentProvider
from ecocommit.validator import FidelityValidator

NAMESPACE = "checkpoint-a-candidate-5"
CASE_WALL_TIMEOUT_SECONDS = 240
REGISTRATION = ROOT / "evidence/checkpoint-a-candidate-5-preregistration.json"


def candidate_provider(api_key: str) -> OpenAICompatibleIntentProvider:
    return OpenAICompatibleIntentProvider(
        "https://api.groq.com/openai/v1", api_key, "qwen/qwen3.6-27b",
        reasoning_effort="none", use_json_schema=False, max_completion_tokens=2048,
        max_attempts=3, max_schema_corrections=2, max_retry_delay=15, timeout=60,
    )


def stable_manifest(manifest: dict) -> dict:
    return {k: v for k, v in manifest.items() if k not in {"source_revision", "workflow", "manifest_sha256"}}


def verify_registration(manifest: dict, registration_path: Path = REGISTRATION) -> dict:
    registration = load_evidence_object(registration_path)
    unsigned = {k: v for k, v in registration.items() if k != "preregistration_sha256"}
    if registration.get("preregistration_sha256") != canonical_sha256(unsigned):
        raise ValueError("Candidate 5 preregistration digest mismatch")
    frozen = registration["frozen_manifest"]
    if manifest.get("candidate_version") != CANDIDATE_VERSION or stable_manifest(manifest) != stable_manifest(frozen):
        raise ValueError("Candidate 5 preregistration configuration/source hashes mismatch")
    if frozen.get("manifest_sha256") != canonical_sha256({k: v for k, v in frozen.items() if k != "manifest_sha256"}):
        raise ValueError("Candidate 5 frozen manifest digest mismatch")
    if registration.get("artifact_namespace") != NAMESPACE:
        raise ValueError("Candidate 5 namespace mismatch")
    return registration


def verify_health(receipt: dict, manifest: dict) -> None:
    unsigned = {k: v for k, v in receipt.items() if k != "receipt_sha256"}
    if receipt.get("receipt_sha256") != canonical_sha256(unsigned):
        raise ValueError("Candidate 5 health receipt digest mismatch")
    if (
        receipt.get("candidate_id") != CANDIDATE_VERSION
        or receipt.get("candidate_source_sha") != manifest["source_revision"]
        or receipt.get("provider") != manifest["provider"]
        or receipt.get("runner_sha256") != manifest["runner_sha256"]
        or receipt.get("preregistration_sha256") != verify_registration(manifest)["preregistration_sha256"]
        or receipt.get("observation", {}).get("healthy") is not True
        or receipt.get("github", {}).get("run_attempt") != "1"
    ):
        raise ValueError("Candidate 5 requires a passing exact-source provider preflight")


def impossible_thresholds(frozen: list, by_id: dict[str, dict]) -> dict:
    """Optimistic upper bounds only, never partial-run scores or passing evidence."""
    missing = [g for g in frozen if g.case_id not in by_id]
    rows = list(by_id.values())
    validated = [r for r in rows if (r.get("detail") or {}).get("validator_status") == "VALIDATED"]
    correct = sum(r.get("passed") is True for r in validated)
    clarified = sum(
        (by_id.get(g.case_id, {}).get("detail") or {}).get("validator_status") == "CLARIFICATION_REQUIRED"
        for g in frozen if g.expected_status.value == "CLARIFICATION_REQUIRED"
    )
    remaining_ambiguous = sum(g.expected_status.value == "CLARIFICATION_REQUIRED" for g in missing)
    possible_validated = len(validated) + len(missing)
    bounds = {
        "case_pass_rate_min": (sum(r.get("passed") is True for r in rows) + len(missing)) / 80,
        "autonomous_coverage_min": possible_validated / 80,
        "selective_semantic_reliability_min": (correct + len(missing)) / possible_validated if possible_validated else 0.0,
        "ambiguous_clarification_accuracy_min": (clarified + remaining_ambiguous) / 30,
    }
    return {k: {"optimistic_upper_bound": v, "frozen_minimum": CRITERIA[k]} for k, v in bounds.items() if v < CRITERIA[k]}


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify-offline", action="store_true")
    parser.add_argument("--output-dir")
    parser.add_argument("--health-receipt")
    args = parser.parse_args()
    frozen = _clear_cases() + _ambiguous_cases()
    manifest = build_manifest(frozen, candidate_provider("offline-manifest-only"))
    registration = verify_registration(manifest)
    if args.verify_offline:
        print("CANDIDATE_5_OFFLINE_PREFLIGHT_OK", registration["preregistration_sha256"])
        return 0
    if os.getenv("GITHUB_RUN_ATTEMPT") != "1":
        raise ValueError("Candidate 5 is one-shot: workflow reruns are forbidden")
    if not args.output_dir or not args.health_receipt or not os.getenv("ECOCOMMIT_LLM_API_KEY"):
        raise ValueError("fresh output directory, exact-source health receipt and provider secret required")
    health = load_evidence_object(Path(args.health_receipt))
    verify_health(health, manifest)
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=False)
    case_dir = out / "cases"
    case_dir.mkdir()
    write_json(out / "manifest.json", manifest)
    write_json(out / "preregistration.json", registration)
    write_json(out / "provider-health.json", health)
    by_id = {}
    eliminated = {}
    infrastructure = []
    validator = FidelityValidator()
    for index, gold in enumerate(frozen):
        case_path = case_dir / f"case-{index}-attempt-1.json"
        try:
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts/checkpoint_a_shard.py"),
                 "--start", str(index), "--end", str(index + 1), "--output", str(case_path.resolve())],
                cwd=ROOT, capture_output=True, text=True, timeout=CASE_WALL_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            infrastructure.append({"case_id": gold.case_id, "kind": "CASE_WALL_TIMEOUT", "seconds": CASE_WALL_TIMEOUT_SECONDS})
            break
        (out / f"case-{index}.log").write_text(result.stdout + result.stderr, encoding="utf-8")
        if case_path.exists():
            payload = load_evidence_object(case_path)
            verify_manifest(payload["manifest"], manifest)
            for row in payload["cases"]:
                if row.get("id") != gold.case_id:
                    raise ValueError("unexpected case identity")
                by_id[gold.case_id] = verify_row(row, gold, manifest, validator)
            if payload.get("infrastructure_error"):
                infrastructure.append(payload["infrastructure_error"])
        if result.returncode not in {0, 75}:
            infrastructure.append({"case_id": gold.case_id, "kind": "CASE_PROCESS_FAILED", "exit_code": result.returncode})
            break
        eliminated = impossible_thresholds(frozen, by_id)
        if eliminated:
            break
        print(f"Completed scheduled case {index + 1}/80", flush=True)
    aggregate_path = out / "checkpoint_a_candidate_5_results_attempt_1.json"
    receipt_path = out / "checkpoint_a_candidate_5_receipt_attempt_1.json"
    evidence_ref = (
        f"github-actions://{os.environ['GITHUB_REPOSITORY']}/runs/{os.environ['GITHUB_RUN_ID']}"
        f"/attempts/1/{NAMESPACE}-results-attempt-1"
    )
    aggregate = subprocess.run(
        [sys.executable, str(ROOT / "scripts/checkpoint_a_aggregate.py"),
         "--input-dir", str(case_dir.resolve()), "--output", str(aggregate_path.resolve()),
         "--receipt-output", str(receipt_path.resolve()), "--evidence-reference", evidence_ref],
        cwd=ROOT, capture_output=True, text=True, timeout=60,
    )
    (out / "aggregate.log").write_text(aggregate.stdout + aggregate.stderr, encoding="utf-8")
    status = "PASSED" if aggregate.returncode == 0 else "FAILED" if eliminated else "INCOMPLETE"
    decision = {
        "schema_version": "A.CANDIDATE5.DECISION.1", "candidate_version": CANDIDATE_VERSION,
        "source_revision": manifest["source_revision"], "manifest_sha256": manifest["manifest_sha256"],
        "status": status, "terminal_case_count": len(by_id), "mathematical_elimination": eliminated,
        "infrastructure_deferrals": infrastructure, "aggregate_exit_code": aggregate.returncode,
        "typed_a_receipt_present": receipt_path.exists(), "score_recovery_retries": 0,
    }
    decision["decision_sha256"] = canonical_sha256(decision)
    write_json(out / "decision.json", decision)
    print("CANDIDATE_5", status, "DECISION_SHA256", decision["decision_sha256"])
    return 0 if status == "PASSED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
