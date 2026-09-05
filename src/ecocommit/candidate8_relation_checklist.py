from __future__ import annotations

import re

from .candidate7_flat import FactKind, LabeledFact, RelationBatch, RelationKind, grounded_span
from .candidate7_relation_checklist import (
    ActionEntityDecisionKind,
    Pass2DecisionBatch,
    validate_and_materialize_pass2 as validate_and_materialize_candidate7,
)
from .candidate8_logic import C8FactDisposition


_DETERMINER_ONLY = re.compile(
    r"^[\s,;:\-]*(?:(?:the|a|an|this|that|these|those)\b[\s,;:\-]*)*$",
    re.IGNORECASE,
)
_TRAILING_CONTEXT_MARKER = re.compile(r"\b(?:for|if|after|before|because|when|while|during|about)\s*$", re.I)


def _source_locality(instruction: str, action: LabeledFact, entity: LabeledFact) -> tuple[bool, bool, str]:
    action_start, action_end = grounded_span(instruction, action.text_span)
    entity_start, entity_end = grounded_span(instruction, entity.text_span)
    embedded = action_start <= entity_start and entity_end <= action_end
    gap = instruction[action_end:entity_start] if entity_start >= action_end else ""
    bare_after = entity_start >= action_end and bool(_DETERMINER_ONLY.fullmatch(gap))
    return embedded, bare_after, gap


def _validate_direct_object_role(
    instruction: str,
    facts: tuple[LabeledFact, ...],
    batch: Pass2DecisionBatch,
) -> None:
    """Reject counterpart labels for bare source-local grammatical objects.

    Candidate-8 defines ACTION_OBJECT by source syntax rather than by whether the
    noun denotes a person, organization, payee, vendor, or other participant.
    The verifier never rewrites a model decision; it rejects inconsistent role
    evidence so the bounded correction attempt can reconsider it.
    """
    by_id = {fact.id: fact for fact in facts}
    for decision in batch.action_entity_decisions:
        if decision.decision is not ActionEntityDecisionKind.ACTION_COUNTERPARTY:
            continue
        action = by_id[decision.action]
        entity = by_id[decision.entity]
        embedded, bare_after, _ = _source_locality(instruction, action, entity)
        if embedded or bare_after:
            raise ValueError("C8_DIRECT_OBJECT_MISCLASSIFIED_AS_COUNTERPARTY")


def _validate_relation_grounding(instruction: str, batch: Pass2DecisionBatch) -> None:
    """Reject, rather than silently drop, semantically asserted ungrounded relations."""
    for relation in batch.relations:
        if relation.justification_span not in instruction:
            raise ValueError("C8_UNGROUNDED_RELATION_JUSTIFICATION")


def semantic_dispositions(
    instruction: str,
    facts: tuple[LabeledFact, ...],
    relations: RelationBatch,
) -> dict[str, C8FactDisposition]:
    """Classify every fact as semantically USED or explicitly IRRELEVANT.

    Material facts cannot disappear.  Entities may be irrelevant only when they
    are demonstrably non-local context and are not referenced by any semantic edge.
    """
    by_id = {fact.id: fact for fact in facts}
    refs = {relation.left for relation in relations.relations} | {relation.right for relation in relations.relations}
    actions = tuple(fact for fact in facts if fact.kind is FactKind.ACTION)
    dispositions: dict[str, C8FactDisposition] = {}

    for fact in facts:
        if fact.kind is FactKind.ACTION:
            dispositions[fact.id] = C8FactDisposition.USED
            continue

        if fact.kind is FactKind.CONSTRAINT:
            targets = [
                r.right for r in relations.relations
                if r.kind is RelationKind.CONSTRAINT_APPLIES_TO and r.left == fact.id
            ]
            if len(targets) != 1:
                raise ValueError("C8_REQUIRED_CONSTRAINT_TARGET_MISSING")
            dispositions[fact.id] = C8FactDisposition.USED
            continue

        if fact.kind is FactKind.PREDICATE:
            uses = [
                r for r in relations.relations
                if fact.id in {r.left, r.right}
                and r.kind in {
                    RelationKind.PREDICATE_SUBJECT,
                    RelationKind.GUARDS_ACTION,
                    RelationKind.BLOCKS_ACTION,
                    RelationKind.EXCEPTION_WHEN,
                    RelationKind.ALL_OF,
                    RelationKind.ANY_OF,
                    RelationKind.AMBIGUITY_TARGET,
                }
            ]
            if not uses:
                raise ValueError("C8_REQUIRED_PREDICATE_UNUSED")
            dispositions[fact.id] = C8FactDisposition.USED
            continue

        if fact.kind is FactKind.EXCEPTION:
            targets = [
                r.right for r in relations.relations
                if r.kind is RelationKind.EXCEPTION_TARGET and r.left == fact.id
            ]
            if len(targets) != 1:
                raise ValueError("C8_REQUIRED_EXCEPTION_TARGET_MISSING")
            dispositions[fact.id] = C8FactDisposition.USED
            continue

        if fact.kind is FactKind.AMBIGUITY:
            # Untargeted ambiguity is still semantically used: Candidate-7 graph
            # construction blocks every action in that fail-closed case.
            dispositions[fact.id] = C8FactDisposition.USED
            continue

        if fact.kind is FactKind.ENTITY:
            if fact.id in refs:
                dispositions[fact.id] = C8FactDisposition.USED
                continue

            # An unreferenced entity that is source-local to an action is unsafe:
            # the relation classifier failed to account for a plausible operand.
            local = False
            for action in actions:
                embedded, bare_after, _ = _source_locality(instruction, action, fact)
                if embedded or bare_after:
                    local = True
                    break
            if local:
                raise ValueError("C8_UNLINKED_SOURCE_LOCAL_ENTITY")

            # Non-local context can be classified irrelevant only when its source
            # placement is introduced as trailing context. This is deliberately
            # narrow and fail-closed; it does not infer an economic role.
            entity_start, _ = grounded_span(instruction, fact.text_span)
            prefix = instruction[:entity_start]
            if _TRAILING_CONTEXT_MARKER.search(prefix):
                dispositions[fact.id] = C8FactDisposition.IRRELEVANT
                continue
            raise ValueError("C8_ENTITY_DISPOSITION_UNRESOLVED")

        raise ValueError("C8_UNKNOWN_FACT_KIND")

    if set(dispositions) != set(by_id):
        raise ValueError("C8_FACT_DISPOSITION_COVERAGE")
    return dispositions


def validate_and_materialize_pass2(
    instruction: str,
    facts: tuple[LabeledFact, ...],
    batch: Pass2DecisionBatch,
) -> tuple[RelationBatch, dict[str, C8FactDisposition]]:
    _validate_direct_object_role(instruction, facts, batch)
    _validate_relation_grounding(instruction, batch)
    materialized = validate_and_materialize_candidate7(instruction, facts, batch)
    dispositions = semantic_dispositions(instruction, facts, materialized)
    return materialized, dispositions
