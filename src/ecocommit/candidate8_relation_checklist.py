from __future__ import annotations

import re

from .candidate7_flat import LabeledFact, grounded_span
from .candidate7_relation_checklist import (
    ActionEntityDecisionKind,
    Pass2DecisionBatch,
    validate_and_materialize_pass2 as validate_and_materialize_candidate7,
)


_DETERMINER_ONLY = re.compile(
    r"^[\s,;:\-]*(?:(?:the|a|an|this|that|these|those)\b[\s,;:\-]*)*$",
    re.IGNORECASE,
)


def _validate_direct_object_role(
    instruction: str,
    facts: tuple[LabeledFact, ...],
    batch: Pass2DecisionBatch,
) -> None:
    """Reject counterpart labels for bare source-local grammatical objects.

    Candidate-8 defines ACTION_OBJECT by source syntax rather than by whether the
    noun denotes a person, organization, payee, vendor, or other participant.
    An entity embedded in the action span is already protected by Candidate-7.
    This additional gate covers an entity that follows the action span with only
    whitespace/punctuation and an optional determiner between them.  Explicitly
    relational/prepositional entities (for example introduced by to/from/with/
    through/via/by/at) are not rewritten and remain provider-classified.

    The verifier is fail-closed: it never creates or changes a relation; it only
    rejects a semantically inconsistent provider decision so the bounded schema
    correction path may reconsider it.
    """

    by_id = {fact.id: fact for fact in facts}
    for decision in batch.action_entity_decisions:
        if decision.decision is not ActionEntityDecisionKind.ACTION_COUNTERPARTY:
            continue
        action = by_id[decision.action]
        entity = by_id[decision.entity]
        action_start, action_end = grounded_span(instruction, action.text_span)
        entity_start, entity_end = grounded_span(instruction, entity.text_span)

        if action_start <= entity_start and entity_end <= action_end:
            # Candidate-7 already rejects this, keep the rule explicit here too.
            raise ValueError("C8_DIRECT_OBJECT_MISCLASSIFIED_AS_COUNTERPARTY")
        if entity_start < action_end:
            continue

        gap = instruction[action_end:entity_start]
        if _DETERMINER_ONLY.fullmatch(gap):
            raise ValueError("C8_DIRECT_OBJECT_MISCLASSIFIED_AS_COUNTERPARTY")


def validate_and_materialize_pass2(
    instruction: str,
    facts: tuple[LabeledFact, ...],
    batch: Pass2DecisionBatch,
):
    _validate_direct_object_role(instruction, facts, batch)
    return validate_and_materialize_candidate7(instruction, facts, batch)
