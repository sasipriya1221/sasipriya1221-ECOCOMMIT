from __future__ import annotations

import pytest

from ecocommit.candidate8 import run_candidate8
from ecocommit.candidate7_flat import LabeledFact, Relation, RelationBatch
from ecocommit.candidate7_relation_checklist import Pass2DecisionBatch
from ecocommit.candidate8_logic import C8FactDisposition, C8RelationType, build_typed_ast, verify_ast_conservation
from ecocommit.candidate8_normalize import (
    candidate8_dispositions,
    infer_candidate8_relations,
    normalize_candidate8_facts,
)
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


def _normalize(instruction, raw):
    return normalize_candidate8_facts(instruction, tuple(raw)).facts


def _relation_signatures(batch):
    return {(r.kind.value, r.left, r.right) for r in batch.relations}


def test_source_grounded_normalizer_builds_direct_object_counterparty_and_constraint():
    instruction = "Pay the invoice to the carrier exactly ₹21,700."
    raw = (
        fact("F0001", "Pay", "ACTION", action_type="PAY"),
        fact("F0002", "invoice", "ENTITY"),
        fact("F0003", "carrier", "ENTITY"),
        fact("F0004", "exactly ₹21,700", "CONSTRAINT"),
    )
    facts = _normalize(instruction, raw)
    relations = infer_candidate8_relations(instruction, facts)
    by_quote = {f.text_span.quote: f.id for f in facts}
    assert ("ACTION_OBJECT", by_quote["Pay"], by_quote["invoice"]) in _relation_signatures(relations)
    assert ("ACTION_COUNTERPARTY", by_quote["Pay"], by_quote["carrier"]) in _relation_signatures(relations)
    assert ("CONSTRAINT_APPLIES_TO", by_quote["exactly ₹21,700"], by_quote["Pay"]) in _relation_signatures(relations)


def test_source_grounded_normalizer_atomizes_nested_boolean_guard():
    instruction = "Order supplies only if inventory is low and either branch A or branch B requests replenishment."
    raw = (
        fact("F0001", "Order", "ACTION", action_type="ORDER"),
        fact("F0002", "supplies", "ENTITY"),
        fact("F0003", "inventory is low and either branch A or branch B requests replenishment", "PREDICATE"),
    )
    facts = _normalize(instruction, raw)
    predicates = [f for f in facts if f.kind.value == "PREDICATE"]
    assert [f.text_span.quote for f in predicates] == ["inventory is low", "branch A", "branch B requests replenishment"]
    relations = infer_candidate8_relations(instruction, facts)
    kinds = [r.kind.value for r in relations.relations]
    assert kinds.count("GUARDS_ACTION") == 3
    assert "ALL_OF" in kinds
    assert "ANY_OF" in kinds


def test_unless_is_a_blocking_predicate_not_an_exception():
    instruction = "Release the deposit unless inspection fails."
    raw = (
        fact("F0001", "Release the deposit", "ACTION", action_type="RELEASE"),
        fact("F0002", "deposit", "ENTITY"),
        fact("F0003", "inspection fails", "EXCEPTION"),
    )
    facts = _normalize(instruction, raw)
    assert not [f for f in facts if f.kind.value == "EXCEPTION"]
    relations = infer_candidate8_relations(instruction, facts)
    assert "BLOCKS_ACTION" in {r.kind.value for r in relations.relations}


def test_vague_budget_and_subjective_selection_become_blocking_ambiguity():
    instruction = "Buy a high-quality laptop at an affordable price."
    raw = (
        fact("F0001", "Buy", "ACTION", action_type="BUY"),
        fact("F0002", "a high-quality laptop", "ENTITY"),
        fact("F0003", "an affordable price", "CONSTRAINT"),
    )
    facts = _normalize(instruction, raw)
    ambiguities = [f for f in facts if f.kind.value == "AMBIGUITY"]
    assert ambiguities
    relations = infer_candidate8_relations(instruction, facts)
    dispositions = candidate8_dispositions(instruction, facts, relations)
    assert all(dispositions[f.id] is C8FactDisposition.USED for f in ambiguities)


def test_sequence_builds_dependency_without_duplicate_success_guard():
    instruction = "Order components, then release the advance after the order succeeds."
    raw = (
        fact("F0001", "Order components", "ACTION", action_type="ORDER"),
        fact("F0002", "components", "ENTITY"),
        fact("F0003", "release the advance", "ACTION", action_type="RELEASE"),
        fact("F0004", "advance", "ENTITY"),
        fact("F0005", "the order succeeds", "PREDICATE"),
    )
    facts = _normalize(instruction, raw)
    relations = infer_candidate8_relations(instruction, facts)
    kinds = [r.kind.value for r in relations.relations]
    assert kinds.count("AFTER_SUCCESS") == 1
    assert "GUARDS_ACTION" not in kinds


def test_irrelevant_trailing_context_is_removed_from_authority_graph():
    instruction = "Pay courier exactly ₹4,500 for completed route."
    raw = (
        fact("F0001", "Pay", "ACTION", action_type="PAY"),
        fact("F0002", "courier", "ENTITY"),
        fact("F0003", "exactly ₹4,500", "CONSTRAINT"),
        fact("F0004", "completed route", "ENTITY"),
    )
    facts = _normalize(instruction, raw)
    relations = infer_candidate8_relations(instruction, facts)
    dispositions = candidate8_dispositions(instruction, facts, relations)
    context = next(f for f in facts if f.text_span.quote == "completed route")
    assert dispositions[context.id] is C8FactDisposition.IRRELEVANT


def test_invalid_model_relation_proposal_falls_back_to_source_grounded_graph(monkeypatch):
    provider = GroqCandidate8Provider("not-a-real-key", min_request_interval_seconds=0)
    replies = iter([
        ({"facts": [
            {"text_span":{"quote":"Pay","occurrence":1},"kind":"ACTION","polarity":"POSITIVE","action_type":"PAY"},
            {"text_span":{"quote":"printer","occurrence":1},"kind":"ENTITY","polarity":"POSITIVE","action_type":None},
            {"text_span":{"quote":"exactly ₹32,500","occurrence":1},"kind":"CONSTRAINT","polarity":"POSITIVE","action_type":None},
        ]}, {"attempt":1,"candidate_sha256":"facts","finish_reason":"stop"}),
        ({"wrong": []}, {"attempt":1,"candidate_sha256":"bad-1","finish_reason":"stop"}),
        ({"wrong": []}, {"attempt":2,"candidate_sha256":"bad-2","finish_reason":"stop"}),
    ])
    monkeypatch.setattr(provider, "_request", lambda messages, attempt: next(replies))
    parsed = provider.parse_with_metadata("Pay printer exactly ₹32,500 for completed run.")
    signatures = _relation_signatures(parsed.relations)
    assert any(kind == "ACTION_OBJECT" for kind, _, _ in signatures)
    assert any(kind == "CONSTRAINT_APPLIES_TO" for kind, _, _ in signatures)
    assert parsed.provider_trace[-1]["outcome"] == "deterministic_source_fallback"


@pytest.mark.parametrize(
    ("instruction", "first_action", "second_action", "predicate"),
    [
        (
            "Order components, then release the advance after the order succeeds.",
            ("Order components", "ORDER"),
            ("release the advance", "RELEASE"),
            "after the order succeeds",
        ),
        (
            "Reserve the room, then pay the deposit after the reservation is completed.",
            ("Reserve the room", "RESERVE"),
            ("pay the deposit", "PAY"),
            "after the reservation is completed",
        ),
        (
            "Book the venue, then pay the invoice after the booking succeeds.",
            ("Book the venue", "BOOK"),
            ("pay the invoice", "PAY"),
            "after the booking succeeds",
        ),
    ],
)
def test_action_success_tail_is_only_a_dependency(instruction, first_action, second_action, predicate):
    raw = (
        fact("F0001", first_action[0], "ACTION", action_type=first_action[1]),
        fact("F0002", second_action[0], "ACTION", action_type=second_action[1]),
        fact("F0003", predicate, "PREDICATE"),
    )
    facts = _normalize(instruction, raw)
    assert predicate not in {row.text_span.quote for row in facts}
    relations = infer_candidate8_relations(instruction, facts)
    assert sum(row.kind.value in {"AFTER_SUCCESS", "AFTER_COMPLETION"} for row in relations.relations) == 1
    dispositions = candidate8_dispositions(instruction, facts, relations)
    build_typed_ast(facts, relations, dispositions)


def test_trailing_completed_context_is_non_authoritative_entity():
    instruction = "Pay courier exactly ₹4,500 for completed route."
    raw = (
        fact("F0001", "Pay", "ACTION", action_type="PAY"),
        fact("F0002", "courier", "ENTITY"),
        fact("F0003", "exactly ₹4,500", "CONSTRAINT"),
        fact("F0004", "completed route", "PREDICATE"),
    )
    facts = _normalize(instruction, raw)
    context = next(row for row in facts if row.text_span.quote == "completed route")
    assert context.kind.value == "ENTITY"
    relations = infer_candidate8_relations(instruction, facts)
    dispositions = candidate8_dispositions(instruction, facts, relations)
    assert dispositions[context.id] is C8FactDisposition.IRRELEVANT
    build_typed_ast(facts, relations, dispositions)


def test_bare_numeric_constraint_is_folded_into_quantity_object():
    instruction = "Order 125 archive folders."
    raw = (
        fact("F0001", "Order", "ACTION", action_type="ORDER"),
        fact("F0002", "125", "CONSTRAINT"),
        fact("F0003", "archive folders", "ENTITY"),
    )
    facts = _normalize(instruction, raw)
    assert [(row.kind.value, row.text_span.quote) for row in facts] == [
        ("ACTION", "Order"),
        ("ENTITY", "125 archive folders"),
    ]
    relations = infer_candidate8_relations(instruction, facts)
    dispositions = candidate8_dispositions(instruction, facts, relations)
    build_typed_ast(facts, relations, dispositions)


def test_condition_tail_absorbed_into_counterparty_is_split_and_guarded():
    instruction = "Transfer the refund to the customer after finance approves."
    raw = (
        fact("F0001", "Transfer", "ACTION", action_type="TRANSFER"),
        fact("F0002", "refund", "ENTITY"),
        fact("F0003", "the customer after finance approves", "ENTITY"),
        fact("F0004", "finance approves", "PREDICATE"),
    )
    facts = _normalize(instruction, raw)
    assert "the customer" in {row.text_span.quote for row in facts}
    assert "finance approves" in {row.text_span.quote for row in facts}
    relations = infer_candidate8_relations(instruction, facts)
    signatures = _relation_signatures(relations)
    assert any(kind == "ACTION_OBJECT" for kind, _, _ in signatures)
    assert any(kind == "ACTION_COUNTERPARTY" for kind, _, _ in signatures)
    assert any(kind == "GUARDS_ACTION" for kind, _, _ in signatures)
    dispositions = candidate8_dispositions(instruction, facts, relations)
    build_typed_ast(facts, relations, dispositions)


@pytest.mark.parametrize(
    "raw",
    [
        (
            fact("F0001", "Transfer", "ACTION", action_type="TRANSFER"),
            fact("F0002", "the customer after finance approves", "ENTITY"),
            fact("F0003", "finance approves", "PREDICATE"),
            fact("F0004", "refund", "ENTITY"),
        ),
        (
            fact("F0001", "finance approves", "PREDICATE"),
            fact("F0002", "the customer after finance approves", "ENTITY"),
            fact("F0003", "Transfer", "ACTION", action_type="TRANSFER"),
            fact("F0004", "refund", "ENTITY"),
        ),
    ],
)
def test_condition_tail_split_is_independent_of_provider_fact_order(raw):
    instruction = "Transfer the refund to the customer after finance approves."
    facts = _normalize(instruction, raw)
    assert "the customer after finance approves" not in {row.text_span.quote for row in facts}
    assert "the customer" in {row.text_span.quote for row in facts}
    relations = infer_candidate8_relations(instruction, facts)
    signatures = _relation_signatures(relations)
    assert sum(kind == "GUARDS_ACTION" for kind, _, _ in signatures) == 1
    assert sum(kind == "ACTION_OBJECT" for kind, _, _ in signatures) == 1
    assert sum(kind == "ACTION_COUNTERPARTY" for kind, _, _ in signatures) == 1
    dispositions = candidate8_dispositions(instruction, facts, relations)
    assert set(dispositions) == {row.id for row in facts}
    build_typed_ast(facts, relations, dispositions)


@pytest.mark.parametrize(
    "entities",
    [
        ("refund", "the refund", "the customer"),
        ("the refund", "customer", "the customer"),
        ("refund", "the refund", "customer", "the customer"),
    ],
)
def test_determiner_equivalent_entity_duplicates_are_canonicalized(entities):
    instruction = "Transfer the refund to the customer after finance approves."
    raw = [fact("F0001", "Transfer", "ACTION", action_type="TRANSFER")]
    raw.extend(fact(f"F{index:04d}", quote, "ENTITY") for index, quote in enumerate(entities, 2))
    raw.append(fact(f"F{len(raw) + 1:04d}", "finance approves", "PREDICATE"))
    facts = _normalize(instruction, raw)
    entity_quotes = {row.text_span.quote for row in facts if row.kind.value == "ENTITY"}
    assert not ({"refund", "the refund"} <= entity_quotes)
    assert not ({"customer", "the customer"} <= entity_quotes)
    relations = infer_candidate8_relations(instruction, facts)
    kinds = [row.kind.value for row in relations.relations]
    assert kinds.count("ACTION_OBJECT") == 1
    assert kinds.count("ACTION_COUNTERPARTY") == 1
    assert kinds.count("GUARDS_ACTION") == 1
    dispositions = candidate8_dispositions(instruction, facts, relations)
    assert set(dispositions) == {row.id for row in facts}
    build_typed_ast(facts, relations, dispositions)


def test_fail_closed_disposition_error_preserves_sanitized_partial_evidence(monkeypatch):
    instruction = "Transfer the refund to the customer after finance approves."
    provider = GroqCandidate8Provider("not-a-real-key", min_request_interval_seconds=0)
    replies = iter([
        ({"facts": [
            {"text_span":{"quote":"Transfer","occurrence":1},"kind":"ACTION","polarity":"POSITIVE","action_type":"TRANSFER"},
            {"text_span":{"quote":"refund","occurrence":1},"kind":"ENTITY","polarity":"POSITIVE","action_type":None},
            {"text_span":{"quote":"refund to the customer","occurrence":1},"kind":"ENTITY","polarity":"POSITIVE","action_type":None},
            {"text_span":{"quote":"customer","occurrence":1},"kind":"ENTITY","polarity":"POSITIVE","action_type":None},
            {"text_span":{"quote":"finance approves","occurrence":1},"kind":"PREDICATE","polarity":"POSITIVE","action_type":None},
        ]}, {"attempt":1,"candidate_sha256":"facts","finish_reason":"stop"}),
        ({"wrong": []}, {"attempt":1,"candidate_sha256":"bad-1","finish_reason":"stop"}),
        ({"wrong": []}, {"attempt":2,"candidate_sha256":"bad-2","finish_reason":"stop"}),
    ])
    monkeypatch.setattr(provider, "_request", lambda messages, attempt: next(replies))

    result = run_candidate8(instruction, provider)

    assert result.status == "REJECTED"
    assert result.error_code == "C8_UNRESOLVED_ENTITY_DISPOSITION"
    assert result.contract is None
    assert result.graph is None
    assert result.logical_ast is None
    assert result.blocked_actions == frozenset()
    assert result.facts
    assert result.relations is not None
    assert result.dispositions
    assert result.unresolved_fact is not None
    assert result.unresolved_fact.text_span.quote == "refund to the customer"
    assert result.provider_trace
    assert result.provider_trace[-1]["outcome"] == "deterministic_source_fallback"


@pytest.mark.parametrize(
    ("entity_quote", "expected_status", "expected_unresolved"),
    [
        ("to the customer", "COMPILED", None),
        ("refund to the customer", "REJECTED", "refund to the customer"),
        ("the customer after finance approves", "COMPILED", None),
        ("refund to the customer after finance approves", "REJECTED", "refund to the customer"),
    ],
)
def test_crossing_entity_variants_preserve_authority_or_diagnostic_span(
    monkeypatch, entity_quote, expected_status, expected_unresolved,
):
    instruction = "Transfer the refund to the customer after finance approves."
    provider = GroqCandidate8Provider("not-a-real-key", min_request_interval_seconds=0)
    replies = iter([
        ({"facts": [
            {"text_span":{"quote":"Transfer","occurrence":1},"kind":"ACTION","polarity":"POSITIVE","action_type":"TRANSFER"},
            {"text_span":{"quote":"refund","occurrence":1},"kind":"ENTITY","polarity":"POSITIVE","action_type":None},
            {"text_span":{"quote":entity_quote,"occurrence":1},"kind":"ENTITY","polarity":"POSITIVE","action_type":None},
            {"text_span":{"quote":"customer","occurrence":1},"kind":"ENTITY","polarity":"POSITIVE","action_type":None},
            {"text_span":{"quote":"finance approves","occurrence":1},"kind":"PREDICATE","polarity":"POSITIVE","action_type":None},
        ]}, {"attempt":1,"candidate_sha256":"facts","finish_reason":"stop"}),
        ({"wrong": []}, {"attempt":1,"candidate_sha256":"bad-1","finish_reason":"stop"}),
        ({"wrong": []}, {"attempt":2,"candidate_sha256":"bad-2","finish_reason":"stop"}),
    ])
    monkeypatch.setattr(provider, "_request", lambda messages, attempt: next(replies))
    result = run_candidate8(instruction, provider)
    assert result.status == expected_status
    assert result.facts and result.relations is not None
    if expected_unresolved is None:
        assert result.contract is not None
        assert result.unresolved_fact is None
    else:
        assert result.contract is None
        assert result.unresolved_fact is not None
        assert result.unresolved_fact.kind.value == "ENTITY"
        assert result.unresolved_fact.text_span.quote == expected_unresolved


@pytest.mark.parametrize(
    ("instruction", "object_quote", "entity_quote", "nominal_quote"),
    [
        ("Transfer the refund to the customer.", "the refund", "to the customer", "the customer"),
        ("Collect the parcel from the supplier.", "the parcel", "from the supplier", "the supplier"),
        ("Settle the invoice with the carrier.", "the invoice", "with the carrier", "the carrier"),
    ],
)
def test_leading_role_marker_entity_is_canonicalized_and_conserved(
    instruction, object_quote, entity_quote, nominal_quote,
):
    action_quote = instruction.split(" ", 1)[0]
    raw = (
        fact("F0001", action_quote, "ACTION", action_type=action_quote.upper()),
        fact("F0002", object_quote, "ENTITY"),
        fact("F0003", entity_quote, "ENTITY"),
    )
    normalized = normalize_candidate8_facts(instruction, raw)
    assert nominal_quote in {row.text_span.quote for row in normalized.facts}
    assert any(event["outcome"] == "leading_role_marker_removed_from_entity" for event in normalized.events)
    relations = infer_candidate8_relations(instruction, normalized.facts)
    assert sum(row.kind.value == "ACTION_COUNTERPARTY" for row in relations.relations) == 1
    dispositions = candidate8_dispositions(instruction, normalized.facts, relations)
    assert set(dispositions) == {row.id for row in normalized.facts}
    assert set(dispositions.values()) == {C8FactDisposition.USED}
    build_typed_ast(normalized.facts, relations, dispositions)
