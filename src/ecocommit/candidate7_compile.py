from __future__ import annotations

import re
from decimal import Decimal

from .candidate7_flat import FactKind, RelationKind, grounded_span
from .candidate7_structure import C7Graph, _action_kind, _canonical, _constraint_kind, _money, _refs
from .contracts import ClauseType, EconomicClause, EconomicIntentContract, Hardness, Provenance, SourceSpan


_NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
    "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
    "twenty": 20,
}


def _quantity(action_text: str, object_text: str | None) -> tuple[Decimal, str] | None:
    lowered = action_text.lower()
    if re.search(r"\bminus\s+(?:\d+(?:\.\d+)?|" + "|".join(_NUMBER_WORDS) + r")\b", lowered):
        raise ValueError("C7_QUANTITY_INVALID")
    if object_text is None:
        return None
    object_lower = object_text.lower()
    object_pos = lowered.find(object_lower)
    prefix = lowered[:object_pos] if object_pos >= 0 else lowered
    candidates = list(re.finditer(r"\b(?:\d+(?:\.\d+)?|" + "|".join(_NUMBER_WORDS) + r")\b", prefix))
    if not candidates:
        return None
    token = candidates[-1].group(0)
    value = Decimal(_NUMBER_WORDS[token]) if token in _NUMBER_WORDS else Decimal(token)
    if value <= 0:
        raise ValueError("C7_QUANTITY_INVALID")
    tokens = re.findall(r"[a-z]+", object_lower)
    unit = tokens[-1] if tokens else "unit"
    if unit.endswith("s") and len(unit) > 2:
        unit = unit[:-1]
    return value, unit


def _source_span(graph: C7Graph, fact_id: str) -> SourceSpan:
    fact = next(f for f in graph.facts if f.id == fact_id)
    start, end = grounded_span(graph.instruction, fact.text_span)
    return SourceSpan(text=fact.text_span.quote, start=start, end=end)


def _clause(graph: C7Graph, cid: str, typ: ClauseType, value: str, source_fact_id: str, *, depends: tuple[str, ...] = (), exceptions: tuple[str, ...] = ()) -> EconomicClause:
    return EconomicClause(
        clause_id=cid,
        clause_type=typ,
        normalized_value=value,
        source_span=_source_span(graph, source_fact_id),
        provenance=Provenance.EXPLICIT_USER,
        materiality=1.0,
        confidence=1.0,
        hardness=Hardness.HARD,
        depends_on=list(depends),
        exception_to=list(exceptions),
    )


def _dependency_cycle(graph: C7Graph) -> bool:
    edges: dict[str, set[str]] = {}
    for dep in graph.dependencies:
        edges.setdefault(dep.action_id, set()).add(dep.prerequisite_action_id)
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> bool:
        if node in visiting:
            return True
        if node in visited:
            return False
        visiting.add(node)
        if any(visit(parent) for parent in edges.get(node, ())):
            return True
        visiting.remove(node)
        visited.add(node)
        return False

    return any(visit(node) for node in list(edges))


def validate_graph_semantics(graph: C7Graph) -> None:
    by_id = {f.id: f for f in graph.facts}
    if _dependency_cycle(graph):
        raise ValueError("IR_DEPENDENCY_CYCLE")

    constraints_by_action: dict[str, list[tuple[str, Decimal]]] = {}
    for fact in graph.facts:
        if fact.kind is not FactKind.CONSTRAINT:
            continue
        targets = [r.right for r in graph.relations if r.kind is RelationKind.CONSTRAINT_APPLIES_TO and r.left == fact.id]
        if len(targets) != 1:
            raise ValueError("C7_CONSTRAINT_TARGET_CARDINALITY")
        kind = _constraint_kind(fact.text_span.quote)
        amount, _ = _money(fact.text_span.quote)
        constraints_by_action.setdefault(targets[0], []).append((kind, amount))

    for entries in constraints_by_action.values():
        maximums = [amount for kind, amount in entries if kind in {"MAX_TOTAL_COST", "EXACT_TOTAL_COST"}]
        minimums = [amount for kind, amount in entries if kind in {"MIN_TOTAL_COST", "EXACT_TOTAL_COST"}]
        exact = [amount for kind, amount in entries if kind == "EXACT_TOTAL_COST"]
        max_only = [amount for kind, amount in entries if kind == "MAX_TOTAL_COST"]
        min_only = [amount for kind, amount in entries if kind == "MIN_TOTAL_COST"]
        if exact and len(set(exact)) > 1:
            raise ValueError("IR_CONTRADICTORY_CONSTRAINTS")
        if minimums and maximums and max(minimums) > min(maximums):
            raise ValueError("IR_CONTRADICTORY_CONSTRAINTS")
        if exact and max_only and exact[0] > min(max_only):
            raise ValueError("IR_CONTRADICTORY_CONSTRAINTS")
        if exact and min_only and exact[0] < max(min_only):
            raise ValueError("IR_CONTRADICTORY_CONSTRAINTS")

    for fact in graph.facts:
        if fact.kind is FactKind.ACTION:
            objects = [r.right for r in graph.relations if r.kind is RelationKind.ACTION_OBJECT and r.left == fact.id]
            if len(objects) > 1:
                raise ValueError("C7_ACTION_OBJECT_CARDINALITY")
            if objects and by_id[objects[0]].kind is not FactKind.ENTITY:
                raise ValueError("C7_ACTION_OBJECT_KIND")
            _action_kind(fact.text_span.quote)
            _quantity(fact.text_span.quote, by_id[objects[0]].text_span.quote if objects else None)


def compile_graph_v2(graph: C7Graph) -> EconomicIntentContract:
    validate_graph_semantics(graph)
    by_id = {f.id: f for f in graph.facts}
    clause_ids = {f.id: f"c_{f.id}" for f in graph.facts}
    clauses: list[EconomicClause] = []

    for fact in graph.facts:
        if fact.kind is FactKind.ENTITY:
            is_counterparty = any(r.kind is RelationKind.ACTION_COUNTERPARTY and r.right == fact.id for r in graph.relations)
            clauses.append(_clause(graph, clause_ids[fact.id], ClauseType.COUNTERPARTY if is_counterparty else ClauseType.PRODUCT, fact.text_span.quote, fact.id))

    for fact in graph.facts:
        if fact.kind is not FactKind.ACTION:
            continue
        objects = [r.right for r in graph.relations if r.kind is RelationKind.ACTION_OBJECT and r.left == fact.id]
        counterparties = [r.right for r in graph.relations if r.kind is RelationKind.ACTION_COUNTERPARTY and r.left == fact.id]
        if len(counterparties) > 1:
            raise ValueError("C7_ACTION_COUNTERPARTY_CARDINALITY")
        deps = tuple(clause_ids[x] for x in objects + counterparties)
        clauses.append(_clause(graph, clause_ids[fact.id], ClauseType.AUTHORIZATION, _action_kind(fact.text_span.quote), fact.id, depends=deps))
        q = _quantity(fact.text_span.quote, by_id[objects[0]].text_span.quote if objects else None)
        if q is not None:
            amount, unit = q
            clauses.append(_clause(graph, f"c_{fact.id}_quantity", ClauseType.QUANTITY, f"{amount.normalize()} {unit}", fact.id, depends=(clause_ids[fact.id],)))

    for fact in graph.facts:
        if fact.kind is FactKind.CONSTRAINT:
            target = next(r.right for r in graph.relations if r.kind is RelationKind.CONSTRAINT_APPLIES_TO and r.left == fact.id)
            amount, currency = _money(fact.text_span.quote)
            value = f"{_constraint_kind(fact.text_span.quote)}:{currency}:{amount.normalize()}"
            clauses.append(_clause(graph, clause_ids[fact.id], ClauseType.AMOUNT, value, fact.id, depends=(clause_ids[target],)))
        elif fact.kind is FactKind.PREDICATE:
            clauses.append(_clause(graph, clause_ids[fact.id], ClauseType.CONDITION, fact.text_span.quote.strip().lower(), fact.id))

    for guard in graph.guards:
        refs = tuple(sorted(_refs(guard.expr)))
        clauses.append(_clause(graph, f"g_{guard.action_id}", ClauseType.DEPENDENCY, "ONLY_IF:" + _canonical(guard.expr), refs[0], depends=tuple(clause_ids[x] for x in refs) + (clause_ids[guard.action_id],)))

    for dep in graph.dependencies:
        clauses.append(_clause(graph, f"d_{dep.action_id}_{dep.prerequisite_action_id}", ClauseType.DEPENDENCY, dep.relation, dep.action_id, depends=(clause_ids[dep.prerequisite_action_id], clause_ids[dep.action_id])))

    for fact in graph.facts:
        if fact.kind is not FactKind.EXCEPTION:
            continue
        targets = [r.right for r in graph.relations if r.kind is RelationKind.EXCEPTION_TARGET and r.left == fact.id]
        if len(targets) != 1:
            raise ValueError("C7_EXCEPTION_TARGET_CARDINALITY")
        conditions = sorted(r.left for r in graph.relations if r.kind is RelationKind.EXCEPTION_WHEN and r.right == fact.id)
        text = fact.text_span.quote
        if "₹" in text and re.search(r"\b(?:add|above|extra|up to)\b", text, re.I):
            amount, currency = _money(text)
            effect = f"ADD_MONETARY_ALLOWANCE:{currency}:{amount.normalize()}"
        else:
            effect = "BLOCK_ACTION"
        when = "TRUE" if not conditions else "AND(" + ",".join(conditions) + ")"
        clauses.append(_clause(graph, clause_ids[fact.id], ClauseType.EXCEPTION, f"{effect}:WHEN:{when}", fact.id, depends=tuple(clause_ids[x] for x in conditions), exceptions=(clause_ids[targets[0]],)))

    return EconomicIntentContract(instruction=graph.instruction, clauses=clauses)
