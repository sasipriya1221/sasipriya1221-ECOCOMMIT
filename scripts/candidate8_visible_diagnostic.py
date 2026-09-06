from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

from ecocommit.candidate8 import run_candidate8
from ecocommit.candidate8_provider import GroqCandidate8Provider


CASE_ID = "C8D020"


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    corpus = json.loads((root / "data/candidate8-development/development.json").read_text(encoding="utf-8"))
    case = next(row for row in corpus["cases"] if row["case_id"] == CASE_ID)
    instruction = case["instruction"]
    key = os.environ.get("ECOCOMMIT_LLM_API_KEY", "").strip()
    if not key:
        raise SystemExit("ECOCOMMIT_LLM_API_KEY is required")
    result = run_candidate8(instruction, GroqCandidate8Provider(key))
    output = Path(os.environ.get("C8_DIAGNOSTIC_OUTPUT", "artifacts/candidate8-visible-diagnostic.json"))
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "ecocommit.candidate8.visible-diagnostic.v1",
        "case_id": CASE_ID,
        "source_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "instruction_sha256": hashlib.sha256(instruction.encode()).hexdigest(),
        "status": result.status,
        "error_code": result.error_code,
        "contract_present": result.contract is not None,
        "facts": [fact.model_dump(mode="json") for fact in result.facts],
        "relations": result.relations.model_dump(mode="json") if result.relations else None,
        "dispositions": [(fid, disposition.value) for fid, disposition in result.dispositions],
        "normalization_events": list(result.normalization_events),
        "unresolved_fact": result.unresolved_fact.model_dump(mode="json") if result.unresolved_fact else None,
        "provider_trace": list(result.provider_trace),
    }
    output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


if __name__ == "__main__":
    main()
