from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .candidate7_flat import FactKind, LabeledFact, Relation, RelationBatch, RelationKind


class C8RelationType(str, Enum):
    ROLE_OBJECT = "ROLE_OBJECT"
    ROLE_COUNTERPARTY = "ROLE_COUNTERPARTY"
    REQUIRES = "REQUIRES"
    ALTERNATIVE = "ALTERNATIVE"
    CONJUNCTION = "CONJUNCTION"
    CONDITIONAL = "CONDITIONAL"
    NEGATES = "NEGATES"
    BEFORE = "BEFORE"
    AFTER = "AFTER"
    SUBJECT_TO = "SUBJECT_TO"
    AMBIGUOUS = "AMBIGUOUS"
    PREDICATE_SUBJECT = "PREDICATE_SUBJECT"
    EXCEPTION_TARGET = "EXCEPTION_TARGET"
    EXCEPTION_WHEN = "EXCEPTION_WHEN"


class C8FactDisposition(str, Enum):
    USED = "USED"
    IRRELEVANT = "IRRELEVANT"


@dataclass(frozen=True)
class C8Edge:
    relation: C8RelationType
    left: str
    right: str
    source_kind: str


@dataclass(frozen=True)
class C8LogicalAST:
    fact_ids: tuple[str, ...]
    edges: tuple[C8Edge, ...]
    dispositions: tuple[tuple[str, C8FactDisposition], ...]


_MAP = {
    RelationKind.ACTION_OBJECT: C8RelationType.ROLE_OBJECT,
    RelationKind.ACTION_COUNTERPARTY: C8RelationType.ROLE_COUNTERPARTY,
    RelationKind.PREDICATE_SUBJECT: C8RelationType.PREDICATE_SUBJECT,
    RelationKind.CONSTRAINT_APPLIES_TO: C8RelationType.SUBJECT_TO,
    RelationKind.GUARDS_ACTION: C8RelationType.CONDITIONAL,
    RelationKind.BLOCKS_ACTION: C8RelationType.NEGATES,
    RelationKind.AFTER_COMPLETION: C8RelationType.AFTER,
    RelationKind.AFTER_SUCCESS: C8RelationType.REQUIRES,
    RelationKind.EXCEPTION_TARGET: C8RelationType.EXCEPTION_TARGET,
    RelationKind.EXCEPTION_WHEN: C8RelationType.EXCEPTION_WHEN,
    RelationKind.AMBIGUITY_TARGET: C8RelationType.AMBIGUOUS,
    RelationKind.ALL_OF: C8RelationType.CONJUNCTION,
    RelationKind.ANY_OF: C8RelationType.ALTERNATIVE,
}


def _dependency_cycle(edges: tuple[C8Edge, ...]) -> bool:
    graph: dict[str, set[str]] = {}
    for edge in edges:
        if edge.relation not in {C8RelationType.REQUIRES, C8RelationType.AFTER}:
            continue
        graph.setdefault(edge.left, set()).add(edge.right)
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> bool:
        if node in visiting:
            return True
        if node in visited:
            return False
        visiting.add(node)
        if any(visit(parent) for parent in graph.get(node, ())):
            return True
        visiting.remove(node)
        visited.add(node)
        return False

    return any(visit(node) for node in graph)


def build_typed_ast(
    facts: tuple[LabeledFact, ...],
    relations: RelationBatch,
    dispositions: dict[str, C8FactDisposition],
) -> C8LogicalAST:
    ids = {fact.id for fact in facts}
    if set(dispositions) != ids:
        raise ValueError("C8_FACT_DISPOSITION_COVERAGE")

    edges = tuple(
        C8Edge(_MAP[relation.kind], relation.left, relation.right, relation.kind.value)
        for relation in relations.relations
    )
    for edge in edges:
        if edge.left not in ids or edge.right not in ids:
            raise ValueError("C8_DANGLING_RELATION")

    used_refs = {edge.left for edge in edges} | {edge.right for edge in edges}
    by_id = {fact.id: fact for fact in facts}
    for fact_id, disposition in dispositions.items():
        fact = by_id[fact_id]
        if disposition is C8FactDisposition.IRRELEVANT and fact_id in used_refs:
            raise ValueError("C8_IRRELEVANT_FACT_REFERENCED")
        if disposition is C8FactDisposition.IRRELEVANT and fact.kind in {
            FactKind.ACTION, FactKind.CONSTRAINT, FactKind.PREDICATE, FactKind.EXCEPTION, FactKind.AMBIGUITY,
        }:
            raise ValueError("C8_MATERIAL_FACT_MARKED_IRRELEVANT")

    if _dependency_cycle(edges):
        raise ValueError("IR_DEPENDENCY_CYCLE")

    return C8LogicalAST(
        tuple(fact.id for fact in facts),
        edges,
        tuple(sorted(dispositions.items(), key=lambda item: item[0])),
    )


def verify_ast_conservation(ast: C8LogicalAST, relations: RelationBatch) -> None:
    source = sorted((r.kind.value, r.left, r.right) for r in relations.relations)
    restored = sorted((edge.source_kind, edge.left, edge.right) for edge in ast.edges)
    if source != restored:
        raise ValueError("C8_AST_CONSERVATION_FAILURE")
