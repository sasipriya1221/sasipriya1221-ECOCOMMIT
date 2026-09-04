from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from pydantic import ValidationError

from ecocommit.candidate7_flat import LabeledFact, drop_ungrounded_relations
from ecocommit.candidate7_provider import GroqCandidate7Provider, PASS2_SYSTEM_PROMPT
from ecocommit.candidate7_relation_checklist import (
    Pass2DecisionBatch,
    action_entity_pair_payload,
    validate_and_materialize_pass2,
)
from ecocommit.interpreter import ProviderRequestError

CASES = {
    "D003": {
        "instruction": "Pay printer exactly ₹32,500 for completed run.",
        "facts": [
            {"id":"F0001","text_span":{"quote":"Pay","occurrence":1},"kind":"ACTION","polarity":"POSITIVE","action_type":"PAY"},
            {"id":"F0002","text_span":{"quote":"printer","occurrence":1},"kind":"ENTITY","polarity":"POSITIVE","action_type":None},
            {"id":"F0003","text_span":{"quote":"exactly ₹32,500","occurrence":1},"kind":"CONSTRAINT","polarity":"POSITIVE","action_type":None},
            {"id":"F0004","text_span":{"quote":"completed run","occurrence":1},"kind":"ENTITY","polarity":"POSITIVE","action_type":None},
        ],
    },
    "D009": {
        "instruction": "Order 500 envelopes only if warehouse count below 100.",
        "facts": [
            {"id":"F0001","text_span":{"quote":"Order 500 envelopes","occurrence":1},"kind":"ACTION","polarity":"POSITIVE","action_type":"ORDER"},
            {"id":"F0002","text_span":{"quote":"500 envelopes","occurrence":1},"kind":"ENTITY","polarity":"POSITIVE","action_type":None},
            {"id":"F0003","text_span":{"quote":"warehouse count below 100","occurrence":1},"kind":"PREDICATE","polarity":"POSITIVE","action_type":None},
        ],
    },
}


def _facts(case_id: str) -> tuple[LabeledFact, ...]:
    return tuple(LabeledFact.model_validate(x) for x in CASES[case_id]["facts"])


def _messages(case_id: str):
    instruction = CASES[case_id]["instruction"]
    facts = _facts(case_id)
    payload = {
        "instruction": instruction,
        "facts": [f.model_dump(mode="json") for f in facts],
        "action_entity_pairs": action_entity_pair_payload(facts),
    }
    return instruction, facts, [
        {"role": "system", "content": PASS2_SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(payload, separators=(",", ":"), ensure_ascii=False)},
    ]


def _signatures(batch) -> set[tuple[str, str, str]]:
    return {(r.kind.value, r.left, r.right) for r in batch.relations}


def _semantic_result(case_id: str, batch) -> tuple[bool, bool]:
    sig = _signatures(batch)
    if case_id == "D003":
        old_failure = (
            ("ACTION_COUNTERPARTY", "F0001", "F0002") in sig
            and ("ACTION_OBJECT", "F0001", "F0004") in sig
        )
        correct = ("ACTION_OBJECT", "F0001", "F0002") in sig and not old_failure
        return correct, old_failure
    old_failure = ("ACTION_OBJECT", "F0001", "F0002") not in sig
    correct = not old_failure
    return correct, old_failure


def run_attempt(case_id: str, attempt: int, output: Path) -> int:
    output.parent.mkdir(parents=True, exist_ok=True)
    instruction, facts, messages = _messages(case_id)
    row = {
        "case_id": case_id,
        "attempt": attempt,
        "instruction": instruction,
        "status": None,
        "provider_calls": 1,
    }
    try:
        provider = GroqCandidate7Provider(os.environ["ECOCOMMIT_LLM_API_KEY"])
        parsed, metadata = provider._request(messages, 1)
        row["provider_metadata"] = metadata
        try:
            decision_batch = Pass2DecisionBatch.model_validate(parsed)
            materialized = validate_and_materialize_pass2(instruction, facts, decision_batch)
            kept, drops = drop_ungrounded_relations(instruction, materialized)
        except (ValidationError, ValueError, TypeError) as exc:
            row.update({
                "status": "rejected_validation",
                "validation_error_type": type(exc).__name__,
                "validation_error": str(exc),
                "raw_provider_json": parsed,
            })
        else:
            correct, old_failure = _semantic_result(case_id, kept)
            row.update({
                "status": "accepted",
                "decision_batch": decision_batch.model_dump(mode="json"),
                "materialized_relation_batch": materialized.model_dump(mode="json"),
                "relation_batch": kept.model_dump(mode="json"),
                "grounding_drops": list(drops),
                "correct_result": correct,
                "matches_original_failure_signature": old_failure,
            })
    except ProviderRequestError as exc:
        row.update({
            "status": "provider_failed",
            "provider_error_code": exc.code,
            "provider_transient": exc.transient,
        })
    except Exception as exc:
        row.update({
            "status": "interrupted",
            "error_type": type(exc).__name__,
            "error": str(exc),
        })

    output.write_text(json.dumps(row, sort_keys=True, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


def summarize(directory: Path, output: Path) -> int:
    attempts = []
    for case_id in ("D003", "D009"):
        for attempt in range(1, 6):
            path = directory / f"{case_id.lower()}-{attempt}.json"
            if path.exists():
                attempts.append(json.loads(path.read_text(encoding="utf-8")))
            else:
                attempts.append({"case_id": case_id, "attempt": attempt, "status": "interrupted", "provider_calls": 0, "missing_result": True})

    by_case = {}
    any_old_failure = False
    for case_id in ("D003", "D009"):
        rows = [x for x in attempts if x["case_id"] == case_id]
        accepted = [x for x in rows if x["status"] == "accepted"]
        provider_failed = [x for x in rows if x["status"] == "provider_failed"]
        validation_failed = [x for x in rows if x["status"] == "rejected_validation"]
        interrupted = [x for x in rows if x["status"] == "interrupted"]
        old_matches = sum(bool(x.get("matches_original_failure_signature")) for x in accepted)
        correct = sum(bool(x.get("correct_result")) for x in accepted)
        any_old_failure = any_old_failure or old_matches > 0
        by_case[case_id] = {
            "attempted": 5,
            "accepted": len(accepted),
            "provider_failures": len(provider_failed),
            "validation_failures": len(validation_failed),
            "interrupted": len(interrupted),
            "old_failure_signature_matches": old_matches,
            "old_failure_signature_match_rate_among_accepted": (old_matches / len(accepted)) if accepted else None,
            "correct_results": correct,
            "correct_result_rate_among_accepted": (correct / len(accepted)) if accepted else None,
        }

    if any_old_failure:
        status = "FAIL"
    elif any(by_case[c]["accepted"] < 5 for c in ("D003", "D009")):
        status = "INCONCLUSIVE"
    elif all(by_case[c]["correct_results"] == 5 for c in ("D003", "D009")):
        status = "PASS"
    else:
        status = "FAIL"

    summary = {
        "qualification_status": status,
        "provider_call_cap": 10,
        "provider_calls_recorded": sum(int(x.get("provider_calls", 0)) for x in attempts),
        "cases": by_case,
        "attempts": attempts,
    }
    output.write_text(json.dumps(summary, sort_keys=True, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


def self_check() -> int:
    # No provider calls. Validate frozen facts, exhaustive pair payloads, and known-good mocked Pass-2 batches.
    mocked = {
        "D003": {
            "action_entity_decisions": [
                {"action":"F0001","entity":"F0002","decision":"ACTION_OBJECT","justification_span":"Pay printer"},
                {"action":"F0001","entity":"F0004","decision":"NONE","justification_span":None},
            ],
            "relations": [
                {"kind":"CONSTRAINT_APPLIES_TO","left":"F0003","right":"F0001","justification_span":"Pay printer exactly ₹32,500"}
            ],
        },
        "D009": {
            "action_entity_decisions": [
                {"action":"F0001","entity":"F0002","decision":"ACTION_OBJECT","justification_span":"Order 500 envelopes"}
            ],
            "relations": [
                {"kind":"GUARDS_ACTION","left":"F0003","right":"F0001","justification_span":"only if warehouse count below 100"}
            ],
        },
    }
    for case_id in ("D003", "D009"):
        instruction, facts, _ = _messages(case_id)
        batch = Pass2DecisionBatch.model_validate(mocked[case_id])
        materialized = validate_and_materialize_pass2(instruction, facts, batch)
        correct, old_failure = _semantic_result(case_id, materialized)
        if not correct or old_failure:
            raise SystemExit(f"self-check failed for {case_id}")
    print("candidate7 qualification harness self-check passed; provider calls=0")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("self-check")
    run = sub.add_parser("run-attempt")
    run.add_argument("--case", choices=["D003", "D009"], required=True)
    run.add_argument("--attempt", type=int, choices=range(1, 6), required=True)
    run.add_argument("--output", type=Path, required=True)
    summ = sub.add_parser("summarize")
    summ.add_argument("--directory", type=Path, required=True)
    summ.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "self-check":
        return self_check()
    if args.command == "run-attempt":
        return run_attempt(args.case, args.attempt, args.output)
    return summarize(args.directory, args.output)


if __name__ == "__main__":
    sys.exit(main())
