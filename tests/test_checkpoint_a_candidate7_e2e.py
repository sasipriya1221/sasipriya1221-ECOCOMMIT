from __future__ import annotations

import json
import sys
from dataclasses import dataclass

from ecocommit.checkpoint_a_evidence import (
    CANDIDATE7_CRITERIA_SHA256,
    CANDIDATE7_EVALUATOR_SHA256,
    FROZEN_A_DATASET_SHA256,
    CheckpointAEvidenceReceipt,
)
from ecocommit.checkpoint_b_integration import AtoBPolicyBridge
from ecocommit.checkpoint_status import GateReport, GateState
from ecocommit.contracts import (
    ClauseType,
    EconomicClause,
    EconomicIntentContract,
    Provenance,
    SourceSpan,
)
from scripts import checkpoint_a_candidate7 as runner
from scripts.candidate6_official_reachability import (
    OfficialCounts,
    OfficialThresholds,
    final_pass,
    reachable,
)


@dataclass(frozen=True)
class _Gold:
    case_id: str
    instruction: str


class _Contract:
    def model_dump(self, *, mode: str):
        assert mode == "json"
        return {"fixture": "offline-only"}


@dataclass(frozen=True)
class _Result:
    status: str
    contract: _Contract
    blocked_actions: tuple[str, ...] = ()
    error_code: str | None = None
    provider_trace: tuple[dict, ...] = ()


def _production_contract() -> EconomicIntentContract:
    instruction = "Buy widgets from merchant-1 for at most ₹50."

    def span(text: str) -> SourceSpan:
        start = instruction.index(text)
        return SourceSpan(text=text, start=start, end=start + len(text))

    return EconomicIntentContract(
        instruction=instruction,
        clauses=[
            EconomicClause(clause_id="product", clause_type=ClauseType.PRODUCT, normalized_value="widgets", source_span=span("widgets"), provenance=Provenance.EXPLICIT_USER, materiality=0.9, confidence=1.0),
            EconomicClause(clause_id="merchant", clause_type=ClauseType.COUNTERPARTY, normalized_value="merchant-1", source_span=span("merchant-1"), provenance=Provenance.EXPLICIT_USER, materiality=1.0, confidence=1.0),
            EconomicClause(clause_id="amount", clause_type=ClauseType.AMOUNT, normalized_value="maximum ₹50", source_span=span("₹50"), provenance=Provenance.EXPLICIT_USER, materiality=1.0, confidence=1.0),
        ],
    )


def test_c7_preregistration_runner_receipt_loads_into_b(monkeypatch, tmp_path):
    """Exercise the entire offline boundary without making a provider call."""
    frozen = [
        *[_Gold(f"C{i:03d}", f"clear-{i}") for i in range(1, 51)],
        *[_Gold(f"A{i:03d}", f"ambiguous-{i}") for i in range(1, 31)],
    ]
    source_revision = "9" * 40
    prereg = {
        "preregistration_sha256": "1" * 64,
        "supervisor_source_revision": source_revision,
        "frozen_dataset": {"sha256": FROZEN_A_DATASET_SHA256},
        "frozen_evaluator_sha256": CANDIDATE7_EVALUATOR_SHA256,
        "criteria_sha256": CANDIDATE7_CRITERIA_SHA256,
        "qualification": {"evidence_sha256": "2" * 64},
    }
    readiness = {
        "schema_version": "A.CANDIDATE7.PROVIDER.READINESS.1",
        "candidate": "A-CANDIDATE-7",
        "frozen_semantic_source_revision": runner.FROZEN_SOURCE,
        "preregistration_sha256": prereg["preregistration_sha256"],
        "healthy": True,
        "benchmark_cases_used": 0,
    }
    readiness["receipt_sha256"] = runner.canonical_sha256(readiness)

    paths = {}
    for name, value in (("prereg.json", prereg), ("binding.json", {}), ("summary.json", {}), ("readiness.json", readiness)):
        paths[name] = tmp_path / name
        paths[name].write_text(json.dumps(value), encoding="utf-8")

    def fake_runtime(_candidate):
        return {
            "_clear_cases": lambda: frozen[:50],
            "_ambiguous_cases": lambda: frozen[50:],
            "run_candidate7": lambda instruction, _provider: _Result("CLARIFICATION_REQUIRED" if instruction.startswith("ambiguous") else "COMPILED", _Contract()),
            "semantic_case_pass": lambda _contract, gold, _validator: (True, {"validator_status": "CLARIFICATION_REQUIRED" if gold.case_id.startswith("A") else "VALIDATED"}),
            "GroqCandidate7Provider": lambda _key: object(),
            "FidelityValidator": lambda: object(),
            "OfficialCounts": OfficialCounts,
            "OfficialThresholds": OfficialThresholds,
            "final_pass": final_pass,
            "reachable": reachable,
        }

    monkeypatch.setattr(runner, "runtime", fake_runtime)
    monkeypatch.setattr(runner, "verify_preregistration", lambda *_args: None)
    monkeypatch.setattr(runner, "supervisor_head", lambda: source_revision)
    monkeypatch.setenv("GITHUB_RUN_ATTEMPT", "1")
    monkeypatch.setenv("GITHUB_SHA", source_revision)
    monkeypatch.setenv("ECOCOMMIT_LLM_API_KEY", "offline-test-key")
    output = tmp_path / "official"
    evidence = "github-actions://example/ecocommit/runs/1/artifacts/checkpoint-a-candidate7-official"
    monkeypatch.setattr(sys, "argv", [
        "checkpoint_a_candidate7.py", "--candidate-root", str(tmp_path),
        "--preregistration", str(paths["prereg.json"]), "--binding", str(paths["binding.json"]),
        "--summary", str(paths["summary.json"]), "--provider-readiness", str(paths["readiness.json"]),
        "--output-dir", str(output), "--evidence-reference", evidence,
    ])

    assert runner.main() == 0
    receipt = CheckpointAEvidenceReceipt.model_validate_json((output / "checkpoint-a-pass-receipt.json").read_text(encoding="utf-8"))
    gate = GateReport("A", GateState.PASSED, evidence=evidence)
    admission = AtoBPolicyBridge().evaluate(_production_contract(), checkpoint_a_gate=gate, checkpoint_a_receipt=receipt)

    assert receipt.candidate_version == "A-CANDIDATE-7"
    assert receipt.metrics.passed_cases == 80
    assert admission.ready is True
    assert admission.checkpoint_a_manifest_sha256 == prereg["preregistration_sha256"]
