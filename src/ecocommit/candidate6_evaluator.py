from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from .candidate6 import Candidate6Result, action_authorized
from .qualification import QualificationCounts, QualificationThresholds, final_pass, reachable
from .semantic_ir import Truth, normalize_money, normalize_quantity
from .semantic_validation import refs_expr


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def _decimal_text(value: Decimal) -> str:
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _expr_stats(expr) -> dict[str, Any]:
    if expr.op == "ATOM":
        return {"root": "ATOM", "atoms": 1, "not": 0, "ops": {"ATOM"}}
    if expr.op == "NOT":
        child = _expr_stats(expr.arg)
        return {"root": "NOT", "atoms": child["atoms"], "not": child["not"] + 1, "ops": child["ops"] | {"NOT"}}
    children = [_expr_stats(x) for x in expr.args]
    return {
        "root": expr.op,
        "atoms": sum(x["atoms"] for x in children),
        "not": sum(x["not"] for x in children),
        "ops": set().union(*(x["ops"] for x in children)) | {expr.op},
    }


def _action_matches(ir, candidate, expected: dict[str, Any]) -> bool:
    if candidate.kind.value != expected["kind"]:
        return False
    entity = next((e for e in ir.entities if e.id == candidate.object), None)
    searchable = (entity.text if entity else "") + " " + candidate.source.quote
    if expected.get("object_terms") and not set(expected["object_terms"]) <= _tokens(searchable):
        return False
    if "quantity" in expected:
        if candidate.quantity is None:
            return False
        try:
            value, _ = normalize_quantity(candidate.quantity.raw_value, candidate.quantity.raw_unit)
        except ValueError:
            return False
        if _decimal_text(value) != str(expected["quantity"]):
            return False
    return True


def _match_actions(ir, expected: list[dict[str, Any]]) -> bool:
    if len(ir.actions) != len(expected):
        return False
    remaining = list(ir.actions)
    for gold in expected:
        index = next((i for i, action in enumerate(remaining) if _action_matches(ir, action, gold)), None)
        if index is None:
            return False
        remaining.pop(index)
    return not remaining


def _match_constraints(ir, expected: list[list[str]]) -> bool:
    actual = []
    for constraint in ir.constraints:
        try:
            amount, currency = normalize_money(constraint.money.raw_amount, constraint.money.raw_currency)
        except ValueError:
            return False
        actual.append((constraint.kind.value, _decimal_text(amount), currency))
    gold = [(kind, amount, "INR") for kind, amount in expected]
    return sorted(actual) == sorted(gold)


def _match_guards(ir, expected: list[dict[str, Any]]) -> bool:
    if len(ir.guards) != len(expected):
        return False
    remaining = list(ir.guards)
    predicates = {p.id: p for p in ir.predicates}
    for gold in expected:
        matched_index = None
        for i, guard in enumerate(remaining):
            stats = _expr_stats(guard.expr)
            if stats["root"] != gold["root"] or stats["atoms"] != gold["atoms"]:
                continue
            if stats["not"] < gold.get("min_not", 0):
                continue
            if gold.get("contains_root") and gold["contains_root"] not in stats["ops"]:
                continue
            source_text = " ".join(predicates[p].source.quote for p in refs_expr(guard.expr) if p in predicates)
            if not set(gold.get("terms", [])) <= _tokens(source_text):
                continue
            matched_index = i
            break
        if matched_index is None:
            return False
        remaining.pop(matched_index)
    return not remaining


def _match_exceptions(ir, expected: list[dict[str, Any]]) -> bool:
    if len(ir.exceptions) != len(expected):
        return False
    predicates = {p.id: p for p in ir.predicates}
    remaining = list(ir.exceptions)
    for gold in expected:
        match = None
        for i, exception in enumerate(remaining):
            if exception.effect.effect != gold["effect"]:
                continue
            source_text = exception.source.quote + " " + " ".join(predicates[p].source.quote for p in refs_expr(exception.when) if p in predicates)
            if not set(gold.get("terms", [])) <= _tokens(source_text):
                continue
            if "amount" in gold:
                if exception.effect.effect != "ADD_MONETARY_ALLOWANCE":
                    continue
                try:
                    amount, _ = normalize_money(exception.effect.money.raw_amount, exception.effect.money.raw_currency)
                except ValueError:
                    continue
                if _decimal_text(amount) != str(gold["amount"]):
                    continue
            match = i
            break
        if match is None:
            return False
        remaining.pop(match)
    return not remaining


def semantic_match(result: Candidate6Result, gold: dict[str, Any]) -> tuple[bool, list[str]]:
    expected_status = gold["expected_status"]
    expected = gold["gold_semantic_ir"]
    reasons: list[str] = []
    if result.status != expected_status:
        return False, [f"status:{result.status}!={expected_status}"]
    if expected_status == "REJECTED":
        code = expected.get("reject_code")
        ok = bool(code and result.error_code and code in result.error_code)
        return ok, [] if ok else [f"reject_code:{result.error_code}"]
    ir = result.semantic_ir
    if ir is None:
        return False, ["missing_ir"]
    if expected_status == "CLARIFICATION_REQUIRED":
        allowed = set(expected.get("ambiguity_any", []))
        actual = {a.kind.value for a in ir.ambiguities}
        if allowed and not (allowed & actual):
            reasons.append(f"ambiguity:{sorted(actual)}")
        if not result.blocked_actions:
            reasons.append("ambiguity_not_materially_blocking")
        return not reasons, reasons

    if "actions" in expected and not _match_actions(ir, expected["actions"]):
        reasons.append("actions")
    if "constraints" in expected and not _match_constraints(ir, expected["constraints"]):
        reasons.append("constraints")
    if "guards" in expected and not _match_guards(ir, expected["guards"]):
        reasons.append("guards")
    elif "guards" not in expected and ir.guards:
        reasons.append("unexpected_guards")
    if "dependencies" in expected:
        if len(ir.dependencies) != int(expected["dependencies"]):
            reasons.append("dependencies")
    elif ir.dependencies:
        reasons.append("unexpected_dependencies")
    if "exceptions" in expected and not _match_exceptions(ir, expected["exceptions"]):
        reasons.append("exceptions")
    elif "exceptions" not in expected and ir.exceptions:
        reasons.append("unexpected_exceptions")
    if ir.ambiguities:
        reasons.append("unexpected_ambiguity")
    return not reasons, reasons


@dataclass(frozen=True)
class CaseScore:
    case_id: str
    expected_status: str
    observed_status: str
    semantic_correct: bool
    reasons: tuple[str, ...]
    fail_open: bool
    dropped_guard: bool
    dropped_exception: bool
    conservation_failure: bool
    unknown_authorized: bool


def score_case(case_id: str, result: Candidate6Result, gold: dict[str, Any]) -> CaseScore:
    correct, reasons = semantic_match(result, gold)
    expected = gold["gold_semantic_ir"]
    ir = result.semantic_ir
    dropped_guard = bool(expected.get("guards")) and (ir is None or len(ir.guards) < len(expected["guards"]))
    dropped_exception = bool(expected.get("exceptions")) and (ir is None or len(ir.exceptions) < len(expected["exceptions"]))
    fail_open = gold["expected_status"] != "COMPILED" and result.status == "COMPILED"
    conservation_failure = bool(result.error_code and "CONSERVATION" in result.error_code)
    unknown_authorized = False
    if ir is not None:
        guarded_actions = {g.action for g in ir.guards}
        exception_actions = {x.target.id for x in ir.exceptions if x.target.kind == "ACTION" and x.effect.effect == "BLOCK_ACTION"}
        for action_id in guarded_actions | exception_actions:
            if action_authorized(ir, action_id, {}) is True:
                unknown_authorized = True
                break
    return CaseScore(case_id, gold["expected_status"], result.status, correct, tuple(reasons), fail_open, dropped_guard, dropped_exception, conservation_failure, unknown_authorized)


def aggregate(scores: list[CaseScore], gold_rows: list[dict[str, Any]], thresholds: QualificationThresholds = QualificationThresholds()) -> dict[str, Any]:
    gold_by_id = {row["case_id"]: row for row in gold_rows}
    ambiguous_total = sum(1 for row in gold_rows if row["expected_status"] == "CLARIFICATION_REQUIRED")
    case_passes = sum(s.semantic_correct for s in scores)
    autonomous = sum(s.observed_status == "COMPILED" for s in scores)
    correct_autonomous = sum(s.observed_status == "COMPILED" and s.semantic_correct for s in scores)
    ambiguous_processed = sum(gold_by_id[s.case_id]["expected_status"] == "CLARIFICATION_REQUIRED" for s in scores)
    ambiguous_correct = sum(gold_by_id[s.case_id]["expected_status"] == "CLARIFICATION_REQUIRED" and s.semantic_correct for s in scores)
    counts = QualificationCounts(
        total=len(gold_rows), processed=len(scores), case_passes=case_passes,
        autonomous=autonomous, correct_autonomous=correct_autonomous,
        ambiguous_total=ambiguous_total, ambiguous_processed=ambiguous_processed,
        ambiguous_correct=ambiguous_correct, fail_open=sum(s.fail_open for s in scores),
        dropped_guards=sum(s.dropped_guard for s in scores), dropped_exceptions=sum(s.dropped_exception for s in scores),
        conservation_failures=sum(s.conservation_failure for s in scores), unknown_authorized=sum(s.unknown_authorized for s in scores),
    )
    rel = correct_autonomous / autonomous if autonomous else 0.0
    clar = ambiguous_correct / ambiguous_total if ambiguous_total else 1.0
    return {
        "counts": counts.__dict__,
        "metrics": {
            "case_pass_rate": case_passes / len(gold_rows) if gold_rows else 0.0,
            "selective_semantic_reliability": rel,
            "autonomous_coverage": autonomous / len(gold_rows) if gold_rows else 0.0,
            "ambiguous_clarification_accuracy": clar,
        },
        "reachable": reachable(counts, thresholds),
        "passed": final_pass(counts, thresholds),
        "thresholds": thresholds.__dict__,
    }
