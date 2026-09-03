from __future__ import annotations

import argparse
import json
from hashlib import sha256
from pathlib import Path

from checkpoint_a_live import _clear_cases, _ambiguous_cases
from checkpoint_a_protocol import (
    CRITERIA,
    build_manifest,
    load_evidence_object,
    verify_manifest,
    verify_row,
)
from ecocommit.checkpoint_a_evidence import CheckpointAEvidenceReceipt
from ecocommit.contracts import DecisionStatus
from ecocommit.interpreter import OpenAICompatibleIntentProvider
from ecocommit.validator import FidelityValidator


def compute_gate(frozen: list, by_id: dict[str, dict]) -> tuple[list[dict], list[str], dict, bool, bool]:
    ordered = [by_id[g.case_id] for g in frozen if g.case_id in by_id]
    expected_ids = {g.case_id for g in frozen}
    missing = sorted(expected_ids - set(by_id))

    validated = 0
    correct_validated = 0
    clarification_correct = 0
    for gold in frozen:
        row = by_id.get(gold.case_id)
        if not row:
            continue
        detail = row.get("detail")
        if not detail:
            continue
        if detail["validator_status"] == DecisionStatus.VALIDATED.value:
            validated += 1
            if row.get("passed"):
                correct_validated += 1
        if (
            gold.expected_status == DecisionStatus.CLARIFICATION_REQUIRED
            and detail["validator_status"] == DecisionStatus.CLARIFICATION_REQUIRED.value
        ):
            clarification_correct += 1

    total = len(ordered)
    passed_total = sum(1 for row in ordered if row.get("passed"))
    metrics = {
        "passed_cases": passed_total,
        "case_pass_rate": passed_total / 80 if total == 80 else 0.0,
        "autonomous_coverage": validated / 80 if total == 80 else 0.0,
        "selective_semantic_reliability": correct_validated / validated if validated else 0.0,
        "ambiguous_clarification_accuracy": clarification_correct / 30 if total == 80 else 0.0,
    }
    full_run = total == 80 and not missing
    passed = (
        full_run
        and metrics["case_pass_rate"] >= CRITERIA["case_pass_rate_min"]
        and metrics["selective_semantic_reliability"] >= CRITERIA["selective_semantic_reliability_min"]
        and metrics["autonomous_coverage"] >= CRITERIA["autonomous_coverage_min"]
        and metrics["ambiguous_clarification_accuracy"] >= CRITERIA["ambiguous_clarification_accuracy_min"]
    )
    return ordered, missing, metrics, full_run, passed


def main() -> int:
    parser = argparse.ArgumentParser(description="Aggregate frozen ECOCOMMIT Checkpoint A shards")
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--receipt-output")
    parser.add_argument("--evidence-reference")
    args = parser.parse_args()
    if bool(args.receipt_output) != bool(args.evidence_reference):
        raise SystemExit("--receipt-output and --evidence-reference must be supplied together")

    files = sorted(Path(args.input_dir).rglob("*.json"))
    if not files:
        raise SystemExit("no shard JSON files found")

    frozen = _clear_cases() + _ambiguous_cases()
    frozen_by_id = {gold.case_id: gold for gold in frozen}
    first_payload = load_evidence_object(files[0])
    supplied_manifest = first_payload.get("manifest", {})
    provider_config = supplied_manifest.get("provider", {})
    provider = OpenAICompatibleIntentProvider(
        provider_config.get("base_url", ""),
        "manifest-validation-only",
        provider_config.get("model", ""),
        reasoning_effort=provider_config.get("reasoning_effort"),
        max_completion_tokens=provider_config.get("max_completion_tokens"),
        use_json_schema=provider_config.get("json_schema"),
        max_attempts=provider_config.get("max_attempts", 1),
        max_schema_corrections=provider_config.get("max_schema_corrections", 1),
        max_retry_delay=provider_config.get("max_retry_delay_seconds", 0),
        max_response_bytes=provider_config.get("max_response_bytes", 1_048_576),
    )
    expected_manifest = build_manifest(frozen, provider)
    validator = FidelityValidator()

    by_id: dict[str, dict] = {}
    for path in files:
        payload = load_evidence_object(path)
        verify_manifest(payload.get("manifest", {}), expected_manifest)
        for row in payload.get("cases", []):
            case_id = row.get("id")
            gold = frozen_by_id.get(case_id)
            if gold is None:
                raise ValueError(f"unknown Checkpoint A case id: {case_id}")
            verified = verify_row(row, gold, expected_manifest, validator)
            previous = by_id.get(case_id)
            if previous is not None and previous.get("row_sha256") != verified.get("row_sha256"):
                raise ValueError(f"conflicting duplicate rows for {case_id}")
            by_id[case_id] = verified

    # Identical duplicates across immutable attempts are allowed; conflicts are not.
    ordered, missing, metrics, full_run, passed = compute_gate(frozen, by_id)

    summary = {
        "evidence_schema_version": expected_manifest["evidence_schema_version"],
        "manifest": expected_manifest,
        "provider": expected_manifest["provider"],
        "dataset": {"total": len(ordered), "clear": 50 if full_run else None, "ambiguous": 30 if full_run else None, "full_frozen_gate_run": full_run, "missing_case_ids": missing},
        "metrics": metrics,
        "checkpoint_a_gate": {"criteria": CRITERIA, "passed": passed},
        "cases": ordered,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(summary, indent=2, ensure_ascii=False).encode("utf-8")
    output.write_bytes(encoded)
    if passed and args.receipt_output:
        receipt = CheckpointAEvidenceReceipt(
            verification_mode="FROZEN_AGGREGATE",
            evidence_reference=args.evidence_reference,
            aggregate_sha256=sha256(encoded).hexdigest(),
            manifest_sha256=expected_manifest["manifest_sha256"],
            source_revision=expected_manifest["source_revision"],
            candidate_version=expected_manifest["candidate_version"],
            dataset_sha256=expected_manifest["dataset"]["sha256"],
            total_cases=len(ordered),
            full_frozen_gate_run=full_run,
            gate_passed=passed,
            metrics=metrics,
        )
        receipt_path = Path(args.receipt_output)
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(
            receipt.model_dump_json(indent=2) + "\n",
            encoding="utf-8",
        )
    print(json.dumps({"metrics": metrics, "checkpoint_a_gate": summary["checkpoint_a_gate"], "full_run": full_run, "missing": missing}, indent=2))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
