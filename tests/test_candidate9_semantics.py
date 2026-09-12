from __future__ import annotations

import pytest

from ecocommit.candidate7_flat import LabeledFact
from ecocommit.candidate8_normalize import Candidate8DispositionError
from ecocommit.candidate9_normalize import candidate9_dispositions, infer_candidate9_relations


def fact(fid, quote, kind, *, action_type=None):
    return LabeledFact.model_validate({
        "id": fid,
        "text_span": {"quote": quote, "occurrence": 1},
        "kind": kind,
        "polarity": "POSITIVE",
        "action_type": action_type,
    })


@pytest.mark.parametrize("prefix", ["At most ₹500", "Exactly INR 750", "No more than Rs. 900"])
def test_fronted_constraint_binds_to_unique_action_in_same_clause(prefix):
    instruction = f"{prefix}, buy labels."
    facts = (
        fact("F0001", prefix, "CONSTRAINT"),
        fact("F0002", "buy", "ACTION", action_type="BUY"),
        fact("F0003", "labels", "ENTITY"),
    )
    relations = infer_candidate9_relations(instruction, facts)
    signatures = {(row.kind.value, row.left, row.right) for row in relations.relations}
    assert ("CONSTRAINT_APPLIES_TO", "F0001", "F0002") in signatures
    assert ("ACTION_OBJECT", "F0002", "F0003") in signatures
    assert set(candidate9_dispositions(instruction, facts, relations)) == {"F0001", "F0002", "F0003"}


def test_fronted_exception_binds_to_unique_action_in_same_clause():
    instruction = "Except damaged items, refund the order."
    facts = (
        fact("F0001", "damaged items", "EXCEPTION"),
        fact("F0002", "refund", "ACTION", action_type="TRANSFER"),
        fact("F0003", "the order", "ENTITY"),
    )
    relations = infer_candidate9_relations(instruction, facts)
    assert ("EXCEPTION_TARGET", "F0001", "F0002") in {
        (row.kind.value, row.left, row.right) for row in relations.relations
    }


def test_fronted_modifier_with_competing_actions_fails_closed():
    instruction = "At most ₹500, buy labels and pay shipping."
    facts = (
        fact("F0001", "At most ₹500", "CONSTRAINT"),
        fact("F0002", "buy", "ACTION", action_type="BUY"),
        fact("F0003", "labels", "ENTITY"),
        fact("F0004", "pay", "ACTION", action_type="PAY"),
        fact("F0005", "shipping", "ENTITY"),
    )
    relations = infer_candidate9_relations(instruction, facts)
    assert not [row for row in relations.relations if row.left == "F0001"]
    with pytest.raises(Candidate8DispositionError, match="C8_UNRESOLVED_CONSTRAINT_DISPOSITION"):
        candidate9_dispositions(instruction, facts, relations)


def test_modifier_does_not_cross_explicit_clause_boundary():
    instruction = "At most ₹500; buy labels."
    facts = (
        fact("F0001", "At most ₹500", "CONSTRAINT"),
        fact("F0002", "buy", "ACTION", action_type="BUY"),
        fact("F0003", "labels", "ENTITY"),
    )
    relations = infer_candidate9_relations(instruction, facts)
    assert not [row for row in relations.relations if row.left == "F0001"]
