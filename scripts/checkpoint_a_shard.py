from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from checkpoint_a_live import _clear_cases, _ambiguous_cases, _evaluate_one
from ecocommit.interpreter import OpenAICompatibleIntentProvider
from ecocommit.validator import FidelityValidator


def _is_transient_provider_error(row: dict) -> bool:
    error_text = str(row.get("error", ""))
    transient_markers = (
        "provider HTTP 429",
        "provider HTTP 500",
        "provider HTTP 502",
        "provider HTTP 503",
        "provider HTTP 504",
        "provider transport error",
    )
    return any(marker in error_text for marker in transient_markers)


def _load_resume(path: Path | None, selected_ids: set[str]) -> list[dict]:
    if path is None or not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []

    rows: list[dict] = []
    seen: set[str] = set()
    for row in payload.get("cases", []):
        case_id = row.get("id")
        if case_id not in selected_ids or case_id in seen:
            continue
        # Provider capacity errors are infrastructure, never frozen semantic results.
        if _is_transient_provider_error(row):
            continue
        rows.append(row)
        seen.add(case_id)
    return rows


def _write_partial(
    output: Path,
    *,
    base_url: str,
    model: str,
    start: int,
    end: int,
    rows: list[dict],
    frozen_index_by_id: dict[str, int],
    infrastructure_error: str | None = None,
) -> None:
    completed_indices = [frozen_index_by_id[r["id"]] for r in rows if r.get("id") in frozen_index_by_id]
    payload = {
        "provider": {"base_url": base_url, "model": model},
        "shard": {
            "start": start,
            "end": end,
            "completed_case_ids": [r.get("id") for r in rows],
            "last_completed_index": max(completed_indices) if completed_indices else None,
        },
        "cases": rows,
    }
    if infrastructure_error:
        payload["infrastructure_error"] = infrastructure_error
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one resumable ECOCOMMIT Checkpoint A shard")
    parser.add_argument("--start", type=int, required=True, help="0-based inclusive index in frozen 80-case set")
    parser.add_argument("--end", type=int, required=True, help="0-based exclusive index in frozen 80-case set")
    parser.add_argument("--output", required=True)
    parser.add_argument("--resume", default=None, help="optional previous shard JSON to resume from")
    parser.add_argument("--base-url", default=os.getenv("ECOCOMMIT_LLM_BASE_URL", "https://api.openai.com/v1"))
    parser.add_argument("--model", default=os.getenv("ECOCOMMIT_LLM_MODEL"))
    parser.add_argument("--api-key", default=os.getenv("ECOCOMMIT_LLM_API_KEY"))
    args = parser.parse_args()

    if not args.model:
        raise SystemExit("ECOCOMMIT_LLM_MODEL (or --model) is required")
    if not args.api_key:
        raise SystemExit("ECOCOMMIT_LLM_API_KEY (or --api-key) is required")

    frozen = _clear_cases() + _ambiguous_cases()
    if not (0 <= args.start < args.end <= len(frozen)):
        raise SystemExit(f"invalid shard bounds {args.start}:{args.end} for {len(frozen)} frozen cases")

    # CI intentionally fails fast on provider quota/capacity errors. A transient
    # provider failure is retried later as its own immutable case rather than
    # sleeping for many minutes while blocking every case behind it. This changes
    # only execution scheduling; the frozen case, model prompt and scoring stay intact.
    max_attempts = max(1, int(os.getenv("ECOCOMMIT_LLM_CASE_MAX_ATTEMPTS", "2")))
    max_retry_delay = max(0.0, float(os.getenv("ECOCOMMIT_LLM_CASE_MAX_RETRY_DELAY", "15")))
    provider = OpenAICompatibleIntentProvider(
        args.base_url,
        args.api_key,
        args.model,
        timeout=60.0,
        max_attempts=max_attempts,
        max_retry_delay=max_retry_delay,
    )
    validator = FidelityValidator()
    selected = frozen[args.start:args.end]
    selected_ids = {gold.case_id for gold in selected}
    frozen_index_by_id = {gold.case_id: i for i, gold in enumerate(frozen)}
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    resume_path = Path(args.resume) if args.resume else None
    rows = _load_resume(resume_path, selected_ids)
    completed_ids = {row["id"] for row in rows if row.get("id")}

    _write_partial(
        output,
        base_url=args.base_url,
        model=args.model,
        start=args.start,
        end=args.end,
        rows=rows,
        frozen_index_by_id=frozen_index_by_id,
    )

    for gold in selected:
        if gold.case_id in completed_ids:
            print(json.dumps({"resumed": gold.case_id}), flush=True)
            continue

        row = _evaluate_one(gold, provider, validator)
        if _is_transient_provider_error(row):
            _write_partial(
                output,
                base_url=args.base_url,
                model=args.model,
                start=args.start,
                end=args.end,
                rows=rows,
                frozen_index_by_id=frozen_index_by_id,
                infrastructure_error=row.get("error"),
            )
            print(json.dumps({"deferred": gold.case_id, "reason": "transient_provider_error"}), flush=True)
            return 75

        rows.append(row)
        completed_ids.add(gold.case_id)
        _write_partial(
            output,
            base_url=args.base_url,
            model=args.model,
            start=args.start,
            end=args.end,
            rows=rows,
            frozen_index_by_id=frozen_index_by_id,
        )
        print(json.dumps({"completed": gold.case_id, "passed": row.get("passed", False)}), flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
