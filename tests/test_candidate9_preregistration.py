from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ecocommit.candidate7_flat import FactBatch, RelationBatch
from ecocommit.candidate7_relation_checklist import Pass2DecisionBatch
from ecocommit.candidate8_provider import PASS1_SYSTEM_PROMPT_C8, PASS2_SYSTEM_PROMPT


ROOT = Path(__file__).resolve().parents[1]
PREREG = ROOT / "evidence" / "candidate9-development-preregistration.json"


def _file_sha(path: str) -> str:
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


def _text_sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _schema_sha(model: type) -> str:
    payload = json.dumps(model.model_json_schema(), sort_keys=True, separators=(",", ":"))
    return _text_sha(payload)


def test_candidate9_preregistration_binds_frozen_boundary_and_visible_inputs():
    doc = json.loads(PREREG.read_text(encoding="utf-8"))
    assert doc["status"] == "PREREGISTERED"
    assert doc["development_branch"] == "candidate9-development"
    assert doc["base_repository_sha"] == "b32de589352b78fdce206e6ac555567eb3a873be"
    assert doc["frozen_semantic_parent"] == {
        "candidate": "A-CANDIDATE-8",
        "source_sha": "850a7b5f1f21d7951cd4a9a840c0bebbb635d594",
        "terminal_checkpoint_a_status": "FAILED",
        "must_not_be_modified_or_rerun": True,
    }

    visible = doc["visible_corpora"]
    assert visible["development_dataset_sha256"] == _file_sha("data/candidate8-development/development.json")
    assert visible["development_gold_sha256"] == _file_sha("data/candidate8-development/development_gold.json")
    assert visible["regression_dataset_sha256"] == _file_sha("data/candidate8-development/regression.json")
    assert visible["regression_gold_sha256"] == _file_sha("data/candidate8-development/regression_gold.json")


def test_candidate9_preregistration_binds_prompts_schemas_and_strict_gates():
    doc = json.loads(PREREG.read_text(encoding="utf-8"))
    assert doc["prompts"]["pass1_sha256"] == _text_sha(PASS1_SYSTEM_PROMPT_C8)
    assert doc["prompts"]["pass2_sha256"] == _text_sha(PASS2_SYSTEM_PROMPT)
    assert doc["schemas"]["fact_batch_canonical_json_schema_sha256"] == _schema_sha(FactBatch)
    assert doc["schemas"]["pass2_decision_batch_canonical_json_schema_sha256"] == _schema_sha(Pass2DecisionBatch)
    assert doc["schemas"]["relation_batch_canonical_json_schema_sha256"] == _schema_sha(RelationBatch)

    assert doc["provider_configuration"] == {
        "provider": "Groq",
        "model": "qwen/qwen3.6-27b",
        "temperature": 0,
        "reasoning_effort": "none",
        "maximum_completion_tokens": 900,
        "maximum_attempts_per_pass": 2,
        "semantic_failure_retry": False,
    }
    assert doc["thresholds"] == {
        "case_pass_rate_minimum": 0.95,
        "selective_semantic_reliability_minimum": 0.97,
        "autonomous_coverage_minimum": 0.60,
        "ambiguous_clarification_accuracy_minimum": 0.90,
        "fail_open_errors_maximum": 0,
        "dropped_guards_maximum": 0,
        "dropped_exceptions_maximum": 0,
        "conservation_failures_maximum": 0,
        "unknown_to_authorized_errors_maximum": 0,
    }
    assert doc["iteration_policy"]["maximum_visible_development_iterations"] == 3
    assert "official Checkpoint-A" in " ".join(doc["evidence_boundary"]["forbidden"])
