from __future__ import annotations

import argparse
import hashlib
import json
import os
from dataclasses import asdict
from pathlib import Path

from ecocommit.candidate7 import run_candidate7
from ecocommit.candidate7_evaluator import aggregate, score_case
from ecocommit.candidate7_provider import GroqCandidate7Provider


PROVIDER_DEFERRAL_STREAK_LIMIT = 3


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _trace_metrics(rows) -> tuple[int, int]:
    relations_dropped_ungrounded = 0
    actions_corrected_out_of_vocab = 0
    for row in rows:
        trace = row.get("provider_trace") or []
        relations_dropped_ungrounded += sum(
            entry.get("outcome") == "relation_dropped_ungrounded" for entry in trace
        )
        # Branch 1c routes OOV ACTION values through the existing bounded schema
        # correction loop. Count an OOV invalid attempt only when a later facts
        # attempt for that same case was accepted, i.e. the bounded correction worked.
        saw_oov = any(
            entry.get("stage") == "facts"
            and entry.get("outcome") == "schema_invalid"
            and any(issue.get("code") == "C7_ACTION_TYPE_OUT_OF_VOCAB" for issue in entry.get("issues", []))
            for entry in trace
        )
        later_accepted = any(
            entry.get("stage") == "facts" and entry.get("outcome") == "accepted"
            for entry in trace
        )
        if saw_oov and later_accepted:
            actions_corrected_out_of_vocab += 1
    return relations_dropped_ungrounded, actions_corrected_out_of_vocab


def _write_summary(output_dir: Path, rows, scores, gold_rows, provider_attempts: int, **extra) -> dict:
    payload = aggregate(scores, gold_rows)
    relations_dropped_ungrounded, actions_corrected_out_of_vocab = _trace_metrics(rows)
    payload.update({
        "provider_attempts": provider_attempts,
        "mode": "development",
        "relations_dropped_ungrounded": relations_dropped_ungrounded,
        "actions_corrected_out_of_vocab": actions_corrected_out_of_vocab,
        **extra,
    })
    payload["provider_deferred_cases"] = sum(row["observed_status"] == "PROVIDER_DEFERRED" for row in rows)
    payload["terminal_semantic_cases"] = len(scores)
    (output_dir / "aggregate.json").write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    (output_dir / "rows.json").write_text(json.dumps(rows, indent=2, sort_keys=True), encoding="utf-8")
    return payload


def run(output_dir: Path) -> int:
    root = Path(__file__).resolve().parents[1]
    # Candidate 7 intentionally reuses the already-open Candidate-6 DEVELOPMENT suite
    # for direct architecture comparison. It does not read holdout or official-A data.
    suite_path = root / "data" / "candidate6" / "development.json"
    gold_path = root / "data" / "candidate6" / "development_gold.json"

    api_key = os.getenv("ECOCOMMIT_LLM_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("ECOCOMMIT_LLM_API_KEY is required")

    suite = _load(suite_path)
    gold_doc = _load(gold_path)
    cases = suite["cases"]
    gold_rows = gold_doc["cases"]
    gold_by_id = {row["case_id"]: row for row in gold_rows}
    if len(cases) != 60 or len(gold_rows) != 60 or {case[0] for case in cases} != set(gold_by_id):
        raise SystemExit("Candidate-7 development suite/gold coverage must be exactly 60 unique cases")

    output_dir.mkdir(parents=True, exist_ok=False)
    provider = GroqCandidate7Provider(api_key)
    rows = []
    scores = []
    provider_attempts = 0
    provider_deferral_streak = 0

    for case_id, instruction in cases:
        result = run_candidate7(instruction, provider)
        trace = list(result.provider_trace)
        provider_attempts += len([entry for entry in trace if "attempt" in entry])
        score = score_case(case_id, result, gold_by_id[case_id])
        row = {
            "case_id": case_id,
            "instruction_sha256": hashlib.sha256(instruction.encode()).hexdigest(),
            "observed_status": result.status,
            "error_code": result.error_code,
            "blocked_actions": sorted(result.blocked_actions),
            "facts": [fact.model_dump(mode="json") for fact in result.facts],
            "relations": result.relations.model_dump(mode="json") if result.relations is not None else None,
            "contract_sha256": result.contract.canonical_hash() if result.contract is not None else None,
            "provider_trace": trace,
            "score": asdict(score),
        }
        (output_dir / f"{case_id}.json").write_text(json.dumps(row, indent=2, sort_keys=True), encoding="utf-8")
        rows.append(row)

        if result.status == "PROVIDER_DEFERRED":
            provider_deferral_streak += 1
            if provider_deferral_streak >= PROVIDER_DEFERRAL_STREAK_LIMIT:
                _write_summary(
                    output_dir, rows, scores, gold_rows, provider_attempts,
                    stopped_early=True,
                    stopped_after_case=case_id,
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
                output_dir, rows, scores, gold_rows, provider_attempts,
                stopped_early=True,
                stopped_after_case=case_id,
                qualification_state="SEMANTICALLY_UNREACHABLE",
            )
            return 2

    final = _write_summary(
        output_dir, rows, scores, gold_rows, provider_attempts,
        stopped_early=False,
        qualification_state="COMPLETE" if len(scores) == len(gold_rows) else "PROVIDER_INCOMPLETE",
    )
    if len(scores) != len(gold_rows):
        return 75
    return 0 if final["passed"] else 2


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    raise SystemExit(run(args.output_dir))


if __name__ == "__main__":
    main()
