from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from pydantic import ValidationError

from ecocommit.candidate7_flat import LabeledFact, drop_ungrounded_relations
from ecocommit.candidate7_provider import GroqCandidate7Provider, PASS2_SYSTEM_PROMPT
from ecocommit.candidate7_relation_checklist import (
    Pass2DecisionBatch,
    action_entity_pair_payload,
    validate_and_materialize_pass2,
)
from ecocommit.interpreter import ProviderRequestError

MIN_SUCCESS_INTERVAL_SECONDS = 60.0
RATE_LIMIT_BUFFER_SECONDS = 5.0
RATE_LIMIT_HEADER_ALLOWLIST = {
    "retry-after": "Retry-After",
    "x-ratelimit-limit-requests": "x-ratelimit-limit-requests",
    "x-ratelimit-remaining-requests": "x-ratelimit-remaining-requests",
    "x-ratelimit-reset-requests": "x-ratelimit-reset-requests",
    "x-ratelimit-limit-tokens": "x-ratelimit-limit-tokens",
    "x-ratelimit-remaining-tokens": "x-ratelimit-remaining-tokens",
    "x-ratelimit-reset-tokens": "x-ratelimit-reset-tokens",
}

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


class SystemClock:
    def utc_now(self) -> datetime:
        return datetime.now(timezone.utc)

    def monotonic(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


def _utc_iso(clock: Any) -> str:
    return clock.utc_now().astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _write_evidence(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(row, sort_keys=True, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


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
        return ("ACTION_OBJECT", "F0001", "F0002") in sig and not old_failure, old_failure
    old_failure = ("ACTION_OBJECT", "F0001", "F0002") not in sig
    return not old_failure, old_failure


def _sanitize_provider_error(exc: ProviderRequestError) -> dict[str, Any]:
    raw_headers = dict(getattr(exc, "rate_limit_headers", {}) or {})
    lowered = {str(k).lower(): str(v).strip() for k, v in raw_headers.items()}
    headers = {
        saved_name: lowered[source_name]
        for source_name, saved_name in RATE_LIMIT_HEADER_ALLOWLIST.items()
        if source_name in lowered
    }
    status = None
    match = re.fullmatch(r"HTTP_(\d{3})", str(exc.code))
    if match:
        status = int(match.group(1))
    retry_after = getattr(exc, "retry_after_seconds", None)
    try:
        retry_after = float(retry_after) if retry_after is not None else None
    except (TypeError, ValueError):
        retry_after = None
    return {
        "http_status": status,
        "transient": bool(exc.transient),
        "retry_after_seconds": retry_after,
        "headers": headers,
    }


def _duration_seconds(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    try:
        return max(0.0, float(text))
    except ValueError:
        pass
    matches = re.findall(r"(\d+(?:\.\d+)?)\s*(ms|s|m|h)", text)
    if not matches or "".join(f"{n}{u}" for n, u in matches).replace(" ", "") != re.sub(r"\s+", "", text):
        return None
    scale = {"ms": 0.001, "s": 1.0, "m": 60.0, "h": 3600.0}
    return sum(float(number) * scale[unit] for number, unit in matches)


def _provider_directed_wait_seconds(error_evidence: dict[str, Any]) -> float:
    values = []
    retry = error_evidence.get("retry_after_seconds")
    if isinstance(retry, (int, float)):
        values.append(float(retry))
    headers = error_evidence.get("headers") or {}
    for name in ("Retry-After", "x-ratelimit-reset-requests", "x-ratelimit-reset-tokens"):
        parsed = _duration_seconds(headers.get(name))
        if parsed is not None:
            values.append(parsed)
    return max(values, default=0.0)


def required_interval_seconds(error_evidence: dict[str, Any] | None = None) -> float:
    directed = _provider_directed_wait_seconds(error_evidence or {})
    if directed > MIN_SUCCESS_INTERVAL_SECONDS:
        return directed + RATE_LIMIT_BUFFER_SECONDS
    return MIN_SUCCESS_INTERVAL_SECONDS


def run_attempt(
    case_id: str,
    attempt: int,
    output: Path,
    *,
    provider_factory: Callable[[], Any] | None = None,
    clock: Any | None = None,
) -> dict[str, Any]:
    clock = clock or SystemClock()
    provider_factory = provider_factory or (lambda: GroqCandidate7Provider(os.environ["ECOCOMMIT_LLM_API_KEY"]))
    instruction, facts, messages = _messages(case_id)
    row: dict[str, Any] = {
        "case_id": case_id,
        "attempt": attempt,
        "status": "attempt_started",
        "provider_calls": 1,
        "provider_attempt_started_at_utc": _utc_iso(clock),
    }
    _write_evidence(output, row)
    try:
        provider = provider_factory()
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
            })
        else:
            correct, old_failure = _semantic_result(case_id, kept)
            row.update({
                "status": "accepted",
                "relation_signatures": sorted([list(x) for x in _signatures(kept)]),
                "grounding_drop_count": len(drops),
                "correct_result": correct,
                "matches_original_failure_signature": old_failure,
            })
    except ProviderRequestError as exc:
        row.update({
            "status": "provider_failed",
            "provider_error_code": exc.code,
            "provider_error": _sanitize_provider_error(exc),
        })
    except Exception as exc:
        row.update({
            "status": "interrupted",
            "error_type": type(exc).__name__,
        })
    finally:
        row["provider_attempt_finished_at_utc"] = _utc_iso(clock)
        _write_evidence(output, row)
    return row


def _summary_from_attempts(attempts: list[dict[str, Any]], *, stopped_after_429: bool = False) -> dict[str, Any]:
    by_case = {}
    any_old_failure = False
    for case_id in ("D003", "D009"):
        rows = [x for x in attempts if x.get("case_id") == case_id]
        accepted = [x for x in rows if x.get("status") == "accepted"]
        provider_failed = [x for x in rows if x.get("status") == "provider_failed"]
        validation_failed = [x for x in rows if x.get("status") == "rejected_validation"]
        interrupted = [x for x in rows if x.get("status") == "interrupted"]
        old_matches = sum(bool(x.get("matches_original_failure_signature")) for x in accepted)
        correct = sum(bool(x.get("correct_result")) for x in accepted)
        any_old_failure = any_old_failure or old_matches > 0
        by_case[case_id] = {
            "attempted": len(rows),
            "accepted": len(accepted),
            "provider_failures": len(provider_failed),
            "validation_failures": len(validation_failed),
            "interrupted": len(interrupted),
            "old_failure_signature_matches": old_matches,
            "old_failure_signature_match_rate_among_accepted": (old_matches / len(accepted)) if accepted else None,
            "correct_results": correct,
            "correct_result_rate_among_accepted": (correct / len(accepted)) if accepted else None,
        }
    if stopped_after_429:
        status = "INCONCLUSIVE"
    elif any_old_failure:
        status = "FAIL"
    elif len(attempts) < 10 or any(by_case[c]["accepted"] < 5 for c in ("D003", "D009")):
        status = "INCONCLUSIVE"
    elif all(by_case[c]["correct_results"] == 5 for c in ("D003", "D009")):
        status = "PASS"
    else:
        status = "FAIL"
    return {
        "qualification_status": status,
        "provider_call_cap": 10,
        "provider_calls_recorded": sum(int(x.get("provider_calls", 0)) for x in attempts),
        "stopped_after_first_http_429": stopped_after_429,
        "cases": by_case,
        "attempts": attempts,
    }


def summarize(directory: Path, output: Path) -> int:
    attempts = []
    for case_id in ("D003", "D009"):
        for attempt in range(1, 6):
            path = directory / f"{case_id.lower()}-{attempt}.json"
            if path.exists():
                attempts.append(json.loads(path.read_text(encoding="utf-8")))
    stopped = any((x.get("provider_error") or {}).get("http_status") == 429 for x in attempts)
    _write_evidence(output, _summary_from_attempts(attempts, stopped_after_429=stopped))
    return 0


def run_qualification(
    directory: Path,
    *,
    provider_factory: Callable[[], Any] | None = None,
    clock: Any | None = None,
) -> dict[str, Any]:
    clock = clock or SystemClock()
    directory.mkdir(parents=True, exist_ok=True)
    attempts: list[dict[str, Any]] = []
    next_allowed = clock.monotonic()
    stopped_after_429 = False
    for case_id in ("D003", "D009"):
        for attempt in range(1, 6):
            remaining = next_allowed - clock.monotonic()
            if remaining > 0:
                clock.sleep(remaining)
            call_started = clock.monotonic()
            row = run_attempt(
                case_id,
                attempt,
                directory / f"{case_id.lower()}-{attempt}.json",
                provider_factory=provider_factory,
                clock=clock,
            )
            attempts.append(row)
            error_evidence = row.get("provider_error") if row.get("status") == "provider_failed" else None
            interval = required_interval_seconds(error_evidence)
            next_allowed = call_started + interval
            if (error_evidence or {}).get("http_status") == 429:
                stopped_after_429 = True
                summary = _summary_from_attempts(attempts, stopped_after_429=True)
                _write_evidence(directory / "summary.json", summary)
                return summary
            _write_evidence(directory / "summary.partial.json", _summary_from_attempts(attempts))
    summary = _summary_from_attempts(attempts, stopped_after_429=stopped_after_429)
    _write_evidence(directory / "summary.json", summary)
    return summary


def self_check() -> int:
    mocked = {
        "D003": {
            "action_entity_decisions": [
                {"action":"F0001","entity":"F0002","decision":"ACTION_OBJECT","justification_span":"Pay printer"},
                {"action":"F0001","entity":"F0004","decision":"NONE","justification_span":None},
            ],
            "relations": [{"kind":"CONSTRAINT_APPLIES_TO","left":"F0003","right":"F0001","justification_span":"Pay printer exactly ₹32,500"}],
        },
        "D009": {
            "action_entity_decisions": [{"action":"F0001","entity":"F0002","decision":"ACTION_OBJECT","justification_span":"Order 500 envelopes"}],
            "relations": [{"kind":"GUARDS_ACTION","left":"F0003","right":"F0001","justification_span":"only if warehouse count below 100"}],
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
    qual = sub.add_parser("qualify")
    qual.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "self-check":
        return self_check()
    if args.command == "run-attempt":
        run_attempt(args.case, args.attempt, args.output)
        return 0
    if args.command == "qualify":
        run_qualification(args.directory)
        return 0
    return summarize(args.directory, args.output)


if __name__ == "__main__":
    sys.exit(main())
