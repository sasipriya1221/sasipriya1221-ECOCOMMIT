"""One-shot frozen Candidate-7 official Checkpoint-A runner."""
from __future__ import annotations

import argparse, importlib.util, json, os, sys
from pathlib import Path

from checkpoint_a_candidate6 import _counts_from_rows, _metrics, _write_json, canonical_sha256
from checkpoint_a_candidate7_prereg import ARTIFACT_NAMESPACE, CRITERIA, FROZEN_SOURCE, load, verify_preregistration

ROOT = Path(__file__).resolve().parents[1]


def runtime(candidate: Path):
    sys.path.insert(0, str((candidate / "src").resolve()))
    from candidate6_official_reachability import OfficialCounts, OfficialThresholds, final_pass, reachable
    from checkpoint_a_live import _ambiguous_cases, _clear_cases, semantic_case_pass
    from ecocommit.candidate7 import run_candidate7
    from ecocommit.candidate7_provider import GroqCandidate7Provider
    from ecocommit.validator import FidelityValidator
    return locals()


def verify_readiness(value, prereg):
    unsigned = {k:v for k,v in value.items() if k != "receipt_sha256"}
    if value.get("receipt_sha256") != canonical_sha256(unsigned) or not (
        value.get("schema_version") == "A.CANDIDATE7.PROVIDER.READINESS.1" and value.get("candidate") == "A-CANDIDATE-7"
        and value.get("frozen_semantic_source_revision") == FROZEN_SOURCE and value.get("preregistration_sha256") == prereg["preregistration_sha256"]
        and value.get("healthy") is True and value.get("benchmark_cases_used") == 0):
        raise ValueError("passing Candidate-7 provider readiness receipt required")


def main() -> int:
    p=argparse.ArgumentParser(); p.add_argument("--candidate-root",type=Path,required=True); p.add_argument("--preregistration",type=Path,required=True); p.add_argument("--binding",type=Path,required=True); p.add_argument("--summary",type=Path,required=True); p.add_argument("--provider-readiness",type=Path); p.add_argument("--output-dir",type=Path); p.add_argument("--evidence-reference"); p.add_argument("--verify-offline",action="store_true"); a=p.parse_args()
    candidate=a.candidate_root.resolve(); prereg=load(a.preregistration); binding=load(a.binding); summary=load(a.summary)
    verify_preregistration(candidate, prereg, binding, summary); rt=runtime(candidate); frozen=rt["_clear_cases"]()+rt["_ambiguous_cases"]()
    if a.verify_offline: return 0
    if os.getenv("GITHUB_RUN_ATTEMPT") != "1" or not a.provider_readiness or not a.output_dir or not a.evidence_reference: raise ValueError("one-shot official inputs required")
    verify_readiness(load(a.provider_readiness), prereg); key=os.getenv("ECOCOMMIT_LLM_API_KEY","").strip()
    if not key: raise ValueError("provider key required")
    out=a.output_dir.resolve(); out.mkdir(parents=True,exist_ok=False); cases=out/"cases"; cases.mkdir(); provider=rt["GroqCandidate7Provider"](key); validator=rt["FidelityValidator"](); rows=[]; scored=[]; eliminated=None; provider_limited=False
    for index,gold in enumerate(frozen):
        result=rt["run_candidate7"](gold.instruction,provider); passed=False; detail=None
        if result.contract is not None: passed,detail=rt["semantic_case_pass"](result.contract,gold,validator)
        row={"id":gold.case_id,"instruction":gold.instruction,"candidate_status":result.status,"blocked_actions":sorted(result.blocked_actions),"passed":bool(passed),"detail":detail,"error_kind":"provider_deferred" if result.status=="PROVIDER_DEFERRED" else ("candidate_rejection" if result.contract is None else None),"error_code":result.error_code,"provider_trace":list(result.provider_trace),"contract":result.contract.model_dump(mode="json") if result.contract else None,"preregistration_sha256":prereg["preregistration_sha256"]}
        row["row_sha256"]=canonical_sha256(row); rows.append(row); _write_json(cases/f"case-{index:02d}-{gold.case_id}.json",row)
        if result.status == "PROVIDER_DEFERRED": provider_limited=True; break
        scored.append(row); counts=_counts_from_rows(scored,frozen,rt)
        if not rt["reachable"](counts,rt["OfficialThresholds"]()): eliminated=gold.case_id; break
    counts=_counts_from_rows(scored,frozen,rt); metrics=_metrics(counts); complete=counts.processed==80; passed=complete and rt["final_pass"](counts,rt["OfficialThresholds"]()); status="INCONCLUSIVE_PROVIDER_LIMITED" if provider_limited else ("PASS" if passed else "FAILED")
    decision={"candidate":"A-CANDIDATE-7","status":status,"processed":counts.processed,"provider_attempt_rows":len(rows),"mathematically_eliminated_after_case":eliminated,"metrics":metrics,"criteria":CRITERIA,"score_recovery_retries":0}; decision["decision_sha256"]=canonical_sha256(decision); _write_json(out/"decision.json",decision)
    aggregate={"candidate":"A-CANDIDATE-7","status":decision["status"],"processed":counts.processed,"total":80,"metrics":metrics,"decision_sha256":decision["decision_sha256"],"row_sha256":[r["row_sha256"] for r in rows]}; aggregate["aggregate_sha256"]=canonical_sha256(aggregate); _write_json(out/"aggregate.json",aggregate)
    if passed:
        spec=importlib.util.spec_from_file_location("c7_a_receipt",ROOT/"src/ecocommit/checkpoint_a_evidence.py"); module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        q=prereg["qualification"]; receipt=module.CheckpointAEvidenceReceipt(verification_mode="FROZEN_AGGREGATE",evidence_reference=a.evidence_reference,aggregate_sha256=aggregate["aggregate_sha256"],manifest_sha256=prereg["preregistration_sha256"],source_revision=os.getenv("GITHUB_SHA","0"*40),candidate_version="A-CANDIDATE-7",dataset_sha256=prereg["frozen_dataset"]["sha256"],total_cases=80,full_frozen_gate_run=True,gate_passed=True,metrics=module.CheckpointAMetrics(passed_cases=counts.case_passes,**metrics),candidate_source_revision=FROZEN_SOURCE,qualification_status="PASS",qualification_evidence_sha256=q["evidence_sha256"],qualification_source_revision=FROZEN_SOURCE,preregistration_sha256=prereg["preregistration_sha256"],evaluator_sha256=prereg["frozen_evaluator_sha256"],criteria_sha256=prereg["criteria_sha256"],artifact_namespace=ARTIFACT_NAMESPACE,semantic_score_retry_count=0); _write_json(out/"checkpoint-a-pass-receipt.json",receipt.model_dump(mode="json"))
    return 0 if passed else (3 if provider_limited else 2)


if __name__=="__main__": raise SystemExit(main())
