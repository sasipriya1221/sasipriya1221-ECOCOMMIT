from decimal import Decimal

from ecocommit.candidate7_compile import _quantity, compile_graph_v2
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


def test_bare_action_uses_quantity_from_linked_object_span():
    instruction = "Order 75 archive boxes."
    action = _fact("F0001", "Order", FactKind.ACTION, action_type="ORDER")
    obj = _fact("F0002", "75 archive boxes", FactKind.ENTITY)
    relation = Relation(
        kind=RelationKind.ACTION_OBJECT,
        left="F0001",
        right="F0002",
        justification_span="Order 75 archive boxes",
    )
    graph = C7Graph(
        instruction=instruction,
        facts=(action, obj),
        relations=(relation,),
        guards=(),
        dependencies=(),
        blocked_actions=frozenset(),
    )

    contract = compile_graph_v2(graph)
    quantities = [c for c in contract.clauses if c.clause_type is ClauseType.QUANTITY]

    assert len(quantities) == 1
    assert quantities[0].normalized_value == "75 box"


def test_existing_action_span_quantity_path_is_unchanged():
    assert _quantity("Order 75 archive boxes", "archive boxes") == (Decimal("75"), "box")


def test_no_quantity_does_not_infer_unrelated_price_number():
    assert _quantity("Buy", "office chair ₹9000") is None
    assert _quantity("Buy", "printer model 4200") is None
