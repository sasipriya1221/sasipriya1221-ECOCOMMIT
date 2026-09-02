from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest
from pydantic import ValidationError

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import checkpoint_a_protocol
from checkpoint_a_aggregate import compute_gate, main as aggregate_main
from checkpoint_a_constants import CRITERIA, FROZEN_DATASET_SHA256
from checkpoint_a_live import _ambiguous_cases, _clear_cases, _evaluate_one, semantic_case_pass
from checkpoint_a_protocol import (
    bind_row,
    build_manifest,
    canonical_sha256,
    dataset_sha256,
    load_evidence_object,
    verify_manifest,
    verify_row,
)
from checkpoint_a_shard import _is_transient_provider_error, _load_resume
from ecocommit.contracts import EconomicClause, EconomicIntentContract, Provenance, SourceSpan
from ecocommit.checkpoint_a_evidence import CheckpointAEvidenceReceipt, CheckpointAMetrics
from ecocommit.interpreter import (
    CandidateContractError,
    OpenAICompatibleIntentProvider,
    ProviderRequestError,
)
from ecocommit.validator import FidelityValidator


def _provider() -> OpenAICompatibleIntentProvider:
    return OpenAICompatibleIntentProvider(
        "https://api.groq.com/openai/v1",
        "not-used",
        "qwen/qwen3.6-27b",
        reasoning_effort="none",
        max_completion_tokens=1024,
        use_json_schema=False,
        max_attempts=2,
        max_retry_delay=15,
    )


def _passing_row(gold, manifest):
    clauses = []
    for index, requirement in enumerate(gold.required):
        start = gold.instruction.index(requirement.source_text)
        clauses.append(EconomicClause(
            clause_id=f"c{index}",
            clause_type=requirement.clause_type,
            normalized_value=requirement.source_text,
            source_span=SourceSpan(
                text=requirement.source_text,
                start=start,
                end=start + len(requirement.source_text),
            ),
            provenance=Provenance.EXPLICIT_USER,
            materiality=1.0,
            confidence=1.0,
            negated=bool(requirement.negated),
        ))
    contract = EconomicIntentContract(instruction=gold.instruction, clauses=clauses)
    passed, detail = semantic_case_pass(contract, gold, FidelityValidator())
    assert passed
    return bind_row({
        "id": gold.case_id,
        "instruction": gold.instruction,
        "passed": passed,
        "detail": detail,
        "contract": contract.model_dump(mode="json"),
        "provider_trace": [{"attempt": 1, "candidate_sha256": "a" * 64, "outcome": "accepted"}],
    }, gold, manifest)


def _terminal_row(gold, manifest, code: str):
    return bind_row({
        "id": gold.case_id,
        "instruction": gold.instruction,
        "passed": False,
        "error_kind": "candidate_contract_error",
        "error_code": code,
        "error": "candidate contract invalid after bounded correction",
        "provider_trace": [],
    }, gold, manifest)


def test_frozen_dataset_and_threshold_digests_are_locked():
    frozen = _clear_cases() + _ambiguous_cases()

    assert len(frozen) == 80
    assert dataset_sha256(frozen) == FROZEN_DATASET_SHA256
    assert CRITERIA == {
        "case_pass_rate_min": 0.90,
        "selective_semantic_reliability_min": 0.95,
        "autonomous_coverage_min": 0.55,
        "ambiguous_clarification_accuracy_min": 0.80,
    }


def test_manifest_and_semantics_are_recomputed_from_bound_evidence():
    frozen = _clear_cases() + _ambiguous_cases()
    manifest = build_manifest(frozen, _provider())
    gold = frozen[0]
    row = _passing_row(gold, manifest)

    verify_manifest(manifest, deepcopy(manifest))
    assert len(manifest["runner_sha256"]) == 64
    assert verify_row(row, gold, manifest, FidelityValidator()) == row

    tampered = deepcopy(row)
    tampered["detail"]["validator_status"] = "REJECTED"
    tampered["row_sha256"] = row["row_sha256"]
    with pytest.raises(ValueError, match="row digest mismatch"):
        verify_row(tampered, gold, manifest, FidelityValidator())


def test_manifest_mismatch_is_rejected():
    frozen = _clear_cases() + _ambiguous_cases()
    expected = build_manifest(frozen, _provider())
    supplied = deepcopy(expected)
    supplied["provider"]["model"] = "different-model"

    with pytest.raises(ValueError, match="manifest mismatch"):
        verify_manifest(supplied, expected)

    supplied = deepcopy(expected)
    supplied["runner_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="manifest mismatch"):
        verify_manifest(supplied, expected)


def test_manifest_directly_hashes_candidate_runtime_and_evidence_code(monkeypatch):
    captured: list[set[str]] = []
    original = checkpoint_a_protocol._files_sha256

    def capture(paths):
        paths = tuple(paths)
        captured.append({
            path.resolve().relative_to(checkpoint_a_protocol.ROOT).as_posix()
            for path in paths
        })
        return original(paths)

    monkeypatch.setattr(checkpoint_a_protocol, "_files_sha256", capture)
    build_manifest(_clear_cases() + _ambiguous_cases(), _provider())

    required_runtime = {
        "scripts/checkpoint_a_protocol.py",
        "scripts/checkpoint_a_shard.py",
        "scripts/checkpoint_a_aggregate.py",
        "src/ecocommit/_canonical.py",
        "src/ecocommit/checkpoint_a_evidence.py",
        "src/ecocommit/interpreter.py",
    }
    assert any(required_runtime <= group for group in captured)


@pytest.mark.parametrize("raw", [
    '{"manifest":{},"manifest":{},"cases":[]}',
    '{"manifest":{},"cases":[],"score":NaN}',
    '{"manifest":{},"cases":[],"text":"\\ud800"}',
    '[{"manifest":{},"cases":[]}]',
])
def test_a_evidence_loader_rejects_non_strict_or_non_object_json(tmp_path, raw):
    artifact = tmp_path / "attempt.json"
    artifact.write_text(raw, encoding="utf-8")

    with pytest.raises(ValueError, match="Checkpoint A evidence"):
        load_evidence_object(artifact)


def test_a_evidence_hashes_forbid_non_finite_json_numbers():
    with pytest.raises(ValueError):
        canonical_sha256({"metric": float("nan")})


def test_resume_rejects_duplicate_key_artifact_before_manifest_verification(tmp_path):
    frozen = _clear_cases() + _ambiguous_cases()
    manifest = build_manifest(frozen, _provider())
    gold = frozen[0]
    artifact = tmp_path / "attempt.json"
    artifact.write_text(
        '{"manifest":{},"manifest":{},"cases":[]}',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="invalid resume artifact"):
        _load_resume(
            artifact,
            {gold.case_id: gold},
            manifest,
            FidelityValidator(),
        )


def test_resume_accepts_identical_duplicates_but_rejects_conflicts(tmp_path):
    frozen = _clear_cases() + _ambiguous_cases()
    manifest = build_manifest(frozen, _provider())
    gold = frozen[0]
    first = _terminal_row(gold, manifest, "MISSING_MATERIALITY")
    duplicate = deepcopy(first)

    (tmp_path / "attempt-1.json").write_text(json.dumps({"manifest": manifest, "cases": [first]}), encoding="utf-8")
    (tmp_path / "attempt-2.json").write_text(json.dumps({"manifest": manifest, "cases": [duplicate]}), encoding="utf-8")
    rows = _load_resume(tmp_path, {gold.case_id: gold}, manifest, FidelityValidator())
    assert rows == [first]

    conflict = _terminal_row(gold, manifest, "MISSING_CLAUSES")
    (tmp_path / "attempt-3.json").write_text(json.dumps({"manifest": manifest, "cases": [conflict]}), encoding="utf-8")
    with pytest.raises(ValueError, match="conflicting resume rows"):
        _load_resume(tmp_path, {gold.case_id: gold}, manifest, FidelityValidator())


def test_aggregate_rejects_conflicting_duplicate_attempts(tmp_path, monkeypatch):
    frozen = _clear_cases() + _ambiguous_cases()
    manifest = build_manifest(frozen, _provider())
    gold = frozen[0]
    first = _terminal_row(gold, manifest, "MISSING_MATERIALITY")
    conflict = _terminal_row(gold, manifest, "MISSING_CLAUSES")
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "attempt-1.json").write_text(
        json.dumps({"manifest": manifest, "cases": [first]}), encoding="utf-8"
    )
    (input_dir / "attempt-2.json").write_text(
        json.dumps({"manifest": manifest, "cases": [conflict]}), encoding="utf-8"
    )
    monkeypatch.setattr(sys, "argv", [
        "checkpoint_a_aggregate.py",
        "--input-dir", str(input_dir),
        "--output", str(tmp_path / "result.json"),
    ])

    with pytest.raises(ValueError, match="conflicting duplicate rows"):
        aggregate_main()


def test_exact_frozen_90_percent_boundary_passes_but_one_less_fails():
    frozen = _clear_cases() + _ambiguous_cases()
    by_id = {}
    for index, gold in enumerate(frozen[:50]):
        passed = index < 48
        by_id[gold.case_id] = {
            "id": gold.case_id,
            "passed": passed,
            "detail": {"validator_status": "VALIDATED"} if passed else None,
        }
    for index, gold in enumerate(frozen[50:]):
        passed = index < 24
        by_id[gold.case_id] = {
            "id": gold.case_id,
            "passed": passed,
            "detail": {"validator_status": "CLARIFICATION_REQUIRED"} if passed else None,
        }

    _, missing, metrics, full_run, passed = compute_gate(frozen, by_id)
    assert not missing
    assert full_run
    assert metrics["case_pass_rate"] == 0.90
    assert metrics["autonomous_coverage"] == 0.60
    assert metrics["selective_semantic_reliability"] == 1.0
    assert metrics["ambiguous_clarification_accuracy"] == 0.80
    assert passed

    below = deepcopy(by_id)
    below[frozen[0].case_id]["passed"] = False
    assert compute_gate(frozen, below)[-1] is False


class _FailingProvider:
    def __init__(self, trace):
        self.trace = trace

    def interpret_with_metadata(self, instruction):
        raise ProviderRequestError(
            "HTTP_429",
            attempts=2,
            transient=True,
            provider_trace=self.trace,
        )


class _SchemaFailingProvider:
    def __init__(self, correction_attempted):
        self.correction_attempted = correction_attempted

    def interpret_with_metadata(self, instruction):
        raise CandidateContractError(
            [{"location": "clauses.0.confidence", "code": "missing"}],
            [{
                "attempt": 2,
                "outcome": "schema_invalid",
                "issues": [{"location": "clauses.0.confidence", "code": "missing"}],
            }],
            correction_attempted=self.correction_attempted,
        )


@pytest.mark.parametrize(
    ("correction_attempted", "expected_code"),
    [
        (False, "SCHEMA_INVALID_BEFORE_CORRECTION"),
        (True, "SCHEMA_INVALID_AFTER_CORRECTION"),
    ],
)
def test_terminal_schema_evidence_distinguishes_whether_correction_ran(
    correction_attempted,
    expected_code,
):
    gold = (_clear_cases() + _ambiguous_cases())[0]
    row = _evaluate_one(
        gold,
        _SchemaFailingProvider(correction_attempted),
        FidelityValidator(),
    )

    assert row["error_kind"] == "candidate_contract_error"
    assert row["error_code"] == expected_code
    assert row["correction_attempted"] is correction_attempted


def test_transient_correction_interruption_is_resumable_provider_deferral():
    gold = (_clear_cases() + _ambiguous_cases())[0]
    mixed = _evaluate_one(gold, _FailingProvider([
        {"attempt": 1, "outcome": "schema_invalid", "issues": [{"location": "clauses", "code": "missing"}]},
        {"attempt": 2, "outcome": "provider_error", "code": "HTTP_429", "transient": True},
    ]), FidelityValidator())
    pure = _evaluate_one(gold, _FailingProvider([
        {"attempt": 2, "outcome": "provider_error", "code": "HTTP_429", "transient": True},
    ]), FidelityValidator())

    assert mixed["error_kind"] == "candidate_contract_correction_interrupted"
    assert mixed["error_code"] == "CORRECTION_PROVIDER_ERROR"
    assert _is_transient_provider_error(mixed)
    assert pure["error_kind"] == "transient_provider_error"
    assert pure["error_code"] == "HTTP_429"
    assert _is_transient_provider_error(pure)


def test_schema_failure_without_correction_is_resumable_after_transient_retry():
    gold = (_clear_cases() + _ambiguous_cases())[0]
    provider_trace = [
        {"attempt": 1, "outcome": "provider_error", "code": "HTTP_429", "transient": True},
        {"attempt": 2, "outcome": "schema_invalid", "issues": [{"location": "clauses", "code": "missing"}]},
    ]

    class _RetryThenSchemaProvider:
        def interpret_with_metadata(self, instruction):
            raise CandidateContractError(
                [{"location": "clauses", "code": "missing"}],
                provider_trace,
                correction_attempted=False,
            )

    row = _evaluate_one(gold, _RetryThenSchemaProvider(), FidelityValidator())

    assert row["error_kind"] == "candidate_contract_error"
    assert row["error_code"] == "SCHEMA_INVALID_BEFORE_CORRECTION"
    assert _is_transient_provider_error(row)


def test_completed_correction_failure_remains_terminal_after_transient_retry():
    row = {
        "error_kind": "candidate_contract_error",
        "correction_attempted": True,
        "error": "candidate contract invalid after bounded correction",
        "provider_trace": [
            {"attempt": 1, "outcome": "provider_error", "code": "HTTP_429", "transient": True},
            {"attempt": 2, "outcome": "schema_invalid"},
            {"attempt": 3, "outcome": "schema_invalid"},
        ],
    }

    assert not _is_transient_provider_error(row)


def test_nontransient_correction_interruption_remains_terminal():
    row = {
        "error_kind": "candidate_contract_correction_interrupted",
        "error_code": "CORRECTION_PROVIDER_ERROR",
        "error": "provider HTTP_400 after 2 attempt(s)",
        "provider_trace": [
            {"attempt": 1, "outcome": "schema_invalid"},
            {"attempt": 2, "outcome": "provider_error", "code": "HTTP_400", "transient": False},
        ],
    }

    assert not _is_transient_provider_error(row)


def test_unstructured_provider_error_text_cannot_forge_a_deferral():
    row = {
        "error_kind": "candidate_contract_error",
        "correction_attempted": False,
        "error": "provider HTTP_429 after 2 attempt(s)",
        "provider_trace": [],
    }

    assert not _is_transient_provider_error(row)


def test_candidate_3_workflow_is_fresh_immutable_and_secret_scoped():
    workflow = (Path(__file__).resolve().parents[1] / ".github" / "workflows" / "checkpoint-a-live.yml").read_text(
        encoding="utf-8"
    )

    assert "checkpoint-a-candidate-3-case-${{ matrix.case }}-attempt-*" in workflow
    assert "checkpoint-a-candidate-3-results-attempt-${{ github.run_attempt }}" in workflow
    assert "checkpoint_a_candidate_3_results_attempt_${GITHUB_RUN_ATTEMPT}.json" in workflow
    assert "checkpoint-a-candidate-2-case-${{ matrix.case }}-attempt-*" not in workflow
    assert "checkpoint_a_candidate_2_results_attempt" not in workflow
    assert "checkpoint-a-case-${{ matrix.case }}" not in workflow
    assert "overwrite: true" not in workflow
    assert workflow.count("ECOCOMMIT_LLM_API_KEY: ${{ secrets.ECOCOMMIT_GROQ_API_KEY }}") == 2
    assert "actions/checkout@v4" not in workflow
    assert "actions/setup-python@v5" not in workflow
    assert "actions/download-artifact@v4" not in workflow
    assert "actions/upload-artifact@v4" not in workflow
    assert workflow.count("persist-credentials: false") == 3


def test_typed_a_receipt_enforces_frozen_candidate_dataset_and_thresholds():
    values = {
        "verification_mode": "FROZEN_AGGREGATE",
        "evidence_reference": "github-actions://owner/repo/runs/1/candidate-3",
        "aggregate_sha256": "a" * 64,
        "manifest_sha256": "b" * 64,
        "source_revision": "c" * 40,
        "candidate_version": "A-CANDIDATE-3",
        "dataset_sha256": FROZEN_DATASET_SHA256,
        "total_cases": 80,
        "full_frozen_gate_run": True,
        "gate_passed": True,
        "metrics": CheckpointAMetrics(
            passed_cases=72,
            case_pass_rate=0.90,
            autonomous_coverage=0.55,
            selective_semantic_reliability=0.95,
            ambiguous_clarification_accuracy=0.80,
        ),
    }
    receipt = CheckpointAEvidenceReceipt(**values)
    assert receipt.candidate_version == "A-CANDIDATE-3"

    with pytest.raises(ValidationError, match="case-pass threshold"):
        CheckpointAEvidenceReceipt(**{
            **values,
            "metrics": values["metrics"].model_copy(update={"passed_cases": 71}),
        })
    with pytest.raises(ValidationError, match="dataset digest is not frozen"):
        CheckpointAEvidenceReceipt(**{**values, "dataset_sha256": "d" * 64})
    with pytest.raises(ValidationError, match="does not match passed cases"):
        CheckpointAEvidenceReceipt(**{
            **values,
            "metrics": values["metrics"].model_copy(
                update={"passed_cases": 73, "case_pass_rate": 0.90}
            ),
        })


def test_candidate_1_failure_manifest_is_mathematically_closed_and_classified():
    path = Path(__file__).resolve().parents[1] / "evidence" / "checkpoint-a-candidate-1-failure.json"
    failure = json.loads(path.read_text(encoding="utf-8"))
    attempt = failure["attempt_15"]
    terminal_ids = {
        case_id
        for failure_class in failure["terminal_failure_classes"]
        for case_id in failure_class["case_ids"]
    }
    deferred_ids = set(failure["provider_deferrals"]["case_ids"])

    assert failure["status"] == "MATHEMATICALLY_FAILED"
    assert attempt["semantic_passes"] + attempt["terminal_candidate_contract_failures"] == attempt["terminal_rows"]
    assert attempt["terminal_rows"] + attempt["provider_deferred"] == 80
    assert attempt["maximum_possible_passes"] == attempt["semantic_passes"] + attempt["provider_deferred"]
    assert attempt["maximum_possible_case_pass_rate"] == 69 / 80
    assert attempt["maximum_possible_case_pass_rate"] < failure["frozen_gate"]["case_pass_rate_min"]
    assert len(terminal_ids) == 11
    assert len(deferred_ids) == 48
    assert terminal_ids.isdisjoint(deferred_ids)
    assert failure["provider_deferrals"]["all_latest_failed_job_logs_individually_verified"] is True
