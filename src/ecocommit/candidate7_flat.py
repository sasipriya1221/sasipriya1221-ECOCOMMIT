from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class FactKind(str, Enum):
    ENTITY = "ENTITY"
    ACTION = "ACTION"
    CONSTRAINT = "CONSTRAINT"
    PREDICATE = "PREDICATE"
    EXCEPTION = "EXCEPTION"
    AMBIGUITY = "AMBIGUITY"


class Polarity(str, Enum):
    POSITIVE = "POSITIVE"
    NEGATED = "NEGATED"


class TextSpan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    quote: str = Field(min_length=1)
    occurrence: int = Field(default=1, ge=1)


class Fact(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text_span: TextSpan
    kind: FactKind
    polarity: Polarity


class FactBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    facts: list[Fact] = Field(min_length=1)


class LabeledFact(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^F\d{4}$")
    text_span: TextSpan
    kind: FactKind
    polarity: Polarity


class RelationKind(str, Enum):
    ACTION_OBJECT = "ACTION_OBJECT"
    ACTION_COUNTERPARTY = "ACTION_COUNTERPARTY"
    PREDICATE_SUBJECT = "PREDICATE_SUBJECT"
    CONSTRAINT_APPLIES_TO = "CONSTRAINT_APPLIES_TO"
    GUARDS_ACTION = "GUARDS_ACTION"
    BLOCKS_ACTION = "BLOCKS_ACTION"
    AFTER_COMPLETION = "AFTER_COMPLETION"
    AFTER_SUCCESS = "AFTER_SUCCESS"
    EXCEPTION_TARGET = "EXCEPTION_TARGET"
    EXCEPTION_WHEN = "EXCEPTION_WHEN"
    AMBIGUITY_TARGET = "AMBIGUITY_TARGET"
    ALL_OF = "ALL_OF"
    ANY_OF = "ANY_OF"


class Relation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: RelationKind
    left: str = Field(pattern=r"^F\d{4}$")
    right: str = Field(pattern=r"^F\d{4}$")

    @model_validator(mode="after")
    def no_self_relation(self) -> "Relation":
        if self.left == self.right:
            raise ValueError("C7_SELF_RELATION")
        return self


class RelationBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    relations: list[Relation] = Field(default_factory=list)


def assign_fact_ids(batch: FactBatch) -> tuple[LabeledFact, ...]:
    return tuple(
        LabeledFact(
            id=f"F{index:04d}",
            text_span=fact.text_span,
            kind=fact.kind,
            polarity=fact.polarity,
        )
        for index, fact in enumerate(batch.facts, start=1)
    )


_ALLOWED_KIND_PAIRS: dict[RelationKind, set[tuple[FactKind, FactKind]]] = {
    RelationKind.ACTION_OBJECT: {(FactKind.ACTION, FactKind.ENTITY)},
    RelationKind.ACTION_COUNTERPARTY: {(FactKind.ACTION, FactKind.ENTITY)},
    RelationKind.PREDICATE_SUBJECT: {(FactKind.PREDICATE, FactKind.ENTITY)},
    RelationKind.CONSTRAINT_APPLIES_TO: {(FactKind.CONSTRAINT, FactKind.ACTION)},
    RelationKind.GUARDS_ACTION: {(FactKind.PREDICATE, FactKind.ACTION)},
    RelationKind.BLOCKS_ACTION: {(FactKind.PREDICATE, FactKind.ACTION)},
    RelationKind.AFTER_COMPLETION: {(FactKind.ACTION, FactKind.ACTION)},
    RelationKind.AFTER_SUCCESS: {(FactKind.ACTION, FactKind.ACTION)},
    RelationKind.EXCEPTION_TARGET: {
        (FactKind.EXCEPTION, FactKind.ACTION),
        (FactKind.EXCEPTION, FactKind.CONSTRAINT),
    },
    RelationKind.EXCEPTION_WHEN: {(FactKind.PREDICATE, FactKind.EXCEPTION)},
    RelationKind.AMBIGUITY_TARGET: {
        (FactKind.AMBIGUITY, FactKind.ACTION),
        (FactKind.AMBIGUITY, FactKind.CONSTRAINT),
        (FactKind.AMBIGUITY, FactKind.PREDICATE),
        (FactKind.AMBIGUITY, FactKind.ENTITY),
    },
    RelationKind.ALL_OF: {(FactKind.PREDICATE, FactKind.PREDICATE)},
    RelationKind.ANY_OF: {(FactKind.PREDICATE, FactKind.PREDICATE)},
}


def validate_relations(facts: tuple[LabeledFact, ...], batch: RelationBatch) -> None:
    by_id = {fact.id: fact for fact in facts}
    seen: set[tuple[RelationKind, str, str]] = set()
    logic_pairs: dict[frozenset[str], RelationKind] = {}

    for relation in batch.relations:
        if relation.left not in by_id or relation.right not in by_id:
            raise ValueError("C7_UNKNOWN_FACT_REFERENCE")
        pair = (by_id[relation.left].kind, by_id[relation.right].kind)
        if pair not in _ALLOWED_KIND_PAIRS[relation.kind]:
            raise ValueError("C7_RELATION_KIND_MISMATCH")
        key = (relation.kind, relation.left, relation.right)
        if key in seen:
            raise ValueError("C7_DUPLICATE_RELATION")
        seen.add(key)

        if relation.kind in {RelationKind.ALL_OF, RelationKind.ANY_OF}:
            unordered = frozenset({relation.left, relation.right})
            previous = logic_pairs.get(unordered)
            if previous is not None and previous != relation.kind:
                raise ValueError("C7_CONTRADICTORY_LOGIC_RELATION")
            logic_pairs[unordered] = relation.kind


def grounded_span(instruction: str, span: TextSpan) -> tuple[int, int]:
    cursor = 0
    start = -1
    for _ in range(span.occurrence):
        start = instruction.find(span.quote, cursor)
        if start < 0:
            raise ValueError("C7_UNGROUNDED_SPAN")
        cursor = start + len(span.quote)
    return start, start + len(span.quote)
