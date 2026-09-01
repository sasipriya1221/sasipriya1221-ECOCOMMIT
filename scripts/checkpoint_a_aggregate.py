from __future__ import annotations

import argparse
import json
from pathlib import Path

from checkpoint_a_live import _clear_cases, _ambiguous_cases
from ecocommit.contracts import DecisionStatus

CRITERIA = {
    "case_pass_rate_min": 0.90,
    "selective_semantic_reliability_min": 0.95,
    "autonomous_coverage_min": 0.55,
    "ambiguous_clarification_accuracy_min": 0.80,
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Aggregate frozen ECOCOMMIT Checkpoint A shards")
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    files = sorted(Path(args.input_dir).rglob("*.json"))
    if not files:
        raise SystemExit("no shard JSON files found")

    rows: list[dict] = []
    provider = None
    for path in files:
        payload = json.loads(path.read_text(encoding="utf-8"))
        provider = provider or payload.get("provider")
        rows.extend(payload.get("cases", []))

    # Deduplicate by immutable case id, then restore frozen order.
    by_id = {row["id"]: row for row in rows if "id" in row}
    frozen = _clear_cases() + _ambiguous_cases()
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
        if gold.expected_status == DecisionStatus.CLARIFICATION_REQUIRED and detail["validator_status"] == DecisionStatus.CLARIFICATION_REQUIRED.value:
            clarification_correct += 1

    total = len(ordered)
    passed_total = sum(1 for r in ordered if r.get("passed"))
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

    summary = {
        "provider": provider,
        "dataset": {"total": total, "clear": 50 if full_run else None, "ambiguous": 30 if full_run else None, "full_frozen_gate_run": full_run, "missing_case_ids": missing},
        "metrics": metrics,
        "checkpoint_a_gate": {"criteria": CRITERIA, "passed": passed},
        "cases": ordered,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"metrics": metrics, "checkpoint_a_gate": summary["checkpoint_a_gate"], "full_run": full_run, "missing": missing}, indent=2))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
