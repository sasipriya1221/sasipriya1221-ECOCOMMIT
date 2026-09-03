from ecocommit.semantic_ir import *
from ecocommit.semantic_validation import blocked_actions,SemanticValidationError,validate_semantic_ir
from ecocommit.semantic_compiler import compile_contract
from ecocommit.qualification import *

def src(q):return SpanSource(quote=q)
def minimal(text="Buy cables"):
    return SemanticIR(entities=[Entity(id="E1",kind="OBJECT",text="cables",source=src("cables"))],actions=[Action(id="A1",kind="BUY",object="E1",source=src("Buy cables"))])

def test_kleene_truth_tables():
    assert truth_not(Truth.UNKNOWN)==Truth.UNKNOWN
    assert truth_and([Truth.TRUE,Truth.UNKNOWN])==Truth.UNKNOWN
    assert truth_and([Truth.UNKNOWN,Truth.FALSE])==Truth.FALSE
    assert truth_or([Truth.FALSE,Truth.UNKNOWN])==Truth.UNKNOWN
    assert truth_or([Truth.UNKNOWN,Truth.TRUE])==Truth.TRUE

def test_material_ambiguity_blocks_but_nonmaterial_does_not():
    ir=minimal(); ir.ambiguities=[Ambiguity(id="U1",kind="UNDEFINED_QUANTITY",target=AmbiguityTarget(kind="ACTION_FIELD",id="A1",field="quantity"),source=AbsenceSource(expected="quantity"))]
    assert blocked_actions(ir)=={"A1"}
    ir.ambiguities=[Ambiguity(id="U1",kind="SUBJECTIVE_SELECTION_CRITERION",target=AmbiguityTarget(kind="NON_MATERIAL"),source=src("cables"))]
    assert blocked_actions(ir)==set()

def test_block_propagates_to_dependent():
    text="Buy cables then book freight"
    ir=SemanticIR(entities=[Entity(id="E1",kind="OBJECT",text="cables",source=src("cables")),Entity(id="E2",kind="OBJECT",text="freight",source=src("freight"))],actions=[Action(id="A1",kind="BUY",object="E1",source=src("Buy cables")),Action(id="A2",kind="BOOK",object="E2",source=src("book freight"))],dependencies=[Dependency(id="D1",action="A2",prerequisite_action="A1",relation="AFTER_SUCCESS",source=src("then"))],ambiguities=[Ambiguity(id="U1",kind="UNDEFINED_QUANTITY",target=AmbiguityTarget(kind="ACTION_FIELD",id="A1",field="quantity"),source=AbsenceSource(expected="quantity"))])
    assert blocked_actions(ir)=={"A1","A2"}

def test_dependency_cycle_rejected():
    text="Buy cables after booking freight and book freight after buying cables"
    ir=SemanticIR(entities=[Entity(id="E1",kind="OBJECT",text="cables",source=src("cables")),Entity(id="E2",kind="OBJECT",text="freight",source=src("freight"))],actions=[Action(id="A1",kind="BUY",object="E1",source=src("Buy cables")),Action(id="A2",kind="BOOK",object="E2",source=src("book freight"))],dependencies=[Dependency(id="D1",action="A1",prerequisite_action="A2",relation="AFTER_SUCCESS",source=src("after")),Dependency(id="D2",action="A2",prerequisite_action="A1",relation="AFTER_SUCCESS",source=src("after"))])
    try:validate_semantic_ir(ir,text);assert False
    except SemanticValidationError as e:assert any(x.code=="IR_DEPENDENCY_CYCLE" for x in e.findings)

def test_compiler_is_deterministic_and_conserves():
    text="Buy cables"
    ir=minimal(text); a=compile_contract(ir,text); b=compile_contract(ir,text)
    assert a[0].model_dump_json()==b[0].model_dump_json()
    assert {e.source_id for e in a[1]}=={"E1","A1"}

def test_money_normalization():
    assert normalize_money("1.5 lakh","₹")== (Decimal("150000.0"),"INR")

def test_early_stop_separates_ambiguous_reachability():
    # Candidate-5 defect regression: only genuinely remaining ambiguous rows can repair clarification accuracy.
    c=QualificationCounts(total=60,processed=50,case_passes=50,autonomous=32,correct_autonomous=32,ambiguous_total=20,ambiguous_processed=19,ambiguous_correct=16)
    assert not reachable(c) # at best 17/20=.85 < .90

def test_zero_safety_error_is_immediately_unreachable():
    c=QualificationCounts(total=60,processed=1,case_passes=1,autonomous=1,correct_autonomous=1,ambiguous_total=0,ambiguous_processed=0,ambiguous_correct=0,fail_open=1)
    assert not reachable(c)
