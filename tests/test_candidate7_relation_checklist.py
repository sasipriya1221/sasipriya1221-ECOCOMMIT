from __future__ import annotations

import pytest

from ecocommit.candidate7_flat import Fact, FactBatch, FactKind, Polarity, Relation, RelationKind, TextSpan, assign_fact_ids
from ecocommit.candidate7_relation_checklist import (
    ActionEntityDecision,
    ActionEntityDecisionKind,
    Pass2DecisionBatch,
    action_entity_pair_payload,
    validate_and_materialize_pass2,
)


def fact(quote: str, kind: FactKind) -> Fact:
    return Fact(text_span=TextSpan(quote=quote), kind=kind, polarity=Polarity.POSITIVE)


def decision(action: str, entity: str, kind: ActionEntityDecisionKind, justification: str | None = None) -> ActionEntityDecision:
    return ActionEntityDecision(action=action, entity=entity, decision=kind, justification_span=justification)


def test_every_action_entity_pair_is_generated_and_must_be_classified_exactly_once():
    instruction = "Buy cables after audit."
    facts = assign_fact_ids(FactBatch(facts=[
        fact("Buy cables", FactKind.ACTION),
        fact("cables", FactKind.ENTITY),
        fact("audit", FactKind.ENTITY),
    ]))
    assert action_entity_pair_payload(facts) == [
        {"action": "F0001", "entity": "F0002"},
        {"action": "F0001", "entity": "F0003"},
    ]
    incomplete = Pass2DecisionBatch(action_entity_decisions=[
        decision("F0001", "F0002", ActionEntityDecisionKind.ACTION_OBJECT, "Buy cables"),
    ])
    with pytest.raises(ValueError, match="C7_UNCLASSIFIED_ACTION_ENTITY_PAIR"):
        validate_and_materialize_pass2(instruction, facts, incomplete)


def test_duplicate_action_entity_decision_fails_closed():
    instruction = "Buy cables."
    facts = assign_fact_ids(FactBatch(facts=[
        fact("Buy cables", FactKind.ACTION),
        fact("cables", FactKind.ENTITY),
    ]))
    batch = Pass2DecisionBatch(action_entity_decisions=[
        decision("F0001", "F0002", ActionEntityDecisionKind.ACTION_OBJECT, "Buy cables"),
        decision("F0001", "F0002", ActionEntityDecisionKind.NONE),
    ])
    with pytest.raises(ValueError, match="C7_DUPLICATE_ACTION_ENTITY_DECISION"):
        validate_and_materialize_pass2(instruction, facts, batch)


def test_d009_original_omission_signature_is_rejected_by_source_local_verifier():
    instruction = "Order 500 envelopes only if warehouse count below 100."
    facts = assign_fact_ids(FactBatch(facts=[
        fact("Order 500 envelopes", FactKind.ACTION),
        fact("500 envelopes", FactKind.ENTITY),
        fact("warehouse count below 100", FactKind.PREDICATE),
    ]))
    batch = Pass2DecisionBatch(
        action_entity_decisions=[decision("F0001", "F0002", ActionEntityDecisionKind.NONE)],
        relations=[Relation(
            kind=RelationKind.GUARDS_ACTION,
            left="F0003",
            right="F0001",
            justification_span="only if warehouse count below 100",
        )],
    )
    with pytest.raises(ValueError, match="C7_ACTION_LOCAL_ENTITY_WRONG_ROLE"):
        validate_and_materialize_pass2(instruction, facts, batch)


def test_d009_correct_object_decision_materializes_without_inventing_relation():
    instruction = "Order 500 envelopes only if warehouse count below 100."
    facts = assign_fact_ids(FactBatch(facts=[
        fact("Order 500 envelopes", FactKind.ACTION),
        fact("500 envelopes", FactKind.ENTITY),
        fact("warehouse count below 100", FactKind.PREDICATE),
    ]))
    batch = Pass2DecisionBatch(
        action_entity_decisions=[decision(
            "F0001", "F0002", ActionEntityDecisionKind.ACTION_OBJECT, "Order 500 envelopes"
        )],
        relations=[Relation(
            kind=RelationKind.GUARDS_ACTION,
            left="F0003",
            right="F0001",
            justification_span="only if warehouse count below 100",
        )],
    )
    result = validate_and_materialize_pass2(instruction, facts, batch)
    assert {(r.kind, r.left, r.right) for r in result.relations} == {
        (RelationKind.ACTION_OBJECT, "F0001", "F0002"),
        (RelationKind.GUARDS_ACTION, "F0003", "F0001"),
    }


def test_d003_original_role_inversion_is_rejected():
    instruction = "Pay printer exactly ₹32,500 for completed run."
    facts = assign_fact_ids(FactBatch(facts=[
        fact("Pay", FactKind.ACTION),
        fact("printer", FactKind.ENTITY),
        fact("exactly ₹32,500", FactKind.CONSTRAINT),
        fact("completed run", FactKind.ENTITY),
    ]))
    batch = Pass2DecisionBatch(
        action_entity_decisions=[
            decision("F0001", "F0002", ActionEntityDecisionKind.ACTION_COUNTERPARTY, "Pay printer"),
            decision("F0001", "F0004", ActionEntityDecisionKind.ACTION_OBJECT, instruction),
        ],
        relations=[Relation(
            kind=RelationKind.CONSTRAINT_APPLIES_TO,
            left="F0003",
            right="F0001",
            justification_span="Pay printer exactly ₹32,500",
        )],
    )
    with pytest.raises(ValueError, match="C7_ACTION_OBJECT_NOT_SOURCE_LOCAL"):
        validate_and_materialize_pass2(instruction, facts, batch)


def test_d003_corrected_roles_pass_and_completed_run_can_be_explicit_none():
    instruction = "Pay printer exactly ₹32,500 for completed run."
    facts = assign_fact_ids(FactBatch(facts=[
        fact("Pay", FactKind.ACTION),
        fact("printer", FactKind.ENTITY),
        fact("exactly ₹32,500", FactKind.CONSTRAINT),
        fact("completed run", FactKind.ENTITY),
    ]))
    batch = Pass2DecisionBatch(
        action_entity_decisions=[
            decision("F0001", "F0002", ActionEntityDecisionKind.ACTION_OBJECT, "Pay printer"),
            decision("F0001", "F0004", ActionEntityDecisionKind.NONE),
        ],
        relations=[Relation(
            kind=RelationKind.CONSTRAINT_APPLIES_TO,
            left="F0003",
            right="F0001",
            justification_span="Pay printer exactly ₹32,500",
        )],
    )
    result = validate_and_materialize_pass2(instruction, facts, batch)
    assert (RelationKind.ACTION_OBJECT, "F0001", "F0002") in {
        (r.kind, r.left, r.right) for r in result.relations
    }
    assert all(r.right != "F0004" for r in result.relations)


def test_adversarial_trailing_after_entity_can_be_explicit_none_without_becoming_object():
    instruction = "Buy cables after audit."
    facts = assign_fact_ids(FactBatch(facts=[
        fact("Buy cables", FactKind.ACTION),
        fact("cables", FactKind.ENTITY),
        fact("audit", FactKind.ENTITY),
    ]))
    batch = Pass2DecisionBatch(action_entity_decisions=[
        decision("F0001", "F0002", ActionEntityDecisionKind.ACTION_OBJECT, "Buy cables"),
        decision("F0001", "F0003", ActionEntityDecisionKind.NONE),
    ])
    result = validate_and_materialize_pass2(instruction, facts, batch)
    assert [(r.kind, r.left, r.right) for r in result.relations] == [
        (RelationKind.ACTION_OBJECT, "F0001", "F0002")
    ]


def test_immediate_entity_is_not_blanket_forced_to_object_when_no_competing_object_exists():
    instruction = "Pay printer."
    facts = assign_fact_ids(FactBatch(facts=[
        fact("Pay", FactKind.ACTION),
        fact("printer", FactKind.ENTITY),
    ]))
    batch = Pass2DecisionBatch(action_entity_decisions=[
        decision("F0001", "F0002", ActionEntityDecisionKind.ACTION_COUNTERPARTY, "Pay printer"),
    ])
    result = validate_and_materialize_pass2(instruction, facts, batch)
    assert [(r.kind, r.left, r.right) for r in result.relations] == [
        (RelationKind.ACTION_COUNTERPARTY, "F0001", "F0002")
    ]


def test_action_entity_relations_cannot_bypass_checklist_through_free_relations():
    instruction = "Buy cables."
    facts = assign_fact_ids(FactBatch(facts=[
        fact("Buy cables", FactKind.ACTION),
        fact("cables", FactKind.ENTITY),
    ]))
    batch = Pass2DecisionBatch(
        action_entity_decisions=[
            decision("F0001", "F0002", ActionEntityDecisionKind.ACTION_OBJECT, "Buy cables")
        ],
        relations=[Relation(
            kind=RelationKind.ACTION_OBJECT,
            left="F0001",
            right="F0002",
            justification_span="Buy cables",
        )],
    )
    with pytest.raises(ValueError, match="C7_ACTION_ENTITY_RELATION_OUTSIDE_CHECKLIST"):
        validate_and_materialize_pass2(instruction, facts, batch)
