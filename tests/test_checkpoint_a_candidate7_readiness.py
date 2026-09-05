from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest
from pydantic import ValidationError

from ecocommit.checkpoint_a_evidence import CANDIDATE7_CRITERIA_SHA256, CANDIDATE7_EVALUATOR_SHA256, CheckpointAEvidenceReceipt
from scripts.checkpoint_a_candidate7_prereg import FROZEN_SOURCE, canonical_sha256, verify_qualification


def qualification():
    binding = {"candidate":"A-CANDIDATE-7","candidate_sha":FROZEN_SOURCE,"qualification_mode":"candidate7-d003-d009","qualification_harness":"scripts/candidate7_pass2_qualification.py","official_checkpoint_a_cases_used":False,"holdout_opened":False}
    binding["binding_sha256"] = canonical_sha256(binding)
    case = {"accepted":5,"correct_results":5,"old_failure_signature_matches":0}
    return binding, {"qualification_status":"PASS","provider_calls_recorded":10,"stopped_after_first_http_429":False,"cases":{"D003":case,"D009":case}}


def receipt_values():
    return {"verification_mode":"FROZEN_AGGREGATE","evidence_reference":"github-actions://evidence","aggregate_sha256":"a"*64,"manifest_sha256":"b"*64,"source_revision":"c"*40,"candidate_version":"A-CANDIDATE-7","dataset_sha256":"968be3ed3a438a3a28a3402fa65c90a45cb564ed1adad2e6e51d852e24c5bb8b","total_cases":80,"full_frozen_gate_run":True,"gate_passed":True,"metrics":{"passed_cases":72,"case_pass_rate":.9,"autonomous_coverage":.55,"selective_semantic_reliability":.95,"ambiguous_clarification_accuracy":.8},"candidate_source_revision":FROZEN_SOURCE,"qualification_status":"PASS","qualification_evidence_sha256":"d"*64,"qualification_source_revision":FROZEN_SOURCE,"preregistration_sha256":"e"*64,"evaluator_sha256":CANDIDATE7_EVALUATOR_SHA256,"criteria_sha256":CANDIDATE7_CRITERIA_SHA256,"artifact_namespace":"checkpoint-a-candidate-7","semantic_score_retry_count":0}


def test_c7_receipt_accepts_only_complete_frozen_binding():
    assert CheckpointAEvidenceReceipt(**receipt_values()).candidate_version == "A-CANDIDATE-7"


@pytest.mark.parametrize("field,value", [("candidate_source_revision","2"*40),("qualification_source_revision","2"*40),("qualification_status",None),("dataset_sha256","2"*64),("evaluator_sha256","2"*64),("criteria_sha256","2"*64),("artifact_namespace","wrong"),("semantic_score_retry_count",1)])
def test_c7_receipt_rejects_protocol_mismatch(field, value):
    with pytest.raises(ValidationError):
        CheckpointAEvidenceReceipt(**{**receipt_values(),field:value})


def test_qualification_pass_is_required_and_source_bound():
    binding, summary = qualification()
    assert len(verify_qualification(binding, summary)) == 64
    bad = deepcopy(binding); bad["candidate_sha"] = "2"*40; bad["binding_sha256"] = canonical_sha256({k:v for k,v in bad.items() if k != "binding_sha256"})
    with pytest.raises(ValueError, match="binding mismatch"):
        verify_qualification(bad, summary)
    failed = deepcopy(summary); failed["qualification_status"] = "FAIL"
    with pytest.raises(ValueError, match="PASS evidence"):
        verify_qualification(binding, failed)


def test_historical_candidate5_receipt_remains_compatible():
    old = receipt_values()
    for key in ("candidate_source_revision","qualification_status","qualification_evidence_sha256","qualification_source_revision","preregistration_sha256","evaluator_sha256","criteria_sha256","artifact_namespace","semantic_score_retry_count"):
        old.pop(key)
    old["candidate_version"] = "A-CANDIDATE-5"
    assert CheckpointAEvidenceReceipt(**old).candidate_version == "A-CANDIDATE-5"


def test_candidate7_official_runner_has_no_semantic_score_retry_hook():
    source = (Path(__file__).parents[1] / "scripts/checkpoint_a_candidate7_prereg.py").read_text()
    assert '"semantic_score_retry_permitted": False' in source
