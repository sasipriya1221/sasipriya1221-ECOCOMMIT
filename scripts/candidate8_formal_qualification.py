from __future__ import annotations

import argparse, hashlib, importlib.util, json, os, secrets, subprocess
from dataclasses import asdict
from pathlib import Path

from ecocommit.candidate7_evaluator import aggregate, score_case
from ecocommit.candidate8 import run_candidate8
from ecocommit.candidate8_provider import GroqCandidate8Provider, PASS1_SYSTEM_PROMPT_C8, PASS2_SYSTEM_PROMPT
from ecocommit.qualification import QualificationThresholds

FROZEN_SOURCE = "850a7b5f1f21d7951cd4a9a840c0bebbb635d594"
PREFLIGHT_CASES_SHA = "89110c5eb32beacd41fca57782e61934aec874992fdfe57d9e90c3ae99af63b5"
PREFLIGHT_GOLD_SHA = "397e8a627e1ee7c66de2e09c40d4ada574d86aa0a1505eb6e55aea256f3ffa2e"
NAMESPACE = "ecocommit/candidate8/formal-qualification/v1"
THRESHOLDS = QualificationThresholds(.95, .98, .65, .90)

def sha(raw: bytes) -> str: return hashlib.sha256(raw).hexdigest()

def generator():
    path = Path(__file__).with_name("candidate8_sealed_preflight.py")
    spec = importlib.util.spec_from_file_location("c8_generator", path)
    module = importlib.util.module_from_spec(spec); assert spec.loader; spec.loader.exec_module(module)
    return module

def generate(out: Path) -> None:
    seed = secrets.token_bytes(32)
    cases, gold = generator().generate(seed)
    cases = {**cases, "schema":"ecocommit.candidate8.formal-corpus.v1", "namespace":NAMESPACE}
    gold = {**gold, "schema":"ecocommit.candidate8.formal-gold.v1", "namespace":NAMESPACE}
    cr = json.dumps(cases, sort_keys=True, separators=(",", ":")).encode()
    gr = json.dumps(gold, sort_keys=True, separators=(",", ":")).encode()
    if sha(cr) == PREFLIGHT_CASES_SHA or sha(gr) == PREFLIGHT_GOLD_SHA: raise SystemExit("formal set overlaps sealed preflight")
    out.mkdir(parents=True, exist_ok=False)
    (out/"cases.json").write_bytes(cr); (out/"gold.json").write_bytes(gr); (out/"seed.hex").write_text(seed.hex())
    manifest={"schema":"ecocommit.candidate8.formal-set-manifest.v1","namespace":NAMESPACE,"cases_sha256":sha(cr),"gold_sha256":sha(gr),"seed_sha256":sha(seed),"total_cases":len(cases["cases"]),"generated_before_provider_execution":True,"sealed_gold_inspected":False}
    (out/"manifest.json").write_text(json.dumps(manifest,indent=2,sort_keys=True))

def qualify(sealed: Path, aggregate_dir: Path) -> int:
    key=os.environ.get("ECOCOMMIT_LLM_API_KEY","").strip()
    if not key: raise SystemExit("ECOCOMMIT_LLM_API_KEY is required")
    candidate=Path(os.environ["CANDIDATE_ROOT"])
    if subprocess.check_output(["git","-C",str(candidate),"rev-parse","HEAD"],text=True).strip()!=FROZEN_SOURCE: raise SystemExit("source mismatch")
    cr=(sealed/"cases.json").read_bytes(); gr=(sealed/"gold.json").read_bytes(); manifest=json.loads((sealed/"manifest.json").read_text())
    if sha(cr)!=manifest["cases_sha256"] or sha(gr)!=manifest["gold_sha256"]: raise SystemExit("sealed set digest mismatch")
    cases=json.loads(cr); gold=json.loads(gr); by_id={x["case_id"]:x for x in gold["cases"]}
    provider=GroqCandidate8Provider(key); scores=[]; rows=[]; attempts=deferred=0
    for case in cases["cases"]:
        result=run_candidate8(case["instruction"],provider); attempts+=sum("attempt" in x for x in result.provider_trace); deferred+=int(result.status=="PROVIDER_DEFERRED")
        score=score_case(case["case_id"],result,by_id[case["case_id"]]); rows.append({"case_id":case["case_id"],"instruction_sha256":sha(case["instruction"].encode()),"observed_status":result.status,"error_code":result.error_code,"provider_trace":list(result.provider_trace),"score":asdict(score)})
        if result.status!="PROVIDER_DEFERRED": scores.append(score)
        if not aggregate(scores,gold["cases"],THRESHOLDS)["reachable"]: break
    metrics=aggregate(scores,gold["cases"],THRESHOLDS); status="PROVIDER_LIMITED" if deferred else ("PASS" if metrics["passed"] else "FAIL"); metrics["passed"]=status=="PASS"
    summary={"schema":"ecocommit.candidate8.formal-qualification-summary.v1","namespace":NAMESPACE,"candidate":"A-CANDIDATE-8","status":status,"source_sha":FROZEN_SOURCE,"provider":"Groq","model":provider.model,"max_completion_tokens":900,"temperature":0,"reasoning_effort":"none","pass1_prompt_sha256":sha(PASS1_SYSTEM_PROMPT_C8.encode()),"pass2_prompt_sha256":sha(PASS2_SYSTEM_PROMPT.encode()),"cases_sha256":sha(cr),"gold_sha256":sha(gr),"provider_attempts":attempts,"provider_deferred_cases":deferred,**metrics}
    (sealed/"rows.json").write_text(json.dumps(rows,indent=2,sort_keys=True)); (sealed/"summary.json").write_text(json.dumps(summary,indent=2,sort_keys=True))
    aggregate_dir.mkdir(parents=True,exist_ok=False); (aggregate_dir/"summary.json").write_text(json.dumps(summary,indent=2,sort_keys=True))
    return 0 if status in {"PASS","PROVIDER_LIMITED"} else 1

def receipt(summary_path: Path, binding_path: Path, out: Path) -> None:
    summary=json.loads(summary_path.read_text()); binding=json.loads(binding_path.read_text())
    if summary["status"]!="PASS" or summary["passed"] is not True: raise SystemExit("qualification PASS required")
    payload={"schema":"ecocommit.candidate8.qualification-receipt.v1","candidate":"A-CANDIDATE-8","status":"PASS","source_sha":FROZEN_SOURCE,"artifact_namespace":NAMESPACE,"qualification_run_id":binding["run_id"],"qualification_run_attempt":binding["run_attempt"],"binding_sha256":binding["binding_sha256"],"summary_sha256":sha(summary_path.read_bytes()),"cases_sha256":summary["cases_sha256"],"gold_sha256":summary["gold_sha256"],"metrics":summary["metrics"],"counts":summary["counts"],"thresholds":summary["thresholds"],"provider":summary["provider"],"model":summary["model"],"pass1_prompt_sha256":summary["pass1_prompt_sha256"],"pass2_prompt_sha256":summary["pass2_prompt_sha256"]}
    payload["receipt_sha256"]=sha(json.dumps(payload,sort_keys=True,separators=(",",":")).encode()); out.write_text(json.dumps(payload,indent=2,sort_keys=True))

def main():
    p=argparse.ArgumentParser(); sp=p.add_subparsers(dest="cmd",required=True)
    g=sp.add_parser("generate"); g.add_argument("--sealed-dir",type=Path,required=True)
    q=sp.add_parser("qualify"); q.add_argument("--sealed-dir",type=Path,required=True); q.add_argument("--aggregate-dir",type=Path,required=True)
    r=sp.add_parser("receipt"); r.add_argument("--summary",type=Path,required=True); r.add_argument("--binding",type=Path,required=True); r.add_argument("--output",type=Path,required=True)
    a=p.parse_args(); raise SystemExit(0 if a.cmd=="generate" and not generate(a.sealed_dir) else qualify(a.sealed_dir,a.aggregate_dir) if a.cmd=="qualify" else (receipt(a.summary,a.binding,a.output) or 0))
if __name__=="__main__": main()
