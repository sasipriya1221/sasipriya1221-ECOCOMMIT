from __future__ import annotations

import json
import os
import subprocess
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterable

from checkpoint_a_constants import (
    CANDIDATE_VERSION,
    CRITERIA,
    EVIDENCE_SCHEMA_VERSION,
    FROZEN_DATASET_SHA256,
)
from checkpoint_a_live import GoldCase, semantic_case_pass
from ecocommit.contracts import EconomicIntentContract
from ecocommit.interpreter import OpenAICompatibleIntentProvider
from ecocommit.validator import FidelityValidator


ROOT = Path(__file__).resolve().parents[1]


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return sha256(_canonical_bytes(value)).hexdigest()


def frozen_case_payload(gold: GoldCase) -> dict[str, Any]:
    return {
        "id": gold.case_id,
        "instruction": gold.instruction,
        "expected_status": gold.expected_status.value,
        "required": [
            {
                "clause_type": requirement.clause_type.value,
                "source_text": requirement.source_text,
                "negated": requirement.negated,
            }
            for requirement in gold.required
        ],
        "require_exception": gold.require_exception,
        "require_dependency": gold.require_dependency,
    }


def dataset_sha256(frozen: Iterable[GoldCase]) -> str:
    return canonical_sha256([frozen_case_payload(gold) for gold in frozen])


def _files_sha256(paths: Iterable[Path]) -> str:
    entries = []
    for path in sorted(paths, key=lambda item: item.as_posix()):
        relative = path.resolve().relative_to(ROOT).as_posix()
        entries.append({"path": relative, "sha256": sha256(path.read_bytes()).hexdigest()})
    return canonical_sha256(entries)


def current_revision() -> str:
    github_sha = os.getenv("GITHUB_SHA", "").strip()
    if github_sha:
        return github_sha
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def build_manifest(
    frozen: list[GoldCase],
    provider: OpenAICompatibleIntentProvider,
) -> dict[str, Any]:
    actual_dataset_sha256 = dataset_sha256(frozen)
    if actual_dataset_sha256 != FROZEN_DATASET_SHA256:
        raise ValueError("frozen Checkpoint A dataset digest changed")

    prompt_payload = {
        "system_prompt": provider.SYSTEM_PROMPT,
        "compact_schema": provider.COMPACT_SCHEMA,
        "strict_json_schema": provider.STRICT_JSON_SCHEMA,
    }
    evaluator_files = [
        ROOT / "scripts" / "checkpoint_a_live.py",
        ROOT / "src" / "ecocommit" / "contracts.py",
        ROOT / "src" / "ecocommit" / "validator.py",
    ]
    runner_files = [
        ROOT / "scripts" / "checkpoint_a_constants.py",
        ROOT / "scripts" / "checkpoint_a_shard.py",
        ROOT / "scripts" / "checkpoint_a_aggregate.py",
    ]
    manifest: dict[str, Any] = {
        "evidence_schema_version": EVIDENCE_SCHEMA_VERSION,
        "candidate_version": CANDIDATE_VERSION,
        "source_revision": current_revision(),
        "workflow": {
            "run_id": os.getenv("GITHUB_RUN_ID") or None,
            "workflow_ref": os.getenv("GITHUB_WORKFLOW_REF") or None,
        },
        "dataset": {
            "count": len(frozen),
            "sha256": actual_dataset_sha256,
        },
        "prompt_sha256": canonical_sha256(prompt_payload),
        "contract_schema_sha256": canonical_sha256(provider.STRICT_JSON_SCHEMA),
        "evaluator_sha256": _files_sha256(evaluator_files),
        "runner_sha256": _files_sha256(runner_files),
        "criteria": deepcopy(CRITERIA),
        "criteria_sha256": canonical_sha256(CRITERIA),
        "provider": {
            "base_url": provider.base_url,
            "model": provider.model,
            "reasoning_effort": provider.reasoning_effort,
            "json_schema": provider.use_json_schema,
            "max_completion_tokens": provider.max_completion_tokens,
            "max_attempts": provider.max_attempts,
            "max_retry_delay_seconds": provider.max_retry_delay,
            "max_response_bytes": provider.max_response_bytes,
        },
    }
    manifest["manifest_sha256"] = canonical_sha256(manifest)
    return manifest


def verify_manifest(manifest: dict[str, Any], expected: dict[str, Any]) -> None:
    if manifest != expected:
        raise ValueError("Checkpoint A evidence manifest mismatch")
    claimed = manifest.get("manifest_sha256")
    unsigned = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    if claimed != canonical_sha256(unsigned):
        raise ValueError("Checkpoint A evidence manifest digest mismatch")


def bind_row(row: dict[str, Any], gold: GoldCase, manifest: dict[str, Any]) -> dict[str, Any]:
    bound = deepcopy(row)
    bound["manifest_sha256"] = manifest["manifest_sha256"]
    bound["case_sha256"] = canonical_sha256(frozen_case_payload(gold))
    contract = bound.get("contract")
    if contract is not None:
        bound["contract_sha256"] = canonical_sha256(contract)
    bound["row_sha256"] = canonical_sha256(bound)
    return bound


def verify_row(
    row: dict[str, Any],
    gold: GoldCase,
    manifest: dict[str, Any],
    validator: FidelityValidator,
) -> dict[str, Any]:
    if row.get("manifest_sha256") != manifest["manifest_sha256"]:
        raise ValueError(f"manifest mismatch for {gold.case_id}")
    if row.get("id") != gold.case_id or row.get("instruction") != gold.instruction:
        raise ValueError(f"case identity mismatch for {gold.case_id}")
    if row.get("case_sha256") != canonical_sha256(frozen_case_payload(gold)):
        raise ValueError(f"case digest mismatch for {gold.case_id}")

    claimed_row_sha256 = row.get("row_sha256")
    unsigned = {key: value for key, value in row.items() if key != "row_sha256"}
    if claimed_row_sha256 != canonical_sha256(unsigned):
        raise ValueError(f"row digest mismatch for {gold.case_id}")

    contract_payload = row.get("contract")
    detail = row.get("detail")
    if contract_payload is None:
        if detail is not None or row.get("passed") is not False or not row.get("error_kind"):
            raise ValueError(f"invalid terminal error row for {gold.case_id}")
        return deepcopy(row)

    if row.get("contract_sha256") != canonical_sha256(contract_payload):
        raise ValueError(f"contract digest mismatch for {gold.case_id}")
    contract = EconomicIntentContract.model_validate(contract_payload)
    recomputed_passed, recomputed_detail = semantic_case_pass(contract, gold, validator)
    if row.get("passed") != recomputed_passed or detail != recomputed_detail:
        raise ValueError(f"semantic recomputation mismatch for {gold.case_id}")
    if row.get("error_kind") or row.get("error"):
        raise ValueError(f"successful row carries an error for {gold.case_id}")
    return deepcopy(row)
