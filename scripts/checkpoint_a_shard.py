from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from checkpoint_a_live import _clear_cases, _ambiguous_cases, _evaluate_one
from checkpoint_a_protocol import (
    bind_row,
    build_manifest,
    load_evidence_object,
    verify_manifest,
    verify_row,
)
from ecocommit.interpreter import OpenAICompatibleIntentProvider
from ecocommit.validator import FidelityValidator


def _is_transient_provider_error(row: dict) -> bool:
    if row.get("error_kind") == "transient_provider_error":
        return True

    provider_trace = row.get("provider_trace")
    transient_provider_interruption = any(
        isinstance(item, dict)
        and item.get("outcome") == "provider_error"
        and item.get("transient") is True
        for item in provider_trace
    ) if isinstance(provider_trace, list) else False

    # A transient provider interruption does not become semantic evidence merely
    # because it happened while correcting a schema-invalid candidate. Likewise,
    # if transient provider retries consumed the bounded request budget before the
    # first schema correction could run, that row did not receive the candidate's
    # promised correction opportunity and must remain resumable infrastructure.
    if transient_provider_interruption:
        if row.get("error_kind") == "candidate_contract_correction_interrupted":
            return True
        if (
            row.get("error_kind") == "candidate_contract_error"
            and row.get("correction_attempted") is False
        ):
            return True

    # Candidate 3 starts a fresh manifest and therefore has no reason to trust
    # legacy free-form error text. Only typed error fields plus a redacted,
    # structured transient trace can make a row resumable.
    return False


def _load_resume(
    path: Path | None,
    selected_by_id: dict[str, object],
    manifest: dict,
    validator: FidelityValidator,
) -> list[dict]:
    if path is None or not path.exists():
        return []

    files = sorted(path.rglob("*.json")) if path.is_dir() else [path]
    if not files:
        return []

    by_id: dict[str, dict] = {}
    for candidate in files:
        try:
            payload = load_evidence_object(candidate)
        except ValueError as exc:
            raise ValueError(f"invalid resume artifact: {candidate.name}") from exc
        verify_manifest(payload.get("manifest", {}), manifest)
        for row in payload.get("cases", []):
            case_id = row.get("id")
            gold = selected_by_id.get(case_id)
            if gold is None:
                raise ValueError(f"unexpected case in resume artifact: {case_id}")
            verified = verify_row(row, gold, manifest, validator)
            if _is_transient_provider_error(verified):
                continue
            previous = by_id.get(case_id)
            if previous is not None and previous.get("row_sha256") != verified.get("row_sha256"):
                raise ValueError(f"conflicting resume rows for {case_id}")
            by_id[case_id] = verified
    return list(by_id.values())


def _write_partial(
    output: Path,
    *,
    base_url: str,
    model: str,
    start: int,
    end: int,
    rows: list[dict],
    frozen_index_by_id: dict[str, int],
    manifest: dict,
    infrastructure_error: dict | None = None,
) -> None:
    completed_indices = [frozen_index_by_id[r["id"]] for r in rows if r.get("id") in frozen_index_by_id]
    payload = {
        "evidence_schema_version": manifest["evidence_schema_version"],
        "manifest": manifest,
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
    args = parser.parse_args()

    if not args.model:
        raise SystemExit("ECOCOMMIT_LLM_MODEL (or --model) is required")
    api_key = os.getenv("ECOCOMMIT_LLM_API_KEY")
    if not api_key:
        raise SystemExit("ECOCOMMIT_LLM_API_KEY is required; command-line credentials are not accepted")

    frozen = _clear_cases() + _ambiguous_cases()
    if not (0 <= args.start < args.end <= len(frozen)):
        raise SystemExit(f"invalid shard bounds {args.start}:{args.end} for {len(frozen)} frozen cases")

    # CI intentionally fails fast on provider quota/capacity errors. A transient
    # provider failure is retried later as its own immutable case rather than
    # sleeping for many minutes while blocking every case behind it. This changes
    # only execution scheduling; the frozen case, model prompt and scoring stay intact.
    max_attempts = max(1, int(os.getenv("ECOCOMMIT_LLM_CASE_MAX_ATTEMPTS", "3")))
    max_retry_delay = max(0.0, float(os.getenv("ECOCOMMIT_LLM_CASE_MAX_RETRY_DELAY", "15")))
    provider = OpenAICompatibleIntentProvider(
        args.base_url,
        api_key,
        args.model,
        timeout=60.0,
        max_attempts=max_attempts,
        max_retry_delay=max_retry_delay,
    )
    validator = FidelityValidator()
    manifest = build_manifest(frozen, provider)
    from checkpoint_a_candidate5 import verify_registration
    verify_registration(manifest)
    selected = frozen[args.start:args.end]
    selected_by_id = {gold.case_id: gold for gold in selected}
    frozen_index_by_id = {gold.case_id: i for i, gold in enumerate(frozen)}
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    resume_path = Path(args.resume) if args.resume else None
    rows = _load_resume(resume_path, selected_by_id, manifest, validator)
    completed_ids = {row["id"] for row in rows if row.get("id")}

    _write_partial(
        output,
        base_url=args.base_url,
        model=args.model,
        start=args.start,
        end=args.end,
        rows=rows,
        frozen_index_by_id=frozen_index_by_id,
        manifest=manifest,
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
                manifest=manifest,
                infrastructure_error={
                    "case_id": gold.case_id,
                    "kind": row.get("error_kind"),
                    "code": row.get("error_code"),
                    "message": row.get("error"),
                    "provider_trace": row.get("provider_trace", []),
                },
            )
            print(json.dumps({"deferred": gold.case_id, "reason": "transient_provider_error"}), flush=True)
            return 75

        rows.append(bind_row(row, gold, manifest))
        completed_ids.add(gold.case_id)
        _write_partial(
            output,
            base_url=args.base_url,
            model=args.model,
            start=args.start,
            end=args.end,
            rows=rows,
            frozen_index_by_id=frozen_index_by_id,
            manifest=manifest,
        )
        print(json.dumps({"completed": gold.case_id, "passed": row.get("passed", False)}), flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
