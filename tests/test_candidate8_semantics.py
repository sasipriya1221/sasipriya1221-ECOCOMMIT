from __future__ import annotations

import pytest

from ecocommit.candidate7_flat import LabeledFact, Relation, RelationBatch
from ecocommit.candidate7_relation_checklist import Pass2DecisionBatch
from ecocommit.candidate8_logic import C8FactDisposition, C8RelationType, build_typed_ast, verify_ast_conservation
from ecocommit.candidate8_provider import GroqCandidate8Provider
from ecocommit.candidate8_relation_checklist import semantic_dispositions, validate_and_materialize_pass2


def fact(fid, quote, kind, *, action_type=None, polarity="POSITIVE"):
    return LabeledFact.model_validate({
        "id": fid,
        "text_span": {"quote": quote, "occurrence": 1},
        "kind": kind,
        "polarity": polarity,
        "action_type": action_type,
    })


def decisions(rows, relations=()):
    return Pass2DecisionBatch.model_validate({
        "action_entity_decisions": rows,
        "relations": list(relations),
    })


def test_bare_person_direct_object_cannot_be_counterparty():
    instruction = "Pay the carrier after delivery."
    facts = (fact("F0001", "Pay", "ACTION", action_type="PAY"), fact("F0002", "carrier", "ENTITY"))
    batch = decisions([{"action":"F0001","entity":"F0002","decision":"ACTION_COUNTERPARTY","justification_span":"Pay the carrier"}])
    with pytest.raises(ValueError, match="C8_DIRECT_OBJECT_MISCLASSIFIED_AS_COUNTERPARTY"):
        validate_and_materialize_pass2(instruction, facts, batch)


def test_explicit_object_and_counterparty_are_preserved():
    instruction = "Pay the invoice to the carrier."
    facts = (
        fact("F0001", "Pay", "ACTION", action_type="PAY"),
        fact("F0002", "invoice", "ENTITY"),
        fact("F0003", "carrier", "ENTITY"),
    )
    batch = decisions([
        {"action":"F0001","entity":"F0002","decision":"ACTION_OBJECT","justification_span":"Pay the invoice"},
        {"action":"F0001","entity":"F0003","decision":"ACTION_COUNTERPARTY","justification_span":"to the carrier"},
    ])
    materialized, dispositions = validate_and_materialize_pass2(instruction, facts, batch)
    sig = {(r.kind.value, r.left, r.right) for r in materialized.relations}
    assert ("ACTION_OBJECT", "F0001", "F0002") in sig
    assert ("ACTION_COUNTERPARTY", "F0001", "F0003") in sig
    assert set(dispositions.values()) == {C8FactDisposition.USED}


def test_transfer_object_and_prepositioned_counterparty():
    instruction = "Transfer the refund to the customer."
    facts = (
        fact("F0001", "Transfer", "ACTION", action_type="TRANSFER"),
        fact("F0002", "refund", "ENTITY"),
        fact("F0003", "customer", "ENTITY"),
    )
    batch = decisions([
        {"action":"F0001","entity":"F0002","decision":"ACTION_OBJECT","justification_span":"Transfer the refund"},
        {"action":"F0001","entity":"F0003","decision":"ACTION_COUNTERPARTY","justification_span":"to the customer"},
    ])
    materialized, _ = validate_and_materialize_pass2(instruction, facts, batch)
    assert len(materialized.relations) == 2


def test_ungrounded_free_relation_is_rejected_before_acceptance():
    instruction = "Order cartons only if stock is low."
    facts = (
        fact("F0001", "Order cartons", "ACTION", action_type="ORDER"),
        fact("F0002", "cartons", "ENTITY"),
        fact("F0003", "stock is low", "PREDICATE"),
    )
    batch = decisions(
        [{"action":"F0001","entity":"F0002","decision":"ACTION_OBJECT","justification_span":"Order cartons"}],
        [{"kind":"GUARDS_ACTION","left":"F0003","right":"F0001","justification_span":"stock low"}],
    )
    with pytest.raises(ValueError, match="C8_UNGROUNDED_RELATION_JUSTIFICATION"):
        validate_and_materialize_pass2(instruction, facts, batch)


def test_constraint_must_have_exact_target():
    instruction = "Buy monitors for at most ₹80,000."
    facts = (
        fact("F0001", "Buy monitors", "ACTION", action_type="BUY"),
        fact("F0002", "monitors", "ENTITY"),
        fact("F0003", "at most ₹80,000", "CONSTRAINT"),
    )
    relations = RelationBatch(relations=[Relation.model_validate({
        "kind":"ACTION_OBJECT","left":"F0001","right":"F0002","justification_span":"Buy monitors"
    })])
    with pytest.raises(ValueError, match="C8_REQUIRED_CONSTRAINT_TARGET_MISSING"):
        semantic_dispositions(instruction, facts, relations)


def test_material_predicate_cannot_be_unused():
    instruction = "Order labels if stock is below ten."
    facts = (
        fact("F0001", "Order labels", "ACTION", action_type="ORDER"),
        fact("F0002", "labels", "ENTITY"),
        fact("F0003", "stock is below ten", "PREDICATE"),
    )
    relations = RelationBatch(relations=[Relation.model_validate({
        "kind":"ACTION_OBJECT","left":"F0001","right":"F0002","justification_span":"Order labels"
    })])
    with pytest.raises(ValueError, match="C8_REQUIRED_PREDICATE_UNUSED"):
        semantic_dispositions(instruction, facts, relations)


def test_nonlocal_trailing_context_can_be_explicitly_irrelevant():
    instruction = "Pay courier exactly ₹4,500 for completed route."
    facts = (
        fact("F0001", "Pay", "ACTION", action_type="PAY"),
        fact("F0002", "courier", "ENTITY"),
        fact("F0003", "exactly ₹4,500", "CONSTRAINT"),
        fact("F0004", "completed route", "ENTITY"),
    )
    relations = RelationBatch(relations=[
        Relation.model_validate({"kind":"ACTION_OBJECT","left":"F0001","right":"F0002","justification_span":"Pay courier"}),
        Relation.model_validate({"kind":"CONSTRAINT_APPLIES_TO","left":"F0003","right":"F0001","justification_span":"Pay courier exactly ₹4,500"}),
    ])
    dispositions = semantic_dispositions(instruction, facts, relations)
    assert dispositions["F0001"] is C8FactDisposition.USED
    assert dispositions["F0002"] is C8FactDisposition.USED
    assert dispositions["F0003"] is C8FactDisposition.USED
    assert dispositions["F0004"] is C8FactDisposition.IRRELEVANT


def test_unlinked_source_local_entity_fails_closed():
    instruction = "Hire the consultant."
    facts = (fact("F0001", "Hire", "ACTION", action_type="HIRE"), fact("F0002", "consultant", "ENTITY"))
    with pytest.raises(ValueError, match="C8_UNLINKED_SOURCE_LOCAL_ENTITY"):
        semantic_dispositions(instruction, facts, RelationBatch(relations=[]))


def test_typed_ast_maps_boolean_and_dependency_relations_and_conserves():
    facts = (
        fact("F0001", "Order supplies", "ACTION", action_type="ORDER"),
        fact("F0002", "supplies", "ENTITY"),
        fact("F0003", "inventory low", "PREDICATE"),
        fact("F0004", "branch requests replenishment", "PREDICATE"),
    )
    relations = RelationBatch(relations=[
        Relation.model_validate({"kind":"ACTION_OBJECT","left":"F0001","right":"F0002","justification_span":"Order supplies"}),
        Relation.model_validate({"kind":"GUARDS_ACTION","left":"F0003","right":"F0001","justification_span":"inventory low"}),
        Relation.model_validate({"kind":"GUARDS_ACTION","left":"F0004","right":"F0001","justification_span":"branch requests replenishment"}),
        Relation.model_validate({"kind":"ANY_OF","left":"F0003","right":"F0004","justification_span":"inventory low or branch requests replenishment"}),
    ])
    ast = build_typed_ast(facts, relations, {f.id:C8FactDisposition.USED for f in facts})
    assert C8RelationType.ROLE_OBJECT in {e.relation for e in ast.edges}
    assert C8RelationType.CONDITIONAL in {e.relation for e in ast.edges}
    assert C8RelationType.ALTERNATIVE in {e.relation for e in ast.edges}
    verify_ast_conservation(ast, relations)


def test_typed_ast_rejects_dependency_cycle():
    facts = (
        fact("F0001", "Order parts", "ACTION", action_type="ORDER"),
        fact("F0002", "Pay invoice", "ACTION", action_type="PAY"),
    )
    relations = RelationBatch(relations=[
        Relation.model_validate({"kind":"AFTER_SUCCESS","left":"F0001","right":"F0002","justification_span":"after"}),
        Relation.model_validate({"kind":"AFTER_SUCCESS","left":"F0002","right":"F0001","justification_span":"after"}),
    ])
    with pytest.raises(ValueError, match="IR_DEPENDENCY_CYCLE"):
        build_typed_ast(facts, relations, {f.id:C8FactDisposition.USED for f in facts})


def test_provider_configuration_is_hard_bound():
    provider = GroqCandidate8Provider("not-a-real-key")
    assert provider.model == "qwen/qwen3.6-27b"
    assert provider.max_completion_tokens == 900
    with pytest.raises(ValueError, match="C8_OUTPUT_TOKEN_CEILING_MUST_BE_900"):
        GroqCandidate8Provider("not-a-real-key", max_completion_tokens=901)
    with pytest.raises(ValueError, match="C8_MODEL_MUST_BE_QWEN_3_6_27B"):
        GroqCandidate8Provider("not-a-real-key", model="other/model")
