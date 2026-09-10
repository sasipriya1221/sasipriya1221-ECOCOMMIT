import importlib.util, json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]; P=ROOT/"scripts/candidate8_formal_qualification.py"
S=importlib.util.spec_from_file_location("c8q",P); M=importlib.util.module_from_spec(S); S.loader.exec_module(M)

def test_formal_constants_are_frozen_and_independent():
    assert M.FROZEN_SOURCE=="850a7b5f1f21d7951cd4a9a840c0bebbb635d594"
    assert M.NAMESPACE=="ecocommit/candidate8/formal-qualification/v1"
    assert M.THRESHOLDS.case_pass==.95 and M.THRESHOLDS.selective_reliability==.98

def test_generate_seals_before_provider_and_differs_from_preflight(tmp_path):
    out=tmp_path/"sealed"; M.generate(out); manifest=json.loads((out/"manifest.json").read_text())
    assert manifest["generated_before_provider_execution"] is True
    assert manifest["cases_sha256"]!=M.PREFLIGHT_CASES_SHA and manifest["gold_sha256"]!=M.PREFLIGHT_GOLD_SHA
    assert len(json.loads((out/"cases.json").read_text())["cases"])>=20

def test_receipt_is_typed_and_digest_bound(tmp_path):
    summary={"status":"PASS","passed":True,"cases_sha256":"a"*64,"gold_sha256":"b"*64,"metrics":{},"counts":{},"thresholds":{},"provider":"Groq","model":"qwen/qwen3.6-27b","pass1_prompt_sha256":"c"*64,"pass2_prompt_sha256":"d"*64}
    binding={"run_id":"1","run_attempt":1,"binding_sha256":"e"*64}; s=tmp_path/"s"; b=tmp_path/"b"; o=tmp_path/"o"; s.write_text(json.dumps(summary)); b.write_text(json.dumps(binding)); M.receipt(s,b,o)
    assert json.loads(o.read_text())["schema"]=="ecocommit.candidate8.qualification-receipt.v1"
