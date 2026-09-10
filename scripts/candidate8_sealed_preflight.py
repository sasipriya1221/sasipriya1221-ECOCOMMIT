from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import secrets
import subprocess
from dataclasses import asdict
from pathlib import Path
from typing import Any

from ecocommit.candidate7_evaluator import aggregate, score_case
from ecocommit.candidate8 import run_candidate8
from ecocommit.candidate8_provider import GroqCandidate8Provider, PASS1_SYSTEM_PROMPT_C8, PASS2_SYSTEM_PROMPT
from ecocommit.qualification import QualificationThresholds


FROZEN_SOURCE = "850a7b5f1f21d7951cd4a9a840c0bebbb635d594"
THRESHOLDS = QualificationThresholds(.95, .98, .65, .90)
REQUIRED_COVERAGE = {
    "AND", "OR", "nested_AND_OR", "negation", "IF_THEN", "UNLESS",
    "prerequisites", "alternatives", "numeric_constraints", "temporal_constraints",
    "references_pronouns", "multiple_entities", "ordered_actions", "ambiguity",
    "conflicts", "irrelevant_clauses", "direct_object_role", "explicit_counterparty",
    "exceptions", "unrelated_regressions",
}


def _sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha_text(value: str) -> str:
    return _sha_bytes(value.encode())


def _pick(rng: random.Random, values: tuple[str, ...]) -> str:
    return values[rng.randrange(len(values))]


def generate(seed: bytes) -> tuple[dict[str, Any], dict[str, Any]]:
    """Generate the sealed corpus deterministically from an externally hidden seed."""
    rng = random.Random(int.from_bytes(seed, "big"))
    direct = _pick(rng, ("carrier", "printer", "photographer"))
    counterparty = _pick(rng, ("workshop", "carrier", "supplier"))
    item = _pick(rng, ("labels", "cartons", "envelopes"))
    quantity = rng.choice((120, 180, 240, 300))
    stock = rng.choice((20, 30, 40, 50))
    exact = rng.choice((7300, 9200, 12750, 18400))
    fee = rng.choice((4200, 6800, 8900))
    cases: list[dict[str, Any]] = []
    gold: list[dict[str, Any]] = []

    def add(instruction: str, tags: list[str], status: str, ir: dict[str, Any]) -> None:
        cid = f"C8P{len(cases) + 1:03d}"
        cases.append({"case_id": cid, "instruction": instruction, "feature_tags": tags})
        gold.append({"case_id": cid, "expected_status": status, "gold_semantic_ir": ir})

    add(f"Pay {direct} exactly ₹{exact:,} for completed work.", ["direct_object_role", "numeric_constraints"], "COMPILED", {"actions":[{"kind":"PAY","object_terms":[direct]}],"constraints":[["EXACT_TOTAL_COST",str(exact)]]})
    add(f"Pay the repair invoice to the {counterparty} exactly ₹{fee:,}.", ["explicit_counterparty", "multiple_entities", "numeric_constraints"], "COMPILED", {"actions":[{"kind":"PAY","object_terms":["repair","invoice"]}],"constraints":[["EXACT_TOTAL_COST",str(fee)]]})
    add(f"Order {quantity} {item} only if warehouse count is below {stock}.", ["IF_THEN"], "COMPILED", {"actions":[{"kind":"ORDER","object_terms":[item],"quantity":str(quantity)}],"guards":[{"root":"ATOM","atoms":1,"terms":["warehouse","count","below",str(stock)]}]})
    add("Release the deposit unless inspection fails.", ["UNLESS", "negation"], "COMPILED", {"actions":[{"kind":"RELEASE","object_terms":["deposit"]}],"guards":[{"root":"NOT","atoms":1,"min_not":1,"terms":["inspection","fails"]}]})
    add("Hire the trainer only if insurance is valid and legal approves.", ["AND"], "COMPILED", {"actions":[{"kind":"HIRE","object_terms":["trainer"]}],"guards":[{"root":"AND","atoms":2,"terms":["insurance","valid","legal","approves"]}]})
    add("Buy the backup router if the primary router fails or IT declares an emergency.", ["OR", "alternatives"], "COMPILED", {"actions":[{"kind":"BUY","object_terms":["backup","router"]}],"guards":[{"root":"OR","atoms":2,"terms":["primary","router","fails","it","emergency"]}]})
    add("Order supplies only if inventory is low and either branch A or branch B requests replenishment.", ["nested_AND_OR"], "COMPILED", {"actions":[{"kind":"ORDER","object_terms":["supplies"]}],"guards":[{"root":"AND","atoms":3,"contains_root":"OR","terms":["inventory","low","branch","a","b","requests","replenishment"]}]})
    add("Renew the licence only if the compliance notice is not active.", ["negation"], "COMPILED", {"actions":[{"kind":"RENEW","object_terms":["licence"]}],"guards":[{"root":"NOT","atoms":1,"min_not":1,"terms":["compliance","notice","active"]}]})
    add("Order components, then release the advance after the order succeeds.", ["prerequisites", "ordered_actions"], "COMPILED", {"actions":[{"kind":"ORDER","object_terms":["components"]},{"kind":"RELEASE","object_terms":["advance"]}],"dependencies":1})
    add("Reserve the room, then pay the deposit after the reservation is completed.", ["prerequisites", "ordered_actions", "references_pronouns"], "COMPILED", {"actions":[{"kind":"RESERVE","object_terms":["room"]},{"kind":"PAY","object_terms":["deposit"]}],"dependencies":1})
    add("Pay the filing fee within 7 days.", ["temporal_constraints"], "COMPILED", {"actions":[{"kind":"PAY","object_terms":["filing","fee"]}]})
    add("Book 20 seats within 3 days.", ["temporal_constraints", "numeric_constraints"], "COMPILED", {"actions":[{"kind":"BOOK","object_terms":["seats"],"quantity":"20"}]})
    add("Order a reasonable number of folders.", ["ambiguity"], "CLARIFICATION_REQUIRED", {"ambiguity_any":["UNDEFINED_QUANTITY"]})
    add("Buy replacement monitors within the normal departmental budget.", ["ambiguity"], "CLARIFICATION_REQUIRED", {"ambiguity_any":["UNDEFINED_BUDGET"]})
    add("Select a suitable vendor.", ["ambiguity", "explicit_counterparty"], "CLARIFICATION_REQUIRED", {"ambiguity_any":["SUBJECTIVE_SELECTION_CRITERION"]})
    add("Buy the server for at most ₹80,000 and at least ₹95,000.", ["conflicts", "numeric_constraints"], "REJECTED", {"reject_code":"IR_CONTRADICTORY_CONSTRAINTS"})
    add(f"Pay the courier exactly ₹{fee:,} for yesterday's completed route; the office plants are green.", ["irrelevant_clauses"], "COMPILED", {"actions":[{"kind":"PAY","object_terms":["courier"]}],"constraints":[["EXACT_TOTAL_COST",str(fee)]]})
    add("Transfer the refund to the customer after finance approves.", ["explicit_counterparty", "multiple_entities", "IF_THEN"], "COMPILED", {"actions":[{"kind":"TRANSFER","object_terms":["refund"]}],"guards":[{"root":"ATOM","atoms":1,"terms":["finance","approves"]}]})
    add("Commit up to ₹60,000, except allow ₹4,000 extra for shipping.", ["exceptions", "numeric_constraints"], "COMPILED", {"actions":[{"kind":"COMMIT"}],"constraints":[["MAX_TOTAL_COST","60000"]],"exceptions":[{"effect":"ADD_MONETARY_ALLOWANCE","amount":"4000","terms":["shipping"]}]})
    add("Hire the agency only if procurement approves, except do not hire if its licence is expired.", ["exceptions", "references_pronouns"], "COMPILED", {"actions":[{"kind":"HIRE","object_terms":["agency"]}],"guards":[{"root":"ATOM","atoms":1,"terms":["procurement","approves"]}],"exceptions":[{"effect":"BLOCK_ACTION","terms":["licence","expired"]}]})
    add("Book the venue, then pay the invoice after the booking succeeds.", ["references_pronouns", "ordered_actions", "prerequisites"], "COMPILED", {"actions":[{"kind":"BOOK","object_terms":["venue"]},{"kind":"PAY","object_terms":["invoice"]}],"dependencies":1})
    add("Reserve server capacity; after it succeeds, commit the annual fee.", ["references_pronouns", "ordered_actions"], "COMPILED", {"actions":[{"kind":"RESERVE","object_terms":["server","capacity"]},{"kind":"COMMIT","object_terms":["annual","fee"]}],"dependencies":1})
    add("Pay the photographer exactly ₹12,750 for the finished shoot.", ["unrelated_regressions", "direct_object_role"], "COMPILED", {"actions":[{"kind":"PAY","object_terms":["photographer"]}],"constraints":[["EXACT_TOTAL_COST","12750"]]})
    add("Order batteries if stock is below 20; ignore the weather forecast.", ["unrelated_regressions", "irrelevant_clauses"], "COMPILED", {"actions":[{"kind":"ORDER","object_terms":["batteries"]}],"guards":[{"root":"ATOM","atoms":1,"terms":["stock","below","20"]}]})
    assert len(cases) >= 20
    assert REQUIRED_COVERAGE <= {tag for row in cases for tag in row["feature_tags"]}
    return ({"schema":"ecocommit.candidate8.sealed-corpus.v1","cases":cases}, {"schema":"ecocommit.candidate8.sealed-gold.v1","cases":gold})


def run(output_root: Path) -> int:
    key = os.environ.get("ECOCOMMIT_LLM_API_KEY", "").strip()
    if not key:
        raise SystemExit("ECOCOMMIT_LLM_API_KEY is required")
    if subprocess.check_output(["git", "-C", os.environ["CANDIDATE_ROOT"], "rev-parse", "HEAD"], text=True).strip() != FROZEN_SOURCE:
        raise SystemExit("frozen Candidate-8 source mismatch")
    seed = secrets.token_bytes(32)
    corpus, gold_doc = generate(seed)
    sealed = output_root / "sealed"
    aggregate_dir = output_root / "aggregate"
    sealed.mkdir(parents=True, exist_ok=False)
    aggregate_dir.mkdir(parents=True, exist_ok=False)
    corpus_raw = json.dumps(corpus, sort_keys=True, separators=(",", ":")).encode()
    gold_raw = json.dumps(gold_doc, sort_keys=True, separators=(",", ":")).encode()
    (sealed / "cases.json").write_bytes(corpus_raw)
    (sealed / "gold.json").write_bytes(gold_raw)
    (sealed / "seed.hex").write_text(seed.hex(), encoding="ascii")
    gold_by_id = {row["case_id"]: row for row in gold_doc["cases"]}
    provider = GroqCandidate8Provider(key)
    rows, scores = [], []
    provider_attempts = 0
    provider_deferred = 0
    for case in corpus["cases"]:
        result = run_candidate8(case["instruction"], provider)
        provider_attempts += sum("attempt" in entry for entry in result.provider_trace)
        provider_deferred += int(result.status == "PROVIDER_DEFERRED")
        score = score_case(case["case_id"], result, gold_by_id[case["case_id"]])
        rows.append({
            "case_id": case["case_id"], "instruction_sha256": _sha_text(case["instruction"]),
            "observed_status": result.status, "error_code": result.error_code,
            "provider_trace": list(result.provider_trace), "score": asdict(score),
        })
        if result.status != "PROVIDER_DEFERRED":
            scores.append(score)
        interim = aggregate(scores, gold_doc["cases"], THRESHOLDS)
        if not interim["reachable"]:
            break
    metrics = aggregate(scores, gold_doc["cases"], THRESHOLDS)
    status = "PROVIDER_LIMITED" if provider_deferred else ("PASS" if metrics["passed"] else "FAIL")
    metrics["passed"] = status == "PASS"
    summary = {
        "schema":"ecocommit.candidate8.sealed-preflight-summary.v1", "candidate":"A-CANDIDATE-8",
        "status":status, "passed":status == "PASS", "source_sha":FROZEN_SOURCE,
        "provider":"Groq", "model":provider.model, "max_completion_tokens":provider.max_completion_tokens,
        "temperature":0, "reasoning_effort":"none", "pass1_prompt_sha256":_sha_text(PASS1_SYSTEM_PROMPT_C8),
        "pass2_prompt_sha256":_sha_text(PASS2_SYSTEM_PROMPT), "cases_sha256":_sha_bytes(corpus_raw),
        "gold_sha256":_sha_bytes(gold_raw), "seed_sha256":_sha_bytes(seed),
        "provider_attempts":provider_attempts, "provider_deferred_cases":provider_deferred,
        **metrics,
    }
    (sealed / "rows.json").write_text(json.dumps(rows, indent=2, sort_keys=True), encoding="utf-8")
    (sealed / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    (aggregate_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    return 0 if status in {"PASS", "PROVIDER_LIMITED"} else 1


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(run(args.output_root))


if __name__ == "__main__":
    main()
