from __future__ import annotations

import pytest

from ecocommit.candidate7_compile import compile_graph_v2, validate_graph_semantics
from ecocommit.candidate7_flat import Fact, FactBatch, FactKind, Polarity, Relation, RelationBatch, RelationKind, TextSpan, assign_fact_ids
from ecocommit.candidate7_structure import build_graph


def f(quote: str, kind: FactKind, polarity: Polarity = Polarity.POSITIVE) -> Fact:
    return Fact(text_span=TextSpan(quote=quote), kind=kind, polarity=polarity)


def rel(kind: RelationKind, left: str, right: str, instruction: str) -> Relation:
    return Relation(kind=kind, left=left, right=right, justification_span=instruction)


def test_objectless_commit_is_supported_deterministically():
    instruction = "Spend no more than ₹60,000."
    facts = assign_fact_ids(FactBatch(facts=[
        f("Spend", FactKind.ACTION),
        f("no more than ₹60,000", FactKind.CONSTRAINT),
    ]))
    relations = RelationBatch(relations=[rel(RelationKind.CONSTRAINT_APPLIES_TO, "F0002", "F0001", instruction)])
    graph = build_graph(instruction, facts, relations)
    contract = compile_graph_v2(graph)
    assert any(c.clause_type.value == "AUTHORIZATION" for c in contract.clauses)
    assert any("MAX_TOTAL_COST:INR" in c.normalized_value for c in contract.clauses)


def test_contradictory_min_max_constraints_reject():
    instruction = "Buy device for at most ₹20,000 and at least ₹30,000."
    facts = assign_fact_ids(FactBatch(facts=[
        f("Buy device", FactKind.ACTION),
        f("device", FactKind.ENTITY),
        f("at most ₹20,000", FactKind.CONSTRAINT),
        f("at least ₹30,000", FactKind.CONSTRAINT),
    ]))
    relations = RelationBatch(relations=[
        rel(RelationKind.ACTION_OBJECT, "F0001", "F0002", instruction),
        rel(RelationKind.CONSTRAINT_APPLIES_TO, "F0003", "F0001", instruction),
        rel(RelationKind.CONSTRAINT_APPLIES_TO, "F0004", "F0001", instruction),
    ])
    graph = build_graph(instruction, facts, relations)
    with pytest.raises(ValueError, match="IR_CONTRADICTORY_CONSTRAINTS"):
        validate_graph_semantics(graph)


def test_exact_above_max_rejects():
    instruction = "Pay exactly ₹50,000 but never more than ₹45,000."
    facts = assign_fact_ids(FactBatch(facts=[
        f("Pay", FactKind.ACTION),
        f("exactly ₹50,000", FactKind.CONSTRAINT),
        f("never more than ₹45,000", FactKind.CONSTRAINT),
    ]))
    relations = RelationBatch(relations=[
        rel(RelationKind.CONSTRAINT_APPLIES_TO, "F0002", "F0001", instruction),
        rel(RelationKind.CONSTRAINT_APPLIES_TO, "F0003", "F0001", instruction),
    ])
    graph = build_graph(instruction, facts, relations)
    with pytest.raises(ValueError, match="IR_CONTRADICTORY_CONSTRAINTS"):
        validate_graph_semantics(graph)


def test_minus_quantity_rejects_instead_of_becoming_positive():
    instruction = "Order minus five replacement units."
    facts = assign_fact_ids(FactBatch(facts=[
        f("Order minus five replacement units", FactKind.ACTION),
        f("replacement units", FactKind.ENTITY),
    ]))
    relations = RelationBatch(relations=[rel(RelationKind.ACTION_OBJECT, "F0001", "F0002", instruction)])
    graph = build_graph(instruction, facts, relations)
    with pytest.raises(ValueError, match="C7_QUANTITY_INVALID"):
        validate_graph_semantics(graph)


def test_dependency_cycle_rejects():
    instruction = "Pay after booking succeeds and book only after payment succeeds."
    facts = assign_fact_ids(FactBatch(facts=[
        f("Pay", FactKind.ACTION),
        f("book", FactKind.ACTION),
    ]))
    relations = RelationBatch(relations=[
        rel(RelationKind.AFTER_SUCCESS, "F0001", "F0002", instruction),
        rel(RelationKind.AFTER_SUCCESS, "F0002", "F0001", instruction),
    ])
    graph = build_graph(instruction, facts, relations)
    with pytest.raises(ValueError, match="IR_DEPENDENCY_CYCLE"):
        validate_graph_semantics(graph)
