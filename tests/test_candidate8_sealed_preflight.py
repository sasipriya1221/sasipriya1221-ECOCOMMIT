from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "candidate8_sealed_preflight.py"
SPEC = importlib.util.spec_from_file_location("candidate8_sealed_preflight", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def _digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def test_generator_is_seeded_complete_and_non_persistent(tmp_path):
    cases, gold = MODULE.generate(bytes(range(32)))
    assert len(cases["cases"]) == len(gold["cases"]) >= 20
    assert {x["case_id"] for x in cases["cases"]} == {x["case_id"] for x in gold["cases"]}
    assert MODULE.REQUIRED_COVERAGE <= {tag for row in cases["cases"] for tag in row["feature_tags"]}
    assert not list(tmp_path.iterdir())


def test_generator_is_reproducible_for_validation_but_fresh_seed_changes_set():
    first = MODULE.generate(b"a" * 32)
    assert _digest(first) == _digest(MODULE.generate(b"a" * 32))
    assert _digest(first) != _digest(MODULE.generate(b"b" * 32))


def test_summary_schema_exposes_no_plaintext_case_or_gold_fields():
    schema = json.loads((ROOT / "spec/candidate8-sealed-preflight-summary.schema.json").read_text())
    forbidden = {"instruction", "cases", "gold", "rows", "seed"}
    assert forbidden.isdisjoint(schema["properties"])
    assert schema["properties"]["status"]["enum"] == ["PASS", "FAIL", "PROVIDER_LIMITED"]


def test_preflight_workflow_is_manual_and_separates_aggregate_from_sealed_artifact():
    text = (ROOT / ".github/workflows/candidate8-sealed-preflight.yml").read_text()
    assert "workflow_dispatch:" in text
    assert "ECOCOMMIT_GROQ_API_KEY" in text
    assert "candidate8-sealed-preflight-aggregate-" in text
    assert "candidate8-sealed-preflight-restricted-" in text
    assert "cat artifacts" not in text
    assert "850a7b5f1f21d7951cd4a9a840c0bebbb635d594" in text
