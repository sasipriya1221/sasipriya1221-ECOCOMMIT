from __future__ import annotations

import argparse
import hashlib
import json
import os
from dataclasses import asdict
from pathlib import Path

from ecocommit.candidate6 import Candidate6Result
from ecocommit.candidate6_evaluator import aggregate, score_case
from ecocommit.candidate6_freeze import verify_freeze_receipt
from ecocommit.candidate6_provider import GroqSemanticIRProvider, SemanticIRSchemaError
from ecocommit.interpreter import ProviderRequestError
from ecocommit.semantic_compiler import ConservationError, compile_contract
from ecocommit.semantic_validation import SemanticValidationError

PROVIDER_DEFERRAL_STREAK_LIMIT = 3


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _result_from_ir(instruction, ir):
    try:
        contract, _, blocked = compile_contract(ir, instruction)
        return Candidate6Result("CLARIFICATION_REQUIRED" if blocked else "COMPILED", contract, ir, frozenset(blocked))
    except (SemanticValidationError, ConservationError, ValueError) as exc:
        return Candidate6Result("REJECTED", None, ir, frozenset(), str(exc))


def _write_summary(output_dir: Path, rows, scores, gold_rows, provider_attempts: int, mode: str, **extra) -> dict:
    payload = aggregate(scores, gold_rows)
    payload.update({"provider_attempts": provider_attempts, "mode": mode, **extra})
    payload["provider_deferred_cases"] = sum(row["observed_status"] == "PROVIDER_DEFERRED" for row in rows)
    payload["terminal_semantic_cases"] = len(scores)
    (output_dir / "aggregate.json").write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    (output_dir / "rows.json").write_text(json.dumps(rows, indent=2, sort_keys=True), encoding="utf-8")
    return payload


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
        try:
            verify_freeze_receipt(root, receipt)
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
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

    output_dir.mkdir(parents=True, exist_ok=False)
    rows = []
    scores = []
    provider_attempts = 0
    provider_deferral_streak = 0
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
        row = {
            "case_id": case_id,
            "instruction_sha256": hashlib.sha256(instruction.encode()).hexdigest(),
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

        if result.status == "PROVIDER_DEFERRED":
            # Provider availability is infrastructure evidence, not semantic evidence.
            # Do not spend the frozen semantic failure budget on 429/5xx/transport errors.
            provider_deferral_streak += 1
            if provider_deferral_streak >= PROVIDER_DEFERRAL_STREAK_LIMIT:
                _write_summary(
                    output_dir, rows, scores, gold_rows, provider_attempts, mode,
                    stopped_early=True, stopped_after_case=case_id,
                    qualification_state="PROVIDER_INCOMPLETE",
                    infrastructure_reason="CONSECUTIVE_PROVIDER_DEFERRALS",
                )
                return 75
            continue

        provider_deferral_streak = 0
        scores.append(score)
        current = aggregate(scores, gold_rows)
        if not current["reachable"]:
            _write_summary(
                output_dir, rows, scores, gold_rows, provider_attempts, mode,
                stopped_early=True, stopped_after_case=case_id,
                qualification_state="SEMANTICALLY_UNREACHABLE",
            )
            return 2

    final = _write_summary(
        output_dir, rows, scores, gold_rows, provider_attempts, mode,
        stopped_early=False,
        qualification_state="COMPLETE" if len(scores) == len(gold_rows) else "PROVIDER_INCOMPLETE",
    )
    if len(scores) != len(gold_rows):
        return 75
    return 0 if final["passed"] else 2


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", required=True, choices=["development", "holdout"])
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    raise SystemExit(run(args.mode, args.output_dir))


if __name__ == "__main__":
    main()
