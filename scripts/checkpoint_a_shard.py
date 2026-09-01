from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from checkpoint_a_live import _clear_cases, _ambiguous_cases, _evaluate_one
from ecocommit.interpreter import OpenAICompatibleIntentProvider
from ecocommit.validator import FidelityValidator


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one resumable ECOCOMMIT Checkpoint A shard")
    parser.add_argument("--start", type=int, required=True, help="0-based inclusive index in frozen 80-case set")
    parser.add_argument("--end", type=int, required=True, help="0-based exclusive index in frozen 80-case set")
    parser.add_argument("--output", required=True)
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

    provider = OpenAICompatibleIntentProvider(args.base_url, args.api_key, args.model, timeout=60.0)
    validator = FidelityValidator()
    selected = frozen[args.start:args.end]
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    rows: list[dict] = []
    for i, gold in enumerate(selected, start=args.start):
        row = _evaluate_one(gold, provider, validator)
        rows.append(row)
        # Persist after every case so progress is inspectable and no completed case is
        # lost if a provider or runner interrupts a later request.
        partial = {
            "provider": {"base_url": args.base_url, "model": args.model},
            "shard": {"start": args.start, "end": args.end, "last_completed_index": i},
            "cases": rows,
        }
        output.write_text(json.dumps(partial, indent=2, ensure_ascii=False), encoding="utf-8")
        print(json.dumps({"completed": gold.case_id, "passed": row.get("passed", False)}), flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
