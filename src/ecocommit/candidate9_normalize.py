from __future__ import annotations

from .candidate7_flat import FactKind, LabeledFact, Relation, RelationBatch, RelationKind, grounded_span, validate_relations
from .candidate8_normalize import (
    NormalizedCandidate8Input,
    candidate8_dispositions,
    infer_candidate8_relations,
    normalize_candidate8_facts,
)


NormalizedCandidate9Input = NormalizedCandidate8Input
normalize_candidate9_facts = normalize_candidate8_facts
candidate9_dispositions = candidate8_dispositions


def _clause_bounds(instruction: str, start: int, end: int) -> tuple[int, int]:
    left = max(instruction.rfind(";", 0, start), instruction.rfind(".", 0, start)) + 1
    stops = [position for token in (";", ".") if (position := instruction.find(token, end)) >= 0]
    right = min(stops) if stops else len(instruction)
    return left, right


def _cover_span(instruction: str, left: LabeledFact, right: LabeledFact) -> str:
    left_start, left_end = grounded_span(instruction, left.text_span)
    right_start, right_end = grounded_span(instruction, right.text_span)
    return instruction[min(left_start, right_start):max(left_end, right_end)]


def infer_candidate9_relations(instruction: str, facts: tuple[LabeledFact, ...]) -> RelationBatch:
    """Add only uniquely scoped, exact-source fronted modifier relations.

    Candidate 8 already handles modifiers that follow an action. Candidate 9
    closes the source-order gap for fronted constraints and exceptions. A
    relation is added only when exactly one action occurs in the same explicit
    punctuation-delimited clause; competing actions remain unresolved and
    therefore fail closed in the existing disposition layer.
    """
    base = infer_candidate8_relations(instruction, facts)
    relations = list(base.relations)
    signatures = {(relation.kind, relation.left, relation.right) for relation in relations}
    actions = [fact for fact in facts if fact.kind is FactKind.ACTION]

    for modifier, relation_kind in (
        (FactKind.CONSTRAINT, RelationKind.CONSTRAINT_APPLIES_TO),
        (FactKind.EXCEPTION, RelationKind.EXCEPTION_TARGET),
    ):
        for fact in (row for row in facts if row.kind is modifier):
            if any(relation.left == fact.id and relation.kind is relation_kind for relation in relations):
                continue
            start, end = grounded_span(instruction, fact.text_span)
            clause_start, clause_end = _clause_bounds(instruction, start, end)
            candidates = []
            for action in actions:
                action_start, action_end = grounded_span(instruction, action.text_span)
                if clause_start <= action_start and action_end <= clause_end:
                    candidates.append(action)
            if len(candidates) != 1:
                continue
            target = candidates[0]
            signature = (relation_kind, fact.id, target.id)
            if signature not in signatures:
                relations.append(Relation(
                    kind=relation_kind,
                    left=fact.id,
                    right=target.id,
                    justification_span=_cover_span(instruction, fact, target),
                ))
                signatures.add(signature)

    result = RelationBatch(relations=relations)
    validate_relations(facts, result)
    return result
