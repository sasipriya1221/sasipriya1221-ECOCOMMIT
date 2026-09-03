from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict
from pathlib import Path

from ecocommit.candidate6 import Candidate6Result
from ecocommit.candidate6_evaluator import aggregate, score_case
from ecocommit.candidate6_provider import GroqSemanticIRProvider, SemanticIRSchemaError
from ecocommit.interpreter import ProviderRequestError
from ecocommit.semantic_compiler import ConservationError, compile_contract
from ecocommit.semantic_validation import SemanticValidationError


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _result_from_ir(instruction, ir):
    try:
        contract, _, blocked = compile_contract(ir, instruction)
        return Candidate6Result("CLARIFICATION_REQUIRED" if blocked else "COMPILED", contract, ir, frozenset(blocked))
    except (SemanticValidationError, ConservationError, ValueError) as exc:
        # Retain the schema-valid IR for evidence and safety diagnostics even when
        # deterministic validation rejects it. No provider retry follows.
        return Candidate6Result("REJECTED", None, ir, frozenset(), str(exc))


def run(mode: str, output_dir: Path) -> int:
    if mode not in {"development", "holdout"}:
        raise SystemExit("mode must be development or holdout")
    root = Path(__file__).resolve().parents[1]
    suite_path = root / "data" / "candidate6" / f"{mode}.json"
    gold_path = root / "data" / "candidate6" / f"{mode}_gold.json"
    if mode == "holdout":
        receipt_path = root / "evidence" / "candidate6-freeze-receipt.json"
        if not receipt_path.exists():
            raise SystemExit("holdout is sealed until Candidate-6 freeze receipt exists")
        receipt = _load(receipt_path)
        if receipt.get("freeze_state") != "IMPLEMENTATION_FROZEN_BEFORE_HOLDOUT":
            raise SystemExit("invalid Candidate-6 freeze receipt")
        if receipt.get("holdout_provider_calls_before_freeze") != 0 or receipt.get("official_benchmark_calls_before_freeze") != 0:
            raise SystemExit("freeze receipt does not prove zero pre-freeze calls")
        if os.getenv("GITHUB_RUN_ATTEMPT", "1") != "1":
            raise SystemExit("Candidate-6 holdout workflow reruns are forbidden")

    api_key = os.getenv("ECOCOMMIT_LLM_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("ECOCOMMIT_LLM_API_KEY is required")
    provider = GroqSemanticIRProvider(api_key)
    suite = _load(suite_path)
    gold_doc = _load(gold_path)
    cases = suite["cases"]
    gold_rows = gold_doc["cases"]
    gold_by_id = {row["case_id"]: row for row in gold_rows}
    if len(cases) != 60 or len(gold_rows) != 60 or {c[0] for c in cases} != set(gold_by_id):
        raise SystemExit("Candidate-6 suite/gold coverage must be exactly 60 unique cases")

    output_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    scores = []
    provider_attempts = 0
    for case_id, instruction in cases:
        trace = []
        try:
            parsed = provider.parse_with_metadata(instruction)
            trace = list(parsed.provider_trace)
            provider_attempts += len(trace)
            result = _result_from_ir(instruction, parsed.semantic_ir)
        except SemanticIRSchemaError as exc:
            trace = list(exc.provider_trace)
            provider_attempts += len(trace)
            result = Candidate6Result("REJECTED", None, None, frozenset(), "IR_SCHEMA_INVALID")
        except ProviderRequestError as exc:
            trace = list(exc.provider_trace)
            provider_attempts += len(trace) if trace else exc.attempts
            result = Candidate6Result("PROVIDER_DEFERRED", None, None, frozenset(), exc.code)

        score = score_case(case_id, result, gold_by_id[case_id])
        scores.append(score)
        row = {
            "case_id": case_id,
            "instruction_sha256": __import__("hashlib").sha256(instruction.encode()).hexdigest(),
            "observed_status": result.status,
            "error_code": result.error_code,
            "blocked_actions": sorted(result.blocked_actions),
            "semantic_ir": result.semantic_ir.model_dump(mode="json") if result.semantic_ir is not None else None,
            "contract_sha256": result.contract.canonical_hash() if result.contract is not None else None,
            "provider_trace": trace,
            "score": asdict(score),
        }
        (output_dir / f"{case_id}.json").write_text(json.dumps(row, indent=2, sort_keys=True), encoding="utf-8")
        rows.append(row)

        current = aggregate(scores, gold_rows)
        if not current["reachable"]:
            current["stopped_early"] = True
            current["stopped_after_case"] = case_id
            current["provider_attempts"] = provider_attempts
            current["mode"] = mode
            (output_dir / "aggregate.json").write_text(json.dumps(current, indent=2, sort_keys=True), encoding="utf-8")
            (output_dir / "rows.json").write_text(json.dumps(rows, indent=2, sort_keys=True), encoding="utf-8")
            return 2

    final = aggregate(scores, gold_rows)
    final.update({"stopped_early": False, "provider_attempts": provider_attempts, "mode": mode})
    (output_dir / "aggregate.json").write_text(json.dumps(final, indent=2, sort_keys=True), encoding="utf-8")
    (output_dir / "rows.json").write_text(json.dumps(rows, indent=2, sort_keys=True), encoding="utf-8")
    return 0 if final["passed"] else 2


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", required=True, choices=["development", "holdout"])
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    raise SystemExit(run(args.mode, args.output_dir))


if __name__ == "__main__":
    main()
