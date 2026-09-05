from __future__ import annotations

from .candidate7_flat import FactKind, RelationKind
from .candidate7_structure import C7And, C7Atom, C7Graph, C7Not, C7Or, _refs
from .contracts import EconomicIntentContract


class Candidate7ConservationError(RuntimeError):
    pass


def _contains_pair(expr, left: str, right: str, operator: str) -> bool:
    if isinstance(expr, (C7Atom, C7Not)):
        return False
    refs = [_refs(arg) for arg in expr.args]
    if operator == "AND" and isinstance(expr, C7And):
        if any(left in a and right in b or right in a and left in b for i, a in enumerate(refs) for b in refs[i + 1 :]):
            return True
    if operator == "OR" and isinstance(expr, C7Or):
        if left in _refs(expr) and right in _refs(expr):
            return True
    return any(_contains_pair(arg, left, right, operator) for arg in expr.args)


def verify_candidate7_conservation(graph: C7Graph, contract: EconomicIntentContract) -> None:
    by_clause = {clause.clause_id: clause for clause in contract.clauses}
    by_fact = {fact.id: fact for fact in graph.facts}

    for fact in graph.facts:
        if fact.kind is FactKind.AMBIGUITY:
            continue
        if f"c_{fact.id}" not in by_clause and fact.kind not in {FactKind.ACTION}:
            raise Candidate7ConservationError("C7_FACT_CONSERVATION_FAILURE")
        if fact.kind is FactKind.ACTION and f"c_{fact.id}" not in by_clause:
            raise Candidate7ConservationError("C7_ACTION_CONSERVATION_FAILURE")

    guard_by_action = {guard.action_id: guard for guard in graph.guards}

    for relation in graph.relations:
        left_clause = f"c_{relation.left}"
        right_clause = f"c_{relation.right}"
        if relation.kind is RelationKind.ACTION_OBJECT:
            clause = by_clause.get(left_clause)
            if clause is None or right_clause not in clause.depends_on:
                raise Candidate7ConservationError("C7_ACTION_OBJECT_CONSERVATION_FAILURE")
        elif relation.kind is RelationKind.ACTION_COUNTERPARTY:
            clause = by_clause.get(left_clause)
            if clause is None or right_clause not in clause.depends_on:
                raise Candidate7ConservationError("C7_COUNTERPARTY_CONSERVATION_FAILURE")
        elif relation.kind is RelationKind.CONSTRAINT_APPLIES_TO:
            clause = by_clause.get(left_clause)
            if clause is None or right_clause not in clause.depends_on:
                raise Candidate7ConservationError("C7_CONSTRAINT_CONSERVATION_FAILURE")
        elif relation.kind in {RelationKind.GUARDS_ACTION, RelationKind.BLOCKS_ACTION}:
            guard = guard_by_action.get(relation.right)
            clause = by_clause.get(f"g_{relation.right}")
            if guard is None or relation.left not in _refs(guard.expr):
                raise Candidate7ConservationError("C7_GUARD_CONSERVATION_FAILURE")
            if clause is None or left_clause not in clause.depends_on or right_clause not in clause.depends_on:
                raise Candidate7ConservationError("C7_GUARD_CONSERVATION_FAILURE")
        elif relation.kind in {RelationKind.ALL_OF, RelationKind.ANY_OF}:
            containing = [g for g in graph.guards if relation.left in _refs(g.expr) and relation.right in _refs(g.expr)]
            expected = "AND" if relation.kind is RelationKind.ALL_OF else "OR"
            if not containing or not any(_contains_pair(g.expr, relation.left, relation.right, expected) for g in containing):
                raise Candidate7ConservationError("C7_BOOLEAN_RELATION_CONSERVATION_FAILURE")
        elif relation.kind in {RelationKind.AFTER_COMPLETION, RelationKind.AFTER_SUCCESS}:
            cid = f"d_{relation.left}_{relation.right}"
            clause = by_clause.get(cid)
            if clause is None or right_clause not in clause.depends_on or left_clause not in clause.depends_on:
                raise Candidate7ConservationError("C7_DEPENDENCY_CONSERVATION_FAILURE")
        elif relation.kind is RelationKind.EXCEPTION_TARGET:
            clause = by_clause.get(left_clause)
            if clause is None or right_clause not in clause.exception_to:
                raise Candidate7ConservationError("C7_EXCEPTION_TARGET_CONSERVATION_FAILURE")
        elif relation.kind is RelationKind.EXCEPTION_WHEN:
            exception_clause = by_clause.get(right_clause)
            if exception_clause is None or left_clause not in exception_clause.depends_on:
                raise Candidate7ConservationError("C7_EXCEPTION_CONDITION_CONSERVATION_FAILURE")
        elif relation.kind is RelationKind.AMBIGUITY_TARGET:
            ambiguity = by_fact[relation.left]
            target = by_fact[relation.right]
            if ambiguity.kind is not FactKind.AMBIGUITY:
                raise Candidate7ConservationError("C7_AMBIGUITY_CONSERVATION_FAILURE")
            if target.kind is FactKind.ACTION and target.id not in graph.blocked_actions:
                raise Candidate7ConservationError("C7_AMBIGUITY_CONSERVATION_FAILURE")

    if any(f.kind is FactKind.AMBIGUITY for f in graph.facts) and not graph.blocked_actions:
        raise Candidate7ConservationError("C7_AMBIGUITY_FAIL_OPEN")
