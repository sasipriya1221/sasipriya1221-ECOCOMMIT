from __future__ import annotations

from enum import Enum
from hashlib import sha256
from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator


class ClauseType(str, Enum):
    PRODUCT = "PRODUCT"
    QUANTITY = "QUANTITY"
    AMOUNT = "AMOUNT"
    COUNTERPARTY = "COUNTERPARTY"
    TEMPORAL = "TEMPORAL"
    CERTIFICATION = "CERTIFICATION"
    REVERSIBILITY = "REVERSIBILITY"
    AUTHORIZATION = "AUTHORIZATION"
    CONDITION = "CONDITION"
    EXCEPTION = "EXCEPTION"
    DEPENDENCY = "DEPENDENCY"


class Provenance(str, Enum):
    EXPLICIT_USER = "EXPLICIT_USER"
    INCORPORATED_POLICY = "INCORPORATED_POLICY"
    AUTHORITATIVE_EVIDENCE = "AUTHORITATIVE_EVIDENCE"
    INFERENCE = "INFERENCE"


class Hardness(str, Enum):
    HARD = "HARD"
    SOFT = "SOFT"


class DecisionStatus(str, Enum):
    VALIDATED = "VALIDATED"
    CLARIFICATION_REQUIRED = "CLARIFICATION_REQUIRED"
    REJECTED = "REJECTED"


class SourceSpan(BaseModel):
    text: str = Field(min_length=1)
    start: int = Field(ge=0)
    end: int = Field(gt=0)

    @model_validator(mode="after")
    def valid_bounds(self):
        if self.end <= self.start:
            raise ValueError("source span end must be greater than start")
        return self


class EconomicClause(BaseModel):
    clause_id: str = Field(min_length=1)
    clause_type: ClauseType
    normalized_value: str = Field(min_length=1)
    source_span: SourceSpan | None = None
    provenance: Provenance
    materiality: Annotated[float, Field(ge=0.0, le=1.0)]
    confidence: Annotated[float, Field(ge=0.0, le=1.0)]
    hardness: Hardness = Hardness.HARD
    policy_class: str | None = None
    negated: bool = False
    depends_on: list[str] = Field(default_factory=list)
    exception_to: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def recover_grounded_explicit_scores(cls, value):
        """Repair omitted scoring metadata only for already-grounded explicit clauses.

        Some JSON-object providers occasionally omit `materiality` and `confidence`
        even when they return an otherwise complete clause.  A clause that already
        declares EXPLICIT_USER provenance and carries a non-empty source span can be
        repaired conservatively without inventing a new constraint: the parent
        contract still verifies that span exactly against the original instruction.
        We intentionally do not repair ungrounded or inferred clauses.
        """
        if not isinstance(value, dict):
            return value

        repaired = dict(value)
        span = repaired.get("source_span")
        provenance = repaired.get("provenance")
        grounded_explicit = (
            provenance in {Provenance.EXPLICIT_USER, Provenance.EXPLICIT_USER.value}
            and isinstance(span, dict)
            and isinstance(span.get("text"), str)
            and bool(span["text"].strip())
        )
        if grounded_explicit:
            repaired.setdefault("materiality", 1.0)
            repaired.setdefault("confidence", 1.0)
        return repaired

    @model_validator(mode="after")
    def inference_cannot_expand_authority(self):
        if (
            self.provenance == Provenance.INFERENCE
            and self.clause_type in {ClauseType.AMOUNT, ClauseType.AUTHORIZATION, ClauseType.COUNTERPARTY}
            and self.hardness == Hardness.HARD
        ):
            raise ValueError("INFERENCE cannot create hard financial authority constraints")
        return self


class EconomicIntentContract(BaseModel):
    instruction: str = Field(min_length=1)
    clauses: list[EconomicClause] = Field(min_length=1)
    schema_version: Literal["0.1"] = "0.1"

    @model_validator(mode="after")
    def validate_graph(self):
        ids = [c.clause_id for c in self.clauses]
        if len(ids) != len(set(ids)):
            raise ValueError("clause ids must be unique")
        id_set = set(ids)
        for clause in self.clauses:
            missing = (set(clause.depends_on) | set(clause.exception_to)) - id_set
            if missing:
                raise ValueError(f"unknown referenced clause ids: {sorted(missing)}")
            if clause.source_span is not None:
                span = clause.source_span
                if span.end > len(self.instruction):
                    raise ValueError("source span exceeds instruction length")
                if self.instruction[span.start:span.end] != span.text:
                    raise ValueError("source span text does not match instruction")
        return self

    def canonical_hash(self) -> str:
        payload = self.model_dump_json(exclude_none=True, by_alias=True)
        return sha256(payload.encode("utf-8")).hexdigest()
