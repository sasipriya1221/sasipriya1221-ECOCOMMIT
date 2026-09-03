from decimal import Decimal

import pytest

from ecocommit.candidate6 import action_authorized
from ecocommit.qualification import QualificationCounts, reachable
from ecocommit.semantic_compiler import compile_contract
from ecocommit.semantic_ir import *
from ecocommit.semantic_validation import SemanticValidationError, blocked_actions, canonical_expr, validate_semantic_ir


def src(q, occurrence=1):
    return SpanSource(quote=q, occurrence=occurrence)


def minimal(text="Buy cables"):
    return SemanticIR(
        entities=[Entity(id="E1", kind="OBJECT", text="cables", source=src("cables"))],
        actions=[Action(id="A1", kind="BUY", object="E1", source=src("Buy cables"))],
    )


def test_kleene_truth_tables():
    assert truth_not(Truth.TRUE) == Truth.FALSE
    assert truth_not(Truth.FALSE) == Truth.TRUE
    assert truth_not(Truth.UNKNOWN) == Truth.UNKNOWN
    assert truth_and([Truth.TRUE, Truth.TRUE]) == Truth.TRUE
    assert truth_and([Truth.TRUE, Truth.UNKNOWN]) == Truth.UNKNOWN
    assert truth_and([Truth.UNKNOWN, Truth.FALSE]) == Truth.FALSE
    assert truth_or([Truth.FALSE, Truth.FALSE]) == Truth.FALSE
    assert truth_or([Truth.FALSE, Truth.UNKNOWN]) == Truth.UNKNOWN
    assert truth_or([Truth.UNKNOWN, Truth.TRUE]) == Truth.TRUE


def test_unknown_never_authorizes_guard():
    text = "Buy cables only if approval is received"
    ir = SemanticIR(
        entities=[
            Entity(id="E1", kind="OBJECT", text="cables", source=src("cables")),
            Entity(id="E2", kind="DOCUMENT", text="approval", source=src("approval")),
        ],
        actions=[Action(id="A1", kind="BUY", object="E1", source=src("Buy cables"))],
        predicates=[Predicate(id="P1", kind="APPROVAL", subject="E2", operator="RECEIVED", source=src("approval is received"))],
        guards=[Guard(id="G1", action="A1", expr=Atom(op="ATOM", predicate="P1"), source=src("only if approval is received"))],
    )
    assert action_authorized(ir, "A1", {}) is False
    assert action_authorized(ir, "A1", {"P1": Truth.FALSE}) is False
    assert action_authorized(ir, "A1", {"P1": Truth.TRUE}) is True


def test_restrictive_exception_unknown_is_fail_closed():
    text = "Buy cables if approved except when account is frozen"
    ir = SemanticIR(
        entities=[
            Entity(id="E1", kind="OBJECT", text="cables", source=src("cables")),
            Entity(id="E2", kind="DOCUMENT", text="approval", source=src("approved")),
            Entity(id="E3", kind="RESOURCE", text="account", source=src("account")),
        ],
        actions=[Action(id="A1", kind="BUY", object="E1", source=src("Buy cables"))],
        predicates=[
            Predicate(id="P1", kind="APPROVAL", subject="E2", operator="APPROVED", source=src("approved")),
            Predicate(id="P2", kind="STATE", subject="E3", operator="EQ", value="frozen", source=src("account is frozen")),
        ],
        guards=[Guard(id="G1", action="A1", expr=Atom(op="ATOM", predicate="P1"), source=src("if approved"))],
        exceptions=[ExceptionRule(id="X1", target=ExceptionTarget(kind="ACTION", id="A1"), when=Atom(op="ATOM", predicate="P2"), effect=BlockEffect(effect="BLOCK_ACTION"), source=src("except when account is frozen"))],
    )
    assert not action_authorized(ir, "A1", {"P1": Truth.TRUE})
    assert not action_authorized(ir, "A1", {"P1": Truth.TRUE, "P2": Truth.TRUE})
    assert action_authorized(ir, "A1", {"P1": Truth.TRUE, "P2": Truth.FALSE})


def test_material_ambiguity_blocks_but_presentation_does_not():
    ir = minimal()
    ir.ambiguities = [Ambiguity(id="U1", kind="UNDEFINED_QUANTITY", target=AmbiguityTarget(kind="ACTION_FIELD", id="A1", field="quantity"), source=AbsenceSource(expected="quantity"))]
    assert blocked_actions(ir) == {"A1"}
    ir.ambiguities = [Ambiguity(id="U1", kind="SUBJECTIVE_SELECTION_CRITERION", target=AmbiguityTarget(kind="PRESENTATION"), source=src("cables"))]
    assert blocked_actions(ir) == set()


def test_block_propagates_to_dependent():
    text = "Buy cables then book freight"
    ir = SemanticIR(
        entities=[Entity(id="E1", kind="OBJECT", text="cables", source=src("cables")), Entity(id="E2", kind="OBJECT", text="freight", source=src("freight"))],
        actions=[Action(id="A1", kind="BUY", object="E1", source=src("Buy cables")), Action(id="A2", kind="BOOK", object="E2", source=src("book freight"))],
        dependencies=[Dependency(id="D1", action="A2", prerequisite_action="A1", relation="AFTER_SUCCESS", source=src("then"))],
        ambiguities=[Ambiguity(id="U1", kind="UNDEFINED_QUANTITY", target=AmbiguityTarget(kind="ACTION_FIELD", id="A1", field="quantity"), source=AbsenceSource(expected="quantity"))],
    )
    assert blocked_actions(ir) == {"A1", "A2"}


def test_dependency_cycle_rejected():
    text = "Buy cables after booking freight and book freight after buying cables"
    ir = SemanticIR(
        entities=[Entity(id="E1", kind="OBJECT", text="cables", source=src("cables")), Entity(id="E2", kind="OBJECT", text="freight", source=src("freight"))],
        actions=[Action(id="A1", kind="BUY", object="E1", source=src("Buy cables")), Action(id="A2", kind="BOOK", object="E2", source=src("book freight"))],
        dependencies=[Dependency(id="D1", action="A1", prerequisite_action="A2", relation="AFTER_SUCCESS", source=src("after", 1)), Dependency(id="D2", action="A2", prerequisite_action="A1", relation="AFTER_SUCCESS", source=src("after", 2))],
    )
    with pytest.raises(SemanticValidationError) as exc:
        validate_semantic_ir(ir, text)
    assert any(x.code == "IR_DEPENDENCY_CYCLE" for x in exc.value.findings)


def test_compiler_is_deterministic_and_conserves_action_object():
    text = "Buy cables"
    ir = minimal(text)
    first = compile_contract(ir, text)
    second = compile_contract(ir, text)
    assert first[0].model_dump_json() == second[0].model_dump_json()
    assert {e.source_id for e in first[1]} >= {"E1", "A1"}
    action_clause = next(c for c in first[0].clauses if c.clause_id == "ir_A1")
    assert "ir_E1" in action_clause.depends_on


def test_money_and_quantity_normalization():
    assert normalize_money("1.5 lakh", "₹") == (Decimal("150000.0"), "INR")
    assert normalize_quantity("three", "rooms") == (Decimal("3"), "room")
    with pytest.raises(ValueError, match="IR_CURRENCY_INVALID"):
        normalize_money("4000", "$")
    with pytest.raises(ValueError, match="IR_QUANTITY_INVALID"):
        normalize_quantity("minus five", "units")


def test_contradictory_amounts_rejected():
    text = "Buy device for at most ₹20,000 and at least ₹30,000"
    ir = SemanticIR(
        entities=[Entity(id="E1", kind="OBJECT", text="device", source=src("device"))],
        actions=[Action(id="A1", kind="BUY", object="E1", source=src("Buy device"))],
        constraints=[
            Constraint(id="C1", action="A1", kind="MAX_TOTAL_COST", money=Money(raw_amount="20000", raw_currency="₹", source=src("₹20,000"))),
            Constraint(id="C2", action="A1", kind="MIN_TOTAL_COST", money=Money(raw_amount="30000", raw_currency="₹", source=src("₹30,000"))),
        ],
    )
    with pytest.raises(SemanticValidationError) as exc:
        validate_semantic_ir(ir, text)
    assert any(x.code == "IR_CONTRADICTORY_CONSTRAINTS" for x in exc.value.findings)


def test_boolean_metamorphic_canonicalization():
    a = And(op="AND", args=[Atom(op="ATOM", predicate="P2"), Atom(op="ATOM", predicate="P1")])
    b = And(op="AND", args=[Atom(op="ATOM", predicate="P1"), Atom(op="ATOM", predicate="P2")])
    assert canonical_expr(a) == canonical_expr(b)
    assert eval_expr(a, {"P1": Truth.TRUE, "P2": Truth.FALSE}) == Truth.FALSE
    assert eval_expr(Or(op="OR", args=a.args), {"P1": Truth.TRUE, "P2": Truth.FALSE}) == Truth.TRUE


def test_early_stop_separates_ambiguous_reachability():
    c = QualificationCounts(total=60, processed=50, case_passes=50, autonomous=32, correct_autonomous=32, ambiguous_total=20, ambiguous_processed=19, ambiguous_correct=16)
    assert not reachable(c)


def test_reliability_reachability_does_not_assume_every_missing_case_autonomous():
    c = QualificationCounts(total=60, processed=50, case_passes=49, autonomous=35, correct_autonomous=34, ambiguous_total=10, ambiguous_processed=8, ambiguous_correct=8)
    # Coverage needs one extra autonomous case: best reliability is 35/36 < .97.
    assert not reachable(c)


def test_zero_safety_error_is_immediately_unreachable():
    c = QualificationCounts(total=60, processed=1, case_passes=1, autonomous=1, correct_autonomous=1, ambiguous_total=0, ambiguous_processed=0, ambiguous_correct=0, fail_open=1)
    assert not reachable(c)
