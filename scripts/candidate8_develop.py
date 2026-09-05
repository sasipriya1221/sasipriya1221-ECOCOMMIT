from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from dataclasses import asdict
from pathlib import Path

from ecocommit.candidate7_evaluator import aggregate, score_case
from ecocommit.candidate8 import run_candidate8
from ecocommit.candidate8_provider import GroqCandidate8Provider, PASS1_SYSTEM_PROMPT_C8, PASS2_SYSTEM_PROMPT


PARTITIONS = {
    "development": ("development.json", "development_gold.json"),
    "regression": ("regression.json", "regression_gold.json"),
}


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def run(partition: str, output_dir: Path) -> int:
    root = Path(__file__).resolve().parents[1]
    data_name, gold_name = PARTITIONS[partition]
    data_path = root / "data" / "candidate8-development" / data_name
    gold_path = root / "data" / "candidate8-development" / gold_name
    suite = json.loads(data_path.read_text(encoding="utf-8"))
    gold_doc = json.loads(gold_path.read_text(encoding="utf-8"))
    gold_by_id = {row["case_id"]: row for row in gold_doc["cases"]}
    cases = suite["cases"]
    if {row["case_id"] for row in cases} != set(gold_by_id):
        raise SystemExit("visible corpus/gold mismatch")

    key = os.environ.get("ECOCOMMIT_LLM_API_KEY", "").strip()
    if not key:
        raise SystemExit("ECOCOMMIT_LLM_API_KEY is required")
    provider = GroqCandidate8Provider(key)
    source_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    output_dir.mkdir(parents=True, exist_ok=False)

    rows, scores = [], []
    provider_attempts = 0
    for case in cases:
        cid, instruction = case["case_id"], case["instruction"]
        result = run_candidate8(instruction, provider)
        trace = list(result.provider_trace)
        provider_attempts += sum("attempt" in entry for entry in trace)
        score = score_case(cid, result, gold_by_id[cid])
        row = {
            "case_id": cid,
            "instruction_sha256": _sha(instruction),
            "feature_tags": case.get("feature_tags", []),
            "known_regression": bool(case.get("known_regression")),
            "observed_status": result.status,
            "error_code": result.error_code,
            "blocked_actions": sorted(result.blocked_actions),
            "facts": [f.model_dump(mode="json") for f in result.facts],
            "relations": result.relations.model_dump(mode="json") if result.relations else None,
            "logical_ast": {
                "edges": [asdict(e) for e in result.logical_ast.edges],
                "dispositions": [(fid, disp.value) for fid, disp in result.logical_ast.dispositions],
            } if result.logical_ast else None,
            "contract_sha256": result.contract.canonical_hash() if result.contract else None,
            "provider_trace": trace,
            "score": asdict(score),
        }
        (output_dir / f"{cid}.json").write_text(json.dumps(row, indent=2, sort_keys=True, default=str), encoding="utf-8")
        rows.append(row)
        if result.status != "PROVIDER_DEFERRED":
            scores.append(score)

    summary = aggregate(scores, gold_doc["cases"])
    summary.update({
        "candidate": "A-CANDIDATE-8",
        "mode": "VISIBLE_DEVELOPMENT",
        "partition": partition,
        "source_sha": source_sha,
        "provider": "Groq",
        "model": provider.model,
        "max_completion_tokens": provider.max_completion_tokens,
        "temperature": 0,
        "reasoning_effort": "none",
        "pass1_prompt_sha256": _sha(PASS1_SYSTEM_PROMPT_C8),
        "pass2_prompt_sha256": _sha(PASS2_SYSTEM_PROMPT),
        "dataset_sha256": hashlib.sha256(data_path.read_bytes()).hexdigest(),
        "gold_sha256": hashlib.sha256(gold_path.read_bytes()).hexdigest(),
        "provider_attempts": provider_attempts,
        "provider_deferred_cases": sum(r["observed_status"] == "PROVIDER_DEFERRED" for r in rows),
        "schema_or_validation_failures": sum(r["observed_status"] == "REJECTED" and r["error_code"] and "schema" in r["error_code"].lower() for r in rows),
        "known_regression_failures": sum(r["known_regression"] and not r["score"]["semantic_correct"] for r in rows),
    })
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    (output_dir / "rows.json").write_text(json.dumps(rows, indent=2, sort_keys=True, default=str), encoding="utf-8")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--partition", choices=sorted(PARTITIONS), required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(run(args.partition, args.output_dir))


if __name__ == "__main__":
    main()
