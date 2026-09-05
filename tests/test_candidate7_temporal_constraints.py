from ecocommit.candidate7 import Candidate7Result
from ecocommit.candidate7_compile import _constraint_kind_v2, compile_graph_v2
from ecocommit.candidate7_evaluator import semantic_match
from ecocommit.candidate7_flat import FactKind, LabeledFact, Polarity, Relation, RelationKind, TextSpan
from ecocommit.candidate7_structure import C7Graph
from ecocommit.contracts import ClauseType


def _fact(fid: str, quote: str, kind: FactKind, *, action_type: str | None = None) -> LabeledFact:
    return LabeledFact(
        id=fid,
        text_span=TextSpan(quote=quote, occurrence=1),
        kind=kind,
        polarity=Polarity.POSITIVE,
        action_type=action_type,
    )


def _relation(kind: RelationKind, left: str, right: str, span: str) -> Relation:
    return Relation(kind=kind, left=left, right=right, justification_span=span)


def _result(graph: C7Graph) -> Candidate7Result:
    contract = compile_graph_v2(graph)
    return Candidate7Result(
        status="COMPILED",
        contract=contract,
        graph=graph,
        facts=graph.facts,
        relations=None,
        blocked_actions=frozenset(),
    )


def test_temporal_duration_constraint_compiles_as_temporal_clause():
    instruction = "Hire two temporary auditors for one week."
    action = _fact("F0001", "Hire", FactKind.ACTION, action_type="HIRE")
    obj = _fact("F0002", "two temporary auditors", FactKind.ENTITY)
    duration = _fact("F0003", "for one week", FactKind.CONSTRAINT)
    graph = C7Graph(
        instruction=instruction,
        facts=(action, obj, duration),
        relations=(
            _relation(RelationKind.ACTION_OBJECT, "F0001", "F0002", "Hire two temporary auditors"),
            _relation(RelationKind.CONSTRAINT_APPLIES_TO, "F0003", "F0001", "for one week"),
        ),
        guards=(), dependencies=(), blocked_actions=frozenset(),
    )

    contract = compile_graph_v2(graph)
    temporal = [c for c in contract.clauses if c.clause_type is ClauseType.TEMPORAL]

    assert _constraint_kind_v2("for one week") == "TEMPORAL_DURATION"
    assert _constraint_kind_v2("for another year") == "TEMPORAL_DURATION"
    assert _constraint_kind_v2("for 6 months") == "TEMPORAL_DURATION"
    assert len(temporal) == 1
    assert temporal[0].normalized_value == "TEMPORAL_DURATION:for one week"
    assert temporal[0].depends_on == ["c_F0001"]


def test_duration_only_does_not_create_false_monetary_mismatch():
    instruction = "Hire two temporary auditors for one week."
    action = _fact("F0001", "Hire", FactKind.ACTION, action_type="HIRE")
    obj = _fact("F0002", "two temporary auditors", FactKind.ENTITY)
    duration = _fact("F0003", "for one week", FactKind.CONSTRAINT)
    graph = C7Graph(
        instruction=instruction,
        facts=(action, obj, duration),
        relations=(
            _relation(RelationKind.ACTION_OBJECT, "F0001", "F0002", "Hire two temporary auditors"),
            _relation(RelationKind.CONSTRAINT_APPLIES_TO, "F0003", "F0001", "for one week"),
        ),
        guards=(), dependencies=(), blocked_actions=frozenset(),
    )
    gold = {
        "expected_status": "COMPILED",
        "gold_semantic_ir": {
            "actions": [{"kind": "HIRE", "object_terms": ["temporary", "auditors"], "quantity": "2"}],
        },
    }

    ok, reasons = semantic_match(_result(graph), gold)

    assert ok is True
    assert reasons == []


def test_temporal_and_monetary_constraints_evaluate_independently():
    instruction = "Hire two temporary auditors for one week for no more than ₹20,000."
    action = _fact("F0001", "Hire", FactKind.ACTION, action_type="HIRE")
    obj = _fact("F0002", "two temporary auditors", FactKind.ENTITY)
    duration = _fact("F0003", "for one week", FactKind.CONSTRAINT)
    money = _fact("F0004", "no more than ₹20,000", FactKind.CONSTRAINT)
    graph = C7Graph(
        instruction=instruction,
        facts=(action, obj, duration, money),
        relations=(
            _relation(RelationKind.ACTION_OBJECT, "F0001", "F0002", "Hire two temporary auditors"),
            _relation(RelationKind.CONSTRAINT_APPLIES_TO, "F0003", "F0001", "for one week"),
            _relation(RelationKind.CONSTRAINT_APPLIES_TO, "F0004", "F0001", "no more than ₹20,000"),
        ),
        guards=(), dependencies=(), blocked_actions=frozenset(),
    )
    gold = {
        "expected_status": "COMPILED",
        "gold_semantic_ir": {
            "actions": [{"kind": "HIRE", "object_terms": ["temporary", "auditors"], "quantity": "2"}],
            "constraints": [["MAX_TOTAL_COST", "20000"]],
        },
    }

    result = _result(graph)
    ok, reasons = semantic_match(result, gold)

    assert ok is True
    assert reasons == []
    assert sum(c.clause_type is ClauseType.TEMPORAL for c in result.contract.clauses) == 1
    assert sum(c.clause_type is ClauseType.AMOUNT for c in result.contract.clauses) == 1


def test_existing_monetary_constraint_typing_is_unchanged():
    assert _constraint_kind_v2("exactly ₹32,500") == "EXACT_TOTAL_COST"
    assert _constraint_kind_v2("no more than ₹9,000 each") == "MAX_UNIT_COST"
    assert _constraint_kind_v2("₹18,000 or less") == "MAX_TOTAL_COST"
