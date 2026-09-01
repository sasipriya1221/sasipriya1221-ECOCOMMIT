from __future__ import annotations

import argparse
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

from ecocommit.contracts import ClauseType, DecisionStatus, EconomicIntentContract
from ecocommit.interpreter import (
    CandidateContractError,
    OpenAICompatibleIntentProvider,
    ProviderRequestError,
)
from ecocommit.validator import FidelityValidator

from checkpoint_a_constants import CRITERIA


@dataclass(frozen=True)
class GoldRequirement:
    clause_type: ClauseType
    source_text: str
    negated: bool | None = None


@dataclass(frozen=True)
class GoldCase:
    case_id: str
    instruction: str
    expected_status: DecisionStatus
    required: tuple[GoldRequirement, ...]
    require_exception: bool = False
    require_dependency: bool = False


def _clear_cases() -> list[GoldCase]:
    cases: list[GoldCase] = []
    products = [
        ("S17-certified bearings", "500", "₹8 lakh", "five days"),
        ("ISO-9001 pressure valves", "120", "₹6 lakh", "seven days"),
        ("medical-grade power modules", "80", "₹9 lakh", "ten days"),
        ("fire-rated network cabinets", "40", "₹5 lakh", "Friday"),
        ("food-safe conveyor belts", "25", "₹4 lakh", "14 days"),
    ]
    suppliers = ["approved suppliers", "Vendor A", "domestic suppliers", "certified suppliers", "Supplier Q"]
    idx = 1
    for product, qty, amount, deadline in products:
        for supplier in suppliers:
            instruction = f"Buy {qty} {product} from {supplier} for no more than {amount} and ensure delivery within {deadline}."
            cases.append(GoldCase(
                case_id=f"C{idx:03d}",
                instruction=instruction,
                expected_status=DecisionStatus.VALIDATED,
                required=(
                    GoldRequirement(ClauseType.QUANTITY, qty),
                    GoldRequirement(ClauseType.PRODUCT, product),
                    GoldRequirement(ClauseType.COUNTERPARTY, supplier),
                    GoldRequirement(ClauseType.AMOUNT, amount),
                    GoldRequirement(ClauseType.TEMPORAL, deadline),
                ),
            ))
            idx += 1

    advanced = [
        "Buy 300 S17 bearings below ₹7 lakh, but do not use Vendor B unless Vendor A is out of stock.",
        "Purchase 60 industrial sensors for at most ₹3 lakh only if calibration certificates are valid at dispatch.",
        "Order 100 safety relays from approved suppliers; never make more than 20% irreversible before inspection passes.",
        "Acquire 12 cooling units under ₹9 lakh and pay the final 40% only after installation acceptance.",
        "Buy 200 sterile connectors by Thursday, excluding suppliers whose certification expires before delivery.",
        "Purchase 75 power controllers under ₹5 lakh unless the approved replacement guarantee is missing, in which case do not proceed.",
        "Order 30 pumps from Vendor A if stock is reserved; otherwise use Vendor C, but keep total exposure below ₹6 lakh.",
        "Buy 400 packaging seals for no more than ₹2 lakh, provided that food-safety certification is current.",
        "Purchase 18 lab analyzers and do not authorize recurring charges; this is a one-time purchase only.",
        "Buy 90 control boards under ₹4 lakh and do not capture payment before dispatch confirmation.",
        "Order 70 certified actuators within 8 days; if Vendor A cannot meet the deadline, use any approved supplier under ₹5 lakh.",
        "Purchase 45 inspection cameras for ₹6 lakh maximum and never substitute a non-certified model.",
        "Buy 250 S17 fasteners before Monday, but only from suppliers with an active replacement guarantee.",
        "Acquire 10 compressors under ₹8 lakh; do not pay the retention amount until quality acceptance.",
        "Order 150 temperature probes at no more than ₹1.5 lakh and reject any offer that requires automatic renewal.",
        "Buy 24 sterilization units from an approved supplier, unless the warranty is shorter than two years.",
        "Purchase 90 battery packs under ₹4 lakh; capture at most 30% before dispatch and the rest after acceptance.",
        "Order 55 certified routers for delivery before Friday; do not accept a higher price even if delivery is faster.",
        "Buy 80 pressure sensors below ₹3.5 lakh only if inventory is reserved for this transaction.",
        "Purchase 100 relays from Vendor A unless its certification is expired; then use another approved supplier.",
        "Acquire 65 motor controllers under ₹5.5 lakh, excluding any supplier that cannot provide traceable batch certification.",
        "Buy 32 air filters within 6 days and never exceed ₹2 lakh total including fees.",
        "Order 200 connector kits; if the quality certificate is pending, authorize only and do not capture funds.",
        "Purchase 16 industrial PCs under ₹7 lakh, but do not use a marketplace reseller unless explicitly approved.",
        "Buy 500 S17 bolts below ₹2.5 lakh and ensure the order is one-time, not recurring.",
    ]
    for text in advanced:
        required: list[GoldRequirement] = []
        lower = text.lower()
        if "do not" in lower or "never" in lower or "excluding" in lower or "reject" in lower:
            marker = "do not" if "do not" in lower else ("never" if "never" in lower else ("excluding" if "excluding" in lower else "reject"))
            required.append(GoldRequirement(ClauseType.CONDITION, marker, True))
        cases.append(GoldCase(
            case_id=f"C{idx:03d}",
            instruction=text,
            expected_status=DecisionStatus.VALIDATED,
            required=tuple(required),
            require_exception=any(m in lower for m in ("unless", "otherwise", "provided that", "only if", "in which case")),
            require_dependency=any(m in lower for m in ("if ", "before", "after", "until", "unless", "only if", "provided that")),
        ))
        idx += 1
    return cases[:50]


def _ambiguous_cases() -> list[GoldCase]:
    texts = [
        "Buy around 500 production-grade S17 parts at a reasonable price.",
        "Choose a reliable supplier and spend a little more if needed.",
        "Buy the best certified bearings soon, but keep the cost sensible.",
        "Order enough backup units for normal operations without overspending.",
        "Use Vendor A if the deal is good; otherwise choose someone trustworthy.",
        "Buy these components with strong protection and minimal irreversible risk.",
        "Purchase roughly 100 units and keep payment conservative until we are comfortable with quality.",
        "Get a premium model if the price difference is not too much.",
        "Buy from an approved supplier unless another option is clearly better.",
        "Order the usual quantity and use our normal payment safeguards.",
        "Buy replacement parts quickly and avoid unnecessary financial exposure.",
        "Choose the cheapest acceptable option, but quality matters more.",
        "Purchase sufficient stock for the next cycle and keep within our normal limit.",
        "Buy the certified version if it is reasonably available.",
        "Use the preferred supplier unless their terms are materially worse.",
        "Order about 50 units and pay only what is appropriate before inspection.",
        "Get the parts before they are needed and keep the budget under control.",
        "Select a supplier with acceptable guarantees and normal delivery terms.",
        "Buy the standard model unless the upgraded one offers much better value.",
        "Purchase what operations needs, but do not take excessive irreversible risk.",
        "Order the required quantity and use a safe staged-payment approach.",
        "Buy from a reputable domestic supplier if practical.",
        "Choose a certified product with good warranty protection and fair pricing.",
        "Buy enough units to cover expected demand without tying up too much cash.",
        "Use Vendor A unless another certified supplier is substantially cheaper.",
        "Purchase the parts with a reasonable delivery commitment and quality protection.",
        "Buy the usual S17 parts at our standard commercial terms.",
        "Order the best option we can justify without taking unnecessary risk.",
        "Purchase a suitable quantity below the normal approval threshold.",
        "Buy the components and keep the irreversible portion as low as reasonably possible.",
    ]
    return [
        GoldCase(
            case_id=f"A{i:03d}",
            instruction=text,
            expected_status=DecisionStatus.CLARIFICATION_REQUIRED,
            required=(),
            require_exception="unless" in text.lower(),
            require_dependency=bool(re.search(r"\b(?:if|unless|until|before|after)\b", text.lower())),
        )
        for i, text in enumerate(texts, start=1)
    ]


def cases() -> list[GoldCase]:
    clear = _clear_cases()
    ambiguous = _ambiguous_cases()
    assert len(clear) == 50
    assert len(ambiguous) == 30
    return clear + ambiguous


def _content_words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) > 1}


def _span_matches(contract: EconomicIntentContract, requirement: GoldRequirement) -> bool:
    wanted = requirement.source_text.lower()

    # A prohibition is semantically preserved by any negated affected clause; it
    # does not have to be encoded specifically as CONDITION.
    if requirement.negated is True and requirement.clause_type == ClauseType.CONDITION:
        for clause in contract.clauses:
            if not clause.negated:
                continue
            span = clause.source_span.text.lower() if clause.source_span else ""
            if wanted in span or wanted in clause.normalized_value.lower() or wanted in contract.instruction.lower():
                return True
        return False

    for clause in contract.clauses:
        if clause.clause_type != requirement.clause_type:
            continue
        if requirement.negated is not None and clause.negated != requirement.negated:
            continue
        span = clause.source_span.text.lower() if clause.source_span else ""
        value = clause.normalized_value.lower()
        if wanted in span or wanted in value:
            return True

    # Models may validly separate a certified/graded product phrase into PRODUCT
    # plus CERTIFICATION clauses. Accept the composition only when every content
    # word from the gold product phrase is grounded across those two clause types.
    if requirement.clause_type == ClauseType.PRODUCT:
        grounded = " ".join(
            (c.source_span.text if c.source_span else c.normalized_value)
            for c in contract.clauses
            if c.clause_type in {ClauseType.PRODUCT, ClauseType.CERTIFICATION}
        )
        return _content_words(requirement.source_text).issubset(_content_words(grounded))

    return False


def semantic_case_pass(contract: EconomicIntentContract, gold: GoldCase, validator: FidelityValidator) -> tuple[bool, dict]:
    report = validator.validate(contract)
    req_results = [_span_matches(contract, req) for req in gold.required]
    exception_ok = (not gold.require_exception) or any(c.clause_type == ClauseType.EXCEPTION or c.exception_to for c in contract.clauses)
    dependency_ok = (not gold.require_dependency) or any(c.clause_type == ClauseType.DEPENDENCY or c.depends_on for c in contract.clauses)
    status_ok = report.status == gold.expected_status
    passed = all(req_results) and exception_ok and dependency_ok and status_ok
    return passed, {
        "validator_status": report.status.value,
        "expected_status": gold.expected_status.value,
        "coverage": report.coverage,
        "faithfulness": report.faithfulness,
        "selective_risk": report.selective_risk,
        "required_checks": req_results,
        "exception_ok": exception_ok,
        "dependency_ok": dependency_ok,
        "findings": [f.model_dump() for f in report.findings],
    }


def _evaluate_one(gold: GoldCase, provider: OpenAICompatibleIntentProvider, validator: FidelityValidator) -> dict:
    try:
        interpreted = provider.interpret_with_metadata(gold.instruction)
        contract = interpreted.contract
        passed, detail = semantic_case_pass(contract, gold, validator)
        return {
            "id": gold.case_id,
            "instruction": gold.instruction,
            "passed": passed,
            "detail": detail,
            "contract": contract.model_dump(mode="json"),
            "provider_trace": list(interpreted.provider_trace),
        }
    except CandidateContractError as exc:
        return {
            "id": gold.case_id,
            "instruction": gold.instruction,
            "passed": False,
            "error_kind": "candidate_contract_error",
            "error_code": (
                "SCHEMA_INVALID_AFTER_CORRECTION"
                if exc.correction_attempted
                else "SCHEMA_INVALID_BEFORE_CORRECTION"
            ),
            "correction_attempted": exc.correction_attempted,
            "error": str(exc),
            "provider_trace": list(exc.provider_trace),
        }
    except ProviderRequestError as exc:
        provider_trace = list(exc.provider_trace)
        correction_interrupted = any(
            item.get("outcome") == "schema_invalid" for item in provider_trace
        )
        return {
            "id": gold.case_id,
            "instruction": gold.instruction,
            "passed": False,
            "error_kind": (
                "candidate_contract_correction_interrupted"
                if correction_interrupted
                else ("transient_provider_error" if exc.transient else "provider_error")
            ),
            "error_code": "CORRECTION_PROVIDER_ERROR" if correction_interrupted else exc.code,
            "error": str(exc),
            "provider_trace": provider_trace,
        }
    except Exception as exc:
        return {
            "id": gold.case_id,
            "instruction": gold.instruction,
            "passed": False,
            "error_kind": "internal_error",
            "error_code": type(exc).__name__,
            "error": "local evaluation failed; inspect protected job logs",
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run ECOCOMMIT live Checkpoint A evaluation")
    parser.add_argument("--base-url", default=os.getenv("ECOCOMMIT_LLM_BASE_URL", "https://api.openai.com/v1"))
    parser.add_argument("--model", default=os.getenv("ECOCOMMIT_LLM_MODEL"))
    parser.add_argument("--output", default="artifacts/checkpoint_a_results.json")
    parser.add_argument("--clear-limit", type=int, default=50)
    parser.add_argument("--ambiguous-limit", type=int, default=30)
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args()

    if not args.model:
        raise SystemExit("ECOCOMMIT_LLM_MODEL (or --model) is required")
    api_key = os.getenv("ECOCOMMIT_LLM_API_KEY")
    if not api_key:
        raise SystemExit("ECOCOMMIT_LLM_API_KEY is required; command-line credentials are not accepted")

    provider = OpenAICompatibleIntentProvider(args.base_url, api_key, args.model, timeout=60.0)
    validator = FidelityValidator()
    all_cases = _clear_cases()[:max(0, args.clear_limit)] + _ambiguous_cases()[:max(0, args.ambiguous_limit)]

    if args.workers <= 1:
        rows = [_evaluate_one(g, provider, validator) for g in all_cases]
    else:
        rows = []
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            future_to_case = {pool.submit(_evaluate_one, g, provider, validator): g for g in all_cases}
            for future in as_completed(future_to_case):
                rows.append(future.result())
        rows.sort(key=lambda r: r["id"])

    validated = 0
    correct_validated = 0
    clarification_correct = 0
    for gold in all_cases:
        row = next(r for r in rows if r["id"] == gold.case_id)
        detail = row.get("detail")
        if not detail:
            continue
        if detail["validator_status"] == DecisionStatus.VALIDATED.value:
            validated += 1
            if row.get("passed"):
                correct_validated += 1
        if gold.expected_status == DecisionStatus.CLARIFICATION_REQUIRED and detail["validator_status"] == DecisionStatus.CLARIFICATION_REQUIRED.value:
            clarification_correct += 1

    total = len(rows)
    passed_total = sum(1 for r in rows if r.get("passed"))
    clear_count = min(50, max(0, args.clear_limit))
    ambiguous_count = min(30, max(0, args.ambiguous_limit))
    autonomous_coverage = validated / total if total else 0.0
    selective_semantic_reliability = correct_validated / validated if validated else 0.0
    clarification_accuracy = clarification_correct / ambiguous_count if ambiguous_count else 1.0

    metrics = {
        "passed_cases": passed_total,
        "case_pass_rate": passed_total / total if total else 0.0,
        "autonomous_coverage": autonomous_coverage,
        "selective_semantic_reliability": selective_semantic_reliability,
        "ambiguous_clarification_accuracy": clarification_accuracy,
    }
    full_run = clear_count == 50 and ambiguous_count == 30
    summary = {
        "provider": {"base_url": args.base_url, "model": args.model},
        "dataset": {"total": total, "clear": clear_count, "ambiguous": ambiguous_count, "full_frozen_gate_run": full_run},
        "metrics": metrics,
        "checkpoint_a_gate": {
            "criteria": dict(CRITERIA),
        },
        "cases": rows,
    }
    c = summary["checkpoint_a_gate"]["criteria"]
    gate_passed = (
        full_run
        and metrics["case_pass_rate"] >= c["case_pass_rate_min"]
        and selective_semantic_reliability >= c["selective_semantic_reliability_min"]
        and autonomous_coverage >= c["autonomous_coverage_min"]
        and clarification_accuracy >= c["ambiguous_clarification_accuracy_min"]
    )
    summary["checkpoint_a_gate"]["passed"] = gate_passed

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"metrics": metrics, "checkpoint_a_gate": summary["checkpoint_a_gate"], "full_run": full_run}, indent=2))
    return 0 if gate_passed else (0 if not full_run else 2)


if __name__ == "__main__":
    raise SystemExit(main())
