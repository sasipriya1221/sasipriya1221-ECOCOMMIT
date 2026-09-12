from __future__ import annotations
from copy import deepcopy
import hashlib,json
from pathlib import Path
import sys
import pytest
from pydantic import ValidationError
from ecocommit.checkpoint_a_evidence import CheckpointAEvidenceReceipt,CANDIDATE8_CRITERIA_SHA256,CANDIDATE8_EVALUATOR_SHA256
from scripts.checkpoint_a_candidate8_prereg import FROZEN_SOURCE,canonical_sha256,verify_qualification

def evidence():
    binding={"candidate":"A-CANDIDATE-8","source_sha":FROZEN_SOURCE,"official_checkpoint_a_cases_used":False,"qualification_gold_inspected":False}
    binding["binding_sha256"]=canonical_sha256(binding)
    summary={"schema":"ecocommit.candidate8.formal-qualification-summary.v1","candidate":"A-CANDIDATE-8","source_sha":FROZEN_SOURCE,"status":"PASS","passed":True,"provider_deferred_cases":0}
    summary_sha=hashlib.sha256(json.dumps(summary,indent=2,sort_keys=True).encode()).hexdigest()
    receipt={"schema":"ecocommit.candidate8.qualification-receipt.v1","candidate":"A-CANDIDATE-8","source_sha":FROZEN_SOURCE,"status":"PASS","binding_sha256":binding["binding_sha256"],"summary_sha256":summary_sha}
    receipt["receipt_sha256"]=canonical_sha256(receipt)
    return binding,summary,receipt

def receipt_values():
    return {"verification_mode":"FROZEN_AGGREGATE","evidence_reference":"github-actions://evidence","aggregate_sha256":"a"*64,"manifest_sha256":"b"*64,"source_revision":"c"*40,"candidate_version":"A-CANDIDATE-8","dataset_sha256":"968be3ed3a438a3a28a3402fa65c90a45cb564ed1adad2e6e51d852e24c5bb8b","total_cases":80,"full_frozen_gate_run":True,"gate_passed":True,"metrics":{"passed_cases":72,"case_pass_rate":.9,"autonomous_coverage":.55,"selective_semantic_reliability":.95,"ambiguous_clarification_accuracy":.8},"candidate_source_revision":FROZEN_SOURCE,"qualification_status":"PASS","qualification_evidence_sha256":"d"*64,"qualification_source_revision":FROZEN_SOURCE,"preregistration_sha256":"e"*64,"evaluator_sha256":CANDIDATE8_EVALUATOR_SHA256,"criteria_sha256":CANDIDATE8_CRITERIA_SHA256,"artifact_namespace":"checkpoint-a-candidate-8","semantic_score_retry_count":0}

def test_candidate8_formal_pass_is_source_bound():
    binding,summary,receipt=evidence(); assert len(verify_qualification(binding,summary,receipt))==64
    bad=deepcopy(summary); bad["status"]="FAIL"
    with pytest.raises(ValueError,match="PASS evidence"): verify_qualification(binding,bad,receipt)

def test_candidate8_typed_a_receipt_accepts_only_frozen_protocol():
    assert CheckpointAEvidenceReceipt(**receipt_values()).candidate_version=="A-CANDIDATE-8"
    with pytest.raises(ValidationError): CheckpointAEvidenceReceipt(**{**receipt_values(),"semantic_score_retry_count":1})

def test_candidate8_official_runner_forbids_score_retries():
    from pathlib import Path
    text=(Path(__file__).parents[1]/"scripts/checkpoint_a_candidate8_prereg.py").read_text()
    assert '"semantic_score_retry_permitted":False' in text

def test_candidate8_runtime_exposes_reachability_counts(tmp_path):
    from scripts import checkpoint_a_candidate8 as runner
    root = Path(__file__).parents[1]
    sys.path.insert(0, str(root / "scripts"))
    runtime = runner.runtime(root)
    assert runtime["OfficialCounts"].__name__ == "OfficialCounts"
