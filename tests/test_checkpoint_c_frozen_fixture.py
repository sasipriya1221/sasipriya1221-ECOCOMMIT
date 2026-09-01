from __future__ import annotations

from hashlib import sha256
from pathlib import Path

from ecocommit.checkpoint_c_runner import load_plan, load_suite, run_benchmark


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "checkpoint_c"
EXPECTED_SUITE_SHA256 = "4c6d304d3850cb493519bda9c5943f4774c861b522ff8e837a9a8c23161f9392"
EXPECTED_PLAN_SHA256 = "416e13b9a7cbf3097c4a10662290c2b12be20c3b41df46a2e1a9f80c8a44fe43"
EXPECTED_DYNAMIC_WORKFLOW_SHA256 = (
    "cdf0c9dd825bd8739959f4526890afb4fe333929d66b30f04ecea88e6fe2b05c"
)


def _file_sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def test_checked_in_fixture_plan_and_suite_have_literal_frozen_digests():
    suite = load_suite(FIXTURE_ROOT / "frozen_suite.json")
    plan = load_plan(FIXTURE_ROOT / "frozen_plan.json")

    assert suite.canonical_hash() == EXPECTED_SUITE_SHA256
    assert plan.suite_sha256 == EXPECTED_SUITE_SHA256
    assert plan.canonical_hash() == EXPECTED_PLAN_SHA256
    assert plan.baselines[3].canonical_hash() == EXPECTED_DYNAMIC_WORKFLOW_SHA256
    assert suite.eligible_for_final_claims is False
    assert plan.eligible_for_final_claims is False


def test_checked_in_prompt_and_guardrail_files_match_registered_digests():
    plan = load_plan(FIXTURE_ROOT / "frozen_plan.json")
    naive, guarded = plan.baselines[:2]

    assert _file_sha256(FIXTURE_ROOT / "naive-prompt.txt") == naive.prompt_protocol_sha256
    assert _file_sha256(FIXTURE_ROOT / "guarded-prompt.txt") == guarded.prompt_protocol_sha256
    assert _file_sha256(FIXTURE_ROOT / "guardrail.txt") == guarded.guardrail_protocol_sha256


def test_checked_in_fixture_run_remains_structural_and_preliminary_only():
    suite = load_suite(FIXTURE_ROOT / "frozen_suite.json")
    plan = load_plan(FIXTURE_ROOT / "frozen_plan.json")
    artifact = run_benchmark(
        plan,
        suite,
        code_revision="fixture-only",
        working_tree_dirty=False,
    )

    assert artifact.final_comparison_numbers_published is False
    assert artifact.prerequisites_satisfied is False
    assert artifact.provenance.synthetic_fixture_inputs_used is True
    assert artifact.provenance.live_checkpoint_a_outputs_used is False
