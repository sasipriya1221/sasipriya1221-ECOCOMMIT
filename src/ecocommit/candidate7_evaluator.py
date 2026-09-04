from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from .candidate7 import Candidate7Result
from .candidate7_compile import _quantity
from .candidate7_flat import FactKind, RelationKind
from .candidate7_structure import C7And, C7Atom, C7Not, C7Or, C7Truth, _action_kind, _constraint_kind, _money, _refs, eval_expr
from .qualification import QualificationCounts, QualificationThresholds, final_pass, reachable


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def _decimal_text(value: Decimal) -> str:
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _expr_stats(expr) -> dict[str, Any]:
    if isinstance(expr, C7Atom):
        return {"root": "ATOM", "atoms": 1, "not": 0, "ops": {"ATOM"}}
    if isinstance(expr, C7Not):
        child = _expr_stats(expr.arg)
        return {"root": "NOT", "atoms": child["atoms"], "not": child["not"] + 1, "ops": child["ops"] | {"NOT"}}
    children = [_expr_stats(x) for x in expr.args]
    root = "AND" if isinstance(expr, C7And) else "OR"
    return {
        "root": root,
        "atoms": sum(x["atoms"] for x in children),
        "not": sum(x["not"] for x in children),
        "ops": set().union(*(x["ops"] for x in children)) | {root},
    }


def _ambiguity_labels(text: str) -> set[str]:
    lowered = text.lower()
    labels: set[str] = set()
    if any(term in lowered for term in ("reasonable number", "adequate number", "how many", "number of")):
        labels.add("UNDEFINED_QUANTITY")
    if any(term in lowered for term in ("affordable", "normal departmental budget", "above the limit", "whatever is needed", "budget", "limit")):
        labels.add("UNDEFINED_BUDGET")
    if any(term in lowered for term in ("high-quality", "affordable", "suitable", "appropriate", "reasonable", "adequate")):
        labels.add("SUBJECTIVE_SELECTION_CRITERION")
    if any(term in lowered for term in ("if necessary", "if appropriate", "whatever", "commercially sensible", "regardless", "somewhat")):
        labels.add("VAGUE_PERMISSION")
    if any(term in lowered for term in ("acceptable", "unclear condition", "ambiguous condition")):
        labels.add("AMBIGUOUS_CONDITION")
    if any(term in lowered for term in ("whichever", "suitable vendor", "appropriate contractor", "provider")):
        labels.add("UNCLEAR_COUNTERPARTY")
    if "$" in text:
        labels |= {"MISSING_REQUIRED_INFORMATION", "UNDEFINED_BUDGET"}
    if any(term in lowered for term in ("regardless", "commercially sensible", "whatever")):
        labels.add("UNSUPPORTED_SEMANTIC_STRUCTURE")
    return labels or {"MISSING_REQUIRED_INFORMATION"}


def _action_rows(result: Candidate7Result) -> list[tuple[Any, str, str | None, tuple[Decimal, str] | None]]:
    graph = result.graph
    if graph is None:
        return []
    by_id = {f.id: f for f in graph.facts}
    rows = []
    for fact in graph.facts:
        if fact.kind is not FactKind.ACTION:
            continue
        objects = [r.right for r in graph.relations if r.kind is RelationKind.ACTION_OBJECT and r.left == fact.id]
        object_text = by_id[objects[0]].text_span.quote if len(objects) == 1 else None
        try:
            quantity = _quantity(fact.text_span.quote, object_text)
            kind = _action_kind(fact.text_span.quote)
        except ValueError:
            quantity = None
            kind = "UNSUPPORTED"
        rows.append((fact, kind, object_text, quantity))
    return rows


def _match_actions(result: Candidate7Result, expected: list[dict[str, Any]]) -> bool:
    actual = _action_rows(result)
    if len(actual) != len(expected):
        return False
    remaining = list(actual)
    for gold in expected:
        match = None
        for i, (fact, kind, object_text, quantity) in enumerate(remaining):
            if kind != gold["kind"]:
                continue
            searchable = f"{object_text or ''} {fact.text_span.quote}"
            if gold.get("object_terms") and not set(gold["object_terms"]) <= _tokens(searchable):
                continue
            if "quantity" in gold:
                if quantity is None or _decimal_text(quantity[0]) != str(gold["quantity"]):
                    continue
            match = i
            break
        if match is None:
            return False
        remaining.pop(match)
    return not remaining


def _match_constraints(result: Candidate7Result, expected: list[list[str]]) -> bool:
    graph = result.graph
    if graph is None:
        return False
    actual = []
    for fact in graph.facts:
        if fact.kind is FactKind.CONSTRAINT:
            try:
                amount, currency = _money(fact.text_span.quote)
                kind = _constraint_kind(fact.text_span.quote)
            except ValueError:
                return False
            actual.append((kind, _decimal_text(amount), currency))
    gold = [(kind, amount, "INR") for kind, amount in expected]
    return sorted(actual) == sorted(gold)


def _match_guards(result: Candidate7Result, expected: list[dict[str, Any]]) -> bool:
    graph = result.graph
    if graph is None or len(graph.guards) != len(expected):
        return False
    by_id = {f.id: f for f in graph.facts}
    remaining = list(graph.guards)
    for gold in expected:
        matched = None
        for i, guard in enumerate(remaining):
            stats = _expr_stats(guard.expr)
            if stats["root"] != gold["root"] or stats["atoms"] != gold["atoms"]:
                continue
            if stats["not"] < gold.get("min_not", 0):
                continue
            if gold.get("contains_root") and gold["contains_root"] not in stats["ops"]:
                continue
            text = " ".join(by_id[p].text_span.quote for p in sorted(_refs(guard.expr)))
            if not set(gold.get("terms", [])) <= _tokens(text):
                continue
            matched = i
            break
        if matched is None:
            return False
        remaining.pop(matched)
    return not remaining


def _match_exceptions(result: Candidate7Result, expected: list[dict[str, Any]]) -> bool:
    graph = result.graph
    if graph is None or result.contract is None:
        return False
    exception_facts = [f for f in graph.facts if f.kind is FactKind.EXCEPTION]
    if len(exception_facts) != len(expected):
        return False
    by_clause = {c.clause_id: c for c in result.contract.clauses}
    remaining = list(exception_facts)
    for gold in expected:
        matched = None
        for i, fact in enumerate(remaining):
            clause = by_clause.get(f"c_{fact.id}")
            if clause is None or not clause.normalized_value.startswith(gold["effect"]):
                continue
            condition_ids = [r.left for r in graph.relations if r.kind is RelationKind.EXCEPTION_WHEN and r.right == fact.id]
            by_id = {f.id: f for f in graph.facts}
            text = fact.text_span.quote + " " + " ".join(by_id[x].text_span.quote for x in condition_ids)
            if not set(gold.get("terms", [])) <= _tokens(text):
                continue
            if "amount" in gold and str(gold["amount"]) not in clause.normalized_value:
                continue
            matched = i
            break
        if matched is None:
            return False
        remaining.pop(matched)
    return not remaining


def semantic_match(result: Candidate7Result, gold: dict[str, Any]) -> tuple[bool, list[str]]:
    expected_status = gold["expected_status"]
    expected = gold["gold_semantic_ir"]
    reasons: list[str] = []
    if result.status != expected_status:
        return False, [f"status:{result.status}!={expected_status}"]
    if expected_status == "REJECTED":
        expected_code = expected.get("reject_code", "")
        aliases = {
            "IR_QUANTITY_INVALID": {"IR_QUANTITY_INVALID", "C7_QUANTITY_INVALID"},
            "IR_MONEY_INVALID": {"IR_MONEY_INVALID", "C7_MONEY_INVALID", "C7_MONEY_MISSING"},
        }
        accepted = aliases.get(expected_code, {expected_code})
        ok = any(code and result.error_code and code in result.error_code for code in accepted)
        return ok, [] if ok else [f"reject_code:{result.error_code}"]
    if result.graph is None:
        return False, ["missing_graph"]
    if expected_status == "CLARIFICATION_REQUIRED":
        allowed = set(expected.get("ambiguity_any", []))
        actual: set[str] = set()
        for fact in result.graph.facts:
            if fact.kind is FactKind.AMBIGUITY:
                actual |= _ambiguity_labels(fact.text_span.quote)
        if allowed and not (allowed & actual):
            reasons.append(f"ambiguity:{sorted(actual)}")
        if not result.blocked_actions:
            reasons.append("ambiguity_not_materially_blocking")
        return not reasons, reasons

    if "actions" in expected and not _match_actions(result, expected["actions"]):
        reasons.append("actions")
    if "constraints" in expected and not _match_constraints(result, expected["constraints"]):
        reasons.append("constraints")
    if "guards" in expected and not _match_guards(result, expected["guards"]):
        reasons.append("guards")
    elif "guards" not in expected and result.graph.guards:
        reasons.append("unexpected_guards")
    if "dependencies" in expected:
        if len(result.graph.dependencies) != int(expected["dependencies"]):
            reasons.append("dependencies")
    elif result.graph.dependencies:
        reasons.append("unexpected_dependencies")
    if "exceptions" in expected and not _match_exceptions(result, expected["exceptions"]):
        reasons.append("exceptions")
    elif "exceptions" not in expected and any(f.kind is FactKind.EXCEPTION for f in result.graph.facts):
        reasons.append("unexpected_exceptions")
    if any(f.kind is FactKind.AMBIGUITY for f in result.graph.facts):
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


def score_case(case_id: str, result: Candidate7Result, gold: dict[str, Any]) -> CaseScore:
    correct, reasons = semantic_match(result, gold)
    expected = gold["gold_semantic_ir"]
    graph = result.graph
    dropped_guard = bool(expected.get("guards")) and (graph is None or len(graph.guards) < len(expected["guards"]))
    dropped_exception = bool(expected.get("exceptions")) and (graph is None or sum(f.kind is FactKind.EXCEPTION for f in graph.facts) < len(expected["exceptions"]))
    fail_open = gold["expected_status"] != "COMPILED" and result.status == "COMPILED"
    conservation_failure = bool(result.error_code and "CONSERVATION" in result.error_code)
    unknown_authorized = False
    if graph is not None:
        for guard in graph.guards:
            if guard.action_id not in graph.blocked_actions and eval_expr(guard.expr, {}) is C7Truth.TRUE:
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
    return {
        "counts": counts.__dict__,
        "metrics": {
            "case_pass_rate": case_passes / len(gold_rows) if gold_rows else 0.0,
            "selective_semantic_reliability": correct_autonomous / autonomous if autonomous else 0.0,
            "autonomous_coverage": autonomous / len(gold_rows) if gold_rows else 0.0,
            "ambiguous_clarification_accuracy": ambiguous_correct / ambiguous_total if ambiguous_total else 1.0,
        },
        "reachable": reachable(counts, thresholds),
        "passed": final_pass(counts, thresholds),
        "thresholds": thresholds.__dict__,
    }
