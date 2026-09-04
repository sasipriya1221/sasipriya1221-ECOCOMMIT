from __future__ import annotations

from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Annotated, Literal, Mapping, Union

from pydantic import BaseModel, Field


class EntityKind(str, Enum):
    OBJECT = "OBJECT"
    COUNTERPARTY = "COUNTERPARTY"
    PERSON = "PERSON"
    ORGANIZATION = "ORGANIZATION"
    DOCUMENT = "DOCUMENT"
    EVENT = "EVENT"
    RESOURCE = "RESOURCE"
    OTHER = "OTHER"


class ActionKind(str, Enum):
    BUY = "BUY"
    ORDER = "ORDER"
    PAY = "PAY"
    TRANSFER = "TRANSFER"
    HIRE = "HIRE"
    BOOK = "BOOK"
    RENEW = "RENEW"
    RESERVE = "RESERVE"
    SELECT = "SELECT"
    RELEASE = "RELEASE"
    CANCEL = "CANCEL"
    COMMIT = "COMMIT"


class ConstraintKind(str, Enum):
    MAX_TOTAL_COST = "MAX_TOTAL_COST"
    MAX_UNIT_COST = "MAX_UNIT_COST"
    MIN_TOTAL_COST = "MIN_TOTAL_COST"
    EXACT_TOTAL_COST = "EXACT_TOTAL_COST"


class PredicateKind(str, Enum):
    STATE = "STATE"
    APPROVAL = "APPROVAL"
    EVENT = "EVENT"
    DOCUMENT_STATUS = "DOCUMENT_STATUS"
    COMPARISON = "COMPARISON"
    EXISTENCE = "EXISTENCE"


class PredicateOperator(str, Enum):
    EQ = "EQ"
    NEQ = "NEQ"
    LT = "LT"
    LTE = "LTE"
    GT = "GT"
    GTE = "GTE"
    EXISTS = "EXISTS"
    OCCURRED = "OCCURRED"
    APPROVED = "APPROVED"
    VALID = "VALID"
    CURRENT = "CURRENT"
    RECEIVED = "RECEIVED"


class AmbiguityKind(str, Enum):
    UNDEFINED_QUANTITY = "UNDEFINED_QUANTITY"
    UNDEFINED_BUDGET = "UNDEFINED_BUDGET"
    SUBJECTIVE_SELECTION_CRITERION = "SUBJECTIVE_SELECTION_CRITERION"
    UNCLEAR_COUNTERPARTY = "UNCLEAR_COUNTERPARTY"
    VAGUE_PERMISSION = "VAGUE_PERMISSION"
    AMBIGUOUS_CONDITION = "AMBIGUOUS_CONDITION"
    MISSING_REQUIRED_INFORMATION = "MISSING_REQUIRED_INFORMATION"
    UNSUPPORTED_SEMANTIC_STRUCTURE = "UNSUPPORTED_SEMANTIC_STRUCTURE"


EntityRef = Annotated[str, Field(pattern=r"^E\d+$")]
ActionRef = Annotated[str, Field(pattern=r"^A\d+$")]
PredicateRef = Annotated[str, Field(pattern=r"^P\d+$")]
ConstraintRef = Annotated[str, Field(pattern=r"^C\d+$")]
GuardRef = Annotated[str, Field(pattern=r"^G\d+$")]
DependencyRef = Annotated[str, Field(pattern=r"^D\d+$")]


class SpanSource(BaseModel):
    kind: Literal["SPAN"] = "SPAN"
    quote: str = Field(min_length=1)
    occurrence: int = Field(default=1, ge=1)


class AbsenceSource(BaseModel):
    kind: Literal["ABSENCE"] = "ABSENCE"
    expected: str = Field(min_length=1)


SourceGrounding = Annotated[Union[SpanSource, AbsenceSource], Field(discriminator="kind")]


class Entity(BaseModel):
    id: EntityRef
    kind: EntityKind
    text: str = Field(min_length=1)
    source: SpanSource


class Quantity(BaseModel):
    raw_value: str = Field(min_length=1)
    raw_unit: str = Field(min_length=1)
    source: SpanSource


class Action(BaseModel):
    id: ActionRef
    kind: ActionKind
    object: EntityRef
    counterparty: EntityRef | None = None
    quantity: Quantity | None = None
    source: SpanSource


class Money(BaseModel):
    raw_amount: str = Field(min_length=1)
    raw_currency: str = Field(min_length=1)
    source: SpanSource


class Constraint(BaseModel):
    id: ConstraintRef
    action: ActionRef
    kind: ConstraintKind
    money: Money


class Predicate(BaseModel):
    id: PredicateRef
    kind: PredicateKind
    subject: EntityRef
    attribute: str | None = None
    operator: PredicateOperator
    value: str | None = None
    source: SpanSource


class Atom(BaseModel):
    op: Literal["ATOM"]
    predicate: PredicateRef


class And(BaseModel):
    op: Literal["AND"]
    args: list["BoolExpr"] = Field(min_length=2)


class Or(BaseModel):
    op: Literal["OR"]
    args: list["BoolExpr"] = Field(min_length=2)


class Not(BaseModel):
    op: Literal["NOT"]
    arg: "BoolExpr"


BoolExpr = Annotated[Union[Atom, And, Or, Not], Field(discriminator="op")]
And.model_rebuild()
Or.model_rebuild()
Not.model_rebuild()


class Guard(BaseModel):
    id: GuardRef
    action: ActionRef
    mode: Literal["ONLY_IF"] = "ONLY_IF"
    expr: BoolExpr
    source: SpanSource


class Dependency(BaseModel):
    id: DependencyRef
    action: ActionRef
    prerequisite_action: ActionRef
    relation: Literal["AFTER_COMPLETION", "AFTER_SUCCESS"]
    source: SpanSource


class ActionExceptionTarget(BaseModel):
    kind: Literal["ACTION"]
    id: ActionRef


class GuardExceptionTarget(BaseModel):
    kind: Literal["GUARD"]
    id: GuardRef


class ConstraintExceptionTarget(BaseModel):
    kind: Literal["CONSTRAINT"]
    id: ConstraintRef


ExceptionTarget = Annotated[Union[ActionExceptionTarget, GuardExceptionTarget, ConstraintExceptionTarget], Field(discriminator="kind")]


class BlockEffect(BaseModel):
    effect: Literal["BLOCK_ACTION"]


class AllowanceEffect(BaseModel):
    effect: Literal["ADD_MONETARY_ALLOWANCE"]
    money: Money


ExceptionEffect = Annotated[Union[BlockEffect, AllowanceEffect], Field(discriminator="effect")]


class ExceptionRule(BaseModel):
    id: str = Field(pattern=r"^X\d+$")
    target: ExceptionTarget
    when: BoolExpr
    effect: ExceptionEffect
    source: SpanSource


class ActionFieldAmbiguityTarget(BaseModel):
    kind: Literal["ACTION_FIELD"]
    id: ActionRef
    field: str = Field(min_length=1)


class PredicateAmbiguityTarget(BaseModel):
    kind: Literal["PREDICATE"]
    id: PredicateRef
    field: str | None = None


class GuardAmbiguityTarget(BaseModel):
    kind: Literal["GUARD"]
    id: GuardRef
    field: str | None = None


class ConstraintAmbiguityTarget(BaseModel):
    kind: Literal["CONSTRAINT"]
    id: ConstraintRef
    field: str | None = None


class CounterpartyAmbiguityTarget(BaseModel):
    kind: Literal["COUNTERPARTY"]
    id: EntityRef
    field: str | None = None


class DependencyAmbiguityTarget(BaseModel):
    kind: Literal["DEPENDENCY"]
    id: DependencyRef
    field: str | None = None


class PresentationAmbiguityTarget(BaseModel):
    kind: Literal["PRESENTATION"]
    id: None = None
    field: str | None = None


AmbiguityTarget = Annotated[
    Union[
        ActionFieldAmbiguityTarget, PredicateAmbiguityTarget, GuardAmbiguityTarget,
        ConstraintAmbiguityTarget, CounterpartyAmbiguityTarget,
        DependencyAmbiguityTarget, PresentationAmbiguityTarget,
    ],
    Field(discriminator="kind"),
]


class Ambiguity(BaseModel):
    id: str = Field(pattern=r"^U\d+$")
    kind: AmbiguityKind
    target: AmbiguityTarget
    source: SourceGrounding


class SemanticIR(BaseModel):
    schema_version: Literal["semantic-ir-v1"] = "semantic-ir-v1"
    entities: list[Entity] = Field(default_factory=list)
    actions: list[Action] = Field(min_length=1)
    constraints: list[Constraint] = Field(default_factory=list)
    predicates: list[Predicate] = Field(default_factory=list)
    guards: list[Guard] = Field(default_factory=list)
    dependencies: list[Dependency] = Field(default_factory=list)
    exceptions: list[ExceptionRule] = Field(default_factory=list)
    ambiguities: list[Ambiguity] = Field(default_factory=list)


class Truth(str, Enum):
    TRUE = "TRUE"
    FALSE = "FALSE"
    UNKNOWN = "UNKNOWN"


def truth_not(value: Truth) -> Truth:
    return {Truth.TRUE: Truth.FALSE, Truth.FALSE: Truth.TRUE, Truth.UNKNOWN: Truth.UNKNOWN}[value]


def truth_and(values: list[Truth]) -> Truth:
    if Truth.FALSE in values:
        return Truth.FALSE
    if Truth.UNKNOWN in values:
        return Truth.UNKNOWN
    return Truth.TRUE


def truth_or(values: list[Truth]) -> Truth:
    if Truth.TRUE in values:
        return Truth.TRUE
    if Truth.UNKNOWN in values:
        return Truth.UNKNOWN
    return Truth.FALSE


def eval_expr(expr: BoolExpr, predicate_values: Mapping[str, Truth]) -> Truth:
    if expr.op == "ATOM":
        return predicate_values.get(expr.predicate, Truth.UNKNOWN)
    if expr.op == "NOT":
        return truth_not(eval_expr(expr.arg, predicate_values))
    values = [eval_expr(arg, predicate_values) for arg in expr.args]
    return truth_and(values) if expr.op == "AND" else truth_or(values)


_NUMBER_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20,
}
_UNIT_ALIASES = {
    "unit": "unit", "units": "unit", "item": "unit", "items": "unit",
    "piece": "unit", "pieces": "unit", "seat": "seat", "seats": "seat",
    "room": "room", "rooms": "room", "day": "day", "days": "day",
    "week": "week", "weeks": "week", "month": "month", "months": "month",
    "year": "year", "years": "year",
}


def normalize_quantity(raw_value: str, raw_unit: str) -> tuple[Decimal, str]:
    value_text = raw_value.strip().lower().replace(",", "")
    if value_text in _NUMBER_WORDS:
        value = Decimal(_NUMBER_WORDS[value_text])
    else:
        if value_text.startswith("minus "):
            tail = value_text[6:].strip()
            value = Decimal(-_NUMBER_WORDS[tail]) if tail in _NUMBER_WORDS else Decimal("NaN")
        else:
            try:
                value = Decimal(value_text)
            except InvalidOperation as exc:
                raise ValueError("IR_QUANTITY_INVALID") from exc
    if not value.is_finite() or value <= 0:
        raise ValueError("IR_QUANTITY_INVALID")
    unit_text = raw_unit.strip().lower()
    unit = _UNIT_ALIASES.get(unit_text)
    if unit is None:
        unit = unit_text[:-1] if unit_text.endswith("s") and len(unit_text) > 2 else unit_text
    if not unit:
        raise ValueError("IR_UNIT_INVALID")
    return value, unit


def normalize_money(raw_amount: str, raw_currency: str) -> tuple[Decimal, str]:
    currency = raw_currency.strip().upper()
    currency = {"₹": "INR", "RS": "INR", "RS.": "INR", "INR": "INR"}.get(currency, currency)
    if currency != "INR":
        raise ValueError("IR_CURRENCY_INVALID")
    text = raw_amount.strip().lower().replace(",", "")
    for prefix in ("₹", "rs.", "rs"):
        if text.startswith(prefix):
            text = text[len(prefix):].strip()
    multiplier = Decimal(1)
    for suffix, value in (("lakhs", 100000), ("lakh", 100000), ("crores", 10000000), ("crore", 10000000)):
        if text.endswith(suffix):
            multiplier = Decimal(value)
            text = text[:-len(suffix)].strip()
            break
    try:
        amount = Decimal(text) * multiplier
    except InvalidOperation as exc:
        raise ValueError("IR_MONEY_INVALID") from exc
    if not amount.is_finite() or amount < 0:
        raise ValueError("IR_MONEY_INVALID")
    return amount, currency
