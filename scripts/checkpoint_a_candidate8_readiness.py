"""One non-benchmark Candidate-8 provider/schema/compile readiness probe."""
from __future__ import annotations
import argparse,json,os
from pathlib import Path
from checkpoint_a_candidate8_prereg import FROZEN_SOURCE,canonical_sha256,load
from checkpoint_a_live import _ambiguous_cases,_clear_cases
from ecocommit.candidate8 import run_candidate8
from ecocommit.candidate8_provider import GroqCandidate8Provider

def main():
    p=argparse.ArgumentParser(); p.add_argument("--preregistration",type=Path,required=True); p.add_argument("--output",type=Path,required=True); a=p.parse_args()
    instruction="Purchase two blue notebooks from Northwind Supplies for at most ₹900 total."
    if instruction in {x.instruction for x in _clear_cases()+_ambiguous_cases()}: raise ValueError("readiness probe overlaps official data")
    prereg=load(a.preregistration); result=run_candidate8(instruction,GroqCandidate8Provider(os.environ["ECOCOMMIT_LLM_API_KEY"]))
    if result.contract is None or result.status!="COMPILED": raise ValueError("Candidate-8 readiness probe did not compile")
    receipt={"schema_version":"A.CANDIDATE8.PROVIDER.READINESS.1","candidate":"A-CANDIDATE-8","frozen_semantic_source_revision":FROZEN_SOURCE,"preregistration_sha256":prereg["preregistration_sha256"],"healthy":True,"benchmark_cases_used":0,"semantic_scoring_used":False,"probe_instruction_sha256":canonical_sha256(instruction),"contract_sha256":result.contract.canonical_hash(),"provider_trace":list(result.provider_trace)}
    receipt["receipt_sha256"]=canonical_sha256(receipt); a.output.write_text(json.dumps(receipt,indent=2,sort_keys=True)+"\n"); return 0
if __name__=="__main__": raise SystemExit(main())
