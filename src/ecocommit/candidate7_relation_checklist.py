from __future__ import annotations

import re
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .candidate7_flat import (
    FactKind,
    LabeledFact,
    Relation,
    RelationBatch,
    RelationKind,
    grounded_span,
    validate_relations,
)


class ActionEntityDecisionKind(str, Enum):
    ACTION_OBJECT = "ACTION_OBJECT"
    ACTION_COUNTERPARTY = "ACTION_COUNTERPARTY"
    NONE = "NONE"


class ActionEntityDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: str = Field(pattern=r"^F\d{4}$")
    entity: str = Field(pattern=r"^F\d{4}$")
    decision: ActionEntityDecisionKind
    justification_span: str | None = None

    @model_validator(mode="after")
    def justification_matches_decision(self) -> "ActionEntityDecision":
        if self.decision is ActionEntityDecisionKind.NONE:
            if self.justification_span not in {None, ""}:
                raise ValueError("C7_NONE_DECISION_HAS_JUSTIFICATION")
        elif not self.justification_span:
            raise ValueError("C7_RELATION_DECISION_MISSING_JUSTIFICATION")
        return self


class Pass2DecisionBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action_entity_decisions: list[ActionEntityDecision] = Field(default_factory=list)
    relations: list[Relation] = Field(default_factory=list)


def action_entity_pairs(facts: tuple[LabeledFact, ...]) -> tuple[tuple[str, str], ...]:
    actions = [fact.id for fact in facts if fact.kind is FactKind.ACTION]
    entities = [fact.id for fact in facts if fact.kind is FactKind.ENTITY]
    return tuple((action_id, entity_id) for action_id in actions for entity_id in entities)


def action_entity_pair_payload(facts: tuple[LabeledFact, ...]) -> list[dict[str, str]]:
    return [{"action": action, "entity": entity} for action, entity in action_entity_pairs(facts)]


def _source_locality(
    instruction: str,
    action: LabeledFact,
    entity: LabeledFact,
) -> tuple[bool, bool, str]:
    action_start, action_end = grounded_span(instruction, action.text_span)
    entity_start, entity_end = grounded_span(instruction, entity.text_span)
    embedded = action_start <= entity_start and entity_end <= action_end
    gap = instruction[action_end:entity_start] if entity_start >= action_end else ""
    immediately_after = entity_start >= action_end and not gap.strip()
    return embedded, immediately_after, gap


def _validate_source_positions(
    instruction: str,
    facts: tuple[LabeledFact, ...],
    decisions: tuple[ActionEntityDecision, ...],
) -> None:
    by_id = {fact.id: fact for fact in facts}
    by_action: dict[str, list[ActionEntityDecision]] = {}
    for decision in decisions:
        by_action.setdefault(decision.action, []).append(decision)

    for action_id, action_decisions in by_action.items():
        action = by_id[action_id]
        local: list[ActionEntityDecision] = []
        for decision in action_decisions:
            entity = by_id[decision.entity]
            embedded, immediately_after, _ = _source_locality(instruction, action, entity)
            if embedded and decision.decision is not ActionEntityDecisionKind.ACTION_OBJECT:
                raise ValueError("C7_ACTION_LOCAL_ENTITY_WRONG_ROLE")
            if embedded or immediately_after:
                local.append(decision)

        # Conservative inversion guard: if an immediately source-local entity is
        # demoted to COUNTERPARTY while a later entity introduced by a trailing
        # purpose/condition/sequence marker is promoted to OBJECT, reject and let
        # the existing bounded correction attempt reconsider the classifications.
        # The verifier never creates a relation itself.
        local_counterparties = [
            d for d in local if d.decision is ActionEntityDecisionKind.ACTION_COUNTERPARTY
        ]
        if not local_counterparties:
            continue
        for decision in action_decisions:
            if decision.decision is not ActionEntityDecisionKind.ACTION_OBJECT:
                continue
            entity = by_id[decision.entity]
            entity_start, _ = grounded_span(instruction, entity.text_span)
            prefix = instruction[:entity_start]
            if re.search(r"\b(?:for|if|after)\s*$", prefix, re.I):
                raise ValueError("C7_ACTION_OBJECT_NOT_SOURCE_LOCAL")


def validate_and_materialize_pass2(
    instruction: str,
    facts: tuple[LabeledFact, ...],
    batch: Pass2DecisionBatch,
) -> RelationBatch:
    by_id = {fact.id: fact for fact in facts}
    expected = set(action_entity_pairs(facts))
    seen: set[tuple[str, str]] = set()

    for decision in batch.action_entity_decisions:
        pair = (decision.action, decision.entity)
        if pair in seen:
            raise ValueError("C7_DUPLICATE_ACTION_ENTITY_DECISION")
        seen.add(pair)
        if pair not in expected:
            raise ValueError("C7_ACTION_ENTITY_PAIR_KIND_MISMATCH")
        if by_id[decision.action].kind is not FactKind.ACTION or by_id[decision.entity].kind is not FactKind.ENTITY:
            raise ValueError("C7_ACTION_ENTITY_PAIR_KIND_MISMATCH")
        if decision.decision is not ActionEntityDecisionKind.NONE:
            assert decision.justification_span is not None
            if decision.justification_span not in instruction:
                raise ValueError("C7_UNGROUNDED_RELATION_JUSTIFICATION")

    if seen != expected:
        raise ValueError("C7_UNCLASSIFIED_ACTION_ENTITY_PAIR")

    free_batch = RelationBatch(relations=batch.relations)
    for relation in free_batch.relations:
        if relation.kind in {RelationKind.ACTION_OBJECT, RelationKind.ACTION_COUNTERPARTY}:
            raise ValueError("C7_ACTION_ENTITY_RELATION_OUTSIDE_CHECKLIST")
    validate_relations(facts, free_batch)

    decisions = tuple(batch.action_entity_decisions)
    _validate_source_positions(instruction, facts, decisions)

    materialized = list(free_batch.relations)
    for decision in decisions:
        if decision.decision is ActionEntityDecisionKind.NONE:
            continue
        materialized.append(Relation(
            kind=RelationKind(decision.decision.value),
            left=decision.action,
            right=decision.entity,
            justification_span=decision.justification_span or "",
        ))

    result = RelationBatch(relations=materialized)
    validate_relations(facts, result)
    return result
