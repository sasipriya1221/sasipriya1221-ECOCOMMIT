from __future__ import annotations

from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, model_validator


class EntityKind(str, Enum):
    OBJECT="OBJECT"; COUNTERPARTY="COUNTERPARTY"; PERSON="PERSON"; ORGANIZATION="ORGANIZATION"; DOCUMENT="DOCUMENT"; EVENT="EVENT"; RESOURCE="RESOURCE"; OTHER="OTHER"
class ActionKind(str, Enum):
    BUY="BUY"; ORDER="ORDER"; PAY="PAY"; TRANSFER="TRANSFER"; HIRE="HIRE"; BOOK="BOOK"; RENEW="RENEW"; RESERVE="RESERVE"; SELECT="SELECT"; RELEASE="RELEASE"; CANCEL="CANCEL"; COMMIT="COMMIT"
class ConstraintKind(str, Enum):
    MAX_TOTAL_COST="MAX_TOTAL_COST"; MAX_UNIT_COST="MAX_UNIT_COST"; MIN_TOTAL_COST="MIN_TOTAL_COST"; EXACT_TOTAL_COST="EXACT_TOTAL_COST"
class PredicateKind(str, Enum):
    STATE="STATE"; APPROVAL="APPROVAL"; EVENT="EVENT"; DOCUMENT_STATUS="DOCUMENT_STATUS"; COMPARISON="COMPARISON"; EXISTENCE="EXISTENCE"
class PredicateOperator(str, Enum):
    EQ="EQ"; NEQ="NEQ"; LT="LT"; LTE="LTE"; GT="GT"; GTE="GTE"; EXISTS="EXISTS"; OCCURRED="OCCURRED"; APPROVED="APPROVED"; VALID="VALID"; CURRENT="CURRENT"; RECEIVED="RECEIVED"
class AmbiguityKind(str, Enum):
    UNDEFINED_QUANTITY="UNDEFINED_QUANTITY"; UNDEFINED_BUDGET="UNDEFINED_BUDGET"; SUBJECTIVE_SELECTION_CRITERION="SUBJECTIVE_SELECTION_CRITERION"; UNCLEAR_COUNTERPARTY="UNCLEAR_COUNTERPARTY"; VAGUE_PERMISSION="VAGUE_PERMISSION"; AMBIGUOUS_CONDITION="AMBIGUOUS_CONDITION"; MISSING_REQUIRED_INFORMATION="MISSING_REQUIRED_INFORMATION"; UNSUPPORTED_SEMANTIC_STRUCTURE="UNSUPPORTED_SEMANTIC_STRUCTURE"

class SpanSource(BaseModel):
    kind: Literal["SPAN"]="SPAN"
    quote: str = Field(min_length=1)
    occurrence: int = Field(default=1, ge=1)
class AbsenceSource(BaseModel):
    kind: Literal["ABSENCE"]="ABSENCE"
    expected: str = Field(min_length=1)
SourceGrounding = Annotated[Union[SpanSource, AbsenceSource], Field(discriminator="kind")]

class Entity(BaseModel):
    id: str = Field(pattern=r"^E\d+$"); kind: EntityKind; text: str = Field(min_length=1); source: SpanSource
class Quantity(BaseModel):
    raw_value: str = Field(min_length=1); raw_unit: str = Field(min_length=1); source: SpanSource
class Action(BaseModel):
    id: str = Field(pattern=r"^A\d+$"); kind: ActionKind; object: str; counterparty: str|None=None; quantity: Quantity|None=None; source: SpanSource
class Money(BaseModel):
    raw_amount: str = Field(min_length=1); raw_currency: str = Field(min_length=1); source: SpanSource
class Constraint(BaseModel):
    id: str = Field(pattern=r"^C\d+$"); action: str; kind: ConstraintKind; money: Money
class Predicate(BaseModel):
    id: str = Field(pattern=r"^P\d+$"); kind: PredicateKind; subject: str; attribute: str|None=None; operator: PredicateOperator; value: str|None=None; source: SpanSource

class Atom(BaseModel):
    op: Literal["ATOM"]; predicate: str
class And(BaseModel):
    op: Literal["AND"]; args: list["BoolExpr"] = Field(min_length=2)
class Or(BaseModel):
    op: Literal["OR"]; args: list["BoolExpr"] = Field(min_length=2)
class Not(BaseModel):
    op: Literal["NOT"]; arg: "BoolExpr"
BoolExpr = Annotated[Union[Atom,And,Or,Not], Field(discriminator="op")]
And.model_rebuild(); Or.model_rebuild(); Not.model_rebuild()

class Guard(BaseModel):
    id: str = Field(pattern=r"^G\d+$"); action: str; mode: Literal["ONLY_IF"]="ONLY_IF"; expr: BoolExpr; source: SpanSource
class Dependency(BaseModel):
    id: str = Field(pattern=r"^D\d+$"); action: str; prerequisite_action: str; relation: Literal["AFTER_COMPLETION","AFTER_SUCCESS"]; source: SpanSource
class ExceptionTarget(BaseModel):
    kind: Literal["ACTION","GUARD","CONSTRAINT"]; id: str
class BlockEffect(BaseModel): effect: Literal["BLOCK_ACTION"]
class AllowanceEffect(BaseModel): effect: Literal["ADD_MONETARY_ALLOWANCE"]; money: Money
ExceptionEffect=Annotated[Union[BlockEffect,AllowanceEffect],Field(discriminator="effect")]
class ExceptionRule(BaseModel):
    id: str = Field(pattern=r"^X\d+$"); target: ExceptionTarget; when: BoolExpr; effect: ExceptionEffect; source: SpanSource
class AmbiguityTarget(BaseModel):
    kind: Literal["ACTION_FIELD","PREDICATE","GUARD","CONSTRAINT","COUNTERPARTY","DEPENDENCY","NON_MATERIAL"]
    id: str|None=None; field: str|None=None
class Ambiguity(BaseModel):
    id: str = Field(pattern=r"^U\d+$"); kind: AmbiguityKind; target: AmbiguityTarget; source: SourceGrounding

class SemanticIR(BaseModel):
    schema_version: Literal["semantic-ir-v1"]="semantic-ir-v1"
    entities: list[Entity]=Field(default_factory=list)
    actions: list[Action]=Field(min_length=1)
    constraints: list[Constraint]=Field(default_factory=list)
    predicates: list[Predicate]=Field(default_factory=list)
    guards: list[Guard]=Field(default_factory=list)
    dependencies: list[Dependency]=Field(default_factory=list)
    exceptions: list[ExceptionRule]=Field(default_factory=list)
    ambiguities: list[Ambiguity]=Field(default_factory=list)

class Truth(str,Enum): TRUE="TRUE"; FALSE="FALSE"; UNKNOWN="UNKNOWN"
def truth_not(v:Truth)->Truth: return {Truth.TRUE:Truth.FALSE,Truth.FALSE:Truth.TRUE,Truth.UNKNOWN:Truth.UNKNOWN}[v]
def truth_and(values:list[Truth])->Truth:
    if Truth.FALSE in values:return Truth.FALSE
    if Truth.UNKNOWN in values:return Truth.UNKNOWN
    return Truth.TRUE
def truth_or(values:list[Truth])->Truth:
    if Truth.TRUE in values:return Truth.TRUE
    if Truth.UNKNOWN in values:return Truth.UNKNOWN
    return Truth.FALSE

def normalize_money(raw_amount:str, raw_currency:str)->tuple[Decimal,str]:
    c=raw_currency.strip().upper().replace("RS.","INR").replace("RS","INR").replace("₹","INR")
    if c not in {"INR"}: raise ValueError("IR_CURRENCY_INVALID")
    s=raw_amount.strip().lower().replace(",","").replace("₹","").replace("rs.","").replace("rs","").strip()
    mult=Decimal(1)
    if s.endswith("lakh"): mult=Decimal(100000); s=s[:-4].strip()
    elif s.endswith("lakhs"): mult=Decimal(100000); s=s[:-5].strip()
    elif s.endswith("crore"): mult=Decimal(10000000); s=s[:-5].strip()
    try: amount=Decimal(s)*mult
    except InvalidOperation as exc: raise ValueError("IR_MONEY_INVALID") from exc
    if not amount.is_finite() or amount < 0: raise ValueError("IR_MONEY_INVALID")
    return amount,c
