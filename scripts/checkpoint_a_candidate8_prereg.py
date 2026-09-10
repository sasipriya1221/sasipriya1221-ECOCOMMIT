"""Build and verify Candidate-8 official Checkpoint-A preregistration."""
from __future__ import annotations

import argparse, hashlib, json, subprocess, sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_ID = "A-CANDIDATE-8"
FROZEN_SOURCE = "850a7b5f1f21d7951cd4a9a840c0bebbb635d594"
ARTIFACT_NAMESPACE = "checkpoint-a-candidate-8"
FROZEN_DATASET_SHA256 = "968be3ed3a438a3a28a3402fa65c90a45cb564ed1adad2e6e51d852e24c5bb8b"
CRITERIA = {"case_pass_rate_min":.90,"selective_semantic_reliability_min":.95,"autonomous_coverage_min":.55,"ambiguous_clarification_accuracy_min":.80}

def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode()).hexdigest()
def file_sha256(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest()
def git_head(path: Path) -> str: return subprocess.check_output(["git","rev-parse","HEAD"],cwd=path,text=True).strip()
def load(path: Path) -> dict[str,Any]:
    value=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value,dict): raise ValueError("evidence must be a JSON object")
    return value

def verify_qualification(binding: dict[str,Any], summary: dict[str,Any], receipt: dict[str,Any]) -> str:
    unsigned_binding={k:v for k,v in binding.items() if k!="binding_sha256"}
    unsigned_receipt={k:v for k,v in receipt.items() if k!="receipt_sha256"}
    if binding.get("binding_sha256")!=canonical_sha256(unsigned_binding): raise ValueError("qualification binding digest mismatch")
    if receipt.get("receipt_sha256")!=canonical_sha256(unsigned_receipt): raise ValueError("qualification receipt digest mismatch")
    if not (binding.get("candidate")==CANDIDATE_ID and binding.get("source_sha")==FROZEN_SOURCE and binding.get("official_checkpoint_a_cases_used") is False and binding.get("qualification_gold_inspected") is False): raise ValueError("qualification source/protocol binding mismatch")
    if not (summary.get("schema")=="ecocommit.candidate8.formal-qualification-summary.v1" and summary.get("candidate")==CANDIDATE_ID and summary.get("source_sha")==FROZEN_SOURCE and summary.get("status")=="PASS" and summary.get("passed") is True and summary.get("provider_deferred_cases")==0): raise ValueError("formal qualification PASS evidence required")
    if not (receipt.get("schema")=="ecocommit.candidate8.qualification-receipt.v1" and receipt.get("candidate")==CANDIDATE_ID and receipt.get("source_sha")==FROZEN_SOURCE and receipt.get("status")=="PASS" and receipt.get("binding_sha256")==binding["binding_sha256"] and receipt.get("summary_sha256")==file_sha256_value(summary)): raise ValueError("typed qualification receipt mismatch")
    return canonical_sha256({"binding":binding,"summary":summary,"receipt":receipt})

def file_sha256_value(value: Any) -> str:
    return hashlib.sha256(json.dumps(value,indent=2,sort_keys=True).encode()).hexdigest()

def frozen_boundary(candidate_root: Path):
    sys.path[:0]=[str((candidate_root/"src").resolve()),str((ROOT/"scripts").resolve())]
    from checkpoint_a_live import _ambiguous_cases,_clear_cases
    from checkpoint_a_protocol import dataset_sha256
    frozen=_clear_cases()+_ambiguous_cases(); digest=dataset_sha256(frozen)
    if len(frozen)!=80 or digest!=FROZEN_DATASET_SHA256: raise ValueError("frozen Checkpoint-A dataset changed")
    evaluator={name:file_sha256(path) for name,path in {
        "scripts/checkpoint_a_live.py":ROOT/"scripts/checkpoint_a_live.py",
        "src/ecocommit/contracts.py":candidate_root/"src/ecocommit/contracts.py",
        "src/ecocommit/validator.py":candidate_root/"src/ecocommit/validator.py"}.items()}
    return digest,evaluator

def build(candidate_root:Path,binding,summary,receipt,*,qualification_artifact,qualification_archive_sha256):
    if git_head(candidate_root)!=FROZEN_SOURCE: raise ValueError("Candidate-8 checkout is not frozen source")
    qualification_digest=verify_qualification(binding,summary,receipt)
    if not qualification_artifact.startswith("github-actions://") or len(qualification_archive_sha256)!=64: raise ValueError("retained qualification artifact binding required")
    dataset,evaluator=frozen_boundary(candidate_root)
    components={name:file_sha256(candidate_root/name) for name in ("src/ecocommit/candidate8.py","src/ecocommit/candidate8_provider.py","src/ecocommit/candidate8_normalize.py","src/ecocommit/candidate8_logic.py","src/ecocommit/candidate8_relation_checklist.py")}
    runner_names=("scripts/checkpoint_a_candidate8.py","scripts/checkpoint_a_candidate8_prereg.py","scripts/checkpoint_a_candidate8_readiness.py","scripts/candidate6_official_reachability.py",".github/workflows/candidate8-official-prereg.yml",".github/workflows/candidate8-provider-readiness.yml",".github/workflows/checkpoint-a-candidate8.yml")
    runners={name:file_sha256(ROOT/name) for name in runner_names}
    provider={"base_url":"https://api.groq.com/openai/v1","model":"qwen/qwen3.6-27b","reasoning_effort":"none","temperature":0,"max_completion_tokens":900,"max_attempts_per_pass":2,"semantic_score_retry_permitted":False}
    value={"schema_version":"A.CANDIDATE8.PREREGISTRATION.1","candidate":CANDIDATE_ID,"frozen_semantic_source_revision":FROZEN_SOURCE,"artifact_namespace":ARTIFACT_NAMESPACE,"supervisor_source_revision":git_head(ROOT),"qualification":{"status":"PASS","evidence_sha256":qualification_digest,"artifact":qualification_artifact,"archive_sha256":qualification_archive_sha256,"receipt_sha256":receipt["receipt_sha256"]},"frozen_dataset":{"count":80,"sha256":dataset},"frozen_evaluator_files":evaluator,"frozen_evaluator_sha256":canonical_sha256(evaluator),"criteria":CRITERIA,"criteria_sha256":canonical_sha256(CRITERIA),"candidate_components":components,"candidate_components_sha256":canonical_sha256(components),"official_runner_files":runners,"official_runner_sha256":canonical_sha256(runners),"provider_policy":provider,"provider_policy_sha256":canonical_sha256(provider),"early_stop_policy":{"implementation":"class-aware exact optimistic joint reachability","check_before_next_provider_call":True},"one_shot_policy":{"official_run_attempt":1,"rerun_permitted":False,"resume_to_pass_permitted":False,"semantic_score_retry_permitted":False}}
    value["preregistration_sha256"]=canonical_sha256(value); return value

def verify(candidate_root,value,binding,summary,receipt):
    expected=build(candidate_root,binding,summary,receipt,qualification_artifact=value.get("qualification",{}).get("artifact",""),qualification_archive_sha256=value.get("qualification",{}).get("archive_sha256",""))
    if value!=expected: raise ValueError("Candidate-8 official preregistration mismatch")

def main():
    p=argparse.ArgumentParser(); p.add_argument("--candidate-root",type=Path,required=True); p.add_argument("--binding",type=Path,required=True); p.add_argument("--summary",type=Path,required=True); p.add_argument("--receipt",type=Path,required=True); p.add_argument("--qualification-artifact",required=True); p.add_argument("--qualification-archive-sha256",required=True); p.add_argument("--output",type=Path); p.add_argument("--verify",type=Path); a=p.parse_args()
    b,s,r=load(a.binding),load(a.summary),load(a.receipt)
    if a.verify: verify(a.candidate_root.resolve(),load(a.verify),b,s,r); return 0
    if not a.output: raise SystemExit("--output required")
    value=build(a.candidate_root.resolve(),b,s,r,qualification_artifact=a.qualification_artifact,qualification_archive_sha256=a.qualification_archive_sha256); a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_text(json.dumps(value,indent=2,sort_keys=True)+"\n"); return 0
if __name__=="__main__": raise SystemExit(main())
