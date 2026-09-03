"""One frozen Candidate-6 Checkpoint-A run with exact class-aware early stopping."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
NAMESPACE = "checkpoint-a-candidate-6"
CANDIDATE_ID = "A-CANDIDATE-6"
TOTAL_CASES = 80
CLEAR_CASES = 50
AMBIGUOUS_CASES = 30


def canonical_sha256(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _candidate_head(candidate_root: Path) -> str:
    value = subprocess.run(["git", "rev-parse", "HEAD"], cwd=candidate_root, check=True, capture_output=True, text=True).stdout.strip()
    if not re.fullmatch(r"[0-9a-f]{40}", value):
        raise ValueError("Candidate-6 checkout must be an exact commit")
    return value


def _load_runtime(candidate_root: Path):
    candidate_src = str((candidate_root / "src").resolve())
    scripts = str((ROOT / "scripts").resolve())
    if candidate_src not in sys.path:
        sys.path.insert(0, candidate_src)
    if scripts not in sys.path:
        sys.path.insert(1, scripts)

    from checkpoint_a_candidate6_prereg import load_object, verify_preregistration  # type: ignore
    from checkpoint_a_constants import CRITERIA, FROZEN_DATASET_SHA256  # type: ignore
    from checkpoint_a_live import _ambiguous_cases, _clear_cases, semantic_case_pass  # type: ignore
    from checkpoint_a_protocol import dataset_sha256, frozen_case_payload  # type: ignore
    from candidate6_official_reachability import OfficialCounts, OfficialThresholds, final_pass, reachable  # type: ignore
    from ecocommit.candidate6_provider import GroqSemanticIRProvider, SemanticIRSchemaError  # type: ignore
    from ecocommit.interpreter import ProviderRequestError  # type: ignore
    from ecocommit.semantic_compiler import ConservationError, compile_contract  # type: ignore
    from ecocommit.semantic_validation import SemanticValidationError  # type: ignore
    from ecocommit.validator import FidelityValidator  # type: ignore

    return {
        "load_object": load_object,
        "verify_preregistration": verify_preregistration,
        "CRITERIA": CRITERIA,
        "FROZEN_DATASET_SHA256": FROZEN_DATASET_SHA256,
        "clear": _clear_cases,
        "ambiguous": _ambiguous_cases,
        "semantic_case_pass": semantic_case_pass,
        "dataset_sha256": dataset_sha256,
        "frozen_case_payload": frozen_case_payload,
        "OfficialCounts": OfficialCounts,
        "OfficialThresholds": OfficialThresholds,
        "final_pass": final_pass,
        "reachable": reachable,
        "Provider": GroqSemanticIRProvider,
        "SchemaError": SemanticIRSchemaError,
        "ProviderError": ProviderRequestError,
        "ConservationError": ConservationError,
        "compile_contract": compile_contract,
        "SemanticValidationError": SemanticValidationError,
        "Validator": FidelityValidator,
    }


def _verify_health(health: dict[str, Any], prereg: dict[str, Any], candidate_head: str) -> None:
    unsigned = {k: v for k, v in health.items() if k != "receipt_sha256"}
    if health.get("receipt_sha256") != canonical_sha256(unsigned):
        raise ValueError("Candidate-6 provider readiness receipt digest mismatch")
    if not (
        health.get("schema_version") == "A.CANDIDATE6.PROVIDER.READINESS.1"
        and health.get("candidate") == CANDIDATE_ID
        and health.get("candidate_evidence_revision") == candidate_head
        and health.get("preregistration_sha256") == prereg.get("preregistration_sha256")
        and health.get("healthy") is True
        and health.get("benchmark_cases_used") == 0
    ):
        raise ValueError("passing exact-source Candidate-6 provider readiness receipt required")


def _safe_case_row(gold, provider, validator, runtime, prereg: dict[str, Any]) -> dict[str, Any]:
    trace: list[dict[str, Any]] = []
    contract = None
    semantic_ir = None
    candidate_status = "REJECTED"
    error_kind = None
    error_code = None
    detail = None
    passed = False
    blocked_actions: list[str] = []
    try:
        parsed = provider.parse_with_metadata(gold.instruction)
        trace = list(parsed.provider_trace)
        semantic_ir = parsed.semantic_ir
        contract, _, blocked = runtime["compile_contract"](semantic_ir, gold.instruction)
        blocked_actions = sorted(blocked)
        candidate_status = "CLARIFICATION_REQUIRED" if blocked else "COMPILED"
        passed, detail = runtime["semantic_case_pass"](contract, gold, validator)
    except runtime["SchemaError"] as exc:
        trace = list(exc.provider_trace)
        error_kind = "semantic_ir_schema_error"
        error_code = "IR_SCHEMA_INVALID_AFTER_BOUNDED_CORRECTION"
    except runtime["ProviderError"] as exc:
        trace = list(exc.provider_trace)
        error_kind = "provider_deferred" if exc.transient else "provider_error"
        error_code = exc.code
    except (runtime["SemanticValidationError"], runtime["ConservationError"], ValueError) as exc:
        error_kind = "deterministic_candidate_rejection"
        error_code = str(exc)[:200]
    except Exception as exc:  # evidence-safe fail closed; no raw secret/provider body
        error_kind = "internal_error"
        error_code = type(exc).__name__

    row: dict[str, Any] = {
        "id": gold.case_id,
        "instruction": gold.instruction,
        "candidate_status": candidate_status,
        "blocked_actions": blocked_actions,
        "passed": bool(passed),
        "detail": detail,
        "error_kind": error_kind,
        "error_code": error_code,
        "provider_trace": trace,
        "semantic_ir": semantic_ir.model_dump(mode="json") if semantic_ir is not None else None,
        "contract": contract.model_dump(mode="json") if contract is not None else None,
        "preregistration_sha256": prereg["preregistration_sha256"],
        "case_sha256": canonical_sha256(runtime["frozen_case_payload"](gold)),
    }
    if row["contract"] is not None:
        row["contract_sha256"] = canonical_sha256(row["contract"])
    row["row_sha256"] = canonical_sha256(row)
    return row


def _counts_from_rows(rows: list[dict[str, Any]], frozen: list[Any], runtime) -> Any:
    by_id = {row["id"]: row for row in rows}
    clear_processed = 0
    ambiguous_processed = 0
    case_passes = 0
    autonomous = 0
    correct_autonomous = 0
    ambiguous_correct = 0
    for gold in frozen:
        row = by_id.get(gold.case_id)
        if row is None:
            continue
        if gold.case_id.startswith("C"):
            clear_processed += 1
        else:
            ambiguous_processed += 1
        if row.get("passed") is True:
            case_passes += 1
        detail = row.get("detail") or {}
        status = detail.get("validator_status")
        if status == "VALIDATED":
            autonomous += 1
            if row.get("passed") is True:
                correct_autonomous += 1
        if gold.case_id.startswith("A") and status == "CLARIFICATION_REQUIRED":
            ambiguous_correct += 1

    return runtime["OfficialCounts"](
        total=TOTAL_CASES,
        clear_total=CLEAR_CASES,
        ambiguous_total=AMBIGUOUS_CASES,
        processed=len(rows),
        clear_processed=clear_processed,
        ambiguous_processed=ambiguous_processed,
        case_passes=case_passes,
        autonomous=autonomous,
        correct_autonomous=correct_autonomous,
        ambiguous_correct=ambiguous_correct,
    )


def _metrics(counts) -> dict[str, float]:
    return {
        "case_pass_rate": counts.case_passes / TOTAL_CASES,
        "selective_semantic_reliability": counts.correct_autonomous / counts.autonomous if counts.autonomous else 0.0,
        "autonomous_coverage": counts.autonomous / TOTAL_CASES,
        "ambiguous_clarification_accuracy": counts.ambiguous_correct / AMBIGUOUS_CASES,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-root", type=Path, required=True)
    parser.add_argument("--preregistration", type=Path, required=True)
    parser.add_argument("--provider-readiness", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--verify-offline", action="store_true")
    args = parser.parse_args()

    candidate_root = args.candidate_root.resolve()
    runtime = _load_runtime(candidate_root)
    prereg = runtime["load_object"](args.preregistration.resolve())
    runtime["verify_preregistration"](candidate_root, prereg)

    frozen = runtime["clear"]() + runtime["ambiguous"]()
    if len(frozen) != TOTAL_CASES or runtime["dataset_sha256"](frozen) != runtime["FROZEN_DATASET_SHA256"]:
        raise ValueError("historical frozen Checkpoint-A dataset changed")
    if dict(runtime["CRITERIA"]) != prereg["criteria"]:
        raise ValueError("official thresholds differ from preregistration")

    if args.verify_offline:
        print("CANDIDATE6_OFFICIAL_OFFLINE_VERIFICATION_OK", prereg["preregistration_sha256"])
        return 0

    if os.getenv("GITHUB_RUN_ATTEMPT", "") != "1":
        raise ValueError("Candidate-6 official Checkpoint-A workflow is one-shot; reruns are forbidden")
    if not args.output_dir or not args.provider_readiness:
        raise ValueError("output directory and exact provider readiness receipt are required")
    api_key = os.getenv("ECOCOMMIT_LLM_API_KEY", "").strip()
    if not api_key:
        raise ValueError("ECOCOMMIT_LLM_API_KEY is required")

    candidate_head = _candidate_head(candidate_root)
    health = runtime["load_object"](args.provider_readiness.resolve())
    _verify_health(health, prereg, candidate_head)

    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    case_dir = out / "cases"
    case_dir.mkdir()
    _write_json(out / "preregistration.json", prereg)
    _write_json(out / "provider-readiness.json", health)

    provider = runtime["Provider"](api_key)
    validator = runtime["Validator"]()
    thresholds = runtime["OfficialThresholds"]()
    rows: list[dict[str, Any]] = []
    eliminated_after = None

    for index, gold in enumerate(frozen):
        row = _safe_case_row(gold, provider, validator, runtime, prereg)
        rows.append(row)
        _write_json(case_dir / f"case-{index:02d}-{gold.case_id}.json", row)

        counts = _counts_from_rows(rows, frozen, runtime)
        if not runtime["reachable"](counts, thresholds):
            eliminated_after = gold.case_id
            break
        print(f"Completed official scheduled case {index + 1}/{TOTAL_CASES}", flush=True)

    counts = _counts_from_rows(rows, frozen, runtime)
    metrics = _metrics(counts)
    complete = counts.processed == TOTAL_CASES
    passed = complete and runtime["final_pass"](counts, thresholds)
    status = "PASS" if passed else "FAILED"
    decision = {
        "schema_version": "A.CANDIDATE6.DECISION.1",
        "candidate": CANDIDATE_ID,
        "status": status,
        "candidate_evidence_revision": candidate_head,
        "frozen_semantic_source_revision": prereg["frozen_semantic_source_revision"],
        "preregistration_sha256": prereg["preregistration_sha256"],
        "provider_readiness_receipt_sha256": health["receipt_sha256"],
        "terminal_case_count": counts.processed,
        "full_frozen_run_completed": complete,
        "mathematically_eliminated_after_case": eliminated_after,
        "metrics": metrics,
        "counts": {
            "processed": counts.processed,
            "clear_processed": counts.clear_processed,
            "ambiguous_processed": counts.ambiguous_processed,
            "case_passes": counts.case_passes,
            "autonomous": counts.autonomous,
            "correct_autonomous": counts.correct_autonomous,
            "ambiguous_correct": counts.ambiguous_correct,
        },
        "criteria": dict(runtime["CRITERIA"]),
        "official_rerun_permitted": False,
        "resume_to_pass_permitted": False,
        "score_recovery_retries": 0,
    }
    decision["decision_sha256"] = canonical_sha256(decision)
    _write_json(out / "decision.json", decision)

    aggregate = {
        "schema_version": "A.CANDIDATE6.AGGREGATE.1",
        "candidate": CANDIDATE_ID,
        "status": status,
        "metrics": metrics,
        "processed": counts.processed,
        "total": TOTAL_CASES,
        "mathematical_early_stop": eliminated_after is not None,
        "decision_sha256": decision["decision_sha256"],
        "row_sha256": [row["row_sha256"] for row in rows],
    }
    aggregate["aggregate_sha256"] = canonical_sha256(aggregate)
    _write_json(out / "aggregate.json", aggregate)

    if passed:
        receipt = {
            "schema_version": "A.RECEIPT.CANDIDATE6.1",
            "stage": "checkpoint_a",
            "candidate": CANDIDATE_ID,
            "status": "PASS",
            "frozen_semantic_source_revision": prereg["frozen_semantic_source_revision"],
            "candidate_evidence_revision": candidate_head,
            "preregistration_sha256": prereg["preregistration_sha256"],
            "provider_readiness_receipt_sha256": health["receipt_sha256"],
            "official_decision_sha256": decision["decision_sha256"],
            "official_aggregate_sha256": aggregate["aggregate_sha256"],
            "metrics": metrics,
            "criteria": dict(runtime["CRITERIA"]),
            "official_run_attempt": 1,
            "official_rerun_permitted": False,
        }
        receipt["receipt_sha256"] = canonical_sha256(receipt)
        _write_json(out / "checkpoint-a-pass-receipt.json", receipt)

    print("CANDIDATE6_OFFICIAL_A", status, "DECISION_SHA256", decision["decision_sha256"])
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
