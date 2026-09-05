from __future__ import annotations

import pytest
from pydantic import ValidationError

from ecocommit.candidate7_flat import (
    Fact,
    FactBatch,
    FactKind,
    LabeledFact,
    Polarity,
    Relation,
    RelationBatch,
    RelationKind,
    TextSpan,
    assign_fact_ids,
    validate_relations,
)
from ecocommit.candidate7_provider import PASS1_SYSTEM_PROMPT, PASS2_SYSTEM_PROMPT
from ecocommit.candidate7_structure import C7And, C7Atom, C7Not, C7Or, build_graph, compile_graph


def fact(quote: str, kind: FactKind, polarity: Polarity = Polarity.POSITIVE) -> Fact:
    return Fact(text_span=TextSpan(quote=quote), kind=kind, polarity=polarity)


def relation(kind: RelationKind, left: str, right: str, justification: str = "grounded") -> Relation:
    return Relation(kind=kind, left=left, right=right, justification_span=justification)


def test_pass1_schema_has_no_identifier_or_reference_field():
    fields = set(Fact.model_fields)
    assert fields == {"text_span", "kind", "polarity", "action_type"}
    assert "NO IDs" in PASS1_SYSTEM_PROMPT
    assert "NO cross-references" in PASS1_SYSTEM_PROMPT
    assert "Boolean" in PASS1_SYSTEM_PROMPT


def test_ids_are_assigned_only_deterministically_in_extraction_order():
    batch = FactBatch(facts=[
        fact("Order boxes", FactKind.ACTION),
        fact("boxes", FactKind.ENTITY),
        fact("₹18,000 or less", FactKind.CONSTRAINT),
    ])
    labeled = assign_fact_ids(batch)
    assert [item.id for item in labeled] == ["F0001", "F0002", "F0003"]
    assert [item.text_span.quote for item in labeled] == ["Order boxes", "boxes", "₹18,000 or less"]


def test_pass2_schema_can_reference_only_existing_fact_ids():
    facts = assign_fact_ids(FactBatch(facts=[fact("Buy cables", FactKind.ACTION), fact("cables", FactKind.ENTITY)]))
    bad = RelationBatch(relations=[relation(RelationKind.ACTION_OBJECT, "F0001", "F9999")])
    with pytest.raises(ValueError, match="C7_UNKNOWN_FACT_REFERENCE"):
        validate_relations(facts, bad)
    assert "ONLY the existing F#### IDs" in PASS2_SYSTEM_PROMPT
    assert "Do not create any new identifier" in PASS2_SYSTEM_PROMPT


def test_relation_kind_mismatch_fails_closed():
    facts = assign_fact_ids(FactBatch(facts=[fact("Buy cables", FactKind.ACTION), fact("cables", FactKind.ENTITY)]))
    bad = RelationBatch(relations=[relation(RelationKind.ALL_OF, "F0001", "F0002")])
    with pytest.raises(ValueError, match="C7_RELATION_KIND_MISMATCH"):
        validate_relations(facts, bad)


def test_contradictory_boolean_pair_fails_closed():
    facts = assign_fact_ids(FactBatch(facts=[fact("approval received", FactKind.PREDICATE), fact("account frozen", FactKind.PREDICATE)]))
    bad = RelationBatch(relations=[
        relation(RelationKind.ALL_OF, "F0001", "F0002"),
        relation(RelationKind.ANY_OF, "F0001", "F0002"),
    ])
    with pytest.raises(ValueError, match="C7_CONTRADICTORY_LOGIC_RELATION"):
        validate_relations(facts, bad)


def test_single_negated_guard_is_built_deterministically_not_by_model():
    instruction = "Pay invoice if account not frozen."
    facts = assign_fact_ids(FactBatch(facts=[
        fact("Pay invoice", FactKind.ACTION),
        fact("invoice", FactKind.ENTITY),
        fact("account not frozen", FactKind.PREDICATE, Polarity.NEGATED),
    ]))
    relations = RelationBatch(relations=[
        relation(RelationKind.ACTION_OBJECT, "F0001", "F0002", instruction),
        relation(RelationKind.GUARDS_ACTION, "F0003", "F0001", "if account not frozen"),
    ])
    graph = build_graph(instruction, facts, relations)
    assert len(graph.guards) == 1
    expr = graph.guards[0].expr
    assert isinstance(expr, C7Not)
    assert isinstance(expr.arg, C7Atom)
    assert expr.arg.fact_id == "F0003"


def test_unless_style_block_relation_becomes_not_guard_deterministically():
    instruction = "Purchase equipment unless recall notice active."
    facts = assign_fact_ids(FactBatch(facts=[
        fact("Purchase equipment", FactKind.ACTION),
        fact("equipment", FactKind.ENTITY),
        fact("recall notice active", FactKind.PREDICATE),
    ]))
    relations = RelationBatch(relations=[
        relation(RelationKind.ACTION_OBJECT, "F0001", "F0002", instruction),
        relation(RelationKind.BLOCKS_ACTION, "F0003", "F0001", "unless recall notice active"),
    ])
    graph = build_graph(instruction, facts, relations)
    assert isinstance(graph.guards[0].expr, C7Not)


def test_mixed_boolean_structure_is_constructed_from_flat_pair_relations():
    instruction = "Order supplies only when inventory low and either branch A requests replenishment or branch B requests replenishment."
    facts = assign_fact_ids(FactBatch(facts=[
        fact("Order supplies", FactKind.ACTION),
        fact("supplies", FactKind.ENTITY),
        fact("inventory low", FactKind.PREDICATE),
        fact("branch A requests replenishment", FactKind.PREDICATE),
        fact("branch B requests replenishment", FactKind.PREDICATE),
    ]))
    relations = RelationBatch(relations=[
        relation(RelationKind.ACTION_OBJECT, "F0001", "F0002", instruction),
        relation(RelationKind.GUARDS_ACTION, "F0003", "F0001", "only when inventory low"),
        relation(RelationKind.GUARDS_ACTION, "F0004", "F0001", "either branch A requests replenishment or branch B requests replenishment"),
        relation(RelationKind.GUARDS_ACTION, "F0005", "F0001", "either branch A requests replenishment or branch B requests replenishment"),
        relation(RelationKind.ALL_OF, "F0003", "F0004", "inventory low and either branch A requests replenishment"),
        relation(RelationKind.ALL_OF, "F0003", "F0005", "inventory low and either branch A requests replenishment or branch B requests replenishment"),
        relation(RelationKind.ANY_OF, "F0004", "F0005", "either branch A requests replenishment or branch B requests replenishment"),
    ])
    graph = build_graph(instruction, facts, relations)
    expr = graph.guards[0].expr
    assert isinstance(expr, C7And)
    assert any(isinstance(arg, C7Atom) and arg.fact_id == "F0003" for arg in expr.args)
    assert any(isinstance(arg, C7Or) for arg in expr.args)


def test_multiple_guard_predicates_without_logic_relation_fail_closed():
    instruction = "Pay invoice if approval received and account current."
    facts = assign_fact_ids(FactBatch(facts=[
        fact("Pay invoice", FactKind.ACTION),
        fact("invoice", FactKind.ENTITY),
        fact("approval received", FactKind.PREDICATE),
        fact("account current", FactKind.PREDICATE),
    ]))
    relations = RelationBatch(relations=[
        relation(RelationKind.ACTION_OBJECT, "F0001", "F0002", instruction),
        relation(RelationKind.GUARDS_ACTION, "F0003", "F0001", "if approval received"),
        relation(RelationKind.GUARDS_ACTION, "F0004", "F0001", "and account current"),
    ])
    with pytest.raises(ValueError, match="C7_BOOLEAN_RELATION_MISSING"):
        build_graph(instruction, facts, relations)


def test_guard_relation_cannot_be_silently_dropped_from_contract():
    instruction = "Order 500 envelopes only if warehouse count below 100."
    facts = assign_fact_ids(FactBatch(facts=[
        fact("Order 500 envelopes", FactKind.ACTION),
        fact("envelopes", FactKind.ENTITY),
        fact("warehouse count below 100", FactKind.PREDICATE),
    ]))
    relations = RelationBatch(relations=[
        relation(RelationKind.ACTION_OBJECT, "F0001", "F0002", instruction),
        relation(RelationKind.GUARDS_ACTION, "F0003", "F0001", "only if warehouse count below 100"),
    ])
    graph = build_graph(instruction, facts, relations)
    contract = compile_graph(graph)
    guard_clauses = [c for c in contract.clauses if c.clause_id == "g_F0001"]
    assert len(guard_clauses) == 1
    assert "F0003" in guard_clauses[0].normalized_value
    assert "c_F0003" in guard_clauses[0].depends_on
    assert "c_F0001" in guard_clauses[0].depends_on


def test_ambiguity_without_target_blocks_all_actions_fail_closed():
    instruction = "Buy a reasonable number of cables."
    facts = assign_fact_ids(FactBatch(facts=[
        fact("Buy", FactKind.ACTION),
        fact("cables", FactKind.ENTITY),
        fact("reasonable number", FactKind.AMBIGUITY),
    ]))
    relations = RelationBatch(relations=[relation(RelationKind.ACTION_OBJECT, "F0001", "F0002", instruction)])
    graph = build_graph(instruction, facts, relations)
    assert graph.blocked_actions == frozenset({"F0001"})


def test_extra_fields_cannot_smuggle_ids_into_pass1_fact():
    with pytest.raises(ValidationError):
        Fact.model_validate({
            "id": "A1",
            "text_span": {"quote": "Buy cables", "occurrence": 1},
            "kind": "ACTION",
            "polarity": "POSITIVE",
        })
