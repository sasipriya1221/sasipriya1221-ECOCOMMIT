"""One non-benchmark Candidate-7 provider/schema/compile readiness probe."""
from __future__ import annotations
import argparse, json, os
from pathlib import Path
from checkpoint_a_candidate7_prereg import FROZEN_SOURCE, canonical_sha256, load
from checkpoint_a_live import _ambiguous_cases, _clear_cases
from ecocommit.candidate7 import run_candidate7
from ecocommit.candidate7_provider import GroqCandidate7Provider

def main() -> int:
    p=argparse.ArgumentParser(); p.add_argument("--preregistration",type=Path,required=True); p.add_argument("--output",type=Path,required=True); a=p.parse_args()
    instruction="Purchase two blue notebooks from Northwind Supplies for at most ₹900 total."
    official={x.instruction for x in _clear_cases()+_ambiguous_cases()}
    if instruction in official: raise ValueError("readiness probe overlaps official data")
    prereg=load(a.preregistration); result=run_candidate7(instruction,GroqCandidate7Provider(os.environ["ECOCOMMIT_LLM_API_KEY"]))
    if result.contract is None or result.status!="COMPILED": raise ValueError("Candidate-7 readiness probe did not compile")
    receipt={"schema_version":"A.CANDIDATE7.PROVIDER.READINESS.1","candidate":"A-CANDIDATE-7","frozen_semantic_source_revision":FROZEN_SOURCE,"preregistration_sha256":prereg["preregistration_sha256"],"healthy":True,"benchmark_cases_used":0,"semantic_scoring_used":False,"probe_instruction_sha256":canonical_sha256(instruction),"contract_sha256":result.contract.canonical_hash(),"provider_trace":list(result.provider_trace)}
    receipt["receipt_sha256"]=canonical_sha256(receipt); a.output.write_text(json.dumps(receipt,indent=2,sort_keys=True)+"\n",encoding="utf-8"); return 0
if __name__=="__main__": raise SystemExit(main())
