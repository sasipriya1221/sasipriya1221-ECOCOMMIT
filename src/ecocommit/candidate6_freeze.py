from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .candidate6 import PROVIDER_POLICY, SYSTEM_PROMPT
from .semantic_ir import SemanticIR


FROZEN_ARTIFACTS = (
    "src/ecocommit/semantic_ir.py",
    "src/ecocommit/semantic_validation.py",
    "src/ecocommit/semantic_compiler.py",
    "src/ecocommit/candidate6.py",
    "src/ecocommit/candidate6_provider.py",
    "src/ecocommit/candidate6_evaluator.py",
    "src/ecocommit/qualification.py",
    "scripts/candidate6_qualify.py",
    "tests/test_candidate6_semantics.py",
    "data/candidate6/development.json",
    "data/candidate6/development_gold.json",
    "data/candidate6/holdout.json",
    "data/candidate6/holdout_gold.json",
    "data/candidate6/holdout_protocol.json",
)


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_sha256(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def schema_sha256() -> str:
    return canonical_sha256(SemanticIR.model_json_schema())


def prompt_sha256() -> str:
    return hashlib.sha256(SYSTEM_PROMPT.encode("utf-8")).hexdigest()


def provider_policy_sha256() -> str:
    return canonical_sha256(PROVIDER_POLICY)


def build_bindings(root: Path) -> dict[str, Any]:
    return {
        "artifact_sha256": {rel: file_sha256(root / rel) for rel in FROZEN_ARTIFACTS},
        "semantic_ir_schema_sha256": schema_sha256(),
        "parser_prompt_sha256": prompt_sha256(),
        "provider_policy_sha256": provider_policy_sha256(),
    }


def verify_freeze_receipt(root: Path, receipt: dict[str, Any]) -> None:
    if receipt.get("candidate") != "A-CANDIDATE-6":
        raise ValueError("freeze receipt candidate mismatch")
    if receipt.get("freeze_state") != "IMPLEMENTATION_FROZEN_BEFORE_HOLDOUT":
        raise ValueError("Candidate-6 implementation is not frozen")
    if receipt.get("holdout_provider_calls_before_freeze") != 0:
        raise ValueError("holdout provider calls occurred before freeze")
    if receipt.get("official_benchmark_calls_before_freeze") != 0:
        raise ValueError("official benchmark calls occurred before freeze")
    if receipt.get("holdout_qualification_executions_before_freeze") != 0:
        raise ValueError("holdout qualification was executed before freeze")
    expected = build_bindings(root)
    for key, value in expected.items():
        if receipt.get(key) != value:
            raise ValueError(f"freeze binding mismatch: {key}")
    unsigned = {k: v for k, v in receipt.items() if k != "freeze_receipt_sha256"}
    if receipt.get("freeze_receipt_sha256") != canonical_sha256(unsigned):
        raise ValueError("freeze receipt digest mismatch")
