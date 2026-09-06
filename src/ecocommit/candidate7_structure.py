from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Iterable, Mapping

from .candidate7_flat import (
    FactKind,
    LabeledFact,
    Polarity,
    Relation,
    RelationBatch,
    RelationKind,
    grounded_span,
    validate_relations,
)
from .contracts import ClauseType, EconomicClause, EconomicIntentContract, Hardness, Provenance, SourceSpan


class C7Truth(str, Enum):
    TRUE = "TRUE"
    FALSE = "FALSE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class C7Atom:
    fact_id: str


@dataclass(frozen=True)
class C7Not:
    arg: "C7Expr"


@dataclass(frozen=True)
class C7And:
    args: tuple["C7Expr", ...]


@dataclass(frozen=True)
class C7Or:
    args: tuple["C7Expr", ...]


C7Expr = C7Atom | C7Not | C7And | C7Or


@dataclass(frozen=True)
class C7Guard:
    action_id: str
    expr: C7Expr
    source_fact_ids: tuple[str, ...]


@dataclass(frozen=True)
class C7Dependency:
    action_id: str
    prerequisite_action_id: str
    relation: str


@dataclass(frozen=True)
class C7Graph:
    instruction: str
    facts: tuple[LabeledFact, ...]
    relations: tuple[Relation, ...]
    guards: tuple[C7Guard, ...]
    dependencies: tuple[C7Dependency, ...]
    blocked_actions: frozenset[str]


_ACTION_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("BUY", ("buy", "purchase")),
    ("ORDER", ("order", "place order")),
    ("PAY", ("pay", "payment")),
    ("TRANSFER", ("transfer",)),
    ("HIRE", ("hire",)),
    ("BOOK", ("book", "booking")),
    ("RENEW", ("renew", "renewal")),
    ("RESERVE", ("reserve", "reservation")),
    ("SELECT", ("select", "choose")),
    ("RELEASE", ("release",)),
    ("CANCEL", ("cancel",)),
    ("COMMIT", ("commit", "spend", "proceed")),
)

_NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
    "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
    "twenty": 20,
}


def _action_kind(text: str) -> str:
    lowered = text.lower()
    for kind, terms in _ACTION_PATTERNS:
        if any(re.search(rf"\b{re.escape(term)}\b", lowered) for term in terms):
            return kind
    raise ValueError("C7_ACTION_KIND_UNSUPPORTED")


def _money(text: str) -> tuple[Decimal, str]:
    if "$" in text:
        raise ValueError("C7_CURRENCY_AMBIGUOUS")
    match = re.search(r"(?:₹|\b(?:rs\.?|inr)\s*)\s*([+-]?(?:\d+(?:,\d{3})*|\d*\.\d+)\s*(?:lakh|lakhs|crore|crores)?)", text, re.I)
    if not match:
        if re.search(r"₹\s*nan", text, re.I):
            raise ValueError("C7_MONEY_INVALID")
        raise ValueError("C7_MONEY_MISSING")
    raw = match.group(1).strip().lower().replace(",", "")
    multiplier = Decimal(1)
    for suffix, factor in (("lakhs", 100000), ("lakh", 100000), ("crores", 10000000), ("crore", 10000000)):
        if raw.endswith(suffix):
            raw = raw[: -len(suffix)].strip()
            multiplier = Decimal(factor)
            break
    try:
        value = Decimal(raw) * multiplier
    except InvalidOperation as exc:
        raise ValueError("C7_MONEY_INVALID") from exc
    if not value.is_finite() or value < 0:
        raise ValueError("C7_MONEY_INVALID")
    return value, "INR"


def _constraint_kind(text: str) -> str:
    lowered = text.lower()
    if "exactly" in lowered:
        return "EXACT_TOTAL_COST"
    if any(term in lowered for term in ("at least", "no less than", "minimum")):
        return "MIN_TOTAL_COST"
    if any(term in lowered for term in ("each", "per unit", "per item")) and any(term in lowered for term in ("no more", "at most", "or less", "maximum")):
        return "MAX_UNIT_COST"
    if any(term in lowered for term in ("no more", "at most", "or less", "never more", "maximum", "up to")):
        return "MAX_TOTAL_COST"
    raise ValueError("C7_CONSTRAINT_KIND_UNSUPPORTED")


def _quantity(action_text: str, object_text: str) -> tuple[Decimal, str] | None:
    lowered = action_text.lower()
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
    unit_tokens = re.findall(r"[a-z]+", object_lower)
    unit = unit_tokens[-1] if unit_tokens else "unit"
    if unit.endswith("s") and len(unit) > 2:
        unit = unit[:-1]
    return value, unit


def _canonical(expr: C7Expr) -> str:
    if isinstance(expr, C7Atom):
        return expr.fact_id
    if isinstance(expr, C7Not):
        return f"NOT({_canonical(expr.arg)})"
    op = "AND" if isinstance(expr, C7And) else "OR"
    return f"{op}(" + ",".join(_canonical(arg) for arg in expr.args) + ")"


def _refs(expr: C7Expr) -> set[str]:
    if isinstance(expr, C7Atom):
        return {expr.fact_id}
    if isinstance(expr, C7Not):
        return _refs(expr.arg)
    refs: set[str] = set()
    for arg in expr.args:
        refs |= _refs(arg)
    return refs


def _term(fact: LabeledFact) -> C7Expr:
    atom: C7Expr = C7Atom(fact.id)
    if fact.polarity is Polarity.NEGATED:
        atom = C7Not(atom)
    return atom


def _build_guard_expr(predicate_ids: list[str], by_id: Mapping[str, LabeledFact], relations: Iterable[Relation], blocks: set[str]) -> C7Expr:
    if not predicate_ids:
        raise ValueError("C7_EMPTY_GUARD")
    terms = {pid: _term(by_id[pid]) for pid in predicate_ids}
    for pid in blocks:
        terms[pid] = C7Not(terms[pid])
    if len(predicate_ids) == 1:
        return terms[predicate_ids[0]]

    pair_logic: dict[frozenset[str], RelationKind] = {}
    for rel in relations:
        if rel.kind in {RelationKind.ALL_OF, RelationKind.ANY_OF} and rel.left in terms and rel.right in terms:
            pair_logic[frozenset({rel.left, rel.right})] = rel.kind

    if not pair_logic:
        raise ValueError("C7_BOOLEAN_RELATION_MISSING")

    # ANY_OF components become deterministic OR subtrees. Remaining predicates/components
    # are combined by AND only when every cross-component relation is ALL_OF or omitted
    # by transitivity. Contradictory pair labels were already rejected.
    adjacency: dict[str, set[str]] = {pid: set() for pid in predicate_ids}
    for pair, kind in pair_logic.items():
        if kind is RelationKind.ANY_OF:
            a, b = tuple(pair)
            adjacency[a].add(b)
            adjacency[b].add(a)

    components: list[list[str]] = []
    unseen = set(predicate_ids)
    while unseen:
        root = min(unseen)
        stack = [root]
        component: set[str] = set()
        while stack:
            cur = stack.pop()
            if cur in component:
                continue
            component.add(cur)
            stack.extend(adjacency[cur] - component)
        unseen -= component
        components.append(sorted(component))

    built: list[C7Expr] = []
    for component in sorted(components, key=lambda x: x[0]):
        if len(component) == 1:
            built.append(terms[component[0]])
        else:
            built.append(C7Or(tuple(terms[pid] for pid in component)))

    if len(built) == 1:
        return built[0]

    for i, left_component in enumerate(components):
        for right_component in components[i + 1 :]:
            explicit = {
                pair_logic.get(frozenset({left, right}))
                for left in left_component
                for right in right_component
                if frozenset({left, right}) in pair_logic
            }
            if RelationKind.ANY_OF in explicit:
                raise ValueError("C7_BOOLEAN_STRUCTURE_CONTRADICTORY")
            if explicit and explicit != {RelationKind.ALL_OF}:
                raise ValueError("C7_BOOLEAN_STRUCTURE_CONTRADICTORY")
    return C7And(tuple(built))


def build_graph(instruction: str, facts: tuple[LabeledFact, ...], relation_batch: RelationBatch) -> C7Graph:
    validate_relations(facts, relation_batch)
    for fact in facts:
        grounded_span(instruction, fact.text_span)

    by_id = {fact.id: fact for fact in facts}
    actions = {fact.id for fact in facts if fact.kind is FactKind.ACTION}
    if not actions:
        raise ValueError("C7_NO_ACTION")

    guards: list[C7Guard] = []
    blocks_by_action: dict[str, set[str]] = {aid: set() for aid in actions}
    predicates_by_action: dict[str, set[str]] = {aid: set() for aid in actions}
    for rel in relation_batch.relations:
        if rel.kind is RelationKind.GUARDS_ACTION:
            predicates_by_action[rel.right].add(rel.left)
        elif rel.kind is RelationKind.BLOCKS_ACTION:
            predicates_by_action[rel.right].add(rel.left)
            blocks_by_action[rel.right].add(rel.left)

    for action_id in sorted(actions):
        predicate_ids = sorted(predicates_by_action[action_id])
        if predicate_ids:
            expr = _build_guard_expr(predicate_ids, by_id, relation_batch.relations, blocks_by_action[action_id])
            guards.append(C7Guard(action_id, expr, tuple(sorted(_refs(expr)))))

    dependencies = tuple(
        C7Dependency(rel.left, rel.right, rel.kind.value)
        for rel in relation_batch.relations
        if rel.kind in {RelationKind.AFTER_COMPLETION, RelationKind.AFTER_SUCCESS}
    )

    blocked: set[str] = set()
    ambiguity_targets = [rel for rel in relation_batch.relations if rel.kind is RelationKind.AMBIGUITY_TARGET]
    ambiguity_ids = {fact.id for fact in facts if fact.kind is FactKind.AMBIGUITY}
    targeted_ambiguities = {rel.left for rel in ambiguity_targets}
    if ambiguity_ids - targeted_ambiguities:
        blocked |= actions
    for rel in ambiguity_targets:
        target = by_id[rel.right]
        if target.kind is FactKind.ACTION:
            blocked.add(target.id)
        elif target.kind is FactKind.CONSTRAINT:
            blocked |= {
                r.right for r in relation_batch.relations
                if r.kind is RelationKind.CONSTRAINT_APPLIES_TO and r.left == target.id
            }
        elif target.kind is FactKind.PREDICATE:
            blocked |= {
                r.right for r in relation_batch.relations
                if r.kind in {RelationKind.GUARDS_ACTION, RelationKind.BLOCKS_ACTION} and r.left == target.id
            }
        elif target.kind is FactKind.ENTITY:
            blocked |= {
                r.left for r in relation_batch.relations
                if r.kind in {RelationKind.ACTION_OBJECT, RelationKind.ACTION_COUNTERPARTY} and r.right == target.id
            }

    return C7Graph(instruction, facts, tuple(relation_batch.relations), tuple(guards), dependencies, frozenset(blocked))


def _source_span(instruction: str, fact: LabeledFact) -> SourceSpan:
    start, end = grounded_span(instruction, fact.text_span)
    return SourceSpan(text=fact.text_span.quote, start=start, end=end)


def _clause(cid: str, clause_type: ClauseType, value: str, instruction: str, fact: LabeledFact, *, depends: tuple[str, ...] = (), exceptions: tuple[str, ...] = ()) -> EconomicClause:
    return EconomicClause(
        clause_id=cid,
        clause_type=clause_type,
        normalized_value=value,
        source_span=_source_span(instruction, fact),
        provenance=Provenance.EXPLICIT_USER,
        materiality=1.0,
        confidence=1.0,
        hardness=Hardness.HARD,
        depends_on=list(depends),
        exception_to=list(exceptions),
    )


def compile_graph(graph: C7Graph) -> EconomicIntentContract:
    by_id = {fact.id: fact for fact in graph.facts}
    relations = graph.relations
    clauses: list[EconomicClause] = []
    clause_id = {fact.id: f"c_{fact.id}" for fact in graph.facts}

    for fact in graph.facts:
        if fact.kind is FactKind.ENTITY:
            counterparty = any(r.kind is RelationKind.ACTION_COUNTERPARTY and r.right == fact.id for r in relations)
            clauses.append(_clause(clause_id[fact.id], ClauseType.COUNTERPARTY if counterparty else ClauseType.PRODUCT, fact.text_span.quote, graph.instruction, fact))

    for fact in graph.facts:
        if fact.kind is not FactKind.ACTION:
            continue
        objects = [r.right for r in relations if r.kind is RelationKind.ACTION_OBJECT and r.left == fact.id]
        if len(objects) != 1:
            raise ValueError("C7_ACTION_OBJECT_CARDINALITY")
        counterparties = [r.right for r in relations if r.kind is RelationKind.ACTION_COUNTERPARTY and r.left == fact.id]
        if len(counterparties) > 1:
            raise ValueError("C7_ACTION_COUNTERPARTY_CARDINALITY")
        deps = tuple(clause_id[x] for x in objects + counterparties)
        clauses.append(_clause(clause_id[fact.id], ClauseType.AUTHORIZATION, _action_kind(fact.text_span.quote), graph.instruction, fact, depends=deps))
        q = _quantity(fact.text_span.quote, by_id[objects[0]].text_span.quote)
        if q is not None:
            value, unit = q
            clauses.append(_clause(f"c_{fact.id}_quantity", ClauseType.QUANTITY, f"{value.normalize()} {unit}", graph.instruction, fact, depends=(clause_id[fact.id],)))

    for fact in graph.facts:
        if fact.kind is FactKind.CONSTRAINT:
            targets = [r.right for r in relations if r.kind is RelationKind.CONSTRAINT_APPLIES_TO and r.left == fact.id]
            if len(targets) != 1:
                raise ValueError("C7_CONSTRAINT_TARGET_CARDINALITY")
            amount, currency = _money(fact.text_span.quote)
            value = f"{_constraint_kind(fact.text_span.quote)}:{currency}:{amount.normalize()}"
            clauses.append(_clause(clause_id[fact.id], ClauseType.AMOUNT, value, graph.instruction, fact, depends=(clause_id[targets[0]],)))

    for fact in graph.facts:
        if fact.kind is FactKind.PREDICATE:
            clauses.append(_clause(clause_id[fact.id], ClauseType.CONDITION, fact.text_span.quote.strip().lower(), graph.instruction, fact))

    for guard in graph.guards:
        source_fact = by_id[guard.source_fact_ids[0]]
        deps = tuple(clause_id[x] for x in guard.source_fact_ids) + (clause_id[guard.action_id],)
        clauses.append(_clause(f"g_{guard.action_id}", ClauseType.DEPENDENCY, "ONLY_IF:" + _canonical(guard.expr), graph.instruction, source_fact, depends=deps))

    for dep in graph.dependencies:
        fact = by_id[dep.action_id]
        clauses.append(_clause(f"d_{dep.action_id}_{dep.prerequisite_action_id}", ClauseType.DEPENDENCY, dep.relation, graph.instruction, fact, depends=(clause_id[dep.prerequisite_action_id], clause_id[dep.action_id])))

    for fact in graph.facts:
        if fact.kind is not FactKind.EXCEPTION:
            continue
        targets = [r.right for r in relations if r.kind is RelationKind.EXCEPTION_TARGET and r.left == fact.id]
        if len(targets) != 1:
            raise ValueError("C7_EXCEPTION_TARGET_CARDINALITY")
        conditions = [r.left for r in relations if r.kind is RelationKind.EXCEPTION_WHEN and r.right == fact.id]
        text = fact.text_span.quote
        if re.search(r"\b(?:add|additional|above|extra|up to)\b", text, re.I) and "₹" in text:
            amount, currency = _money(text)
            effect = f"ADD_MONETARY_ALLOWANCE:{currency}:{amount.normalize()}"
        else:
            effect = "BLOCK_ACTION"
        when = "TRUE" if not conditions else "AND(" + ",".join(sorted(conditions)) + ")"
        deps = tuple(clause_id[x] for x in sorted(conditions))
        clauses.append(_clause(clause_id[fact.id], ClauseType.EXCEPTION, f"{effect}:WHEN:{when}", graph.instruction, fact, depends=deps, exceptions=(clause_id[targets[0]],)))

    return EconomicIntentContract(instruction=graph.instruction, clauses=clauses)


def eval_expr(expr: C7Expr, predicate_values: Mapping[str, C7Truth]) -> C7Truth:
    if isinstance(expr, C7Atom):
        return predicate_values.get(expr.fact_id, C7Truth.UNKNOWN)
    if isinstance(expr, C7Not):
        value = eval_expr(expr.arg, predicate_values)
        return {C7Truth.TRUE: C7Truth.FALSE, C7Truth.FALSE: C7Truth.TRUE, C7Truth.UNKNOWN: C7Truth.UNKNOWN}[value]
    values = [eval_expr(arg, predicate_values) for arg in expr.args]
    if isinstance(expr, C7And):
        if C7Truth.FALSE in values:
            return C7Truth.FALSE
        if C7Truth.UNKNOWN in values:
            return C7Truth.UNKNOWN
        return C7Truth.TRUE
    if C7Truth.TRUE in values:
        return C7Truth.TRUE
    if C7Truth.UNKNOWN in values:
        return C7Truth.UNKNOWN
    return C7Truth.FALSE
