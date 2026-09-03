from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .contracts import (
    ClauseType,
    EconomicClause,
    EconomicIntentContract,
    Hardness,
    Provenance,
    SourceSpan,
)
from .semantic_ir import SemanticIR, normalize_money, normalize_quantity
from .semantic_validation import blocked_actions, canonical_expr, refs_expr, validate_semantic_ir


@dataclass(frozen=True)
class ConservationEdge:
    source_id: str
    destination_id: str
    relationship: str


class ConservationError(RuntimeError):
    pass


def _decimal_text(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _span(instruction, source):
    cursor = 0
    start = -1
    for _ in range(source.occurrence):
        start = instruction.find(source.quote, cursor)
        if start < 0:
            raise ConservationError("IR_SOURCE_UNGROUNDED")
        cursor = start + len(source.quote)
    return SourceSpan(text=source.quote, start=start, end=start + len(source.quote))


def _clause(cid, typ, value, instruction, source, *, depends=(), exceptions=()):
    return EconomicClause(
        clause_id=cid,
        clause_type=typ,
        normalized_value=value,
        source_span=_span(instruction, source),
        provenance=Provenance.EXPLICIT_USER,
        materiality=1.0,
        confidence=1.0,
        hardness=Hardness.HARD,
        depends_on=list(depends),
        exception_to=list(exceptions),
    )


def compile_contract(ir: SemanticIR, instruction: str) -> tuple[EconomicIntentContract, tuple[ConservationEdge, ...], set[str]]:
    validate_semantic_ir(ir, instruction)
    clauses: list[EconomicClause] = []
    edges: list[ConservationEdge] = []

    entity_clause: dict[str, str] = {}
    for entity in ir.entities:
        typ = ClauseType.COUNTERPARTY if entity.kind.value == "COUNTERPARTY" else ClauseType.PRODUCT
        cid = "ir_" + entity.id
        clauses.append(_clause(cid, typ, entity.text, instruction, entity.source))
        entity_clause[entity.id] = cid
        edges.append(ConservationEdge(entity.id, cid, "entity"))

    action_anchor: dict[str, str] = {}
    for action in ir.actions:
        cid = "ir_" + action.id
        action_anchor[action.id] = cid
        relationships = [entity_clause[action.object]]
        if action.counterparty:
            relationships.append(entity_clause[action.counterparty])
        clauses.append(_clause(cid, ClauseType.AUTHORIZATION, action.kind.value, instruction, action.source, depends=tuple(relationships)))
        edges.append(ConservationEdge(action.id, cid, f"action-object:{entity_clause[action.object]}"))
        if action.counterparty:
            edges.append(ConservationEdge(f"{action.id}.counterparty", cid, f"action-counterparty:{entity_clause[action.counterparty]}"))
        if action.quantity:
            value, unit = normalize_quantity(action.quantity.raw_value, action.quantity.raw_unit)
            qid = cid + "_quantity"
            clauses.append(_clause(qid, ClauseType.QUANTITY, f"{_decimal_text(value)} {unit}", instruction, action.quantity.source, depends=(cid,)))
            edges.append(ConservationEdge(f"{action.id}.quantity", qid, "quantity"))

    constraint_clause: dict[str, str] = {}
    for constraint in ir.constraints:
        amount, currency = normalize_money(constraint.money.raw_amount, constraint.money.raw_currency)
        cid = "ir_" + constraint.id
        constraint_clause[constraint.id] = cid
        value = f"{constraint.kind.value}:{currency}:{_decimal_text(amount)}"
        clauses.append(_clause(cid, ClauseType.AMOUNT, value, instruction, constraint.money.source, depends=(action_anchor[constraint.action],)))
        edges.append(ConservationEdge(constraint.id, cid, f"constraint-action:{action_anchor[constraint.action]}"))

    pred_clause: dict[str, str] = {}
    for predicate in ir.predicates:
        cid = "ir_" + predicate.id
        pred_clause[predicate.id] = cid
        parts = (predicate.kind.value, predicate.operator.value, predicate.attribute, predicate.value)
        value = ":".join(str(x) for x in parts if x is not None)
        clauses.append(_clause(cid, ClauseType.CONDITION, value, instruction, predicate.source))
        edges.append(ConservationEdge(predicate.id, cid, "predicate"))

    guard_clause: dict[str, str] = {}
    for guard in ir.guards:
        cid = "ir_" + guard.id
        guard_clause[guard.id] = cid
        predicate_deps = tuple(pred_clause[x] for x in sorted(refs_expr(guard.expr)))
        canon = canonical_expr(guard.expr)
        clauses.append(_clause(cid, ClauseType.DEPENDENCY, "ONLY_IF:" + canon, instruction, guard.source, depends=predicate_deps + (action_anchor[guard.action],)))
        edges.append(ConservationEdge(guard.id, cid, "guard:" + canon))
        edges.append(ConservationEdge(f"{guard.id}.action", cid, f"guard-action:{action_anchor[guard.action]}"))

    dependency_clause: dict[str, str] = {}
    for dep in ir.dependencies:
        cid = "ir_" + dep.id
        dependency_clause[dep.id] = cid
        clauses.append(_clause(cid, ClauseType.DEPENDENCY, dep.relation, instruction, dep.source, depends=(action_anchor[dep.prerequisite_action], action_anchor[dep.action])))
        edges.append(ConservationEdge(dep.id, cid, f"dependency:{action_anchor[dep.prerequisite_action]}->{action_anchor[dep.action]}:{dep.relation}"))

    for exception in ir.exceptions:
        cid = "ir_" + exception.id
        target = "ir_" + exception.target.id
        predicate_deps = tuple(pred_clause[x] for x in sorted(refs_expr(exception.when)))
        canon = canonical_expr(exception.when)
        effect = exception.effect.effect
        if effect == "ADD_MONETARY_ALLOWANCE":
            amount, currency = normalize_money(exception.effect.money.raw_amount, exception.effect.money.raw_currency)
            effect += f":{currency}:{_decimal_text(amount)}"
            edges.append(ConservationEdge(f"{exception.id}.allowance", cid, effect))
        value = f"{effect}:WHEN:{canon}"
        clauses.append(_clause(cid, ClauseType.EXCEPTION, value, instruction, exception.source, depends=predicate_deps, exceptions=(target,)))
        edges.append(ConservationEdge(exception.id, cid, f"exception-target:{target}:when:{canon}"))

    blocked = blocked_actions(ir)
    for ambiguity in ir.ambiguities:
        destination = "NON_EXECUTABLE"
        if ambiguity.target.id in action_anchor:
            destination = action_anchor[ambiguity.target.id]
        edges.append(ConservationEdge(ambiguity.id, destination, f"ambiguity:{ambiguity.target.kind}:{ambiguity.target.field or ''}"))

    contract = EconomicIntentContract(instruction=instruction, clauses=clauses)
    verify_conservation(ir, contract, edges)
    return contract, tuple(edges), blocked


def verify_conservation(ir: SemanticIR, contract: EconomicIntentContract, edges: list[ConservationEdge]) -> None:
    expected: set[str] = set()
    expected |= {x.id for group in (ir.entities, ir.actions, ir.constraints, ir.predicates, ir.guards, ir.dependencies, ir.exceptions, ir.ambiguities) for x in group}
    expected |= {f"{a.id}.quantity" for a in ir.actions if a.quantity is not None}
    expected |= {f"{a.id}.counterparty" for a in ir.actions if a.counterparty is not None}
    expected |= {f"{g.id}.action" for g in ir.guards}
    expected |= {f"{x.id}.allowance" for x in ir.exceptions if x.effect.effect == "ADD_MONETARY_ALLOWANCE"}

    covered = {edge.source_id for edge in edges}
    if expected - covered:
        raise ConservationError("SEMANTIC_CONSERVATION_FAILURE")

    destinations = {c.clause_id for c in contract.clauses} | {"NON_EXECUTABLE"}
    if any(edge.destination_id not in destinations for edge in edges):
        raise ConservationError("SEMANTIC_CONSERVATION_FAILURE")

    by_id = {c.clause_id: c for c in contract.clauses}
    for edge in edges:
        if edge.destination_id == "NON_EXECUTABLE":
            continue
        clause = by_id[edge.destination_id]
        rel = edge.relationship
        if rel.startswith("action-object:") and rel.split(":", 1)[1] not in clause.depends_on:
            raise ConservationError("RELATIONSHIP_CONSERVATION_FAILURE")
        if rel.startswith("action-counterparty:") and rel.split(":", 1)[1] not in clause.depends_on:
            raise ConservationError("RELATIONSHIP_CONSERVATION_FAILURE")
        if rel.startswith("guard:") and rel.split(":", 1)[1] not in clause.normalized_value:
            raise ConservationError("RELATIONSHIP_CONSERVATION_FAILURE")
        if rel.startswith("guard-action:") and rel.split(":", 1)[1] not in clause.depends_on:
            raise ConservationError("RELATIONSHIP_CONSERVATION_FAILURE")
        if rel.startswith("exception-target:"):
            target = rel.split(":", 2)[1]
            canon = rel.split(":when:", 1)[1]
            if target not in clause.exception_to or canon not in clause.normalized_value:
                raise ConservationError("RELATIONSHIP_CONSERVATION_FAILURE")
        if rel.startswith("ADD_MONETARY_ALLOWANCE") and rel not in clause.normalized_value:
            raise ConservationError("RELATIONSHIP_CONSERVATION_FAILURE")
